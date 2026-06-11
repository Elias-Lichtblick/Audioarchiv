const INDEX_URL = "audio-index.json";

const els = {
  stats: document.querySelector("#stats"),
  search: document.querySelector("#search"),
  tagList: document.querySelector("#tagList"),
  clearTag: document.querySelector("#clearTag"),
  list: document.querySelector("#list"),
  resultInfo: document.querySelector("#resultInfo"),
  sort: document.querySelector("#sort"),
  audio: document.querySelector("#audio"),
  playerBar: document.querySelector("#playerBar"),
  nowTitle: document.querySelector("#nowTitle"),
  nowMeta: document.querySelector("#nowMeta"),
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
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"]/g, (c) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;"}[c]));
const shorten = (value, max) => {
  const s = String(value ?? "").replace(/\s+/g, " ").trim();
  return s.length > max ? s.slice(0, max - 1).trim() + "…" : s;
};
const fmtTime = (seconds) => {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0:00";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return h ? `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}` : `${m}:${String(s).padStart(2,"0")}`;
};
const normalize = (value) => String(value ?? "")
  .toLocaleLowerCase("de-DE")
  .normalize("NFD")
  .replace(/[\u0300-\u036f]/g, "")
  .replace(/ä/g, "ae")
  .replace(/ö/g, "oe")
  .replace(/ü/g, "ue")
  .replace(/ß/g, "ss")
  .replace(/[^a-z0-9]+/g, " ")
  .replace(/\s+/g, " ")
  .trim();

function cleanClientTitle(value) {
  let s = decodeURIComponent(String(value ?? "")).replace(/\.(mp3|m4a|ogg|oga|wav|flac|aac)$/i, "");
  s = s.replace(/[_]+/g, " ").replace(/[.]+/g, " ");
  s = s.replace(/([a-zäöüß])([A-ZÄÖÜ])/g, "$1 $2");
  s = s.replace(/^\s*\d{1,3}\s+/, "");
  s = s.replace(/\s+/g, " ").trim();
  return s || "Ohne Titel";
}

function prepareTrack(t, index) {
  const title = t.title || t.displayTitle || cleanClientTitle(t.name || t.url || `Titel ${index + 1}`);
  const description = t.description || t.youtubeDescription || "";
  const dateLabel = t.dateLabel || t.date || "";
  const tags = Array.isArray(t.tags) ? t.tags.filter(Boolean) : [];
  const displayPath = t.displayPath || t.prettyPath || t.folder || t.source || "Archiv";
  const search = normalize([
    title,
    displayPath,
    t.name,
    dateLabel,
    description,
    t.youtubeTitle,
    tags.join(" ")
  ].join(" "));
  return {
    ...t,
    _i: index,
    title,
    description,
    dateLabel,
    tags,
    displayPath,
    search,
    sortDate: t.sortDate || t.dateIso || t.date || "",
  };
}

async function loadIndex() {
  try {
    const res = await fetch(`${INDEX_URL}?v=${Date.now()}`);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const data = await res.json();
    tracks = data.map(prepareTrack);
    renderStats();
    renderTags();
    render();
  } catch (err) {
    els.stats.textContent = "Index fehlt";
    els.resultInfo.textContent = "audio-index.json konnte nicht geladen werden.";
    els.list.innerHTML = `<div class="empty"><strong>Der Index ist noch nicht erzeugt.</strong><br>Starte in GitHub unter <em>Actions</em> den Workflow <em>Update audio index</em>. Technischer Hinweis: ${escapeHtml(err.message)}</div>`;
  }
}

function renderStats() {
  const withYoutube = tracks.filter(t => t.youtubeUrl).length;
  const total = tracks.length.toLocaleString("de-DE");
  els.stats.textContent = withYoutube ? `${total} Titel · ${withYoutube.toLocaleString("de-DE")} mit YouTube-Texten` : `${total} Titel`;
}

function renderTags() {
  const counts = new Map();
  for (const t of tracks) for (const tag of t.tags || []) counts.set(tag, (counts.get(tag) || 0) + 1);
  const ordered = [...counts.entries()]
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "de"));
  els.tagList.innerHTML = ordered.map(([tag, count]) => `
    <button type="button" data-tag="${escapeHtml(tag)}" class="${tag === activeTag ? "active" : ""}">
      <span>${escapeHtml(tag)}</span>
      <span class="count">${count}</span>
    </button>`).join("");
}

function filteredTracks() {
  const q = normalize(els.search.value);
  let out = tracks.filter(t => !activeTag || (t.tags || []).includes(activeTag));
  if (q) out = out.filter(t => t.search.includes(q));
  if (mode === "continue") out = out.filter(t => getPos(t.url) > 20);
  if (mode === "favs") out = out.filter(t => isFav(t.url));

  const sort = els.sort.value;
  out.sort((a, b) => {
    if (sort === "date-desc") return String(b.sortDate).localeCompare(String(a.sortDate)) || a.title.localeCompare(b.title, "de");
    if (sort === "date-asc") return String(a.sortDate).localeCompare(String(b.sortDate)) || a.title.localeCompare(b.title, "de");
    if (sort === "size-desc") return (b.sizeBytes || 0) - (a.sizeBytes || 0) || a.title.localeCompare(b.title, "de");
    return a.title.localeCompare(b.title, "de", { numeric: true, sensitivity: "base" });
  });
  return out;
}

