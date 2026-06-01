# AI_Services

AI_Services is the backend service that powers EngageX’s video comparison and engagement analysis experience. It is designed to ingest pairs of social videos, build a context-rich session for them, and answer natural language questions using vector-search and large language models.

## What this project does

AI_Services is responsible for:
- ingesting two videos, extracting metadata, and computing engagement insights
- downloading and transcribing video audio
- splitting transcripts into timestamped chunks
- embedding text chunks and indexing them in Pinecone
- caching session state and conversation history in Redis
- answering question queries with a multi-stage retrieval and LLM pipeline
- streaming responses back to the frontend in real time

## Detailed Features

### Video ingestion pipeline

The ingestion pipeline accepts two video URLs and builds a searchable session.

Functionality:
- accept URLs from `YouTube` and `Instagram`
- download the video audio using `yt-dlp`
- use optional cookies if required (`YTDLP_COOKIES_PATH` or `YTDLP_COOKIES_BROWSER`)
- convert audio using `ffmpeg` when available
- transcribe audio through Groq Whisper using the Groq API
- clean transcript noise, remove tags like `[Music]`, and merge the text
- split transcripts into logically-sized chunks with timestamp alignment
- generate embeddings for every chunk using Hugging Face endpoint embeddings
- index the chunk vectors in Pinecone for semantic search
- store session metadata, summaries, and engagement comparisons in Redis

Why this matters:
- users get fast, accurate answers over the exact transcript and video metadata
- timestamped chunks enable precise citations in answers
- vector indexing enables semantic search, not keyword matching

### Asynchronous ingestion

Ingestion is intentionally decoupled from the API request.

How it works:
- `POST /api/ingest` receives ingest requests and validates URLs
- instead of processing immediately, it enqueues a job in RQ
- workers consume the job and perform the heavy ingestion steps
- the API returns `job_id` immediately so user experience stays fast
- the frontend can poll `GET /api/ingest/status/{job_id}`

Benefits:
- API remains responsive
- ingestion can run on separate machines or containers
- failures do not block the request path
- workload can be scaled by adding more workers

### Query and conversational interface

Once ingestion is complete and a session exists, users can ask questions.

Query endpoints:
- `POST /api/query` — synchronous answer
- `POST /api/query/stream` — SSE-style streaming response

Supported question types:
- `compare` — compare both videos side-by-side
- `single_a` / `single_b` — questions about only one video
- `metadata` — factual metadata questions
- `suggest` — improvement or recommendation questions

The query pipeline does the following:
1. validate the session exists in Redis
2. load metadata, engagement, and history
3. rewrite the user query into transcript-like text (HyDE-style)
4. classify question intent with a fast LLM
5. route metadata-only questions directly to Redis
6. retrieve relevant chunks from Pinecone for semantic matching
7. rerank retrieved chunks if needed
8. generate a final answer with a larger LLM
9. append the question and answer to session history

This flow gives a balanced tradeoff between accuracy and cost.

### Session management and caching

Sessions are stored in Redis with a 24-hour TTL.

Stored data includes:
- session metadata
- video A and B metadata
- engagement comparison summary
- embedded transcript summaries
- conversation history

The history is limited to recent turns and refreshed with each query so sessions stay active while in use.

### Rate limiting and abuse protection

The service uses `slowapi` and Upstash Redis for rate limiting.

Built-in protections:
- `POST /api/ingest` limited to `10/day`
- `POST /api/query` limited to `50/day`
- global request rate limiting via Redis-backed slowapi storage
- per-session query counting with `SESSION_QUERY_LIMIT = 50`

These limits are intended to protect capacity and control cost.

### Precomputed engagement comparison

During ingestion, AI_Services builds engagement statistics once and stores them.

This includes:
- engagement rate for both videos
- the engagement winner
- difference and percentage difference
- views comparison and likes/comments breakdown
- a small summary text

Precomputing this avoids recomputing the same engagement logic on every query.

## Architecture and component details

### High-level architecture

