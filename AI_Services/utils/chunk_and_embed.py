"""
VidRival — chunk_embed.py
Chunks transcript segments using LangChain RecursiveCharacterTextSplitter,
embeds with BGE-M3 via HuggingFace Inference API,
and upserts to Pinecone with full metadata for filtered RAG retrieval.

Pipeline:
  VideoData → LangChain text splitter → BGE-M3 embeddings (HF API) → Pinecone upsert

Dependencies:
  pip install langchain langchain-huggingface pinecone python-dotenv tenacity
"""

import os
import re
import time
import hashlib
from typing import TypedDict
from dotenv import load_dotenv

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from pinecone import Pinecone, ServerlessSpec
from tenacity import retry, wait_exponential, stop_after_attempt

load_dotenv()

# ─────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────

PINECONE_API_KEY   = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX     = os.getenv("PINECONE_INDEX_NAME", "vidrival-index")
HF_TOKEN           = os.getenv("HF_TOKEN")
EMBEDDING_MODEL    = "BAAI/bge-m3"   # used only for display/logging
EMBED_DIM          = 1024             # BGE-M3 output dimension
CHUNK_TOKEN_SIZE   = 512              # max tokens per chunk (word-based estimate)
CHUNK_OVERLAP      = 64               # overlap between consecutive chunks
PINECONE_BATCH     = 100              # vectors per upsert batch
PINECONE_CLOUD     = "aws"
PINECONE_REGION    = "us-east-1"      # Pinecone free tier is us-east-1

# ─────────────────────────────────────────────────────────────
#  Singletons (loaded once, reused across calls)
# ─────────────────────────────────────────────────────────────

_embed_model: HuggingFaceEndpointEmbeddings | None = None
_pinecone_index = None


def _get_embed_model() -> HuggingFaceEndpointEmbeddings:
    """Returns singleton HuggingFace Inference API embeddings client."""
    global _embed_model
    if _embed_model is None:
        if not HF_TOKEN:
            raise ValueError("HF_TOKEN not set in .env")
        print(f"[chunk_embed] Connecting to HuggingFace Inference API ({EMBEDDING_MODEL})...")
        _embed_model = HuggingFaceEndpointEmbeddings(
            model=EMBEDDING_MODEL,
            huggingfacehub_api_token=HF_TOKEN,
        )
        print(f"[chunk_embed] HF client ready.")
    return _embed_model


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        if not PINECONE_API_KEY:
            raise ValueError("PINECONE_API_KEY not set in .env")

        pc = Pinecone(api_key=PINECONE_API_KEY)

        # Create index if it doesn't exist
        existing = [idx.name for idx in pc.list_indexes()]
        if PINECONE_INDEX not in existing:
            print(f"[chunk_embed] Creating Pinecone index '{PINECONE_INDEX}'...")
            pc.create_index(
                name      = PINECONE_INDEX,
                dimension = EMBED_DIM,
                metric    = "cosine",
                spec      = ServerlessSpec(
                    cloud  = PINECONE_CLOUD,
                    region = PINECONE_REGION,
                ),
            )
            # Wait for index to be ready
            while not pc.describe_index(PINECONE_INDEX).status["ready"]:
                print("[chunk_embed] Waiting for index to be ready...")
                time.sleep(2)
            print(f"[chunk_embed] Index '{PINECONE_INDEX}' created.")
        else:
            print(f"[chunk_embed] Using existing index '{PINECONE_INDEX}'.")

        _pinecone_index = pc.Index(PINECONE_INDEX)
    return _pinecone_index


# ─────────────────────────────────────────────────────────────
#  Chunk type
# ─────────────────────────────────────────────────────────────

class Chunk(TypedDict):
    chunk_id:        str    # unique ID: "{video_id}_chunk_{n}"
    video_id:        str    # "A" or "B"
    text:            str    # chunk text
    token_count:     int
    chunk_index:     int
    timestamp_start: float  # seconds into video
    timestamp_end:   float
    # metadata carried forward from VideoData
    platform:        str
    url:             str
    title:           str
    creator:         str
    follower_count:  int
    views:           int
    likes:           int
    comments:        int
    engagement_rate: float
    upload_date:     str
    duration:        int
    hashtags:        str    # stored as space-joined string for Pinecone


# ─────────────────────────────────────────────────────────────
#  Step 1: Chunking
# ─────────────────────────────────────────────────────────────

# ── LangChain text splitter (singleton) ──
_text_splitter: RecursiveCharacterTextSplitter | None = None


