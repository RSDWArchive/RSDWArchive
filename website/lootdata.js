const DATA_URL = "./tools/LootData/LootData.json";
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
const tabEnemiesBtn = document.getElementById("tab-enemies");
const tabChestsBtn = document.getElementById("tab-chests");
const tabItemsBtn = document.getElementById("tab-items");
const togglePreviewFormatBtn = document.getElementById("toggle-preview-format");
const copyPreviewBtn = document.getElementById("copy-preview");
const copyToastEl = document.getElementById("copy-toast");

const VIEW_ENEMIES = "enemies";
const VIEW_CHESTS = "chests";
const VIEW_ITEMS = "items";
const PREVIEW_FORMAT_JSON = "json";
const PREVIEW_FORMAT_WIKI = "wiki";

let lootData = null;
let enemyEntries = [];
let chestEntries = [];
let itemEntries = [];
let currentView = VIEW_ENEMIES;
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

function buildEnemyEntries() {
  return Object.entries(lootData.enemies).map(([name, value]) => ({
    key: name,
    type: VIEW_ENEMIES,
    data: value,
    searchBlob: [
      name,
      ...value.sources.map((source) => `${source.fromTable} ${source.targetTable} ${source.targetRow}`),
      ...value.drops.map((drop) => `${drop.itemId} ${drop.itemDisplayName || ""} ${drop.itemObjectName}`)
    ].join(" ").toLowerCase()
  }));
}

function buildChestEntries() {
  return Object.entries(lootData.chests).map(([name, value]) => ({
    key: name,
    type: VIEW_CHESTS,
    data: value,
    searchBlob: [
      name,
      value.prefabRef?.row || "",
      ...(value.guaranteedSetRows || []),
      ...(value.additionalSetRows || []).map((entry) => entry.setRow || ""),
      ...(value.resolvedItems || []).map((entry) => `${entry.item?.itemId || ""} ${entry.item?.itemDisplayName || ""}`)
    ].join(" ").toLowerCase()
  }));
}

function buildItemEntries() {
  const enemyIndex = lootData.indexes.itemToEnemies || {};
  const chestIndex = lootData.indexes.itemToChestProfiles || {};
  const ids = new Set([...Object.keys(enemyIndex), ...Object.keys(chestIndex)]);
  const out = [];
  for (const itemId of ids) {
    const enemies = enemyIndex[itemId] || [];
    const chestProfiles = chestIndex[itemId] || [];
    out.push({
      key: itemId,
      type: VIEW_ITEMS,
      data: { enemies, chestProfiles },
      searchBlob: [itemId, ...enemies, ...chestProfiles].join(" ").toLowerCase()
    });
  }
  out.sort((a, b) => a.key.localeCompare(b.key));
  return out;
}

function getCurrentEntries() {
  if (currentView === VIEW_CHESTS) {
    return chestEntries;
  }
  if (currentView === VIEW_ITEMS) {
    return itemEntries;
  }
  return enemyEntries;
}

function getLabelForView() {
  if (currentView === VIEW_CHESTS) {
    return "Chests";
  }
  if (currentView === VIEW_ITEMS) {
    return "Items";
  }
  return "Enemies";
}

