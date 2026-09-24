import os
import subprocess
import json
import tempfile
import time
import logging
from PIL import Image
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
import config
from concurrent.futures import ThreadPoolExecutor
from core.subtitles import load_cues, write_ass

# Configure logging
logger = logging.getLogger(__name__)

def check_ffmpeg() -> bool:
    """Check if FFmpeg is available in the system."""
    if not shutil.which("ffmpeg"):
        logger.error("FFmpeg not found in system PATH")
        print("[!] FFmpeg not found. Please install FFmpeg:")
        print("    Ubuntu/Debian: sudo apt install ffmpeg")
        print("    MacOS: brew install ffmpeg")
        print("    Windows: Download from https://ffmpeg.org/download.html")
        return False
    logger.info("FFmpeg is available")
    return True

def _escape_ffmpeg_path(path: str) -> str:
    """Escape a path for safe use as a single-quoted ffmpeg filtergraph option
    value (e.g. subtitles=filename='...'). Backslash and colon are escaped
    for the filtergraph mini-language. A literal single quote can't be
    escaped *inside* a quoted string at all in ffmpeg's parser - so it's
    handled the same way POSIX shells do: close the quote, insert a
    backslash-escaped quote, then reopen the quote (['it's] -> 'it'\''s').
    A prior version used "\\'" here, which just truncates the string at the
    quote instead of escaping it - broke every clip for any video title
    containing an apostrophe (confirmed in production: "Neuroscientist's
    Guide..." caused 'Error initializing filters' for all 36 clips)."""
    escaped = str(path).replace('\\', '\\\\').replace(':', '\\:')
    return escaped.replace("'", "'\\''")


