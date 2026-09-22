"""Local web UI for the Instagram Reel Creator.

Serves a single HTML page (app/web/index.html) that:
  - takes a YouTube link and submits it to /api/process, which runs the
    pipeline (core.pipeline.process_video) in a background thread - this
    can take minutes to hours (long podcasts get chunked, see pipeline.py),
    so it's fire-and-forget with the page polling /api/status for progress
  - browses the local output library via /api/library, which lists each
    video's folder under downloads/instagram_reels/<title>/ and its clips
  - serves clip video files for in-browser preview via /clips/<path>

This is a single-user, one-job-at-a-time local tool, not a multi-tenant
server - state is a single in-memory dict, no database.
"""
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, abort

import config
from core.pipeline import process_video
from core.video_overlay import check_ffmpeg, verify_background_image

app = Flask(__name__, static_folder=None)

_job_lock = threading.Lock()
_job = {"state": "idle", "message": "", "reels": [], "title": None, "error": None}


def _run_job(url: str) -> None:
    def on_progress(message: str) -> None:
        with _job_lock:
            _job["message"] = message

    try:
        result = process_video(url, progress_callback=on_progress)
        with _job_lock:
            _job["state"] = "done"
            _job["reels"] = result.get("reels", [])
            _job["title"] = result.get("title")
            _job["message"] = (
                f"Done - {len(_job['reels'])} reels ready" if _job["reels"] else "Finished, but no reels were produced"
            )
    except Exception as e:
        with _job_lock:
            _job["state"] = "error"
            _job["error"] = str(e)
            _job["message"] = f"Failed: {e}"


@app.route("/")
def index():
    return send_from_directory(Path(__file__).parent / "web", "index.html")


@app.route("/api/process", methods=["POST"])
def api_process():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url or not any(p in url for p in ("youtube.com/watch", "youtu.be/")):
        return jsonify({"error": "Please provide a valid YouTube URL"}), 400

    with _job_lock:
        if _job["state"] == "running":
            return jsonify({"error": "A video is already processing"}), 409
        _job.update(state="running", message="Starting...", reels=[], title=None, error=None)

    threading.Thread(target=_run_job, args=(url,), daemon=True).start()
    return jsonify({"started": True})


@app.route("/api/status")
def api_status():
    with _job_lock:
        return jsonify(dict(_job))


@app.route("/api/library")
def api_library():
    """List every processed video's folder and the clips inside it."""
    reels_dir = Path(config.OUTPUT_REELS_DIR)
    videos = []
    if reels_dir.exists():
        for folder in sorted(reels_dir.iterdir(), reverse=True):
            if not folder.is_dir():
                continue
            clips = sorted(f.name for f in folder.iterdir() if f.suffix == ".mp4")
            if clips:
                videos.append({"title": folder.name, "clips": clips})
    return jsonify({"videos": videos})


@app.route("/clips/<path:filepath>")
def serve_clip(filepath):
    """Serve a clip file for in-browser preview/download. filepath is
    '<video_title>/<clip_filename>.mp4', scoped strictly under OUTPUT_REELS_DIR."""
    reels_dir = Path(config.OUTPUT_REELS_DIR).resolve()
    full_path = (reels_dir / filepath).resolve()

    try:
        full_path.relative_to(reels_dir)
    except ValueError:
        abort(403)
    if not full_path.is_file():
        abort(404)

    return send_from_directory(full_path.parent, full_path.name)


def main() -> None:
    if not check_ffmpeg():
        print("[!] FFmpeg is required for video processing. Please install it first.")
        return
    background_path = os.path.abspath(config.BACKGROUND_IMAGE)
    if not verify_background_image(background_path):
        print(f"[!] Please ensure the background image exists at: {background_path}")
        return

    print("🎬 Instagram Reel Creator - web UI")
    print("=" * 50)
    print("Open http://127.0.0.1:5000 in your browser")
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
