"""Generate subtitle cues for a clip from word-level transcription timestamps,
and render them as an ASS subtitle file.

Two steps, split because the final render position (MarginV) depends on where
the video ends up placed on the 1080x1920 canvas, which isn't known until the
background-overlay step - but the cue text/timing IS known right after a clip
is cut. So: build_cues()+save_cues() run at cut time; write_ass() runs at
overlay time once the final placement is known.

ASS (not plain SRT) is used deliberately: ffmpeg's subtitles filter scales a
plain SRT's forced font size unreliably in practice (confirmed empirically -
force_style's FontSize did not scale correctly against original_size). An ASS
file's own PlayResX/PlayResY + style block is what libass actually honors
reliably.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

Cue = Tuple[float, float, str]  # (start_seconds, end_seconds, text) - clip-local time


def build_cues(
    words: List[Dict], clip_start: float, clip_end: float,
    max_words_per_cue: int = 6, max_cue_duration: float = 3.0,
) -> List[Cue]:
    """Group word-level timestamps (global video timeline) into short,
    readable subtitle cues on the clip's own 0-based timeline. Cues break at
    max_words_per_cue words, max_cue_duration seconds, or sentence-ending
    punctuation - whichever comes first."""
    clip_duration = clip_end - clip_start
    clip_words = [w for w in words if w['start'] < clip_end and w['end'] > clip_start]
    if not clip_words:
        return []

    cues: List[Cue] = []
    current: List[str] = []
    cue_start = None
    cue_end = None

    for w in clip_words:
        w_start = max(0.0, min(clip_duration, w['start'] - clip_start))
        w_end = max(0.0, min(clip_duration, w['end'] - clip_start))
        if cue_start is None:
            cue_start = w_start
        current.append(w['text'])
        cue_end = w_end

        ends_sentence = w['text'].strip().endswith(('.', '!', '?'))
        if len(current) >= max_words_per_cue or (cue_end - cue_start) >= max_cue_duration or ends_sentence:
            cues.append((cue_start, cue_end, ' '.join(current)))
            current = []
            cue_start = None

    if current:
        cues.append((cue_start, cue_end, ' '.join(current)))

    return cues


def save_cues(cues: List[Cue], output_path: str) -> Optional[str]:
    """Persist cues as JSON so the overlay step (a separate function call,
    possibly a separate process via the thread pool) can load them once the
    final render position is known."""
    if not cues:
        return None
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(cues, f, ensure_ascii=False)
    except OSError as e:
        logger.error(f"Failed to write cues file {output_path}: {e}")
        return None
    return output_path


def load_cues(cues_path: str) -> List[Cue]:
    try:
        with open(cues_path, 'r', encoding='utf-8') as f:
            return [tuple(c) for c in json.load(f)]
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to load cues file {cues_path}: {e}")
        return []


def _format_ass_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{centis:02d}"


def write_ass(
    cues: List[Cue], output_path: str,
    play_width: int, play_height: int, font_size: int, margin_v: int,
) -> Optional[str]:
    """Write an ASS subtitle file with an explicit PlayResX/PlayResY and
    style, so libass renders font size/position reliably relative to the
    actual output frame."""
    if not cues:
        return None

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_width}\n"
        f"PlayResY: {play_height}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"1,0,0,0,100,100,0,0,1,3,0,2,10,10,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    lines = [header]
    for start, end, text in cues:
        text = str(text).replace('\n', ' ')
        lines.append(f"Dialogue: 0,{_format_ass_timestamp(start)},{_format_ass_timestamp(end)},Default,,0,0,0,,{text}\n")

    try:
        Path(output_path).write_text(''.join(lines), encoding='utf-8')
    except OSError as e:
        logger.error(f"Failed to write subtitle file {output_path}: {e}")
        return None
    return output_path
