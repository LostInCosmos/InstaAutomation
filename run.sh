#!/usr/bin/env bash
# Run the Instagram Reel Creator.
#
# Usage:
#   ./run.sh          # start the web UI at http://127.0.0.1:5000 (default)
#   ./run.sh web      # same as above
#   ./run.sh cli      # run the interactive terminal version instead

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[!] FFmpeg not found. Install it first:"
    echo "    Ubuntu/Debian: sudo apt install ffmpeg"
    echo "    MacOS:         brew install ffmpeg"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[+] Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "[+] Checking dependencies..."
pip install -q -r requirements.txt

if [ ! -f ".env" ]; then
    echo "[!] No .env file found. Create one with:"
    echo "    GROQ_API_KEY=your_groq_api_key_here"
    exit 1
fi

MODE="${1:-web}"

cd app
case "$MODE" in
    web)
        exec python server.py
        ;;
    cli)
        exec python main.py
        ;;
    *)
        echo "Usage: $0 [web|cli]"
        exit 1
        ;;
esac
