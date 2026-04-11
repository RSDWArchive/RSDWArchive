const DATA_URL = "./tools/VestigeData/VestigeData.json";

function fileName(path) {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function buildRows(data) {
  const entries = data.entries || {};
  return Object.keys(entries).map((path) => {
    const entry = entries[path];
    const en = entry.enrichment || {};
    const display = en.displayName || entry.name || fileName(path);
    const internal = (entry.properties && entry.properties.InternalName) || "";
    const hay = [path, display, internal, JSON.stringify(en.recipesToUnlock || [])].join(" ");
    return {
      id: path,
      label: display,
      listFileLeaf: fileName(path),
      haystack: hay,
      getPreview: () => entry,
    };
  });
}

function buildSubtitle(data) {
  const n = Object.keys(data.entries || {}).length;
  const v = data.version || "unknown";
  return `Browse ${n.toLocaleString()} vestiges (dataset ${v}). Wiki: study text and unlocked recipes.`;
}

window.rsdwInitFlatDatasetViewer({
  dataUrl: DATA_URL,
  loadingSubtitle: "Browse vestige scrolls — recipe unlock chains for wiki.",
  buildSubtitle,
  buildRows,
  fileNameToggleId: "toggle-filenames",
  loadedSummary: (data) =>
    `${Object.keys(data.entries || {}).length.toLocaleString()} vestiges`,
});
