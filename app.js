const INDEX_URL = "audio-index.json";
const AUDIO_EXT = /\.(mp3|m4a|ogg|oga|wav|flac|aac)$/i;

const els = {
  stats: document.querySelector("#stats"),
  search: document.querySelector("#search"),
  folderTree: document.querySelector("#folderTree"),
  list: document.querySelector("#list"),
  resultInfo: document.querySelector("#resultInfo"),
  sort: document.querySelector("#sort"),
  audio: document.querySelector("#audio"),
  playerBar: document.querySelector("#playerBar"),
  nowTitle: document.querySelector("#nowTitle"),
  nowPath: document.querySelector("#nowPath"),
  openOriginal: document.querySelector("#openOriginal"),
  rewind30: document.querySelector("#rewind30"),
  forward30: document.querySelector("#forward30"),
  favCurrent: document.querySelector("#favCurrent"),
  showAll: document.querySelector("#showAll"),
  showContinue: document.querySelector("#showContinue"),
  showFavs: document.querySelector("#showFavs"),
};

let tracks = [];
let current = null;
let activeFolder = "";
let mode = "all";

const key = (prefix, url) => `${prefix}:${url}`;
const getPos = (url) => Number(localStorage.getItem(key("pos", url)) || 0);
const getDur = (url) => Number(localStorage.getItem(key("dur", url)) || 0);
const isFav = (url) => localStorage.getItem(key("fav", url)) === "1";
const fmtTime = (seconds) => {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0:00";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return h ? `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}` : `${m}:${String(s).padStart(2,"0")}`;
};

