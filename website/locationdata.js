const DATA_URL = "./tools/LocationData/LocationData.json";
const CONFIG_URL = "./data.config.json";
let ROOT_FOLDER = "0.11.0.3";
const MAX_RESULTS = 400;
const SEARCH_DEBOUNCE_MS = 90;
const MAX_MAP_MARKERS = 500;

const searchInput = document.getElementById("file-search");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const resultsViewer = document.querySelector(".results-viewer");
const landingMessageEl = document.getElementById("landing-message");
const homeStatusEl = document.getElementById("home-status");
const homeSubtitleEl = document.getElementById("home-subtitle");
const selectedPathEl = document.getElementById("selected-path");
const fileContentEl = document.getElementById("file-content");
const siteLogo = document.getElementById("site-logo");
const toolsToggleBtn = document.getElementById("tools-toggle");
const toolsDropdownEl = document.getElementById("tools-dropdown");
const combineBtn = document.getElementById("combine-btn");
const combinerModal = document.getElementById("combiner-modal");
const includeNamesInput = document.getElementById("include-names");
const includeZInput = document.getElementById("include-z");
const combinerCancelBtn = document.getElementById("combiner-cancel");
const combinerCreateBtn = document.getElementById("combiner-create");
const togglePreviewFormatBtn = document.getElementById("toggle-preview-format");
const copyPreviewBtn = document.getElementById("copy-preview");
const copyToastEl = document.getElementById("copy-toast");
const locationMapEl = document.getElementById("location-map");
const toggleMapModeBtn = document.getElementById("toggle-map-mode");

let locations = [];
let currentMatches = [];
let currentFiltered = [];
let selectedMatchIndex = -1;
let currentActiveBtn = null;
let debounceTimer = null;
let lastQuery = "";
let previewMode = "wiki";
let currentOpenEntry = null;
let copyToastTimer = null;
let locationMap = null;
let locationMarkersLayer = null;
let mapMode = "selected";

siteLogo.addEventListener("error", () => {
  siteLogo.style.opacity = "0.5";
  siteLogo.title = "Add website/logo.png to display your logo.";
});

