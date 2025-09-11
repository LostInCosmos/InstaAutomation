import os
import yt_dlp
import whisper
import re
import json
import logging
from concurrent.futures import ThreadPoolExecutor
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
import config

# Configure logging
logger = logging.getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    return sanitized.replace('\n', '').replace('\r', '').strip()

def check_existing_transcript(video_url: str, output_dir: str = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Check if transcript files already exist for this video"""
    if output_dir is None:
        output_dir = str(config.DOWNLOADS_DIR)
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = sanitize_filename(info['title'])
    except Exception as e:
        logger.error(f"Failed to extract video info: {e}")
        return None, None, None
    
    output_path = Path(output_dir)
    base_path = output_path / title
    # Build paths safely without with_suffix for custom suffix additions
    transcript_path = str(output_path / f"{title}.txt")
    sentences_json_path = str(output_path / f"{title}_sentences.json")
    
    if Path(transcript_path).exists() and Path(sentences_json_path).exists():
        logger.info(f"Found existing transcript files for: {title}")
        print(f"[+] 🎯 Found existing transcript files for: {title}")
        print(f"[+] Skipping audio download - using cached transcript")
        return transcript_path, sentences_json_path, title
    
    return None, None, title

def download_youtube_audio(video_url: str, output_dir: str = None, cleanup: bool = False) -> Tuple[Optional[str], Optional[str]]:
    """Download YouTube audio with improved error handling and logging."""
    if output_dir is None:
        output_dir = str(config.DOWNLOADS_DIR)
    logger.info(f"Starting audio download for URL: {video_url}")
    print("\n[1/3] 🎵 Fetching video information...")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = sanitize_filename(info['title'])
            duration = info.get('duration', 0)
            logger.info(f"Video info extracted: {title}, duration: {duration}s")
            print(f"[+] Video found: {title}")
            print(f"[+] Duration: {duration//60}m {duration%60}s")
    except Exception as e:
        logger.error(f"Failed to fetch video info: {e}")
        print(f"[!] Failed to fetch video info: {e}")
        return None, None
    
    mp3_file = output_path / f"{title}.mp3"
    if mp3_file.exists():
        logger.info(f"MP3 already exists, reusing: {mp3_file}")
        print(f"[+] MP3 already exists, reusing: {mp3_file}")
        return str(mp3_file), title
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': str(output_path / f'{title}.%(ext)s'),
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
            logger.info(f"Successfully downloaded and converted to mp3: {mp3_file}")
            print(f"[+] Downloaded and converted to mp3: {mp3_file}")
            return str(mp3_file), title
    except Exception as e:
        logger.error(f"Failed to download audio: {e}")
        print(f"[!] Failed to download audio: {e}")
        print("[!] Try upgrading yt-dlp: pip install -U yt-dlp")
        return None, None

def transcribe_audio_to_text(audio_path: str) -> Tuple[str, List[Dict]]:
    """Transcribe audio to text with improved error handling and logging."""
    logger.info(f"Starting transcription for: {audio_path}")
    print("\n[2/3] 🎯 Preparing transcription...")
    
    audio_file = Path(audio_path)
    base_stem = audio_file.with_suffix('').name
    output_dir = audio_file.parent
    transcript_path = output_dir / f"{base_stem}.txt"
    sentences_json_path = output_dir / f"{base_stem}_sentences.json"
    
    if transcript_path.exists() and sentences_json_path.exists():
        logger.info("Found existing transcription files, loading...")
        print(f"[+] Found existing transcription files")
        print(f"[+] Loading transcript: {transcript_path}")
        print(f"[+] Loading timestamps: {sentences_json_path}")
        
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                transcript = f.read()
            with open(sentences_json_path, "r", encoding="utf-8") as f:
                sentences = json.load(f)
            logger.info(f"Loaded cached transcript: {len(transcript)} chars, {len(sentences)} sentences")
            return transcript, sentences
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to load cached files: {e}")
            # Continue with transcription if cached files are corrupted
    logger.info("Loading Whisper model (tiny - faster processing)...")
    print(f"[+] Loading Whisper model (tiny - faster processing)...")
    
    try:
        model = whisper.load_model("tiny")  # Use tiny model for 4x faster processing
        
        logger.info(f"Starting transcription of: {audio_file.name}")
        print(f"[+] Starting transcription of: {audio_file.name}")
        print(f"[+] Using fast transcription mode...")
        
        # Optimize transcription for speed
        result = model.transcribe(
            str(audio_path), 
            word_timestamps=False,
            fp16=True,  # Use half precision for speed
            language="en",  # Skip language detection
            condition_on_previous_text=False  # Disable context for speed
        )
        transcript = result['text']
        
        logger.info("Transcription completed successfully")
        print(f"[+] Transcription completed successfully!")
        print(f"[+] Saving transcript to file...")
        
        # Save transcript
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript)
        logger.info(f"Transcript saved: {transcript_path.name}")
        print(f"[+] Transcript saved: {transcript_path.name}")
        
        # Process segments into sentences
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
        
        # Save sentences with timestamps
        with open(sentences_json_path, "w", encoding="utf-8") as f:
            json.dump(sentences, f, ensure_ascii=False, indent=2)
        logger.info(f"Sentences with timestamps saved: {sentences_json_path.name}")
        print(f"[+] Sentences with timestamps saved at: {sentences_json_path}")
        return transcript, sentences
        
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        print(f"[!] Transcription failed: {e}")
        raise

def connect_highlights_to_sentences(sentences: List[Dict], highlights: List[str]) -> List[Dict]:
    """Connect highlights to sentences with improved matching algorithms."""
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


def cut_video_segments(video_url: str, segments: List[Dict], output_dir: str = None) -> List[str]:
    """Cut video segments with improved error handling and logging."""
    if output_dir is None:
        output_dir = config.OUTPUT_CLIPS_DIR
    logger.info(f"Starting video segmentation for {len(segments)} segments")
    print("\n[3/3] 🎬 Processing video segments...")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    output_files = []

    # Download optimized quality video for faster processing
    logger.info("Downloading optimized video for processing...")
    print("[+] Downloading optimized video for processing...")
    
    ydl_opts = {
        'format': 'best[height<=480][ext=mp4]/best[ext=mp4]/best',  # Lower resolution for faster processing
        'outtmpl': str(output_path / 'temp_video.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        video_path = output_path / 'temp_video.mp4'
        logger.info(f"Video downloaded successfully: {video_path}")
    except Exception as e:
        logger.error(f"Failed to download video: {e}")
        print(f"[!] Failed to download high quality video: {e}")
        return []

    def process_segment(idx: int, seg: Dict) -> Optional[str]:
        """Process a single video segment with improved error handling."""
        start_time = seg.get("start_time") or seg.get("start")
        end_time = seg.get("end_time") or seg.get("end")
        
        if start_time is None or end_time is None:
            logger.warning(f"Skipping segment {idx} - Invalid timestamps")
            print(f"[!] Skipping segment {idx} - Invalid timestamps")
            return None
            
        out_file = output_path / f"clip_{idx:02d}_{int(start_time)}-{int(end_time)}.mp4"
        
        logger.info(f"Processing clip {idx}/{len(segments)}: {int(end_time - start_time)}s")
        print(f"[+] Processing clip {idx}/{len(segments)}: {int(end_time - start_time)}s")
        
        # Optimized FFmpeg command for 720p output quality
        cmd = [
            "ffmpeg",
            "-y",  # Overwrite output
            "-ss", str(start_time),  # Seek to start time
            "-i", str(video_path),  # Input file
            "-t", str(end_time - start_time),  # Duration instead of end time
            "-c:v", "libx264",  # Video codec
            "-preset", config.FFMPEG_PRESET,  # Balanced speed/quality
            "-crf", str(config.VIDEO_QUALITY),  # Better quality for 720p
            "-c:a", "aac",  # Audio codec  
            "-b:a", config.AUDIO_BITRATE,  # Higher audio bitrate for quality
            "-avoid_negative_ts", "make_zero",  # Fix timing issues
            str(out_file)
        ]
        
        try:
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            logger.info(f"Successfully processed segment {idx}: {out_file.name}")
            print(f"[+] Saved: {out_file.name}")
            return str(out_file)
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed for segment {idx}: {e}")
            print(f"[!] Failed to process segment {idx}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error processing segment {idx}: {e}")
            print(f"[!] Failed to process segment {idx}: {e}")
            return None

    max_workers = min(config.MAX_PARALLEL_WORKERS, os.cpu_count() or 1)
    logger.info(f"Cutting {len(segments)} video segments with {max_workers} parallel threads...")
    print(f"[+] Cutting {len(segments)} video segments with {max_workers} parallel threads...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        output_files = list(executor.map(process_segment, range(1, len(segments) + 1), segments))
    
    # Cleanup temporary full video
    try:
        if video_path.exists():
            video_path.unlink()
            logger.info("Cleaned up temporary video file")
    except Exception as e:
        logger.warning(f"Failed to cleanup temporary video: {e}")
        
    output_files = [f for f in output_files if f is not None]
    logger.info(f"Successfully created {len(output_files)} video clips")
    print(f"\n✨ Successfully created {len(output_files)} video clips!")
    return output_files

