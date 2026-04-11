const DATA_URL = "./tools/ItemData/ItemData.json";

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
    const hay = [path, display, internal, JSON.stringify(en), entry.type || ""].join(" ");
    return {
      id: path,
      label: display,
      listFileLeaf: fileName(path),
      haystack: hay,
      getPreview: () => entry,
    };
  });
}

function subtitle(data) {
  const n = Object.keys(data.entries || {}).length;
  const v = data.version || "unknown";
  return `Browse ${n.toLocaleString()} items (dataset ${v}). Wiki: infobox names, tags, weights, and enrichments.`;
}

/** Pipe breaks MediaWiki template parameters; use magic word instead. */
function escapeTemplateValue(value) {
  if (value == null || value === "") {
    return "";
  }
  return String(value).replace(/\|/g, "{{!}}");
}

function localizedField(props, key) {
  const f = props && props[key];
  if (!f || typeof f !== "object") {
    return "";
  }
  return f.LocalizedString || f.SourceString || "";
}

/**
 * Rough journal-style label from ItemFilterTags / Category (see wiki Template:Infobox Item type list).
 */
function inferItemJournalType(props) {
  const tags = props && props.ItemFilterTags;
  if (Array.isArray(tags) && tags.length > 0) {
    const raw = tags[tags.length - 1];
    const s = String(raw);
    const dot = s.lastIndexOf(".");
    return dot >= 0 ? s.slice(dot + 1) : s;
  }
  const cat = props && props.Category && props.Category.TagName;
  if (typeof cat === "string" && cat) {
    const parts = cat.split(".");
    return parts[parts.length - 1] || "";
  }
  return "";
}

/**
 * {{Infobox Item}} skeleton aligned with dragonwilds.runescape.wiki (fill release/update/hydration manually).
 * @see https://dragonwilds.runescape.wiki/w/Template:Infobox_Item
 */
function wikiPreviewItem(_dataset, row) {
  const entry = row.getPreview();
  const props = entry.properties || {};
  const en = entry.enrichment || {};
  const stem = fileName(row.id).replace(/\.json$/i, "");
  const name = escapeTemplateValue(
    en.displayName || localizedField(props, "Name") || entry.name || stem
  );
  const description = escapeTemplateValue(en.flavourText || localizedField(props, "FlavourText"));
  const typeStr = escapeTemplateValue(inferItemJournalType(props));
  const w = props.Weight;
  const max = props.MaxStackSize;
  const lines = [
    "{{Infobox Item",
    `|name = ${name}`,
    `|image = ${name}.png`,
    "|release = ",
    "|update = ",
    typeStr ? `|type = ${typeStr}` : "|type = ",
    typeof w === "number" ? `|weight = ${w}` : "|weight = ",
    typeof max === "number" ? `|stacklimit = ${max}` : "|stacklimit = ",
    description ? `|description = ${description}` : "|description = ",
    "|hydration = ",
    "|sustenance = ",
    "}}",
    "",
  ];
  return lines.join("\n");
}

window.rsdwInitFlatDatasetViewer({
  dataUrl: DATA_URL,
  loadingSubtitle: "Browse items — names, tags, and enrichments for wiki infoboxes.",
  buildSubtitle: subtitle,
  buildRows,
  fileNameToggleId: "toggle-filenames",
  wikiPreview: wikiPreviewItem,
  loadedSummary: (data) =>
    `${Object.keys(data.entries || {}).length.toLocaleString()} items`,
});
