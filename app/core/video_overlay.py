import os
import subprocess
import json
from PIL import Image
import shutil
import config

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
        
        # FFmpeg command to overlay video on background
        ffmpeg_cmd = [
            "ffmpeg", "-y",  # Overwrite output file
            
            # Input background image
            "-loop", "1", "-i", background_image_path,
            
            # Input video
            "-i", video_path,
            
            # Filter complex to overlay video on background
            "-filter_complex",
            f"[0:v]scale={target_width}:{target_height}[bg];"
            f"[1:v]scale={scaled_width}:{scaled_height}[vid];"
            f"[bg][vid]overlay={x_offset}:{y_offset}[out]",
            
            # Map the overlayed video and audio from original video
            "-map", "[out]",
            "-map", "1:a?",  # Map audio if present (? makes it optional)
            
            # Video encoding settings
            "-c:v", "libx264",
            "-preset", config.FFMPEG_PRESET,
            "-crf", str(config.VIDEO_QUALITY),
            "-pix_fmt", config.PIXEL_FORMAT,
            
            # Audio encoding settings
            "-c:a", "aac",
            "-b:a", config.AUDIO_BITRATE,
            
            # Set output duration to match input video
            "-shortest",
            
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
    Process multiple video clips by overlaying them onto a background image.
    
    Args:
        clip_files: List of paths to video clip files
        background_image_path: Path to the background image
        output_dir: Directory to save the Instagram reel videos
    
    Returns:
        List of paths to the created Instagram reel videos
    """
    print(f"\n[+] 🎨 Creating Instagram reels with background overlay...")
    print(f"[+] Background image: {background_image_path}")
    print(f"[+] Processing {len(clip_files)} clips...")
    
    # Check if FFmpeg is available
    if not check_ffmpeg():
        print("[!] Cannot proceed without FFmpeg")
        return []
    
    # Verify background image
    if not verify_background_image(background_image_path):
        print("[!] Cannot proceed without valid background image")
        return []
    
    os.makedirs(output_dir, exist_ok=True)
    reel_files = []
    
    for idx, clip_path in enumerate(clip_files, 1):
        if not os.path.exists(clip_path):
            print(f"[!] Clip not found: {clip_path}")
            continue
            
        # Generate output filename with video title and reel number
        output_path = os.path.join(output_dir, f"{video_title}_reel{idx:02d}.mp4")
        
        print(f"\n[{idx}/{len(clip_files)}] Processing: {os.path.basename(clip_path)}")
        
        result_path = overlay_video_on_background(
            video_path=clip_path,
            background_image_path=background_image_path,
            output_path=output_path
        )
        
        if result_path:
            reel_files.append(result_path)
            print(f"[+] Saved: {os.path.basename(result_path)}")
        else:
            print(f"[!] Failed to process: {os.path.basename(clip_path)}")
    
    print(f"\n✨ Successfully created {len(reel_files)} Instagram reels!")
    print(f"📁 Output directory: {output_dir}")
    
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
