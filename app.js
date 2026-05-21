const INDEX_URL = "audio-index.json";
const AUDIO_EXT = /\.(mp3|m4a|ogg|oga|wav|flac|aac)$/i;

const els = {
  stats: document.querySelector("#stats"),
  search: document.querySelector("#search"),
  tagList: document.querySelector("#tagList"),
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
let activeTag = "";
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
  return decodeURIComponent(name || "")
    .replace(AUDIO_EXT, "")
    .replace(/^\d{1,3}[\s_.-]+/, "")
    .replace(/_/g, " ")
    .replace(/[.]+/g, " ")
    .replace(/\s*[-–—]+\s*/g, " – ")
    .replace(/([a-zäöüß])([A-ZÄÖÜ])/g, "$1 $2")
    .replace(/\bDiskussion\b$/i, "– Diskussion")
    .replace(/\s+/g, " ")
    .trim();
}

function normalize(s) {
  return String(s || "")
    .toLowerCase()
    .replaceAll("ä", "ae").replaceAll("ö", "oe").replaceAll("ü", "ue").replaceAll("ß", "ss")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

async function loadIndex() {
  try {
    const res = await fetch(INDEX_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    tracks = (await res.json()).filter(t => AUDIO_EXT.test(t.url || t.name || ""));
    tracks = tracks.map((t, i) => {
      const tags = Array.isArray(t.tags) ? t.tags.filter(Boolean) : [];
      const title = t.title || cleanTitle(t.name || t.url.split("/").pop());
      const displayPath = t.displayPath || t.folder || "Archiv";
      const description = t.description || "";
      return {
        id: t.id || String(i),
        name: t.name || title || t.url.split("/").pop(),
        title,
        url: t.url,
        folder: t.folder || "",
        displayPath,
        source: t.source || (t.folder || "Archiv").split("/")[0],
        tags,
        path: t.path || t.folder || "",
        size: t.size || "",
        sizeBytes: t.sizeBytes || 0,
        date: t.date || "",
        description,
        youtubeUrl: t.youtubeUrl || "",
        search: normalize(`${title} ${t.name || ""} ${displayPath} ${t.folder || ""} ${tags.join(" ")} ${description}`)
      };
    });
    els.stats.textContent = `${tracks.length.toLocaleString("de-DE")} Audio-Dateien`;
    buildTags();
    render();
  } catch (err) {
    els.stats.textContent = "Index fehlt";
    els.list.innerHTML = `<div class="empty">Konnte <code>audio-index.json</code> nicht laden. Starte zuerst <code>python3 crawl_k23.py</code> oder lass die GitHub Action laufen.</div>`;
    console.error(err);
  }
}

function setMode(next) {
  mode = next;
  [els.showAll, els.showContinue, els.showFavs].forEach(b => b.classList.remove("active"));
  ({ all: els.showAll, continue: els.showContinue, favs: els.showFavs })[mode].classList.add("active");
  render();
}

function buildTags() {
  const counts = new Map();
  tracks.forEach(t => (t.tags || []).forEach(tag => counts.set(tag, (counts.get(tag) || 0) + 1)));
  const entries = [...counts.entries()]
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "de"));

  els.tagList.innerHTML = `<button class="active" data-tag="">Alle Tags <span class="count">${tracks.length}</span></button>` +
    entries.map(([tag, count]) => `<button data-tag="${escapeHtml(tag)}">${escapeHtml(tag)} <span class="count">${count}</span></button>`).join("");
}

function filteredTracks() {
  const q = normalize(els.search.value.trim());
  let out = tracks.filter(t => !activeTag || (t.tags || []).includes(activeTag));
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
  const tagPart = activeTag ? ` · Tag: ${activeTag}` : "";
  els.resultInfo.textContent = `${out.length.toLocaleString("de-DE")} Treffer${tagPart}`;
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
  const tagHtml = (t.tags || []).slice(0, 8).map(tag => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("");
  const desc = t.description ? `<p class="description">${escapeHtml(shorten(t.description, 260))}</p>` : "";
  const youtube = t.youtubeUrl ? `<span><a href="${escapeHtml(t.youtubeUrl)}" target="_blank" rel="noreferrer">YouTube</a></span>` : "";
  return `<article class="card" data-url="${escapeHtml(t.url)}">
    <div>
      <h3>${escapeHtml(t.title)}</h3>
      <div class="meta">
        <span class="meta-path">${escapeHtml(t.displayPath || t.source || "Archiv")}</span>
        ${t.date ? `<span>${escapeHtml(t.date)}</span>` : ""}
        ${t.size ? `<span>${escapeHtml(t.size)}</span>` : ""}
        ${pos > 20 ? `<span>${resume}</span>` : ""}
        ${youtube}
      </div>
      ${tagHtml ? `<div class="tags">${tagHtml}</div>` : ""}
      ${desc}
      <div class="progress"><span style="width:${percent}%"></span></div>
    </div>
    <div class="actions">
      <button class="play" title="${resume}">▶</button>
      <button class="fav" title="Favorit">${isFav(t.url) ? "★" : "☆"}</button>
    </div>
  </article>`;
}

function playTrack(t) {
  current = t;
  els.playerBar.hidden = false;
  els.nowTitle.textContent = t.title;
  els.nowPath.textContent = t.displayPath || t.source || "Archiv";
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

function shorten(s, n) {
  s = String(s).replace(/\s+/g, " ").trim();
  return s.length > n ? s.slice(0, n - 1).trim() + "…" : s;
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
  else if (!e.target.closest("a")) playTrack(t);
});

els.tagList.addEventListener("click", e => {
  const btn = e.target.closest("button[data-tag]");
  if (!btn) return;
  activeTag = btn.dataset.tag;
  els.tagList.querySelectorAll("button").forEach(b => b.classList.remove("active"));
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
