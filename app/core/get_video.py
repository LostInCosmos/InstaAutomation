from __future__ import unicode_literals
import os
import yt_dlp
import whisper
import re
import json


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

        # 1. Exact sequence match
        for i in range(len(sentence_texts)):
            for j in range(i + 1, len(sentence_texts) + 1):
                combined = " ".join(sentence_texts[i:j]).strip()
                if combined == highlight:
                    results.append({
                        "text": highlight,
                        "start": sentences[i]["start"],
                        "end": sentences[j - 1]["end"]
                    })
                    found = True
                    break
            if found:
                break

        if not found:
            for j in range(len(sentence_texts), 0, -1):
                for i in range(j):
                    combined = " ".join(sentence_texts[i:j]).strip()
                    if highlight in combined:
                        start_idx = i
                        while start_idx > 0 and sentence_texts[start_idx - 1] in highlight:
                            start_idx -= 1
                        results.append({
                            "text": highlight,
                            "start": sentences[start_idx]["start"],
                            "end": sentences[j - 1]["end"]
                        })
                        found = True
                        break
                if found:
                    break

        if not found:
            max_overlap = 0
            best_i, best_j = None, None
            for i in range(len(sentence_texts)):
                for j in range(i + 1, len(sentence_texts) + 1):
                    combined = " ".join(sentence_texts[i:j]).strip()
                    overlap = len(os.path.commonprefix([highlight, combined]))
                    if overlap > max_overlap:
                        max_overlap = overlap
                        best_i, best_j = i, j
            if best_i is not None and best_j is not None and max_overlap > 30:
                results.append({
                    "text": highlight,
                    "start": sentences[best_i]["start"],
                    "end": sentences[best_j - 1]["end"]
                })
                found = True

        if not found:
            from difflib import SequenceMatcher
            best_ratio, best_sent = 0, None
            for sent in sentences:
                ratio = SequenceMatcher(None, highlight.lower(), sent["text"].lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_sent = sent
            if best_sent and best_ratio > 0.4:
                results.append({
                    "text": highlight,
                    "start": best_sent["start"],
                    "end": best_sent["end"]
                })
            else:
                results.append({
                    "text": highlight,
                    "start": None,
                    "end": None
                })

    return results


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

