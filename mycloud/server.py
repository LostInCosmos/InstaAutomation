import os
import json
import shutil
import email
import email.policy
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage")
STATIC_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

os.makedirs(STORAGE_DIR, exist_ok=True)


class CloudHandler(SimpleHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/api/files":
            query    = parse_qs(parsed.query)
            rel_path = unquote(query.get("path", ["/"])[0]).lstrip("/")
            abs_path = os.path.join(STORAGE_DIR, rel_path)

            # Path traversal guard
            if not os.path.abspath(abs_path).startswith(os.path.abspath(STORAGE_DIR)):
                self._json({"error": "Forbidden"}, 403)
                return

            if not os.path.isdir(abs_path):
                self._json({"error": "Not a directory"}, 404)
                return

            items = []
            for name in sorted(os.listdir(abs_path)):
                full = os.path.join(abs_path, name)
                items.append({
                    "name":     name,
                    "type":     "folder" if os.path.isdir(full) else "file",
                    "size":     os.path.getsize(full) if os.path.isfile(full) else None,
                    "modified": int(os.path.getmtime(full)),
                })
            self._json(items)
            return

        if path == "/api/download":
            query    = parse_qs(parsed.query)
            rel_path = unquote(query.get("path", [""])[0]).lstrip("/")
            abs_path = os.path.join(STORAGE_DIR, rel_path)

            # Path traversal guard
            if not os.path.abspath(abs_path).startswith(os.path.abspath(STORAGE_DIR)):
                self._json({"error": "Forbidden"}, 403)
                return

            if not os.path.isfile(abs_path):
                self._json({"error": "File not found"}, 404)
                return

            self.send_response(200)
            self.send_header("Content-Disposition",
                             f'attachment; filename="{os.path.basename(abs_path)}"')
            self.send_header("Content-Length", str(os.path.getsize(abs_path)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with open(abs_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        if path == "/" or path == "":
            path = "/index.html"

        file_path = os.path.join(STATIC_DIR, path.lstrip("/"))
        if os.path.isfile(file_path):
            self._serve_file(file_path)
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/api/upload":
            query    = parse_qs(parsed.query)
            rel_dir  = unquote(query.get("path", ["/"])[0]).lstrip("/")
            abs_dir  = os.path.join(STORAGE_DIR, rel_dir)

            # Path traversal guard
            if not os.path.abspath(abs_dir).startswith(os.path.abspath(STORAGE_DIR)):
                self._json({"error": "Forbidden"}, 403)
                return

            os.makedirs(abs_dir, exist_ok=True)

            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._json({"error": "Expected multipart/form-data"}, 400)
                return

            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)

            # Parse multipart using the email stdlib (replaces deprecated cgi module)
            mime_msg = email.message_from_bytes(
                f"Content-Type: {content_type}\r\n\r\n".encode() + raw_body,
                policy=email.policy.compat32,
            )

            saved = []
            for part in mime_msg.get_payload():
                disp = part.get("Content-Disposition", "")
                if 'name="file"' not in disp:
                    continue
                # Extract filename from Content-Disposition header
                filename = None
                for segment in disp.split(";"):
                    segment = segment.strip()
                    if segment.startswith("filename="):
                        filename = segment[9:].strip().strip('"')
                        break
                if not filename:
                    continue
                safe_name = os.path.basename(filename)
                if not safe_name:
                    continue
                dest = os.path.join(abs_dir, safe_name)
                with open(dest, "wb") as f:
                    payload = part.get_payload(decode=True)
                    if payload is not None:
                        f.write(payload)
                saved.append(safe_name)

            self._json({"uploaded": saved})
            return

        if path == "/api/mkdir":
            content_length = int(self.headers.get("Content-Length", 0))
            body     = json.loads(self.rfile.read(content_length))
            rel_path = body.get("path", "").lstrip("/")
            abs_path = os.path.join(STORAGE_DIR, rel_path)

            # Path traversal guard
            if not os.path.abspath(abs_path).startswith(os.path.abspath(STORAGE_DIR)):
                self._json({"error": "Forbidden"}, 403)
                return

            os.makedirs(abs_path, exist_ok=True)
            self._json({"created": rel_path})
            return

        self._json({"error": "Not found"}, 404)

    def do_DELETE(self):
        parsed   = urlparse(self.path)
        query    = parse_qs(parsed.query)
        rel_path = unquote(query.get("path", [""])[0]).lstrip("/")
        abs_path = os.path.join(STORAGE_DIR, rel_path)

        # Path traversal guard
        if not os.path.abspath(abs_path).startswith(os.path.abspath(STORAGE_DIR)):
            self._json({"error": "Forbidden"}, 403)
            return

        # Prevent deleting storage root
        if os.path.abspath(abs_path) == os.path.abspath(STORAGE_DIR):
            self._json({"error": "Cannot delete storage root"}, 400)
            return

        if os.path.isfile(abs_path):
            os.remove(abs_path)
            self._json({"deleted": rel_path})
        elif os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
            self._json({"deleted": rel_path})
        else:
            self._json({"error": "Not found"}, 404)

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path):
        ext_map = {
            ".html": "text/html",
            ".js":   "application/javascript",
            ".css":  "text/css",
        }
        ext  = os.path.splitext(path)[1]
        mime = ext_map.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")


if __name__ == "__main__":
    PORT   = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", PORT), CloudHandler)
    print(f"✅ MyCloud running at http://localhost:{PORT}")
    print(f"📁 Serving files from: {STORAGE_DIR}")
    print(f"   Run: cloudflared tunnel --url http://localhost:{PORT}")
    server.serve_forever()
