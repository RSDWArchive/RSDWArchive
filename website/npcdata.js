const DATA_URL = "./tools/NPCData/NPCData.json";
const MAX_RESULTS = 500;
const SEARCH_DEBOUNCE_MS = 90;

const searchInput = document.getElementById("file-search");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const resultsViewer = document.querySelector(".results-viewer");
const landingMessageEl = document.getElementById("landing-message");
const homeStatusEl = document.getElementById("home-status");
const homeSubtitleEl = document.getElementById("home-subtitle");
const listTitleEl = document.getElementById("list-title");
const selectedPathEl = document.getElementById("selected-path");
const fileContentEl = document.getElementById("file-content");
const siteLogo = document.getElementById("site-logo");
const toolsToggleBtn = document.getElementById("tools-toggle");
const toolsDropdownEl = document.getElementById("tools-dropdown");
const tabNpcsBtn = document.getElementById("tab-npcs");
const tabDifficultyBtn = document.getElementById("tab-difficulty");
const tabLootRowsBtn = document.getElementById("tab-loot-rows");
const togglePreviewFormatBtn = document.getElementById("toggle-preview-format");
const copyPreviewBtn = document.getElementById("copy-preview");
const copyToastEl = document.getElementById("copy-toast");

const VIEW_NPCS = "npcs";
const VIEW_DIFFICULTY = "difficulty";
const VIEW_LOOT_ROWS = "lootRows";
const PREVIEW_FORMAT_JSON = "json";
const PREVIEW_FORMAT_WIKI = "wiki";

let npcData = null;
let npcEntries = [];
let difficultyEntries = [];
let lootRowEntries = [];
let currentView = VIEW_NPCS;
let currentMatches = [];
let selectedMatchIndex = -1;
let currentActiveBtn = null;
let currentOpenEntry = null;
let debounceTimer = null;
let previewFormat = PREVIEW_FORMAT_JSON;
let copyToastTimer = null;

siteLogo.addEventListener("error", () => {
  siteLogo.style.opacity = "0.5";
  siteLogo.title = "Add website/logo.png to display your logo.";
});

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

function updatePreviewControlsState() {
  const hasSelection = Boolean(currentOpenEntry);
  togglePreviewFormatBtn.disabled = !hasSelection;
  copyPreviewBtn.disabled = !hasSelection;
}

