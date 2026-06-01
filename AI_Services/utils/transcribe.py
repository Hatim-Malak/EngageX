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
from yt_dlp.utils import DownloadError
from groq import Groq
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from dotenv import load_dotenv

load_dotenv()

YTDLP_COOKIES_PATH = os.getenv("YTDLP_COOKIES_PATH")
YTDLP_COOKIES_BROWSER = os.getenv("YTDLP_COOKIES_BROWSER")

groq_client = Groq(api_key=os.getenv("GROQ"))


def _find_ffmpeg() -> Optional[str]:
    """Checks PATH then common Windows install locations for ffmpeg. Returns the bin dir or None."""
    if shutil.which("ffmpeg"):
        return None

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

    return None


FFMPEG_LOCATION = _find_ffmpeg()


class VideoData(TypedDict):
    video_id:          str
    platform:          str
    url:               str
    title:             str
    creator:           str
    follower_count:    int
    views:             int
    likes:             int
    comments:          int
    hashtags:          list[str]
    upload_date:       str
    duration:          int
    engagement_rate:   float
    transcript:        str
    transcript_chunks: list[dict]


def _detect_platform(url: str) -> str:
    """Returns 'youtube' or 'instagram' based on the URL host."""
    parsed = urlparse(url)
    host   = parsed.netloc.lower()

    if any(h in host for h in ["youtube.com", "youtu.be"]):
        return "youtube"
    if any(h in host for h in ["instagram.com", "instagr.am"]):
        return "instagram"

    raise ValueError(f"Unsupported platform for URL: {url}")


def _extract_youtube_id(url: str) -> str:
    """Extracts the 11-character video ID from any YouTube URL format."""
    parsed = urlparse(url)

    if "youtu.be" in parsed.netloc:
        return parsed.path.lstrip("/").split("?")[0]

    qs = parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0]

    match = re.search(r"/shorts/([a-zA-Z0-9_-]{11})", parsed.path)
    if match:
        return match.group(1)

    raise ValueError(f"Cannot extract YouTube video ID from: {url}")


def _parse_hashtags(text: str) -> list[str]:
    """Extracts all #hashtags from a description string."""
    return re.findall(r"#\w+", text or "")


def _format_date(raw: str) -> str:
    """Converts yt-dlp's YYYYMMDD string to YYYY-MM-DD."""
    if raw and len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw or "unknown"


def _compute_engagement(likes: int, comments: int, views: int) -> float:
    """Returns (likes + comments) / views × 100, or 0.0 if views is zero."""
    if not views:
        return 0.0
    return round((likes + comments) / views * 100, 4)


def _build_yt_dlp_opts(base_opts: dict | None = None) -> dict:
    opts = dict(base_opts or {})
    if YTDLP_COOKIES_PATH:
        opts["cookiefile"] = YTDLP_COOKIES_PATH
        print(f"[yt-dlp] Using cookies file from YTDLP_COOKIES_PATH: {YTDLP_COOKIES_PATH}")
    elif YTDLP_COOKIES_BROWSER:
        opts["cookiesfrombrowser"] = (YTDLP_COOKIES_BROWSER,) 
        print(f"[yt-dlp] Using browser cookies from: {YTDLP_COOKIES_BROWSER}")
    return opts


def _download_audio(url: str, tmp_dir: str) -> str:
    """
    Downloads audio from a URL using yt-dlp.
    Converts to mp3 if ffmpeg is available; otherwise downloads raw m4a/webm.
    Returns the path to the downloaded file.
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
        base_opts["ffmpeg_location"] = FFMPEG_LOCATION

    if FFMPEG_LOCATION is not None or shutil.which("ffmpeg"):
        # Added /b as the ultimate fallback
        base_opts["format"] = "bestaudio/best/b" 
        base_opts["postprocessors"] = [{
            "key":             "FFmpegExtractAudio",
            "preferredcodec":  "mp3",
            "preferredquality": "64",
        }]
        print("[fetch_video] ffmpeg found — downloading as mp3")
    else:
        # Added /b as the ultimate fallback
        base_opts["format"] = "bestaudio/best/b" 
        print("[fetch_video] ffmpeg NOT found — downloading raw audio or video...")
        
    ydl_opts = _build_yt_dlp_opts(base_opts)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadError as e:
        raise RuntimeError(
            "yt-dlp failed to download YouTube audio. "
            "This often happens when the video is age-restricted or requires cookies/login. "
            "Set YTDLP_COOKIES_PATH or YTDLP_COOKIES_BROWSER in .env and retry. "
            f"Original error: {e}"
        ) from e

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
    Sends an audio file to Groq Whisper and returns segments as [{text, start, end}].
    Handles both dict and object responses defensively.
    """
    import json as _json

    with open(audio_path, "rb") as audio_file:
        response = groq_client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=audio_file,
            response_format="verbose_json",
            language="en",
        )

    if isinstance(response, str):
        response = _json.loads(response)

    if not isinstance(response, dict):
        if hasattr(response, "model_dump"):
            response = response.model_dump()
        elif hasattr(response, "dict"):
            response = response.dict()
        elif hasattr(response, "__dict__"):
            response = vars(response)
        else:
            response = {}

    raw_segments = response.get("segments") or []
    full_text    = response.get("text", "")

    segments = []

    if raw_segments:
        for seg in raw_segments:
            if isinstance(seg, dict):
                text  = seg.get("text", "").strip()
                start = round(float(seg.get("start", 0.0)), 2)
                end   = round(float(seg.get("end",   0.0)), 2)
            else:
                text  = getattr(seg, "text", "").strip()
                start = round(float(getattr(seg, "start", 0.0)), 2)
                end   = round(float(getattr(seg, "end",   0.0)), 2)

            if text:
                segments.append({"text": text, "start": start, "end": end})

        print(f"[groq] Transcribed {len(segments)} segments")

    if not segments and full_text:
        print("[groq] No segments returned, using full text as single chunk")
        segments = [{"text": full_text.strip(), "start": 0.0, "end": 0.0}]

    if not segments:
        raise ValueError("Groq returned empty transcription. Check audio file quality.")

    return segments


