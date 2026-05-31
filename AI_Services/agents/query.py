"""
VidRival — query_graph.py
LangGraph query pipeline: per user turn, fully streaming

Flow:
    START
      │
      ▼
  validate_session_node     ← checks Redis session exists
      │
      ▼
  query_rewriter_node       ← rewrites query with HyDE for better retrieval
      │
      ▼
  intent_router_node        ← classifies: compare | single | metadata | suggest
      │
      ├── "metadata" ──────► metadata_lookup_node   ← Redis only, no Pinecone
      │                             │
      └── everything else ──► retrieve_node          ← Pinecone vector search
                                    │
                                    ▼
                              rerank_node             ← scores + filters chunks
                                    │
                                    └──────────────────┐
                                                       ▼
                                              stream_response_node  ← Groq Llama SSE
                                                       │
                                                       ▼
                                              update_memory_node    ← append to history
                                                       │
                                                       ▼
                                                     END

Dependencies:
  pip install langchain langchain-groq langgraph upstash-redis pinecone
              langchain-huggingface python-dotenv
"""

import os
import json
import re
from typing import TypedDict, Optional, Literal, Annotated
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from utils.cache_session import (
    get_both_metadata,
    get_engagement_comparison,
    get_video_metadata,
    session_exists,
    load_history,
    append_turn,
    clear_history,
    get_history_length,
)
from pinecone import Pinecone

load_dotenv()

# ─────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────

GROQ_API_KEY     = os.getenv("GROQ_API_KEY")
HF_TOKEN         = os.getenv("HF_TOKEN")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX   = os.getenv("PINECONE_INDEX_NAME", "vidrival-index")
EMBEDDING_MODEL  = "BAAI/bge-m3"

# Groq free tier models
# llama-3.3-70b-versatile -> best quality, use for generation
# llama-3.1-8b-instant    -> fastest, use for routing + rewriting
GROQ_MODEL_FAST = "llama-3.1-8b-instant"     # routing, rewriting, reranking
GROQ_MODEL_PRO  = "llama-3.3-70b-versatile"  # final response generation

TOP_K_SINGLE       = 8    # chunks retrieved for single-video queries
TOP_K_DUAL         = 6    # chunks per video for compare/suggest queries
TOP_K_AFTER_RERANK = 5    # chunks kept after reranking

# ─────────────────────────────────────────────────────────────
#  Singletons
# ─────────────────────────────────────────────────────────────

_llm_flash: ChatGroq | None = None   # fast: routing + rewriting + reranking
_llm_pro: ChatGroq | None = None     # smart: final response generation
_embed_model: HuggingFaceEndpointEmbeddings | None = None
_pinecone_index = None


def _get_llm_flash() -> ChatGroq:
    """Llama 3.1 8B Instant via Groq - ultra fast for routing, rewriting, reranking.
    Groq free tier: 14,400 req/day, 500,000 tokens/min.
    """
    global _llm_flash
    if _llm_flash is None:
        _llm_flash = ChatGroq(
            model=GROQ_MODEL_FAST,
            api_key=GROQ_API_KEY,
            temperature=0.0,    # deterministic for routing/classification
            max_tokens=512,
        )
    return _llm_flash


def _get_llm_pro() -> ChatGroq:
    """Llama 3.3 70B Versatile via Groq - best quality for final response.
    Groq free tier: 14,400 req/day, 12,000 tokens/min.
    Streaming enabled for SSE token-by-token delivery to frontend.
    """
    global _llm_pro
    if _llm_pro is None:
        _llm_pro = ChatGroq(
            model=GROQ_MODEL_PRO,
            api_key=GROQ_API_KEY,
            temperature=0.7,
            max_tokens=1024,
            streaming=True,     # token-by-token SSE streaming
        )
    return _llm_pro


def _get_embed_model() -> HuggingFaceEndpointEmbeddings:
    global _embed_model
    if _embed_model is None:
        _embed_model = HuggingFaceEndpointEmbeddings(
            model=EMBEDDING_MODEL,
            huggingfacehub_api_token=HF_TOKEN,
        )
    return _embed_model


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is None:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _pinecone_index = pc.Index(PINECONE_INDEX)
    return _pinecone_index


