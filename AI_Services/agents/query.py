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
    get_session_snapshot,
    session_exists,
    load_history,
    append_turn,
    clear_history,
    get_history_length,
)
from pinecone import Pinecone
from functools import lru_cache

load_dotenv()

GROQ_API_KEY     = os.getenv("GROQ_API_KEY")
HF_TOKEN         = os.getenv("HUGGINGFACEHUB_API_TOKEN")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX   = os.getenv("PINECONE_INDEX_NAME", "engageX")
EMBEDDING_MODEL  = "BAAI/bge-m3"

GROQ_MODEL_FAST = "llama-3.1-8b-instant"
GROQ_MODEL_PRO  = "llama-3.3-70b-versatile"

TOP_K_SINGLE       = 8
TOP_K_DUAL         = 6
TOP_K_AFTER_RERANK = 5

_llm_flash: ChatGroq | None = None
_llm_pro: ChatGroq | None = None
_embed_model: HuggingFaceEndpointEmbeddings | None = None
_pinecone_index = None


def _get_llm_flash() -> ChatGroq:
    """Fast model used for routing, rewriting, and reranking."""
    global _llm_flash
    if _llm_flash is None:
        _llm_flash = ChatGroq(
            model=GROQ_MODEL_FAST,
            api_key=GROQ_API_KEY,
            temperature=0.0,
            max_tokens=512,
        )
    return _llm_flash