function updatePreviewModeButtonLabel() {
  togglePreviewFormatBtn.textContent = previewFormat === PREVIEW_FORMAT_JSON ? "JSON" : "Wiki";
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

function inferAggressiveText(gameplayTags) {
  if (!Array.isArray(gameplayTags)) {
    return null;
  }
  if (gameplayTags.includes("AI.Aggressive")) {
    return "Yes";
  }
  if (gameplayTags.includes("AI.Passive")) {
    return "No";
  }
  return null;
}

function inferWeaknessResistance(affinities) {
  const out = { weakness: [], resistance: [] };
  if (!Array.isArray(affinities)) {
    return out;
  }
  for (const entry of affinities) {
    if (!entry || typeof entry !== "object") {
      continue;
    }
    const affinity = String(entry.affinity || "");
    const tag = String(entry.damageTypeTag || "");
    const short = tag.split(".").pop() || tag;
    if (affinity.endsWith("Weakness")) {
      out.weakness.push(short);
    } else if (affinity.endsWith("Resistance")) {
      out.resistance.push(short);
    }
  }
  out.weakness = [...new Set(out.weakness)].sort();
  out.resistance = [...new Set(out.resistance)].sort();
  return out;
}

function buildNpcEntries() {
  const npcs = npcData.npcs || {};
  return Object.entries(npcs)
    .map(([id, value]) => {
      const displayName = value.displayName || id;
      const difficultyTag = value.classification?.difficultyTag || "";
      const lootRow = value.loot?.enemyLootRowName || "";
      const gameplayTags = Array.isArray(value.classification?.gameplayTags) ? value.classification.gameplayTags : [];
      return {
        key: `${displayName} (${id})`,
        id,
        type: VIEW_NPCS,
        data: value,
        searchBlob: [
          id,
          displayName,
          difficultyTag,
          lootRow,
          value.meta?.aiDataRowName || "",
          value.combat?.combatAttacksTable || "",
          ...gameplayTags
        ].join(" ").toLowerCase()
      };
    })
    .sort((a, b) => a.key.localeCompare(b.key));
}

function buildDifficultyEntries() {
  const byDifficulty = npcData.indexes?.byDifficultyTag || {};
  return Object.entries(byDifficulty)
    .map(([tag, ids]) => ({
      key: tag,
      type: VIEW_DIFFICULTY,
      data: { npcIds: Array.isArray(ids) ? ids : [] },
      searchBlob: [tag, ...(Array.isArray(ids) ? ids : [])].join(" ").toLowerCase()
    }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

function buildLootRowEntries() {
  const byLootRow = npcData.indexes?.byEnemyLootRowName || {};
  return Object.entries(byLootRow)
    .map(([lootRow, ids]) => ({
      key: lootRow,
      type: VIEW_LOOT_ROWS,
      data: { npcIds: Array.isArray(ids) ? ids : [] },
      searchBlob: [lootRow, ...(Array.isArray(ids) ? ids : [])].join(" ").toLowerCase()
    }))
    .sort((a, b) => a.key.localeCompare(b.key));
}

function getCurrentEntries() {
  if (currentView === VIEW_DIFFICULTY) {
    return difficultyEntries;
  }
  if (currentView === VIEW_LOOT_ROWS) {
    return lootRowEntries;
  }
  return npcEntries;
}

function getLabelForView() {
  if (currentView === VIEW_DIFFICULTY) {
    return "Difficulty";
  }
  if (currentView === VIEW_LOOT_ROWS) {
    return "Loot Rows";
  }
  return "NPCs";
}

function getPlaceholderForView() {
  if (currentView === VIEW_DIFFICULTY) {
    return "Search Difficulty Tags...";
  }
  if (currentView === VIEW_LOOT_ROWS) {
    return "Search Loot Rows...";
  }
  return "Search NPCs...";
}

function renderResults(matches) {
  resultsEl.innerHTML = "";
  currentActiveBtn = null;

  if (matches.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No matching entries.";
    li.style.color = "#8ca0b3";
    li.style.padding = "0.75rem";
    resultsEl.appendChild(li);
    return;
  }

  const fragment = document.createDocumentFragment();
  matches.forEach((entry, idx) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.textContent = entry.key;
    btn.title = entry.key;
    btn.type = "button";
    btn.dataset.idx = String(idx);
    btn.addEventListener("click", () => openMatchByIndex(idx));
    li.appendChild(btn);
    fragment.appendChild(li);
  });
  resultsEl.appendChild(fragment);
}

function renderNpcPreview(entry) {
  const out = {
    id: entry.id,
    displayName: entry.data.displayName || entry.id,
    classification: entry.data.classification || {},
    movement: entry.data.movement || {},
    combat: entry.data.combat || {},
    loot: entry.data.loot || {},
    meta: entry.data.meta || {},
    source: entry.data.source || {}
  };
  return `${JSON.stringify(out, null, 2)}\n`;
}

function renderDifficultyPreview(entry) {
  const out = {
    difficultyTag: entry.key,
    npcCount: entry.data.npcIds.length,
    npcIds: entry.data.npcIds
  };
  return `${JSON.stringify(out, null, 2)}\n`;
}

function renderLootRowPreview(entry) {
  const out = {
    enemyLootRowName: entry.key,
    npcCount: entry.data.npcIds.length,
    npcIds: entry.data.npcIds
  };
  return `${JSON.stringify(out, null, 2)}\n`;
}

function renderNpcWiki(entry) {
  const npc = entry.data || {};
  const name = npc.displayName || entry.id;
  const gameplayTags = Array.isArray(npc.classification?.gameplayTags) ? npc.classification.gameplayTags : [];
  const aggressive = inferAggressiveText(gameplayTags);
  const affinities = inferWeaknessResistance(npc.combat?.damageTypeAffinities);
  const lines = [
    `{{External|rs=${name}|os=${name}}}`,
    "{{Infobox Monster",
    `|name = ${name}`,
    `|image = ${name}.png`
  ];
  const difficultyTag = npc.classification?.difficultyTag;
  if (typeof difficultyTag === "string" && difficultyTag) {
    lines.push(`|race = ${difficultyTag.split(".").pop()}`);
  }
  const health = npc.combat?.maxHealth;
  if (typeof health === "number") {
    lines.push(`|health = ${Number.isInteger(health) ? String(health) : String(health)}`);
  }
  if (affinities.weakness.length > 0) {
    lines.push(`|weakness = ${affinities.weakness.join(", ")}`);
  }
  if (affinities.resistance.length > 0) {
    lines.push(`|resistance = ${affinities.resistance.join(", ")}`);
  }
  if (aggressive) {
    lines.push(`|aggressive = ${aggressive}`);
  }
  lines.push("}}");
  lines.push(`The '''${name}''' is a monster.`);
  return `${lines.join("\n")}\n`;
}

function renderDifficultyWiki(entry) {
  const lines = [
    `==${entry.key}==`,
    `* NPCs: ${entry.data.npcIds.length}`,
    ...entry.data.npcIds.map((id) => `* ${id}`)
  ];
  return `${lines.join("\n")}\n`;
}

function renderLootRowWiki(entry) {
  const lines = [
    `==${entry.key}==`,
    `* NPCs: ${entry.data.npcIds.length}`,
    ...entry.data.npcIds.map((id) => `* ${id}`)
  ];
  return `${lines.join("\n")}\n`;
}

function renderEntryPreview(entry) {
  if (previewFormat === PREVIEW_FORMAT_WIKI) {
    if (entry.type === VIEW_DIFFICULTY) {
      return renderDifficultyWiki(entry);
    }
    if (entry.type === VIEW_LOOT_ROWS) {
      return renderLootRowWiki(entry);
    }
    return renderNpcWiki(entry);
  }

  if (entry.type === VIEW_DIFFICULTY) {
    return renderDifficultyPreview(entry);
  }
  if (entry.type === VIEW_LOOT_ROWS) {
    return renderLootRowPreview(entry);
  }
  return renderNpcPreview(entry);
}

function openMatchByIndex(index) {
  if (index < 0 || index >= currentMatches.length) {
    return;
  }
  setSelectedMatch(index);
  const entry = currentMatches[index];
  currentOpenEntry = entry;
  selectedPathEl.textContent = entry.key;
  fileContentEl.textContent = renderEntryPreview(entry);
  updatePreviewControlsState();
}

function handleSearch() {
  const query = searchInput.value.trim().toLowerCase();
  const entries = getCurrentEntries();
  const label = getLabelForView();
  const filtered = query
    ? entries.filter((entry) => entry.searchBlob.includes(query))
    : entries;

  currentMatches = filtered.slice(0, MAX_RESULTS);
  renderResults(currentMatches);
  resultsViewer.classList.add("visible");
  setLandingVisible(false);

  selectedMatchIndex = -1;
  currentOpenEntry = null;
  selectedPathEl.textContent = "Select an entry";
  fileContentEl.textContent = "Search and click an entry to preview compiled NPC data.";
  updatePreviewControlsState();
  setSelectedMatch(0);

  const capped = filtered.length > MAX_RESULTS
    ? ` (showing first ${MAX_RESULTS.toLocaleString()})`
    : "";
  updateStatus(`${filtered.length.toLocaleString()} ${label.toLowerCase()}${capped}.`);
}

function triggerDebouncedSearch() {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(handleSearch, SEARCH_DEBOUNCE_MS);
}

function setView(view) {
  currentView = view;
  const label = getLabelForView();
  listTitleEl.textContent = label;
  searchInput.placeholder = getPlaceholderForView();

  const mapping = [
    [tabNpcsBtn, VIEW_NPCS],
    [tabDifficultyBtn, VIEW_DIFFICULTY],
    [tabLootRowsBtn, VIEW_LOOT_ROWS]
  ];
  for (const [button, buttonView] of mapping) {
    const active = view === buttonView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  }

  updateHomeSubtitle(`Browse ${getCurrentEntries().length.toLocaleString()} ${label}`);
  handleSearch();
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
      openMatchByIndex(selectedMatchIndex);
    }
  }
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
    await copyTextToClipboard(renderEntryPreview(currentOpenEntry));
    showCopyToast("Copied to clipboard.");
  } catch {
    showCopyToast("Unable to copy preview text.", true);
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
      throw new Error("Invalid NPCData JSON shape");
    }
    if (!parsed.npcs || !parsed.indexes) {
      throw new Error("NPCData JSON missing expected sections");
    }

    npcData = parsed;
    npcEntries = buildNpcEntries();
    difficultyEntries = buildDifficultyEntries();
    lootRowEntries = buildLootRowEntries();

    updateHomeStatus("NPC Data Loaded.");
    updateStatus("NPC Data Loaded.");
    updateHomeSubtitle(`Browse ${npcEntries.length.toLocaleString()} NPCs (dataset ${parsed.version || "unknown"})`);
    setView(VIEW_NPCS);
  } catch (error) {
    const errorText = `Failed to load NPCData: ${error instanceof Error ? error.message : "Unknown error"}`;
    updateHomeStatus(errorText);
    updateStatus(errorText);
    updateHomeSubtitle("Browse NPCs, difficulty tags, and loot row mappings");
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

tabNpcsBtn.addEventListener("click", () => {
  setView(VIEW_NPCS);
});
tabDifficultyBtn.addEventListener("click", () => {
  setView(VIEW_DIFFICULTY);
});
tabLootRowsBtn.addEventListener("click", () => {
  setView(VIEW_LOOT_ROWS);
});

togglePreviewFormatBtn.addEventListener("click", () => {
  previewFormat = previewFormat === PREVIEW_FORMAT_JSON ? PREVIEW_FORMAT_WIKI : PREVIEW_FORMAT_JSON;
  updatePreviewModeButtonLabel();
  if (currentOpenEntry) {
    fileContentEl.textContent = renderEntryPreview(currentOpenEntry);
  }
});

copyPreviewBtn.addEventListener("click", () => {
  void handleCopyPreview();
});

updatePreviewModeButtonLabel();
updatePreviewControlsState();
init();
