

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

def extract_meaningful_parts(transcript):
    keywords = [
        "joke", "funny", "quote", "laugh", "moment", "lesson", "story", "advice", "wisdom", "important", "key", "tip"
    ]
    sentences = re.split(r'(?<=[.!?])\s+', transcript)
    return [s.strip() for s in sentences if any(k in s.lower() for k in keywords)]
