from core.get_video import download_youtube_audio, transcribe_audio_to_text, cut_video_segments, connect_highlights_to_sentences, check_existing_transcript
from core.video_overlay import process_clips_with_background, verify_background_image, check_ffmpeg
from ai.generate_script import extract_reel_material_hf
from utils import retry_on_failure, time_operation, log_performance, ErrorHandler, validate_url
import config
import os
import time
import json
import logging
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
import argparse

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_FILE)
    ]
)
logger = logging.getLogger(__name__)


class InstagramReelProcessor:
    """Optimized Instagram Reel Creator with dictionary-based configurations."""
    
    # Configuration dictionary to replace if-else chains
    CONFIG = {
        'messages': {
            'welcome': {
                'header': "🎬 Instagram Reel Creator",
                'separator': "=" * 50,
                'description': "This tool will create Instagram reels from YouTube videos\nby extracting engaging clips and overlaying them on a background."
            },
            'errors': {
                'empty_url': "[!] Please enter a valid YouTube URL",
                'invalid_url': "[!] Please enter a valid YouTube URL (youtube.com or youtu.be)",
                'ffmpeg_missing': "[!] FFmpeg is required for video processing. Please install it first.",
                'background_missing': "[!] Please ensure the background image exists at: {}",
                'download_failed': "[!] Error downloading MP3.",
                'no_clips': "[!] No video clips were created to process with background.",
                'no_material': "[!] No reel material found. Try adjusting your prompt or check the transcript."
            },
            'success': {
                'system_ready': "[+] ✅ System ready! Background image: {}",
                'cached_files': "[+] Loading cached transcript and sentences...",
                'download_complete': "⏱️  Download completed in: {:.1f}s",
                'transcription_complete': "⏱️  Transcription completed in: {:.1f}s",
                'cutting_complete': "⏱️  Video cutting completed in: {:.1f}s total",
                'final_result': "[+] 🎉 Final result: {} Instagram reels ready!"
            }
        },
        'url_patterns': ['youtube.com/watch', 'youtu.be/'],
        'file_encoding': 'utf-8',
        'timing': {
            'cached_file_time': 0.1,
            'display_precision': 1
        }
    }
    
    def __init__(self, background_image_path: Optional[str] = None,
                 min_duration: Optional[int] = None,
                 max_duration: Optional[int] = None):
        self.output_dir = Path(config.OUTPUT_CLIPS_DIR)
        self.background_image_path = Path(background_image_path or config.BACKGROUND_IMAGE).resolve()
        self.min_duration = int(min_duration if min_duration is not None else config.CLIP_DURATION_MIN)
        self.max_duration = int(max_duration if max_duration is not None else config.CLIP_DURATION_MAX)
        self.start_time = time.time()
        self.timing_data: Dict[str, float] = {}
        self.error_handler = ErrorHandler()
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        Path(config.OUTPUT_REELS_DIR).mkdir(parents=True, exist_ok=True)
    
    def display_welcome(self) -> None:
        """Display welcome message using config."""
        welcome = self.CONFIG['messages']['welcome']
        print(welcome['header'])
        print(welcome['separator'])
        print(welcome['description'])
        print()
    
    def validate_url(self, url: str) -> bool:
        """Validate YouTube URL using dictionary config."""
        if not url:
            return False
        return validate_url(url) and any(pattern in url for pattern in self.CONFIG['url_patterns'])
    
    def get_youtube_url(self) -> str:
        """Get and validate YouTube URL with optimized error handling."""
        while True:
            url = input("🔗 Enter YouTube URL: ").strip()
            
            if not url:
                print(self.CONFIG['messages']['errors']['empty_url'])
                continue
            
            if not self.validate_url(url):
                print(self.CONFIG['messages']['errors']['invalid_url'])
                continue
            
            print(f"[+] Using URL: {url}")
            return url
    
    def check_system_requirements(self) -> bool:
        """Check system requirements with early exit pattern."""
        logger.info("Checking system requirements...")
        
        checks = [
            (check_ffmpeg, self.CONFIG['messages']['errors']['ffmpeg_missing']),
            (lambda: verify_background_image(str(self.background_image_path)), 
             self.CONFIG['messages']['errors']['background_missing'].format(self.background_image_path))
        ]
        
        for check_func, error_msg in checks:
            try:
                if not check_func():
                    logger.error(error_msg)
                    print(error_msg)
                    return False
            except Exception as e:
                logger.error(f"System check failed: {e}")
                print(f"[!] System check error: {e}")
                return False
        
        success_msg = self.CONFIG['messages']['success']['system_ready'].format(
            self.background_image_path.name)
        logger.info("System requirements check passed")
        print(success_msg)
        return True
    
    def load_cached_transcript(self, transcript_path: str, sentences_path: str) -> Tuple[str, List[Dict]]:
        """Load cached transcript files with optimized file handling."""
        logger.info("Loading cached transcript files")
        print(self.CONFIG['messages']['success']['cached_files'])
        
        try:
            with open(transcript_path, "r", encoding=self.CONFIG['file_encoding']) as f:
                transcript = f.read()
            with open(sentences_path, "r", encoding=self.CONFIG['file_encoding']) as f:
                sentences = json.load(f)
            
            # Set timing data for cached files
            cache_time = self.CONFIG['timing']['cached_file_time']
            self.timing_data.update({
                'download_time': cache_time,
                'transcription_time': cache_time
            })
            
            print(f"⏱️  Using cached files - no download/transcription needed: {cache_time * 2:.1f}s")
            logger.info(f"Loaded cached transcript: {len(transcript)} chars, {len(sentences)} sentences")
            return transcript, sentences
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Failed to load cached files: {e}")
            raise
    
    @time_operation("download_and_transcribe")
    def download_and_transcribe(self, url: str) -> Tuple[Optional[str], Optional[List[Dict]], Optional[str]]:
        """Download and transcribe audio with optimized timing."""
        logger.info(f"Starting download and transcription for URL: {url}")
        
        try:
            step_start = time.time()
            mp3_path, video_title = download_youtube_audio(url, cleanup=True)
            if not mp3_path or not video_title:
                logger.error("Failed to download video")
                print(self.CONFIG['messages']['errors']['download_failed'])
                self._display_total_time()
                return None, None, None
            
            logger.info(f"Downloaded video: {video_title}")
            print("Final MP3 saved at:", mp3_path)
            self.timing_data['download_time'] = time.time() - step_start
            print(self.CONFIG['messages']['success']['download_complete'].format(
                self.timing_data['download_time']))
            
            step_start = time.time()
            transcript, sentences = transcribe_audio_to_text(mp3_path)
            logger.info(f"Transcription completed: {len(transcript)} chars, {len(sentences)} sentences")
            
            # Clean up audio file
            self._safe_file_remove(mp3_path, "audio file")
            
            self.timing_data['transcription_time'] = time.time() - step_start
            print(self.CONFIG['messages']['success']['transcription_complete'].format(
                self.timing_data['transcription_time']))
            
            return transcript, sentences, video_title
        except Exception as e:
            logger.error(f"Download and transcription failed: {e}")
            print(f"[!] Error during download/transcription: {e}")
            return None, None, None
    
    def get_transcript_data(self, url: str) -> Tuple[Optional[str], Optional[List[Dict]], Optional[str]]:
        """Get transcript data using cached files or download/transcribe."""
        transcript_path, sentences_path, video_title = check_existing_transcript(url)
        
        if all([transcript_path, sentences_path, video_title]):
            transcript, sentences = self.load_cached_transcript(transcript_path, sentences_path)
            return transcript, sentences, video_title
        
        return self.download_and_transcribe(url)
    
    @time_operation("process_highlights")
    def process_highlights(self, sentences: List[Dict]) -> List[Dict]:
        """Process highlights with optimized timestamp handling."""
        highlights = extract_reel_material_hf(sentences)
        
        if not highlights:
            return []
        
        # Use dictionary-based logic instead of if-else
        highlight_processors = {
            'has_timestamps': lambda h: h if isinstance(h[0], dict) and 'start_time' in h[0] else None,
            'needs_connection': lambda h: connect_highlights_to_sentences(sentences, h)
        }
        
        # Determine processing method
        has_timestamps = (highlights and isinstance(highlights[0], dict) and 'start_time' in highlights[0])
        processor_key = 'has_timestamps' if has_timestamps else 'needs_connection'
        
        processed = highlight_processors[processor_key](highlights) or highlights
        return processed

    def filter_highlights_by_duration(self, highlights_with_times: List[Dict]) -> List[Dict]:
        """Filter highlights to be within configured duration bounds."""
        filtered: List[Dict] = []
        for h in highlights_with_times:
            start = h.get('start_time') if 'start_time' in h else h.get('start')
            end = h.get('end_time') if 'end_time' in h else h.get('end')
            duration = h.get('duration')
            if duration is None and start is not None and end is not None:
                duration = float(end) - float(start)
            if duration is None:
                continue
            if self.min_duration <= float(duration) <= self.max_duration:
                filtered.append(h)
        return filtered
    
    def display_highlights(self, highlights_with_times: List[Dict]) -> None:
        """Display highlights with optimized formatting."""
        print("[+] Extracted reel material:")
        
        for h in highlights_with_times:
            if h.get("start_time") is not None:
                duration = h.get("duration", h.get("end_time", 0) - h.get("start_time", 0))
                hook = h.get("hook", "")
                
                print(f"- [{h['start_time']:.1f}s - {h.get('end_time', 0):.1f}s] "
                      f"({duration:.1f}s): {h['text'][:100]}...")
                
                if hook:
                    print(f"  💡 Hook: {hook}")
            else:
                print(f"- [timestamp not found]: {h.get('text', str(h))[:100]}...")
    
    @time_operation("create_video_segments")
    def create_video_segments(self, url: str, highlights_with_times: List[Dict]) -> List[str]:
        """Create video segments with timing."""
        print("[+] Cutting video segments...")
        step_start = time.time()
        cut_files = cut_video_segments(url, highlights_with_times, output_dir=self.output_dir)
        print(f"[+] Created {len(cut_files)} video clips in {self.output_dir}")
        
        self.timing_data['cutting_time'] = time.time() - step_start
        print(self.CONFIG['messages']['success']['cutting_complete'].format(
            self.timing_data['cutting_time']))
        
        return cut_files
    
    @time_operation("create_instagram_reels")
    def create_instagram_reels(self, cut_files: List[str], video_title: str) -> List[str]:
        """Create Instagram reels and clean up intermediate files."""
        if not cut_files:
            print(self.CONFIG['messages']['errors']['no_clips'])
            return []
        
        step_start = time.time()
        instagram_reels = process_clips_with_background(
            clip_files=cut_files,
            background_image_path=self.background_image_path,
            output_dir=config.OUTPUT_REELS_DIR,
            video_title=video_title
        )
        self.timing_data['overlay_time'] = time.time() - step_start
        
        # Clean up clip files
        self._cleanup_files(cut_files, "clip")
        
        return instagram_reels
    
    def display_final_results(self, instagram_reels: List[str]) -> None:
        """Display final results with performance metrics."""
        if not instagram_reels:
            return
        
        print(self.CONFIG['messages']['success']['final_result'].format(len(instagram_reels)))
        for reel in instagram_reels:
            print(f"   📱 {os.path.basename(reel)}")
        
        self._display_performance_summary(instagram_reels)
    
    def _cleanup_files(self, files: List[str], file_type: str) -> None:
        """Generic file cleanup with error handling."""
        logger.info(f"Cleaning up {len(files)} {file_type} files...")
        print(f"[+] Cleaning up {file_type} files...")
        
        for file_path in files:
            self._safe_file_remove(file_path, file_type)
    
    def _safe_file_remove(self, file_path: str, file_type: str) -> None:
        """Safely remove a file with error handling."""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.info(f"Deleted {file_type}: {path.name}")
                print(f"[+] Deleted {file_type}: {path.name}")
            else:
                logger.warning(f"File not found for deletion: {file_path}")
        except Exception as e:
            logger.error(f"Could not delete {file_type} {Path(file_path).name}: {e}")
            print(f"[!] Could not delete {file_type} {Path(file_path).name}: {e}")
    
    def _format_time(self, seconds: float) -> Tuple[int, int]:
        """Format time into minutes and seconds."""
        return int(seconds // 60), int(seconds % 60)
    
    def _display_total_time(self) -> None:
        """Display total processing time."""
        total_time = time.time() - self.start_time
        minutes, seconds = self._format_time(total_time)
        print(f"⏱️  Total processing time: {minutes}m {seconds}s")
    
    def _display_performance_summary(self, instagram_reels: List[str]) -> None:
        """Display comprehensive performance summary."""
        total_time = time.time() - self.start_time
        minutes, seconds = self._format_time(total_time)
        
        download_time = self.timing_data.get('download_time', 0)
        transcription_time = self.timing_data.get('transcription_time', 0)
        cutting_time = self.timing_data.get('cutting_time', 0)
        overlay_time = self.timing_data.get('overlay_time', 0)
        
        print(f"\n🎯 PROCESSING COMPLETE!")
        print("=" * 50)
        print(f"⏱️  Total processing time: {minutes}m {seconds}s ({total_time:.1f}s)")
        print(f"📊 Performance:")
        print(f"   • Download: {download_time:.1f}s")
        print(f"   • Transcription: {transcription_time:.1f}s")
        print(f"   • Cutting: {cutting_time:.1f}s")
        if overlay_time:
            print(f"   • Overlay: {overlay_time:.1f}s")
        print(f"🎬 Final output: {len(instagram_reels)} high-quality Instagram reels!")
    
    @log_performance
    def run(self, url: Optional[str] = None) -> None:
        """Main execution method with optimized flow and error handling."""
        try:
            # Display welcome message
            self.display_welcome()
            
            # Get and validate URL
            url = url or self.get_youtube_url()
            print()
            
            # Check system requirements
            if not self.check_system_requirements():
                logger.error("System requirements check failed")
                exit(1)
            
            # Get transcript data
            transcript, sentences, video_title = self.get_transcript_data(url)
            if not all([transcript, sentences, video_title]):
                logger.error("Failed to get transcript data")
                exit(1)
            
            # Display transcript info
            print(f"[+] Transcript length: {len(transcript)} characters")
            print("[+] Transcript sample:", transcript[:300], "...")
            
            # Process highlights
            highlights_with_times = self.process_highlights(sentences)
            # Filter highlights by configured duration
            highlights_with_times = self.filter_highlights_by_duration(highlights_with_times)
            
            if not highlights_with_times:
                logger.warning("No highlights found")
                print(self.CONFIG['messages']['errors']['no_material'])
                return
            
            # Display highlights
            self.display_highlights(highlights_with_times)
            
            # Create video segments
            cut_files = self.create_video_segments(url, highlights_with_times)
            
            # Create Instagram reels
            instagram_reels = self.create_instagram_reels(cut_files, video_title)
            
            # Display final results
            self.display_final_results(instagram_reels)
            
            # Display error summary if any
            if self.error_handler.error_count > 0:
                print(f"\n⚠️  {self.error_handler.get_error_summary()}")
                
        except KeyboardInterrupt:
            logger.info("Process interrupted by user")
            print("\n[!] Process interrupted by user")
        except Exception as e:
            logger.error(f"Unexpected error in main process: {e}")
            self.error_handler.handle_error(e, "main process", critical=True)
            print(f"[!] Unexpected error: {e}")
            print(f"[!] {self.error_handler.get_error_summary()}")


def main():
    """Entry point for the Instagram Reel Creator."""
    parser = argparse.ArgumentParser(description="Instagram Reel Creator")
    parser.add_argument("--url", help="YouTube URL to process", default=None)
    parser.add_argument("--background", help="Path to background image", default=None)
    parser.add_argument("--min-duration", type=int, help="Minimum clip duration (seconds)", default=None)
    parser.add_argument("--max-duration", type=int, help="Maximum clip duration (seconds)", default=None)
    args = parser.parse_args()

    processor = InstagramReelProcessor(
        background_image_path=args.background,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
    )
    processor.run(url=args.url)


if __name__ == "__main__":
    main()