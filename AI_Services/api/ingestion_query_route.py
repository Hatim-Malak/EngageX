"""
VidRival — api/routes.py
FastAPI APIRouter with all endpoints.
Rate limiting via slowapi (wrapper around limits library).

Endpoints:
  POST   /api/ingest                    → ingest both videos
  POST   /api/query                     → single query turn
  POST   /api/query/stream              → SSE streaming query
  GET    /api/session/{id}              → session status + metadata
  GET    /api/session/{id}/full         → session + metadata + history in ONE call
  GET    /api/session/{id}/history      → conversation history only
  DELETE /api/session/{id}/history      → clear history
  GET    /api/rate-limits               → current usage
  GET    /api/health                    → health check (pin in UptimeRobot)

Rate limits (slowapi):
  POST /api/ingest        →  5/day    per IP   (heavy op)
  POST /api/query         → 50/day    per IP   (per-session enforced inside)
  POST /api/query/stream  → 50/day    per IP
  GET  /api/session/*     → 60/hour   per IP
  GET  /api/health        → no limit

Dependencies:
  pip install slowapi limits fastapi upstash-redis
"""

import os
import json
import asyncio
from typing import Optional
from datetime import datetime, date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from upstash_redis import Redis
from dotenv import load_dotenv

from agents.Ingestion import build_ingestion_graph
from agents.query  import build_query_graph, stream_query
from utils.cache_session import (
    session_exists,
    get_both_metadata,
    get_engagement_comparison,
    get_history_length,
    clear_history,
    load_history,
)

load_dotenv()

# ─────────────────────────────────────────────────────────────
#  slowapi Limiter
#
#  key_func: what identifies a "user" for rate limiting
#  get_remote_address: uses X-Forwarded-For on Render (real IP)
#
#  Storage backend: in-memory by default (fine for single Render instance)
#  For multi-instance: use storage_uri="redis://..." but Render free = 1 instance
# ─────────────────────────────────────────────────────────────

limiter = Limiter(
    key_func        = get_remote_address,   # rate limit per IP
    default_limits  = ["1000/day"],         # global fallback across all endpoints
)

# ─────────────────────────────────────────────────────────────
#  Router
# ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["VidRival"])

# ─────────────────────────────────────────────────────────────
#  Upstash Redis (for session_id-level query tracking only)
#  slowapi handles IP-level limits
#  Redis handles per-session daily query counts
# ─────────────────────────────────────────────────────────────

def _get_redis() -> Redis:
    url   = os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        raise RuntimeError("Upstash Redis credentials missing in .env")
    return Redis(url=url, token=token)


SESSION_QUERY_LIMIT = 50     # max queries per session per day
TTL_DAY             = 86400  # 24 hours in seconds


def _check_session_query_limit(session_id: str) -> tuple[int, int]:
    """
    Check and increment per-session daily query counter in Upstash Redis.
    Returns (current_count, limit).
    Raises HTTP 429 if limit exceeded.

    Why Redis for this (not slowapi):
    slowapi keys off IP address. One IP can have multiple sessions,
    and one session can be accessed from multiple IPs (mobile → desktop).
    Per-session limiting needs the session_id as the key → Redis directly.
    """
    redis  = _get_redis()
    bucket = date.today().isoformat()          # resets daily
    key    = f"ratelimit:session_daily:{session_id}:{bucket}"

    current = redis.incr(key)
    if current == 1:
        redis.expire(key, TTL_DAY)            # set TTL on first request

    if current > SESSION_QUERY_LIMIT:
        raise HTTPException(
            status_code = 429,
            detail = {
                "error":       "session_daily_limit_exceeded",
                "message":     f"Max {SESSION_QUERY_LIMIT} queries per session per day.",
                "limit":       SESSION_QUERY_LIMIT,
                "current":     int(current),
                "retry_after": "tomorrow 00:00 UTC",
            }
        )

    return int(current), SESSION_QUERY_LIMIT


# ─────────────────────────────────────────────────────────────
#  Graph singletons — built once at startup, reused every request
# ─────────────────────────────────────────────────────────────

_ingestion_app = None
_query_app     = None


def get_ingestion_app():
    global _ingestion_app
    if _ingestion_app is None:
        print("[api] Building ingestion graph...")
        _ingestion_app = build_ingestion_graph()
    return _ingestion_app


