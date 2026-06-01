import os
import json
import uuid
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

from upstash_redis import Redis

load_dotenv()

UPSTASH_REDIS_REST_URL   = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

SESSION_TTL_SECONDS = 60 * 60 * 24
HISTORY_MAX_TURNS   = 20

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


def _key(session_id: str, *parts: str) -> str:
    return f"session:{session_id}:{':'.join(parts)}"


def get_session_snapshot(session_id: str) -> dict:
    """
    Retrieve metadata, video A/B metadata, engagement, summaries and history
    in a single Redis MGET call where possible and return a dict snapshot.

    Returns keys (all optional):
      - meta
      - video_a
      - video_b
      - engagement
      - summary_a
      - summary_b
      - history
    """
    redis = _get_redis()

    keys = [
        _key(session_id, "meta"),
        _key(session_id, "video", "A"),
        _key(session_id, "video", "B"),
        _key(session_id, "engagement"),
        _key(session_id, "summary", "A"),
        _key(session_id, "summary", "B"),
        _key(session_id, "history"),
    ]

    # Prefer MGET for fewer roundtrips; fall back to individual GETs if not supported
    try:
        # Upstash client expects separate args; splat the keys for safety.
        raw = redis.mget(*keys)
    except Exception:
        raw = [redis.get(k) for k in keys]

    # Normalize returned formats: list, tuple, dict, or single value
    if isinstance(raw, dict):
        # Map keys to values preserving order
        raw = [raw.get(k) for k in keys]
    elif not isinstance(raw, (list, tuple)):
        # If a single value returned, fall back to individual GETs
        raw = [redis.get(k) for k in keys]

    def _parse(v):
        if not v:
            return None
        try:
            return json.loads(v)
        except Exception:
            # already JSON-decoded or plain string
            return v

    meta, video_a, video_b, engagement, summary_a, summary_b, history = [_parse(r) for r in raw]

    # Ensure history is a list
    if history is None:
        history = []

    return {
        "meta":       meta or {},
        "video_a":    video_a or {},
        "video_b":    video_b or {},
        "engagement": engagement or {},
        "summary_a":  summary_a or {},
        "summary_b":  summary_b or {},
        "history":    history or [],
    }


def _extract_video_metadata(video_data: dict) -> dict:
    """Strips transcript and chunks from VideoData — we only cache the metadata."""
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
    """Pre-computes engagement comparison so we never recalculate it per query."""
    eng_a   = meta_a.get("engagement_rate", 0.0)
    eng_b   = meta_b.get("engagement_rate", 0.0)
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


def cache_session(
    session_id: str,
    video_a: dict,
    video_b: dict,
    embed_summary_a: dict,
    embed_summary_b: dict,
) -> dict:
    """Stores all session data to Redis with a 24h TTL."""
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

    print(f"[cache_session] Session '{session_id}' cached. "
          f"{len(written_keys)} keys written. TTL: 24h.")

    return {
        "session_id":   session_id,
        "keys_written": written_keys,
        "engagement":   engagement_comparison,
        "status":       "cached",
    }


def _safe_parse(raw):
    """Parses a Redis value that might already be a Python object (Upstash auto-parses JSON)."""
    if raw is None:
        return None
    if isinstance(raw, (str, bytes, bytearray)):
        return json.loads(raw)
    return raw


def get_video_metadata(session_id: str, video_id: str) -> Optional[dict]:
    """Fetches cached metadata for a single video (A or B).

    Uses `get_session_snapshot` so callers that need multiple keys can be
    satisfied with one MGET. Returns an empty dict when missing to match
    previous behavior.
    """
    snap = get_session_snapshot(session_id)
    return snap.get("video_a" if video_id == "A" else "video_b") or {}


def get_both_metadata(session_id: str) -> dict:
    """Fetches metadata for both videos using a single snapshot MGET."""
    snap = get_session_snapshot(session_id)
    return {"A": snap.get("video_a", {}), "B": snap.get("video_b", {})}


