#!/usr/bin/env python3
"""
Simple test script to verify the Instagram reel creation functionality.
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from core.video_overlay import verify_background_image, check_ffmpeg
import config

def test_system_requirements():
    """Test if all system requirements are met."""
    print("🧪 Testing System Requirements...")
    print("-" * 40)
    
    # Test 1: FFmpeg
    print("1. Testing FFmpeg installation...")
    if check_ffmpeg():
        print("   ✅ FFmpeg is available")
    else:
        print("   ❌ FFmpeg not found")
        return False
    
    # Test 2: Background image
    print("2. Testing background image...")
    bg_path = os.path.abspath(config.BACKGROUND_IMAGE)
    print(f"   Looking for: {bg_path}")
    
    if verify_background_image(bg_path):
        print("   ✅ Background image is valid")
    else:
        print("   ❌ Background image not found or invalid")
        return False
    
    # Test 3: Output directories
    print("3. Testing output directories...")
    clips_dir = os.path.abspath(config.OUTPUT_CLIPS_DIR)
    reels_dir = os.path.abspath(config.OUTPUT_REELS_DIR)
    
    try:
        os.makedirs(clips_dir, exist_ok=True)
        os.makedirs(reels_dir, exist_ok=True)
        print(f"   ✅ Clips directory: {clips_dir}")
        print(f"   ✅ Reels directory: {reels_dir}")
    except Exception as e:
        print(f"   ❌ Cannot create output directories: {e}")
        return False
    
    # Test 4: Python packages
    print("4. Testing Python packages...")
    required_packages = ['PIL']
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} not found")
            return False
    
    print("\n🎉 All system requirements are met!")
    print("You're ready to create Instagram reels!")
    return True

def show_configuration():
    """Display current configuration settings."""
    print("\n⚙️  Current Configuration:")
    print("-" * 40)
    print(f"Video Resolution: {config.TARGET_WIDTH}x{config.TARGET_HEIGHT}")
    print(f"Video Scale Factor: {config.VIDEO_SCALE_FACTOR}")
    print(f"Video Quality (CRF): {config.VIDEO_QUALITY}")
    print(f"Audio Bitrate: {config.AUDIO_BITRATE}")
    print(f"AI Model: {config.DEFAULT_AI_MODEL}")
    print(f"Clip Duration: {config.CLIP_DURATION_MIN}-{config.CLIP_DURATION_MAX}s")
    print(f"FFmpeg Preset: {config.FFMPEG_PRESET}")

def main():
    """Run the test suite."""
    print("🚀 Instagram Reel Automation - System Test")
    print("=" * 50)
    
    # Test system requirements
    if test_system_requirements():
        show_configuration()
        print("\n✅ System test passed! You can now run:")
        print("   python main.py")
    else:
        print("\n❌ System test failed. Please fix the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
