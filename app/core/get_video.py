from __future__ import unicode_literals
import os
import yt_dlp
import whisper

def download_youtube_audio(video_url, output_dir="../downloads/", cleanup=False):
    os.makedirs(output_dir, exist_ok=True)
    # Get video title without downloading using yt_dlp
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = info['title']
    except Exception as e:
        print(f"[!] Failed to fetch video info: {e}")
        return None

    mp3_file = os.path.join(output_dir, f"{title}.mp3")
    if os.path.exists(mp3_file):
        print(f"[+] MP3 already exists, reusing: {mp3_file}")
        return mp3_file

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            print(f"[+] Downloaded and converted to mp3: {mp3_file}")
            return mp3_file
    except Exception as e:
        print(f"[!] Failed to download audio: {e}")
        print("[!] Try upgrading yt-dlp: pip install -U yt-dlp")
        return None

def transcribe_audio_to_text(audio_path):
    base, _ = os.path.splitext(audio_path)
    transcript_path = base + ".txt"
    if os.path.exists(transcript_path):
        print(f"[+] Transcript already exists, reusing: {transcript_path}")
        with open(transcript_path, "r", encoding="utf-8") as f:
            return f.read()
    model = whisper.load_model("base")
    print(f"[+] Transcribing audio: {audio_path}")
    result = model.transcribe(audio_path)
    transcript = result['text']
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript)
    print(f"[+] Transcript saved at: {transcript_path}")
    return transcript

def transcribe_audio_to_segments(audio_path):
    """
    Transcribe audio and return a list of segments with text and timestamps.
    Each segment: {'start': float, 'end': float, 'text': str}
    """
    base, _ = os.path.splitext(audio_path)
    segments_path = base + "_segments.json"
    if os.path.exists(segments_path):
        print(f"[+] Segments already exist, reusing: {segments_path}")
        import json
        with open(segments_path, "r", encoding="utf-8") as f:
            return json.load(f)
    model = whisper.load_model("base")
    print(f"[+] Transcribing audio to segments: {audio_path}")
    result = model.transcribe(audio_path, word_timestamps=False)
    segments = [
        {"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
        for seg in result["segments"]
    ]
    import json
    with open(segments_path, "w", encoding="utf-8") as f:
        json.dump(segments, f)
    return segments

def extract_meaningful_parts(transcript):
    import re
    keywords = [
        "joke", "funny", "quote", "laugh", "moment", "lesson", "story", "advice", "wisdom", "important", "key", "tip"
    ]
    # Split transcript into sentences using regex for better accuracy
    sentences = re.split(r'(?<=[.!?])\s+', transcript)
    highlights = [
        s.strip() for s in sentences
        if any(k in s.lower() for k in keywords)
    ]
    return highlights

def extract_reel_material(transcript):
    """
    Use OpenAI GPT to extract the most interesting, deep, or impactful moments from the transcript.
    Returns a list of 'reel material' sentences or paragraphs.
    If OpenAI quota is exceeded, fallback to keyword-based extraction.
    """
    try:
        import openai
        openai.api_key = os.getenv("OPENAI_API_KEY")  # Set your API key in env variable

        # Split transcript into smaller chunks if it's too long for the model
        max_chunk_size = 3500  # chars, safe for gpt-3.5-turbo context
        chunks = [transcript[i:i+max_chunk_size] for i in range(0, len(transcript), max_chunk_size)]
        all_highlights = []

        for idx, chunk in enumerate(chunks):
            prompt = (
                "Extract all interesting, deep, emotional, or impactful quotes or moments from the following transcript chunk. "
                "Return each as a separate bullet point. Only include content suitable for social media reels.\n\n"
                f"Transcript chunk {idx+1}:\n{chunk}\n\nReel Material:"
            )
            client = openai.OpenAI(api_key=openai.api_key)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.7,
            )
            content = response.choices[0].message.content
            highlights = [line.lstrip('-• ').strip() for line in content.split('\n') if line.strip()]
            all_highlights.extend(highlights)

        # Remove duplicates and empty lines
        unique_highlights = []
        seen = set()
        for h in all_highlights:
            if h and h not in seen:
                unique_highlights.append(h)
                seen.add(h)
        return unique_highlights

    except Exception as e:
        print(f"[!] OpenAI API error: {e}")
        print("[!] Falling back to keyword-based extraction.")
        return extract_meaningful_parts(transcript)

# Utility function to estimate tokens for a given text
def estimate_token_count(text):
    """
    Roughly estimates the number of tokens for a given text.
    For English, 1 token ≈ 4 characters or ≈ 0.75 words.
    """
    num_words = len(text.split())
    estimated_tokens = int(num_words / 0.75)
    print(f"[i] Estimated tokens for transcript: {estimated_tokens} (for {num_words} words)")
    return estimated_tokens

def find_timestamps_for_highlights(segments, highlights):
    """
    For each highlight, find the segment with the highest text overlap.
    Returns a list of dicts: {'text': highlight, 'start': float, 'end': float}
    """
    from difflib import SequenceMatcher
    results = []
    for highlight in highlights:
        best_ratio = 0
        best_seg = None
        for seg in segments:
            ratio = SequenceMatcher(None, highlight.lower(), seg["text"].lower()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_seg = seg
        if best_seg and best_ratio > 0.4:  # threshold to avoid false matches
            results.append({
                "text": highlight,
                "start": max(0, best_seg["start"] - 1),
                "end": best_seg["end"] + 1
            })
        else:
            results.append({
                "text": highlight,
                "start": None,
                "end": None
            })
    return results

# Use direct link
url = "https://www.youtube.com/watch?v=dlKkFQQg9_Q"
mp3_path = download_youtube_audio(url, cleanup=True)
if mp3_path:
    print("Final MP3 saved at:", mp3_path)
    transcript = transcribe_audio_to_text(mp3_path)
    print(f"[+] Transcript length: {len(transcript)} characters")
    print("[+] Transcript sample:", transcript[:300], "...")
    estimate_token_count(transcript)
    highlights = extract_reel_material(transcript)
    print("[+] Extracted reel material:")
    if highlights:
        segments = transcribe_audio_to_segments(mp3_path)
        highlights_with_times = find_timestamps_for_highlights(segments, highlights)
        for h in highlights_with_times:
            if h["start"] is not None:
                print(f"- [{h['start']:.1f}s - {h['end']:.1f}s]: {h['text']}")
            else:
                print(f"- [timestamp not found]: {h['text']}")
    else:
        print("[!] No reel material found. Try adjusting your prompt or check the transcript.")
else:
    print("[!] Download failed.")
