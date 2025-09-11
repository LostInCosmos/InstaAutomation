import re
import os
import json
import logging
from typing import List, Dict, Optional
from huggingface_hub import InferenceClient

# Configure logging
logger = logging.getLogger(__name__)

def extract_reel_material_hf(
    transcript_segments: List[Dict],  # Changed from transcript to transcript_segments
    model: str = "moonshotai/Kimi-K2-Instruct",
    hf_token: Optional[str] = None
) -> List[Dict]:
    if hf_token is None:
        hf_token = os.getenv("HUGGINGFACE_API_TOKEN") or os.getenv("HF_TOKEN")
    if not hf_token:
        logger.error("HuggingFace API token not set")
        print("[!] HuggingFace API token not set. Set HUGGINGFACE_API_TOKEN or HF_TOKEN env variable.")
        return []
    
    # Create a formatted transcript with timestamps for AI analysis
    formatted_transcript = ""
    for i, segment in enumerate(transcript_segments):
        start_time = segment.get('start', 0)
        end_time = segment.get('end', 0)
        text = segment.get('text', '')
        formatted_transcript += f"[{start_time:.1f}s - {end_time:.1f}s]: {text}\n"
    
    logger.info(f"Sending {len(transcript_segments)} segments to AI for analysis")
    print(f"[+] 🤖 Sending {len(transcript_segments)} segments to AI for analysis...")
    print(f"[+] 💡 Looking for 40-60 second viral clips...")
    
    prompt = (
        "From the timestamped transcript below, create COMPLETE 40-60 second video clips that are perfect for social media reels.\n\n"
        "IMPORTANT RULES:\n"
        "- Each clip should be 40-60 seconds long and tell a COMPLETE story or thought\n"
        "- DO NOT cut off sentences mid-way - ensure each clip has natural start and end points\n"
        "- Group consecutive segments together to create coherent, engaging narratives\n"
        "- Focus on: motivational quotes, funny moments, emotional stories, mind-blowing facts, complete explanations\n"
        "- Each clip should hook viewers immediately and keep them engaged throughout\n"
        "- Prefer clips that can stand alone and make sense without additional context\n"
        "- Calculate exact start and end times based on the timestamps provided\n\n"
        f"Timestamped Transcript:\n{formatted_transcript}\n\n"
        "Return your response as a JSON array with this format:\n"
        "[\n"
        "  {\n"
        "    \"text\": \"exact transcript text for the clip\",\n"
        "    \"start_time\": start_timestamp_in_seconds,\n"
        "    \"end_time\": end_timestamp_in_seconds,\n"
        "    \"duration\": duration_in_seconds,\n"
        "    \"hook\": \"what makes this clip engaging\"\n"
        "  }\n"
        "]\n"
    )
    
    try:
        logger.info(f"Creating HuggingFace client with model: {model}")
        client = InferenceClient(
            provider="together",
            api_key=hf_token,
        )
        
        logger.info("Sending request to HuggingFace API...")
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = completion.choices[0].message.content
        logger.debug(f"AI response received: {len(content)} characters")
        print("[AI RAW RESPONSE]\n", content)
        
        try:
            # Try to parse the response as JSON
            # First, try to clean up common JSON issues
            content_clean = content.strip()
            
            # Remove markdown code blocks if present
            if content_clean.startswith('```'):
                content_clean = '\n'.join(content_clean.split('\n')[1:-1])
            
            # Try to extract JSON array from the response
            json_match = re.search(r'\[.*\]', content_clean, re.DOTALL)
            if json_match:
                content_clean = json_match.group(0)
            
            clips = json.loads(content_clean)
            if isinstance(clips, list) and len(clips) > 0:
                # Validate that clips have required fields
                valid_clips = []
                for clip in clips:
                    if isinstance(clip, dict) and 'text' in clip:
                        # Ensure required fields exist
                        if 'start_time' not in clip:
                            clip['start_time'] = None
                        if 'end_time' not in clip:
                            clip['end_time'] = None
                        if 'duration' not in clip:
                            clip['duration'] = None
                        if 'hook' not in clip:
                            clip['hook'] = 'AI extracted content'
                        valid_clips.append(clip)
                
                if valid_clips:
                    logger.info(f"Successfully extracted {len(valid_clips)} clips from AI")
                    print(f"[+] ✅ Successfully extracted {len(valid_clips)} clips from AI")
                    return valid_clips
                    
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            print("[!] Failed to parse JSON response, trying to extract from text...")
        
        # Fallback: extract from bullet points if JSON parsing fails
        logger.info("Falling back to text extraction")
        highlights = [line.lstrip('-• ').strip() for line in content.split('\n') if line.strip()]
        # Convert to expected format for compatibility
        fallback_clips = [{"text": highlight, "start_time": None, "end_time": None, "duration": None, "hook": "AI extracted"} for highlight in highlights if highlight]
        logger.info(f"Extracted {len(fallback_clips)} clips from text fallback")
        return fallback_clips
        
    except Exception as e:
        logger.error(f"HuggingFace API error: {e}")
        print(f"[!] HuggingFace API error: {e}")
        print("[!] Falling back to keyword-based extraction.")
        return extract_meaningful_parts(transcript_segments)

def extract_meaningful_parts(transcript_segments: List[Dict]) -> List[Dict]:
    """Extract meaningful parts using keyword matching as fallback."""
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


    