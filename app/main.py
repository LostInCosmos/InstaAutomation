from core.get_video import download_youtube_audio, transcribe_audio_to_text, cut_video_segments, connect_highlights_to_sentences
from core.video_overlay import process_clips_with_background, verify_background_image, check_ffmpeg
from ai.generate_script import extract_reel_material_hf
import config
import yt_dlp
import os

output_dir = config.OUTPUT_CLIPS_DIR
background_image_path = os.path.abspath(config.BACKGROUND_IMAGE)

# --- MAIN EXECUTION ---
print("🎬 Instagram Reel Creator")
print("=" * 50)
print("This tool will create Instagram reels from YouTube videos")
print("by extracting engaging clips and overlaying them on a background.")
print()

# Get YouTube URL from user
while True:
    url = input("🔗 Enter YouTube URL: ").strip()
    
    if not url:
        print("[!] Please enter a valid YouTube URL")
        continue
    
    # Basic URL validation
    if "youtube.com/watch" not in url and "youtu.be/" not in url:
        print("[!] Please enter a valid YouTube URL (youtube.com or youtu.be)")
        continue
    
    print(f"[+] Using URL: {url}")
    break

print()

# Check system requirements
if not check_ffmpeg():
    print("[!] FFmpeg is required for video processing. Please install it first.")
    exit(1)

# Verify background image exists
if not verify_background_image(background_image_path):
    print(f"[!] Please ensure the background image exists at: {background_image_path}")
    exit(1)

print(f"[+] ✅ System ready! Background image: {os.path.basename(background_image_path)}")

mp3_path = download_youtube_audio(url, cleanup=True)
if mp3_path:
    print("Final MP3 saved at:", mp3_path)
    transcript, sentences = transcribe_audio_to_text(mp3_path)
    print(f"[+] Transcript length: {len(transcript)} characters")
    print("[+] Transcript sample:", transcript[:300], "...")
    highlights = extract_reel_material_hf(sentences)  # Pass sentences instead of transcript
    print("[+] Extracted reel material:")
    if highlights:
        # Check if highlights already have timestamps (from AI JSON response)
        if highlights and isinstance(highlights[0], dict) and 'start_time' in highlights[0]:
            highlights_with_times = highlights
        else:
            # Fallback: connect text highlights to sentences for timestamps
            highlights_with_times = connect_highlights_to_sentences(sentences, highlights)
        for h in highlights_with_times:
            if h.get("start_time") is not None:
                duration = h.get("duration", h.get("end_time", 0) - h.get("start_time", 0))
                hook = h.get("hook", "")
                print(f"- [{h['start_time']:.1f}s - {h.get('end_time', 0):.1f}s] ({duration:.1f}s): {h['text'][:100]}...")
                if hook:
                    print(f"  💡 Hook: {hook}")
            else:
                print(f"- [timestamp not found]: {h.get('text', str(h))[:100]}...")
        video_url = url
        video_output = mp3_path.replace(".mp3", ".mp4")
        if not os.path.exists(video_output):
            print(f"[+] Downloading video: {video_url}")
            ydl_opts = {
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': video_output,
                'quiet': True,
                'merge_output_format': 'mp4'
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
        print("[+] Cutting video segments...")
        cut_files = cut_video_segments(url, highlights_with_times, output_dir=output_dir)
        print(f"[+] Created {len(cut_files)} video clips in {output_dir}")
        
        # Process clips with background overlay to create Instagram reels
        if cut_files:
            instagram_reels = process_clips_with_background(
                clip_files=cut_files,
                background_image_path=background_image_path,
                output_dir=config.OUTPUT_REELS_DIR
            )
            print(f"[+] 🎉 Final result: {len(instagram_reels)} Instagram reels ready!")
            for reel in instagram_reels:
                print(f"   📱 {os.path.basename(reel)}")
        else:
            print("[!] No video clips were created to process with background.")
    else:
        print("[!] No reel material found. Try adjusting your prompt or check the transcript.")
else:
    print("[!] Error downloading MP3.")