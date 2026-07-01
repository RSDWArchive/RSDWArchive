/**
 * Map.html: wiki tiles + a sidebar chunk picker that highlights the selected
 * WorldPartition cell on the map. All chunks are drawn faintly as context; the
 * selected chunk gets a prominent overlay plus a detail readout.
 *
 * Data source: website/tools/MapData/CompileMapData.py (sibling GeoJSONs).
 * CRS / transformation comes from shared/map-calibration.js
 * (game X,Y -> Leaflet lat,lng as Y,X).
 */
const GEOJSON_GRID = "/tools/MapData/ChunkWorldMapBounds_GridCell.geojson";
const GEOJSON_CONTENT = "/tools/MapData/ChunkWorldMapBounds_ContentBounds.geojson";

const mapEl = document.getElementById("world-map");
const statusEl = document.getElementById("map-status");
const siteLogo = document.getElementById("site-logo");
const chunkSearchInput = document.getElementById("map-chunk-search");
const chunkListEl = document.getElementById("map-chunk-list");
const chunkCountEl = document.getElementById("map-chunk-count");
const chunkDetailEl = document.getElementById("map-chunk-detail");
const ctxMenuEl = document.getElementById("map-context-menu");
const ctxMenuHeaderEl = document.getElementById("map-context-menu-header");
const ctxMenuHideBtn = document.getElementById("map-context-menu-hide");

const CONTEXT_STYLE = {
  color: "rgba(180, 164, 140, 0.52)",
  weight: 1,
  opacity: 0.55,
  fillColor: "rgba(180, 164, 140, 0.16)",
  fillOpacity: 0.08
};

// Selection overlays are non-interactive so clicks pass through to whatever
// chunk the user is actually aiming at (e.g. a MainGrid cell underneath an
// HLOD cell they previously selected).
const SELECTED_GRID_STYLE = {
  color: "rgba(224, 200, 150, 0.98)",
  weight: 2.5,
  opacity: 1,
  fillColor: "rgba(224, 200, 150, 0.34)",
  fillOpacity: 0.25,
  interactive: false
};

const SELECTED_CONTENT_STYLE = {
  color: "rgba(210, 178, 116, 0.95)",
  weight: 2,
  opacity: 0.95,
  dashArray: "6,4",
  fillColor: "rgba(210, 178, 116, 0.14)",
  fillOpacity: 0.1,
  interactive: false
};

/** Content bounds wider/taller than this are treated as world-scale / sentinel boxes. */
const MAX_REASONABLE_CONTENT_SPAN = 500000;

/** @typedef {{ id: string, gridName: string | null, gridRing: number[][] | null, contentRing: number[][] | null }} ChunkRecord */

/** @type {ChunkRecord[]} */
let chunks = [];
/** @type {Map<string, ChunkRecord>} */
const chunksById = new Map();
/** @type {string | null} */
let selectedId = null;

let map = null;
/** Faint backdrop showing every grid cell. */
let contextLayer = null;
/** Highlighted layers for the selected chunk (cleared between selections). */
let selectedGridLayer = null;
let selectedContentLayer = null;

if (siteLogo) {
  siteLogo.addEventListener("error", () => {
    siteLogo.style.opacity = "0.5";
    siteLogo.title = "Add website/logo.png to display your logo.";
  });
}

function setStatus(text) {
  if (statusEl) {
    statusEl.textContent = text;
  }
}

function createDragonwildsMap(container) {
  return window.RSDW_MAP_CALIBRATION.createLeafletMap(container, {
    zoom: 1,
    minZoom: 0.5,
    maxZoom: 4,
    zoomSnap: 0.5
  });
}

/** GeoJSON rings store [game X, game Y]; Leaflet on this page uses lat=Y, lng=X. */
function geoJsonCoordsToLatLng(coords) {
  return window.L.latLng(coords[1], coords[0]);
}

