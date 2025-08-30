# InstaAutomation 🎬📱

An AI-powered tool that automatically creates Instagram reels from YouTube videos by extracting the most engaging clips and overlaying them on custom backgrounds.

## Features ✨

- 🎵 **YouTube Audio Download**: Downloads high-quality audio from YouTube videos
- 🎯 **AI-Powered Clip Extraction**: Uses advanced AI to identify the most engaging 40-60 second clips
- ✂️ **Smart Video Segmentation**: Automatically cuts video segments with precise timestamps  
- 🎨 **Background Overlay**: Overlays video clips onto custom background images for Instagram reel format
- 📱 **Instagram Ready**: Outputs videos in perfect 9:16 aspect ratio for Instagram reels
- 🤖 **Multiple AI Models**: Supports various Hugging Face models for content analysis

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

4. **Set up Hugging Face API token**:
   ```bash
   export HUGGINGFACE_API_TOKEN="your_token_here"
   # or
   export HF_TOKEN="your_token_here"
   ```

## Usage 🎯

### Quick Start with Demo

```bash
cd app
python demo.py "https://www.youtube.com/watch?v=YOUR_VIDEO_ID"
```

### Manual Usage

```bash
cd app
python main.py
```

### Custom Background

Place your custom background image in `assets/background/` and update the path in the code.

## How It Works 🔄

1. **Video Analysis**: Downloads YouTube video and extracts audio
2. **Transcription**: Uses OpenAI Whisper to create timestamped transcript
3. **AI Processing**: Analyzes content to identify engaging clips (jokes, insights, stories)
4. **Video Cutting**: Extracts precise video segments based on AI recommendations
5. **Background Overlay**: Overlays clips onto background image in Instagram reel format
6. **Output**: Generates ready-to-upload Instagram reels

## Output Structure 📁

```
downloads/
├── reels/              # Original extracted clips
└── instagram_reels/    # Final Instagram reels with background overlay
```

## Customization 🛠️

- **Background Images**: Place custom backgrounds in `assets/background/`
- **AI Models**: Modify the model parameter in `generate_script.py`
- **Video Quality**: Adjust FFmpeg parameters in `video_overlay.py`
- **Clip Duration**: Modify the 40-60 second requirement in the AI prompt

## Requirements 📋

- Python 3.8+
- FFmpeg
- Hugging Face API token
- Sufficient disk space for video processing

## Troubleshooting 🔧

- **FFmpeg not found**: Install FFmpeg and ensure it's in your system PATH
- **API errors**: Check your Hugging Face token and internet connection
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
