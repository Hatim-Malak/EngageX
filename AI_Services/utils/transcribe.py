"""
VidRival — fetch_video.py
Handles transcript + metadata extraction for YouTube and Instagram Reels.
Uses:
  - youtube-transcript-api  → YouTube captions (instant, no audio needed)
  - yt-dlp                  → audio download fallback + Instagram
  - Groq Whisper API        → transcription for Instagram Reels
"""

import os
import re
import json
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import TypedDict, Optional

import shutil
import httpx
import instaloader
import yt_dlp
from groq import Groq
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from dotenv import load_dotenv

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ"))


def _find_ffmpeg() -> Optional[str]:
    """
    Find ffmpeg binary. Checks PATH first, then common Windows install locations.
    Returns the directory containing ffmpeg.exe, or None if not found.
    """
    # Check if ffmpeg is already on PATH
    if shutil.which("ffmpeg"):
        return None  # None means yt-dlp will find it on PATH automatically

    # Common Windows locations
    candidates = [
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
        r"C:\Program Files (x86)\ffmpeg\bin",
        os.path.join(os.environ.get("USERPROFILE", ""), "ffmpeg", "bin"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "ffmpeg", "bin"),
    ]
    for path in candidates:
        if os.path.isfile(os.path.join(path, "ffmpeg.exe")):
            print(f"[ffmpeg] Found at: {path}")
            return path

    return None  # Not found — will fail gracefully later


FFMPEG_LOCATION = _find_ffmpeg()


# ─────────────────────────────────────────────────────────────
#  Return type
# ─────────────────────────────────────────────────────────────

