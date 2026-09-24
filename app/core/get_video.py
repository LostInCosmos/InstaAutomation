import os
import yt_dlp
from groq import Groq
import re
import json
import logging
from concurrent.futures import ThreadPoolExecutor
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
import config
from utils.error_handler import retry_on_failure
from core.subtitles import build_cues, save_cues

logger = logging.getLogger(__name__)

# YouTube authentication headers
YOUTUBE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

EXTRACTOR_ARGS = {
    'youtube': {
        'player_client': ['android', 'web', 'ios'],
        'extract_flat': 'in_playlist'
    }
}


def sanitize_filename(filename: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    return sanitized.replace('\n', '').replace('\r', '').strip()


def _download_progress_hook(d: Dict[str, Any]) -> None:
    """Show download progress."""
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', 'N/A')
        size = d.get('_total_bytes_str', 'unknown')
        print(f"[+] Downloading: {percent} of {size}", end='\r')
    elif d['status'] == 'finished':
        print(f"[+] Download finished, now converting to MP3...")


def get_video_info(video_url: str) -> Optional[Dict[str, Any]]:
    """Look up a video's title/duration once, without downloading anything."""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'http_headers': YOUTUBE_HEADERS,
            'extractor_args': EXTRACTOR_ARGS,
            'socket_timeout': 30
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
        return {'title': sanitize_filename(info['title']), 'duration': info.get('duration', 0)}
    except Exception as e:
        logger.error(f"Failed to extract video info: {e}")
        print(f"[!] Failed to fetch video info: {e}")
        print("[!] Try updating yt-dlp: pip install -U yt-dlp")
        return None


# --- Caching (avoid re-spending Groq's transcription/LLM budget on re-runs) ---

def load_cached_results(title: str, output_dir: str = None) -> Optional[Dict[str, Any]]:
    """Load a previously-completed transcript + sentences + highlights for this
    title, if all three are present on disk. Word-level timestamps (used for
    subtitles and precise clip-boundary padding) are loaded too if present, but
    aren't required for a cache hit - older cached videos won't have them, and
    forcing a full re-transcription just to backfill them would waste quota."""
    if output_dir is None:
        output_dir = str(config.DOWNLOADS_DIR)
    output_path = Path(output_dir)
    transcript_path = output_path / f"{title}.txt"
    sentences_path = output_path / f"{title}_sentences.json"
    highlights_path = output_path / f"{title}_highlights.json"
    words_path = output_path / f"{title}_words.json"

    if not (transcript_path.exists() and sentences_path.exists() and highlights_path.exists()):
        return None

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = f.read()
        with open(sentences_path, "r", encoding="utf-8") as f:
            sentences = json.load(f)
        with open(highlights_path, "r", encoding="utf-8") as f:
            highlights = json.load(f)
        words = []
        if words_path.exists():
            with open(words_path, "r", encoding="utf-8") as f:
                words = json.load(f)
        logger.info(f"Loaded cached results for '{title}': {len(sentences)} sentences, {len(highlights)} highlights, {len(words)} words")
        return {'transcript': transcript, 'sentences': sentences, 'highlights': highlights, 'words': words}
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to load cached results, reprocessing: {e}")
        return None


def save_results(title: str, sentences: List[Dict], highlights: List[Dict], words: List[Dict] = None, output_dir: str = None) -> None:
    """Persist the assembled transcript/sentences/highlights/words so a re-run
    of the same video can skip transcription and clip-selection entirely."""
    if output_dir is None:
        output_dir = str(config.DOWNLOADS_DIR)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    transcript = " ".join(s['text'] for s in sentences)
    with open(output_path / f"{title}.txt", "w", encoding="utf-8") as f:
        f.write(transcript)
    with open(output_path / f"{title}_sentences.json", "w", encoding="utf-8") as f:
        json.dump(sentences, f, ensure_ascii=False, indent=2)
    with open(output_path / f"{title}_highlights.json", "w", encoding="utf-8") as f:
        json.dump(highlights, f, ensure_ascii=False, indent=2)
    if words:
        with open(output_path / f"{title}_words.json", "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved results for '{title}'")


# --- Downloads (audio and video are independent and can run concurrently) ---

def download_audio(video_url: str, title: str, output_dir: str = None) -> Optional[str]:
    """Download the video's audio as MP3."""
    if output_dir is None:
        output_dir = str(config.DOWNLOADS_DIR)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    mp3_file = output_path / f"{title}.mp3"
    if mp3_file.exists():
        logger.info(f"MP3 already exists, reusing: {mp3_file}")
        print(f"[+] MP3 already exists, reusing: {mp3_file}")
        return str(mp3_file)

    logger.info(f"Starting audio download for URL: {video_url}")
    print("[+] 🎵 Downloading audio...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_path / f'{title}.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
        'no_warnings': True,
        'http_headers': YOUTUBE_HEADERS,
        'extractor_args': EXTRACTOR_ARGS,
        'socket_timeout': 30,
        'retry_sleep': 5,
        'progress_hooks': [_download_progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(video_url, download=True)
        logger.info(f"Downloaded and converted to mp3: {mp3_file}")
        print(f"[+] ✅ Downloaded audio: {mp3_file.name}")
        return str(mp3_file)
    except Exception as e:
        logger.error(f"Failed to download audio: {e}")
        print(f"[!] Failed to download audio: {e}")
        print("[!] Troubleshooting steps:")
        print("[!] 1. Update yt-dlp: pip install -U yt-dlp")
        print("[!] 2. Check your internet connection")
        print("[!] 3. Try again in a few moments (YouTube rate limiting)")
        return None


def download_video(video_url: str, output_dir: str = None) -> Optional[str]:
    """Download a moderate-resolution (<=480p) copy of the source video for clip
    cutting. Deliberately capped: the final overlay only displays the clip inside
    a fraction of the 1080x1920 canvas, so a full-res download would be wasted
    bandwidth. Meant to be started in the background, in parallel with the audio
    pipeline, since it doesn't depend on transcription or clip selection at all."""
    if output_dir is None:
        output_dir = config.OUTPUT_CLIPS_DIR

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading source video for clip cutting...")
    print("[+] 🎬 Downloading source video (<=480p) for clip cutting...")

    ydl_opts = {
        'format': 'best[height<=480][ext=mp4]/best[ext=mp4]/best',
        'outtmpl': str(output_path / 'temp_video.%(ext)s'),
        'quiet': False,
        'no_warnings': True,
        'http_headers': YOUTUBE_HEADERS,
        'extractor_args': EXTRACTOR_ARGS,
        'socket_timeout': 30,
        'retry_sleep': 5,
        'progress_hooks': [_download_progress_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        video_path = output_path / 'temp_video.mp4'
        logger.info(f"Video downloaded: {video_path}")
        print(f"[+] ✅ Source video downloaded")
        return str(video_path)
    except Exception as e:
        logger.error(f"Failed to download video: {e}")
        print(f"[!] Failed to download video: {e}")
        return None


# --- Audio chunking + transcription ---

def _get_audio_duration(audio_path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(json.loads(result.stdout)["format"]["duration"])


def chunk_audio(audio_path: str, chunk_seconds: float, overlap_seconds: float, output_dir: str) -> List[Tuple[str, float]]:
    """Split an audio file into overlapping time windows, each small enough to
    stay under Groq's Whisper 25MB-per-request limit. Returns a list of
    (chunk_file_path, offset_seconds) pairs, where offset_seconds is the
    chunk's start time in the ORIGINAL audio (used to globally offset
    transcribed timestamps). If the audio is already short enough, returns it
    unchanged as a single "chunk" - no ffmpeg work needed."""
    total_duration = _get_audio_duration(audio_path)
    if total_duration <= chunk_seconds:
        return [(audio_path, 0.0)]

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    base_stem = Path(audio_path).with_suffix('').name

    chunks = []
    window_start = 0.0
    idx = 0
    while window_start < total_duration:
        duration = min(chunk_seconds, total_duration - window_start)
        chunk_path = str(output_path / f"{base_stem}_chunk{idx:02d}.mp3")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(window_start),
            "-i", str(audio_path),
            "-t", str(duration),
            "-c", "copy",
            chunk_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        chunks.append((chunk_path, window_start))
        idx += 1
        window_start += chunk_seconds - overlap_seconds

    return chunks


def _attr(obj, key, default=None):
    """Access a field on a Groq SDK response item, whether it comes back as a
    dict or a typed object."""
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


@retry_on_failure(max_retries=2, delay=5.0)
def transcribe_chunk(chunk_path: str, offset_seconds: float, groq_api_key: str) -> Tuple[List[Dict], List[Dict]]:
    """Transcribe one audio chunk via Groq's hosted Whisper, returning
    (sentences, words) with timestamps offset to match the ORIGINAL
    (pre-chunking) audio timeline. Sentences feed the clip-selection LLM
    prompt (word-level would be too verbose/token-heavy for that); words feed
    subtitle generation and precise clip-boundary padding for the final,
    already-selected clips."""
    client = Groq(api_key=groq_api_key)
    chunk_file = Path(chunk_path)

    with open(chunk_path, "rb") as f:
        result = client.audio.transcriptions.create(
            file=(chunk_file.name, f.read()),
            model=config.GROQ_WHISPER_MODEL,
            response_format="verbose_json",
            language="en",
            timestamp_granularities=["word", "segment"],
        )

    sentences = []
    for seg in result.segments:
        seg_text = _attr(seg, "text")
        seg_start = _attr(seg, "start") + offset_seconds
        seg_end = _attr(seg, "end") + offset_seconds
        seg_sentences = re.split(r'(?<=[.!?])\s+', seg_text.strip())

        if len(seg_sentences) == 1:
            sentences.append({"text": seg_sentences[0], "start": seg_start, "end": seg_end})
        else:
            total_len = sum(len(s) for s in seg_sentences)
            cur_start = seg_start
            for s in seg_sentences:
                ratio = len(s) / total_len if total_len > 0 else 1.0 / len(seg_sentences)
                duration = (seg_end - seg_start) * ratio
                sentences.append({"text": s, "start": cur_start, "end": cur_start + duration})
                cur_start += duration

    words = []
    for w in (getattr(result, "words", None) or []):
        words.append({
            "text": _attr(w, "word", _attr(w, "text", "")),
            "start": _attr(w, "start") + offset_seconds,
            "end": _attr(w, "end") + offset_seconds,
        })

    return sentences, words


def connect_highlights_to_sentences(sentences: List[Dict], highlights: List[str]) -> List[Dict]:
    """Fuzzy-match bare highlight text back onto the transcript to recover
    timestamps. Only needed when the LLM's structured JSON call fails and we
    fall back to plain-text bullet parsing (see ai/generate_script.py)."""
    logger.info(f"Connecting {len(highlights)} highlights to {len(sentences)} sentences")
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


# --- Cutting clips from the (already-downloaded) source video ---

def cut_segments_from_video(video_path: str, segments: List[Dict], words: List[Dict] = None, output_dir: str = None) -> List[str]:
    """Cut clips from an already-downloaded source video, in parallel. Deletes
    the source video once cutting is done. If word-level timestamps are given,
    also writes a matching <clip>.cues.json subtitle-cue file next to each
    clip (see core.subtitles) for the overlay step to burn in later."""
    if output_dir is None:
        output_dir = config.OUTPUT_CLIPS_DIR

    print("\n[+] 🎬 Cutting video segments...")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    video_file = Path(video_path)

    def process_segment(idx: int, seg: Dict) -> Optional[str]:
        start_time = seg.get("start_time") if seg.get("start_time") is not None else seg.get("start")
        end_time = seg.get("end_time") if seg.get("end_time") is not None else seg.get("end")

        if start_time is None or end_time is None:
            logger.warning(f"Skipping segment {idx} - Invalid timestamps")
            print(f"[!] Skipping segment {idx} - Invalid timestamps")
            return None

        duration = int(end_time - start_time)
        out_file = output_path / f"clip_{idx:02d}_{int(start_time)}-{int(end_time)}.mp4"

        logger.info(f"Processing clip {idx}/{len(segments)}: {duration}s")
        print(f"[+] Processing clip {idx}/{len(segments)}: {duration}s")

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", str(video_file),
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", config.FFMPEG_PRESET,
            "-crf", str(config.VIDEO_QUALITY),
            "-c:a", "aac",
            "-b:a", config.AUDIO_BITRATE,
            "-avoid_negative_ts", "make_zero",
            str(out_file)
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            logger.info(f"Processed segment {idx}: {out_file.name}")
            print(f"[+] Saved: {out_file.name}")

            if words:
                cues = build_cues(words, start_time, end_time)
                save_cues(cues, str(out_file.with_suffix('.cues.json')))

            return str(out_file)
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed for segment {idx}: {e}")
            print(f"[!] Failed to process segment {idx}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error processing segment {idx}: {e}")
            print(f"[!] Error processing segment {idx}: {e}")
            return None

    max_workers = min(config.MAX_PARALLEL_WORKERS, os.cpu_count() or 1)
    logger.info(f"Cutting {len(segments)} segments with {max_workers} workers...")
    print(f"[+] Cutting {len(segments)} segments with {max_workers} parallel workers...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        output_files = list(executor.map(process_segment, range(1, len(segments) + 1), segments))

    try:
        if video_file.exists():
            video_file.unlink()
            logger.info("Cleaned up temporary video")
    except OSError as e:
        logger.warning(f"Failed to cleanup temporary video: {e}")

    output_files = [f for f in output_files if f is not None]
    logger.info(f"Successfully created {len(output_files)} video clips")
    print(f"\n✨ Successfully created {len(output_files)} video clips!")
    return output_files