def _get_text_splitter() -> RecursiveCharacterTextSplitter:
    """
    Returns a singleton RecursiveCharacterTextSplitter.

    Why RecursiveCharacterTextSplitter:
    - Tries to split on paragraph → sentence → word boundaries in that order
    - Never cuts mid-sentence if it can avoid it
    - chunk_size in characters (~2000 chars ≈ 400-500 words ≈ 512 tokens for speech)
    - chunk_overlap in characters (~300 chars ≈ 60 tokens)
    """
    global _text_splitter
    if _text_splitter is None:
        _text_splitter = RecursiveCharacterTextSplitter(
            chunk_size         = 2000,    # ~512 tokens for conversational English
            chunk_overlap      = 300,     # ~64 token overlap between chunks
            length_function    = len,     # character-based length
            separators         = [
                "\n\n",   # paragraph break — highest priority
                "\n",      # line break
                ". ",       # sentence end
                "? ",       # question end
                "! ",       # exclamation end
                ", ",       # clause break
                " ",        # word break — last resort
                "",         # character break — absolute fallback
            ],
        )
    return _text_splitter


def _clean_transcript(text: str) -> str:
    """Remove noise tokens from transcript text before splitting."""
    text = re.sub(r"\[.*?\]", "", text)   # [Music], [Applause], [Laughter]
    text = re.sub(r"♪[^♪]*♪", "", text)    # ♪ song lyrics ♪
    text = re.sub(r"\s+", " ", text)       # collapse multiple spaces/newlines
    return text.strip()


def _build_timestamped_full_text(segments: list[dict]) -> tuple[str, list[dict]]:
    """
    Joins all transcript segments into one full text string.
    Also returns a lookup table: character_offset → {start, end} timestamp
    so we can map chunk positions back to video timestamps after splitting.
    """
    full_text = ""
    offset_map = []   # [{char_start, char_end, ts_start, ts_end}]

    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        char_start = len(full_text)
        full_text += text + " "
        char_end   = len(full_text)
        offset_map.append({
            "char_start": char_start,
            "char_end":   char_end,
            "ts_start":   seg.get("start", 0.0),
            "ts_end":     seg.get("end",   0.0),
        })

    return full_text.strip(), offset_map


def _find_timestamp_for_chunk(
    chunk_text: str,
    full_text: str,
    offset_map: list[dict],
) -> tuple[float, float]:
    """
    Find the video timestamp for a chunk by locating its position
    in the full text and looking up the offset map.
    Returns (timestamp_start, timestamp_end) in seconds.
    """
    if not offset_map:
        return 0.0, 0.0

    # Find where this chunk starts in the full text
    pos = full_text.find(chunk_text[:80])  # use first 80 chars to locate
    if pos == -1:
        # Fallback: return timestamps of first and last segment
        return offset_map[0]["ts_start"], offset_map[-1]["ts_end"]

    chunk_end_pos = pos + len(chunk_text)

    # Find segments that overlap with this character range
    ts_start = offset_map[-1]["ts_start"]  # default to last
    ts_end   = offset_map[0]["ts_end"]     # default to first

    for entry in offset_map:
        if entry["char_start"] <= pos < entry["char_end"]:
            ts_start = entry["ts_start"]
        if entry["char_start"] < chunk_end_pos <= entry["char_end"]:
            ts_end = entry["ts_end"]
            break

    return ts_start, ts_end


