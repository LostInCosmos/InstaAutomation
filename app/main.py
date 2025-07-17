from core.get_video import download_youtube_audio, transcribe_audio_to_text, cut_video_segments, connect_highlights_to_sentences
from ai.generate_script import extract_reel_material_hf
import yt_dlp
import os

output_dir = "../downloads/reels/"

# --- MAIN EXECUTION ---
url = "https://www.youtube.com/watch?v=2-inNDXoeVE"
mp3_path = download_youtube_audio(url, cleanup=True)
if mp3_path:
    print("Final MP3 saved at:", mp3_path)
    transcript, sentences = transcribe_audio_to_text(mp3_path)
    print(f"[+] Transcript length: {len(transcript)} characters")
    print("[+] Transcript sample:", transcript[:300], "...")
    highlights = extract_reel_material_hf(transcript)
    print("[+] Extracted reel material:")
    if highlights:
        highlights_with_times = connect_highlights_to_sentences(sentences, highlights)
        for h in highlights_with_times:
            if h["start"] is not None:
                print(f"- [{h['start']:.1f}s - {h['end']:.1f}s]: {h['text']}")
            else:
                print(f"- [timestamp not found]: {h['text']}")
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
        cut_files = cut_video_segments(video_output, highlights_with_times, output_dir=output_dir)
        print(f"[+] Created {len(cut_files)} video clips in {output_dir}")
    else:
        print("[!] No reel material found. Try adjusting your prompt or check the transcript.")
else:
    print("[!] Error downloading MP3.")