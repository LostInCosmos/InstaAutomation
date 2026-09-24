"""End-to-end pipeline: YouTube URL -> Instagram reels.

Flow:
  1. Look up the video's title/duration once (no download).
  2. Kick off the source video download in the background immediately - it
     doesn't depend on transcription or clip selection, so it runs the whole
     time the audio pipeline below is working.
  3. If a fully cached transcript + sentences + highlights already exists for
     this title, skip straight to step 6.
  4. Otherwise: download audio, split it into overlapping ~15 min chunks
     (small enough for Groq Whisper's 25MB-per-request limit), and pipeline
     each chunk through: transcribe (Groq Whisper) -> extract clips (Groq LLM,
     rate-limit-paced ~60s apart). While paced-waiting between LLM calls, the
     NEXT chunk's audio is already being transcribed in the background, so
     that wait isn't wasted - Whisper and the LLM draw from separate Groq
     quota pools, so this doesn't cost anything.
  5. Dedupe clips collected across chunk-overlap boundaries, then cache the
     assembled transcript/sentences/highlights for future re-runs.
  6. Wait for the source video (almost certainly already finished by now),
     cut the selected clips out of it, and overlay them on the background.

No database/queue is used for state - everything is in-memory for the run,
with the existing JSON-file cache for resuming a repeated run on the same
video. If you need mid-run resumability (e.g. surviving a crash partway
through a long podcast), that needs persistent storage and is a bigger
change - ask before adding one.
"""
import os
import time
import logging
from collections import Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Dict, List, Optional, Tuple, Any

import config
from core.get_video import (
    get_video_info, load_cached_results, save_results,
    download_audio, download_video, chunk_audio, transcribe_chunk,
    cut_segments_from_video, connect_highlights_to_sentences,
)
from core.video_overlay import process_clips_with_background
from ai.generate_script import extract_clips_from_segment, dedupe_clips, extract_meaningful_parts

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str], None]]


def _notify(progress_callback: ProgressCallback, message: str) -> None:
    """Print a progress message (CLI UX, unchanged) and also forward it to an
    optional callback (used by the web UI to show live status without
    scraping stdout)."""
    print(message)
    if progress_callback:
        progress_callback(message)