def get_query_app():
    global _query_app
    if _query_app is None:
        print("[api] Building query graph...")
        _query_app = build_query_graph()
    return _query_app


# ─────────────────────────────────────────────────────────────
#  Request / Response schemas
# ─────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    url_a: str
    url_b: str

    @field_validator("url_a", "url_b")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("http"):
            raise ValueError("URL must start with http:// or https://")
        supported = ["youtube.com", "youtu.be", "instagram.com", "instagr.am"]
        if not any(s in v for s in supported):
            raise ValueError(
                f"Only YouTube and Instagram URLs supported. Got: {v[:60]}"
            )
        return v


class IngestResponse(BaseModel):
    session_id:        str
    status:            str
    chunks_a:          int
    chunks_b:          int
    engagement_winner: str
    engagement_rate_a: float
    engagement_rate_b: float
    message:           str


class QueryRequest(BaseModel):
    session_id: str
    user_query: str

    @field_validator("user_query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("user_query cannot be empty")
        if len(v) > 1000:
            raise ValueError("user_query must be under 1000 characters")
        return v


class QueryResponse(BaseModel):
    session_id:  str
    response:    str
    citations:   list[dict]
    intent:      Optional[str]
    history_len: int
    queries_used:      int
    queries_remaining: int


class SessionStatusResponse(BaseModel):
    session_id:     str
    exists:         bool
    video_a:        Optional[dict]
    video_b:        Optional[dict]
    engagement:     Optional[dict]
    history_length: int


class SessionFullResponse(BaseModel):
    """Combined response for page load — metadata + history in one call."""
    session_id:      str
    exists:          bool
    video_a:         Optional[dict]
    video_b:         Optional[dict]
    engagement:      Optional[dict]
    history:         list[dict]       # full conversation history
    history_length:  int
    queries_used:    int
    queries_remaining: int
    queries_limit:   int


# ─────────────────────────────────────────────────────────────
#  Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestResponse)
@limiter.limit("5/day")          # 5 ingestions per IP per day
async def ingest_videos(request: Request, body: IngestRequest):
    """
    Ingest two videos: fetch transcripts + metadata, chunk + embed,
    upsert to Pinecone, cache to Redis.

    Returns session_id — store this in your frontend for all future queries.

    Rate limit: 5 ingestions/day per IP (slowapi)
    Takes: 30–120 seconds depending on video length.
    """
    try:
        app    = get_ingestion_app()
        result = app.invoke({
            "url_a": body.url_a,
            "url_b": body.url_b,
        })
    except Exception as e:
        raise HTTPException(
            status_code = 500,
            detail = {"error": "ingestion_failed", "message": str(e)}
        )

    engagement = result.get("cache_result", {}).get("engagement", {})
    summary_a  = result.get("embed_summary_a", {})
    summary_b  = result.get("embed_summary_b", {})
    session_id = result.get("session_id", "")

    return IngestResponse(
        session_id        = session_id,
        status            = "ready",
        chunks_a          = summary_a.get("chunks_created", 0),
        chunks_b          = summary_b.get("chunks_created", 0),
        engagement_winner = engagement.get("winner", "?"),
        engagement_rate_a = engagement.get("engagement_rate_a", 0.0),
        engagement_rate_b = engagement.get("engagement_rate_b", 0.0),
        message           = (
            f"Ingestion complete. Session ID: {session_id}. "
            f"Video {engagement.get('winner','?')} has higher engagement "
            f"({engagement.get('engagement_rate_a',0):.2f}% vs "
            f"{engagement.get('engagement_rate_b',0):.2f}%). "
            f"You have {SESSION_QUERY_LIMIT} queries available today."
        ),
    )


@router.post("/query", response_model=QueryResponse)
@limiter.limit("50/day")         # 50 queries per IP per day (slowapi)
async def query(request: Request, body: QueryRequest):
    """
    Single query — returns full response (non-streaming).
    History loaded automatically from Redis.

    Rate limits:
      - 50 queries/day per IP     (slowapi)
      - 50 queries/day per session (Upstash Redis)
    """
    if not session_exists(body.session_id):
        raise HTTPException(
            status_code = 404,
            detail = {
                "error":   "session_not_found",
                "message": f"Session '{body.session_id}' not found or expired. Re-ingest your videos.",
            }
        )

    # Per-session limit (slowapi handles per-IP above)
    count, limit = _check_session_query_limit(body.session_id)

    try:
        app    = get_query_app()
        result = app.invoke({
            "session_id":   body.session_id,
            "user_query":   body.user_query,
            "chat_history": [],   # loaded from Redis inside graph
        })
    except Exception as e:
        raise HTTPException(
            status_code = 500,
            detail = {"error": "query_failed", "message": str(e)}
        )

    history_len = get_history_length(body.session_id)
    remaining   = max(0, limit - count)

    return JSONResponse(
        content = QueryResponse(
            session_id        = body.session_id,
            response          = result.get("response", ""),
            citations         = result.get("citations", []),
            intent            = result.get("intent"),
            history_len       = history_len,
            queries_used      = count,
            queries_remaining = remaining,
        ).model_dump(),
        headers = {
            "X-RateLimit-Limit":     str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset":     "tomorrow 00:00 UTC",
        }
    )


@router.post("/query/stream")
@limiter.limit("50/day")         # 50 streaming queries per IP per day
async def query_stream(request: Request, body: QueryRequest):
    """
    Streaming query via Server-Sent Events.
    Responses stream word by word. Use this for the chat UI.

    SSE events:
      data: [RATELIMIT]{...}\\n\\n   → rate limit info (first event)
      data: <word> \\n\\n            → response tokens
      data: [CITATIONS]{...}\\n\\n   → citations (end of response)
      data: [DONE]\\n\\n             → stream complete

    Rate limits: same as /query
    """
    if not session_exists(body.session_id):
        raise HTTPException(
            status_code = 404,
            detail = {
                "error":   "session_not_found",
                "message": f"Session '{body.session_id}' not found or expired.",
            }
        )

    # Per-session limit
    count, limit = _check_session_query_limit(body.session_id)
    remaining    = max(0, limit - count)

    async def event_generator():
        # First event: rate limit info so frontend can update UI
        yield (
            f"data: [RATELIMIT]"
            f"{{\"used\": {count}, \"limit\": {limit}, \"remaining\": {remaining}}}\n\n"
        )

        try:
            loop = asyncio.get_event_loop()

            # stream_query is sync generator — run in thread pool
            # so it doesn't block FastAPI's async event loop
            def run_sync():
                return list(stream_query(body.session_id, body.user_query))

            chunks = await loop.run_in_executor(None, run_sync)

            for chunk in chunks:
                yield chunk
                await asyncio.sleep(0)   # yield control between tokens

        except Exception as e:
            yield f"data: [ERROR]{json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type = "text/event-stream",
        headers    = {
            "Cache-Control":         "no-cache",
            "Connection":            "keep-alive",
            "X-Accel-Buffering":     "no",             # disable Nginx buffering on Render
            "X-RateLimit-Limit":     str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset":     "tomorrow 00:00 UTC",
        }
    )


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
@limiter.limit("60/hour")
async def get_session_status(session_id: str, request: Request):
    """
    Check if session exists, load video metadata and engagement comparison.
    Call on page load to validate session before showing the chat UI.
    """
    exists = session_exists(session_id)

    if not exists:
        return SessionStatusResponse(
            session_id     = session_id,
            exists         = False,
            video_a        = None,
            video_b        = None,
            engagement     = None,
            history_length = 0,
        )

    both_meta   = get_both_metadata(session_id)
    engagement  = get_engagement_comparison(session_id)
    history_len = get_history_length(session_id)

    return SessionStatusResponse(
        session_id     = session_id,
        exists         = True,
        video_a        = both_meta.get("A"),
        video_b        = both_meta.get("B"),
        engagement     = engagement,
        history_length = history_len,
    )


