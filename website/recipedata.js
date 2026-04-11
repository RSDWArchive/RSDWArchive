const DATA_URL = "./tools/RecipeData/RecipeData.json";

function fileName(path) {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function recipePrimaryLabel(entry, path) {
  const en = entry.enrichment || {};
  const skill = (en.skillUsedToCraft && en.skillUsedToCraft.displayName) || "";
  const leaf = fileName(path);
  const firstOut = (en.itemsCreated && en.itemsCreated[0]) || {};
  const title =
    firstOut.displayName || leaf.replace(/\.json$/i, "");
  const label = skill ? `${title} · ${skill}` : title;
  return { label, listFileLeaf: leaf };
}

function buildRecipeRowsOnly(data) {
  const rows = [];
  const entries = data.entries || {};
  for (const path of Object.keys(entries)) {
    const entry = entries[path];
    const en = entry.enrichment || {};
    const skill = (en.skillUsedToCraft && en.skillUsedToCraft.displayName) || "";
    const { label, listFileLeaf } = recipePrimaryLabel(entry, path);
    const hay = [path, fileName(path), skill, JSON.stringify(en.itemsConsumed || []), JSON.stringify(en.itemsCreated || [])].join(" ");
    rows.push({
      id: path,
      label,
      listFileLeaf,
      haystack: hay,
      getPreview: () => entry,
    });
  }
  return rows;
}

function displayNameForIndexedItem(data, itemId) {
  const entries = data.entries || {};
  const rbi = (data.indexes && data.indexes.recipesByItemId) || {};
  const paths = rbi[itemId];
  if (!paths || !paths.length) {
    return null;
  }
  for (const p of paths) {
    const entry = entries[p];
    const en = entry && entry.enrichment;
    if (!en) {
      continue;
    }
    for (const slot of [...(en.itemsConsumed || []), ...(en.itemsCreated || [])]) {
      if (slot && slot.itemId === itemId && slot.displayName) {
        return slot.displayName;
      }
    }
  }
  return null;
}

function buildByItemRowsOnly(data) {
  const rows = [];
  const rbi = (data.indexes && data.indexes.recipesByItemId) || {};
  for (const itemId of Object.keys(rbi)) {
    const paths = rbi[itemId];
    const hay = ["item", itemId, ...(paths || [])].join(" ");
    const display = displayNameForIndexedItem(data, itemId);
    const label = display ? `Recipes · ${display}` : `Recipes · ${itemId}`;
    const listFileLeaf = display ? itemId : undefined;
    rows.push({
      id: `reverse:${itemId}`,
      label,
      listFileLeaf,
      haystack: hay,
      getPreview: () => ({ itemId, recipePaths: paths }),
    });
  }
  return rows;
}

function buildSubtitle(data) {
  const n = Object.keys(data.entries || {}).length;
  const v = data.version || "unknown";
  const misses = ((data.issues || {}).enrichmentMisses || []).length;
  return `Browse ${n.toLocaleString()} recipes + reverse item index (dataset ${v}). Enrichment misses: ${misses}.`;
}

window.rsdwInitFlatDatasetViewer({
  dataUrl: DATA_URL,
  loadingSubtitle: "Browse recipes — ingredients, outputs, skills, and XP for wiki pages.",
  buildSubtitle,
  wikiPreview: (dataset, row) =>
    window.rsdwWikiRecipeTemplate.previewRecipeDataset(dataset, row),
  loadedSummary: (data, meta) => {
    const tab = meta && meta.tab;
    if (tab === "byitem") {
      const n = Object.keys((data.indexes && data.indexes.recipesByItemId) || {}).length;
      return `${n.toLocaleString()} items (recipe index)`;
    }
    return `${Object.keys(data.entries || {}).length.toLocaleString()} recipes`;
  },
  viewTabs: {
    defaultTab: "recipes",
    tabs: {
      recipes: buildRecipeRowsOnly,
      byitem: buildByItemRowsOnly,
    },
  },
  fileNameToggleId: "toggle-filenames",
});