def get_engagement_comparison(session_id: str) -> Optional[dict]:
    """Fetches the pre-computed engagement comparison dict via snapshot."""
    snap = get_session_snapshot(session_id)
    return snap.get("engagement") or {}


def get_session_meta(session_id: str) -> Optional[dict]:
    """Returns session meta dict, or None if expired."""
    snap = get_session_snapshot(session_id)
    return snap.get("meta") or None


def session_exists(session_id: str) -> bool:
    """Returns True if the session exists in Redis."""
    redis = _get_redis()
    return redis.exists(_key(session_id, "meta")) == 1


def delete_session(session_id: str) -> int:
    """Deletes all Redis keys for a session. Returns the number of keys deleted."""
    redis = _get_redis()
    keys = [
        _key(session_id, "meta"),
        _key(session_id, "video", "A"),
        _key(session_id, "video", "B"),
        _key(session_id, "summary", "A"),
        _key(session_id, "summary", "B"),
        _key(session_id, "engagement"),
        _key(session_id, "history"),
    ]
    deleted = redis.delete(*keys)
    print(f"[cache_session] Deleted {deleted} keys for session '{session_id}'.")
    return deleted


def save_history(session_id: str, history: list[dict]) -> bool:
    """Persists conversation history to Redis. Caps at HISTORY_MAX_TURNS and refreshes TTL."""
    redis = _get_redis()

    if len(history) > HISTORY_MAX_TURNS:
        history = history[-HISTORY_MAX_TURNS:]

    try:
        redis.setex(
            _key(session_id, "history"),
            SESSION_TTL_SECONDS,
            json.dumps(history),
        )
        redis.expire(_key(session_id, "meta"), SESSION_TTL_SECONDS)
        print(f"[cache_session] History saved: {len(history)} turns for '{session_id}'.")
        return True
    except Exception as e:
        print(f"[cache_session] Failed to save history: {e}")
        return False


def load_history(session_id: str) -> list[dict]:
    """Loads conversation history from Redis. Returns an empty list if none exists yet.

    Uses snapshot MGET when possible.
    """
    try:
        snap = get_session_snapshot(session_id)
        return snap.get("history", []) or []
    except Exception as e:
        print(f"[cache_session] Failed to load history: {e}")
        return []


def append_turn(session_id: str, user_query: str, assistant_response: str) -> list[dict]:
    """Appends one Q&A exchange to stored history and saves it back to Redis."""
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
    """Clears conversation history without touching session metadata or Pinecone vectors."""
    redis = _get_redis()
    try:
        redis.delete(_key(session_id, "history"))
        print(f"[cache_session] History cleared for '{session_id}'.")
        return True
    except Exception as e:
        print(f"[cache_session] Failed to clear history: {e}")
        return False


def get_history_length(session_id: str) -> int:
    """Returns how many turns are stored for this session."""
    return len(load_history(session_id))


def make_session_id() -> str:
    """Generates a unique session ID in the format engagex_{8-char-hex}."""
    return f"engagex_{uuid.uuid4().hex[:8]}"


def cache_session_node(state: dict) -> dict:
    """LangGraph node — generates a session ID, caches everything to Redis, passes it forward."""
    video_a         = state.get("video_a")
    video_b         = state.get("video_b")
    embed_summary_a = state.get("embed_summary_a", {})
    embed_summary_b = state.get("embed_summary_b", {})

    if not video_a or not video_b:
        raise ValueError("cache_session_node requires video_a and video_b in state.")

    session_id = state.get("session_id") or make_session_id()

    cache_result = cache_session(
        session_id      = session_id,
        video_a         = video_a,
        video_b         = video_b,
        embed_summary_a = embed_summary_a,
        embed_summary_b = embed_summary_b,
    )

    print(f"[cache_session] Node complete. session_id={session_id}")

    return {
        **state,
        "session_id":         session_id,
        "cache_result":       cache_result,
        "ingestion_complete": True,
    }