# ─────────────────────────────────────────────────────────────
#  Intent type
# ─────────────────────────────────────────────────────────────

IntentType = Literal["compare", "single_a", "single_b", "metadata", "suggest"]

# ─────────────────────────────────────────────────────────────
#  Query State
# ─────────────────────────────────────────────────────────────

class QueryState(TypedDict):
    # ── Inputs ──
    session_id:     str
    user_query:     str
    # chat_history is now optional — loaded automatically from Redis
    # Frontend no longer needs to send history on every request
    # Still accepted if provided (for backward compatibility)
    chat_history:   Optional[list[dict]]

    # ── Produced by validate_session_node ──
    session_valid:  Optional[bool]
    meta_a:         Optional[dict]
    meta_b:         Optional[dict]
    engagement:     Optional[dict]
    chat_history:   Optional[list[dict]]   # loaded from Redis here

    # ── Produced by query_rewriter_node ──
    rewritten_query:  Optional[str]

    # ── Produced by intent_router_node ──
    intent:           Optional[IntentType]

    # ── Produced by retrieve_node or metadata_lookup_node ──
    retrieved_chunks: Optional[list[dict]]   # [{text, video_id, timestamp, score, ...}]
    context_source:   Optional[str]          # "pinecone" | "redis"

    # ── Produced by rerank_node ──
    reranked_chunks:  Optional[list[dict]]

    # ── Produced by stream_response_node ──
    response:         Optional[str]          # full assembled response
    citations:        Optional[list[dict]]   # [{video_id, chunk_index, timestamp}]

    # ── Produced by update_memory_node ──
    updated_history:  Optional[list[dict]]


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _format_history_for_llm(chat_history: list[dict]) -> list:
    """Convert chat_history dicts to LangChain message objects."""
    messages = []
    for turn in chat_history[-6:]:   # keep last 6 turns (3 exchanges) for context
        role    = turn.get("role", "user")
        content = turn.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def _format_chunks_as_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into a context string for the LLM prompt.
    Each chunk includes its citation label.
    """
    if not chunks:
        return "No relevant context found."

    parts = []
    for i, chunk in enumerate(chunks):
        video_id  = chunk.get("video_id", "?")
        ts_start  = chunk.get("timestamp_start", 0)
        ts_end    = chunk.get("timestamp_end", 0)
        text      = chunk.get("text", "")
        title     = chunk.get("title", "")

        # Format timestamp as MM:SS
        def fmt_ts(s):
            s = int(s)
            return f"{s // 60:02d}:{s % 60:02d}"

        citation = f"[Video {video_id}, {fmt_ts(ts_start)}–{fmt_ts(ts_end)}]"
        parts.append(f"{citation}\nTitle: {title}\n{text}")

    return "\n\n---\n\n".join(parts)


def _build_metadata_context(meta_a: dict, meta_b: dict, engagement: dict) -> str:
    """Format metadata + engagement into a readable context block."""
    def fmt(m: dict, label: str) -> str:
        return (
            f"Video {label}:\n"
            f"  Title:           {m.get('title', 'N/A')}\n"
            f"  Creator:         {m.get('creator', 'N/A')}\n"
            f"  Followers:       {m.get('follower_count', 0):,}\n"
            f"  Platform:        {m.get('platform', 'N/A')}\n"
            f"  Views:           {m.get('views', 0):,}\n"
            f"  Likes:           {m.get('likes', 0):,}\n"
            f"  Comments:        {m.get('comments', 0):,}\n"
            f"  Engagement Rate: {m.get('engagement_rate', 0.0):.3f}%\n"
            f"  Upload Date:     {m.get('upload_date', 'N/A')}\n"
            f"  Duration:        {m.get('duration', 0)}s\n"
            f"  Hashtags:        {', '.join(m.get('hashtags', []))}"
        )

    eng = engagement or {}
    comparison = (
        f"\nEngagement Comparison:\n"
        f"  Winner:          Video {eng.get('winner', '?')}\n"
        f"  Engagement A:    {eng.get('engagement_rate_a', 0):.3f}%\n"
        f"  Engagement B:    {eng.get('engagement_rate_b', 0):.3f}%\n"
        f"  Difference:      {eng.get('engagement_diff', 0):.3f}%\n"
        f"  Summary:         {eng.get('summary', '')}"
    )

    return f"{fmt(meta_a, 'A')}\n\n{fmt(meta_b, 'B')}\n{comparison}"


# ─────────────────────────────────────────────────────────────
#  Node 1 — validate_session_node
# ─────────────────────────────────────────────────────────────

def validate_session_node(state: QueryState) -> dict:
    """
    Checks session exists in Redis.
    Loads metadata, engagement AND conversation history into state.

    History is loaded here once per turn — no need for frontend
    to send the full history payload on every request.
    The frontend only needs to send session_id + user_query.
    """
    session_id = state["session_id"]

    if not session_exists(session_id):
        return {
            "session_valid": False,
            "meta_a":        {},
            "meta_b":        {},
            "engagement":    {},
            "chat_history":  [],
        }

    both_meta  = get_both_metadata(session_id)
    engagement = get_engagement_comparison(session_id)

    # Load history from Redis — frontend no longer needs to send it
    history = load_history(session_id)
    print(f"[validate_session] Loaded {len(history)} history turns from Redis.")

    return {
        "session_valid": True,
        "meta_a":        both_meta.get("A", {}),
        "meta_b":        both_meta.get("B", {}),
        "engagement":    engagement or {},
        "chat_history":  history,
    }


# ─────────────────────────────────────────────────────────────
#  Node 2 — query_rewriter_node
# ─────────────────────────────────────────────────────────────

def query_rewriter_node(state: QueryState) -> dict:
    """
    Rewrites the user query using HyDE (Hypothetical Document Embedding).

    HyDE: instead of embedding the raw question, we generate a
    hypothetical ideal answer and embed that. This matches the style
    of the transcript chunks much better and improves retrieval recall.

    Example:
      Input:  "What was the hook in Video A?"
      Output: "The video opens with an attention-grabbing statement
               directly addressing the viewer in the first few seconds,
               creating immediate engagement..."
    """
    if not state.get("session_valid"):
        return {"rewritten_query": state["user_query"]}

    llm   = _get_llm_flash()
    query = state["user_query"]
    meta_a = state.get("meta_a", {})
    meta_b = state.get("meta_b", {})

    system_prompt = (
        "You are a video content analyst assistant. "
        "You are analyzing two videos:\n"
        f"  Video A: '{meta_a.get('title', 'Video A')}' by {meta_a.get('creator', 'unknown')}\n"
        f"  Video B: '{meta_b.get('title', 'Video B')}' by {meta_b.get('creator', 'unknown')}\n\n"
        "Your task: rewrite the user's question as a hypothetical passage "
        "that would appear in a video transcript. "
        "Write 2-3 sentences as if they are spoken words from the video. "
        "Be specific. Do not answer the question — just rewrite it as transcript text.\n"
        "Return ONLY the rewritten passage, nothing else."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Rewrite this question as transcript text: {query}"),
    ]

    response = llm.invoke(messages)
    rewritten = response.content.strip()

    print(f"[query_rewriter] Original:  {query}")
    print(f"[query_rewriter] Rewritten: {rewritten[:100]}...")

    return {"rewritten_query": rewritten}


# ─────────────────────────────────────────────────────────────
#  Node 3 — intent_router_node
# ─────────────────────────────────────────────────────────────

def intent_router_node(state: QueryState) -> dict:
    """
    Classifies the user query into one of 5 intent buckets.

    Intents:
      compare   → "Why did A outperform B?", "Compare the hooks"
      single_a  → "What's the hook in Video A?", "Summarize Video A"
      single_b  → "What did Video B talk about?"
      metadata  → "Who is the creator?", "What's the engagement rate?"
      suggest   → "How can B improve?", "What should B do differently?"

    Uses Llama 3.1 8B Instant via Groq with JSON output - fast and cheap.
    Falls back to "compare" if classification fails.
    """
    llm   = _get_llm_flash()
    query = state["user_query"]

    system_prompt = (
        "Classify the user's question about two videos (Video A and Video B) "
        "into exactly one of these intents:\n\n"
        "  compare  → comparing both videos, engagement, hooks, performance\n"
        "  single_a → question only about Video A\n"
        "  single_b → question only about Video B\n"
        "  metadata → factual question: creator name, follower count, views, "
        "             likes, comments, upload date, duration, engagement rate\n"
        "  suggest  → asking for improvements, recommendations, suggestions for a video\n\n"
        "Respond with ONLY a JSON object: {\"intent\": \"<one of the 5 above>\"}\n"
        "No explanation. No markdown. Just the JSON."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query),
    ]

    try:
        response = llm.invoke(messages)
        raw      = response.content.strip()

        # Strip markdown fences if present
        raw = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(raw)
        intent = parsed.get("intent", "compare")

        # Validate intent is one of the 5 allowed values
        allowed = {"compare", "single_a", "single_b", "metadata", "suggest"}
        if intent not in allowed:
            intent = "compare"

    except Exception as e:
        print(f"[intent_router] Classification failed: {e} — defaulting to 'compare'")
        intent = "compare"

    print(f"[intent_router] Query: '{query}' → Intent: '{intent}'")
    return {"intent": intent}


# ─────────────────────────────────────────────────────────────
#  Routing function — decides next node after intent_router
# ─────────────────────────────────────────────────────────────

def route_by_intent(state: QueryState) -> str:
    """
    LangGraph conditional edge function.
    Returns the name of the next node based on intent.
    """
    intent = state.get("intent", "compare")
    if intent == "metadata":
        return "metadata_lookup_node"
    return "retrieve_node"


# ─────────────────────────────────────────────────────────────
#  Node 4A — metadata_lookup_node (Redis path)
# ─────────────────────────────────────────────────────────────

def metadata_lookup_node(state: QueryState) -> dict:
    """
    Answers metadata questions directly from Redis cache.
    Zero Pinecone calls — sub-millisecond response.

    Formats metadata as structured chunks so the rest of
    the pipeline (rerank → stream) works the same way.
    """
    meta_a     = state.get("meta_a", {})
    meta_b     = state.get("meta_b", {})
    engagement = state.get("engagement", {})

    # Format as a single "chunk" — rerank_node will pass it through
    context_text = _build_metadata_context(meta_a, meta_b, engagement)

    metadata_chunk = {
        "text":            context_text,
        "video_id":        "A+B",
        "chunk_index":     0,
        "timestamp_start": 0.0,
        "timestamp_end":   0.0,
        "title":           "Session Metadata",
        "score":           1.0,
    }

    print(f"[metadata_lookup] Answered from Redis cache. No Pinecone call.")

    return {
        "retrieved_chunks": [metadata_chunk],
        "context_source":   "redis",
    }


# ─────────────────────────────────────────────────────────────
#  Node 4B — retrieve_node (Pinecone path)
# ─────────────────────────────────────────────────────────────

def retrieve_node(state: QueryState) -> dict:
    """
    Retrieves relevant chunks from Pinecone using the rewritten query.

    Routing by intent:
      compare / suggest → dual retrieve: top-6 from A AND top-6 from B
      single_a          → filtered retrieve: top-8 from A only
      single_b          → filtered retrieve: top-8 from B only

    Uses BGE-M3 query-side embedding:
      NOTE: query side uses plain text (no "Represent this sentence:" prefix)
      Only the document side uses the prefix during ingestion.
    """
    intent         = state.get("intent", "compare")
    rewritten_query = state.get("rewritten_query") or state["user_query"]
    index          = _get_pinecone_index()
    embed_model    = _get_embed_model()

    # Embed the rewritten query
    query_embedding = embed_model.embed_query(rewritten_query)

    chunks = []

    if intent in ("compare", "suggest"):
        # Dual retrieve — both videos in parallel (two sequential calls)
        for vid_id in ["A", "B"]:
            results = index.query(
                vector          = query_embedding,
                top_k           = TOP_K_DUAL,
                filter          = {"video_id": {"$eq": vid_id}},
                include_metadata = True,
            )
            for match in results.matches:
                chunk = dict(match.metadata)
                chunk["score"]    = round(match.score, 4)
                chunk["chunk_id"] = match.id
                chunks.append(chunk)
        print(f"[retrieve] Dual retrieve: {len(chunks)} chunks "
              f"({TOP_K_DUAL} per video).")

    elif intent == "single_a":
        results = index.query(
            vector          = query_embedding,
            top_k           = TOP_K_SINGLE,
            filter          = {"video_id": {"$eq": "A"}},
            include_metadata = True,
        )
        for match in results.matches:
            chunk = dict(match.metadata)
            chunk["score"]    = round(match.score, 4)
            chunk["chunk_id"] = match.id
            chunks.append(chunk)
        print(f"[retrieve] Single retrieve (A): {len(chunks)} chunks.")

    elif intent == "single_b":
        results = index.query(
            vector          = query_embedding,
            top_k           = TOP_K_SINGLE,
            filter          = {"video_id": {"$eq": "B"}},
            include_metadata = True,
        )
        for match in results.matches:
            chunk = dict(match.metadata)
            chunk["score"]    = round(match.score, 4)
            chunk["chunk_id"] = match.id
            chunks.append(chunk)
        print(f"[retrieve] Single retrieve (B): {len(chunks)} chunks.")

    return {
        "retrieved_chunks": chunks,
        "context_source":   "pinecone",
    }


# ─────────────────────────────────────────────────────────────
#  Node 5 — rerank_node
# ─────────────────────────────────────────────────────────────

def rerank_node(state: QueryState) -> dict:
    """
    Reranks retrieved chunks by relevance to the original user query.

    Since we're on a free stack (no Cohere rerank API), we use
    a cross-encoder style scoring with Llama 3.1 8B Instant via Groq:
    Ask the LLM to score each chunk 0-10 for relevance and sort.

    This reduces 12 raw chunks → top 5, cutting LLM context by ~58%
    which saves tokens on the final generation step.

    For metadata queries (context_source = "redis"), passes through unchanged.
    """
    chunks         = state.get("retrieved_chunks", [])
    context_source = state.get("context_source", "pinecone")

    # Metadata path: pass through unchanged
    if context_source == "redis" or len(chunks) <= TOP_K_AFTER_RERANK:
        return {"reranked_chunks": chunks}

    query = state["user_query"]

    # Score each chunk with a quick LLM call
    llm = _get_llm_flash()

    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        preview = chunk.get("text", "")[:200]
        chunk_summaries.append(f"Chunk {i} [Video {chunk.get('video_id','?')}]: {preview}")

    scoring_prompt = (
        f"User question: {query}\n\n"
        f"Rate each chunk's relevance to the question (0-10).\n"
        f"Return ONLY a JSON array of scores in order:\n"
        f"Example: [8, 3, 9, 2, 7, 5, 8, 4, 6, 3, 7, 2]\n\n"
        + "\n".join(chunk_summaries)
    )

    try:
        response = llm.invoke([HumanMessage(content=scoring_prompt)])
        raw      = response.content.strip()
        raw      = re.sub(r"```json|```", "", raw).strip()
        scores   = json.loads(raw)

        if isinstance(scores, list) and len(scores) == len(chunks):
            # Attach scores and sort descending
            for i, chunk in enumerate(chunks):
                chunk["rerank_score"] = float(scores[i])
            chunks.sort(key=lambda c: c.get("rerank_score", 0), reverse=True)
        else:
            # Score count mismatch — fall back to cosine score sort
            chunks.sort(key=lambda c: c.get("score", 0), reverse=True)

    except Exception as e:
        print(f"[rerank] Scoring failed: {e} — using cosine score fallback.")
        chunks.sort(key=lambda c: c.get("score", 0), reverse=True)

    # Keep top N
    reranked = chunks[:TOP_K_AFTER_RERANK]
    print(f"[rerank] {len(chunks)} → {len(reranked)} chunks after reranking.")

    return {"reranked_chunks": reranked}


# ─────────────────────────────────────────────────────────────
#  Node 6 — stream_response_node
# ─────────────────────────────────────────────────────────────

def stream_response_node(state: QueryState) -> dict:
    """
    Generates the final response using Llama 3.3 70B Versatile via Groq.

    Prompt structure:
      - System: role + instructions for citations + tone
      - Metadata context: always included (engagement rates etc.)
      - Retrieved chunks: formatted with citation labels
      - Chat history: last 6 turns for memory
      - User query: the actual question

    Citations:
      Every claim about video content must reference [Video A, MM:SS-MM:SS]
      The LLM is instructed to cite inline, not at the end.

    Returns full assembled response string.
    For SSE streaming to frontend, use stream_response_sse() instead.
    """
    query          = state["user_query"]
    reranked_chunks = state.get("reranked_chunks", [])
    meta_a         = state.get("meta_a", {})
    meta_b         = state.get("meta_b", {})
    engagement     = state.get("engagement", {})
    chat_history   = state.get("chat_history", [])
    intent         = state.get("intent", "compare")

    # ── Build system prompt ──
    system_prompt = f"""You are VidRival, an AI assistant that helps content creators 
