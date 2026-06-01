import os
import json
import asyncio
from typing import Optional
from datetime import datetime, date
from redis import Redis as StandardRedis
from rq import Queue
from rq.job import Job
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from upstash_redis import Redis
from dotenv import load_dotenv
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
#  Redis & Queue Setup
# ─────────────────────────────────────────────────────────────

UPSTASH_REDIS_URI = os.getenv("REDIS_URL")  
if not UPSTASH_REDIS_URI:
    raise RuntimeError("UPSTASH_REDIS_URI missing in .env")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000/day"],
    storage_uri=UPSTASH_REDIS_URI, 
)

# Standard Redis connection for RQ
redis_conn = StandardRedis.from_url(UPSTASH_REDIS_URI)
ingest_queue = Queue("ingestion", connection=redis_conn)

router = APIRouter(prefix="/api", tags=["EngageX"])

# Upstash REST client for session state and queries
def _get_redis() -> Redis:
    url   = os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        raise RuntimeError("Upstash Redis credentials missing in .env")
    return Redis(url=url, token=token)

SESSION_QUERY_LIMIT = 50
TTL_DAY             = 86400

def _check_session_query_limit(session_id: str) -> tuple[int, int]:
    """Increments the per-session daily query counter and raises 429 if the limit is hit."""
    redis  = _get_redis()
    bucket = date.today().isoformat()
    key    = f"ratelimit:session_daily:{session_id}:{bucket}"

    current = redis.incr(key)
    if current == 1:
        redis.expire(key, TTL_DAY)

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
#  Graph Singletons
# ─────────────────────────────────────────────────────────────

_query_app = None

def get_query_app():
    global _query_app
    if _query_app is None:
        _query_app = build_query_graph()
    return _query_app


# ─────────────────────────────────────────────────────────────
#  Pydantic Models
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


class QueuedIngestResponse(BaseModel):
    job_id: str
    status: str
    message: str


class IngestionResult(BaseModel):
    session_id: str
    engagement_winner: str
    engagement_rate_a: float
    engagement_rate_b: float


class JobStatusResponse(BaseModel):
    status: str
    result: Optional[IngestionResult] = None
    error: Optional[str] = None


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
    session_id:        str
    exists:            bool
    video_a:           Optional[dict]
    video_b:           Optional[dict]
    engagement:        Optional[dict]
    history:           list[dict]
    history_length:    int
    queries_used:      int
    queries_remaining: int
    queries_limit:     int


# ─────────────────────────────────────────────────────────────
#  Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/ingest", response_model=QueuedIngestResponse)
@limiter.limit("10/day")
async def ingest_videos(request: Request, body: IngestRequest):
    """
    Dispatches the heavy ingestion graph to a background worker.
    Returns a job_id immediately so the frontend doesn't hang.
    """
    try:
        job = ingest_queue.enqueue(
            "workers.ingestion_worker.run_ingestion_job", 
            args=(body.url_a, body.url_b),
            job_timeout=600  # 10 minutes max for Whisper/Pinecone ops
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "queue_failed", "message": str(e)}
        )

    return QueuedIngestResponse(
        job_id=job.id,
        status="queued",
        message="Videos added to the processing queue."
    )


@router.get("/ingest/status/{job_id}", response_model=JobStatusResponse)
async def get_ingestion_status(job_id: str):
    """
    Frontend polls this endpoint every 3-5 seconds to check if ingestion is done.
    """
    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.is_finished:
        return JobStatusResponse(status="finished", result=job.result)
    elif job.is_failed:
        return JobStatusResponse(status="failed", error=str(job.exc_info))
    else:
        return JobStatusResponse(status=job.get_status())


@router.post("/query", response_model=QueryResponse)
@limiter.limit("50/day")
async def query(request: Request, body: QueryRequest):
    """Non-streaming query endpoint. History is loaded automatically from Redis."""
    if not session_exists(body.session_id):
        raise HTTPException(
            status_code = 404,
            detail = {
                "error":   "session_not_found",
                "message": f"Session '{body.session_id}' not found or expired. Re-ingest your videos.",
            }
        )

    count, limit = _check_session_query_limit(body.session_id)

    try:
        app    = get_query_app()
        result = app.invoke({
            "session_id":   body.session_id,
            "user_query":   body.user_query,
            "chat_history": [],
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
@limiter.limit("50/day")
async def query_stream(request: Request, body: QueryRequest):
    """Streaming query via SSE. Use this for the chat UI."""
    if not session_exists(body.session_id):
        raise HTTPException(
            status_code = 404,
            detail = {
                "error":   "session_not_found",
                "message": f"Session '{body.session_id}' not found or expired.",
            }
        )

    count, limit = _check_session_query_limit(body.session_id)
    remaining    = max(0, limit - count)

    async def event_generator():
        yield (
            f"data: [RATELIMIT]"
            f"{{\"used\": {count}, \"limit\": {limit}, \"remaining\": {remaining}}}\n\n"
        )

        try:
            loop = asyncio.get_event_loop()

            def run_sync():
                return list(stream_query(body.session_id, body.user_query))

            chunks = await loop.run_in_executor(None, run_sync)

            for chunk in chunks:
                yield chunk
                await asyncio.sleep(0)

        except Exception as e:
            yield f"data: [ERROR]{json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type = "text/event-stream",
        headers    = {
            "Cache-Control":         "no-cache",
            "Connection":            "keep-alive",
            "X-Accel-Buffering":     "no",
            "X-RateLimit-Limit":     str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset":     "tomorrow 00:00 UTC",
        }
    )


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
@limiter.limit("60/hour")
async def get_session_status(session_id: str, request: Request):
    """Retrieves session status, video metadata, and engagement comparison."""
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
    """Returns everything the chat UI needs on page load in one call."""
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

    both_meta  = get_both_metadata(session_id)
    engagement = get_engagement_comparison(session_id)
    history    = load_history(session_id)

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
    """Retrieves full conversation history for a session."""
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
    """Clears conversation history without touching the session or Pinecone vectors."""
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
    """Returns current rate limit status. Pass ?session_id=... for per-session usage."""
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
    Pin this in UptimeRobot (free) every 5 min to prevent Render cold starts.
    """
    return {
        "status":    "ok",
        "service":   "EngageX API",
        "timestamp": datetime.utcnow().isoformat(),
    }