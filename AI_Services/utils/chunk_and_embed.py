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
from functools import lru_cache

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX   = os.getenv("PINECONE_INDEX_NAME", "engagex")
HF_TOKEN         = os.getenv("HUGGINGFACEHUB_API_TOKEN")
EMBEDDING_MODEL  = "BAAI/bge-m3"
EMBED_DIM        = 1024
CHUNK_TOKEN_SIZE = 512
CHUNK_OVERLAP    = 64
PINECONE_BATCH   = 100
PINECONE_CLOUD   = "aws"
PINECONE_REGION  = "us-east-1"

_embed_model: HuggingFaceEndpointEmbeddings | None = None
_pinecone_index = None


def _get_embed_model() -> HuggingFaceEndpointEmbeddings:
    """Returns a singleton HuggingFace embeddings client."""
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
            while not pc.describe_index(PINECONE_INDEX).status["ready"]:
                print("[chunk_embed] Waiting for index to be ready...")
                time.sleep(2)
            print(f"[chunk_embed] Index '{PINECONE_INDEX}' created.")
        else:
            print(f"[chunk_embed] Using existing index '{PINECONE_INDEX}'.")

        _pinecone_index = pc.Index(PINECONE_INDEX)
    return _pinecone_index


class Chunk(TypedDict):
    chunk_id:        str
    video_id:        str
    text:            str
    token_count:     int
    chunk_index:     int
    timestamp_start: float
    timestamp_end:   float
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
    hashtags:        str


_text_splitter: RecursiveCharacterTextSplitter | None = None


def _get_text_splitter() -> RecursiveCharacterTextSplitter:
    """Returns a singleton RecursiveCharacterTextSplitter configured for transcript text."""
    global _text_splitter
    if _text_splitter is None:
        _text_splitter = RecursiveCharacterTextSplitter(
            chunk_size    = 2000,
            chunk_overlap = 300,
            length_function = len,
            separators = [
                "\n\n",
                "\n",
                ". ",
                "? ",
                "! ",
                ", ",
                " ",
                "",
            ],
        )
    return _text_splitter


