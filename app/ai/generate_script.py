import json
import logging
from typing import List, Dict
from groq import Groq
import config
from utils.error_handler import retry_on_failure

logger = logging.getLogger(__name__)


@retry_on_failure(max_retries=2, delay=10.0)
def extract_clips_from_segment(segments: List[Dict], model: str, groq_api_key: str) -> List[Dict]:
    """Send one batch of timestamped segments to Groq and parse the returned clips."""
    formatted_transcript = ""
    for segment in segments:
        start_time = segment.get('start', 0)
        end_time = segment.get('end', 0)
        text = segment.get('text', '')
        formatted_transcript += f"[{start_time:.1f}s - {end_time:.1f}s]: {text}\n"

    prompt = (
        f"From the FULL timestamped transcript below, find EVERY good clip that would work as a standalone "
        "social media reel. Read through the ENTIRE transcript before deciding - do not stop after finding "
        "just one or two. If the content supports it, return several clips (aim for at least 4-6 when "
        "there's enough material), spread across different parts of the transcript rather than clustered "
        "in one section.\n\n"
        "IMPORTANT RULES:\n"
        f"- Target length is {config.CLIP_DURATION_MIN}-{config.CLIP_DURATION_TARGET_MAX} seconds. You may run "
        f"up to {config.CLIP_DURATION_MAX} seconds if - and only if - you need the extra time to reach a real, "
        "complete ending. A clip that's a bit longer with a satisfying conclusion is ALWAYS better than a "
        "shorter one that cuts off mid-thought. Never end a clip mid-sentence or mid-idea just to hit a "
        "shorter duration\n"
        "- DO NOT cut off sentences mid-way - ensure each clip has natural start and end points, and ends on "
        "a genuine conclusion (the punchline, the answer, the resolution) rather than trailing off\n"
        "- The clip's OPENING LINE must work as a hook on its own - a bold claim, a surprising fact, a direct "
        "question, or a strong opinion that would stop someone mid-scroll. Choose the start_time so the clip "
        "begins AT that hook line, not somewhere before it with unrelated lead-in\n"
        "- If the transcript is a conversation/interview, prefer clips that capture a full, satisfying exchange "
        "(a complete question and its answer, or a complete back-and-forth) over a single isolated statement "
        "ripped out of context\n"
        "- Group consecutive segments together to create coherent, engaging narratives\n"
        "- Focus on: motivational quotes, funny moments, emotional stories, mind-blowing facts, complete explanations\n"
        "- Prefer clips that can stand alone and make sense without additional context\n"
        "- Calculate exact start and end times based on the timestamps provided\n"
        "- Do NOT return multiple clips that cover the same or heavily overlapping time range - "
        "pick only the single best version of each moment\n\n"
        f"Timestamped Transcript:\n{formatted_transcript}\n\n"
        "Return your response as valid JSON in this exact format:\n"
        "{\n"
        "  \"clips\": [\n"
        "    {\n"
        "      \"text\": \"exact transcript text for the clip\",\n"
        "      \"start_time\": start_timestamp_in_seconds,\n"
        "      \"end_time\": end_timestamp_in_seconds,\n"
        "      \"duration\": duration_in_seconds,\n"
        "      \"hook\": \"the opening hook line and why it grabs attention\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
    )

    logger.info(f"Sending {len(segments)} segments to Groq ({model}) for analysis")

    client = Groq(api_key=groq_api_key)
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=config.AI_TEMPERATURE,
        max_completion_tokens=config.AI_MAX_COMPLETION_TOKENS,
        reasoning_effort="low",       # gpt-oss-120b is a reasoning model - hidden "thinking"
        reasoning_format="hidden",    # tokens draw from the same budget as the JSON answer,
    )                                 # so keep reasoning short or it can eat the whole budget
    content = completion.choices[0].message.content
    logger.debug(f"AI response received: {len(content)} characters")

    try:
        data = json.loads(content)
        clips = data.get("clips", []) if isinstance(data, dict) else data

        if isinstance(clips, list) and len(clips) > 0:
            valid_clips = []
            for clip in clips:
                if isinstance(clip, dict) and 'text' in clip:
                    clip.setdefault('start_time', None)
                    clip.setdefault('end_time', None)
                    clip.setdefault('duration', None)
                    clip.setdefault('hook', 'AI extracted content')
                    valid_clips.append(clip)

            if valid_clips:
                logger.info(f"Successfully extracted {len(valid_clips)} clips from AI")
                print(f"[+] ✅ Extracted {len(valid_clips)} clips from this batch")
                return valid_clips

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON response: {e}")
        print("[!] Failed to parse JSON response, trying to extract from text...")

    # Fallback: extract from bullet points if JSON parsing fails
    logger.info("Falling back to text extraction")
    highlights = [line.lstrip('-• ').strip() for line in content.split('\n') if line.strip()]
    fallback_clips = [
        {"text": h, "start_time": None, "end_time": None, "duration": None, "hook": "AI extracted"}
        for h in highlights if h
    ]
    logger.info(f"Extracted {len(fallback_clips)} clips from text fallback")
    return fallback_clips


def dedupe_clips(clips: List[Dict], overlap_threshold: float = 0.5) -> List[Dict]:
    """Drop clips whose time range substantially overlaps a previously kept clip
    (expected near chunk-overlap boundaries), keeping the longer one."""
    timed = [c for c in clips if c.get('start_time') is not None and c.get('end_time') is not None]
    untimed = [c for c in clips if c.get('start_time') is None or c.get('end_time') is None]
    timed.sort(key=lambda c: c['start_time'])

    kept: List[Dict] = []
    for clip in timed:
        replaced = False
        for i, existing in enumerate(kept):
            overlap = min(clip['end_time'], existing['end_time']) - max(clip['start_time'], existing['start_time'])
            shorter = min(clip['end_time'] - clip['start_time'], existing['end_time'] - existing['start_time'])
            if shorter > 0 and overlap / shorter > overlap_threshold:
                if (clip['end_time'] - clip['start_time']) > (existing['end_time'] - existing['start_time']):
                    kept[i] = clip
                replaced = True
                break
        if not replaced:
            kept.append(clip)

    kept.sort(key=lambda c: c['start_time'])
    return kept + untimed


def extract_meaningful_parts(transcript_segments: List[Dict]) -> List[Dict]:
    """Extract meaningful parts using keyword matching - last-resort fallback
    if the AI extraction fails for every chunk."""
    logger.info("Using keyword-based extraction as fallback")

    keywords = [
        "joke", "funny", "quote", "laugh", "moment", "lesson", "story",
        "advice", "wisdom", "important", "key", "tip", "amazing", "incredible",
        "unbelievable", "shocking", "mind-blowing", "insane", "crazy"
    ]

    results = []
    for segment in transcript_segments:
        text = segment.get('text', '')
        if any(keyword in text.lower() for keyword in keywords):
            results.append({
                "text": text,
                "start_time": segment.get('start'),
                "end_time": segment.get('end'),
                "duration": segment.get('end', 0) - segment.get('start', 0),
                "hook": "Keyword matched"
            })

    logger.info(f"Extracted {len(results)} segments using keyword matching")
    return results
