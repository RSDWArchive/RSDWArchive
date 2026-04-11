const DATA_URL = "./tools/SpellData/SpellData.json";

function fileName(path) {
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

function buildRows(data) {
  const entries = data.entries || {};
  return Object.keys(entries).map((path) => {
    const entry = entries[path];
    const en = entry.enrichment || {};
    const spellName =
      (entry.properties &&
        entry.properties.SpellDisplayName &&
        entry.properties.SpellDisplayName.LocalizedString) ||
      entry.name ||
      fileName(path);
    const hay = [
      path,
      fileName(path),
      spellName,
      entry.name || "",
      entry.primaryExportSource || "",
      JSON.stringify(en.castXpEvents || []),
      JSON.stringify(en.spellItemCosts || []),
      JSON.stringify(en.gameplayEffects || []),
    ].join(" ");
    return {
      id: path,
      label: `${spellName} (${fileName(path)})`,
      previewTitle: spellName,
      haystack: hay,
      getPreview: () => entry,
    };
  });
}

function buildSubtitle(data) {
  const n = Object.keys(data.entries || {}).length;
  const v = data.version || "unknown";
  return `Browse ${n.toLocaleString()} utility spells (dataset ${v}). Wiki: costs, XP events, gameplay effects.`;
}

function escapeTemplateValue(value) {
  if (value == null || value === "") {
    return "";
  }
  return String(value).replace(/\|/g, "{{!}}");
}

function spellDisplayName(entry) {
  const sn = entry.properties && entry.properties.SpellDisplayName;
  if (sn && typeof sn === "object") {
    return sn.LocalizedString || sn.SourceString || "";
  }
  return entry.name || "";
}

/** SKILL_Foo -> "Foo" for wiki skill line (adjust on-wiki if needed). */
function skillLabelFromCastXp(entry) {
  const en = entry.enrichment || {};
  const events = en.castXpEvents;
  if (!Array.isArray(events) || !events[0]) {
    return "";
  }
  const row = events[0].row;
  if (!row || !Array.isArray(row.SkillXPList) || !row.SkillXPList[0]) {
    return "";
  }
  const skillObj = row.SkillXPList[0].Skill;
  const on = skillObj && skillObj.ObjectName;
  if (typeof on !== "string") {
    return "";
  }
  const m = on.match(/SkillData'SKILL_([^']+)'/);
  return m ? m[1].replace(/_/g, " ") : "";
}

/** One {{RuneReq|name|count}} per enriched cost row. */
function formatRuneReqLine(costs) {
  if (!Array.isArray(costs) || costs.length === 0) {
    return "";
  }
  const parts = [];
  for (const c of costs) {
    const name = escapeTemplateValue(c.displayName || c.itemId || "");
    if (!name) {
      continue;
    }
    const n = typeof c.count === "number" ? c.count : "";
    parts.push(`{{RuneReq|${name}|${n}}}`);
  }
  return parts.join("<br>");
}

/**
 * {{Infobox Spell}} — fill release/level/description on the wiki when missing from export.
 * @see https://dragonwilds.runescape.wiki/w/Template:Infobox_Spell
 */
function wikiPreviewSpell(_dataset, row) {
  const entry = row.getPreview();
  const props = entry.properties || {};
  const stem = fileName(row.id).replace(/\.json$/i, "");
  const name = escapeTemplateValue(spellDisplayName(entry) || stem);
  const skill = escapeTemplateValue(skillLabelFromCastXp(entry));
  const cd = props.CooldownDuration;
  const runes = formatRuneReqLine((entry.enrichment || {}).spellItemCosts);
  const lines = [
    "{{Infobox Spell",
    `|name = ${name}`,
    `|image = ${name}.png`,
    "|imagesize = ",
    "|release = ",
    skill ? `|skill = ${skill}` : "|skill = ",
    "|level = ",
    typeof cd === "number" ? `|cooldown = ${cd}` : "|cooldown = ",
    runes ? `|runes = ${runes}` : "|runes = ",
    "|description = ",
    "}}",
    "",
  ];
  return lines.join("\n");
}

window.rsdwInitFlatDatasetViewer({
  dataUrl: DATA_URL,
  loadingSubtitle: "Browse USD spells — costs, cast XP, and effect blueprints.",
  buildSubtitle,
  buildRows,
  wikiPreview: wikiPreviewSpell,
  loadedSummary: (data) =>
    `${Object.keys(data.entries || {}).length.toLocaleString()} spells`,
});