def _clean_transcript(text: str) -> str:
    """Strips noise tokens like [Music] and ♪ lyrics ♪ before splitting."""
    text = re.sub(r"\[.*?\]", "", text)
    text = re.sub(r"♪[^♪]*♪", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_timestamped_full_text(segments: list[dict]) -> tuple[str, list[dict]]:
    """
    Joins all transcript segments into one string and returns a
    character-offset to timestamp lookup table alongside it.
    """
    full_text  = ""
    offset_map = []

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
    Locates a chunk's position in the full transcript text and returns
    its (start, end) timestamp in seconds.
    """
    if not offset_map:
        return 0.0, 0.0

    pos = full_text.find(chunk_text[:80])
    if pos == -1:
        return offset_map[0]["ts_start"], offset_map[-1]["ts_end"]

    chunk_end_pos = pos + len(chunk_text)

    ts_start = offset_map[-1]["ts_start"]
    ts_end   = offset_map[0]["ts_end"]

    for entry in offset_map:
        if entry["char_start"] <= pos < entry["char_end"]:
            ts_start = entry["ts_start"]
        if entry["char_start"] < chunk_end_pos <= entry["char_end"]:
            ts_end = entry["ts_end"]
            break

    return ts_start, ts_end


def _chunk_transcript(video_data: dict) -> list[Chunk]:
    """Cleans, joins, splits, and timestamps the transcript into Chunk objects."""
    video_id = video_data["video_id"]
    segments = video_data.get("transcript_chunks", [])

    if not segments:
        segments = [{"text": video_data.get("transcript", ""), "start": 0.0, "end": 0.0}]

    cleaned_segments = []
    for seg in segments:
        cleaned_text = _clean_transcript(seg.get("text", ""))
        if cleaned_text:
            cleaned_segments.append({**seg, "text": cleaned_text})

    if not cleaned_segments:
        print("[chunk_embed] Warning: all segments empty after cleaning.")
        return []

    full_text, offset_map = _build_timestamped_full_text(cleaned_segments)

    if not full_text:
        print("[chunk_embed] Warning: full_text is empty.")
        return []

    splitter    = _get_text_splitter()
    split_texts = splitter.split_text(full_text)

    print(f"[chunk_embed] Video {video_id}: LangChain produced {len(split_texts)} chunks "
          f"from {len(cleaned_segments)} segments.")

    chunks: list[Chunk] = []
    for idx, chunk_text in enumerate(split_texts):
        chunk_text = chunk_text.strip()
        if not chunk_text:
            continue

        ts_start, ts_end = _find_timestamp_for_chunk(chunk_text, full_text, offset_map)

        chunk_hash = hashlib.md5(
            f"{video_id}_{idx}_{chunk_text[:50]}".encode()
        ).hexdigest()[:8]
        chunk_id = f"{video_id}_chunk_{idx:04d}_{chunk_hash}"

        chunks.append(Chunk(
            chunk_id        = chunk_id,
            video_id        = video_id,
            text            = chunk_text,
            token_count     = len(chunk_text.split()),
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


@retry(
    wait=wait_exponential(min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _embed_texts_with_retry(model: HuggingFaceEndpointEmbeddings, texts: list[str]) -> list[list[float]]:
    """Calls the HuggingFace API with automatic retry on rate limit errors."""
    return model.embed_documents(texts)


# Cache batch embeddings by joining texts into a single key. We store tuples
# (immutable) so they are compatible with lru_cache. This reduces repeated
# HF calls for identical chunk batches.
@lru_cache(maxsize=1024)
def _embed_texts_cached_key(texts_key: str) -> tuple:
    texts = texts_key.split('\x1f') if texts_key else []
    model = _get_embed_model()
    # Use cached batch embedding when possible
    key = "\x1f".join(texts)
    embeddings = [list(e) for e in _embed_texts_cached_key(key)]
    # Convert embeddings to tuple-of-tuples for caching
    return tuple(tuple(e) for e in embeddings)


def _embed_chunks(chunks: list[Chunk]) -> list[tuple[Chunk, list[float]]]:
    """Embeds all chunks via BGE-M3 on the HuggingFace Inference API."""
    if not chunks:
        return []

    model = _get_embed_model()
    texts = [f"Represent this sentence: {c['text']}" for c in chunks]

    print(f"[chunk_embed] Embedding {len(chunks)} chunks via HuggingFace API ({EMBEDDING_MODEL})...")

    embeddings = _embed_texts_with_retry(model, texts)

    print(f"[chunk_embed] Got {len(embeddings)} embeddings (dim={len(embeddings[0]) if embeddings else 0}).")
    return list(zip(chunks, embeddings))


def _upsert_to_pinecone(chunk_embeddings: list[tuple[Chunk, list[float]]]) -> int:
    """Upserts all chunk vectors to Pinecone in batches. Returns total upserted count."""
    if not chunk_embeddings:
        return 0

    index          = _get_pinecone_index()
    total_upserted = 0

    vectors = []
    for chunk, embedding in chunk_embeddings:
        vectors.append({
            "id":     chunk["chunk_id"],
            "values": embedding,
            "metadata": {
                "video_id":        chunk["video_id"],
                "chunk_index":     chunk["chunk_index"],
                "text":            chunk["text"],
                "timestamp_start": chunk["timestamp_start"],
                "timestamp_end":   chunk["timestamp_end"],
                "title":           chunk["title"],
                "url":             chunk["url"],
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

    for batch_start in range(0, len(vectors), PINECONE_BATCH):
        batch = vectors[batch_start : batch_start + PINECONE_BATCH]
        index.upsert(vectors=batch)
        total_upserted += len(batch)
        print(f"[chunk_embed] Upserted {total_upserted}/{len(vectors)} vectors...")

    print(f"[chunk_embed] ✓ Done. {total_upserted} vectors in Pinecone index '{PINECONE_INDEX}'.")
    return total_upserted


def chunk_and_embed(video_data: dict) -> dict:
    """Runs the full pipeline: transcript → chunks → embeddings → Pinecone upsert."""
    video_id = video_data.get("video_id", "?")
    print(f"\n[chunk_embed] ── Starting pipeline for Video {video_id} ──")

    chunks = _chunk_transcript(video_data)
    if not chunks:
        return {
            "video_id":         video_id,
            "chunks_created":   0,
            "vectors_upserted": 0,
            "error":            "No chunks produced — transcript may be empty",
        }

    chunk_embeddings = _embed_chunks(chunks)
    total_upserted   = _upsert_to_pinecone(chunk_embeddings)

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
                "chunk_id":  c["chunk_id"],
                "index":     c["chunk_index"],
                "tokens":    c["token_count"],
                "timestamp": f"{c['timestamp_start']:.1f}s – {c['timestamp_end']:.1f}s",
                "preview":   c["text"][:120] + "..." if len(c["text"]) > 120 else c["text"],
            }
            for c in chunks[:3]
        ],
    }

    print(f"[chunk_embed] ── Video {video_id} complete: "
          f"{len(chunks)} chunks, {total_upserted} vectors ──\n")
    return summary