function escapeHtml(str) {
  return str
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function loadWebsiteConfig() {
  try {
    const response = await fetch(CONFIG_URL, { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const parsed = await response.json();
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return;
    }
    if (typeof parsed.datasetVersion === "string" && parsed.datasetVersion.trim()) {
      ROOT_FOLDER = parsed.datasetVersion.trim();
    }
  } catch {
    // Keep defaults if config cannot be loaded.
  }
}

function updateStatus(text) {
  statusEl.textContent = text;
}

function updateHomeStatus(text) {
  homeStatusEl.textContent = text;
}

function updateHomeSubtitle(text) {
  homeSubtitleEl.textContent = text;
}

function setLandingVisible(visible) {
  landingMessageEl.hidden = !visible;
  statusEl.style.display = visible ? "none" : "block";
}

function setToolsDropdown(open) {
  toolsDropdownEl.hidden = !open;
  toolsToggleBtn.setAttribute("aria-expanded", String(open));
}

function setCombinerModal(open) {
  combinerModal.hidden = !open;
}

function updatePreviewControlsState() {
  const hasSelection = Boolean(currentOpenEntry);
  togglePreviewFormatBtn.disabled = !hasSelection;
  copyPreviewBtn.disabled = !hasSelection;
}

function getPreviewText(entry) {
  if (previewMode === "coords") {
    return `${entry.x} ${entry.y} ${entry.z}`;
  }

  const previewData = {
    x: toNumberOrString(entry.x),
    y: toNumberOrString(entry.y),
    z: toNumberOrString(entry.z)
  };
  return `${JSON.stringify(previewData, null, 2)}\n`;
}

function updatePreviewModeButtonLabel() {
  togglePreviewFormatBtn.textContent = previewMode === "wiki" ? "Wiki" : "Coords";
}

function showCopyToast(message, isError = false) {
  if (!copyToastEl) {
    return;
  }
  if (copyToastTimer) {
    clearTimeout(copyToastTimer);
  }
  copyToastEl.textContent = message;
  copyToastEl.classList.toggle("error", isError);
  copyToastEl.hidden = false;
  requestAnimationFrame(() => {
    copyToastEl.classList.add("show");
  });
  copyToastTimer = setTimeout(() => {
    copyToastEl.classList.remove("show");
    setTimeout(() => {
      copyToastEl.hidden = true;
    }, 200);
  }, 1800);
}

function updateCombineButtonState() {
  const count = currentFiltered.length;
  combineBtn.disabled = count === 0;
  combineBtn.textContent = count > 0 ? `Combine (${count.toLocaleString()})` : "Combine";
}

function updateMapModeButtonLabel() {
  if (!toggleMapModeBtn) {
    return;
  }
  toggleMapModeBtn.textContent = mapMode === "selected" ? "Map: Selected" : "Map: Filtered";
}

function initLocationMap() {
  if (!locationMapEl || typeof window.L === "undefined") {
    return;
  }
  if (locationMap) {
    return;
  }

  const bounds = [{ lon: 0, lat: -100800 }, { lon: 302400, lat: 201600 }];
  const mult = 6144 / 302400 / 16;
  const dragonwildsCRS = window.L.extend({}, window.L.CRS.Simple, {
    projection: window.L.Projection.LonLat,
    transformation: new window.L.Transformation(mult, 0, mult, mult * 100800)
  });

  locationMap = window.L.map(locationMapEl, {
    crs: dragonwildsCRS,
    maxBounds: bounds,
    zoom: 2,
    minZoom: 0.5,
    maxZoom: 4,
    zoomSnap: 0.5,
    attributionControl: false
  });

  window.L.tileLayer("https://maps.runescape.wiki/dw/tiles/{z}/{x}_{y}.png").addTo(locationMap);
  locationMarkersLayer = window.L.layerGroup().addTo(locationMap);
  locationMap.fitBounds(bounds);
}

function entryToLatLng(entry) {
  const x = Number.parseFloat(String(entry.x));
  const y = Number.parseFloat(String(entry.y));
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }
  // Dragonwilds map works as lat=y, lng=x (same axis swap used by wiki center examples).
  return [y, x];
}

function syncMapMarkers() {
  if (!locationMap || !locationMarkersLayer) {
    return;
  }

  locationMarkersLayer.clearLayers();
  const sourceEntries = mapMode === "filtered"
    ? currentFiltered.slice(0, MAX_MAP_MARKERS)
    : (currentOpenEntry ? [currentOpenEntry] : []);
  const bounds = [];

  for (const entry of sourceEntries) {
    const latLng = entryToLatLng(entry);
    if (!latLng) {
      continue;
    }
    bounds.push(latLng);
    const marker = window.L.marker(latLng);
    marker.bindPopup(
      `<strong class="map-popup-title">${escapeHtml(entry.name)}</strong><br/>X: ${escapeHtml(String(entry.x))}<br/>Y: ${escapeHtml(String(entry.y))}`
    );
    marker.addTo(locationMarkersLayer);
  }

  if (!bounds.length) {
    return;
  }

  if (mapMode === "selected") {
    const [lat, lng] = bounds[0];
    locationMap.setView([lat, lng], Math.max(locationMap.getZoom(), 2.5));
    const firstMarker = locationMarkersLayer.getLayers()[0];
    if (firstMarker) {
      firstMarker.openPopup();
    }
  } else {
    locationMap.fitBounds(bounds, { padding: [24, 24] });
  }

  locationMap.invalidateSize();
}

function setActiveButton(buttonEl) {
  if (currentActiveBtn) {
    currentActiveBtn.classList.remove("active");
  }
  if (buttonEl) {
    buttonEl.classList.add("active");
  }
  currentActiveBtn = buttonEl;
}

function setSelectedMatch(index) {
  if (currentMatches.length === 0) {
    selectedMatchIndex = -1;
    setActiveButton(null);
    return;
  }

  selectedMatchIndex = Math.max(0, Math.min(index, currentMatches.length - 1));
  const button = resultsEl.querySelector(`button[data-idx="${selectedMatchIndex}"]`);
  if (!button) {
    return;
  }

  setActiveButton(button);
  button.scrollIntoView({ block: "nearest" });
}

function openLocation(entry) {
  currentOpenEntry = entry;
  selectedPathEl.textContent = entry.name;
  fileContentEl.textContent = getPreviewText(entry);
  updatePreviewControlsState();
  syncMapMarkers();
}

function openMatchByIndex(index) {
  if (index < 0 || index >= currentMatches.length) {
    return;
  }
  setSelectedMatch(index);
  openLocation(currentMatches[index]);
}

function parseCoordinates(value) {
  const parts = String(value).trim().split(/\s+/);
  const [x = "", y = "", z = ""] = parts;
  return { x, y, z };
}

function toNumberOrString(value) {
  const parsed = Number.parseFloat(String(value));
  return Number.isFinite(parsed) ? parsed : value;
}

function sanitizeForFilename(input) {
  const cleaned = input
    .trim()
    .replaceAll(/\s+/g, "")
    .replaceAll(/[^a-zA-Z0-9_-]/g, "");
  return cleaned || "combined";
}

function downloadCombinedLocationData() {
  const includeNames = includeNamesInput.checked;
  const includeZ = includeZInput.checked;

  const payload = currentFiltered.map((entry) => {
    const out = {
      x: toNumberOrString(entry.x),
      y: toNumberOrString(entry.y)
    };
    if (includeZ) {
      out.z = toNumberOrString(entry.z);
    }
    if (includeNames) {
      out.name = entry.name;
    }
    return out;
  });

  const fileName = `${sanitizeForFilename(lastQuery)}LocationData.json`;
  const blob = new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

function renderResults(matches) {
  resultsEl.innerHTML = "";
  currentActiveBtn = null;

  if (matches.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No matching locations.";
    li.style.color = "#8ca0b3";
    li.style.padding = "0.75rem";
    resultsEl.appendChild(li);
    return;
  }

  const fragment = document.createDocumentFragment();
  matches.forEach((entry, idx) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.textContent = entry.name;
    btn.title = entry.name;
    btn.type = "button";
    btn.dataset.idx = String(idx);
    btn.addEventListener("click", () => openMatchByIndex(idx));
    li.appendChild(btn);
    fragment.appendChild(li);
  });
  resultsEl.appendChild(fragment);
}

function filterAndRender() {
  const queryRaw = searchInput.value.trim();
  const query = queryRaw.toLowerCase();
  lastQuery = queryRaw;
  if (!query) {
    currentMatches = [];
    currentFiltered = [];
    selectedMatchIndex = -1;
    currentOpenEntry = null;
    setActiveButton(null);
    resultsViewer.classList.remove("visible");
    setLandingVisible(true);
    resultsEl.innerHTML = "";
    selectedPathEl.textContent = "Select a location";
    fileContentEl.textContent = "Search and click a location to preview XYZ coordinates.";
    updatePreviewControlsState();
    updateCombineButtonState();
    syncMapMarkers();
    return;
  }

  const matches = locations.filter((entry) => (
    entry.nameLower.includes(query) || entry.coordsLower.includes(query)
  ));
  currentFiltered = matches;
  currentMatches = matches.slice(0, MAX_RESULTS);
  renderResults(currentMatches);
  resultsViewer.classList.add("visible");
  setLandingVisible(false);
  setSelectedMatch(0);

  const capped = matches.length > MAX_RESULTS ? ` (showing first ${MAX_RESULTS.toLocaleString()})` : "";
  updateStatus(`${matches.length.toLocaleString()} matches${capped}.`);
  updateCombineButtonState();
  syncMapMarkers();
}

function triggerDebouncedSearch() {
  const hasInput = searchInput.value.trim().length > 0;
  setLandingVisible(!hasInput);

  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(filterAndRender, SEARCH_DEBOUNCE_MS);
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed";
  textArea.style.opacity = "0";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  document.execCommand("copy");
  document.body.removeChild(textArea);
}

async function handleCopyPreview() {
  if (!currentOpenEntry) {
    return;
  }

  try {
    await copyTextToClipboard(getPreviewText(currentOpenEntry));
    showCopyToast("Copied to clipboard.");
  } catch {
    showCopyToast("Unable to copy preview text.", true);
  }
}

function handleSearchKeyDown(event) {
  if (event.key === "Escape") {
    searchInput.value = "";
    filterAndRender();
    return;
  }

  if (!resultsViewer.classList.contains("visible") || currentMatches.length === 0) {
    return;
  }

  if (event.key === "ArrowDown") {
    event.preventDefault();
    setSelectedMatch(selectedMatchIndex + 1);
    return;
  }

  if (event.key === "ArrowUp") {
    event.preventDefault();
    setSelectedMatch(selectedMatchIndex - 1);
    return;
  }

  if (event.key === "Enter") {
    event.preventDefault();
    if (selectedMatchIndex >= 0) {
      openMatchByIndex(selectedMatchIndex);
    }
  }
}

async function init() {
  await loadWebsiteConfig();
  try {
    initLocationMap();

    const response = await fetch(DATA_URL);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const parsed = await response.json();
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("Invalid LocationData JSON shape");
    }

    locations = Object.entries(parsed).map(([name, coords]) => {
      const xyz = parseCoordinates(coords);
      return {
        name,
        nameLower: name.toLowerCase(),
        coords: String(coords),
        coordsLower: String(coords).toLowerCase(),
        x: xyz.x,
        y: xyz.y,
        z: xyz.z
      };
    });

    const loaded = `${locations.length.toLocaleString()} locations`;
    updateStatus(loaded);
    updateHomeStatus(loaded);
    updateHomeSubtitle(`Browse ${locations.length.toLocaleString()} Locations in ${ROOT_FOLDER}`);
    setLandingVisible(true);
  } catch (error) {
    const errorText = `Failed to load LocationData: ${error instanceof Error ? error.message : "Unknown error"}`;
    updateStatus(errorText);
    updateHomeStatus(errorText);
    updateHomeSubtitle(`Browse Locations in ${ROOT_FOLDER}`);
    setLandingVisible(true);
  }

  // Leaflet may still be loading when this script starts.
  if (!locationMap && locationMapEl) {
    window.setTimeout(() => {
      initLocationMap();
      syncMapMarkers();
    }, 300);
  }
}

