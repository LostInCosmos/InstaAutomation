# Instagram Reel Automation Configuration

from pathlib import Path
from dotenv import load_dotenv
import os

# Load environment variables from .env file
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

# Project Paths
# Resolve to the repository root (app/ -> project root)
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
DOWNLOADS_DIR = BASE_DIR / "downloads"

# Video Settings
TARGET_WIDTH = 1080      # Instagram reel width
TARGET_HEIGHT = 1920     # Instagram reel height (1080x1920 = 9:16)
VIDEO_SCALE_FACTOR = 0.7 # How much of the reel height the video should occupy (70%)
VIDEO_QUALITY = 25       # libx264 CRF - lower is higher quality

# Audio Settings
AUDIO_BITRATE = "128k"

# AI Settings (Groq)
DEFAULT_AI_MODEL = "openai/gpt-oss-120b"   # Clip-selection LLM
GROQ_WHISPER_MODEL = "whisper-large-v3"    # Transcription model
CLIP_DURATION_MIN = 30   # Minimum clip duration in seconds
CLIP_DURATION_TARGET_MAX = 40  # Ideal/target max - the LLM should aim for this...
CLIP_DURATION_MAX = 90         # ...but may run up to this long if it needs the extra
                                # time to reach a real, complete ending instead of
                                # cutting off mid-thought
CLIP_BUFFER_SECONDS = 3.0  # Pad each clip's start/end by up to this much so the cut
                            # doesn't clip off the first syllable of the hook line -
                            # bounded by the neighboring sentence's own boundary, so
                            # it never eats into the previous/next sentence's speech
CLIP_BUFFER_SAFETY_MARGIN = 0.5  # Extra pullback when the gap to the neighboring
                                  # sentence is tight, so the buffer stops just
                                  # BEFORE that sentence's boundary rather than
                                  # landing on/in it (Whisper's timestamps aren't
                                  # frame-perfect, so landing exactly on the
                                  # boundary can still catch its first syllable)
AI_TEMPERATURE = 0.3             # Lower temperature for consistent extraction (not creative writing)
AI_MAX_COMPLETION_TOKENS = 4096  # gpt-oss-120b's hidden reasoning tokens share this budget with
                                  # the actual JSON answer - too low and reasoning alone can
                                  # exhaust it, producing an empty/invalid completion

# Chunking for long videos/podcasts. Two independent Groq limits force this:
#  - Whisper (free tier): 25MB max per transcription request (~20 min of 192kbps mp3)
#  - gpt-oss-120b (free tier): 8,000 tokens/min, so a full-length transcript can't be
#    sent in one clip-selection call either.
# Audio is cut into overlapping windows up front; each window is transcribed, then
# sent to the LLM for clip selection. The overlap ensures a clip that straddles a
# window boundary still gets fully captured by at least one window.
CHUNK_DURATION_SECONDS = 900     # ~15 min per audio/transcript chunk
CHUNK_OVERLAP_SECONDS = 120      # 2 min overlap shared between adjacent chunks
AI_CHUNK_DELAY_SECONDS = 60      # Pause between LLM calls to stay under Groq's 8K TPM cap

# Paths (absolute)
BACKGROUND_IMAGE = str(ASSETS_DIR / "background/divine_virtues.png")
OUTPUT_CLIPS_DIR = str(DOWNLOADS_DIR / "reels/")
OUTPUT_REELS_DIR = str(DOWNLOADS_DIR / "instagram_reels/")

# FFmpeg Settings
FFMPEG_PRESET = "fast"        # Balanced speed/quality
PIXEL_FORMAT = "yuv420p"      # Pixel format for compatibility

# Performance Settings
MAX_PARALLEL_WORKERS = 4      # Maximum parallel workers for video clip cutting
MAX_OVERLAY_WORKERS = 3       # Maximum parallel workers for background-overlay processing

# Logging Settings
LOG_LEVEL = "INFO"                  # Logging level (DEBUG, INFO, WARNING, ERROR)
LOG_FILE = "insta_automation.log"   # Log file name (written under BASE_DIR)

# Error Handling
MAX_RETRIES = 3               # Maximum retries for failed operations
RETRY_DELAY = 1.0             # Delay between retries in seconds