```
User -> FastAPI App
         ├─ /api/ingest
         ├─ /api/ingest/status/{job_id}
         ├─ /api/query
         └─ /api/query/stream
             |
             +--> Redis for session state and history
             +--> Pinecone for vector search
             +--> Groq and Hugging Face for model inference

Background worker process:
RQ queue -> ingestion_worker -> ingestion graph -> Redis/Pinecone
```

### Component responsibilities

- `main.py`
  - defines the FastAPI application
  - configures CORS and middleware
  - sets up lifespan events and rate-limit exception handling
  - includes the router from `api/ingestion_query_route.py`

- `api/ingestion_query_route.py`
  - defines API endpoints and Pydantic request/response models
  - sets up rate limiting using `slowapi`
  - validates sessions and query limits
  - invokes the query graph for question answering

- `workers/ingestion_worker.py`
  - entrypoint for RQ workers
  - loads the ingestion graph and executes ingestion jobs
  - returns the session id and engagement summary once complete

- `agents/Ingestion.py`
  - defines the ingestion pipeline nodes using `langgraph`
  - `fetch_video_node()` downloads/transcribes videos
  - `chunk_embed_node()` chunks and embeds transcripts
  - `cache_session_node()` stores session data in Redis

- `agents/query.py`
  - defines the query pipeline nodes using `langgraph`
  - performs validation, rewriting, intent classification, retrieval, reranking, response generation, and memory updates
  - implements caching for embeddings and rewritten queries

- `utils/transcribe.py`
  - detects platform and extracts video ids
  - downloads audio via `yt-dlp`
  - finds `ffmpeg` and converts audio when possible
  - sends audio to Groq Whisper and parses transcription segments

- `utils/chunk_and_embed.py`
  - cleans transcript text
  - builds timestamp mappings for chunks
  - splits text into chunks using LangChain text splitters
  - computes embeddings and upserts them in Pinecone

- `utils/cache_session.py`
  - manages Redis session state and history
  - provides helpers to load metadata, check existence, save history, and clear sessions
  - uses JSON serialization for Redis values and handles Upstash data formats

## Ingestion flow in detail

1. The frontend calls `POST /api/ingest` with `url_a` and `url_b`.
2. The API validates URL format and enqueues an RQ job in `ingest_queue`.
3. The worker process loads `agents/Ingestion.build_ingestion_graph()`.
4. `fetch_video_node()` executes:
   - `utils.transcribe.fetch_video()` downloads and transcribes both videos
   - it returns metadata and transcript segments for both A and B
5. `chunk_embed_node()` executes:
   - `utils.chunk_and_embed.chunk_and_embed()` cleans and chunks transcripts
   - text chunks are timestamped and converted to embeddings
   - chunks are stored in Pinecone with embedded metadata
6. `cache_session_node()` executes:
   - `utils.cache_session.cache_session()` stores session state in Redis
   - it writes metadata, engagement summary, and chunk summaries to Redis
7. The ingestion worker job completes and returns the new `session_id`.

## Query flow in detail

1. The frontend calls `POST /api/query` with `session_id` and `user_query`.
2. The API checks that the session exists and that query limits are not exceeded.
3. The query graph is built from `agents/query.py`.
4. `validate_session_node()` loads session metadata and history from Redis.
5. If the session is invalid, the graph returns a helpful error without doing retrieval.
6. If valid, `query_rewriter_node()` rewrites the question using Groq.
   - this improves semantic matching against transcript chunks
   - rewritten queries are cached with `@lru_cache`
7. `intent_router_node()` classifies the question intent using a fast Groq model.
8. `route_by_intent()` sends metadata-only questions to Redis and others to Pinecone.
9. `retrieve_node()` queries Pinecone with the rewritten query embedding.
10. `rerank_node()` optionally rescoring chunks with the fast LLM.
11. `stream_response_node()` produces the final answer with the larger Groq model.
12. `update_memory_node()` appends the question and answer to session history.

## Optimizations in depth

### Worker-based ingestion

By moving all ingestion work to a background worker, the API does not have to wait for:
- video downloads
- transcription
- chunk embedding
- vector indexing

This is essential for keeping user-facing latency low.

