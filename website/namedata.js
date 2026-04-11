const DATA_URL = "./tools/NameData/NameData.json";

function fileName(path) {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

const HAYSTACK_KEY_CAP = 2500;

function haystackForParsed(parsed) {
  if (!parsed || parsed.kind !== "stringTable") {
    return JSON.stringify(parsed || {});
  }
  const kte = parsed.keysToEntries || {};
  const keys = Object.keys(kte);
  const sample = keys.slice(0, HAYSTACK_KEY_CAP);
  const vals = sample.map((k) => kte[k]);
  const extra = keys.length > HAYSTACK_KEY_CAP ? ` totalKeys:${keys.length}` : "";
  return [parsed.tableNamespace || "", parsed.exportName || "", ...sample, ...vals, extra].join(" ");
}

function buildRows(data) {
  const entries = data.entries || {};
  return Object.keys(entries).map((path) => {
    const entry = entries[path];
    const parsed = (entry && entry.parsed) || {};
    const n = parsed.kind === "stringTable" ? parsed.keyCount || 0 : 0;
    const label =
      parsed.kind === "stringTable"
        ? `${fileName(path)} (${n.toLocaleString()} keys)`
        : `${fileName(path)} (${parsed.kind || "entry"})`;
    return {
      id: path,
      label,
      previewTitle: fileName(path),
      haystack: `${path} ${haystackForParsed(parsed)}`,
      getPreview: () => entry,
    };
  });
}

function buildSubtitle(data) {
  const n = Object.keys(data.entries || {}).length;
  const tk = (data.counts && data.counts.totalKeys) || 0;
  const v = data.version || "unknown";
  return `Browse ${n.toLocaleString()} string tables (${tk.toLocaleString()} keys, dataset ${v}). Wiki: lookup loc keys and display strings.`;
}

window.rsdwInitFlatDatasetViewer({
  dataUrl: DATA_URL,
  loadingSubtitle: "Browse ST_ string tables — keys and values for wiki and enrichment checks.",
  buildSubtitle,
  buildRows,
  loadedSummary: (data) =>
    `${Object.keys(data.entries || {}).length.toLocaleString()} string tables`,
});
