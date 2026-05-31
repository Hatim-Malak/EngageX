"""
VidRival — cache_session.py
Caches session state to Upstash Redis after ingestion is complete.

What gets cached (TTL: 24h):
  - Metadata for both videos (views, likes, engagement rate, creator, etc.)
  - Ingestion summary (chunk counts, vector counts)
  - Session config (video IDs, URLs, platform)

What does NOT get cached:
  - Transcripts (too large, already in Pinecone)
  - Embeddings (already in Pinecone)
  - Conversation history (managed by LangGraph MemorySaver separately)

Why Redis for this:
  - Metadata queries ("who is the creator?", "what's the engagement rate?")
    are answered directly from Redis — zero Pinecone calls, sub-millisecond
  - Avoids re-fetching video metadata on every query turn

Dependencies:
  pip install upstash-redis python-dotenv
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

from upstash_redis import Redis

load_dotenv()

# ─────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────

UPSTASH_REDIS_REST_URL   = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

SESSION_TTL_SECONDS = 60 * 60 * 24   # 24 hours


# ─────────────────────────────────────────────────────────────
#  Redis client singleton
# ─────────────────────────────────────────────────────────────

_redis_client: Redis | None = None


def _get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
            raise ValueError(
                "Missing Upstash credentials.\n"
                "Add to .env:\n"
                "  UPSTASH_REDIS_REST_URL=https://your-db.upstash.io\n"
                "  UPSTASH_REDIS_REST_TOKEN=your_token"
            )
        _redis_client = Redis(
            url   = UPSTASH_REDIS_REST_URL,
            token = UPSTASH_REDIS_REST_TOKEN,
        )
        print("[cache_session] Upstash Redis client ready.")
    return _redis_client


# ─────────────────────────────────────────────────────────────
#  Key schema
#  All keys are namespaced under session:{session_id}:
#
#  session:{id}:meta          → session-level info (created_at, urls, status)
#  session:{id}:video:A       → full metadata for Video A
#  session:{id}:video:B       → full metadata for Video B
#  session:{id}:summary:A     → ingestion summary for Video A (chunk count etc.)
#  session:{id}:summary:B     → ingestion summary for Video B
#  session:{id}:engagement    → precomputed engagement comparison dict
# ─────────────────────────────────────────────────────────────

def _key(session_id: str, *parts: str) -> str:
    """Build a namespaced Redis key."""
    return f"session:{session_id}:{':'.join(parts)}"


# ─────────────────────────────────────────────────────────────
#  What we cache per video
#  (extracted from VideoData — excludes transcript + chunks)
# ─────────────────────────────────────────────────────────────

def _extract_video_metadata(video_data: dict) -> dict:
    """
    Extract only the metadata fields from a VideoData dict.
    Strips transcript and transcript_chunks — they're large
    and already stored in Pinecone.
    """
    return {
        "video_id":       video_data.get("video_id"),
        "platform":       video_data.get("platform"),
        "url":            video_data.get("url"),
        "title":          video_data.get("title"),
        "creator":        video_data.get("creator"),
        "follower_count": video_data.get("follower_count", 0),
        "views":          video_data.get("views", 0),
        "likes":          video_data.get("likes", 0),
        "comments":       video_data.get("comments", 0),
        "hashtags":       video_data.get("hashtags", []),
        "upload_date":    video_data.get("upload_date", ""),
        "duration":       video_data.get("duration", 0),
        "engagement_rate": video_data.get("engagement_rate", 0.0),
    }


def _build_engagement_comparison(meta_a: dict, meta_b: dict) -> dict:
    """
    Precompute engagement comparison between the two videos.
    Stored as a ready-to-read dict so the LLM doesn't have to calculate it.

    Includes:
    - Which video has higher engagement rate
    - Difference in engagement rate
    - View counts comparison
    - Like ratio comparison
    """
    eng_a = meta_a.get("engagement_rate", 0.0)
    eng_b = meta_b.get("engagement_rate", 0.0)
    views_a = meta_a.get("views", 0)
    views_b = meta_b.get("views", 0)

    winner = "A" if eng_a >= eng_b else "B"
    diff   = round(abs(eng_a - eng_b), 4)

    return {
        "winner":              winner,
        "engagement_rate_a":   eng_a,
        "engagement_rate_b":   eng_b,
        "engagement_diff":     diff,
        "engagement_diff_pct": round((diff / max(eng_b, 0.0001)) * 100, 2),
        "views_a":             views_a,
        "views_b":             views_b,
        "views_winner":        "A" if views_a >= views_b else "B",
        "likes_a":             meta_a.get("likes", 0),
        "likes_b":             meta_b.get("likes", 0),
        "comments_a":          meta_a.get("comments", 0),
        "comments_b":          meta_b.get("comments", 0),
        "summary": (
            f"Video {winner} has higher engagement "
            f"({max(eng_a, eng_b):.3f}% vs {min(eng_a, eng_b):.3f}%, "
            f"difference: {diff:.3f}%)"
        ),
    }


# ─────────────────────────────────────────────────────────────
#  Core cache operations
# ─────────────────────────────────────────────────────────────

def cache_session(
    session_id: str,
    video_a: dict,
    video_b: dict,
    embed_summary_a: dict,
    embed_summary_b: dict,
) -> dict:
    """
    Cache all session data to Upstash Redis.

    Args:
        session_id:      Unique session ID (generate with make_session_id())
        video_a:         VideoData dict from fetch_video() for Video A
        video_b:         VideoData dict from fetch_video() for Video B
        embed_summary_a: Summary dict from chunk_and_embed() for Video A
        embed_summary_b: Summary dict from chunk_and_embed() for Video B

    Returns:
        cache_result dict with session_id and all keys written

    Redis keys written (all with 24h TTL):
        session:{id}:meta
        session:{id}:video:A
        session:{id}:video:B
        session:{id}:summary:A
        session:{id}:summary:B
        session:{id}:engagement
    """
    redis = _get_redis()

    meta_a = _extract_video_metadata(video_a)
    meta_b = _extract_video_metadata(video_b)

    engagement_comparison = _build_engagement_comparison(meta_a, meta_b)

    session_meta = {
        "session_id":  session_id,
        "created_at":  datetime.utcnow().isoformat(),
        "status":      "ready",
        "url_a":       video_a.get("url", ""),
        "url_b":       video_b.get("url", ""),
        "platform_a":  video_a.get("platform", ""),
        "platform_b":  video_b.get("platform", ""),
        "ttl_seconds": SESSION_TTL_SECONDS,
    }

    # ── Write all keys to Redis with TTL ──
    keys_to_write = {
        _key(session_id, "meta"):          session_meta,
        _key(session_id, "video", "A"):    meta_a,
        _key(session_id, "video", "B"):    meta_b,
        _key(session_id, "summary", "A"):  embed_summary_a,
        _key(session_id, "summary", "B"):  embed_summary_b,
        _key(session_id, "engagement"):    engagement_comparison,
    }

    written_keys = []
    for key, value in keys_to_write.items():
        redis.setex(
            key,
            SESSION_TTL_SECONDS,
            json.dumps(value),
        )
        written_keys.append(key)
        print(f"[cache_session] Cached → {key}")

    print(f"[cache_session] ✓ Session '{session_id}' cached. "
          f"{len(written_keys)} keys written. TTL: 24h.")

    return {
        "session_id":   session_id,
        "keys_written": written_keys,
        "engagement":   engagement_comparison,
        "status":       "cached",
    }


# ─────────────────────────────────────────────────────────────
#  Read helpers — used by the query graph (not ingestion)
# ─────────────────────────────────────────────────────────────

def get_video_metadata(session_id: str, video_id: str) -> Optional[dict]:
    """
    Fetch cached metadata for a single video.

    Args:
        session_id: The session ID
        video_id:   "A" or "B"

    Returns:
        metadata dict or None if not found / expired
    """
    redis = _get_redis()
    raw = redis.get(_key(session_id, "video", video_id))
    if raw is None:
        return [] if "history" in locals() else None
    if isinstance(raw, (str, bytes, bytearray)):
        return json.loads(raw)
    return raw


def get_both_metadata(session_id: str) -> dict:
    """
    Fetch cached metadata for both videos at once.
    Used by the intent_router for metadata-type questions.

    Returns:
        {"A": {...}, "B": {...}} or empty dicts if not found
    """
    return {
        "A": get_video_metadata(session_id, "A") or {},
        "B": get_video_metadata(session_id, "B") or {},
    }


def get_engagement_comparison(session_id: str) -> Optional[dict]:
    """
    Fetch precomputed engagement comparison.
    Used to answer "what's the engagement rate?" without Pinecone.
    """
    redis = _get_redis()
    raw = redis.get(_key(session_id, "engagement"))
    if raw is None:
        return [] if "history" in locals() else None
    if isinstance(raw, (str, bytes, bytearray)):
        return json.loads(raw)
    return raw


def get_session_meta(session_id: str) -> Optional[dict]:
    """
    Check if a session exists and is still valid.
    Returns session meta or None if expired/not found.
    """
    redis = _get_redis()
    raw = redis.get(_key(session_id, "meta"))
    if raw is None:
        return [] if "history" in locals() else None
    if isinstance(raw, (str, bytes, bytearray)):
        return json.loads(raw)
    return raw


def session_exists(session_id: str) -> bool:
    """Quick check — does this session exist in Redis?"""
    redis = _get_redis()
    return redis.exists(_key(session_id, "meta")) == 1


def delete_session(session_id: str) -> int:
    """
    Delete all keys for a session (manual cleanup).
    Returns number of keys deleted.
    """
    redis = _get_redis()
    keys = [
        _key(session_id, "meta"),
        _key(session_id, "video", "A"),
        _key(session_id, "video", "B"),
        _key(session_id, "summary", "A"),
        _key(session_id, "summary", "B"),
        _key(session_id, "engagement"),
        _key(session_id, "history"),      # also delete conversation history
    ]
    deleted = redis.delete(*keys)
    print(f"[cache_session] Deleted {deleted} keys for session '{session_id}'.")
    return deleted

# ─────────────────────────────────────────────────────────────
#  Conversation history — persisted in Redis per session
#
#  Key: session:{id}:history
#  Value: JSON array of {role, content, timestamp} dicts
#  TTL: refreshed to 24h on every write (sliding window)
#
#  Why Redis for history (not just frontend state):
#  - Survives page refresh, tab close, browser crash
#  - Frontend only needs to send session_id, not full history
#  - History is loaded once per turn in validate_session_node
#  - Saves bandwidth — no history payload on every request
# ─────────────────────────────────────────────────────────────

HISTORY_MAX_TURNS = 20   # max entries (10 exchanges) kept in Redis


def save_history(session_id: str, history: list[dict]) -> bool:
    """
    Persist conversation history to Redis.
    Overwrites the existing history for this session.
    Refreshes TTL to 24h on every save (sliding expiry).

    Args:
        session_id: The session ID
        history:    List of {"role": "user"|"assistant",
                             "content": "...",
                             "timestamp": "ISO string"} dicts

    Returns:
        True if saved successfully, False on error
    """
    redis = _get_redis()

    # Cap at max turns before saving
    if len(history) > HISTORY_MAX_TURNS:
        history = history[-HISTORY_MAX_TURNS:]

    try:
        redis.setex(
            _key(session_id, "history"),
            SESSION_TTL_SECONDS,    # refresh TTL on every write
            json.dumps(history),
        )
        # Also refresh the session meta TTL so session stays alive
        # as long as the conversation is active
        redis.expire(_key(session_id, "meta"), SESSION_TTL_SECONDS)
        print(f"[cache_session] History saved: {len(history)} turns for '{session_id}'.")
        return True
    except Exception as e:
        print(f"[cache_session] Failed to save history: {e}")
        return False


def load_history(session_id: str) -> list[dict]:
    """
    Load conversation history from Redis.
    Returns empty list if no history exists yet (first turn).

    Args:
        session_id: The session ID

    Returns:
        List of {"role", "content", "timestamp"} dicts
        Empty list if no history or session expired
    """
    redis = _get_redis()
    try:
        raw = redis.get(_key(session_id, "history"))
        if raw is None:
            return []
        if isinstance(raw, (str, bytes, bytearray)):
            return json.loads(raw)
        return raw
    except Exception as e:
        print(f"[cache_session] Failed to load history: {e}")
        return []


def append_turn(session_id: str, user_query: str, assistant_response: str) -> list[dict]:
    """
    Append one Q/A exchange to history and save back to Redis.
    This is the main function called by update_memory_node.

    Adds timestamp to each entry for potential UI display.
    Caps history at HISTORY_MAX_TURNS before saving.

    Args:
        session_id:          The session ID
        user_query:          The user's message
        assistant_response:  The assistant's response

    Returns:
        Updated history list (after appending + capping)
    """
    from datetime import datetime

    history = load_history(session_id)

    history.append({
        "role":      "user",
        "content":   user_query,
        "timestamp": datetime.utcnow().isoformat(),
    })
    history.append({
        "role":      "assistant",
        "content":   assistant_response,
        "timestamp": datetime.utcnow().isoformat(),
    })

    save_history(session_id, history)
    return history


def clear_history(session_id: str) -> bool:
    """
    Clear conversation history for a session without
    deleting the session itself (metadata + embeddings stay).
    Useful for "start new conversation" button in the UI.

    Returns True if cleared, False on error.
    """
    redis = _get_redis()
    try:
        redis.delete(_key(session_id, "history"))
        print(f"[cache_session] History cleared for '{session_id}'.")
        return True
    except Exception as e:
        print(f"[cache_session] Failed to clear history: {e}")
        return False


def get_history_length(session_id: str) -> int:
    """Returns number of turns in history. 0 if none."""
    return len(load_history(session_id))



# ─────────────────────────────────────────────────────────────
#  Session ID generator
# ─────────────────────────────────────────────────────────────

def make_session_id() -> str:
    """
    Generate a unique session ID.
    Format: vidrival_{8-char-uuid}
    Example: vidrival_a3f9c21b
    """
    return f"vidrival_{uuid.uuid4().hex[:8]}"


# ─────────────────────────────────────────────────────────────
#  LangGraph node wrapper
# ─────────────────────────────────────────────────────────────

def cache_session_node(state: dict) -> dict:
    """
    LangGraph node. Reads video_a, video_b, embed_summary_a,
    embed_summary_b from state. Generates a session_id,
    caches everything to Redis, writes session_id back to state.

    State keys consumed:
        video_a, video_b
        embed_summary_a, embed_summary_b

    State keys produced:
        session_id       → used by all query graph nodes
        cache_result     → summary of what was cached
        ingestion_complete → True
    """
    video_a         = state.get("video_a")
    video_b         = state.get("video_b")
    embed_summary_a = state.get("embed_summary_a", {})
    embed_summary_b = state.get("embed_summary_b", {})

    if not video_a or not video_b:
        raise ValueError("cache_session_node requires video_a and video_b in state.")

    # Reuse existing session_id if already in state (re-ingestion case)
    session_id = state.get("session_id") or make_session_id()

    cache_result = cache_session(
        session_id      = session_id,
        video_a         = video_a,
        video_b         = video_b,
        embed_summary_a = embed_summary_a,
        embed_summary_b = embed_summary_b,
    )

    print(f"[cache_session] ✓ Node complete. session_id={session_id}")

    return {
        **state,
        "session_id":         session_id,
        "cache_result":       cache_result,
        "ingestion_complete": True,
    }


# ─────────────────────────────────────────────────────────────
#  Quick test — python cache_session.py
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    # ── Mock data (replace with real fetch_video output) ──
    mock_video_a = {
        "video_id": "A", "platform": "youtube",
        "url": "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up",
        "creator": "Rick Astley", "follower_count": 4500000,
        "views": 1777682501, "likes": 19127703, "comments": 2400000,
        "hashtags": ["#RickAstley", "#NeverGonnaGiveYouUp"],
        "upload_date": "2009-10-25", "duration": 213,
        "engagement_rate": 1.211,
        "transcript": "We're no strangers to love...",
        "transcript_chunks": [],
    }
    mock_video_b = {
        "video_id": "B", "platform": "instagram",
        "url": "https://instagram.com/reel/example/",
        "title": "My Instagram Reel",
        "creator": "some_creator", "follower_count": 150000,
        "views": 500000, "likes": 45000, "comments": 3200,
        "hashtags": ["#reels", "#viral"],
        "upload_date": "2024-06-01", "duration": 30,
        "engagement_rate": 9.64,
        "transcript": "Hey everyone welcome back...",
        "transcript_chunks": [],
    }
    mock_summary_a = {"video_id": "A", "chunks_created": 12, "vectors_upserted": 12}
    mock_summary_b = {"video_id": "B", "chunks_created": 4,  "vectors_upserted": 4}

    # ── Test cache_session ──
    session_id = make_session_id()
    print(f"Generated session_id: {session_id}\n")

    result = cache_session(
        session_id      = session_id,
        video_a         = mock_video_a,
        video_b         = mock_video_b,
        embed_summary_a = mock_summary_a,
        embed_summary_b = mock_summary_b,
    )
    print("\nCache result:")
    print(json.dumps(result, indent=2))

    # ── Test reads ──
    print("\n── Reading back from Redis ──")

    meta_a = get_video_metadata(session_id, "A")
    print(f"\nVideo A metadata:")
    print(json.dumps(meta_a, indent=2))

    engagement = get_engagement_comparison(session_id)
    print(f"\nEngagement comparison:")
    print(json.dumps(engagement, indent=2))

    exists = session_exists(session_id)
    print(f"\nSession exists: {exists}")