function cleanTitle(name) {
  return decodeURIComponent(name)
    .replace(AUDIO_EXT, "")
    .replace(/[._]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

async function loadIndex() {
  try {
    const res = await fetch(INDEX_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    tracks = (await res.json()).filter(t => AUDIO_EXT.test(t.url || t.name || ""));
    tracks = tracks.map((t, i) => ({
      id: t.id || String(i),
      name: t.name || t.title || t.url.split("/").pop(),
      title: t.title || cleanTitle(t.name || t.url.split("/").pop()),
      url: t.url,
      folder: t.folder || "",
      path: t.path || t.folder || "",
      size: t.size || "",
      sizeBytes: t.sizeBytes || 0,
      date: t.date || "",
      search: `${t.title || ""} ${t.name || ""} ${t.folder || ""} ${t.path || ""}`.toLowerCase()
    }));
    els.stats.textContent = `${tracks.length.toLocaleString("de-DE")} Audio-Dateien`;
    buildFolders();
    render();
  } catch (err) {
    els.stats.textContent = "Index fehlt";
    els.list.innerHTML = `<div class="empty">Konnte <code>audio-index.json</code> nicht laden. Starte zuerst <code>python3 crawl_k23.py</code>.</div>`;
    console.error(err);
  }
}

function setMode(next) {
  mode = next;
  [els.showAll, els.showContinue, els.showFavs].forEach(b => b.classList.remove("active"));
  ({ all: els.showAll, continue: els.showContinue, favs: els.showFavs })[mode].classList.add("active");
  render();
}

function buildFolders() {
  const counts = new Map();
  tracks.forEach(t => {
    const parts = (t.folder || "").split("/").filter(Boolean);
    let acc = "";
    parts.forEach(p => {
      acc = acc ? `${acc}/${p}` : p;
      counts.set(acc, (counts.get(acc) || 0) + 1);
    });
  });
  const entries = [...counts.entries()].sort((a,b) => a[0].localeCompare(b[0], "de"));
  els.folderTree.innerHTML = `<button class="root active" data-folder="">Alle Ordner <span class="count">${tracks.length}</span></button>` +
    entries.map(([folder, count]) => {
      const depth = folder.split("/").length - 1;
      const label = folder.split("/").pop();
      return `<button data-folder="${escapeHtml(folder)}" style="padding-left:${0.5 + depth * 1.0}rem">${escapeHtml(label)} <span class="count">${count}</span></button>`;
    }).join("");
}

function filteredTracks() {
  const q = els.search.value.trim().toLowerCase();
  let out = tracks.filter(t => !activeFolder || t.folder === activeFolder || t.folder.startsWith(activeFolder + "/"));
  if (q) out = out.filter(t => t.search.includes(q));
  if (mode === "continue") out = out.filter(t => getPos(t.url) > 20);
  if (mode === "favs") out = out.filter(t => isFav(t.url));
  const sort = els.sort.value;
  out.sort((a,b) => {
    if (sort === "date-desc") return String(b.date).localeCompare(String(a.date));
    if (sort === "date-asc") return String(a.date).localeCompare(String(b.date));
    if (sort === "size-desc") return (b.sizeBytes || 0) - (a.sizeBytes || 0);
    return a.title.localeCompare(b.title, "de");
  });
  return out;
}

function render() {
  const out = filteredTracks();
  els.resultInfo.textContent = `${out.length.toLocaleString("de-DE")} Treffer`;
  if (!out.length) {
    els.list.innerHTML = `<div class="empty">Keine Treffer.</div>`;
    return;
  }
  els.list.innerHTML = out.map(trackCard).join("");
}

function trackCard(t) {
  const pos = getPos(t.url);
  const dur = getDur(t.url);
  const percent = dur ? Math.min(100, (pos / dur) * 100) : 0;
  const resume = pos > 20 ? `Weiter bei ${fmtTime(pos)}` : "Abspielen";
  return `<article class="card" data-url="${escapeHtml(t.url)}">
    <div>
      <h3>${escapeHtml(t.title)}</h3>
      <div class="meta">
        <span>${escapeHtml(t.folder || "Root")}</span>
        ${t.date ? `<span>${escapeHtml(t.date)}</span>` : ""}
        ${t.size ? `<span>${escapeHtml(t.size)}</span>` : ""}
        ${pos > 20 ? `<span>${resume}</span>` : ""}
      </div>
      <div class="progress"><span style="width:${percent}%"></span></div>
    </div>
    <div class="actions">
      <button class="play">▶</button>
      <button class="fav">${isFav(t.url) ? "★" : "☆"}</button>
    </div>
  </article>`;
}

function playTrack(t) {
  current = t;
  els.playerBar.hidden = false;
  els.nowTitle.textContent = t.title;
  els.nowPath.textContent = t.folder || "Root";
  els.openOriginal.href = t.url;
  els.favCurrent.textContent = isFav(t.url) ? "★" : "☆";
  if (els.audio.src !== t.url) {
    els.audio.src = t.url;
    els.audio.addEventListener("loadedmetadata", () => {
      const saved = getPos(t.url);
      if (saved > 20 && saved < els.audio.duration - 10) els.audio.currentTime = saved;
      if (Number.isFinite(els.audio.duration)) localStorage.setItem(key("dur", t.url), String(els.audio.duration));
      els.audio.play().catch(() => {});
    }, { once: true });
  } else {
    els.audio.play().catch(() => {});
  }
}

function toggleFav(url) {
  if (isFav(url)) localStorage.removeItem(key("fav", url));
  else localStorage.setItem(key("fav", url), "1");
  if (current?.url === url) els.favCurrent.textContent = isFav(url) ? "★" : "☆";
  render();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
}

els.list.addEventListener("click", e => {
  const card = e.target.closest(".card");
  if (!card) return;
  const t = tracks.find(x => x.url === card.dataset.url);
  if (!t) return;
  if (e.target.closest(".fav")) toggleFav(t.url);
  else playTrack(t);
});

els.folderTree.addEventListener("click", e => {
  const btn = e.target.closest("button[data-folder]");
  if (!btn) return;
  activeFolder = btn.dataset.folder;
  els.folderTree.querySelectorAll("button").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  render();
});

els.audio.addEventListener("timeupdate", () => {
  if (!current) return;
  localStorage.setItem(key("pos", current.url), String(els.audio.currentTime));
  if (Number.isFinite(els.audio.duration)) localStorage.setItem(key("dur", current.url), String(els.audio.duration));
});
els.audio.addEventListener("ended", () => {
  if (current) localStorage.removeItem(key("pos", current.url));
  render();
});
els.rewind30.addEventListener("click", () => els.audio.currentTime = Math.max(0, els.audio.currentTime - 30));
els.forward30.addEventListener("click", () => els.audio.currentTime = Math.min(els.audio.duration || Infinity, els.audio.currentTime + 30));
els.favCurrent.addEventListener("click", () => current && toggleFav(current.url));
els.search.addEventListener("input", render);
els.sort.addEventListener("change", render);
els.showAll.addEventListener("click", () => setMode("all"));
els.showContinue.addEventListener("click", () => setMode("continue"));
els.showFavs.addEventListener("click", () => setMode("favs"));

loadIndex();
