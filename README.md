# InstaAutomation 🎬📱

An AI-powered tool that automatically creates Instagram reels from YouTube videos by extracting the most engaging clips and overlaying them on custom backgrounds.

## Features ✨

- 🎵 **Parallel Downloads**: Audio and source video download concurrently, not sequentially
- 🎯 **AI-Powered Clip Extraction**: Uses Groq's `gpt-oss-120b` to identify the most engaging 40-60 second clips
- 📼 **Long-Video Support**: Multi-hour podcasts are automatically chunked (transcription + clip-selection) to work within Groq's free-tier rate limits
- ✂️ **Smart Video Segmentation**: Automatically cuts video segments with precise timestamps
- 🎨 **Background Overlay**: Overlays video clips onto custom background images for Instagram reel format
- 📱 **Instagram Ready**: Outputs videos in perfect 9:16 aspect ratio for Instagram reels
- 💾 **Result Caching**: A fully-processed video's transcript + selected clips are cached, so re-runs skip straight to cutting

## Installation 🚀

1. **Clone the repository**:
   ```bash
   git clone https://github.com/LostInCosmos/InstaAutomation.git
   cd InstaAutomation
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install FFmpeg** (required for video processing):
   - **Ubuntu/Debian**: `sudo apt install ffmpeg`
   - **MacOS**: `brew install ffmpeg` 
   - **Windows**: Download from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)

4. **Set up Groq API key** (used for both transcription and AI clip selection):
   ```bash
   export GROQ_API_KEY="your_groq_api_key_here"
   ```
   Get a free key at [console.groq.com](https://console.groq.com).

## Usage 🎯

```bash
cd app
python main.py
```

The tool will prompt you for a YouTube URL interactively.

### Custom Background

Place your custom background image in `assets/background/` and set its path in `app/config.py` (`BACKGROUND_IMAGE`).

## How It Works 🔄

1. **Video lookup**: Title/duration are fetched once (no download).
2. **Parallel downloads**: The (larger, slower) source video starts downloading in the background immediately, while:
3. **Audio pipeline runs concurrently**: audio is downloaded, split into overlapping ~15 min chunks (needed for Groq Whisper's 25MB-per-request limit on long videos/podcasts), and each chunk is transcribed (Groq Whisper `large-v3`) then sent to Groq's `gpt-oss-120b` for clip selection. Calls to the clip-selection model are paced ~60s apart to stay under Groq's free-tier rate limit; while waiting, the *next* chunk is already being transcribed in the background so no time is wasted.
4. **Dedup**: Clips found in the overlapping region between adjacent chunks are merged, keeping the better version.
5. **Video cutting**: Once the source video (from step 2) and the selected clips (from step 4) are both ready, clips are cut out with FFmpeg.
6. **Background overlay**: Clips are overlaid onto the background image in Instagram reel format (1080x1920, 9:16).
7. **Caching**: The transcript, sentences, and selected clips are saved to `downloads/`, so re-running on the same video skips straight to cutting.

This means a short video (under ~15 min) is processed with a single transcription + clip-selection call, while a multi-hour podcast is automatically split into several chunks and pipelined - see `app/core/pipeline.py`.

## Output Structure 📁

```
downloads/
├── reels/              # Original extracted clips
└── instagram_reels/    # Final Instagram reels with background overlay
```

## Customization 🛠️

- **Background Images**: Place custom backgrounds in `assets/background/`
- **AI Model**: Change `DEFAULT_AI_MODEL` in `app/config.py`
- **Video Quality**: Adjust `VIDEO_QUALITY`/`FFMPEG_PRESET` in `app/config.py`
- **Clip Duration**: Adjust `CLIP_DURATION_MIN`/`CLIP_DURATION_MAX` in `app/config.py`
- **Chunk size/pacing** (for long videos): `CHUNK_DURATION_SECONDS`, `CHUNK_OVERLAP_SECONDS`, `AI_CHUNK_DELAY_SECONDS` in `app/config.py`

## Requirements 📋

- Python 3.8+
- FFmpeg
- Groq API key
- Sufficient disk space for video processing

## Troubleshooting 🔧

- **FFmpeg not found**: Install FFmpeg and ensure it's in your system PATH
- **API errors**: Check your Groq API key and internet connection
- **Video download fails**: Try updating yt-dlp: `pip install -U yt-dlp`
- **Background image not found**: Ensure the image exists in `assets/background/`

## Contributing 🤝

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License 📄

This project is open source and available under the [MIT License](LICENSE).

---

**Made with ❤️ for content creators who want to automate their Instagram reel workflow!**
