const DATA_URL = "./tools/PlanData/PlanData.json";

function fileName(path) {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function buildRows(data) {
  const entries = data.entries || {};
  return Object.keys(entries).map((path) => {
    const entry = entries[path];
    const en = entry.enrichment || {};
    const b = en.buildingPieceToUnlock || {};
    const summ = b.summary || {};
    const pieceName = summ.displayName || summ.internalName || "";
    const leaf = fileName(path);
    const hay = [path, leaf, pieceName, JSON.stringify(summ), entry.name || ""].join(" ");
    const title = pieceName || leaf;
    return {
      id: path,
      label: title,
      listFileLeaf: pieceName ? leaf : undefined,
      haystack: hay,
      getPreview: () => entry,
    };
  });
}

function buildSubtitle(data) {
  const n = Object.keys(data.entries || {}).length;
  const v = data.version || "unknown";
  return `Browse ${n.toLocaleString()} plans (dataset ${v}). Wiki: building unlocks and requirements.`;
}

window.rsdwInitFlatDatasetViewer({
  dataUrl: DATA_URL,
  loadingSubtitle: "Browse building plans — unlocked pieces, tags, and stability.",
  buildSubtitle,
  wikiPreview: (dataset, row) =>
    window.rsdwWikiRecipeTemplate.formatPlanEntry(row.getPreview()),
  buildRows,
  fileNameToggleId: "toggle-filenames",
  loadedSummary: (data) =>
    `${Object.keys(data.entries || {}).length.toLocaleString()} plans`,
});
