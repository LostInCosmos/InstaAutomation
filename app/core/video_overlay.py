import os
import subprocess
import json
import time
from PIL import Image
import shutil
import config
from concurrent.futures import ThreadPoolExecutor

def check_ffmpeg():
    """Check if FFmpeg is available in the system."""
    if not shutil.which("ffmpeg"):
        print("[!] FFmpeg not found. Please install FFmpeg:")
        print("    Ubuntu/Debian: sudo apt install ffmpeg")
        print("    MacOS: brew install ffmpeg")
        print("    Windows: Download from https://ffmpeg.org/download.html")
        return False
    return True

def overlay_video_on_background(video_path, background_image_path, output_path, 
                               target_width=None, target_height=None):
    """
    Overlay a video clip onto a background image to create Instagram reel format.
    
    Args:
        video_path: Path to the input video clip
        background_image_path: Path to the background image
        output_path: Path where the final video will be saved
        target_width: Target width for Instagram reels (uses config default if None)
        target_height: Target height for Instagram reels (uses config default if None)
    """
    if target_width is None:
        target_width = config.TARGET_WIDTH
    if target_height is None:
        target_height = config.TARGET_HEIGHT
        
    print(f"[+] Creating Instagram reel overlay for: {os.path.basename(video_path)}")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    try:
        # Get video dimensions and duration
        probe_cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams",
            video_path
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[!] Failed to probe video: {video_path}")
            return None
            
        video_info = json.loads(result.stdout)
        video_stream = None
        for stream in video_info['streams']:
            if stream['codec_type'] == 'video':
                video_stream = stream
                break
                
        if not video_stream:
            print(f"[!] No video stream found in: {video_path}")
            return None
            
        video_width = int(video_stream['width'])
        video_height = int(video_stream['height'])
        
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
        
        # FFmpeg command to overlay video on background (optimized for 720p quality)
        ffmpeg_cmd = [
            "ffmpeg", "-y",  # Overwrite output file
            
            # Input background image
            "-loop", "1", "-i", background_image_path,
            
            # Input video  
            "-i", video_path,
            
            # High quality filter complex for 720p
            "-filter_complex",
            f"[0:v]scale={target_width}:{target_height}:flags=lanczos[bg];"
            f"[1:v]scale={scaled_width}:{scaled_height}:flags=lanczos[vid];"
            f"[bg][vid]overlay={x_offset}:{y_offset}:format=yuv420[out]",
            
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
        
        print(f"[+] Running FFmpeg overlay process...")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"[+] ✅ Successfully created Instagram reel: {os.path.basename(output_path)}")
            return output_path
        else:
            print(f"[!] FFmpeg error: {result.stderr}")
            return None
            
    except Exception as e:
        print(f"[!] Error creating video overlay: {e}")
        return None

def process_clips_with_background(clip_files, background_image_path, output_dir="../downloads/instagram_reels", video_title="video"):
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
    print(f"\n[+] 🎨 Creating Instagram reels with background overlay...")
    print(f"[+] Background image: {background_image_path}")
    print(f"[+] Processing {len(clip_files)} clips in parallel...")
    
    # Check if FFmpeg is available
    if not check_ffmpeg():
        print("[!] Cannot proceed without FFmpeg")
        return []
    
    # Verify background image
    if not verify_background_image(background_image_path):
        print("[!] Cannot proceed without valid background image")
        return []
    
    os.makedirs(output_dir, exist_ok=True)
    
    def process_single_clip(clip_data):
        idx, clip_path = clip_data
        if not os.path.exists(clip_path):
            print(f"[!] Clip not found: {clip_path}")
            return None
            
        # Generate output filename with video title and reel number
        output_path = os.path.join(output_dir, f"{video_title}_reel{idx:02d}.mp4")
        
        print(f"\n[{idx}/{len(clip_files)}] Processing: {os.path.basename(clip_path)}")
        
        result_path = overlay_video_on_background(
            video_path=clip_path,
            background_image_path=background_image_path,
            output_path=output_path
        )
        
        if result_path:
            print(f"[+] Saved: {os.path.basename(result_path)}")
            return result_path
        else:
            print(f"[!] Failed to process: {os.path.basename(clip_path)}")
            return None
    
    # Process clips in parallel (limit to 3 threads to avoid overwhelming FFmpeg)
    max_workers = min(3, len(clip_files), os.cpu_count())
    print(f"[+] Using {max_workers} parallel threads for overlay processing...")
    
    overlay_start_time = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        clip_data = [(idx, clip_path) for idx, clip_path in enumerate(clip_files, 1)]
        results = list(executor.map(process_single_clip, clip_data))
        reel_files = [f for f in results if f is not None]
    
    overlay_time = time.time() - overlay_start_time
    print(f"\n✨ Successfully created {len(reel_files)} Instagram reels!")
    print(f"📁 Output directory: {output_dir}")
    print(f"⏱️  Overlay processing completed in: {overlay_time:.1f}s")
    
    return reel_files

def verify_background_image(background_path):
    """
    Verify that the background image exists and is valid.
    """
    if not os.path.exists(background_path):
        print(f"[!] Background image not found: {background_path}")
        return False
        
    try:
        with Image.open(background_path) as img:
            print(f"[+] Background image loaded: {img.size[0]}x{img.size[1]}")
            return True
    except Exception as e:
        print(f"[!] Invalid background image: {e}")
        return False
