const INDEX_URL = "./file-index.json";
const CONFIG_URL = "./data.config.json";
let BRANCH = "main";
let ROOT_FOLDER = "0.11.0.3";
const MAX_RESULTS = 300;
const SEARCH_DEBOUNCE_MS = 100;
const TEXT_EXTENSIONS = new Set([
  ".json",
  ".txt",
  ".xml",
  ".ini",
  ".cfg",
  ".md",
  ".csv",
  ".yaml",
  ".yml",
  ".js",
  ".ts",
  ".py",
  ".sh",
  ".bat",
  ".ps1",
  ".log"
]);
const IMAGE_EXTENSIONS = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".gif",
  ".bmp",
  ".svg",
  ".ico"
]);

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
const togglePathsBtn = document.getElementById("toggle-paths");
const copyGithubUrlBtn = document.getElementById("copy-github-url");
const copyRawUrlBtn = document.getElementById("copy-raw-url");
const downloadFileBtn = document.getElementById("download-file");
const toolsToggleBtn = document.getElementById("tools-toggle");
const toolsDropdownEl = document.getElementById("tools-dropdown");

let indexedFiles = [];
let currentActiveBtn = null;
let currentMatches = [];
let selectedMatchIndex = -1;
let debounceTimer = null;
let currentQueryTokens = [];
let showFullPaths = false;
let currentOpenPath = null;
const DEFAULT_REPO_CONTEXT = { owner: "RSDWArchive", repo: "RSDWArchive" };

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

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeFilePath(path) {
  return path.replaceAll("\\", "/").replace(/^(\.\/|\.\.\/)+/, "").replace(/^\/+/, "");
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
    if (typeof parsed.repoBranch === "string" && parsed.repoBranch.trim()) {
      BRANCH = parsed.repoBranch.trim();
    }
    if (typeof parsed.datasetVersion === "string" && parsed.datasetVersion.trim()) {
      ROOT_FOLDER = parsed.datasetVersion.trim();
    }
  } catch {
    // Keep defaults if config cannot be loaded.
  }
}

function getRepoContext() {
  const host = window.location.hostname;
  const pathParts = window.location.pathname.split("/").filter(Boolean);
  if (!host.endsWith("github.io") || pathParts.length === 0) {
    return null;
  }

  const owner = host.slice(0, host.indexOf(".github.io"));
  const repo = pathParts[0];
  return { owner, repo };
}

function buildRawGithubUrl(filePath) {
  const context = getRepoContext() || DEFAULT_REPO_CONTEXT;
  return `https://raw.githubusercontent.com/${context.owner}/${context.repo}/${BRANCH}/${encodeURI(filePath)}`;
}

function buildGithubTreeUrl(filePath) {
  const context = getRepoContext() || DEFAULT_REPO_CONTEXT;
  return `https://github.com/${context.owner}/${context.repo}/tree/${BRANCH}/${encodeURI(filePath)}`;
}

function buildLocalUrl(filePath) {
  return `../${encodeURI(filePath)}`;
}

function isTextFile(filePath) {
  const extIndex = filePath.lastIndexOf(".");
  if (extIndex === -1) {
    return false;
  }
  return TEXT_EXTENSIONS.has(filePath.slice(extIndex).toLowerCase());
}

function isJsonFile(filePath) {
  return filePath.toLowerCase().endsWith(".json");
}

function isImageFile(filePath) {
  const extIndex = filePath.lastIndexOf(".");
  if (extIndex === -1) {
    return false;
  }
  return IMAGE_EXTENSIONS.has(filePath.slice(extIndex).toLowerCase());
}