def process_video(url: str, progress_callback: ProgressCallback = None) -> Dict[str, Any]:
    """Run the full YouTube -> Instagram reel pipeline for one video."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        _notify(progress_callback, "[!] GROQ_API_KEY not set. Set it in your .env file.")
        return {'reels': []}

    start_time = time.time()

    info = get_video_info(url)
    if not info:
        return {'reels': []}
    title = info['title']
    duration = info['duration']
    _notify(progress_callback, f"[+] Video found: {title} ({duration // 60}m {duration % 60}s)")

    # Source video download doesn't depend on anything below - start it now so
    # it's (almost certainly) already done by the time we need it.
    download_pool = ThreadPoolExecutor(max_workers=1)
    video_future = download_pool.submit(download_video, url, config.OUTPUT_CLIPS_DIR)

    cached = load_cached_results(title)
    if cached:
        _notify(progress_callback, f"[+] 🎯 Using cached transcript + highlights for: {title}")
        sentences, words, highlights = cached['sentences'], cached.get('words', []), cached['highlights']
    else:
        sentences, words, highlights = _run_audio_pipeline(url, title, groq_api_key, progress_callback)
        if sentences and highlights:
            save_results(title, sentences, highlights, words)

    if not highlights:
        _notify(progress_callback, "[!] No reel material found. Try a different video.")
        # cancel() only works if the download hasn't started yet - by this point it
        # almost certainly has (or has already finished), so wait for it and clean
        # up the file directly rather than leaking it in downloads/reels/.
        video_path = video_future.result()
        download_pool.shutdown()
        if video_path and Path(video_path).exists():
            os.remove(video_path)
        return {'reels': [], 'title': title}

    highlights = _resolve_missing_timestamps(highlights, sentences)
    highlights = _pad_clip_boundaries(highlights, words or sentences)
    highlights = _filter_by_duration(highlights, progress_callback)

    if not highlights:
        _notify(progress_callback, "[!] No clips left after duration filtering. Try a different video.")
        video_path = video_future.result()
        download_pool.shutdown()
        if video_path and Path(video_path).exists():
            os.remove(video_path)
        return {'reels': [], 'title': title}

    ai_time = time.time() - start_time
    _notify(progress_callback, f"[+] Extracted {len(highlights)} clips in {ai_time:.1f}s - waiting for source video download...")

    video_path = video_future.result()
    download_pool.shutdown()
    if not video_path:
        return {'reels': [], 'title': title}

    cut_files = cut_segments_from_video(video_path, highlights, words=words, output_dir=config.OUTPUT_CLIPS_DIR)
    if not cut_files:
        _notify(progress_callback, "[!] No video clips were created to process with background.")
        return {'reels': [], 'title': title}

    _notify(progress_callback, f"[+] 🎨 Overlaying {len(cut_files)} clips onto background...")
    reels = process_clips_with_background(
        clip_files=cut_files,
        background_image_path=os.path.abspath(config.BACKGROUND_IMAGE),
        output_dir=config.OUTPUT_REELS_DIR,
        video_title=title,
    )

    print("[+] Cleaning up clip files...")
    for f in cut_files:
        try:
            os.remove(f)
            print(f"[+] Deleted clip: {os.path.basename(f)}")
        except OSError as e:
            print(f"[!] Could not delete clip {os.path.basename(f)}: {e}")
        cues_file = Path(f).with_suffix('.cues.json')
        if cues_file.exists():
            try:
                cues_file.unlink()
            except OSError:
                pass

    categories = Counter(h.get('category', 'other') for h in highlights)
    breakdown = ", ".join(f"{count} {name}" for name, count in categories.most_common())
    _notify(progress_callback, f"[+] 🎉 Done: {len(reels)} Instagram reels ready in downloads/instagram_reels/{title}/ ({breakdown})")
    return {
        'reels': reels, 'title': title, 'total_time': time.time() - start_time,
        'categories': dict(categories),
    }


def _run_audio_pipeline(
    url: str, title: str, groq_api_key: str, progress_callback: ProgressCallback = None
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Download audio, chunk it, and pipeline transcribe+extract per chunk with
    a one-chunk prefetch so the LLM rate-limit pacing wait isn't wasted time.
    Returns (sentences, words, highlights)."""
    mp3_path = download_audio(url, title, str(config.DOWNLOADS_DIR))
    if not mp3_path:
        return [], [], []

    chunks = chunk_audio(mp3_path, config.CHUNK_DURATION_SECONDS, config.CHUNK_OVERLAP_SECONDS, str(config.DOWNLOADS_DIR))
    if not chunks:
        return [], [], []
    _notify(progress_callback, f"[+] 📼 Split audio into {len(chunks)} chunk(s) for transcription + analysis")

    prep_pool = ThreadPoolExecutor(max_workers=1)

    all_sentences: List[Dict] = []
    all_words: List[Dict] = []
    all_clips: List[Dict] = []
    next_future: Future = prep_pool.submit(transcribe_chunk, *chunks[0], groq_api_key)

    for i, (chunk_path, offset) in enumerate(chunks):
        _notify(progress_callback, f"[+] 🎯 Transcribing chunk {i + 1}/{len(chunks)} ({offset:.0f}s - {offset + config.CHUNK_DURATION_SECONDS:.0f}s)...")
        chunk_sentences, chunk_words = next_future.result()

        # Prefetch the NEXT chunk's transcription now, so it happens in the
        # background while THIS chunk's LLM call + rate-limit pacing wait
        # (below) are in progress - Whisper and the LLM are separate Groq
        # quota pools, so this doesn't compete with the LLM's budget.
        if i + 1 < len(chunks):
            next_chunk_path, next_offset = chunks[i + 1]
            next_future = prep_pool.submit(transcribe_chunk, next_chunk_path, next_offset, groq_api_key)

        # The LLM sees the FULL chunk (including its overlap with neighbors) so
        # a clip near the boundary has a full chance to be captured. The
        # assembled transcript, though, should have each moment only once -
        # drop the leading overlap here since the previous chunk already
        # contributed that span.
        if i > 0:
            boundary = offset + config.CHUNK_OVERLAP_SECONDS
            all_sentences.extend(s for s in chunk_sentences if s['start'] >= boundary)
            all_words.extend(w for w in chunk_words if w['start'] >= boundary)
        else:
            all_sentences.extend(chunk_sentences)
            all_words.extend(chunk_words)

        _notify(progress_callback, f"[+] 🤖 Sending chunk {i + 1}/{len(chunks)} to AI for clip selection...")
        try:
            chunk_clips = extract_clips_from_segment(chunk_sentences, config.DEFAULT_AI_MODEL, groq_api_key)
            all_clips.extend(chunk_clips)
        except Exception as e:
            logger.error(f"Chunk {i + 1} clip extraction failed, skipping: {e}")
            print(f"[!] Chunk {i + 1} clip extraction failed, skipping: {e}")

        if len(chunks) > 1 and Path(chunk_path).exists():
            try:
                os.remove(chunk_path)
            except OSError as e:
                logger.warning(f"Could not delete chunk file {chunk_path}: {e}")

        if i + 1 < len(chunks):
            time.sleep(config.AI_CHUNK_DELAY_SECONDS)

    prep_pool.shutdown()

    if Path(mp3_path).exists():
        os.remove(mp3_path)

    if not all_clips:
        _notify(progress_callback, "[!] AI extraction failed for all chunks, falling back to keyword matching.")
        return all_sentences, all_words, extract_meaningful_parts(all_sentences)

    deduped = dedupe_clips(all_clips)
    _notify(progress_callback, f"[+] ✅ Collected {len(deduped)} unique clips across {len(chunks)} chunk(s)")
    return all_sentences, all_words, deduped


