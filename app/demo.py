#!/usr/bin/env python3
"""
Instagram Reel Automation - Demo Script

This script demonstrates how to:
1. Download a YouTube video
2. Extract meaningful clips using AI
3. Overlay the clips onto a background image to create Instagram reels

Usage:
    python demo.py [youtube_url]
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from core.get_video import download_youtube_audio, transcribe_audio_to_text, cut_video_segments, connect_highlights_to_sentences
from core.video_overlay import process_clips_with_background, verify_background_image, check_ffmpeg
from ai.generate_script import extract_reel_material_hf
import yt_dlp

def create_instagram_reels_from_youtube(youtube_url, background_image_path=None):
    """
    Complete workflow to create Instagram reels from a YouTube video.
    
    Args:
        youtube_url: URL of the YouTube video to process
        background_image_path: Path to background image (optional)
    
    Returns:
        List of created Instagram reel file paths
    """
    
    # Set default paths
    if background_image_path is None:
        background_image_path = os.path.abspath("../assets/background/instagram_reel_black.jpg")
    
    output_dir = "../downloads/reels/"
    instagram_reels_dir = "../downloads/instagram_reels/"
    
    print("🎬 Instagram Reel Creator Started!")
    print(f"📹 Processing: {youtube_url}")
    print(f"🖼️  Background: {os.path.basename(background_image_path)}")
    print("-" * 60)
    
    # Check system requirements
    if not check_ffmpeg():
        print("[!] FFmpeg is required. Please install it first.")
        return []
    
    # Verify background image
    if not verify_background_image(background_image_path):
        print(f"[!] Background image not found: {background_image_path}")
        return []
    
    print(f"[+] ✅ System ready!")
    
    try:
        # Step 1: Download audio from YouTube
        mp3_path = download_youtube_audio(youtube_url, cleanup=True)
        if not mp3_path:
            print("[!] Failed to download audio from YouTube")
            return []
        
        # Step 2: Transcribe audio to text with timestamps
        transcript, sentences = transcribe_audio_to_text(mp3_path)
        print(f"[+] Transcript: {len(transcript)} characters, {len(sentences)} segments")
        
        # Step 3: Extract meaningful highlights using AI
        highlights = extract_reel_material_hf(sentences)
        if not highlights:
            print("[!] No meaningful content extracted. Check your video content.")
            return []
        
        # Step 4: Prepare clips with timestamps
        if highlights and isinstance(highlights[0], dict) and 'start_time' in highlights[0]:
            highlights_with_times = highlights
        else:
            highlights_with_times = connect_highlights_to_sentences(sentences, highlights)
        
        # Show what we found
        print(f"\n[+] 🎯 Found {len(highlights_with_times)} potential clips:")
        valid_clips = []
        for i, h in enumerate(highlights_with_times, 1):
            if h.get("start_time") is not None and h.get("end_time") is not None:
                duration = h.get("duration", h.get("end_time", 0) - h.get("start_time", 0))
                hook = h.get("hook", "")
                print(f"   {i}. [{h['start_time']:.1f}s - {h.get('end_time', 0):.1f}s] ({duration:.1f}s)")
                print(f"      💡 {hook}")
                print(f"      📝 {h['text'][:80]}...")
                valid_clips.append(h)
        
        if not valid_clips:
            print("[!] No clips with valid timestamps found.")
            return []
        
        # Step 5: Cut video segments
        print(f"\n[+] ✂️  Cutting {len(valid_clips)} video segments...")
        cut_files = cut_video_segments(youtube_url, valid_clips, output_dir=output_dir)
        
        if not cut_files:
            print("[!] No video clips were created.")
            return []
        
        print(f"[+] Successfully created {len(cut_files)} video clips")
        
        # Step 6: Create Instagram reels with background overlay
        print(f"\n[+] 🎨 Creating Instagram reels with background overlay...")
        instagram_reels = process_clips_with_background(
            clip_files=cut_files,
            background_image_path=background_image_path,
            output_dir=instagram_reels_dir
        )
        
        if instagram_reels:
            print(f"\n🎉 SUCCESS! Created {len(instagram_reels)} Instagram reels:")
            for reel in instagram_reels:
                print(f"   📱 {os.path.basename(reel)}")
            print(f"\n📁 Find your reels in: {os.path.abspath(instagram_reels_dir)}")
        
        return instagram_reels
        
    except Exception as e:
        print(f"[!] Error in processing: {e}")
        import traceback
        traceback.print_exc()
        return []

def main():
    """Main function to run the demo."""
    
    # Default YouTube URL or get from command line
    default_url = "https://www.youtube.com/watch?v=JjvN_hYDp3g"
    
    if len(sys.argv) > 1:
        youtube_url = sys.argv[1]
    else:
        youtube_url = default_url
        print(f"Using default URL: {youtube_url}")
        print("To use your own video: python demo.py 'YOUR_YOUTUBE_URL'")
        print()
    
    # Run the complete workflow
    reels = create_instagram_reels_from_youtube(youtube_url)
    
    if reels:
        print("\n✨ Demo completed successfully!")
        print("Your Instagram reels are ready to upload! 🚀")
    else:
        print("\n❌ Demo failed. Please check the error messages above.")

if __name__ == "__main__":
    main()