analyze and compare two videos to understand what drives engagement.

You have access to:
1. Full transcripts of both videos (retrieved as chunks below)
2. Metadata: views, likes, comments, engagement rates, creator info

RULES:
- Always cite your sources inline using [Video A, MM:SS–MM:SS] format
- Never make up numbers — only use figures from the context provided
- When comparing, always reference both videos
- Be direct and actionable — creators want practical insights
- If context is insufficient, say so clearly

VIDEO METADATA:
{_build_metadata_context(meta_a, meta_b, engagement)}
"""

    # ── Build context from chunks ──
    context_str = _format_chunks_as_context(reranked_chunks)

    # ── Build intent-specific instruction ──
    intent_instructions = {
        "compare": "Compare both videos directly. Explain what Video A did differently from B and why it matters for engagement.",
        "single_a": "Focus on Video A. Be specific about what you find in the transcript.",
        "single_b": "Focus on Video B. Be specific about what you find in the transcript.",
        "metadata": "Answer using the metadata provided. Be precise with numbers.",
        "suggest": "Give 3-5 specific, actionable improvements for the lower-performing video based on what worked in the better one.",
    }
    instruction = intent_instructions.get(intent, "")

    # ── Assemble messages ──
    messages = [SystemMessage(content=system_prompt)]

    # Add chat history for memory
    messages.extend(_format_history_for_llm(chat_history))

    # Add current query with context
    user_message = (
        f"RETRIEVED CONTEXT:\n{context_str}\n\n"
        f"INSTRUCTION: {instruction}\n\n"
        f"QUESTION: {query}"
    )
    messages.append(HumanMessage(content=user_message))

    # ── Generate response ──
    llm = _get_llm_pro()

    print(f"[stream_response] Generating response for intent='{intent}'...")
    response     = llm.invoke(messages)
    response_text = response.content.strip()

    # ── Extract citations from response ──
    citation_pattern = r"\[Video ([AB]),\s*(\d{2}:\d{2})(?:–(\d{2}:\d{2}))?\]"
    found_citations  = re.findall(citation_pattern, response_text)
    citations = [
        {"video_id": c[0], "timestamp_start": c[1], "timestamp_end": c[2]}
        for c in found_citations
    ]

    print(f"[stream_response] Response: {len(response_text)} chars, "
          f"{len(citations)} citations.")

    return {
        "response":  response_text,
        "citations": citations,
    }


# ─────────────────────────────────────────────────────────────
#  Node 7 — update_memory_node
# ─────────────────────────────────────────────────────────────

def update_memory_node(state: QueryState) -> dict:
    """
    Persists the current Q/A turn to Redis via append_turn().

    This replaces the old approach of storing history in frontend
    state and sending it back on every request.

    Now:
    - validate_session_node  → loads history from Redis
    - update_memory_node     → saves history to Redis
    - Frontend               → only sends session_id + user_query
    - History key in Redis   → session:{id}:history (TTL refreshes on every turn)
    """
    session_id = state["session_id"]
    query      = state["user_query"]
    response   = state.get("response", "")

    # append_turn loads existing history, appends, caps, saves back to Redis
    updated_history = append_turn(
        session_id         = session_id,
        user_query         = query,
        assistant_response = response,
    )

    print(f"[update_memory] History saved to Redis: {len(updated_history)} turns.")
    return {"updated_history": updated_history}


# ─────────────────────────────────────────────────────────────
#  Invalid session handler
# ─────────────────────────────────────────────────────────────

def handle_invalid_session_node(state: QueryState) -> dict:
    """Handles expired or missing sessions gracefully."""
    return {
        "response": (
            "Session not found or expired. "
            "Please re-ingest your videos to start a new session."
        ),
        "citations":        [],
        "reranked_chunks":  [],
        "updated_history":  [],
    }


# ─────────────────────────────────────────────────────────────
#  Session validation routing
# ─────────────────────────────────────────────────────────────

def route_after_validation(state: QueryState) -> str:
    if not state.get("session_valid"):
        return "handle_invalid_session_node"
    return "query_rewriter_node"


# ─────────────────────────────────────────────────────────────
#  Graph builder
# ─────────────────────────────────────────────────────────────

def build_query_graph():
    """
    Builds and compiles the LangGraph query pipeline.

    Usage:
        app = build_query_graph()

        # First turn
        result = app.invoke({
            "session_id":   "vidrival_a3f9c21b",
            "user_query":   "Why did Video A get more engagement?",
            "chat_history": [],
        })
        print(result["response"])
        history = result["updated_history"]

        # Second turn (pass history for memory)
        result = app.invoke({
            "session_id":   "vidrival_a3f9c21b",
            "user_query":   "What was the hook in the first 5 seconds?",
            "chat_history": history,
        })
    """
    graph = StateGraph(QueryState)

    # ── Register all nodes ──
    graph.add_node("validate_session_node",    validate_session_node)
    graph.add_node("handle_invalid_session_node", handle_invalid_session_node)
    graph.add_node("query_rewriter_node",      query_rewriter_node)
    graph.add_node("intent_router_node",       intent_router_node)
    graph.add_node("metadata_lookup_node",     metadata_lookup_node)
    graph.add_node("retrieve_node",            retrieve_node)
    graph.add_node("rerank_node",              rerank_node)
    graph.add_node("stream_response_node",     stream_response_node)
    graph.add_node("update_memory_node",       update_memory_node)

    # ── Entry ──
    graph.add_edge(START, "validate_session_node")

    # ── Conditional: valid session? ──
    graph.add_conditional_edges(
        "validate_session_node",
        route_after_validation,
        {
            "query_rewriter_node":       "query_rewriter_node",
            "handle_invalid_session_node": "handle_invalid_session_node",
        },
    )

    # ── Invalid session exits immediately ──
    graph.add_edge("handle_invalid_session_node", END)

    # ── Normal path ──
    graph.add_edge("query_rewriter_node", "intent_router_node")

    # ── Conditional: route by intent ──
    graph.add_conditional_edges(
        "intent_router_node",
        route_by_intent,
        {
            "metadata_lookup_node": "metadata_lookup_node",
            "retrieve_node":        "retrieve_node",
        },
    )

    # ── Both retrieval paths converge at rerank ──
    graph.add_edge("metadata_lookup_node", "rerank_node")
    graph.add_edge("retrieve_node",        "rerank_node")

    # ── Final path ──
    graph.add_edge("rerank_node",          "stream_response_node")
    graph.add_edge("stream_response_node", "update_memory_node")
    graph.add_edge("update_memory_node",   END)

    return graph.compile()


# ─────────────────────────────────────────────────────────────
#  SSE streaming helper — used by FastAPI endpoint
# ─────────────────────────────────────────────────────────────

def stream_query(
    session_id: str,
    user_query: str,
):
    """
    Generator for SSE streaming from FastAPI.
    History is loaded automatically from Redis.
    Frontend only needs to send session_id + user_query.

    Usage in FastAPI:
        @app.post("/query")
        async def query(req: QueryRequest):
            return StreamingResponse(
                stream_query(req.session_id, req.query),
                media_type="text/event-stream"
            )

    SSE events:
        data: <word>\n\n             streamed response tokens
        data: [CITATIONS]{...}\n\n   citation list JSON
        data: [DONE]\n\n             end of stream
    """
    app = build_query_graph()

    result = app.invoke({
        "session_id":   session_id,
        "user_query":   user_query,
        "chat_history": [],    # loaded from Redis in validate_session_node
    })

    response  = result.get("response", "")
    citations = result.get("citations", [])

    # Stream word by word
    for word in response.split(" "):
        yield f"data: {word} \n\n"

    yield f"data: [CITATIONS]{json.dumps(citations)}\n\n"
    yield "data: [DONE]\n\n"