def _resolve_missing_timestamps(highlights: List[Dict], sentences: List[Dict]) -> List[Dict]:
    """For any clip the AI returned without timestamps (the JSON call failed and
    we fell back to bullet-text parsing), fuzzy-match its text back onto the
    transcript to recover a start/end time."""
    missing = [h for h in highlights if h.get('start_time') is None]
    if not missing:
        return highlights

    resolved = connect_highlights_to_sentences(sentences, [h['text'] for h in missing])
    resolved_by_text = {r['text']: r for r in resolved}

    fixed = []
    for h in highlights:
        if h.get('start_time') is None and h['text'] in resolved_by_text:
            r = resolved_by_text[h['text']]
            h = {**h, 'start_time': r['start'], 'end_time': r['end']}
        fixed.append(h)
    return fixed


def _pad_clip_boundaries(
    highlights: List[Dict], sentences: List[Dict],
    lead_max: float = None, trail_max: float = None, safety_margin: float = None,
) -> List[Dict]:
    """Pad each clip's start by up to lead_max seconds so the cut doesn't clip
    off the first syllable of the hook line (Whisper's sentence-start
    timestamp often lands a beat after the word actually begins). The end is
    padded by up to trail_max seconds (0 by default - the LLM is instructed
    to end each clip on a deliberate conclusion, so there's no trailing word
    to protect the way there is at the start).

    Padding is capped by the neighboring sentence's own boundary, minus a
    small safety_margin, so it stops just BEFORE that sentence rather than
    landing exactly on (or into) it - Whisper's timestamps aren't frame-perfect,
    so landing exactly on the boundary can still catch the next sentence's own
    first syllable, which sounds like a new thought starting and immediately
    getting cut off."""
    if lead_max is None:
        lead_max = config.CLIP_LEAD_BUFFER_SECONDS
    if trail_max is None:
        trail_max = config.CLIP_TRAIL_BUFFER_SECONDS
    if safety_margin is None:
        safety_margin = config.CLIP_BUFFER_SAFETY_MARGIN

    sentence_starts = sorted(s['start'] for s in sentences)
    sentence_ends = sorted(s['end'] for s in sentences)

    padded = []
    for h in highlights:
        start, end = h.get('start_time'), h.get('end_time')
        if start is None or end is None:
            padded.append(h)
            continue

        prev_end = max((e for e in sentence_ends if e <= start), default=0.0)
        next_start = min((s for s in sentence_starts if s >= end), default=end + trail_max)

        lead_gap = max(0.0, (start - prev_end) - safety_margin)
        trail_gap = max(0.0, (next_start - end) - safety_margin)

        lead_buffer = min(lead_max, lead_gap)
        trail_buffer = min(trail_max, trail_gap)

        # Don't let padding push a clip that's already near the duration
        # ceiling over it - that would get the whole clip dropped by
        # _filter_by_duration for a few seconds of breathing room, which is
        # exactly backwards. Scale padding down (not off) so it still uses
        # whatever room is actually available.
        room = max(0.0, config.CLIP_DURATION_MAX - (end - start))
        total_buffer = lead_buffer + trail_buffer
        if total_buffer > room:
            scale = (room / total_buffer) if total_buffer > 0 else 0.0
            lead_buffer *= scale
            trail_buffer *= scale

        padded.append({**h, 'start_time': start - lead_buffer, 'end_time': end + trail_buffer})

    return padded


def _filter_by_duration(highlights: List[Dict], progress_callback: ProgressCallback = None) -> List[Dict]:
    """Drop any clip outside [CLIP_DURATION_MIN, CLIP_DURATION_MAX] - a safety
    net regardless of why it ended up too short (the LLM ignoring the prompt,
    or the keyword-matching fallback grabbing a single short sentence) or too
    long (padding pushed it past the ceiling)."""
    kept = []
    dropped = 0
    for h in highlights:
        start, end = h.get('start_time'), h.get('end_time')
        if start is None or end is None:
            dropped += 1
            continue
        duration = end - start
        if config.CLIP_DURATION_MIN <= duration <= config.CLIP_DURATION_MAX:
            kept.append(h)
        else:
            dropped += 1
            logger.info(f"Dropping clip outside duration bounds ({duration:.1f}s): {h.get('text', '')[:60]}")

    if dropped:
        _notify(progress_callback, f"[+] Dropped {dropped} clip(s) outside {config.CLIP_DURATION_MIN}-{config.CLIP_DURATION_MAX}s")

    return kept
