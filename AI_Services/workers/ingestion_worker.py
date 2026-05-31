import os
from redis import Redis
from rq import SimpleWorker as Worker, Queue
from dotenv import load_dotenv

from agents.Ingestion import build_ingestion_graph

load_dotenv()


def run_ingestion_job(url_a: str, url_b: str) -> dict:
    """
    Runs the heavy LangGraph ingestion pipeline.
    This executes on the background worker, not the web server.
    """
    app = build_ingestion_graph()
    result = app.invoke({
        "url_a": url_a,
        "url_b": url_b,
    })
    
    engagement = result.get("cache_result", {}).get("engagement", {})
    
    return {
        "session_id": result.get("session_id"),
        "engagement_winner": engagement.get("winner", "?"),
        "engagement_rate_a": engagement.get("engagement_rate_a", 0.0),
        "engagement_rate_b": engagement.get("engagement_rate_b", 0.0),
    }


if __name__ == '__main__':
    redis_url = os.getenv("REDIS_URL")
    redis_conn = Redis.from_url(redis_url)
    
    # Pass the connection directly to the worker
    worker = Worker(["ingestion"], connection=redis_conn)
    print("[Worker] Listening for ingestion jobs...")
    worker.work()