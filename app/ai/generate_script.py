import re

def extract_reel_material_hf(
    transcript_segments,  # Changed from transcript to transcript_segments
    model="moonshotai/Kimi-K2-Instruct",
    hf_token=None
):
    import os
    import json
    from huggingface_hub import InferenceClient
    if hf_token is None:
        hf_token = os.getenv("HUGGINGFACE_API_TOKEN") or os.getenv("HF_TOKEN")
    if not hf_token:
        print("[!] HuggingFace API token not set. Set HUGGINGFACE_API_TOKEN or HF_TOKEN env variable.")
        return []
    
    # Create a formatted transcript with timestamps for AI analysis
    formatted_transcript = ""
    for i, segment in enumerate(transcript_segments):
        start_time = segment.get('start', 0)
        end_time = segment.get('end', 0)
        text = segment.get('text', '')
        formatted_transcript += f"[{start_time:.1f}s - {end_time:.1f}s]: {text}\n"
    
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
        
        try:
            # Try to parse the response as JSON
            # First, try to clean up common JSON issues
            content_clean = content.strip()
            
            # Remove markdown code blocks if present
            if content_clean.startswith('```'):
                content_clean = '\n'.join(content_clean.split('\n')[1:-1])
            
            # Try to extract JSON array from the response
            import re
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
                    print(f"[+] ✅ Successfully extracted {len(valid_clips)} clips from AI")
                    return valid_clips
                    
        except json.JSONDecodeError:
            print("[!] Failed to parse JSON response, trying to extract from text...")
        
        # Fallback: extract from bullet points if JSON parsing fails
        highlights = [line.lstrip('-• ').strip() for line in content.split('\n') if line.strip()]
        # Convert to expected format for compatibility
        return [{"text": highlight, "start_time": None, "end_time": None, "duration": None, "hook": "AI extracted"} for highlight in highlights if highlight]
    except Exception as e:
        print(f"[!] HuggingFace API error: {e}")
        print("[!] Falling back to keyword-based extraction.")
        return extract_meaningful_parts(transcript_segments)

def extract_meaningful_parts(transcript_segments):
    keywords = [
        "joke", "funny", "quote", "laugh", "moment", "lesson", "story", "advice", "wisdom", "important", "key", "tip"
    ]
    results = []
    for segment in transcript_segments:
        text = segment.get('text', '')
        if any(k in text.lower() for k in keywords):
            results.append({
                "text": text,
                "start_time": segment.get('start'),
                "end_time": segment.get('end'),
                "duration": segment.get('end', 0) - segment.get('start', 0),
                "hook": "Keyword matched"
            })
    return results