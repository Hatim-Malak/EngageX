from utils.transcribe import fetch_video
from utils.chunk_and_embed import chunk_and_embed
from utils.cache_session import make_session_id,cache_session
import os
from typing import TypedDict,Optional
from langgraph.graph import StateGraph,START,END



class IngestionState(TypedDict):
    url_a:str
    url_b:str
    video_a:Optional[dict]
    video_b:Optional[dict]
    embed_summary_a:Optional[dict]
    embed_summary_b:Optional[dict]
    ingestion_complete:bool
    session_id:str
    cache_result:Optional[dict]
    

def fetch_video_node(state: IngestionState) -> dict:
    """
    LangGraph node. Reads url_a / url_b from state,
    fetches both videos, writes results back to state.

    State keys consumed:  url_a, url_b
    State keys produced:  video_a, video_b
    """
    video_a = fetch_video(state["url_a"], "A")
    video_b = fetch_video(state["url_b"], "B")

    return {
        "video_a": video_a,
        "video_b": video_b,
    }




def chunk_embed_node(state: IngestionState) -> dict:
    """
    LangGraph node. Reads video_a and video_b from state,
    runs chunk_and_embed for both, writes summaries back.

    State keys consumed:  video_a, video_b
    State keys produced:  embed_summary_a, embed_summary_b, ingestion_complete
    """
    video_a = state.get("video_a")
    video_b = state.get("video_b")

    if not video_a or not video_b:
        raise ValueError("chunk_embed_node requires both video_a and video_b in state")

    summary_a = chunk_and_embed(video_a)
    summary_b = chunk_and_embed(video_b)

    return {
        "embed_summary_a":   summary_a,
        "embed_summary_b":   summary_b,
    }


# # ─────────────────────────────────────────────────────────────
# #  Quick test — python chunk_embed.py
# # ─────────────────────────────────────────────────────────────

# if __name__ == "__main__":
#     import json
#     import sys
#     sys.path.insert(0, os.path.dirname(__file__))



#     TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

#     print("=" * 60)
#     print("Step 1: Fetching video...")
#     print("=" * 60)
#     video_data = fetch_video(TEST_URL, "A")
#     print(f"Got transcript: {len(video_data['transcript_chunks'])} segments")

#     print("\n" + "=" * 60)
#     print("Step 2: Chunk + Embed + Upsert...")
#     print("=" * 60)
#     result = chunk_and_embed(video_data)

#     print("\n" + "=" * 60)
#     print("Result:")
#     print("=" * 60)
#     print(json.dumps(result, indent=2))
    

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
        "session_id":         session_id,
        "cache_result":       cache_result,
        "ingestion_complete": True,
    }

def build_ingestion_graph() ->StateGraph:
    graph = StateGraph(IngestionState)
    
    graph.add_node("fetch_video_node",fetch_video_node)
    graph.add_node("chunk_embed_node",chunk_embed_node)
    graph.add_node("cache_session_node",cache_session_node)
    
    graph.add_edge(START,"fetch_video_node")
    graph.add_edge("fetch_video_node","chunk_embed_node")
    graph.add_edge("chunk_embed_node","cache_session_node")
    graph.add_edge("cache_session_node",END)
    
    app = graph.compile()
    
    return app