@router.get("/session/{session_id}/full", response_model=SessionFullResponse)
@limiter.limit("60/hour")
async def get_session_full(session_id: str, request: Request):
    """
    Combined endpoint — returns EVERYTHING needed on page load in ONE request:
      - Session existence check
      - Video A + B metadata (title, creator, views, likes, engagement rate...)
      - Engagement comparison (winner, diff, summary)
      - Full conversation history (for rendering previous messages)
      - Current rate limit usage

    Use this instead of calling /session/{id} and /session/{id}/history separately.
    Replaces two round-trips with one.

    Frontend usage (on /chat page load):
        const data = await api.get(`/session/${sessionId}/full`)
        if (!data.exists) redirect to /
        set videoA, videoB, engagement, messages, queriesRemaining from data
    """
    exists = session_exists(session_id)

    if not exists:
        return SessionFullResponse(
            session_id        = session_id,
            exists            = False,
            video_a           = None,
            video_b           = None,
            engagement        = None,
            history           = [],
            history_length    = 0,
            queries_used      = 0,
            queries_remaining = SESSION_QUERY_LIMIT,
            queries_limit     = SESSION_QUERY_LIMIT,
        )

    # Load everything in parallel using Redis — all fast reads
    both_meta  = get_both_metadata(session_id)
    engagement = get_engagement_comparison(session_id)
    history    = load_history(session_id)

    # Get current query usage from Redis
    redis  = _get_redis()
    bucket = date.today().isoformat()
    key    = f"ratelimit:session_daily:{session_id}:{bucket}"
    try:
        queries_used = int(redis.get(key) or 0)
    except Exception:
        queries_used = 0

    queries_remaining = max(0, SESSION_QUERY_LIMIT - queries_used)

    return SessionFullResponse(
        session_id        = session_id,
        exists            = True,
        video_a           = both_meta.get("A"),
        video_b           = both_meta.get("B"),
        engagement        = engagement,
        history           = history,
        history_length    = len(history),
        queries_used      = queries_used,
        queries_remaining = queries_remaining,
        queries_limit     = SESSION_QUERY_LIMIT,
    )