async function loadJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} for ${url}`);
  }
  return response.json();
}

/**
 * Pull the first ring out of a Polygon Feature (GeoJSON). Returns null if absent.
 * @param {any} feature
 * @returns {number[][] | null}
 */
function firstRingFromFeature(feature) {
  const geom = feature && feature.geometry;
  if (!geom || geom.type !== "Polygon") return null;
  const coords = geom.coordinates;
  if (!Array.isArray(coords) || coords.length === 0) return null;
  const ring = coords[0];
  return Array.isArray(ring) && ring.length > 0 ? ring : null;
}

/**
 * Merge both GeoJSON files into unified chunk records keyed by id. Each chunk
 * may have a grid-cell ring, a content-bounds ring, or both.
 */
function buildChunkRecords(gridGeo, contentGeo) {
  /** @type {Map<string, ChunkRecord>} */
  const byId = new Map();

  function upsert(feature, ringKey) {
    const props = feature && feature.properties;
    const id = props && props.id;
    if (!id || typeof id !== "string") return;
    const ring = firstRingFromFeature(feature);
    let record = byId.get(id);
    if (!record) {
      record = { id, gridName: null, gridRing: null, contentRing: null };
      byId.set(id, record);
    }
    if (ring) record[ringKey] = ring;
    const g = props && props.gridName;
    if (!record.gridName && typeof g === "string" && g.trim()) {
      record.gridName = g.trim();
    }
  }

  for (const f of (gridGeo && gridGeo.features) || []) upsert(f, "gridRing");
  for (const f of (contentGeo && contentGeo.features) || []) upsert(f, "contentRing");

  return Array.from(byId.values()).sort((a, b) => a.id.localeCompare(b.id));
}

/** @param {number[][]} ring */
function ringSpan(ring) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const pt of ring) {
    const x = pt[0];
    const y = pt[1];
    if (Number.isFinite(x)) {
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
    }
    if (Number.isFinite(y)) {
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    }
  }
  if (!Number.isFinite(minX)) return null;
  return { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY };
}

function formatInt(n) {
  if (!Number.isFinite(n)) return "—";
  return Math.round(n).toLocaleString();
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

// --- Rendering -------------------------------------------------------------

/** @param {ChunkRecord[]} visibleChunks */
function renderContextLayer(visibleChunks) {
  if (!map) return;
  if (contextLayer) {
    map.removeLayer(contextLayer);
    contextLayer = null;
  }

  const features = [];
  for (const c of visibleChunks) {
    if (!c.gridRing) continue;
    features.push({
      type: "Feature",
      properties: { id: c.id, gridName: c.gridName },
      geometry: { type: "Polygon", coordinates: [c.gridRing] }
    });
  }
  if (features.length === 0) return;

  contextLayer = window.L.geoJSON(
    { type: "FeatureCollection", features },
    {
      coordsToLatLng: geoJsonCoordsToLatLng,
      style: () => CONTEXT_STYLE,
      onEachFeature(feature, layer) {
        const id = feature && feature.properties && feature.properties.id;
        if (typeof id !== "string") return;
        layer.on("click", (ev) => {
          selectChunk(id);
          if (ev && ev.originalEvent && typeof window.L.DomEvent !== "undefined") {
            window.L.DomEvent.stopPropagation(ev.originalEvent);
          }
        });
        layer.on("contextmenu", (ev) => {
          const orig = ev && ev.originalEvent;
          if (orig) {
            if (typeof window.L.DomEvent !== "undefined") {
              window.L.DomEvent.preventDefault(orig);
              window.L.DomEvent.stopPropagation(orig);
            }
            openContextMenu(id, orig.clientX, orig.clientY);
          }
        });
      }
    }
  ).addTo(map);
}

function clearSelectionOverlays() {
  if (selectedGridLayer && map) {
    map.removeLayer(selectedGridLayer);
  }
  if (selectedContentLayer && map) {
    map.removeLayer(selectedContentLayer);
  }
  selectedGridLayer = null;
  selectedContentLayer = null;
}

function drawSelectedChunk(record) {
  clearSelectionOverlays();
  if (!map) return;

  if (record.gridRing) {
    selectedGridLayer = window.L.polygon(record.gridRing.map(geoJsonCoordsToLatLng), {
      ...SELECTED_GRID_STYLE
    }).addTo(map);
    if (typeof selectedGridLayer.bringToFront === "function") {
      selectedGridLayer.bringToFront();
    }
  }

  if (record.contentRing) {
    const span = ringSpan(record.contentRing);
    const oversized =
      !!span &&
      (span.width > MAX_REASONABLE_CONTENT_SPAN || span.height > MAX_REASONABLE_CONTENT_SPAN);
    if (!oversized) {
      selectedContentLayer = window.L.polygon(
        record.contentRing.map(geoJsonCoordsToLatLng),
        { ...SELECTED_CONTENT_STYLE }
      ).addTo(map);
      if (typeof selectedContentLayer.bringToFront === "function") {
        selectedContentLayer.bringToFront();
      }
    }
  }
}

function renderDetailPanel(record) {
  if (!chunkDetailEl) return;
  if (!record) {
    chunkDetailEl.hidden = true;
    chunkDetailEl.innerHTML = "";
    return;
  }

  const gridSpan = record.gridRing ? ringSpan(record.gridRing) : null;
  const contentSpan = record.contentRing ? ringSpan(record.contentRing) : null;
  const contentOversized =
    !!contentSpan &&
    (contentSpan.width > MAX_REASONABLE_CONTENT_SPAN ||
      contentSpan.height > MAX_REASONABLE_CONTENT_SPAN);

  const rows = [];
  rows.push(
    `<div class="map-detail-row"><span class="map-detail-label">ID</span><code class="map-detail-value">${escapeHtml(
      record.id
    )}</code></div>`
  );
  if (record.gridName) {
    rows.push(
      `<div class="map-detail-row"><span class="map-detail-label">Grid</span><span class="map-detail-value">${escapeHtml(
        record.gridName
      )}</span></div>`
    );
  }
  if (gridSpan) {
    rows.push(
      `<div class="map-detail-row"><span class="map-detail-label">Cell XY</span><span class="map-detail-value">${formatInt(
        gridSpan.minX
      )} … ${formatInt(gridSpan.maxX)}, ${formatInt(gridSpan.minY)} … ${formatInt(
        gridSpan.maxY
      )}</span></div>`
    );
    rows.push(
      `<div class="map-detail-row"><span class="map-detail-label">Cell size</span><span class="map-detail-value">${formatInt(
        gridSpan.width
      )} × ${formatInt(gridSpan.height)}</span></div>`
    );
  } else {
    rows.push(
      `<div class="map-detail-row"><span class="map-detail-label">Cell</span><span class="map-detail-value map-detail-muted">not in grid cell file</span></div>`
    );
  }
  if (contentSpan) {
    const note = contentOversized ? ' <span class="map-detail-muted">(oversized — hidden on map)</span>' : "";
    rows.push(
      `<div class="map-detail-row"><span class="map-detail-label">Content size</span><span class="map-detail-value">${formatInt(
        contentSpan.width
      )} × ${formatInt(contentSpan.height)}${note}</span></div>`
    );
  }

  chunkDetailEl.innerHTML = rows.join("");
  chunkDetailEl.hidden = false;
}

// --- Query parsing --------------------------------------------------------

/**
 * Parse the search input into positive/negative tokens. Whitespace-separated;
 * tokens prefixed with "-" are negations. Examples:
 *   "maingrid"              → { positive: ["maingrid"], negative: [] }
 *   "maingrid -78RMVK..."   → { positive: ["maingrid"], negative: ["78RMVK..."] }
 *   "-78RMVK..."            → { positive: [], negative: ["78RMVK..."] }
 */
function parseQuery(raw) {
  const positive = [];
  const negative = [];
  if (typeof raw !== "string") return { positive, negative };
  const tokens = raw.split(/\s+/).map((t) => t.trim()).filter(Boolean);
  for (const tok of tokens) {
    if (tok.startsWith("-") && tok.length > 1) {
      negative.push(tok.slice(1).toLowerCase());
    } else if (!tok.startsWith("-")) {
      positive.push(tok.toLowerCase());
    }
  }
  return { positive, negative };
}

function chunkHaystack(record) {
  const grid = record.gridName || "";
  return `${record.id}\n${grid}`.toLowerCase();
}

/**
 * A chunk passes when it matches every positive token (AND) and none of the
 * negative tokens. An empty positive list means "all positives match".
 */
function chunkMatchesTokens(record, tokens) {
  const hay = chunkHaystack(record);
  for (const neg of tokens.negative) {
    if (hay.includes(neg)) return false;
  }
  for (const pos of tokens.positive) {
    if (!hay.includes(pos)) return false;
  }
  return true;
}

function currentQuery() {
  return chunkSearchInput ? chunkSearchInput.value.trim() : "";
}

function getVisibleChunks() {
  const q = currentQuery();
  if (!q) return chunks;
  const tokens = parseQuery(q);
  if (tokens.positive.length === 0 && tokens.negative.length === 0) return chunks;
  return chunks.filter((c) => chunkMatchesTokens(c, tokens));
}

// --- Sidebar list ---------------------------------------------------------

/** @param {ChunkRecord[]} visibleChunks */
function renderChunkList(visibleChunks) {
  if (!chunkListEl) return;

  chunkListEl.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const c of visibleChunks) {
    const li = document.createElement("li");
    li.className = "map-chunk-list-item";
    li.setAttribute("role", "option");
    li.dataset.chunkId = c.id;
    if (c.id === selectedId) {
      li.classList.add("is-selected");
      li.setAttribute("aria-selected", "true");
    }

    const idSpan = document.createElement("span");
    idSpan.className = "map-chunk-item-id";
    idSpan.textContent = c.id;
    li.appendChild(idSpan);

    if (c.gridName) {
      const badge = document.createElement("span");
      badge.className = "map-chunk-item-badge";
      badge.textContent = c.gridName;
      li.appendChild(badge);
    }

    li.addEventListener("click", () => selectChunk(c.id));
    li.addEventListener("contextmenu", (ev) => {
      ev.preventDefault();
      openContextMenu(c.id, ev.clientX, ev.clientY);
    });
    frag.appendChild(li);
  }
  chunkListEl.appendChild(frag);

  if (chunkCountEl) {
    const query = currentQuery();
    if (query) {
      chunkCountEl.textContent = `${visibleChunks.length.toLocaleString()} / ${chunks.length.toLocaleString()} chunks`;
    } else {
      chunkCountEl.textContent = `${chunks.length.toLocaleString()} chunks`;
    }
  }
}

/**
 * Re-run the current search filter against the sidebar list and the map
 * context layer, keeping the selection overlay visible only while the
 * selected chunk still matches the filter.
 */
function refreshFilter() {
  const visible = getVisibleChunks();
  renderContextLayer(visible);
  renderChunkList(visible);

  if (!selectedId) return;
  const record = chunksById.get(selectedId);
  const stillVisible = !!record && visible.some((c) => c.id === selectedId);
  if (stillVisible) {
    // Context layer was rebuilt just above; redraw selection so it stays on top.
    drawSelectedChunk(record);
    renderDetailPanel(record);
  } else {
    clearSelectionOverlays();
    renderDetailPanel(null);
  }
}

function scrollSelectedIntoView() {
  if (!chunkListEl) return;
  const el = chunkListEl.querySelector(".map-chunk-list-item.is-selected");
  if (el && typeof el.scrollIntoView === "function") {
    el.scrollIntoView({ block: "nearest" });
  }
}

function selectChunk(id) {
  const record = chunksById.get(id);
  if (!record) return;
  selectedId = id;
  renderChunkList(getVisibleChunks());
  scrollSelectedIntoView();
  drawSelectedChunk(record);
  renderDetailPanel(record);
  setStatus(`Selected ${record.id}${record.gridName ? ` (${record.gridName})` : ""}`);
}

// --- Context menu + hide --------------------------------------------------

/** Chunk id captured when the context menu last opened. */
let ctxMenuChunkId = null;

function closeContextMenu() {
  if (!ctxMenuEl) return;
  ctxMenuEl.hidden = true;
  ctxMenuChunkId = null;
}

function openContextMenu(chunkId, clientX, clientY) {
  if (!ctxMenuEl) return;
  ctxMenuChunkId = chunkId;
  if (ctxMenuHeaderEl) {
    ctxMenuHeaderEl.textContent = chunkId;
  }

  ctxMenuEl.hidden = false;

  // Clamp to viewport so the menu is never clipped.
  const rect = ctxMenuEl.getBoundingClientRect();
  const pad = 6;
  const maxX = window.innerWidth - rect.width - pad;
  const maxY = window.innerHeight - rect.height - pad;
  const x = Math.max(pad, Math.min(clientX, Number.isFinite(maxX) ? maxX : clientX));
  const y = Math.max(pad, Math.min(clientY, Number.isFinite(maxY) ? maxY : clientY));
  ctxMenuEl.style.left = `${x}px`;
  ctxMenuEl.style.top = `${y}px`;
}

/**
 * Append `-<chunkId>` to the search box (no-op if already excluded) and
 * re-run the filter. The filter grammar — not a separate hidden list — is the
 * single source of truth for which chunks are hidden.
 */
function hideChunk(chunkId) {
  if (!chunkSearchInput || !chunkId) return;
  const existing = chunkSearchInput.value || "";
  const tokens = parseQuery(existing);
  if (tokens.negative.includes(chunkId.toLowerCase())) {
    // Already excluded via filter (even if spelled differently); just refresh.
    refreshFilter();
    return;
  }
  const separator = existing && !existing.endsWith(" ") ? " " : "";
  chunkSearchInput.value = `${existing}${separator}-${chunkId}`;
  refreshFilter();
  setStatus(`Hidden ${chunkId}. Edit the filter to unhide.`);
}

// --- Init -----------------------------------------------------------------

async function init() {
  if (!mapEl || typeof window.L === "undefined") {
    setStatus("Map library failed to load.");
    return;
  }

  map = createDragonwildsMap(mapEl);
  setStatus("Loading chunk boundaries…");

  try {
    const [gridGeo, contentGeo] = await Promise.all([
      loadJson(GEOJSON_GRID),
      loadJson(GEOJSON_CONTENT)
    ]);
    chunks = buildChunkRecords(gridGeo, contentGeo);
    chunksById.clear();
    for (const c of chunks) chunksById.set(c.id, c);
  } catch (err) {
    setStatus(`Failed to load chunk GeoJSON: ${err instanceof Error ? err.message : String(err)}`);
    return;
  }

  refreshFilter();

  if (chunks.length === 0) {
    setStatus("No chunks found.");
    return;
  }
  setStatus(
    `${chunks.length.toLocaleString()} chunks. Click to highlight, right-click to hide. Filter supports -token to exclude.`
  );

  if (chunkSearchInput) {
    chunkSearchInput.addEventListener("input", () => refreshFilter());
  }

  if (ctxMenuHideBtn) {
    ctxMenuHideBtn.addEventListener("click", () => {
      const id = ctxMenuChunkId;
      closeContextMenu();
      if (id) hideChunk(id);
    });
  }

  // Close the context menu on any outside interaction.
  document.addEventListener("click", (ev) => {
    if (!ctxMenuEl || ctxMenuEl.hidden) return;
    if (ev.target instanceof Node && ctxMenuEl.contains(ev.target)) return;
    closeContextMenu();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeContextMenu();
  });
  window.addEventListener("blur", () => closeContextMenu());
  if (map) {
    map.on("movestart zoomstart", () => closeContextMenu());
  }

  window.addEventListener("resize", () => {
    if (map) map.invalidateSize();
  });
}

if (typeof window.L !== "undefined") {
  void init();
} else {
  window.setTimeout(() => {
    if (typeof window.L !== "undefined") {
      void init();
    } else {
      setStatus("Leaflet failed to load.");
    }
  }, 400);
}