def _fetch_youtube(url: str, video_id: str) -> VideoData:
    """Fetches transcript and metadata for a YouTube video."""

    yt_vid_id = _extract_youtube_id(url)

    transcript_chunks  = []
    transcript_fetched = False

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(yt_vid_id)

        fetched_raw = None

        try:
            fetched_raw = transcript_list.find_manually_created_transcript(
                ["en", "en-US", "en-GB", "en-CA", "en-AU"]
            ).fetch()
        except Exception:
            pass

        if not fetched_raw:
            try:
                fetched_raw = transcript_list.find_generated_transcript(
                    ["en", "en-US"]
                ).fetch()
            except Exception:
                pass

        if not fetched_raw:
            try:
                first_transcript = next(iter(transcript_list))
                if first_transcript.language_code.startswith("en"):
                    fetched_raw = first_transcript.fetch()
                else:
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

    if not transcript_fetched:
        print(f"[fetch_video] Falling back to Groq Whisper for {yt_vid_id}...")
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                audio_path        = _download_audio(url, tmp_dir)
                transcript_chunks = _transcribe_with_groq(audio_path)
            print(f"[fetch_video] Groq Whisper transcription complete "
                  f"({len(transcript_chunks)} segments)")
        except Exception as e:
            print(f"[fetch_video] Groq Whisper also failed: {e}")
            transcript_chunks = [{"text": "", "start": 0.0, "end": 0.0}]

    transcript_text = " ".join(c["text"] for c in transcript_chunks)

    ydl_opts = {
        "quiet":         True,
        "no_warnings":   True,
        "skip_download": True,
    }
    if FFMPEG_LOCATION:
        ydl_opts["ffmpeg_location"] = FFMPEG_LOCATION

    ydl_opts = _build_yt_dlp_opts(ydl_opts)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise RuntimeError(
            "yt-dlp failed to extract YouTube metadata. "
            "This usually means the video is blocked by YouTube's bot/login checks. "
            "Set YTDLP_COOKIES_PATH or YTDLP_COOKIES_BROWSER in .env and retry. "
            f"Original error: {e}"
        ) from e

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


def _fetch_instagram(url: str, video_id: str) -> VideoData:
    """
    Fetches transcript and metadata for an Instagram Reel.
    Always uses Groq Whisper since Instagram has no caption API.
    """
    match = re.search(r"/(?:p|reel|reels|tv)/([^/?#&]+)", url)
    if not match:
        raise ValueError(f"Could not extract Instagram shortcode from: {url}")
    shortcode = match.group(1)

    print(f"[fetch_video] Fetching Instaloader metadata for {shortcode}...")
    L = instaloader.Instaloader(quiet=True)

    ig_user = os.getenv("IG_USERNAME")
    ig_pass = os.getenv("IG_PASSWORD")

    if ig_user and ig_pass:
        try:
            L.load_session_from_file(ig_user)
            print("[fetch_video] Loaded existing Instagram session from file.")
        except FileNotFoundError:
            try:
                print("[fetch_video] No session file found. Logging into Instagram...")
                L.login(ig_user, ig_pass)
                L.save_session_to_file()
                print("[fetch_video] Successfully logged in and saved session.")
            except Exception as login_err:
                print(f"[fetch_video] Login failed: {login_err}. Attempting unauthenticated...")
    else:
        print("[fetch_video] WARNING: No IG credentials found in .env. Metrics may fail.")

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
    except Exception as e:
        raise RuntimeError(f"Instaloader failed to fetch post {shortcode}: {e}")

    likes    = post.likes or 0
    comments = post.comments or 0
    views    = post.video_view_count if post.is_video and post.video_view_count else 0

    try:
        follower_count = post.owner_profile.followers or 0
    except Exception:
        follower_count = 0

    description = post.caption or ""
    title       = description[:80] if description else "Instagram Reel"
    creator     = post.owner_username or "Unknown"
    upload_date = post.date_utc.strftime("%Y-%m-%d") if post.date_utc else "unknown"

    duration = getattr(post, 'video_duration', 0)
    duration = int(duration) if duration else 0

    if not post.is_video or not post.video_url:
        raise ValueError("This Instagram post is not a video or has no video URL.")

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
        video_id          = video_id,
        platform          = "instagram",
        url               = url,
        title             = title,
        creator           = creator,
        follower_count    = follower_count,
        views             = views,
        likes             = likes,
        comments          = comments,
        hashtags          = _parse_hashtags(description),
        upload_date       = upload_date,
        duration          = duration,
        engagement_rate   = _compute_engagement(likes, comments, views),
        transcript        = transcript_text,
        transcript_chunks = transcript_chunks,
    )


def fetch_video(url: str, video_id: str) -> VideoData:
    """
    Main entry point — routes to YouTube or Instagram fetcher based on URL.
    Returns a VideoData dict with full transcript, metadata, and engagement rate.
    """
    platform = _detect_platform(url)
    print(f"[fetch_video] Detected platform: {platform} | video_id: {video_id}")

    if platform == "youtube":
        return _fetch_youtube(url, video_id)
    elif platform == "instagram":
        return _fetch_instagram(url, video_id)
    else:
        raise ValueError(f"Unsupported platform: {platform}")


def fetch_video_node(state: dict) -> dict:
    """LangGraph node wrapper. Reads url_a/url_b from state, returns video_a/video_b."""
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