### Redis session cache

Instead of recomputing video metadata and summaries on every query, the service caches everything in Redis with a 24h TTL.

This reduces:
- repeated Redis reads for the same session
- repeated computation of engagement statistics
- the need to store large data on the API server

### Single-shot snapshots

`utils/cache_session.get_session_snapshot()` is optimized to read multiple Redis keys together. That reduces the number of round trips to Redis, which improves query latency.

### Cached query embeddings and rewrites

The code uses `@lru_cache` for:
- rewritten queries (`_cached_rewrite`)
- query embeddings (`_cached_embed_query`)

These caches reduce repeated calls to external ML APIs when the same question is asked multiple times.

### Metadata-only answers

Questions classified as `metadata` are answered directly from cached session data in Redis.

This bypasses:
- Pinecone vector search
- slow reranking
- expensive final LLM context preparation

This makes factual questions much cheaper and faster.

### Precomputed engagement metrics

The system computes the engagement winner, rates, and summary during ingestion and stores it.

That is more efficient than recomputing these values on each query.

## Scaling guidance

### What is already prepared for scale

- API is stateless with managed Redis and Pinecone
- ingestion is separate from user query traffic
- session state is externalized
- rate limits help keep load bounded

### What to scale for 1000 users/day

If 1000 users/day are mainly querying already ingested sessions, this architecture is a strong starting point.

If 1000 users/day are ingesting two new videos each, the workload is significantly larger and will require:
- more worker capacity
- higher Pinecone usage quotas
- more transcription/embedding budget
- stronger rate limiting

### Paid cloud services and cost efficiency

Using paid managed services will make the system more reliable, but cost efficiency still requires optimization.

Essential paid services:
- managed Redis / Upstash
- managed Pinecone vector database
- paid Groq inference for transcription and generation
- paid Hugging Face endpoint for embeddings

Cost-optimization guidelines:
- use cheaper models for query rewriting and reranking
- only use the large model for the final answer
- cache embeddings and repeated questions
- use metadata-only path for simple factual queries
- reuse sessions instead of re-ingesting the same videos

### Recommended production architecture

- deploy the FastAPI app behind a load balancer or API gateway
- run several app instances for request throughput
- run one or more dedicated ingestion worker services
- use managed Redis and Pinecone
- monitor queue length, job failure rate, and API error rate

## Deployment notes

### Required environment variables

Ensure `.env` includes:
- `REDIS_URL`
- `UPSTASH_REDIS_REST_URL`
- `UPSTASH_REDIS_REST_TOKEN`
- `PINECONE_API_KEY`
- `PINECONE_INDEX_NAME`
- `GROQ_API_KEY`
- `GROQ` (for `utils/transcribe.py` Groq client)
- `HUGGINGFACEHUB_API_TOKEN`
- `YTDLP_COOKIES_PATH` or `YTDLP_COOKIES_BROWSER` if needed

### Running locally

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
python workers/ingestion_worker.py
```

### Production deployment checklist

- use autoscaling or container orchestration for app and workers
- move Redis and Pinecone to managed cloud plans
- configure monitoring and logging
- secure credentials and environment variables
- add authentication if the service becomes public

## Why this design exists

The design separates heavy background work from the interactive query path, which is critical for a good user experience.

It uses multi-stage retrieval because:
- direct LLM answering on raw transcripts would be too expensive
- vector search makes the model focus on the most relevant context
- metadata-only answers avoid unnecessary inference
- session caching avoids repeated expensive work

## Future improvements

These enhancements would make the service stronger:
- add per-user authentication and quota tracking
- enable query result caching for repeated questions
- add session cleanup for expired Redis keys and stale Pinecone vectors
- switch to autoscaling workers in production
- add job failure tracking and retry handling
- support more video source platforms beyond YouTube and Instagram

## How to use this README in a presentation

This README now contains:
- feature-level descriptions
- architecture and pipeline explanations
- optimization details
- scaling guidance for production
- deployment instructions and environment setup
- suggested future enhancements

If you need, I can also produce a short “presentation-ready” summary of this README with bullet points for slides.