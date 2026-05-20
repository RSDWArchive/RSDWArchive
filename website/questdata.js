const DATA_URL = "./tools/QuestData/QuestData.json";
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
const tabQuestsBtn = document.getElementById("tab-quests");
const tabItemsBtn = document.getElementById("tab-items");
const tabVariablesBtn = document.getElementById("tab-variables");
const tabProgressionBtn = document.getElementById("tab-progression");
const togglePreviewFormatBtn = document.getElementById("toggle-preview-format");
const copyPreviewBtn = document.getElementById("copy-preview");
const copyToastEl = document.getElementById("copy-toast");

const VIEW_QUESTS = "quests";
const VIEW_ITEMS = "items";
const VIEW_VARIABLES = "variables";
const VIEW_PROGRESSION = "progression";
const PREVIEW_FORMAT_JSON = "json";
const PREVIEW_FORMAT_WIKI = "wiki";

let questData = null;
let questEntries = [];
let itemEntries = [];
let variableEntries = [];
let progressionEntries = [];
let currentView = VIEW_QUESTS;
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

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function questLabel(questId) {
  const quest = questData?.quests?.[questId];
  return quest?.displayName || quest?.internalName || questId;
}

function questSearchText(questId) {
  const quest = questData?.quests?.[questId];
  if (!quest) {
    return questId;
  }
  return [
    questId,
    quest.displayName,
    quest.internalName,
    quest.persistenceId,
    quest.description
  ].filter(Boolean).join(" ");
}

function itemName(item) {
  return item?.itemDisplayName || item?.itemId || "";
}

function itemKey(item) {
  return item?.itemId || item?.itemObjectName || "";
}