function formatJsonForPreview(rawText) {
  try {
    const parsed = JSON.parse(rawText);
    return escapeHtml(JSON.stringify(parsed, null, 2));
  } catch {
    return escapeHtml(rawText);
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
  if (!toolsDropdownEl || !toolsToggleBtn) {
    return;
  }
  toolsDropdownEl.hidden = !open;
  toolsToggleBtn.setAttribute("aria-expanded", String(open));
}

function updateContentActionState() {
  const hasSelection = Boolean(currentOpenPath);
  copyGithubUrlBtn.disabled = !hasSelection;
  copyRawUrlBtn.disabled = !hasSelection;
  downloadFileBtn.disabled = !hasSelection;
}

function basename(path) {
  const idx = path.lastIndexOf("/");
  return idx === -1 ? path : path.slice(idx + 1);
}

function displayPath(path) {
  return showFullPaths ? path : basename(path);
}

function splitTokens(query) {
  return query.trim().toLowerCase().split(/\s+/).filter(Boolean);
}

function scoreEntry(entry, query, tokens) {
  if (tokens.length === 0) {
    return -1;
  }

  for (const token of tokens) {
    if (!entry.pathLower.includes(token)) {
      return -1;
    }
  }

  let score = 0;

  if (entry.baseLower === query) {
    score += 1400;
  } else if (entry.baseLower.startsWith(query)) {
    score += 1000;
  } else if (entry.pathLower === query) {
    score += 900;
  }

  for (const token of tokens) {
    if (entry.baseLower === token) {
      score += 360;
    } else if (entry.baseLower.startsWith(token)) {
      score += 240;
    } else if (entry.baseLower.includes(token)) {
      score += 120;
    }

    const segmentMatch = entry.pathLower.includes(`/${token}`);
    score += segmentMatch ? 60 : 20;
  }

  score += Math.max(0, 90 - Math.floor(entry.path.length * 0.03));

  return score;
}

function highlightMatches(path, tokens) {
  if (tokens.length === 0) {
    return escapeHtml(path);
  }

  const normalizedTokens = [...new Set(tokens.map((token) => token.trim().toLowerCase()).filter(Boolean))]
    .sort((a, b) => b.length - a.length);

  const ranges = [];
  const lowerPath = path.toLowerCase();

  for (const token of normalizedTokens) {
    const matcher = new RegExp(escapeRegex(token), "gi");
    let match = matcher.exec(lowerPath);
    while (match) {
      ranges.push({ start: match.index, end: match.index + token.length });
      match = matcher.exec(lowerPath);
    }
  }

  if (ranges.length === 0) {
    return escapeHtml(path);
  }

  ranges.sort((a, b) => a.start - b.start);
  const merged = [];
  for (const range of ranges) {
    const prev = merged[merged.length - 1];
    if (!prev || range.start > prev.end) {
      merged.push({ ...range });
    } else {
      prev.end = Math.max(prev.end, range.end);
    }
  }

  let output = "";
  let cursor = 0;
  for (const range of merged) {
    output += escapeHtml(path.slice(cursor, range.start));
    output += `<mark>${escapeHtml(path.slice(range.start, range.end))}</mark>`;
    cursor = range.end;
  }
  output += escapeHtml(path.slice(cursor));
  return output;
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

function renderResults(matches, tokens) {
  resultsEl.innerHTML = "";
  currentActiveBtn = null;

  if (matches.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No matching files.";
    li.style.color = "#8ca0b3";
    li.style.padding = "0.75rem";
    resultsEl.appendChild(li);
    return;
  }

  const fragment = document.createDocumentFragment();
  matches.forEach((entry, idx) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    const shownPath = displayPath(entry.path);
    btn.innerHTML = highlightMatches(shownPath, tokens);
    btn.title = entry.path;
    btn.type = "button";
    btn.dataset.idx = String(idx);
    btn.addEventListener("click", () => openMatchByIndex(idx));
    li.appendChild(btn);
    fragment.appendChild(li);
  });
  resultsEl.appendChild(fragment);
}

async function openMatchByIndex(index) {
  if (index < 0 || index >= currentMatches.length) {
    return;
  }
  setSelectedMatch(index);
  const entry = currentMatches[index];
  await openFile(entry.path);
}

async function openFile(filePath) {
  currentOpenPath = filePath;
  updateContentActionState();
  selectedPathEl.textContent = displayPath(filePath);
  fileContentEl.textContent = "Loading...";
  const localUrl = buildLocalUrl(filePath);
  const githubRawUrl = buildRawGithubUrl(filePath);
  const candidates = [localUrl, githubRawUrl].filter(Boolean);

  if (isImageFile(filePath)) {
    for (const url of candidates) {
      const loaded = await new Promise((resolve) => {
        const img = new Image();
        img.onload = () => resolve({ ok: true, url });
        img.onerror = () => resolve({ ok: false, url });
        img.src = url;
      });
      if (loaded.ok) {
        fileContentEl.innerHTML = `<img src="${loaded.url}" alt="${filePath}" /><p class="preview-note">Image preview</p>`;
        return;
      }
    }

    fileContentEl.textContent =
      "Unable to load image preview from the current page context.\n" +
      "Use GitHub Pages or run a local web server from the repo root (not file://).";
    return;
  }

  if (!isTextFile(filePath)) {
    fileContentEl.textContent = githubRawUrl
      ? `Binary/non-text file. Open directly:\n${githubRawUrl}`
      : `Binary/non-text file. Open directly:\n${localUrl}`;
    return;
  }

  for (const url of candidates) {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        continue;
      }
      const text = await response.text();
      fileContentEl.innerHTML = isJsonFile(filePath) ? formatJsonForPreview(text) : escapeHtml(text);
      return;
    } catch {
      // Try the next source (e.g. local static host or GitHub raw).
    }
  }

  fileContentEl.textContent =
    "Unable to preview this file from the current page context.\n" +
    "Use GitHub Pages or run a local web server from the repo root (not file://).";
}

