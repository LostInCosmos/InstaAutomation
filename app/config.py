# Instagram Reel Automation Configuration

from pathlib import Path

# Project Paths
# Resolve to the repository root (app/ -> project root)
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
DOWNLOADS_DIR = BASE_DIR / "downloads"

# Video Settings
TARGET_WIDTH = 1080      # Instagram reel width
TARGET_HEIGHT = 1920     # Instagram reel height
VIDEO_SCALE_FACTOR = 0.7 # How much of the reel height the video should occupy (70%)
VIDEO_QUALITY = 25       # Balanced quality for 720p output

# Audio Settings  
AUDIO_BITRATE = "128k"   # Higher quality audio for 720p reels

# AI Settings
DEFAULT_AI_MODEL = "moonshotai/Kimi-K2-Instruct"
CLIP_DURATION_MIN = 40   # Minimum clip duration in seconds
CLIP_DURATION_MAX = 60   # Maximum clip duration in seconds

# Paths (absolute)
BACKGROUND_IMAGE = str(ASSETS_DIR / "background/divine_virtues.png")
OUTPUT_CLIPS_DIR = str(DOWNLOADS_DIR / "reels/")
OUTPUT_REELS_DIR = str(DOWNLOADS_DIR / "instagram_reels/")

# FFmpeg Settings
FFMPEG_PRESET = "fast"        # Balanced speed/quality for 720p output
PIXEL_FORMAT = "yuv420p"      # Pixel format for compatibility

# Performance Settings
MAX_PARALLEL_WORKERS = 4      # Maximum parallel workers for video processing
MAX_OVERLAY_WORKERS = 3       # Maximum parallel workers for overlay processing
CACHE_FILE_TIME = 0.1         # Time to simulate for cached file operations

# Logging Settings
LOG_LEVEL = "INFO"            # Logging level (DEBUG, INFO, WARNING, ERROR)
LOG_FILE = "insta_automation.log"  # Log file name

# Error Handling
MAX_RETRIES = 3               # Maximum retries for failed operations
RETRY_DELAY = 1.0             # Delay between retries in seconds