def _get_llm_pro() -> ChatGroq:
    """Larger model used for final response generation."""
    global _llm_pro
    if _llm_pro is None:
        _llm_pro = ChatGroq(
            model=GROQ_MODEL_PRO,
            api_key=GROQ_API_KEY,
            temperature=0.7,
            max_tokens=1024,
            streaming=True,
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


# ---------------------------
# CACHING HELPERS
# ---------------------------


@lru_cache(maxsize=4096)
def _cached_rewrite(query: str, title_a: str, title_b: str) -> str:
    """Cached HyDE rewrite using llm_flash. Cache key: (query, title_a, title_b)."""
    llm   = _get_llm_flash()

    system_prompt = (
        "You are a video content analyst assistant. "
        "You are analyzing two videos:\n"
        f"  Video A: '{title_a}'\n"
        f"  Video B: '{title_b}'\n\n"
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
    return response.content.strip()


@lru_cache(maxsize=8192)
def _cached_embed_query(text: str) -> tuple:
    """Cache query-side embeddings (as tuple) to reduce HF calls."""
    model = _get_embed_model()
    emb = model.embed_query(text)
    return tuple(emb)


# FIX: Added "general" intent for casual/off-topic queries
IntentType = Literal["compare", "single_a", "single_b", "metadata", "suggest", "general"]


class QueryState(TypedDict):
    session_id:     str
    user_query:     str
    chat_history:   Optional[list[dict]]

    session_valid:  Optional[bool]
    meta_a:         Optional[dict]
    meta_b:         Optional[dict]
    engagement:     Optional[dict]
    chat_history:   Optional[list[dict]]

    rewritten_query:  Optional[str]
    intent:           Optional[IntentType]

    retrieved_chunks: Optional[list[dict]]
    context_source:   Optional[str]

    reranked_chunks:  Optional[list[dict]]

    response:         Optional[str]
    citations:        Optional[list[dict]]

    updated_history:  Optional[list[dict]]


def _format_history_for_llm(chat_history: list[dict]) -> list:
    """Convert chat history dicts to LangChain message objects."""
    messages = []
    for turn in chat_history[-6:]:
        role    = turn.get("role", "user")
        content = turn.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    return messages


def _format_chunks_as_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a context string with citation labels."""
    if not chunks:
        return "No relevant context found."

    parts = []
    for i, chunk in enumerate(chunks):
        video_id = chunk.get("video_id", "?")
        ts_start = chunk.get("timestamp_start", 0)
        ts_end   = chunk.get("timestamp_end", 0)
        text     = chunk.get("text", "")
        title    = chunk.get("title", "")

        def fmt_ts(s):
            s = int(s)
            return f"{s // 60:02d}:{s % 60:02d}"

        citation = f"[Video {video_id}, {fmt_ts(ts_start)}–{fmt_ts(ts_end)}]"
        parts.append(f"{citation}\nTitle: {title}\n{text}")

    return "\n\n---\n\n".join(parts)


def _build_metadata_context(meta_a: dict, meta_b: dict, engagement: dict) -> str:
    """Format video metadata and engagement into a readable block for the LLM."""
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


def validate_session_node(state: QueryState) -> dict:
    """
    Checks the session exists and loads metadata, engagement, and
    conversation history from Redis into state.
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

    # Use single-shot Redis snapshot to reduce number of Upstash commands
    snap       = get_session_snapshot(session_id)
    both_meta  = {"A": snap.get("video_a", {}), "B": snap.get("video_b", {})}
    engagement = snap.get("engagement", {})
    history    = snap.get("history", [])

    print(f"[validate_session] Loaded {len(history)} history turns from Redis.")

    return {
        "session_valid": True,
        "meta_a":        both_meta.get("A", {}),
        "meta_b":        both_meta.get("B", {}),
        "engagement":    engagement or {},
        "chat_history":  history,
    }


def query_rewriter_node(state: QueryState) -> dict:
    """
    Rewrites the user query using HyDE so it reads like transcript text.
    This makes the embedding match stored chunks much more reliably.
    Skipped for "general" intent to avoid mangling casual conversation.
    """
    # FIX: Skip HyDE rewriting for general/casual queries — no transcript to match
    if not state.get("session_valid") or state.get("intent") == "general":
        return {"rewritten_query": state["user_query"]}

    query  = state["user_query"]
    meta_a = state.get("meta_a", {})
    meta_b = state.get("meta_b", {})

    # Use cached rewrite to avoid repeated Groq calls for identical queries
    rewritten = _cached_rewrite(
        query,
        meta_a.get("title", "Video A"),
        meta_b.get("title", "Video B"),
    )

    print(f"[query_rewriter] Original:  {query}")
    print(f"[query_rewriter] Rewritten: {rewritten[:100]}...")

    return {"rewritten_query": rewritten}


def intent_router_node(state: QueryState) -> dict:
    """
    Classifies the query into one of six intents:
    compare, single_a, single_b, metadata, suggest, or general.
    Falls back to 'compare' if classification fails.
    """
    llm   = _get_llm_flash()
    query = state["user_query"]

    # FIX: Added "general" intent for greetings and off-topic messages
    system_prompt = (
        "Classify the user's question about two videos (Video A and Video B) "
        "into exactly one of these intents:\n\n"
        "  compare  → comparing both videos, engagement, hooks, performance\n"
        "  single_a → question only about Video A\n"
        "  single_b → question only about Video B\n"
        "  metadata → factual question: creator name, follower count, views, "
        "             likes, comments, upload date, duration, engagement rate\n"
        "  suggest  → asking for improvements, recommendations, suggestions for a video\n"
        "  general  → greetings, small talk, or anything unrelated to video analysis "
        "             (e.g. 'hello', 'how are you', 'what can you do', 'thanks')\n\n"
        "Respond with ONLY a JSON object: {\"intent\": \"<one of the 6 above>\"}\n"
        "No explanation. No markdown. Just the JSON."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=query),
    ]

    try:
        response = llm.invoke(messages)
        raw      = response.content.strip()
        raw      = re.sub(r"```json|```", "", raw).strip()
        parsed   = json.loads(raw)
        intent   = parsed.get("intent", "compare")

        # FIX: Added "general" to the allowed set
        allowed = {"compare", "single_a", "single_b", "metadata", "suggest", "general"}
        if intent not in allowed:
            intent = "compare"

    except Exception as e:
        print(f"[intent_router] Classification failed: {e} — defaulting to 'compare'")
        intent = "compare"

    print(f"[intent_router] Query: '{query}' → Intent: '{intent}'")
    return {"intent": intent}


def route_by_intent(state: QueryState) -> str:
    """
    Metadata queries go straight to Redis.
    General/casual queries go to a simple conversational handler.
    Everything else hits Pinecone.
    """
    intent = state.get("intent", "compare")
    if intent == "metadata":
        return "metadata_lookup_node"
    # FIX: Route general intent away from Pinecone entirely
    if intent == "general":
        return "handle_general_node"
    return "retrieve_node"


def metadata_lookup_node(state: QueryState) -> dict:
    """Answers metadata questions directly from Redis — no Pinecone call needed."""
    meta_a     = state.get("meta_a", {})
    meta_b     = state.get("meta_b", {})
    engagement = state.get("engagement", {})

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

    print("[metadata_lookup] Answered from Redis cache. No Pinecone call.")

    return {
        "retrieved_chunks": [metadata_chunk],
        "context_source":   "redis",
    }


# FIX: New node — handles greetings and off-topic messages without touching Pinecone
def handle_general_node(state: QueryState) -> dict:
    """
    Responds conversationally to greetings, small talk, and off-topic messages.
    Does NOT query Pinecone or render engagement metric tables.
    """
    query        = state["user_query"]
    chat_history = state.get("chat_history", [])
    llm          = _get_llm_pro()

    system_prompt = (
        "You are EngageX, a friendly AI assistant that helps content creators "
        "analyze and compare video engagement metrics. "
        "Respond warmly and naturally to casual conversation or off-topic questions. "
        "Keep your reply brief (1–3 sentences). "
        "Do NOT produce tables, metrics, or structured analysis. "
        "If appropriate, gently remind the user what you can help with: "
        "comparing videos, analyzing engagement, or suggesting improvements."
    )

    messages = [SystemMessage(content=system_prompt)]
    messages.extend(_format_history_for_llm(chat_history))
    messages.append(HumanMessage(content=query))

    response = llm.invoke(messages)
    response_text = response.content.strip()

    print(f"[handle_general] Casual response generated ({len(response_text)} chars).")

    return {
        "response":        response_text,
        "citations":       [],
        "reranked_chunks": [],
    }


def retrieve_node(state: QueryState) -> dict:
    """
    Retrieves chunks from Pinecone using the HyDE-rewritten query.
    Compare/suggest intents query both videos; single-video intents filter by ID.
    """
    intent          = state.get("intent", "compare")
    rewritten_query = state.get("rewritten_query") or state["user_query"]
    index           = _get_pinecone_index()

    # Use cached query embedding to reduce Hugging Face calls for repeated queries
    query_embedding = list(_cached_embed_query(rewritten_query))

    chunks = []

    if intent in ("compare", "suggest"):
        for vid_id in ["A", "B"]:
            results = index.query(
                vector           = query_embedding,
                top_k            = TOP_K_DUAL,
                filter           = {"video_id": {"$eq": vid_id}},
                include_metadata = True,
            )
            for match in results.matches:
                chunk = dict(match.metadata)
                chunk["score"]    = round(match.score, 4)
                chunk["chunk_id"] = match.id
                chunks.append(chunk)
        print(f"[retrieve] Dual retrieve: {len(chunks)} chunks ({TOP_K_DUAL} per video).")

    elif intent == "single_a":
        results = index.query(
            vector           = query_embedding,
            top_k            = TOP_K_SINGLE,
            filter           = {"video_id": {"$eq": "A"}},
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
            vector           = query_embedding,
            top_k            = TOP_K_SINGLE,
            filter           = {"video_id": {"$eq": "B"}},
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


def rerank_node(state: QueryState) -> dict:
    """
    Scores each retrieved chunk 0–10 for relevance and keeps the top 5.
    Uses the fast LLM as a lightweight cross-encoder. Falls back to cosine
    score ordering if the LLM response can't be parsed.
    """
    chunks         = state.get("retrieved_chunks", [])
    context_source = state.get("context_source", "pinecone")

    if context_source == "redis" or len(chunks) <= TOP_K_AFTER_RERANK:
        return {"reranked_chunks": chunks}

    query = state["user_query"]
    llm   = _get_llm_flash()

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
            for i, chunk in enumerate(chunks):
                chunk["rerank_score"] = float(scores[i])
            chunks.sort(key=lambda c: c.get("rerank_score", 0), reverse=True)
        else:
            chunks.sort(key=lambda c: c.get("score", 0), reverse=True)

    except Exception as e:
        print(f"[rerank] Scoring failed: {e} — using cosine score fallback.")
        chunks.sort(key=lambda c: c.get("score", 0), reverse=True)

    reranked = chunks[:TOP_K_AFTER_RERANK]
    print(f"[rerank] {len(chunks)} → {len(reranked)} chunks after reranking.")

    return {"reranked_chunks": reranked}


def stream_response_node(state: QueryState) -> dict:
    """Generates the final markdown response using the larger Llama model."""
    query           = state["user_query"]
    reranked_chunks = state.get("reranked_chunks", [])
    meta_a          = state.get("meta_a", {})
    meta_b          = state.get("meta_b", {})
    engagement      = state.get("engagement", {})
    chat_history    = state.get("chat_history", [])
    intent          = state.get("intent", "compare")

    system_prompt = f"""You are EngageX, an AI assistant that helps content creators
analyze and compare two videos to understand what drives engagement.

You have access to:
1. Full transcripts of both videos (retrieved as chunks below)
2. Metadata: views, likes, comments, engagement rates, creator info

═══════════════════════════════════
FORMATTING RULES (strictly follow):
═══════════════════════════════════

Always structure your response using markdown like this:

## 🎯 [Short answer headline]

[1-2 sentence direct answer]

---

### 📊 Key Findings

| Metric | Video A | Video B |
|--------|---------|---------| 
| Engagement Rate | X% | Y% |
| Views | X | Y |
| Likes | X | Y |

---

### 🔍 Analysis

**Point 1 title**
Explanation with citation [Video A, MM:SS–MM:SS]

**Point 2 title**
Explanation with citation [Video B, MM:SS–MM:SS]

---

### ✅ Takeaway / Suggestions  (only for compare/suggest intents)

1. **First suggestion** — explanation
2. **Second suggestion** — explanation
3. **Third suggestion** — explanation

═══════════════════════════════════
CONTENT RULES:
═══════════════════════════════════
- Always cite inline using [Video A, MM:SS–MM:SS] format — never skip citations
- Never make up numbers — only use figures from the provided context
- When comparing, always show both videos side by side
- Use **bold** for key terms and important numbers
- Use bullet points for lists, numbered lists for steps/suggestions
- Keep each section short and scannable — no walls of text
- For metadata-only questions: just answer with a small table, skip Analysis section
- If context is insufficient, say exactly what is missing

VIDEO METADATA:
{_build_metadata_context(meta_a, meta_b, engagement)}
"""

    context_str = _format_chunks_as_context(reranked_chunks)

    intent_instructions = {
        "compare": (
            "Compare both videos directly using the format above. "
            "Show a metrics table first, then explain the key differences. "
            "Always reference specific moments using timestamps."
        ),
        "single_a": (
            "Focus only on Video A. Use ## heading with the video title. "
            "Use bold for key insights. Cite timestamps for every claim."
        ),
        "single_b": (
            "Focus only on Video B. Use ## heading with the video title. "
            "Use bold for key insights. Cite timestamps for every claim."
        ),
        "metadata": (
            "Answer using ONLY the metadata numbers. "
            "Present as a clean table — no Analysis section needed. "
            "Be precise with numbers, format them with commas (1,234,567)."
        ),
        "suggest": (
            "Give exactly 3-5 numbered, actionable improvements. "
            "Each suggestion must: name a specific tactic, explain WHY it works "
            "based on what Video A did [with timestamp], and HOW to apply it to Video B."
        ),
    }
    instruction = intent_instructions.get(intent, "")

    messages = [SystemMessage(content=system_prompt)]
    messages.extend(_format_history_for_llm(chat_history))

    user_message = (
        f"RETRIEVED CONTEXT:\n{context_str}\n\n"
        f"INSTRUCTION: {instruction}\n\n"
        f"QUESTION: {query}"
    )
    messages.append(HumanMessage(content=user_message))

    llm = _get_llm_pro()

    print(f"[stream_response] Generating response for intent='{intent}'...")
    response      = llm.invoke(messages)
    response_text = response.content.strip()

    citation_pattern = r"\[Video ([AB]),\s*(\d{2}:\d{2})(?:–(\d{2}:\d{2}))?\]"
    found_citations  = re.findall(citation_pattern, response_text)
    citations = [
        {"video_id": c[0], "timestamp_start": c[1], "timestamp_end": c[2]}
        for c in found_citations
    ]

    print(f"[stream_response] Response: {len(response_text)} chars, {len(citations)} citations.")

    return {
        "response":  response_text,
        "citations": citations,
    }


def update_memory_node(state: QueryState) -> dict:
    """Appends the current Q&A turn to Redis so history persists across reloads."""
    session_id = state["session_id"]
    query      = state["user_query"]
    response   = state.get("response", "")

    updated_history = append_turn(
        session_id         = session_id,
        user_query         = query,
        assistant_response = response,
    )

    print(f"[update_memory] History saved to Redis: {len(updated_history)} turns.")
    return {"updated_history": updated_history}


def handle_invalid_session_node(state: QueryState) -> dict:
    """Returns a friendly error when the session doesn't exist or has expired."""
    return {
        "response": (
            "Session not found or expired. "
            "Please re-ingest your videos to start a new session."
        ),
        "citations":       [],
        "reranked_chunks": [],
        "updated_history": [],
    }


def route_after_validation(state: QueryState) -> str:
    if not state.get("session_valid"):
        return "handle_invalid_session_node"
    return "query_rewriter_node"


def build_query_graph():
    """Builds and compiles the full LangGraph query pipeline."""
    graph = StateGraph(QueryState)

    graph.add_node("validate_session_node",       validate_session_node)
    graph.add_node("handle_invalid_session_node",  handle_invalid_session_node)
    graph.add_node("query_rewriter_node",          query_rewriter_node)
    graph.add_node("intent_router_node",           intent_router_node)
    graph.add_node("metadata_lookup_node",         metadata_lookup_node)
    # FIX: Register the new general handler node
    graph.add_node("handle_general_node",          handle_general_node)
    graph.add_node("retrieve_node",                retrieve_node)
    graph.add_node("rerank_node",                  rerank_node)
    graph.add_node("stream_response_node",         stream_response_node)
    graph.add_node("update_memory_node",           update_memory_node)

    graph.add_edge(START, "validate_session_node")

    graph.add_conditional_edges(
        "validate_session_node",
        route_after_validation,
        {
            "query_rewriter_node":         "query_rewriter_node",
            "handle_invalid_session_node": "handle_invalid_session_node",
        },
    )

    graph.add_edge("handle_invalid_session_node", END)
    graph.add_edge("query_rewriter_node", "intent_router_node")

    # FIX: Added "handle_general_node" to the conditional routing map
    graph.add_conditional_edges(
        "intent_router_node",
        route_by_intent,
        {
            "metadata_lookup_node": "metadata_lookup_node",
            "retrieve_node":        "retrieve_node",
            "handle_general_node":  "handle_general_node",  # FIX
        },
    )

    graph.add_edge("metadata_lookup_node", "rerank_node")
    graph.add_edge("retrieve_node",        "rerank_node")
    graph.add_edge("rerank_node",          "stream_response_node")
    graph.add_edge("stream_response_node", "update_memory_node")

    # FIX: General responses skip Pinecone/rerank/stream but still save to memory
    graph.add_edge("handle_general_node",  "update_memory_node")

    graph.add_edge("update_memory_node",   END)

    return graph.compile()


def stream_query(session_id: str, user_query: str):
    """
    Generator for the FastAPI streaming endpoint.
    Yields SSE-formatted chunks: tokens, citations, then DONE.
    """
    app = build_query_graph()

    result = app.invoke({
        "session_id":   session_id,
        "user_query":   user_query,
        "chat_history": [],
    })

    response  = result.get("response", "")
    citations = result.get("citations", [])

    for word in response.split(" "):
        chunk_json = json.dumps({"text": word + " "})
        yield f"data: {chunk_json}\n\n"

    yield f"data: [CITATIONS]{json.dumps(citations)}\n\n"
    yield "data: [DONE]\n\n"