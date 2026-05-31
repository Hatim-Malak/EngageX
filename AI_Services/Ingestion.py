from utils.transcribe import fetch_video
from utils.chunk_and_embed import chunk_and_embed

def fetch_video_node(state: dict) -> dict:
    """
    LangGraph node. Reads url_a / url_b from state,
    fetches both videos, writes results back to state.

    State keys consumed:  url_a, url_b
    State keys produced:  video_a, video_b
    """
    video_a = fetch_video(state["url_a"], "A")
    video_b = fetch_video(state["url_b"], "B")

    return {
        **state,
        "video_a": video_a,
        "video_b": video_b,
    }




def chunk_embed_node(state: dict) -> dict:
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
        **state,
        "embed_summary_a":   summary_a,
        "embed_summary_b":   summary_b,
        "ingestion_complete": True,
    }


# ─────────────────────────────────────────────────────────────
#  Quick test — python chunk_embed.py
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, os.path.dirname(__file__))



    TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    print("=" * 60)
    print("Step 1: Fetching video...")
    print("=" * 60)
    video_data = fetch_video(TEST_URL, "A")
    print(f"Got transcript: {len(video_data['transcript_chunks'])} segments")

    print("\n" + "=" * 60)
    print("Step 2: Chunk + Embed + Upsert...")
    print("=" * 60)
    result = chunk_and_embed(video_data)

    print("\n" + "=" * 60)
    print("Result:")
    print("=" * 60)
    print(json.dumps(result, indent=2))