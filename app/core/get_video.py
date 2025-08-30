import os
import yt_dlp
import whisper
import re
import json

def sanitize_filename(filename):
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    return sanitized.replace('\n', '').replace('\r', '').strip()

def download_youtube_audio(video_url, output_dir="../downloads/", cleanup=False):
    print("\n[1/3] 🎵 Fetching video information...")
    os.makedirs(output_dir, exist_ok=True)
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = sanitize_filename(info['title'])
            duration = info.get('duration', 0)
            print(f"[+] Video found: {title}")
            print(f"[+] Duration: {duration//60}m {duration%60}s")
    except Exception as e:
        print(f"[!] Failed to fetch video info: {e}")
        return None, None
    mp3_file = os.path.join(output_dir, f"{title}.mp3")
    if os.path.exists(mp3_file):
        print(f"[+] MP3 already exists, reusing: {mp3_file}")
        return mp3_file, title
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, f'{title}.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        },
        'progress_hooks': [lambda d: print(f"[+] Downloading: {d['_percent_str']} of {d.get('_total_bytes_str', 'unknown size')}") 
                          if d['status'] == 'downloading' else None],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(video_url, download=True)
            print(f"[+] Downloaded and converted to mp3: {mp3_file}")
            return mp3_file, title
    except Exception as e:
        print(f"[!] Failed to download audio: {e}")
        print("[!] Try upgrading yt-dlp: pip install -U yt-dlp")
        return None, None

def transcribe_audio_to_text(audio_path):
    print("\n[2/3] 🎯 Preparing transcription...")
    base, _ = os.path.splitext(audio_path)
    transcript_path = base + ".txt"
    sentences_json_path = base + "_sentences.json"
    
    if os.path.exists(transcript_path) and os.path.exists(sentences_json_path):
        print(f"[+] Found existing transcription files")
        print(f"[+] Loading transcript: {transcript_path}")
        print(f"[+] Loading timestamps: {sentences_json_path}")
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = f.read()
        with open(sentences_json_path, "r", encoding="utf-8") as f:
            sentences = json.load(f)
        return transcript, sentences
    print(f"[+] Loading Whisper model...")
    model = whisper.load_model("base")
    
    print(f"[+] Starting transcription of: {os.path.basename(audio_path)}")
    print(f"[+] This might take a few minutes depending on the audio length...")
    
    result = model.transcribe(audio_path, word_timestamps=False)
    transcript = result['text']
    
    print(f"[+] Transcription completed successfully!")
    print(f"[+] Saving transcript to file...")
    
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript)
    print(f"[+] Transcript saved: {os.path.basename(transcript_path)}")
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


def cut_video_segments(video_url, segments, output_dir="../downloads/clips"):
    print("\n[3/3] 🎬 Processing video segments...")
    import subprocess
    os.makedirs(output_dir, exist_ok=True)
    output_files = []

    # Download high quality video first
    print("[+] Downloading high quality video...")
    ydl_opts = {
        'format': 'best[height<=720][ext=mp4]/best[ext=mp4]/best',  # Lower quality to avoid restrictions
        'outtmpl': os.path.join(output_dir, 'temp_video.%(ext)s'),
        'quiet': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        },
        'progress_hooks': [lambda d: print(f"[+] Downloading: {d['_percent_str']} of {d.get('_total_bytes_str', 'unknown size')}") 
                          if d['status'] == 'downloading' else None],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        video_path = os.path.join(output_dir, 'temp_video.mp4')
    except Exception as e:
        print(f"[!] Failed to download high quality video: {e}")
        return []

    print(f"[+] Cutting {len(segments)} video segments...")
    for idx, seg in enumerate(segments, 1):
        start_time = seg.get("start_time") or seg.get("start")
        end_time = seg.get("end_time") or seg.get("end")
        
        if start_time is None or end_time is None:
            print(f"[!] Skipping segment {idx} - Invalid timestamps")
            continue
            
        out_file = os.path.join(
            output_dir,
            f"clip_{idx:02d}_{int(start_time)}-{int(end_time)}.mp4"
        )
        
        print(f"[+] Processing clip {idx}/{len(segments)}: {int(end_time - start_time)}s")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(start_time),
            "-to", str(end_time),
            "-i", video_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "22",
            out_file
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[+] Saved: {os.path.basename(out_file)}")
            output_files.append(out_file)
        except Exception as e:
            print(f"[!] Failed to process segment {idx}: {e}")
    
    # Cleanup temporary full video
    try:
        os.remove(video_path)
    except:
        pass
        
    print(f"\n✨ Successfully created {len(output_files)} video clips!")
    return output_files

