# Instagram Reel Automation Configuration

# Video Settings
TARGET_WIDTH = 1080      # Instagram reel width
TARGET_HEIGHT = 1920     # Instagram reel height
VIDEO_SCALE_FACTOR = 0.7 # How much of the reel height the video should occupy (70%)
VIDEO_QUALITY = 22       # FFmpeg CRF value (lower = better quality, larger file)

# Audio Settings  
AUDIO_BITRATE = "128k"   # Audio bitrate for output videos

# AI Settings
DEFAULT_AI_MODEL = "moonshotai/Kimi-K2-Instruct"
CLIP_DURATION_MIN = 40   # Minimum clip duration in seconds
CLIP_DURATION_MAX = 60   # Maximum clip duration in seconds

# Paths
BACKGROUND_IMAGE = "../assets/background/divine_virtues.png"
OUTPUT_CLIPS_DIR = "../downloads/reels/"
OUTPUT_REELS_DIR = "../downloads/instagram_reels/"

# FFmpeg Settings
FFMPEG_PRESET = "fast"   # FFmpeg encoding preset (ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow)
PIXEL_FORMAT = "yuv420p" # Pixel format for compatibility
