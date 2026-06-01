# AI_Services

Backend for EngageX. Takes two video URLs, ingests them into a searchable session, and lets users ask natural language questions about the videos through a multi-stage RAG pipeline.

Built with FastAPI, LangGraph, Pinecone, Groq, and Upstash Redis. Runs entirely on free tiers right now.

---

## Table of Contents

- [What it does](#what-it-does)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [System architecture](#system-architecture)
- [The two LangGraph pipelines](#the-two-langgraph-pipelines)
- [Ingestion flow](#ingestion-flow)
- [Query flow](#query-flow)
- [API endpoints](#api-endpoints)
- [Optimisations](#optimisations)
- [Free-tier capacity (real numbers)](#free-tier-capacity-real-numbers)
- [What breaks at 1000 users/day](#what-breaks-at-1000-usersday)
- [Scaling to 1000 users/day](#scaling-to-1000-usersday)
- [Environment variables](#environment-variables)
- [Running locally](#running-locally)
- [Future work](#future-work)

---

## What it does

- Accepts two video URLs (YouTube or Instagram)
- Downloads audio, transcribes it, chunks the transcript, embeds the chunks with BGE-M3, and indexes everything in Pinecone
- Caches session state (video metadata, engagement stats, chat history) in Upstash Redis with 24h TTL
- Answers questions through a multi-stage pipeline: HyDE rewriting, intent classification, conditional retrieval, LLM reranking, and final generation with Llama 3.3 70B
- Streams responses via SSE to the chat frontend
- Rate-limits per IP and per session to stay within free-tier quotas

---

## Tech stack

| Layer | Technology | Reason |
|-------|-----------|--------|
| Web framework | FastAPI + Uvicorn | async, auto-docs, fast |
| Pipeline orchestration | LangGraph StateGraph | declarative nodes with conditional routing |
| Transcription | Groq Whisper (whisper-large-v3-turbo) | fastest whisper inference, cheap |
| YouTube transcripts | youtube-transcript-api | free fallback, avoids whisper entirely when captions exist |
| Video download | yt-dlp + ffmpeg | handles YT + IG, cookies, format conversion |
| Instagram metadata | instaloader | pulls likes, comments, views, followers from reels |
| Embeddings | HuggingFace Inference API (BAAI/bge-m3) | 1024-dim, multilingual, free tier |
| Vector DB | Pinecone serverless (AWS us-east-1) | managed, metadata filtering, scales well |
| Session cache | Upstash Redis (REST) | serverless, pay-per-request |
| Job queue | RQ (Redis Queue) | simple python job queue for background work |
| LLMs | Groq (llama-3.1-8b-instant + llama-3.3-70b-versatile) | fast model for routing, big model for answers |
| Rate limiting | SlowAPI + Upstash Redis | per-IP + per-session, redis-backed counters |

---

## Project structure

```
AI_Services/
├── main.py                           # FastAPI app, CORS, middleware, lifespan
├── api/
│   └── ingestion_query_route.py      # all endpoints, pydantic models, rate limits
├── agents/
│   ├── Ingestion.py                  # LangGraph ingestion pipeline (graph 1)
│   └── query.py                      # LangGraph query pipeline (graph 2)
├── utils/
│   ├── transcribe.py                 # video download, platform detection, groq whisper
│   ├── chunk_and_embed.py            # transcript cleaning, chunking, embedding, pinecone upsert
│   └── cache_session.py              # redis session CRUD, history mgmt, MGET snapshots
├── workers/
│   └── ingestion_worker.py           # RQ worker entry point for background ingestion
├── requirements.txt
├── pyproject.toml
└── .env
```

---

## System architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Frontend (React/Vite)                        │
│   POST /api/ingest  ·  GET /api/ingest/status/{job_id}               │
│   POST /api/query   ·  POST /api/query/stream                        │
│   GET /api/session/{id}/full  ·  DELETE /api/session/{id}/history     │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTPS
                                v
┌──────────────────────────────────────────────────────────────────────┐
│                     FastAPI Application (Render)                      │
│                                                                       │
│  ┌─────────────┐   ┌──────────────────┐   ┌───────────────────────┐  │
│  │  SlowAPI     │   │  API routes      │   │  Query Graph          │  │
│  │  Rate Limiter│   │  (endpoints +    │   │  (singleton,          │  │
│  │  (Redis)     │   │   validation)    │   │   built at startup)   │  │
│  └──────┬──────┘   └──────┬───────────┘   └──────────┬────────────┘  │
│         │                  │                          │               │
│         v                  v                          v               │
│    ┌─────────┐     ┌──────────────┐          ┌──────────────┐        │
│    │ Upstash │     │ RQ Job Queue │          │ LangGraph    │        │
│    │ Redis   │<----│ (enqueue)    │          │ Query Pipeline│       │
│    │ (REST)  │     └──────┬───────┘          └──────┬───────┘        │
│    └────┬────┘            │                         │                │
└─────────┼────────────────┼─────────────────────────┼────────────────┘
          │                │                         │
          │                v                         │
          │  ┌──────────────────────────┐            │
          │  │   RQ Worker Process      │            │
          │  │   (separate container)   │            │
          │  │                          │            │
          │  │   LangGraph Ingestion    │            │
          │  │   Pipeline               │            │
          │  └─────┬──────────┬─────────┘            │
          │        │          │                      │
          v        v          v                      v
  ┌──────────┐  ┌────────┐  ┌──────────┐  ┌──────────────────┐
  │ Upstash  │  │ Groq   │  │ Pinecone │  │ HuggingFace      │
  │ Redis    │  │ API    │  │ Vector DB│  │ Inference API     │
  │          │  │        │  │          │  │ (BGE-M3 embeds)   │
  │ sessions │  │ whisper│  │ chunked  │  └──────────────────┘
  │ history  │  │ llama  │  │ vectors  │
  │ metadata │  │ 3.1/3.3│  │ 1024-dim │       ┌───────────┐
  │ rate     │  └────────┘  │ cosine   │       │ yt-dlp    │
  │ limits   │              └──────────┘       │ ffmpeg    │
  └──────────┘                                 │instaloader│
                                               └───────────┘
```

The key design decision: ingestion and querying are completely separate. The API never blocks on video processing. It enqueues the job and returns a `job_id`. The worker picks it up, does the heavy lifting, and writes results to Redis + Pinecone. The frontend polls for completion.

---

## The two LangGraph pipelines

The whole system runs on two compiled LangGraph `StateGraph` instances. One handles ingestion, the other handles queries. Both get compiled once and reused.

### Graph 1 — Ingestion Pipeline

Defined in `agents/Ingestion.py`, function `build_ingestion_graph()`.

Linear, 3 nodes, no branching:

```
START
  │
  v
fetch_video_node
  │  - detect platform (YT or IG)
  │  - download audio via yt-dlp
  │  - try YT captions first (free), fall back to groq whisper
  │  - extract metadata: views, likes, comments, followers, etc.
  │  - compute engagement rate: (likes + comments) / views * 100
  │
  v
chunk_embed_node
  │  - clean transcript (strip [Music], noise tokens)
  │  - build character-offset-to-timestamp mapping
  │  - split with RecursiveCharacterTextSplitter (2000 chars, 300 overlap)
  │  - map each chunk back to video timestamps
  │  - embed via BGE-M3 (1024-dim) with retry on 429s
  │  - upsert to Pinecone in batches of 100
  │
  v
cache_session_node
  │  - generate session ID (engagex_ + 8 hex chars)
  │  - strip raw transcript, keep only metadata
  │  - precompute engagement comparison (winner, diff, summary)
  │  - write 6 redis keys with 24h TTL
  │
  v
END
```

State shape:

```python
class IngestionState(TypedDict):
    url_a:              str
    url_b:              str
    video_a:            Optional[dict]    # full VideoData
    video_b:            Optional[dict]
    embed_summary_a:    Optional[dict]    # chunk/vector stats
    embed_summary_b:    Optional[dict]
    ingestion_complete: bool
    session_id:         str
    cache_result:       Optional[dict]
```

---

### Graph 2 — Query Pipeline

Defined in `agents/query.py`, function `build_query_graph()`.

9 nodes, 2 conditional routing edges:

```
START
  │
  v
validate_session_node
  │  - check session exists in redis
  │  - load metadata, engagement, history via MGET (1 call)
  │
  ├── session invalid ──> handle_invalid_session_node ──> END
  │                        ("Session not found or expired.")
  │
  v (session valid)
query_rewriter_node
  │  - HyDE rewrite via llama-3.1-8b-instant
  │  - turns "what hook does video A use?" into transcript-like text
  │  - cached with @lru_cache(4096)
  │
  v
intent_router_node
  │  - classify into: compare | single_a | single_b | metadata | suggest
  │  - uses llama-3.1-8b-instant, JSON output
  │  - fallback: compare
  │
  ├── intent == "metadata"
  │       │
  │       v
  │   metadata_lookup_node
  │       │  - answer from redis cache
  │       │  - zero pinecone calls
  │       │  - zero embedding calls
  │       │
  ├── intent != "metadata"
  │       │
  │       v
  │   retrieve_node
  │       │  - embed rewritten query (cached, @lru_cache 8192)
  │       │  - query pinecone
  │       │  - compare/suggest: top 6 per video (12 total)
  │       │  - single_a/b: top 8 from one video
  │       │
  └───────┤
          v
      rerank_node
          │  - skip if from redis (metadata)
          │  - skip if <= 5 chunks
          │  - score 0-10 via llama-3.1-8b, keep top 5
          │  - fallback: cosine score sort
          │
          v
      stream_response_node
          │  - system prompt with formatting rules
          │  - inject metadata + engagement context
          │  - include last 6 history turns
          │  - intent-specific instructions
          │  - generate via llama-3.3-70b (temp=0.7, 1024 max tokens)
          │  - extract inline citations [Video A, MM:SS-MM:SS]
          │
          v
      update_memory_node
          │  - append Q&A turn to redis
          │  - cap at 20 turns
          │  - refresh TTL
          │
          v
        END
```

State shape:

```python
class QueryState(TypedDict):
    session_id:       str
    user_query:       str
    chat_history:     Optional[list[dict]]
    session_valid:    Optional[bool]
    meta_a:           Optional[dict]
    meta_b:           Optional[dict]
    engagement:       Optional[dict]
    rewritten_query:  Optional[str]
    intent:           Optional[str]       # compare|single_a|single_b|metadata|suggest
    retrieved_chunks: Optional[list[dict]]
    context_source:   Optional[str]       # "pinecone" or "redis"
    reranked_chunks:  Optional[list[dict]]
    response:         Optional[str]
    citations:        Optional[list[dict]]
    updated_history:  Optional[list[dict]]
```

---

## Ingestion flow

Step by step, what happens when someone ingests two videos:

1. Frontend calls `POST /api/ingest` with `{ url_a, url_b }`
2. API validates URLs (must be youtube or instagram), enqueues an RQ job, returns `job_id` immediately
3. RQ worker picks up the job, calls `build_ingestion_graph().invoke()`
4. `fetch_video_node` runs for both videos:
   - detects platform from URL
   - for YouTube: tries `youtube-transcript-api` first (manual captions > auto-generated > translated). only falls back to groq whisper if no captions exist at all
   - for Instagram: always downloads video MP4 via instaloader + httpx, sends to groq whisper
   - pulls metadata: title, creator, followers, views, likes, comments, hashtags, upload date, duration
   - computes engagement rate
5. `chunk_embed_node` runs for both:
   - cleans transcript (strips `[Music]`, `♪lyrics♪`, extra whitespace)
   - joins segments into one string, builds character-offset-to-timestamp lookup
   - splits using RecursiveCharacterTextSplitter (2000 chars, 300 overlap)
   - maps each chunk back to its timestamp range
   - creates deterministic chunk IDs via MD5
   - embeds via HuggingFace BGE-M3 with exponential backoff retry (3 attempts)
   - upserts to pinecone in batches of 100
6. `cache_session_node` finishes it off:
   - generates session ID
   - strips raw transcript from video data to save redis memory
   - precomputes engagement comparison (winner, rates, diff, summary text)
   - writes 6 redis keys: meta, video:A, video:B, engagement, summary:A, summary:B. all with 24h TTL
7. Frontend polls `GET /api/ingest/status/{job_id}` every 3-5s until `"finished"`

---

## Query flow

What happens when someone asks a question:

1. Frontend calls `POST /api/query` or `POST /api/query/stream` with `{ session_id, user_query }`
2. API checks session exists, checks per-session daily limit (50 queries/session/day)
3. `validate_session_node` loads metadata + engagement + history in one MGET call
4. `query_rewriter_node` does a HyDE rewrite — turns the question into transcript-like text so embedding similarity works better. cached with `@lru_cache(4096)`, so repeated questions skip the LLM
5. `intent_router_node` classifies the question into one of 5 intents via llama-3.1-8b. JSON output, falls back to "compare" if parsing fails
6. routing:
   - `metadata` intent goes to `metadata_lookup_node` — answers straight from redis, no pinecone, no embedding
   - everything else goes to `retrieve_node` — embeds the rewritten query (also cached), queries pinecone
7. `retrieve_node` does filtered vector search:
   - compare/suggest: top 6 per video = 12 chunks
   - single_a/b: top 8 from one video
8. `rerank_node` scores chunks 0-10 via llama-3.1-8b, keeps top 5. skipped if metadata path or if already <= 5 chunks. falls back to cosine sort if LLM parsing fails
9. `stream_response_node` generates the final answer with llama-3.3-70b (temp 0.7). includes metadata context, last 6 history turns, intent-specific instructions. extracts citations via regex
10. `update_memory_node` appends Q&A to redis, caps at 20 turns, refreshes session TTL

---

## API endpoints

| Method | Endpoint | Rate Limit | What it does |
|--------|----------|------------|-------------|
| POST | `/api/ingest` | 10/day per IP | enqueue video pair for ingestion |
| GET | `/api/ingest/status/{job_id}` | none | poll ingestion job status |
| POST | `/api/query` | 50/day per IP | synchronous query |
| POST | `/api/query/stream` | 50/day per IP | SSE streaming query |
| GET | `/api/session/{id}` | 60/hour | session metadata + engagement |
| GET | `/api/session/{id}/full` | 60/hour | full session state in one call |
| GET | `/api/session/{id}/history` | 60/hour | conversation history |
| DELETE | `/api/session/{id}/history` | 10/hour | clear history, keep session |
| GET | `/api/rate-limits` | 30/hour | current rate limit status |
| GET | `/api/health` | none | health check for uptime monitors |

---

## Optimisations

Everything listed here is actually implemented in the codebase. Not planned, not theoretical — it's in the code right now.

### YouTube caption fallback

`utils/transcribe.py` — tries three caption sources before touching whisper:
1. manual english captions
2. auto-generated english
3. any language, auto-translated to english

Most youtube videos have at least auto-generated captions. This saves 100% of the whisper quota for those videos.

### Singleton clients

`agents/query.py`, `utils/chunk_and_embed.py` — every external client (groq LLMs, HF embeddings, pinecone index) is initialised once as a global and reused. no redundant connections.

### Query graph pre-built at startup

`main.py` lifespan event compiles the query graph during startup. first user request doesn't pay the compilation cost.

### Cached query rewrites

`agents/query.py`, `@lru_cache(maxsize=4096)` on `_cached_rewrite`. if 10 users ask the same question against the same videos, only the first one hits groq. cache key is `(query, title_a, title_b)`.

### Cached query embeddings

`agents/query.py`, `@lru_cache(maxsize=8192)` on `_cached_embed_query`. identical rewritten queries reuse the same embedding vector without calling huggingface again.

### MGET session snapshots

`utils/cache_session.py`, `get_session_snapshot()` — fetches meta, video A, video B, engagement, summary A, summary B, and history in a single MGET call instead of 7 separate GETs. cuts redis command count roughly in half per query.

### Metadata fast path

`agents/query.py` — when intent is classified as `metadata` (like "how many views does video A have?"), the pipeline answers directly from cached redis data. no pinecone search, no embedding, no reranking. saves 3-4 external API calls.

### Precomputed engagement

`utils/cache_session.py`, `_build_engagement_comparison()` — engagement winner, rates, diff, and summary are computed once during ingestion and stored. never recalculated.

### Two-model strategy

- `llama-3.1-8b-instant` (temp 0.0, 512 tokens): routing, rewriting, reranking. 3 cheap calls.
- `llama-3.3-70b-versatile` (temp 0.7, 1024 tokens): final answer only. 1 expensive call.

keeps token cost low where quality doesn't matter as much.

### Rerank skip

reranking is skipped when context came from redis (metadata queries) or when there are 5 or fewer chunks. saves one groq call on simple queries.

### Timestamp-preserving chunking

`utils/chunk_and_embed.py` — built a character-offset-to-timestamp mapping so chunks can be traced back to their original video timestamps after splitting. this is what makes inline citations like `[Video A, 02:15-02:45]` possible.

### Retry with backoff on embeddings

`utils/chunk_and_embed.py` — `@retry(wait_exponential(min=2, max=10), stop_after_attempt(3))` on the HF embedding call. handles transient 429s from the free tier.

### Transcript cleaning

`utils/chunk_and_embed.py` — strips `[Music]`, `[Applause]`, `♪lyrics♪` before chunking. prevents garbage chunks that would pollute vector search.

### Non-blocking ingestion

`workers/ingestion_worker.py` — ingestion runs in a separate RQ worker process. API returns `job_id` in under 200ms, frontend polls for completion. failures don't crash the API, workers can scale independently.

### History capping

`utils/cache_session.py` — history is trimmed to 20 turns before saving. query pipeline further limits to last 6 turns in the LLM prompt. bounds redis memory and context window size.

### Per-session daily limits

`api/ingestion_query_route.py` — each session gets 50 queries/day via redis counters with TTL. prevents one abusive session from eating the entire groq/HF quota.

### Health endpoint for cold-start prevention

`/api/health` has no rate limit. pin it to UptimeRobot (free, every 5 min) to keep render from sleeping the service.

---

## Free-tier capacity (real numbers)

Running entirely on free tiers. Here is what that actually supports:

### Per-service limits

| Service | Free Limit | Usage Per User |
|---------|-----------|----------------|
| Groq Whisper | 7,200 audio-seconds/day | ~90s per video x 2 = 180s per ingestion |
| Groq LLMs | 500K tok/min (8B), 12K tok/min (70B) | ~3K tokens per query across models |
| HuggingFace | ~10,000 requests/day | ~20-30 embed calls per ingestion, 1 per query |
| Upstash Redis | 10,000 commands/day | ~8-10 commands per query, ~12 per ingestion |
| Pinecone | 1 index, 1GB storage | ~20-40 vectors per video, fine for hundreds of sessions |
| Render | 512MB RAM, 0.1 CPU | app + worker sharing resources |

### Realistic daily capacity

| Metric | Capacity |
|--------|----------|
| Ingestions/day | ~30-40 (whisper is the bottleneck: 7200s / 180s = 40) |
| Queries/day | ~500-800 (upstash 10K commands / ~12 per query) |
| Concurrent users | ~5-10 (render 0.1 CPU) |
| Active sessions | ~100-200 (redis memory + 24h TTL) |
| Comfortable users/day | ~100-200 |

The optimisations above squeeze about 3-5x more out of these free tiers than a naive implementation would. the youtube caption fallback alone saves the entire whisper budget for most youtube videos. the metadata fast path skips pinecone + HF for roughly 20% of queries. MGET cuts redis commands in half.

---

## What breaks at 1000 users/day

### Groq Whisper — the real killer

Free limit: 7,200 audio-seconds/day. Need for 1000 users: 1000 x 180s = 180,000s. That's **25x over the limit**.

Even with youtube caption fallback saving ~60% of ingestions from whisper, instagram reels always need it. unworkable on free tier at this scale.

### Upstash Redis — 4.5x over

Free limit: 10,000 commands/day. At 1000 users x 5 queries x 9 redis ops = 45,000 commands. **4.5x over**.

### HuggingFace — 2.5x over

Free limit: ~10,000 requests/day. At 1000 ingestions x 25 embed calls = 25,000 requests. **2.5x over**. LRU cache helps on queries but ingestion embeddings are always unique.

### Groq LLMs — fine

The two-model strategy keeps token usage low enough. 500K tok/min for 8b and 12K tok/min for 70b are both within budget even at 1000 users.

### Pinecone — fine

1 index, 1GB storage handles thousands of sessions. cold starts disappear at high volume.

### Render — tight

512MB RAM gets tight with concurrent ingestions. 0.1 CPU with only 2 workers means queues could build to 30+ minutes at 50 concurrent ingestions.

---

## Scaling to 1000 users/day

### Phase 1: tier upgrades (~$27/month)

The cheapest path to real 1000 users/day:

| Service | Change | Monthly Cost |
|---------|--------|:------------:|
| Render | Starter plan — 1GB RAM, 0.5 CPU | $7 |
| Upstash Redis | pay-as-you-go (~$0.2 per 100K commands) | ~$8 |
| HuggingFace | switch to OpenAI text-embedding-3-small ($0.02/1M tokens) | ~$2 |
| Groq Whisper | paid tier ($0.111/hour audio) | ~$10 |
| Pinecone | free tier still fine | $0 |
| **Total** | | **~$27/month** |

### Phase 2: architecture changes

Things I would change in the code itself:

**Separate API and worker containers.** Right now they share one render instance. Splitting them means the API stays responsive during heavy ingestion, workers can scale to 2-3 instances, and OOM risk drops.

```
┌──────────────┐     ┌──────────────────┐
│ Render Web   │     │ Render Worker    │
│ (API only)   │     │ (ingestion only) │
│ 512MB, 0.5CPU│     │ 1GB, 0.5CPU      │
└──────┬───────┘     └────────┬─────────┘
       └──────────┬───────────┘
                  │
            ┌─────v─────┐
            │ Upstash   │
            │ Redis     │
            └───────────┘
```

**Response caching.** Cache final LLM responses in redis keyed by `(session_id, query_hash, intent)`. "Compare the engagement" gets asked by almost everyone. a 1-hour TTL on response caches would cut ~30% of LLM calls.

**Batch embedding.** Instead of embedding chunks per-video, accumulate from multiple ingestions and embed in one larger batch. HF charges per request not per token — fewer requests = more capacity.

**Connection pooling.** Replace per-request upstash REST client with a persistent connection pool. right now `_get_redis()` creates a new client each time in the API routes. a singleton with keep-alive would reduce latency and TCP overhead.

**Smarter whisper routing.** For short videos (< 30s, most IG reels), use groq whisper. For longer videos, use OpenAI whisper ($0.006/min) — cheaper at scale and no daily quota.

### Phase 3: production hardening

| Change | Impact |
|--------|--------|
| authentication (API keys or OAuth) | per-user quotas, abuse prevention |
| job failure tracking + dead letter queue | no silent ingestion failures |
| pinecone vector cleanup on session expiry | prevents storage bloat over time |
| request logging to a time-series DB | debugging, monitoring |
| auto-scaling worker pool | handle ingestion spikes |
| websocket streaming instead of SSE | better connection management |
| CDN for static assets | reduce render bandwidth usage |

---

## Environment variables

```env
# Redis (for RQ job queue — standard redis protocol)
REDIS_URL=redis://default:xxx@your-redis-host:6379

# Upstash Redis (for session state — REST API)
UPSTASH_REDIS_REST_URL=https://your-db.upstash.io
UPSTASH_REDIS_REST_TOKEN=your_token

# Pinecone
PINECONE_API_KEY=your_key
PINECONE_INDEX_NAME=engagex

# Groq
GROQ_API_KEY=your_key          # used by langchain-groq in agents/query.py
GROQ=your_key                  # used by groq SDK in utils/transcribe.py

# HuggingFace
HUGGINGFACEHUB_API_TOKEN=hf_xxxxx

# Optional: yt-dlp cookies for age-restricted videos
YTDLP_COOKIES_PATH=./youtube_cookies.txt
# or
YTDLP_COOKIES_BROWSER=chrome

# Optional: Instagram credentials
IG_USERNAME=your_username
IG_PASSWORD=your_password

# CORS
ALLOWED_ORIGINS=http://localhost:5173,https://your-frontend.vercel.app
```

---

## Running locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the API:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Start the worker (separate terminal):

```bash
python workers/ingestion_worker.py
```

Test:

```bash
curl http://localhost:8000/api/health

curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"url_a": "https://youtube.com/watch?v=xxx", "url_b": "https://youtube.com/watch?v=yyy"}'

curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"session_id": "engagex_abc12345", "user_query": "Compare the hooks"}'
```

---

## Future work

- per-user auth and quota tracking
- response caching for repeated queries
- pinecone vector cleanup when sessions expire
- auto-scaling workers
- job failure tracking with dead letter queue
- tiktok and twitter/X support
- multi-language transcripts
- websocket streaming
- observability (prometheus + grafana or similar)
- experiment with different chunk sizes and overlap strategies