function render() {
  const out = filteredTracks();
  const tagPart = activeTag ? ` · Tag: ${activeTag}` : "";
  els.clearTag.hidden = !activeTag;
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
  const tagHtml = (t.tags || []).slice(0, 10).map(tag => `<span class="tag-pill">${escapeHtml(tag)}</span>`).join("");
  const preview = t.description ? `<p class="description-preview">${escapeHtml(shorten(t.description, 300))}</p>` : "";
  const youtube = t.youtubeUrl ? `<span><a href="${escapeHtml(t.youtubeUrl)}" target="_blank" rel="noreferrer">YouTube</a></span>` : "";
  const match = t.matchScore ? `<dt>Abgleich</dt><dd>${Math.round(Number(t.matchScore) * 100)}%</dd>` : "";
  const detailsText = t.description ? escapeHtml(t.description) : "Keine zusätzliche Beschreibung gefunden.";
  const date = t.dateLabel ? `<span class="meta-date">${escapeHtml(t.dateLabel)}</span>` : "";
  return `<article class="card" data-url="${escapeHtml(t.url)}" id="${escapeHtml(domId(t.url))}">
    <div>
      <h3>${escapeHtml(t.title)}</h3>
      <div class="meta">
        <span class="meta-path">${escapeHtml(t.displayPath || "Archiv")}</span>
        ${date}
        ${t.size ? `<span>${escapeHtml(t.size)}</span>` : ""}
        ${pos > 20 ? `<span>${resume}</span>` : ""}
        ${youtube}
      </div>
      ${tagHtml ? `<div class="tags">${tagHtml}</div>` : ""}
      ${preview}
      <div class="progress"><span style="width:${percent}%"></span></div>
    </div>
    <div class="actions">
      <button class="play" type="button" title="${escapeHtml(resume)}">▶</button>
      <button class="fav" type="button" title="Favorit">${isFav(t.url) ? "★" : "☆"}</button>
    </div>
    <details class="details">
      <summary>Informationen zum Vortrag</summary>
      <div class="details-grid">
        <div class="details-text">${detailsText}</div>
        <div class="details-side">
          <dl>
            ${t.youtubeTitle ? `<dt>YouTube-Titel</dt><dd>${escapeHtml(t.youtubeTitle)}</dd>` : ""}
            ${t.dateLabel ? `<dt>Datum</dt><dd>${escapeHtml(t.dateLabel)}</dd>` : ""}
            <dt>Bereich</dt><dd>${escapeHtml(t.displayPath || "Archiv")}</dd>
            ${t.name ? `<dt>Originaldatei</dt><dd>${escapeHtml(t.name)}</dd>` : ""}
            ${t.youtubeUrl ? `<dt>YouTube</dt><dd><a href="${escapeHtml(t.youtubeUrl)}" target="_blank" rel="noreferrer">Video öffnen</a></dd>` : ""}
            <dt>Audiodatei</dt><dd><a href="${escapeHtml(t.url)}" target="_blank" rel="noreferrer">Original öffnen</a></dd>
            ${match}
          </dl>
        </div>
      </div>
    </details>
  </article>`;
}

function playTrack(t) {
  current = t;
  els.playerBar.hidden = false;
  els.nowTitle.textContent = t.title;
  els.nowMeta.textContent = [t.displayPath, t.dateLabel].filter(Boolean).join(" · ") || "Archiv";
  els.openOriginal.href = t.url;
  els.favCurrent.textContent = isFav(t.url) ? "★" : "☆";

  const absolute = new URL(t.url, window.location.href).href;
  if (els.audio.src !== absolute) {
    els.audio.src = t.url;
    els.audio.addEventListener("loadedmetadata", () => {
      const saved = getPos(t.url);
      if (saved > 20 && Number.isFinite(els.audio.duration) && saved < els.audio.duration - 10) {
        els.audio.currentTime = saved;
      }
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

function setMode(nextMode) {
  mode = nextMode;
  for (const [button, name] of [[els.showAll, "all"], [els.showContinue, "continue"], [els.showFavs, "favs"]]) {
    button.classList.toggle("active", mode === name);
  }
  render();
}

function domId(url) {
  let hash = 0;
  for (let i = 0; i < url.length; i++) hash = ((hash << 5) - hash + url.charCodeAt(i)) | 0;
  return `t-${Math.abs(hash)}`;
}

els.list.addEventListener("click", (e) => {
  const card = e.target.closest(".card");
  if (!card) return;
  const t = tracks.find(x => x.url === card.dataset.url);
  if (!t) return;
  if (e.target.closest(".fav")) toggleFav(t.url);
  else if (e.target.closest(".play")) playTrack(t);
});

els.tagList.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tag]");
  if (!btn) return;
  activeTag = btn.dataset.tag;
  renderTags();
  render();
});
els.clearTag.addEventListener("click", () => {
  activeTag = "";
  renderTags();
  render();
});
els.search.addEventListener("input", render);
els.sort.addEventListener("change", render);
els.showAll.addEventListener("click", () => setMode("all"));
els.showContinue.addEventListener("click", () => setMode("continue"));
els.showFavs.addEventListener("click", () => setMode("favs"));
els.rewind30.addEventListener("click", () => { els.audio.currentTime = Math.max(0, els.audio.currentTime - 30); });
els.forward30.addEventListener("click", () => {
  const max = Number.isFinite(els.audio.duration) ? els.audio.duration : Infinity;
  els.audio.currentTime = Math.min(max, els.audio.currentTime + 30);
});
els.favCurrent.addEventListener("click", () => current && toggleFav(current.url));

els.audio.addEventListener("timeupdate", () => {
  if (!current) return;
  localStorage.setItem(key("pos", current.url), String(els.audio.currentTime));
  if (Number.isFinite(els.audio.duration)) localStorage.setItem(key("dur", current.url), String(els.audio.duration));
});
els.audio.addEventListener("ended", () => {
  if (current) localStorage.removeItem(key("pos", current.url));
  render();
});

loadIndex();