function getPlaceholderForView() {
  if (currentView === VIEW_CHESTS) {
    return "Search Chests...";
  }
  if (currentView === VIEW_ITEMS) {
    return "Search Items...";
  }
  return "Search Enemies...";
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

function renderEnemyPreview(entry) {
  const out = {
    enemy: entry.key,
    sourceRefs: entry.data.sources,
    drops: entry.data.drops
  };
  return `${JSON.stringify(out, null, 2)}\n`;
}

function renderChestPreview(entry) {
  const out = {
    chestProfile: entry.key,
    respawn: entry.data.respawn,
    prefabRef: entry.data.prefabRef,
    guaranteedSetRows: entry.data.guaranteedSetRows,
    additionalSetRows: entry.data.additionalSetRows,
    resolvedItems: entry.data.resolvedItems
  };
  return `${JSON.stringify(out, null, 2)}\n`;
}

function renderItemPreview(entry) {
  const out = {
    itemId: entry.key,
    enemyCount: entry.data.enemies.length,
    chestProfileCount: entry.data.chestProfiles.length,
    enemies: entry.data.enemies,
    chestProfiles: entry.data.chestProfiles
  };
  return `${JSON.stringify(out, null, 2)}\n`;
}

function toQuantityText(minimumDropAmount, maximumDropAmount) {
  if (minimumDropAmount === undefined || maximumDropAmount === undefined) {
    return "?";
  }
  if (minimumDropAmount === maximumDropAmount) {
    return String(minimumDropAmount);
  }
  return `${minimumDropAmount}-${maximumDropAmount}`;
}

function toRarityText(dropChance) {
  if (dropChance === undefined || dropChance === null) {
    return "Unknown";
  }
  if (dropChance === 100 || dropChance === 100.0) {
    return "Always";
  }
  return `${dropChance}/100`;
}

function escapeWikiValue(value) {
  return String(value ?? "").replaceAll("|", "&#124;");
}

function buildWikiDropLinesFromEnemy(entry) {
  return entry.data.drops.map((drop) => {
    const itemName = drop.itemDisplayName || drop.itemId;
    return `{{DropsLine|name=${escapeWikiValue(itemName)}|quantity=${toQuantityText(drop.minimumDropAmount, drop.maximumDropAmount)}|rarity=${toRarityText(drop.dropChance)}}}`;
  });
}

function buildWikiDropLinesFromChest(entry) {
  return entry.data.resolvedItems.map((resolved) => {
    const item = resolved.item || {};
    const itemName = item.itemDisplayName || item.itemId;
    return `{{DropsLine|name=${escapeWikiValue(itemName)}|quantity=${toQuantityText(item.minimumDropAmount, item.maximumDropAmount)}|rarity=${toRarityText(item.dropChance)}}}`;
  });
}

function renderWikiDropsBlock(lines) {
  if (lines.length === 0) {
    return [
      "===Drop Table===",
      "{{DropsTableHead}}",
      "{{DropsTableBottom}}"
    ].join("\n");
  }
  return [
    "===Drop Table===",
    "{{DropsTableHead}}",
    ...lines,
    "{{DropsTableBottom}}"
  ].join("\n");
}

function renderEnemyWiki(entry) {
  return `${renderWikiDropsBlock(buildWikiDropLinesFromEnemy(entry))}\n`;
}

function renderChestWiki(entry) {
  return `${renderWikiDropsBlock(buildWikiDropLinesFromChest(entry))}\n`;
}

function renderItemWiki(entry) {
  const lines = [
    "===Item Lookup===",
    `* itemId: ${entry.key}`,
    `* enemies: ${entry.data.enemies.length}`,
    `* chestProfiles: ${entry.data.chestProfiles.length}`
  ];
  return `${lines.join("\n")}\n`;
}

function renderEntryPreview(entry) {
  if (previewFormat === PREVIEW_FORMAT_WIKI) {
    if (entry.type === VIEW_CHESTS) {
      return renderChestWiki(entry);
    }
    if (entry.type === VIEW_ITEMS) {
      return renderItemWiki(entry);
    }
    return renderEnemyWiki(entry);
  }

  if (entry.type === VIEW_CHESTS) {
    return renderChestPreview(entry);
  }
  if (entry.type === VIEW_ITEMS) {
    return renderItemPreview(entry);
  }
  return renderEnemyPreview(entry);
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
  fileContentEl.textContent = "Search and click an entry to preview compiled loot data.";
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
    [tabEnemiesBtn, VIEW_ENEMIES],
    [tabChestsBtn, VIEW_CHESTS],
    [tabItemsBtn, VIEW_ITEMS]
  ];
  for (const [button, buttonView] of mapping) {
    const active = view === buttonView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  }

  const ver = (lootData && lootData.version) || "unknown";
  updateHomeSubtitle(
    `Browse ${getCurrentEntries().length.toLocaleString()} ${label} (dataset ${ver}).`
  );
  const n = getCurrentEntries().length;
  const hero = `${n.toLocaleString()} ${label.toLowerCase()}`;
  updateHomeStatus(hero);
  updateStatus(hero);
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
    if (!parsed || typeof parsed !== "object") {
      throw new Error("Invalid LootData JSON shape");
    }
    if (!parsed.enemies || !parsed.chests || !parsed.indexes) {
      throw new Error("LootData JSON missing expected sections");
    }

    lootData = parsed;
    enemyEntries = buildEnemyEntries();
    chestEntries = buildChestEntries();
    itemEntries = buildItemEntries();

    setView(VIEW_ENEMIES);
  } catch (error) {
    const errorText = `Failed to load LootData: ${error instanceof Error ? error.message : "Unknown error"}`;
    updateHomeStatus(errorText);
    updateStatus(errorText);
    updateHomeSubtitle("Browse enemy drops, chests, and item lookups");
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

tabEnemiesBtn.addEventListener("click", () => {
  setView(VIEW_ENEMIES);
});
tabChestsBtn.addEventListener("click", () => {
  setView(VIEW_CHESTS);
});
tabItemsBtn.addEventListener("click", () => {
  setView(VIEW_ITEMS);
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
