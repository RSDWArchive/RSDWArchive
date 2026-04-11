const DATA_URL = "./tools/ProgressionData/ProgressionData.json";

function shortTablePath(fullPath) {
  const idx = fullPath.lastIndexOf("/");
  return idx >= 0 ? fullPath.slice(idx + 1) : fullPath;
}

/** Strip DT_Progression_ and .json for dropdown labels. */
function progressionDropdownLabel(tableKey) {
  const leaf = tableKey.includes("/") ? tableKey.split("/").pop() : tableKey;
  let s = String(leaf).replace(/\.json$/i, "");
  if (s.startsWith("DT_Progression_")) {
    s = s.slice("DT_Progression_".length);
  }
  return s || leaf;
}

/** Table meta name without DT_Progression_ prefix for list display. */
function shortMetaName(metaName) {
  const m = String(metaName || "");
  return m.startsWith("DT_Progression_") ? m.slice("DT_Progression_".length) : m;
}

function buildRows(data, tablePathFilter) {
  const rows = [];
  const tables = data.tables || {};
  const paths = tablePathFilter ? [tablePathFilter] : Object.keys(tables).sort();
  for (const tpath of paths) {
    const tbl = tables[tpath];
    if (!tbl) {
      continue;
    }
    const metaName = (tbl.meta && tbl.meta.name) || shortTablePath(tpath);
    const sm = shortMetaName(metaName);
    const rmap = tbl.rows || {};
    for (const rowName of Object.keys(rmap)) {
      const row = rmap[rowName];
      const hay = [tpath, metaName, rowName, JSON.stringify(row)].join(" ");
      const shortLine = `${sm} / ${rowName}`;
      const fullLine = `${metaName} / ${rowName}`;
      const rowObj = {
        id: `${tpath}::${rowName}`,
        label: shortLine,
        haystack: hay,
        getPreview: () => ({ tablePath: tpath, tableName: metaName, rowName, row }),
      };
      if (fullLine !== shortLine) {
        rowObj.listLabelExpanded = fullLine;
      }
      rows.push(rowObj);
    }
  }
  return rows;
}

function buildSubtitle(data) {
  const n = Object.keys(data.tables || {}).length;
  const v = data.version || "unknown";
  const misses = ((data.issues || {}).enrichmentMisses || []).length;
  return `Browse progression tables (${n} files, dataset ${v}). Enrichment misses: ${misses}.`;
}

window.rsdwInitFlatDatasetViewer({
  dataUrl: DATA_URL,
  loadingSubtitle: "Browse progression rows — unlock queries and resolved item names.",
  buildSubtitle,
  loadedSummary: (data, meta) => {
    const n =
      meta && typeof meta.rowCount === "number"
        ? meta.rowCount
        : buildRows(data, "").length;
    return `${n.toLocaleString()} progression rows`;
  },
  tableSelect: {
    selectId: "progression-table-filter",
    buildRows,
    formatOptionLabel: progressionDropdownLabel,
  },
  fileNameToggleId: "toggle-filenames",
});