function handleSearch() {
  const query = searchInput.value.trim().toLowerCase();
  const tokens = splitTokens(query);
  currentQueryTokens = tokens;

  if (!query) {
    currentMatches = [];
    selectedMatchIndex = -1;
    setActiveButton(null);
    resultsViewer.classList.remove("visible");
    setLandingVisible(true);
    resultsEl.innerHTML = "";
    currentOpenPath = null;
    updateContentActionState();
    selectedPathEl.textContent = "Select a file";
    fileContentEl.textContent = "Search and click a file to preview its content.";
    const loadedText = "Archive Loaded.";
    const subtitleText = `Browse ${indexedFiles.length.toLocaleString()} Files in ${ROOT_FOLDER}`;
    updateStatus(loadedText);
    updateHomeStatus(loadedText);
    updateHomeSubtitle(subtitleText);
    return;
  }

  const scored = [];
  for (const entry of indexedFiles) {
    const score = scoreEntry(entry, query, tokens);
    if (score >= 0) {
      scored.push({ entry, score });
    }
  }

  scored.sort((a, b) => {
    if (b.score !== a.score) {
      return b.score - a.score;
    }
    return a.entry.path.localeCompare(b.entry.path);
  });

  const totalMatches = scored.length;
  currentMatches = scored.slice(0, MAX_RESULTS).map((item) => item.entry);

  renderResults(currentMatches, currentQueryTokens);
  resultsViewer.classList.add("visible");
  setLandingVisible(false);
  setSelectedMatch(0);

  const capped = totalMatches > MAX_RESULTS
    ? ` (showing first ${MAX_RESULTS.toLocaleString()})`
    : "";
  updateStatus(`${totalMatches.toLocaleString()} matches${capped}.`);
}

function applyPathDisplayMode() {
  togglePathsBtn.textContent = showFullPaths ? "Hide Paths" : "Show Paths";

  if (!currentMatches.length) {
    if (currentOpenPath) {
      selectedPathEl.textContent = displayPath(currentOpenPath);
    }
    return;
  }

  const selectedBefore = selectedMatchIndex;
  renderResults(currentMatches, currentQueryTokens);
  if (selectedBefore >= 0) {
    setSelectedMatch(selectedBefore);
  }

  if (currentOpenPath) {
    selectedPathEl.textContent = displayPath(currentOpenPath);
  }
}