def overlay_video_on_background(video_path: str, background_image_path: str, output_path: str,
                               target_width: Optional[int] = None, target_height: Optional[int] = None,
                               cues_path: Optional[str] = None) -> Optional[str]:
    """
    Overlay a video clip onto a background image to create Instagram reel format.

    Args:
        video_path: Path to the input video clip
        background_image_path: Path to the background image
        output_path: Path where the final video will be saved
        target_width: Target width for Instagram reels (uses config default if None)
        target_height: Target height for Instagram reels (uses config default if None)
        cues_path: Optional path to a JSON cues file (from core.subtitles.save_cues)
            to render as burned-in subtitles

    Returns:
        Path to the created video file if successful, None otherwise
    """
    if target_width is None:
        target_width = config.TARGET_WIDTH
    if target_height is None:
        target_height = config.TARGET_HEIGHT
        
    logger.info(f"Creating Instagram reel overlay for: {Path(video_path).name}")
    print(f"[+] Creating Instagram reel overlay for: {Path(video_path).name}")
    
    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    temp_ass_path = None
    try:
        # Get video dimensions and duration
        probe_cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams",
            video_path
        ]
        
        logger.debug(f"Probing video: {video_path}")
        result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        video_info = json.loads(result.stdout)
        
        video_stream = None
        for stream in video_info['streams']:
            if stream['codec_type'] == 'video':
                video_stream = stream
                break
                
        if not video_stream:
            logger.error(f"No video stream found in: {video_path}")
            print(f"[!] No video stream found in: {video_path}")
            return None
            
        video_width = int(video_stream['width'])
        video_height = int(video_stream['height'])
        logger.info(f"Video dimensions: {video_width}x{video_height}")
        
        # Calculate video scaling to fit nicely in the reel format
        # We want to scale the video to take up about 70% of the reel height
        max_video_height = int(target_height * config.VIDEO_SCALE_FACTOR)
        max_video_width = int(target_width * 0.9)
        
        # Calculate scale factor maintaining aspect ratio
        scale_factor = min(max_video_width / video_width, max_video_height / video_height)
        
        scaled_width = int(video_width * scale_factor)
        scaled_height = int(video_height * scale_factor)
        
        # Calculate position to center the video
        x_offset = (target_width - scaled_width) // 2
        y_offset = (target_height - scaled_height) // 2
        
        print(f"[+] Video dimensions: {video_width}x{video_height}")
        print(f"[+] Scaled dimensions: {scaled_width}x{scaled_height}")
        print(f"[+] Position: ({x_offset}, {y_offset})")

        filter_complex = (
            f"[0:v]scale={target_width}:{target_height}:flags=lanczos[bg];"
            f"[1:v]scale={scaled_width}:{scaled_height}:flags=lanczos[vid];"
        )

        if cues_path and Path(cues_path).exists():
            cues = load_cues(cues_path)
            if cues:
                # Burn subtitles into the background space just below the
                # video, not overlapping it. White text with a black outline
                # for legibility against whatever the background art looks
                # like. Position/size are only known now that y_offset and
                # scaled_height are computed, so the ASS file (which is what
                # libass actually honors reliably - see core.subtitles) is
                # written here, at render time, not at cut time.
                space_below_video = target_height - (y_offset + scaled_height)
                margin_v = max(60, int(space_below_video * 0.4))
                # Use a neutral system temp path, NOT one derived from
                # output_path - that lives in a folder named after the video
                # title, which can contain characters (apostrophes, colons)
                # that are awkward-to-impossible to escape correctly inside
                # an ffmpeg filtergraph's quoted option value. Simplest fix:
                # never put untrusted/arbitrary text in that path at all.
                ass_fd, temp_ass_path = tempfile.mkstemp(suffix='.ass')
                os.close(ass_fd)
                write_ass(
                    cues, temp_ass_path,
                    play_width=target_width, play_height=target_height,
                    font_size=config.SUBTITLE_FONT_SIZE, margin_v=margin_v,
                )

        if temp_ass_path:
            escaped_ass = _escape_ffmpeg_path(temp_ass_path)
            filter_complex += (
                f"[bg][vid]overlay={x_offset}:{y_offset}:format=yuv420[composited];"
                f"[composited]subtitles=filename='{escaped_ass}'[out]"
            )
        else:
            filter_complex += f"[bg][vid]overlay={x_offset}:{y_offset}:format=yuv420[out]"

        # FFmpeg command to overlay video on background (optimized for 720p quality)
        ffmpeg_cmd = [
            "ffmpeg", "-y",  # Overwrite output file

            # Input background image
            "-loop", "1", "-i", background_image_path,

            # Input video
            "-i", video_path,

            # High quality filter complex for 720p
            "-filter_complex", filter_complex,

            # Map the overlayed video and audio from original video
            "-map", "[out]",
            "-map", "1:a?",  # Map audio if present (? makes it optional)
            
            # Video encoding settings (optimized for 720p quality)
            "-c:v", "libx264",
            "-preset", config.FFMPEG_PRESET,  # Use fast preset for balance
            "-crf", str(config.VIDEO_QUALITY),  # Better CRF for 720p
            "-pix_fmt", config.PIXEL_FORMAT,
            
            # Audio encoding settings (higher quality)
            "-c:a", "aac",
            "-b:a", config.AUDIO_BITRATE,  # Higher bitrate for quality
            
            # Performance optimizations
            "-threads", "0",  # Use all available CPU threads
            "-shortest",  # Set output duration to match input video
            
            # Output file
            output_path
        ]
        
        logger.info("Running FFmpeg overlay process...")
        print(f"[+] Running FFmpeg overlay process...")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Successfully created Instagram reel: {Path(output_path).name}")
            print(f"[+] ✅ Successfully created Instagram reel: {Path(output_path).name}")
            return output_path
        else:
            logger.error(f"FFmpeg error: {result.stderr}")
            print(f"[!] FFmpeg error: {result.stderr}")
            return None
            
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg probe failed: {e}")
        print(f"[!] Failed to probe video: {e}")
        return None
    except Exception as e:
        logger.error(f"Error creating video overlay: {e}")
        print(f"[!] Error creating video overlay: {e}")
        return None
    finally:
        if temp_ass_path and Path(temp_ass_path).exists():
            try:
                Path(temp_ass_path).unlink()
            except OSError as e:
                logger.warning(f"Could not delete temp subtitle file {temp_ass_path}: {e}")

