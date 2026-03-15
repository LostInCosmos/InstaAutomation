let currentPath  = "/";
let allFiles     = [];
let pendingFiles = [];
let currentView  = "grid";

const STORAGE_LIMIT_BYTES = 500 * 1024 ** 3; // 500 GB

window.addEventListener("DOMContentLoaded", () => {
  loadFiles("/");

  // Sidebar buttons
  document.getElementById("btnUpload").addEventListener("click", openUpload);
  document.getElementById("btnNewFolder").addEventListener("click", createFolder);

  // Topbar
  document.getElementById("searchInput").addEventListener("input", (e) => filterFiles(e.target.value));
  document.getElementById("btnGrid").addEventListener("click", () => setView("grid"));
  document.getElementById("btnList").addEventListener("click", () => setView("list"));

  // Upload modal
  document.getElementById("btnCloseModal").addEventListener("click", closeUpload);
  document.getElementById("btnCancel").addEventListener("click", closeUpload);
  document.getElementById("btnUploadSubmit").addEventListener("click", uploadFiles);

  // Dropzone
  const dropzone  = document.getElementById("dropzone");
  const fileInput = document.getElementById("fileInput");
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("drag"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag"));
  dropzone.addEventListener("drop", handleDrop);
  fileInput.addEventListener("change", () => handleFiles(fileInput.files));
});

async function loadFiles(path) {
  currentPath = path;
  updateBreadcrumb(path);
  document.getElementById("loadingMsg").style.display = "block";
  document.getElementById("fileGrid").innerHTML = "";
  try {
    const res = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
    allFiles  = await res.json();
    renderFiles(allFiles);
  } catch (e) {
    document.getElementById("loadingMsg").textContent = "❌ Could not connect to server.";
  }
  document.getElementById("loadingMsg").style.display = "none";
  updateStorage();
}

function renderFiles(files) {
  const grid = document.getElementById("fileGrid");
  grid.className = currentView === "grid" ? "file-grid" : "file-list";
  grid.innerHTML = "";

  if (!files.length) {
    grid.innerHTML = `<div class="empty">📭 This folder is empty</div>`;
    return;
  }

  const sorted = [...files].sort((a, b) => {
    if (a.type === b.type) return a.name.localeCompare(b.name);
    return a.type === "folder" ? -1 : 1;
  });

  sorted.forEach(file => {
    const card     = document.createElement("div");
    card.className = "file-card";
    const icon     = getIcon(file);
    const sizeText = file.type === "folder" ? "Folder" : formatSize(file.size);
    const date     = new Date(file.modified * 1000).toLocaleDateString();
    const filePath = joinPath(currentPath, file.name);

    if (currentView === "grid") {
      card.innerHTML = `
        <div class="card-icon">${icon}</div>
        <div class="card-name" title="${escapeAttr(file.name)}">${escapeHtml(file.name)}</div>
        <div class="card-meta">${sizeText} · ${date}</div>
        <div class="card-actions">
          ${file.type === "file" ? `<button class="action-btn" data-action="download" data-path="${escapeAttr(filePath)}" title="Download">⬇</button>` : ""}
          <button class="action-btn" data-action="delete" data-path="${escapeAttr(filePath)}" title="Delete">🗑</button>
        </div>`;
    } else {
      card.innerHTML = `
        <span class="list-icon">${icon}</span>
        <span class="list-name">${escapeHtml(file.name)}</span>
        <span class="list-size">${sizeText}</span>
        <span class="list-date">${date}</span>
        <span class="list-actions">
          ${file.type === "file" ? `<button class="action-btn" data-action="download" data-path="${escapeAttr(filePath)}" title="Download">⬇</button>` : ""}
          <button class="action-btn" data-action="delete" data-path="${escapeAttr(filePath)}" title="Delete">🗑</button>
        </span>`;
    }

    // Delegate button actions via data attributes (avoids inline JS injection)
    card.addEventListener("click", (e) => {
      const btn = e.target.closest(".action-btn");
      if (btn) {
        const action = btn.dataset.action;
        const p      = btn.dataset.path;
        if (action === "download") downloadFile(p);
        if (action === "delete")   deleteItem(p);
        return;
      }
      if (file.type === "folder") {
        loadFiles(joinPath(currentPath, file.name));
      }
    });

    if (file.type === "folder") card.style.cursor = "pointer";

    grid.appendChild(card);
  });
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeAttr(str) {
  return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function updateBreadcrumb(path) {
  const bc    = document.getElementById("breadcrumb");
  bc.innerHTML = "";

  const root = document.createElement("span");
  root.className = "bc-item";
  root.textContent = "My Drive";
  root.addEventListener("click", () => loadFiles("/"));
  bc.appendChild(root);

  const parts = path.split("/").filter(Boolean);
  let built   = "";
  parts.forEach(p => {
    built += "/" + p;
    const sep = document.createElement("span");
    sep.className = "bc-sep";
    sep.textContent = " / ";
    bc.appendChild(sep);

    const snap = built;
    const item = document.createElement("span");
    item.className = "bc-item";
    item.textContent = p;
    item.addEventListener("click", () => loadFiles(snap));
    bc.appendChild(item);
  });
}

function filterFiles(query) {
  const filtered = allFiles.filter(f => f.name.toLowerCase().includes(query.toLowerCase()));
  renderFiles(filtered);
}

function setView(v) {
  currentView = v;
  document.getElementById("btnGrid").classList.toggle("active", v === "grid");
  document.getElementById("btnList").classList.toggle("active", v === "list");
  renderFiles(allFiles);
}

function openUpload()  { document.getElementById("uploadModal").classList.add("open"); }
function closeUpload() {
  document.getElementById("uploadModal").classList.remove("open");
  pendingFiles = [];
  document.getElementById("uploadList").innerHTML = "";
  document.getElementById("fileInput").value = "";
}

function handleDrop(e) {
  e.preventDefault();
  document.getElementById("dropzone").classList.remove("drag");
  handleFiles(e.dataTransfer.files);
}

function handleFiles(fileList) {
  pendingFiles = Array.from(fileList);
  const ul = document.getElementById("uploadList");
  ul.innerHTML = "";
  pendingFiles.forEach(f => {
    const li = document.createElement("li");
    li.textContent = `📄 ${f.name} (${formatSize(f.size)})`;
    ul.appendChild(li);
  });
}

async function uploadFiles() {
  if (!pendingFiles.length) return;
  const formData = new FormData();
  pendingFiles.forEach(f => formData.append("file", f));
  try {
    const res  = await fetch(`/api/upload?path=${encodeURIComponent(currentPath)}`, {
      method: "POST", body: formData,
    });
    await res.json();
    closeUpload();
    loadFiles(currentPath);
  } catch (e) {
    alert("Upload failed: " + e.message);
  }
}

async function createFolder() {
  const name = prompt("Folder name:");
  if (!name || !name.trim()) return;
  const safeName = name.trim();
  await fetch("/api/mkdir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: joinPath(currentPath, safeName) }),
  });
  loadFiles(currentPath);
}

function downloadFile(path) {
  const a = document.createElement("a");
  a.href = `/api/download?path=${encodeURIComponent(path)}`;
  a.rel  = "noopener noreferrer";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

async function deleteItem(path) {
  const name = path.split("/").pop();
  if (!confirm(`Delete "${name}"?`)) return;
  await fetch(`/api/files?path=${encodeURIComponent(path)}`, { method: "DELETE" });
  loadFiles(currentPath);
}

async function updateStorage() {
  try {
    const res   = await fetch("/api/files?path=/");
    const files = await res.json();
    const total = files.reduce((s, f) => s + (f.size || 0), 0);
    const gb    = (total / 1024 / 1024 / 1024).toFixed(2);
    document.getElementById("storageText").textContent = `${gb} GB used`;
    const pct = Math.min((total / STORAGE_LIMIT_BYTES) * 100, 100);
    document.getElementById("storageFill").style.width = pct + "%";
  } catch {}
}

function joinPath(base, name) {
  return (base === "/" ? "" : base) + "/" + name;
}

function formatSize(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return bytes.toFixed(1) + " " + units[i];
}

function getIcon(file) {
  if (file.type === "folder") return "📁";
  const ext = file.name.split(".").pop().toLowerCase();
  const map = {
    pdf: "📄", mp4: "🎬", mkv: "🎬", avi: "🎬",
    mp3: "🎵", wav: "🎵", flac: "🎵",
    jpg: "🖼", jpeg: "🖼", png: "🖼", gif: "🖼", webp: "🖼",
    zip: "📦", tar: "📦", gz: "📦", rar: "📦",
    xlsx: "📊", csv: "📊", xls: "📊",
    txt: "📝", md: "📝", py: "🐍", js: "📜",
  };
  return map[ext] || "📄";
}
