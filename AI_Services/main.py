"""
VidRival — main.py
FastAPI entry point.

Run locally:
    uvicorn main:app --reload --port 8000

Render start command:
    uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.ingestion_query_route import router, limiter, get_ingestion_app, get_query_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] Pre-building LangGraph graphs...")
    get_ingestion_app()
    get_query_app()
    print("[startup] Ready.")
    yield
    print("[shutdown] Shutting down.")


app = FastAPI(
    title       = "VidRival API",
    description = "RAG-powered video engagement analysis",
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ALLOWED_ORIGINS,
    allow_credentials = True,
    allow_methods     = ["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers     = ["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {
        "service":   "VidRival API",
        "docs":      "/docs",
        "health":    "/api/health",
        "endpoints": {
            "ingest":        "POST   /api/ingest",
            "query":         "POST   /api/query",
            "query_stream":  "POST   /api/query/stream",
            "session":       "GET    /api/session/{id}",
            "history":       "GET    /api/session/{id}/history",
            "clear_history": "DELETE /api/session/{id}/history",
            "rate_limits":   "GET    /api/rate-limits",
            "health":        "GET    /api/health",
        }
    }