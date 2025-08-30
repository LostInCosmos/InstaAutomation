from core.get_video import download_youtube_audio, transcribe_audio_to_text, cut_video_segments, connect_highlights_to_sentences, check_existing_transcript
from core.video_overlay import process_clips_with_background, verify_background_image, check_ffmpeg
from ai.generate_script import extract_reel_material_hf
import config
import yt_dlp
import os
import time

output_dir = config.OUTPUT_CLIPS_DIR
background_image_path = os.path.abspath(config.BACKGROUND_IMAGE)

# Start timing
start_time = time.time()

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

# Check if transcript already exists to skip download
transcript_path, sentences_path, video_title = check_existing_transcript(url)

if transcript_path and sentences_path and video_title:
    # Load existing transcript files
    print(f"[+] Loading cached transcript and sentences...")
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read()
    with open(sentences_path, "r", encoding="utf-8") as f:
        import json
        sentences = json.load(f)
    
    # Timing checkpoint 1 (no download needed)
    download_time = 0.1  # Minimal time for file loading
    transcription_time = 0.1  # Minimal time for loading
    print(f"⏱️  Using cached files - no download/transcription needed: {download_time + transcription_time:.1f}s")
    
else:
    # Need to download and transcribe
    mp3_path, video_title = download_youtube_audio(url, cleanup=True)
    if not mp3_path or not video_title:
        print("[!] Error downloading MP3.")
        total_time = time.time() - start_time
        minutes = int(total_time // 60) 
        seconds = int(total_time % 60)
        print(f"⏱️  Total processing time: {minutes}m {seconds}s")
        exit(1)
    
    print("Final MP3 saved at:", mp3_path)
    
    # Timing checkpoint 1
    download_time = time.time() - start_time
    print(f"⏱️  Download completed in: {download_time:.1f}s")
    
    transcript, sentences = transcribe_audio_to_text(mp3_path)
    
    # Delete audio file after transcript is created (use transcript as cache)
    try:
        os.remove(mp3_path)
        print(f"[+] Cleaned up audio file: {os.path.basename(mp3_path)}")
    except Exception as e:
        print(f"[!] Could not delete audio file: {e}")
    
    # Timing checkpoint 2
    transcription_time = time.time() - start_time - download_time
    print(f"⏱️  Transcription completed in: {transcription_time:.1f}s")

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
    
    print("[+] Cutting video segments...")
    cut_files = cut_video_segments(url, highlights_with_times, output_dir=output_dir)
    print(f"[+] Created {len(cut_files)} video clips in {output_dir}")
    
    # Timing checkpoint 3
    cutting_time = time.time() - start_time
    print(f"⏱️  Video cutting completed in: {cutting_time:.1f}s total")
    
    # Process clips with background overlay to create Instagram reels
    if cut_files:
        instagram_reels = process_clips_with_background(
            clip_files=cut_files,
            background_image_path=background_image_path,
            output_dir=config.OUTPUT_REELS_DIR,
            video_title=video_title
        )
        
        # Delete clip files after reels are created (save only final reels)
        print("[+] Cleaning up clip files...")
        for clip_file in cut_files:
            try:
                os.remove(clip_file)
                print(f"[+] Deleted clip: {os.path.basename(clip_file)}")
            except Exception as e:
                print(f"[!] Could not delete clip {os.path.basename(clip_file)}: {e}")
        
        print(f"[+] 🎉 Final result: {len(instagram_reels)} Instagram reels ready!")
        for reel in instagram_reels:
            print(f"   📱 {os.path.basename(reel)}")
        
        # Calculate and display total processing time
        total_time = time.time() - start_time
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        
        print(f"\n🎯 PROCESSING COMPLETE!")
        print("=" * 50)
        print(f"⏱️  Total processing time: {minutes}m {seconds}s ({total_time:.1f}s)")
        print(f"📊 Performance:")
        print(f"   • Download: {download_time:.1f}s")
        print(f"   • Transcription: {transcription_time:.1f}s") 
        print(f"   • Video processing: {cutting_time - transcription_time - download_time:.1f}s")
        print(f"   • Reel creation: {total_time - cutting_time:.1f}s")
        print(f"🎬 Final output: {len(instagram_reels)} high-quality Instagram reels!")
    else:
        print("[!] No video clips were created to process with background.")
else:
    print("[!] No reel material found. Try adjusting your prompt or check the transcript.")