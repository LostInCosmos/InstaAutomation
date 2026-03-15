# MyCloud — Personal Cloud Storage

A self-hosted personal cloud storage prototype (like Google Drive) built with a **pure Python stdlib backend** and **vanilla JavaScript frontend**, accessible from anywhere via [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/).

---

## Architecture

```
YOUR HDD/Device
      │
 Python Server  ←── reads/writes files on your disk
      │  (runs on localhost:8000)
      │
 cloudflared    ←── free tunnel, no port forwarding needed
      │
  Internet
      │
 Your Browser   ←── open from anywhere
```

---

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/LostInCosmos/InstaAutomation.git
   cd InstaAutomation/mycloud
   ```

2. **Start the server** (Python 3.8+ required — no pip packages needed)
   ```bash
   python server.py
   ```

3. **Expose it to the internet** with Cloudflare Tunnel
   ```bash
   # Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/
   cloudflared tunnel --url http://localhost:8000
   ```

4. **Open the generated `*.trycloudflare.com` URL** in any browser — from anywhere in the world.

---

## Pointing Storage to a Real HDD

By default files are stored in `mycloud/storage/`. To use a different drive or directory, change `STORAGE_DIR` in `server.py`:

```python
# server.py — line 6
STORAGE_DIR = "/mnt/my-hdd"          # Linux / macOS external drive
# STORAGE_DIR = "D:\\MyCloudStorage"  # Windows
```

---

## API Reference

| Method   | Endpoint                       | Description                                  |
|----------|--------------------------------|----------------------------------------------|
| `GET`    | `/api/files?path=/`            | List files and folders at the given path     |
| `GET`    | `/api/download?path=/file.txt` | Download a file                              |
| `POST`   | `/api/upload?path=/`           | Upload files (`multipart/form-data`)         |
| `POST`   | `/api/mkdir`                   | Create a new folder (`{"path": "/newfolder"}`)|
| `DELETE` | `/api/files?path=/file.txt`    | Delete a file or folder                      |

---

## Features

- ⬆ **Upload** files via button or drag-and-drop
- ⬇ **Download** any file with one click
- 🗑 **Delete** files and folders
- 📁 **Create folders** anywhere in the tree
- 🔍 **Search** files by name (client-side, instant)
- ⊞ **Grid / ☰ List** view toggle
- 🧭 **Breadcrumb** navigation for deep folders
- 📊 **Storage bar** showing disk usage
- 🌙 **Dark theme** — easy on the eyes

---

## Tech Stack

| Layer     | Technology                        |
|-----------|-----------------------------------|
| Backend   | Python 3.8+ stdlib (`http.server`, `cgi`, `json`, `shutil`) |
| Frontend  | Vanilla JavaScript (ES2017+), no frameworks |
| Styling   | Plain CSS, dark theme             |
| Tunnel    | Cloudflare Tunnel (`cloudflared`) |

---

## Project Structure

```
mycloud/
├── server.py          # Python HTTP server (stdlib only)
├── storage/           # All uploaded files live here
│   └── .gitkeep
├── static/
│   ├── index.html     # UI shell
│   ├── app.js         # Frontend logic
│   └── style.css      # Dark theme
├── requirements.txt   # No dependencies!
└── README.md
```