searchInput.addEventListener("input", triggerDebouncedSearch);
searchInput.addEventListener("keydown", handleSearchKeyDown);

toolsToggleBtn.addEventListener("click", () => {
  setToolsDropdown(toolsDropdownEl.hidden);
});
document.addEventListener("click", (event) => {
  if (!(event.target instanceof Node)) {
    return;
  }
  if (!toolsDropdownEl.contains(event.target) && !toolsToggleBtn.contains(event.target)) {
    setToolsDropdown(false);
  }
});

combineBtn.addEventListener("click", () => {
  includeNamesInput.checked = false;
  includeZInput.checked = false;
  setCombinerModal(true);
});

combinerCancelBtn.addEventListener("click", () => {
  setCombinerModal(false);
});

combinerCreateBtn.addEventListener("click", () => {
  downloadCombinedLocationData();
  setCombinerModal(false);
});

togglePreviewFormatBtn.addEventListener("click", () => {
  previewMode = previewMode === "wiki" ? "coords" : "wiki";
  updatePreviewModeButtonLabel();
  if (currentOpenEntry) {
    fileContentEl.textContent = getPreviewText(currentOpenEntry);
  }
});

toggleMapModeBtn.addEventListener("click", () => {
  mapMode = mapMode === "selected" ? "filtered" : "selected";
  updateMapModeButtonLabel();
  syncMapMarkers();
});

copyPreviewBtn.addEventListener("click", () => {
  void handleCopyPreview();
});

combinerModal.addEventListener("click", (event) => {
  if (event.target === combinerModal) {
    setCombinerModal(false);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !combinerModal.hidden) {
    setCombinerModal(false);
  }
});

updatePreviewModeButtonLabel();
updateMapModeButtonLabel();
updatePreviewControlsState();
init();