class VideoData(TypedDict):
    video_id:        str          # "A" or "B"
    platform:        str          # "youtube" | "instagram"
    url:             str
    title:           str
    creator:         str
    follower_count:  int
    views:           int
    likes:           int
    comments:        int
    hashtags:        list[str]
    upload_date:     str          # "YYYY-MM-DD"
    duration:        int          # seconds
    engagement_rate: float        # (likes + comments) / views * 100
    transcript:      str          # full plain text
    transcript_chunks: list[dict] # [{text, start, end}]


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _detect_platform(url: str) -> str:
    """Detect whether URL is YouTube or Instagram."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    if any(h in host for h in ["youtube.com", "youtu.be"]):
        return "youtube"
    if any(h in host for h in ["instagram.com", "instagr.am"]):
        return "instagram"

    raise ValueError(f"Unsupported platform for URL: {url}")


def _extract_youtube_id(url: str) -> str:
    """Extract 11-character video ID from any YouTube URL format."""
    parsed = urlparse(url)

    # youtu.be/VIDEO_ID
    if "youtu.be" in parsed.netloc:
        return parsed.path.lstrip("/").split("?")[0]

    # youtube.com/watch?v=VIDEO_ID
    qs = parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0]

    # youtube.com/shorts/VIDEO_ID
    match = re.search(r"/shorts/([a-zA-Z0-9_-]{11})", parsed.path)
    if match:
        return match.group(1)

    raise ValueError(f"Cannot extract YouTube video ID from: {url}")


def _parse_hashtags(text: str) -> list[str]:
    """Extract hashtags from a description string."""
    return re.findall(r"#\w+", text or "")


def _format_date(raw: str) -> str:
    """Convert yt-dlp date string YYYYMMDD → YYYY-MM-DD."""
    if raw and len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw or "unknown"


def _compute_engagement(likes: int, comments: int, views: int) -> float:
    """Engagement rate = (likes + comments) / views × 100."""
    if not views:
        return 0.0
    return round((likes + comments) / views * 100, 4)


# ─────────────────────────────────────────────────────────────
#  Audio download + Groq Whisper transcription
# ─────────────────────────────────────────────────────────────

def _download_audio(url: str, tmp_dir: str) -> str:
    """
    Download audio from a video URL using yt-dlp.
    Returns path to the downloaded audio file.

    Strategy:
    - If ffmpeg is available: download bestaudio and convert to mp3 (smaller, faster upload to Groq)
    - If ffmpeg NOT found: download best audio-only format directly (m4a/webm)
      and send raw to Groq — Groq accepts m4a, mp4, webm, wav, flac, ogg
    """
    output_template = os.path.join(tmp_dir, "audio.%(ext)s")

    base_opts = {
        "outtmpl":    output_template,
        "quiet":      True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    }

    if FFMPEG_LOCATION is not None:
        # ffmpeg found at a specific path — tell yt-dlp where it is
        base_opts["ffmpeg_location"] = FFMPEG_LOCATION

    if FFMPEG_LOCATION is not None or shutil.which("ffmpeg"):
        # ffmpeg available — convert to mp3 (Groq's preferred format)
        base_opts["format"] = "bestaudio/best"
        base_opts["postprocessors"] = [{
            "key":             "FFmpegExtractAudio",
            "preferredcodec":  "mp3",
            "preferredquality": "64",  # 64kbps is enough for speech
        }]
        print("[fetch_video] ffmpeg found — downloading as mp3")
    else:
        # ffmpeg NOT available — download raw audio (m4a or webm)
        # Groq Whisper accepts: mp3, mp4, m4a, webm, wav, flac, ogg
        base_opts["format"] = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"
        print("[fetch_video] ffmpeg NOT found — downloading raw audio (m4a/webm). "
              "Install ffmpeg for better quality: winget install ffmpeg")

    with yt_dlp.YoutubeDL(base_opts) as ydl:
        ydl.download([url])

    # Find the output file (any audio extension)
    audio_extensions = ["*.mp3", "*.m4a", "*.webm", "*.wav", "*.ogg", "*.flac", "*.mp4"]
    for pattern in audio_extensions:
        for f in Path(tmp_dir).glob(pattern):
            print(f"[fetch_video] Audio downloaded: {f.name} ({f.stat().st_size // 1024} KB)")
            return str(f)

    raise FileNotFoundError(
        "yt-dlp did not produce an audio file. "
        "Check the URL is public and accessible."
    )


def _transcribe_with_groq(audio_path: str) -> list[dict]:
    """
    Send audio file to Groq Whisper API.
    Returns list of segments: [{text, start, end}]
    Groq free tier: 7,200 seconds of audio/day.

    NOTE: Groq SDK returns segments as plain dicts, not objects.
    Handles both dict and object forms defensively.
    """
    import json as _json

    with open(audio_path, "rb") as audio_file:
        response = groq_client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=audio_file,
            response_format="verbose_json",
            language="en",
        )

    # ── Normalise response: Groq SDK may return object, dict, or JSON string ──
    if isinstance(response, str):
        response = _json.loads(response)

    # Convert Pydantic/dataclass object → dict if needed
    if not isinstance(response, dict):
        if hasattr(response, "model_dump"):
            response = response.model_dump()       # Pydantic v2
        elif hasattr(response, "dict"):
            response = response.dict()             # Pydantic v1
        elif hasattr(response, "__dict__"):
            response = vars(response)
        else:
            response = {}

    raw_segments = response.get("segments") or []
    full_text    = response.get("text", "")

    segments = []

    if raw_segments:
        for seg in raw_segments:
            # seg is always a plain dict from Groq: {"text":"..","start":0.0,"end":2.5}
            if isinstance(seg, dict):
                text  = seg.get("text", "").strip()
                start = round(float(seg.get("start", 0.0)), 2)
                end   = round(float(seg.get("end",   0.0)), 2)
            else:
                # Object fallback (future-proofing)
                text  = getattr(seg, "text", "").strip()
                start = round(float(getattr(seg, "start", 0.0)), 2)
                end   = round(float(getattr(seg, "end",   0.0)), 2)

            if text:
                segments.append({"text": text, "start": start, "end": end})

        print(f"[groq] Transcribed {len(segments)} segments")

    if not segments and full_text:
        # No segments but have full text — single chunk fallback
        print("[groq] No segments returned, using full text as single chunk")
        segments = [{"text": full_text.strip(), "start": 0.0, "end": 0.0}]

    if not segments:
        raise ValueError("Groq returned empty transcription. Check audio file quality.")

    return segments


# ─────────────────────────────────────────────────────────────
#  YouTube fetch
# ─────────────────────────────────────────────────────────────

def _fetch_youtube(url: str, video_id: str) -> VideoData:
    """Fetch transcript + metadata for a YouTube video."""

    yt_vid_id = _extract_youtube_id(url)

    # ── 1. Transcript via youtube-transcript-api ──
    # Try order: manual EN → auto-generated EN → any language → Groq fallback
    transcript_chunks = []
    transcript_fetched = False

    try:
        # First: list all available transcripts
        transcript_list = YouTubeTranscriptApi.list_transcripts(yt_vid_id)

        fetched_raw = None

        # Try manual English captions first
        try:
            fetched_raw = transcript_list.find_manually_created_transcript(
                ["en", "en-US", "en-GB", "en-CA", "en-AU"]
            ).fetch()
        except Exception:
            pass

        # Try auto-generated English captions
        if not fetched_raw:
            try:
                fetched_raw = transcript_list.find_generated_transcript(
                    ["en", "en-US"]
                ).fetch()
            except Exception:
                pass

        # Try any available transcript (translate to English if needed)
        if not fetched_raw:
            try:
                first_transcript = next(iter(transcript_list))
                if first_transcript.language_code.startswith("en"):
                    fetched_raw = first_transcript.fetch()
                else:
                    # Translate to English
                    fetched_raw = first_transcript.translate("en").fetch()
            except Exception:
                pass

        if fetched_raw:
            transcript_chunks = [
                {
                    "text":  seg["text"].strip(),
                    "start": round(seg["start"], 2),
                    "end":   round(seg["start"] + seg.get("duration", 0), 2),
                }
                for seg in fetched_raw
                if seg.get("text", "").strip()
            ]
            transcript_fetched = True
            print(f"[fetch_video] Transcript fetched via youtube-transcript-api "
                  f"({len(transcript_chunks)} segments)")

    except Exception as e:
        print(f"[fetch_video] youtube-transcript-api failed: {type(e).__name__}: {e}")

    # ── Fallback to Groq Whisper if transcript not fetched ──
    if not transcript_fetched:
        print(f"[fetch_video] Falling back to Groq Whisper for {yt_vid_id}...")
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                audio_path = _download_audio(url, tmp_dir)
                transcript_chunks = _transcribe_with_groq(audio_path)
            print(f"[fetch_video] Groq Whisper transcription complete "
                  f"({len(transcript_chunks)} segments)")
        except Exception as e:
            print(f"[fetch_video] Groq Whisper also failed: {e}")
            # Last resort: empty transcript, don't crash the whole pipeline
            transcript_chunks = [{"text": "", "start": 0.0, "end": 0.0}]

    transcript_text = " ".join(c["text"] for c in transcript_chunks)

    # ── 2. Metadata via yt-dlp (no download, just info) ──
    ydl_opts = {
        "quiet":         True,
        "no_warnings":   True,
        "skip_download": True,
    }
    if FFMPEG_LOCATION:
        ydl_opts["ffmpeg_location"] = FFMPEG_LOCATION

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    likes          = info.get("like_count")             or 0
    comments       = info.get("comment_count")          or 0
    views          = info.get("view_count")              or 0
    follower_count = info.get("channel_follower_count") or 0

    return VideoData(
        video_id          = video_id,
        platform          = "youtube",
        url               = url,
        title             = info.get("title", "Unknown"),
        creator           = info.get("uploader", info.get("channel", "Unknown")),
        follower_count    = follower_count,
        views             = views,
        likes             = likes,
        comments          = comments,
        hashtags          = _parse_hashtags(info.get("description", "")),
        upload_date       = _format_date(info.get("upload_date", "")),
        duration          = info.get("duration") or 0,
        engagement_rate   = _compute_engagement(likes, comments, views),
        transcript        = transcript_text,
        transcript_chunks = transcript_chunks,
    )


# ─────────────────────────────────────────────────────────────
#  Instagram fetch
# ─────────────────────────────────────────────────────────────

def _fetch_instagram(url: str, video_id: str) -> VideoData:
    """
    Fetch transcript + metadata for an Instagram Reel.
    Instagram has no caption API → always uses Groq Whisper.
    Metadata comes directly from Instaloader GraphQL schema (authenticated).
    """
    # ── 1. Extract shortcode from URL ──
    match = re.search(r"/(?:p|reel|reels|tv)/([^/?#&]+)", url)
    if not match:
        raise ValueError(f"Could not extract Instagram shortcode from: {url}")
    shortcode = match.group(1)

    # ── 2. Metadata via Instaloader (AUTHENTICATED) ──
    print(f"[fetch_video] Fetching Instaloader metadata for {shortcode}...")
    L = instaloader.Instaloader(quiet=True)
    
    # >>> START OF UPDATE: Session Authentication Logic <<<
    ig_user = os.getenv("IG_USERNAME")
    ig_pass = os.getenv("IG_PASSWORD")
    
    if ig_user and ig_pass:
        try:
            # Try loading a saved cookie session file to stay under the radar
            L.load_session_from_file(ig_user)
            print("[fetch_video] Loaded existing Instagram session from file.")
        except FileNotFoundError:
            try:
                print("[fetch_video] No session file found. Logging into Instagram...")
                L.login(ig_user, ig_pass)
                L.save_session_to_file()  # Persist session to local file for next time
                print("[fetch_video] Successfully logged in and saved session.")
            except Exception as login_err:
                print(f"[fetch_video] Login failed: {login_err}. Attempting unauthenticated...")
    else:
        print("[fetch_video] WARNING: No IG credentials found in .env. Metrics may fail.")
    # >>> END OF UPDATE <<<

    # Fetch the post data using the authenticated context
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
    except Exception as e:
        raise RuntimeError(f"Instaloader failed to fetch post {shortcode}: {e}")

    # Extract metrics safely (Now unlocked via authentication)
    likes = post.likes or 0
    comments = post.comments or 0
    views = post.video_view_count if post.is_video and post.video_view_count else 0
    
    try:
        follower_count = post.owner_profile.followers or 0
    except Exception:
        follower_count = 0

    description = post.caption or ""
    title = description[:80] if description else "Instagram Reel"
    creator = post.owner_username or "Unknown"
    upload_date = post.date_utc.strftime("%Y-%m-%d") if post.date_utc else "unknown"
    
    duration = getattr(post, 'video_duration', 0)
    duration = int(duration) if duration else 0

    if not post.is_video or not post.video_url:
        raise ValueError("This Instagram post is not a video or has no video URL.")

    # ── 3. Direct Video Download + Groq Whisper transcription ──
    transcript_chunks = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        print("[fetch_video] Downloading Instagram MP4 directly for Groq Whisper...")
        video_path = os.path.join(tmp_dir, "video.mp4")
        
        with httpx.Client() as client:
            response = client.get(post.video_url, follow_redirects=True)
            response.raise_for_status()
            with open(video_path, "wb") as f:
                f.write(response.content)

        transcript_chunks = _transcribe_with_groq(video_path)

    transcript_text = " ".join(c["text"] for c in transcript_chunks)

    return VideoData(
        video_id        = video_id,
        platform        = "instagram",
        url             = url,
        title           = title,
        creator         = creator,
        follower_count  = follower_count,
        views           = views,
        likes           = likes,
        comments        = comments,
        hashtags        = _parse_hashtags(description),
        upload_date     = upload_date,
        duration        = duration,
        engagement_rate = _compute_engagement(likes, comments, views),
        transcript      = transcript_text,
        transcript_chunks = transcript_chunks,
    )


# ─────────────────────────────────────────────────────────────
#  Main public function — this is what LangGraph calls
# ─────────────────────────────────────────────────────────────

def fetch_video(url: str, video_id: str) -> VideoData:
    """
    Entry point for the LangGraph fetch_video_A / fetch_video_B nodes.

    Args:
        url:      Full YouTube or Instagram URL
        video_id: "A" or "B" — used to tag all chunks in Pinecone

    Returns:
        VideoData dict with transcript, metadata, and engagement rate

    Example:
        data = fetch_video("https://youtube.com/watch?v=dQw4w9WgXcQ", "A")
        print(data["engagement_rate"])   # 4.23
        print(data["transcript"][:200])  # first 200 chars
    """
    platform = _detect_platform(url)
    print(f"[fetch_video] Detected platform: {platform} | video_id: {video_id}")

    if platform == "youtube":
        return _fetch_youtube(url, video_id)
    elif platform == "instagram":
        return _fetch_instagram(url, video_id)
    else:
        raise ValueError(f"Unsupported platform: {platform}")


# ─────────────────────────────────────────────────────────────
#  LangGraph node wrapper
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
#  Quick test — run directly: python fetch_video.py
# ─────────────────────────────────────────────────────────────

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