function uniqueItems(entries) {
  const seen = new Set();
  const out = [];
  for (const entry of asArray(entries)) {
    const item = entry.item || {};
    const key = `${item.itemId || ""}|${item.amount ?? ""}|${entry.condition || ""}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push(entry);
  }
  return out;
}

function compactQuest(quest) {
  return {
    id: quest.id,
    displayName: quest.displayName,
    description: quest.description,
    questRegion: quest.questRegion,
    isMainQuest: quest.isMainQuest,
    persistenceId: quest.persistenceId,
    currentSource: quest.source,
    counts: {
      objectives: asArray(quest.objectives).length,
      flowFiles: asArray(quest.flowFiles).length,
      requiredItems: asArray(quest.itemRequirements).length,
      checkedItems: asArray(quest.itemChecks).length,
      inventorySpaceChecks: asArray(quest.inventorySpaceChecks).length,
      rewardItems: asArray(quest.itemRewards).length,
      consumedItems: asArray(quest.itemConsumes).length,
      recipeRewards: asArray(quest.recipeRewards).length,
      locations: asArray(quest.questLocations).length,
      progressionTriggers: asArray(quest.progressionTriggers).length,
      variables: asArray(quest.questVariables).length
    }
  };
}

function buildQuestEntries() {
  return Object.entries(questData.quests).map(([questId, quest]) => {
    const itemBits = [
      ...asArray(quest.itemRequirements),
      ...asArray(quest.itemChecks),
      ...asArray(quest.inventorySpaceChecks),
      ...asArray(quest.itemRewards),
      ...asArray(quest.itemConsumes)
    ].map((entry) => `${itemKey(entry.item)} ${itemName(entry.item)}`);
    const variableBits = asArray(quest.questVariables).map((entry) => `${entry.boolName || ""} ${entry.intName || ""}`);
    const objectiveBits = asArray(quest.objectives).map((entry) => `${entry.id || ""} ${entry.text || ""}`);
    const progressionBits = asArray(quest.progressionTriggers).map((entry) => `${entry.rowName || ""} ${entry.unlockQueryString || ""}`);
    return {
      key: questId,
      label: questLabel(questId),
      type: VIEW_QUESTS,
      data: quest,
      searchBlob: [
        questSearchText(questId),
        quest.questRegion,
        quest.isMainQuest ? "main mainquest" : "side sidequest",
        ...objectiveBits,
        ...itemBits,
        ...variableBits,
        ...progressionBits,
        ...asArray(quest.entryPoints).map((entry) => entry.entryTag || ""),
        ...asArray(quest.questLocations).map((entry) => entry.locationName || "")
      ].join(" ").toLowerCase()
    };
  }).sort((a, b) => a.label.localeCompare(b.label));
}

function buildItemEntries() {
  const indexes = questData.indexes || {};
  const itemIds = new Set([
    ...Object.keys(indexes.itemToRequiredByQuests || {}),
    ...Object.keys(indexes.itemToCheckedByQuests || {}),
    ...Object.keys(indexes.itemToInventorySpaceCheckedByQuests || {}),
    ...Object.keys(indexes.itemToRewardedByQuests || {}),
    ...Object.keys(indexes.itemToConsumedByQuests || {})
  ]);
  const out = [];
  for (const itemId of itemIds) {
    const requiredBy = indexes.itemToRequiredByQuests?.[itemId] || [];
    const checkedBy = indexes.itemToCheckedByQuests?.[itemId] || [];
    const inventorySpaceCheckedBy = indexes.itemToInventorySpaceCheckedByQuests?.[itemId] || [];
    const rewardedBy = indexes.itemToRewardedByQuests?.[itemId] || [];
    const consumedBy = indexes.itemToConsumedByQuests?.[itemId] || [];
    const questIds = new Set([...requiredBy, ...checkedBy, ...inventorySpaceCheckedBy, ...rewardedBy, ...consumedBy]);
    const displayNames = [];
    for (const questId of questIds) {
      const quest = questData.quests[questId];
      for (const section of ["itemRequirements", "itemChecks", "inventorySpaceChecks", "itemRewards", "itemConsumes"]) {
        for (const entry of asArray(quest?.[section])) {
          if (entry.item?.itemId === itemId && entry.item?.itemDisplayName) {
            displayNames.push(entry.item.itemDisplayName);
          }
        }
      }
    }
    const displayName = displayNames[0] || itemId;
    out.push({
      key: itemId,
      label: displayName,
      type: VIEW_ITEMS,
      data: { itemId, displayName, requiredBy, checkedBy, inventorySpaceCheckedBy, rewardedBy, consumedBy },
      searchBlob: [
        itemId,
        displayName,
        ...[...questIds].map(questSearchText)
      ].join(" ").toLowerCase()
    });
  }
  out.sort((a, b) => a.label.localeCompare(b.label));
  return out;
}

function buildVariableEntries() {
  const variableIndex = questData.indexes?.questVariableToQuests || {};
  return Object.entries(variableIndex).map(([name, quests]) => ({
    key: name,
    label: name,
    type: VIEW_VARIABLES,
    data: { name, quests },
    searchBlob: [
      name,
      ...asArray(quests).map(questSearchText)
    ].join(" ").toLowerCase()
  })).sort((a, b) => a.key.localeCompare(b.key));
}

function buildProgressionEntries() {
  const progressionIndex = questData.indexes?.progressionRowToQuests || {};
  return Object.entries(progressionIndex).map(([rowName, quests]) => ({
    key: rowName,
    label: rowName,
    type: VIEW_PROGRESSION,
    data: { rowName, quests },
    searchBlob: [
      rowName,
      ...asArray(quests).map((questId) => {
        const quest = questData.quests[questId];
        const triggers = asArray(quest?.progressionTriggers).filter((entry) => entry.rowName === rowName);
        return [
          questSearchText(questId),
          ...triggers.map((entry) => `${entry.unlockQueryString || ""} ${entry.conversationEntryPointTag || ""}`)
        ].join(" ");
      })
    ].join(" ").toLowerCase()
  })).sort((a, b) => a.key.localeCompare(b.key));
}

function getCurrentEntries() {
  if (currentView === VIEW_ITEMS) {
    return itemEntries;
  }
  if (currentView === VIEW_VARIABLES) {
    return variableEntries;
  }
  if (currentView === VIEW_PROGRESSION) {
    return progressionEntries;
  }
  return questEntries;
}

function getLabelForView() {
  if (currentView === VIEW_ITEMS) {
    return "Items";
  }
  if (currentView === VIEW_VARIABLES) {
    return "Variables";
  }
  if (currentView === VIEW_PROGRESSION) {
    return "Progression";
  }
  return "Quests";
}

function getPlaceholderForView() {
  if (currentView === VIEW_ITEMS) {
    return "Search Items...";
  }
  if (currentView === VIEW_VARIABLES) {
    return "Search Variables...";
  }
  if (currentView === VIEW_PROGRESSION) {
    return "Search Progression Rows...";
  }
  return "Search Quests...";
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
    btn.textContent = entry.label || entry.key;
    btn.title = entry.key;
    btn.type = "button";
    btn.dataset.idx = String(idx);
    btn.addEventListener("click", () => openMatchByIndex(idx));
    li.appendChild(btn);
    fragment.appendChild(li);
  });
  resultsEl.appendChild(fragment);
}

function renderQuestPreview(entry) {
  const quest = entry.data;
  const out = {
    quest: compactQuest(quest),
    objectives: quest.objectives,
    flowFiles: quest.flowFiles,
    items: {
      required: uniqueItems(quest.itemRequirements),
      checked: uniqueItems(quest.itemChecks),
      inventorySpace: uniqueItems(quest.inventorySpaceChecks),
      rewarded: uniqueItems(quest.itemRewards),
      consumed: uniqueItems(quest.itemConsumes)
    },
    recipeRewards: quest.recipeRewards,
    locations: quest.questLocations,
    variables: quest.questVariables,
    prerequisites: quest.questPrerequisites,
    progressionTriggers: quest.progressionTriggers,
    saveLookup: {
      persistenceId: quest.persistenceId,
      objectiveIds: asArray(quest.objectives).map((objective) => objective.id).filter(Boolean),
      boolNames: [...new Set(asArray(quest.questVariables).map((variable) => variable.boolName).filter(Boolean))],
      intNames: [...new Set(asArray(quest.questVariables).map((variable) => variable.intName).filter(Boolean))]
    }
  };
  return `${JSON.stringify(out, null, 2)}\n`;
}

function renderItemPreview(entry) {
  const out = {
    itemId: entry.data.itemId,
    displayName: entry.data.displayName,
    requiredBy: entry.data.requiredBy.map((questId) => ({ questId, displayName: questLabel(questId) })),
    checkedBy: entry.data.checkedBy.map((questId) => ({ questId, displayName: questLabel(questId) })),
    inventorySpaceCheckedBy: entry.data.inventorySpaceCheckedBy.map((questId) => ({ questId, displayName: questLabel(questId) })),
    rewardedBy: entry.data.rewardedBy.map((questId) => ({ questId, displayName: questLabel(questId) })),
    consumedBy: entry.data.consumedBy.map((questId) => ({ questId, displayName: questLabel(questId) }))
  };
  return `${JSON.stringify(out, null, 2)}\n`;
}

function renderVariablePreview(entry) {
  const out = {
    variableName: entry.key,
    quests: asArray(entry.data.quests).map((questId) => {
      const quest = questData.quests[questId];
      return {
        questId,
        displayName: questLabel(questId),
        boolRefs: asArray(quest?.questVariables).filter((variable) => variable.boolName === entry.key),
        intRefs: asArray(quest?.questVariables).filter((variable) => variable.intName === entry.key)
      };
    })
  };
  return `${JSON.stringify(out, null, 2)}\n`;
}

function renderProgressionPreview(entry) {
  const out = {
    rowName: entry.key,
    quests: asArray(entry.data.quests).map((questId) => {
      const quest = questData.quests[questId];
      return {
        questId,
        displayName: questLabel(questId),
        triggers: asArray(quest?.progressionTriggers).filter((trigger) => trigger.rowName === entry.key)
      };
    })
  };
  return `${JSON.stringify(out, null, 2)}\n`;
}

function escapeWikiValue(value) {
  return String(value ?? "").replaceAll("|", "&#124;");
}

function bulletList(items) {
  if (items.length === 0) {
    return ["* None found"];
  }
  return items.map((item) => `* ${item}`);
}

function itemLine(entry) {
  const item = entry.item || {};
  const amount = item.amount === undefined || item.amount === null ? "" : ` x${item.amount}`;
  const condition = entry.condition ? ` (${entry.condition})` : "";
  return `${item.itemDisplayName || item.itemId || "Unknown item"}${amount}${condition}`;
}

function questLinkLine(questId) {
  return `${questLabel(questId)} (${questId})`;
}

function renderQuestWiki(entry) {
  const quest = entry.data;
  const lines = [
    `==${quest.displayName || quest.id}==`,
    quest.description || "",
    "",
    "===Quest Info===",
    `* questId: ${quest.id}`,
    `* internalName: ${quest.internalName || ""}`,
    `* persistenceId: ${quest.persistenceId || ""}`,
    `* region: ${quest.questRegion || "Unknown"}`,
    `* type: ${quest.isMainQuest ? "Main quest" : "Side quest"}`,
    "",
    "===Objectives===",
    ...bulletList(asArray(quest.objectives).map((objective) => `${objective.id || "Objective"}: ${escapeWikiValue(objective.text || "")}`)),
    "",
    "===Required or Checked Items===",
    ...bulletList(uniqueItems([...(quest.itemRequirements || []), ...(quest.itemChecks || [])]).map(itemLine)),
    "",
    "===Reward Inventory Space Checks===",
    ...bulletList(uniqueItems(quest.inventorySpaceChecks).map(itemLine)),
    "",
    "===Consumed Items===",
    ...bulletList(uniqueItems(quest.itemConsumes).map(itemLine)),
    "",
    "===Rewards===",
    ...bulletList(uniqueItems(quest.itemRewards).map(itemLine)),
    "",
    "===Recipe Unlocks===",
    ...bulletList(asArray(quest.recipeRewards).map((entry) => entry.recipe?.recipeId || "Unknown recipe")),
    "",
    "===Quest Locations===",
    ...bulletList(asArray(quest.questLocations).map((entry) => `${entry.locationName || "Unknown"}${entry.revealed === false ? " (hidden)" : ""}`)),
    "",
    "===Save Variables===",
    ...bulletList([...new Set(asArray(quest.questVariables).map((entry) => entry.boolName || entry.intName).filter(Boolean))])
  ];
  return `${lines.join("\n")}\n`;
}

function renderItemWiki(entry) {
  const lines = [
    `==${entry.data.displayName}==`,
    `* itemId: ${entry.data.itemId}`,
    "",
    "===Required By===",
    ...bulletList(asArray(entry.data.requiredBy).map(questLinkLine)),
    "",
    "===Checked By===",
    ...bulletList(asArray(entry.data.checkedBy).map(questLinkLine)),
    "",
    "===Reward Inventory Space Checked By===",
    ...bulletList(asArray(entry.data.inventorySpaceCheckedBy).map(questLinkLine)),
    "",
    "===Rewarded By===",
    ...bulletList(asArray(entry.data.rewardedBy).map(questLinkLine)),
    "",
    "===Consumed By===",
    ...bulletList(asArray(entry.data.consumedBy).map(questLinkLine))
  ];
  return `${lines.join("\n")}\n`;
}

function renderVariableWiki(entry) {
  const lines = [
    `==${entry.key}==`,
    "===Referenced By===",
    ...bulletList(asArray(entry.data.quests).map(questLinkLine))
  ];
  return `${lines.join("\n")}\n`;
}

function renderProgressionWiki(entry) {
  const lines = [
    `==${entry.key}==`,
    "===Changed Quests===",
    ...bulletList(asArray(entry.data.quests).map(questLinkLine))
  ];
  return `${lines.join("\n")}\n`;
}

function renderEntryPreview(entry) {
  if (previewFormat === PREVIEW_FORMAT_WIKI) {
    if (entry.type === VIEW_ITEMS) {
      return renderItemWiki(entry);
    }
    if (entry.type === VIEW_VARIABLES) {
      return renderVariableWiki(entry);
    }
    if (entry.type === VIEW_PROGRESSION) {
      return renderProgressionWiki(entry);
    }
    return renderQuestWiki(entry);
  }

  if (entry.type === VIEW_ITEMS) {
    return renderItemPreview(entry);
  }
  if (entry.type === VIEW_VARIABLES) {
    return renderVariablePreview(entry);
  }
  if (entry.type === VIEW_PROGRESSION) {
    return renderProgressionPreview(entry);
  }
  return renderQuestPreview(entry);
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

function entryMatchesSearchQuery(entry, queryRaw) {
  const fn = window.rsdwHaystackMatchesQuery;
  if (typeof fn === "function") {
    return fn(entry.searchBlob, queryRaw);
  }
  const q = String(queryRaw || "").trim().toLowerCase();
  return !q || entry.searchBlob.includes(q);
}

function handleSearch() {
  const queryRaw = searchInput.value.trim();
  const entries = getCurrentEntries();
  const label = getLabelForView();
  const filtered = queryRaw
    ? entries.filter((entry) => entryMatchesSearchQuery(entry, queryRaw))
    : entries;

  currentMatches = filtered.slice(0, MAX_RESULTS);
  renderResults(currentMatches);
  resultsViewer.classList.add("visible");
  setLandingVisible(false);

  selectedMatchIndex = -1;
  currentOpenEntry = null;
  selectedPathEl.textContent = "Select an entry";
  fileContentEl.textContent = "Search and click an entry to preview compiled quest data.";
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
    [tabQuestsBtn, VIEW_QUESTS],
    [tabItemsBtn, VIEW_ITEMS],
    [tabVariablesBtn, VIEW_VARIABLES],
    [tabProgressionBtn, VIEW_PROGRESSION]
  ];
  for (const [button, buttonView] of mapping) {
    const active = view === buttonView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  }

  const ver = (questData && questData.version) || "unknown";
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
      throw new Error("Invalid QuestData JSON shape");
    }
    if (!parsed.quests || !parsed.indexes) {
      throw new Error("QuestData JSON missing expected sections");
    }

    questData = parsed;
    questEntries = buildQuestEntries();
    itemEntries = buildItemEntries();
    variableEntries = buildVariableEntries();
    progressionEntries = buildProgressionEntries();

    setView(VIEW_QUESTS);
  } catch (error) {
    const errorText = `Failed to load QuestData: ${error instanceof Error ? error.message : "Unknown error"}`;
    updateHomeStatus(errorText);
    updateStatus(errorText);
    updateHomeSubtitle("Browse quests, items, variables, and progression hooks");
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

tabQuestsBtn.addEventListener("click", () => {
  setView(VIEW_QUESTS);
});
tabItemsBtn.addEventListener("click", () => {
  setView(VIEW_ITEMS);
});
tabVariablesBtn.addEventListener("click", () => {
  setView(VIEW_VARIABLES);
});
tabProgressionBtn.addEventListener("click", () => {
  setView(VIEW_PROGRESSION);
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