def _chunk_transcript(video_data: dict) -> list[Chunk]:
    """
    Splits transcript into chunks using LangChain RecursiveCharacterTextSplitter.

    Flow:
    1. Clean noise ([Music], ♪) from all segments
    2. Join all segments into one full text string
    3. Build a char-offset → timestamp lookup table
    4. Run LangChain splitter on the full text
    5. Map each chunk back to its video timestamp
    6. Attach all video metadata to every chunk
    """
    video_id = video_data["video_id"]
    segments = video_data.get("transcript_chunks", [])

    if not segments:
        # Fallback: treat full transcript string as single segment
        segments = [{"text": video_data.get("transcript", ""), "start": 0.0, "end": 0.0}]

    # ── Step 1: Clean ──
    cleaned_segments = []
    for seg in segments:
        cleaned_text = _clean_transcript(seg.get("text", ""))
        if cleaned_text:
            cleaned_segments.append({**seg, "text": cleaned_text})

    if not cleaned_segments:
        print("[chunk_embed] Warning: all segments empty after cleaning.")
        return []

    # ── Step 2 + 3: Join text + build offset map ──
    full_text, offset_map = _build_timestamped_full_text(cleaned_segments)

    if not full_text:
        print("[chunk_embed] Warning: full_text is empty.")
        return []

    # ── Step 4: LangChain split ──
    splitter    = _get_text_splitter()
    split_texts = splitter.split_text(full_text)

    print(f"[chunk_embed] Video {video_id}: LangChain produced {len(split_texts)} chunks "
          f"from {len(cleaned_segments)} segments.")

    # ── Step 5 + 6: Build Chunk objects ──
    chunks: list[Chunk] = []
    for idx, chunk_text in enumerate(split_texts):
        chunk_text = chunk_text.strip()
        if not chunk_text:
            continue

        # Map back to timestamp
        ts_start, ts_end = _find_timestamp_for_chunk(chunk_text, full_text, offset_map)

        # Stable chunk ID
        chunk_hash = hashlib.md5(
            f"{video_id}_{idx}_{chunk_text[:50]}".encode()
        ).hexdigest()[:8]
        chunk_id = f"{video_id}_chunk_{idx:04d}_{chunk_hash}"

        chunks.append(Chunk(
            chunk_id        = chunk_id,
            video_id        = video_id,
            text            = chunk_text,
            token_count     = len(chunk_text.split()),   # word count (display only)
            chunk_index     = idx,
            timestamp_start = ts_start,
            timestamp_end   = ts_end,
            platform        = video_data.get("platform", "unknown"),
            url             = video_data.get("url", ""),
            title           = video_data.get("title", ""),
            creator         = video_data.get("creator", ""),
            follower_count  = video_data.get("follower_count", 0),
            views           = video_data.get("views", 0),
            likes           = video_data.get("likes", 0),
            comments        = video_data.get("comments", 0),
            engagement_rate = video_data.get("engagement_rate", 0.0),
            upload_date     = video_data.get("upload_date", ""),
            duration        = video_data.get("duration", 0),
            hashtags        = " ".join(video_data.get("hashtags", [])),
        ))

    print(f"[chunk_embed] Video {video_id}: {len(chunks)} chunks built.")
    return chunks


# ─────────────────────────────────────────────────────────────
#  Step 2: Embedding
# ─────────────────────────────────────────────────────────────