function triggerDebouncedSearch() {
  const hasInput = searchInput.value.trim().length > 0;
  setLandingVisible(!hasInput);

  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(handleSearch, SEARCH_DEBOUNCE_MS);
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

function getCurrentRawUrl() {
  if (!currentOpenPath) {
    return null;
  }
  return buildRawGithubUrl(currentOpenPath);
}

async function handleCopyUrl() {
  if (!currentOpenPath) {
    return;
  }
  const url = buildGithubTreeUrl(currentOpenPath);
  try {
    await copyTextToClipboard(url);
    const oldText = copyGithubUrlBtn.textContent;
    copyGithubUrlBtn.textContent = "Copied!";
    setTimeout(() => {
      copyGithubUrlBtn.textContent = oldText;
    }, 1200);
  } catch {
    updateStatus("Unable to copy GitHub URL in this browser context.");
  }
}

async function handleCopyRawUrl() {
  const url = getCurrentRawUrl();
  if (!url) {
    return;
  }
  try {
    await copyTextToClipboard(url);
    const oldText = copyRawUrlBtn.textContent;
    copyRawUrlBtn.textContent = "Copied!";
    setTimeout(() => {
      copyRawUrlBtn.textContent = oldText;
    }, 1200);
  } catch {
    updateStatus("Unable to copy raw URL in this browser context.");
  }
}

async function handleDownloadFile() {
  if (!currentOpenPath) {
    return;
  }
  const rawUrl = buildRawGithubUrl(currentOpenPath);
  try {
    const response = await fetch(rawUrl);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = basename(currentOpenPath);
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(objectUrl);
  } catch {
    window.open(rawUrl, "_blank", "noopener,noreferrer");
  }
}

function handleSearchKeyDown(event) {
  if (event.key === "Escape") {
    searchInput.value = "";
    handleSearch();
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
      void openMatchByIndex(selectedMatchIndex);
    }
  }
}

async function init() {
  await loadWebsiteConfig();
  try {
    const response = await fetch(INDEX_URL);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const parsed = await response.json();
    if (!Array.isArray(parsed.files)) {
      throw new Error("Invalid file-index.json format");
    }

    indexedFiles = parsed.files
      .filter((path) => typeof path === "string")
      .map((path) => normalizeFilePath(path))
      .filter((path) => path.startsWith(`${ROOT_FOLDER}/`))
      .map((path) => ({
        path,
        pathLower: path.toLowerCase(),
        base: basename(path),
        baseLower: basename(path).toLowerCase()
      }));
    const loadedText = "Archive Loaded.";
    const subtitleText = `Browse ${indexedFiles.length.toLocaleString()} Files in ${ROOT_FOLDER}`;
    updateStatus(loadedText);
    updateHomeStatus(loadedText);
    updateHomeSubtitle(subtitleText);
    setLandingVisible(true);
  } catch (error) {
    const errorText = `Failed to load file index: ${error instanceof Error ? error.message : "Unknown error"}`;
    updateStatus(errorText);
    updateHomeStatus(errorText);
    updateHomeSubtitle(`Search Files in ${ROOT_FOLDER}`);
    setLandingVisible(true);
  }
}

searchInput.addEventListener("input", triggerDebouncedSearch);
searchInput.addEventListener("keydown", handleSearchKeyDown);
togglePathsBtn.addEventListener("click", () => {
  showFullPaths = !showFullPaths;
  applyPathDisplayMode();
});
copyGithubUrlBtn.addEventListener("click", () => {
  void handleCopyUrl();
});
copyRawUrlBtn.addEventListener("click", () => {
  void handleCopyRawUrl();
});
downloadFileBtn.addEventListener("click", () => {
  void handleDownloadFile();
});

if (toolsToggleBtn && toolsDropdownEl) {
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
}

updateContentActionState();
applyPathDisplayMode();
init();
