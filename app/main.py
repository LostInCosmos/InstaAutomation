"""CLI entry point for the Instagram Reel Creator."""
import logging
import os
import config
from core.video_overlay import verify_background_image, check_ffmpeg
from core.pipeline import process_video

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    filename=str(config.BASE_DIR / config.LOG_FILE),
    filemode='a',
    encoding='utf-8',
)

URL_PATTERNS = ('youtube.com/watch', 'youtu.be/')


def get_youtube_url() -> str:
    """Prompt for and validate a YouTube URL."""
    while True:
        url = input("🔗 Enter YouTube URL: ").strip()

        if not url:
            print("[!] Please enter a valid YouTube URL")
            continue
        if not any(pattern in url for pattern in URL_PATTERNS):
            print("[!] Please enter a valid YouTube URL (youtube.com or youtu.be)")
            continue

        print(f"[+] Using URL: {url}")
        return url


def check_system_requirements() -> bool:
    """Verify FFmpeg and the background image are available before doing any work."""
    if not check_ffmpeg():
        print("[!] FFmpeg is required for video processing. Please install it first.")
        return False

    background_path = os.path.abspath(config.BACKGROUND_IMAGE)
    if not verify_background_image(background_path):
        print(f"[!] Please ensure the background image exists at: {background_path}")
        return False

    print(f"[+] ✅ System ready! Background image: {os.path.basename(background_path)}")
    return True


def main() -> None:
    print("🎬 Instagram Reel Creator")
    print("=" * 50)
    print("This tool will create Instagram reels from YouTube videos")
    print("by extracting engaging clips and overlaying them on a background.\n")

    url = get_youtube_url()
    print()

    if not check_system_requirements():
        exit(1)

    result = process_video(url)
    reels = result.get('reels', [])

    if not reels:
        return

    print(f"\n[+] 🎉 Final result: {len(reels)} Instagram reels ready!")
    for reel in reels:
        print(f"   📱 {os.path.basename(reel)}")

    total_time = result.get('total_time', 0)
    minutes, seconds = int(total_time // 60), int(total_time % 60)
    print(f"\n🎯 PROCESSING COMPLETE!")
    print("=" * 50)
    print(f"⏱️  Total processing time: {minutes}m {seconds}s ({total_time:.1f}s)")


if __name__ == "__main__":
    main()
