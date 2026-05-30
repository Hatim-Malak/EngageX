from utils.transcribe import fetch_video


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




if __name__ == "__main__":
    import json

    TEST_YT_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    TEST_IG_URL = "https://www.instagram.com/reel/YOUR_REEL_ID/"

    print("Testing YouTube fetch...")
    yt_data = fetch_video(TEST_YT_URL, "A")
    print(json.dumps({
        k: v for k, v in yt_data.items()
        if k not in ("transcript", "transcript_chunks")
    }, indent=2))
    print(f"Transcript preview: {yt_data['transcript']}")
    print(f"Total chunks: {len(yt_data['transcript_chunks'])}")