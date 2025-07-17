from __future__ import unicode_literals
import os
import yt_dlp
import whisper
import re
import json

output_dir = "../downloads/reels/"

def sanitize_filename(filename):
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    return sanitized.replace('\n', '').replace('\r', '').strip()

def download_youtube_audio(video_url, output_dir="../downloads/", cleanup=False):
    os.makedirs(output_dir, exist_ok=True)
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = sanitize_filename(info['title'])
    except Exception as e:
        print(f"[!] Failed to fetch video info: {e}")
        return None
    mp3_file = os.path.join(output_dir, f"{title}.mp3")
    if os.path.exists(mp3_file):
        print(f"[+] MP3 already exists, reusing: {mp3_file}")
        return mp3_file
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, f'{title}.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(video_url, download=True)
            print(f"[+] Downloaded and converted to mp3: {mp3_file}")
            return mp3_file
    except Exception as e:
        print(f"[!] Failed to download audio: {e}")
        print("[!] Try upgrading yt-dlp: pip install -U yt-dlp")
        return None

def transcribe_audio_to_text(audio_path):
    base, _ = os.path.splitext(audio_path)
    transcript_path = base + ".txt"
    sentences_json_path = base + "_sentences.json"
    if os.path.exists(transcript_path) and os.path.exists(sentences_json_path):
        print(f"[+] Transcript and sentences JSON already exist, reusing: {transcript_path}, {sentences_json_path}")
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = f.read()
        with open(sentences_json_path, "r", encoding="utf-8") as f:
            sentences = json.load(f)
        return transcript, sentences
    model = whisper.load_model("base")
    print(f"[+] Transcribing audio: {audio_path}")
    result = model.transcribe(audio_path, word_timestamps=False)
    transcript = result['text']
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript)
    print(f"[+] Transcript saved at: {transcript_path}")
    sentences = []
    for seg in result["segments"]:
        seg_sentences = re.split(r'(?<=[.!?])\s+', seg["text"].strip())
        start, end = seg["start"], seg["end"]
        if len(seg_sentences) == 1:
            sentences.append({"text": seg_sentences[0], "start": start, "end": end})
        else:
            total_len = sum(len(s) for s in seg_sentences)
            cur_start = start
            for s in seg_sentences:
                ratio = len(s) / total_len if total_len > 0 else 1.0 / len(seg_sentences)
                duration = (end - start) * ratio
                sentences.append({"text": s, "start": cur_start, "end": cur_start + duration})
                cur_start += duration
    with open(sentences_json_path, "w", encoding="utf-8") as f:
        json.dump(sentences, f, ensure_ascii=False, indent=2)
    print(f"[+] Sentences with timestamps saved at: {sentences_json_path}")
    return transcript, sentences

def connect_highlights_to_sentences(sentences, highlights):
    results = []
    sentence_texts = [s["text"].strip() for s in sentences]
    for highlight in highlights:
        highlight = highlight.strip()
        found = False
        for i in range(len(sentence_texts)):
            for j in range(i+1, len(sentence_texts)+1):
                combined = " ".join(sentence_texts[i:j]).strip()
                if combined == highlight:
                    start = sentences[i]["start"]
                    end = sentences[j-1]["end"]
                    results.append({"text": highlight, "start": start, "end": end})
                    found = True
                    break
            if found:
                break
        if not found:
            from difflib import SequenceMatcher
            best_ratio, best_sent = 0, None
            for sent in sentences:
                ratio = SequenceMatcher(None, highlight.lower(), sent["text"].lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_sent = sent
            if best_sent and best_ratio > 0.4:
                results.append({"text": highlight, "start": best_sent["start"], "end": best_sent["end"]})
            else:
                results.append({"text": highlight, "start": None, "end": None})
    return results

def extract_meaningful_parts(transcript):
    keywords = [
        "joke", "funny", "quote", "laugh", "moment", "lesson", "story", "advice", "wisdom", "important", "key", "tip"
    ]
    sentences = re.split(r'(?<=[.!?])\s+', transcript)
    return [s.strip() for s in sentences if any(k in s.lower() for k in keywords)]

def extract_reel_material_hf(
    transcript,
    model="moonshotai/Kimi-K2-Instruct",
    hf_token=None
):
    import os
    from huggingface_hub import InferenceClient
    if hf_token is None:
        hf_token = os.getenv("HUGGINGFACE_API_TOKEN") or os.getenv("HF_TOKEN")
    if not hf_token:
        print("[!] HuggingFace API token not set. Set HUGGINGFACE_API_TOKEN or HF_TOKEN env variable.")
        return []
    prompt = (
        "From the transcript below, extract all segments that are powerful, funny, emotional, insightful, or otherwise suitable for social media reels.\n\n"
        "IMPORTANT RULES:\n"
        "- DO NOT rephrase, rewrite, or summarize anything.\n"
        "- Copy the exact lines from the transcript as they appear.\n"
        "- Group consecutive lines together into longer segments if they form a complete thought, story, or flow naturally (such as a quote continued after a pause, a full anecdote, or a back-and-forth conversation).\n"
        "- Prefer longer, context-rich segments over short snippets, as long as they remain engaging and relevant.\n"
        "- Include full conversations, jokes, or statements only if the entire sequence feels impactful or reel-worthy.\n"
        "- Use your best judgment as a content editor to find viral, emotional, or highly engaging moments.\n"
        "- If in doubt, prefer to include more context rather than less.\n\n"
        f"Transcript:\n{transcript}\n\n"
        "Reel-Worthy Transcript Segments (Verbatim, as bullet points):"
    )
    try:
        client = InferenceClient(
            provider="together",
            api_key=hf_token,
        )
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = completion.choices[0].message.content
        print("[AI RAW RESPONSE]\n", content)
        highlights = [line.lstrip('-• ').strip() for line in content.split('\n') if line.strip()]
        return highlights
    except Exception as e:
        print(f"[!] HuggingFace API error: {e}")
        print("[!] Falling back to keyword-based extraction.")
        return extract_meaningful_parts(transcript)

def cut_video_segments(video_path, segments, output_dir="../downloads/clips"):
    import subprocess
    os.makedirs(output_dir, exist_ok=True)
    output_files = []
    for idx, seg in enumerate(segments):
        if seg["start"] is None or seg["end"] is None:
            continue
        out_file = os.path.join(
            output_dir,
            f"clip_{idx+1}_{int(seg['start'])}-{int(seg['end'])}.mp4"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(seg["start"]),
            "-to", str(seg["end"]),
            "-i", video_path,
            "-c", "copy",
            out_file
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        output_files.append(out_file)
    return output_files

# --- MAIN EXECUTION ---
url = "https://www.youtube.com/watch?v=FRTpI2Gu1KA"
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