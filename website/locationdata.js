const DATA_URL = "./tools/LocationData/LocationData.json";
const ROOT_FOLDER = "0.11.0.3";
const MAX_RESULTS = 400;
const SEARCH_DEBOUNCE_MS = 90;

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

let locations = [];
let currentMatches = [];
let currentFiltered = [];
let selectedMatchIndex = -1;
let currentActiveBtn = null;
let debounceTimer = null;
let lastQuery = "";

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

function updateCombineButtonState() {
  const count = currentFiltered.length;
  combineBtn.disabled = count === 0;
  combineBtn.textContent = count > 0 ? `Combine (${count.toLocaleString()})` : "Combine";
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
  selectedPathEl.textContent = entry.name;
  const pretty = `X: ${entry.x}\nY: ${entry.y}\nZ: ${entry.z}`;
  fileContentEl.textContent = pretty;
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
    setActiveButton(null);
    resultsViewer.classList.remove("visible");
    setLandingVisible(true);
    resultsEl.innerHTML = "";
    selectedPathEl.textContent = "Select a location";
    fileContentEl.textContent = "Search and click a location to preview XYZ coordinates.";
    updateCombineButtonState();
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
}

function triggerDebouncedSearch() {
  const hasInput = searchInput.value.trim().length > 0;
  setLandingVisible(!hasInput);

  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(filterAndRender, SEARCH_DEBOUNCE_MS);
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
  try {
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

    const loaded = "Location Data Loaded.";
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

init();