@router.get("/session/{session_id}/history")
@limiter.limit("60/hour")
async def get_session_history(session_id: str, request: Request):
    """
    Retrieve full conversation history for a session.
    Returns list of {role, content, timestamp} dicts.
    """
    if not session_exists(session_id):
        raise HTTPException(
            status_code = 404,
            detail = {"error": "session_not_found", "message": f"Session '{session_id}' not found."}
        )

    history = load_history(session_id)
    return {
        "session_id": session_id,
        "history":    history,
        "count":      len(history),
    }


@router.delete("/session/{session_id}/history")
@limiter.limit("10/hour")
async def clear_session_history(session_id: str, request: Request):
    """
    Clear conversation history without deleting the session.
    Use for the 'New Conversation' button — videos stay ingested.
    """
    if not session_exists(session_id):
        raise HTTPException(
            status_code = 404,
            detail = {"error": "session_not_found"}
        )

    success = clear_history(session_id)
    return {
        "session_id": session_id,
        "cleared":    success,
        "message":    "History cleared. Videos still ingested — no need to re-ingest.",
    }


@router.get("/rate-limits")
@limiter.limit("30/hour")
async def get_rate_limit_status(request: Request):
    """
    Returns current per-session rate limit status.
    Pass session_id as query param to check session usage.

    Example: GET /api/rate-limits?session_id=vidrival_a3f9c21b
    """
    session_id = request.query_params.get("session_id")
    result     = {
        "ip_limits": {
            "ingest":  {"limit": "5/day",  "note": "per IP address"},
            "query":   {"limit": "50/day", "note": "per IP address"},
            "stream":  {"limit": "50/day", "note": "per IP address"},
        },
        "session_limits": {
            "queries": {"limit": SESSION_QUERY_LIMIT, "per": "day", "resets": "00:00 UTC"},
        },
    }

    if session_id and session_exists(session_id):
        redis  = _get_redis()
        bucket = date.today().isoformat()
        key    = f"ratelimit:session_daily:{session_id}:{bucket}"
        try:
            used = int(redis.get(key) or 0)
        except Exception:
            used = 0

        result["session"] = {
            "session_id":  session_id,
            "used_today":  used,
            "limit":       SESSION_QUERY_LIMIT,
            "remaining":   max(0, SESSION_QUERY_LIMIT - used),
            "resets":      "tomorrow 00:00 UTC",
        }

    return result


@router.get("/health")
async def health_check():
    """
    Health check — no rate limit.
    Pin this in UptimeRobot (free) every 5 min to prevent Render cold starts:
    uptimerobot.com → New Monitor → HTTP → https://your-app.render.com/api/health
    """
    return {
        "status":    "ok",
        "service":   "VidRival API",
        "timestamp": datetime.utcnow().isoformat(),
    }