@retry(
    wait=wait_exponential(min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _embed_texts_with_retry(model: HuggingFaceEndpointEmbeddings, texts: list[str]) -> list[list[float]]:
    """
    Calls HuggingFace Inference API with automatic retry on rate limits (429).
    Retries up to 3 times with exponential backoff: 2s → 4s → 8s.
    """
    return model.embed_documents(texts)


def _embed_chunks(chunks: list[Chunk]) -> list[tuple[Chunk, list[float]]]:
    """
    Embed all chunks via HuggingFace Inference API (BGE-M3).

    BGE-M3 tip: prefix with 'Represent this sentence:' on the document side
    for better retrieval recall (~3-5% improvement).

    HF free tier limit: ~1000 requests/day.
    Each call embeds all chunks in one batch request.
    """
    if not chunks:
        return []

    model = _get_embed_model()

    # BGE-M3 passage prefix — only on document side, not query side
    texts = [f"Represent this sentence: {c['text']}" for c in chunks]

    print(f"[chunk_embed] Embedding {len(chunks)} chunks via HuggingFace API ({EMBEDDING_MODEL})...")

    embeddings = _embed_texts_with_retry(model, texts)

    print(f"[chunk_embed] Got {len(embeddings)} embeddings (dim={len(embeddings[0]) if embeddings else 0}).")
    return list(zip(chunks, embeddings))


# ─────────────────────────────────────────────────────────────
#  Step 3: Pinecone upsert
# ─────────────────────────────────────────────────────────────

def _upsert_to_pinecone(chunk_embeddings: list[tuple[Chunk, list[float]]]) -> int:
    """
    Upsert chunk vectors to Pinecone in batches of PINECONE_BATCH.
    Returns total number of vectors upserted.

    Pinecone metadata fields (all filterable):
      - video_id        → filter by "A" or "B" in RAG retrieval
      - chunk_index     → used for citation ordering
      - timestamp_start → surfaced in citations "[Video A, 01:24]"
      - engagement_rate → available to LLM for comparison queries
      - creator, views, likes, comments, follower_count → metadata queries
    """
    if not chunk_embeddings:
        return 0

    index = _get_pinecone_index()
    total_upserted = 0

    # Build Pinecone vector records
    vectors = []
    for chunk, embedding in chunk_embeddings:
        vectors.append({
            "id":     chunk["chunk_id"],
            "values": embedding,
            "metadata": {
                # ── Retrieval filters ──
                "video_id":        chunk["video_id"],
                "chunk_index":     chunk["chunk_index"],

                # ── Text (for LLM context) ──
                "text":            chunk["text"],

                # ── Citation data ──
                "timestamp_start": chunk["timestamp_start"],
                "timestamp_end":   chunk["timestamp_end"],
                "title":           chunk["title"],
                "url":             chunk["url"],

                # ── Engagement metadata ──
                "engagement_rate": chunk["engagement_rate"],
                "views":           chunk["views"],
                "likes":           chunk["likes"],
                "comments":        chunk["comments"],
                "creator":         chunk["creator"],
                "follower_count":  chunk["follower_count"],
                "platform":        chunk["platform"],
                "upload_date":     chunk["upload_date"],
                "duration":        chunk["duration"],
                "hashtags":        chunk["hashtags"],
            },
        })

    # ── Batch upsert ──
    for batch_start in range(0, len(vectors), PINECONE_BATCH):
        batch = vectors[batch_start : batch_start + PINECONE_BATCH]
        index.upsert(vectors=batch)
        total_upserted += len(batch)
        print(f"[chunk_embed] Upserted {total_upserted}/{len(vectors)} vectors...")

    print(f"[chunk_embed] ✓ Done. {total_upserted} vectors in Pinecone index '{PINECONE_INDEX}'.")
    return total_upserted


# ─────────────────────────────────────────────────────────────
#  Public function — called directly or via LangGraph
# ─────────────────────────────────────────────────────────────

def chunk_and_embed(video_data: dict) -> dict:
    """
    Full pipeline: VideoData → chunks → embeddings → Pinecone.

    Args:
        video_data: VideoData dict from fetch_video()

    Returns:
        Summary dict with chunk count, vector count, and first 3 chunk previews

    Example:
        from fetch_video import fetch_video
        from chunk_embed import chunk_and_embed

        data   = fetch_video("https://youtube.com/watch?v=...", "A")
        result = chunk_and_embed(data)
        print(result["chunks_created"])   # 42
        print(result["vectors_upserted"]) # 42
    """
    video_id = video_data.get("video_id", "?")
    print(f"\n[chunk_embed] ── Starting pipeline for Video {video_id} ──")

    # Step 1: Chunk
    chunks = _chunk_transcript(video_data)
    if not chunks:
        return {
            "video_id":         video_id,
            "chunks_created":   0,
            "vectors_upserted": 0,
            "error":            "No chunks produced — transcript may be empty",
        }

    # Step 2: Embed
    chunk_embeddings = _embed_chunks(chunks)

    # Step 3: Upsert to Pinecone
    total_upserted = _upsert_to_pinecone(chunk_embeddings)

    summary = {
        "video_id":         video_id,
        "chunks_created":   len(chunks),
        "vectors_upserted": total_upserted,
        "token_stats": {
            "total_tokens": sum(c["token_count"] for c in chunks),
            "avg_tokens":   round(sum(c["token_count"] for c in chunks) / len(chunks), 1),
            "min_tokens":   min(c["token_count"] for c in chunks),
            "max_tokens":   max(c["token_count"] for c in chunks),
        },
        "chunk_previews": [
            {
                "chunk_id":   c["chunk_id"],
                "index":      c["chunk_index"],
                "tokens":     c["token_count"],
                "timestamp":  f"{c['timestamp_start']:.1f}s – {c['timestamp_end']:.1f}s",
                "preview":    c["text"][:120] + "..." if len(c["text"]) > 120 else c["text"],
            }
            for c in chunks[:3]  # first 3 chunks only
        ],
    }

    print(f"[chunk_embed] ── Video {video_id} complete: "
          f"{len(chunks)} chunks, {total_upserted} vectors ──\n")
    return summary


# ─────────────────────────────────────────────────────────────
#  LangGraph node wrapper
# ─────────────────────────────────────────────────────────────

def chunk_embed_node(state: dict) -> dict:
    """
    LangGraph node. Reads video_a and video_b from state,
    runs chunk_and_embed for both, writes summaries back.

    State keys consumed:  video_a, video_b
    State keys produced:  embed_summary_a, embed_summary_b, ingestion_complete
    """
    video_a = state.get("video_a")
    video_b = state.get("video_b")

    if not video_a or not video_b:
        raise ValueError("chunk_embed_node requires both video_a and video_b in state")

    summary_a = chunk_and_embed(video_a)
    summary_b = chunk_and_embed(video_b)

    return {
        **state,
        "embed_summary_a":   summary_a,
        "embed_summary_b":   summary_b,
        "ingestion_complete": True,
    }


# ─────────────────────────────────────────────────────────────
#  Quick test — python chunk_embed.py
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, os.path.dirname(__file__))

    from utils.transcribe import fetch_video

    TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    print("=" * 60)
    print("Step 1: Fetching video...")
    print("=" * 60)
    video_data = fetch_video(TEST_URL, "A")
    print(f"Got transcript: {len(video_data['transcript_chunks'])} segments")

    print("\n" + "=" * 60)
    print("Step 2: Chunk + Embed + Upsert...")
    print("=" * 60)
    result = chunk_and_embed(video_data)

    print("\n" + "=" * 60)
    print("Result:")
    print("=" * 60)
    print(json.dumps(result, indent=2))