def process_clips_with_background(clip_files: List[str], background_image_path: str, 
                                 output_dir: Optional[str] = None, 
                                 video_title: str = "video") -> List[str]:
    """
    Process multiple video clips by overlaying them onto a background image using parallel processing.
    
    Args:
        clip_files: List of paths to video clip files
        background_image_path: Path to the background image
        output_dir: Directory to save the Instagram reel videos
        video_title: Title for naming the output files
    
    Returns:
        List of paths to the created Instagram reel videos
    """
    logger.info(f"Creating Instagram reels with background overlay for {len(clip_files)} clips")
    print(f"\n[+] 🎨 Creating Instagram reels with background overlay...")
    print(f"[+] Background image: {background_image_path}")
    print(f"[+] Processing {len(clip_files)} clips in parallel...")
    
    # Check if FFmpeg is available
    if not check_ffmpeg():
        logger.error("Cannot proceed without FFmpeg")
        print("[!] Cannot proceed without FFmpeg")
        return []
    
    # Verify background image
    if not verify_background_image(background_image_path):
        logger.error("Cannot proceed without valid background image")
        print("[!] Cannot proceed without valid background image")
        return []
    
    if output_dir is None:
        output_dir = config.OUTPUT_REELS_DIR
    # Each video gets its own folder: <output_dir>/<video_title>/reel01.mp4, reel02.mp4, ...
    video_dir = Path(output_dir) / video_title
    video_dir.mkdir(parents=True, exist_ok=True)

    # Clear any reels from a previous run of this video first, so re-processing
    # (e.g. after a prompt/config change) never leaves stale clips mixed in with
    # the new ones - the folder should always reflect only the latest run.
    for old_file in video_dir.glob("*.mp4"):
        try:
            old_file.unlink()
        except OSError as e:
            logger.warning(f"Could not remove stale reel {old_file}: {e}")

    def process_single_clip(clip_data: Tuple[int, str]) -> Optional[str]:
        """Process a single clip with improved error handling."""
        idx, clip_path = clip_data
        clip_file = Path(clip_path)

        if not clip_file.exists():
            logger.error(f"Clip not found: {clip_path}")
            print(f"[!] Clip not found: {clip_path}")
            return None

        output_path = video_dir / f"reel{idx:02d}.mp4"
        
        logger.info(f"Processing clip {idx}/{len(clip_files)}: {clip_file.name}")
        print(f"\n[{idx}/{len(clip_files)}] Processing: {clip_file.name}")
        
        cues_path = clip_file.with_suffix('.cues.json')

        result_path = overlay_video_on_background(
            video_path=str(clip_path),
            background_image_path=background_image_path,
            output_path=str(output_path),
            cues_path=str(cues_path) if cues_path.exists() else None,
        )
        
        if result_path:
            logger.info(f"Successfully processed clip {idx}: {Path(result_path).name}")
            print(f"[+] Saved: {Path(result_path).name}")
            return result_path
        else:
            logger.error(f"Failed to process clip {idx}: {clip_file.name}")
            print(f"[!] Failed to process: {clip_file.name}")
            return None
    
    # Process clips in parallel (limit to configured threads to avoid overwhelming FFmpeg)
    max_workers = min(config.MAX_OVERLAY_WORKERS, len(clip_files), os.cpu_count() or 1)
    logger.info(f"Using {max_workers} parallel threads for overlay processing")
    print(f"[+] Using {max_workers} parallel threads for overlay processing...")
    
    overlay_start_time = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        clip_data = [(idx, clip_path) for idx, clip_path in enumerate(clip_files, 1)]
        results = list(executor.map(process_single_clip, clip_data))
        reel_files = [f for f in results if f is not None]
    
    overlay_time = time.time() - overlay_start_time
    logger.info(f"Successfully created {len(reel_files)} Instagram reels in {overlay_time:.1f}s")
    print(f"\n✨ Successfully created {len(reel_files)} Instagram reels!")
    print(f"📁 Output directory: {video_dir}")
    print(f"⏱️  Overlay processing completed in: {overlay_time:.1f}s")
    
    return reel_files

def verify_background_image(background_path: str) -> bool:
    """
    Verify that the background image exists and is valid.
    
    Args:
        background_path: Path to the background image file
        
    Returns:
        True if the image is valid, False otherwise
    """
    bg_file = Path(background_path)
    
    if not bg_file.exists():
        logger.error(f"Background image not found: {background_path}")
        print(f"[!] Background image not found: {background_path}")
        return False
        
    try:
        with Image.open(background_path) as img:
            logger.info(f"Background image loaded: {img.size[0]}x{img.size[1]}")
            print(f"[+] Background image loaded: {img.size[0]}x{img.size[1]}")
            return True
    except Exception as e:
        logger.error(f"Invalid background image: {e}")
        print(f"[!] Invalid background image: {e}")
        return False
