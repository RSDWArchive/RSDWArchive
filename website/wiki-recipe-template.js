/**
 * Shared [[Template:Recipe]] wikitext for RecipeData (RECIPE_*) and PlanData (DA_Consumable_Plan_*).
 * https://dragonwilds.runescape.wiki/w/Template:Recipe
 */
(function (global) {
  function escapeTemplateValue(value) {
    if (value == null || value === "") {
      return "";
    }
    return String(value).replace(/\|/g, "{{!}}");
  }

  function skillLabelFromSkillObjectName(objectName) {
    if (typeof objectName !== "string") {
      return "";
    }
    const m = objectName.match(/SkillData'SKILL_([^']+)'/);
    return m ? m[1].replace(/_/g, " ") : "";
  }

  /** Recipe JSON: onCraftXp or SkillXPAwardedOnCraft. */
  function wikiSkillXpRecipeEntry(entry) {
    const en = entry.enrichment || {};
    const row = en.onCraftXp && en.onCraftXp.row;
    if (row && Array.isArray(row.SkillXPList) && row.SkillXPList[0]) {
      const xp = row.SkillXPList[0].XP;
      if (typeof xp === "number") {
        return Number.isInteger(xp) ? String(xp) : String(Math.round(xp * 100) / 100);
      }
    }
    const raw = entry.properties && entry.properties.SkillXPAwardedOnCraft;
    if (typeof raw === "number") {
      return String(raw);
    }
    return "";
  }

  function inferRecipeFacility(entry) {
    const first = (entry.enrichment && entry.enrichment.itemsCreated && entry.enrichment.itemsCreated[0]) || {};
    const itemId = String(first.itemId || "");
    if (itemId.includes("Plan") || itemId.startsWith("DA_Consumable_Plan")) {
      return "Build Menu";
    }
    return "Crafting table";
  }

  function formatRecipeWikiFromRecipeEntry(entry) {
    const en = entry.enrichment || {};
    const consumed = Array.isArray(en.itemsConsumed) ? en.itemsConsumed : [];
    const created = Array.isArray(en.itemsCreated) ? en.itemsCreated : [];
    const firstOut = created[0] || {};
    const outDisplay = firstOut.displayName || "";
    const facility = inferRecipeFacility(entry);
    let recipeLine =
      outDisplay ||
      String(entry.name || "")
        .replace(/^RECIPE_/i, "")
        .replace(/\.json$/i, "");
    if (facility === "Build Menu" && recipeLine && !/^PLAN:\s*/i.test(recipeLine)) {
      recipeLine = `PLAN: ${recipeLine}`;
    }
    const skill = (en.skillUsedToCraft && en.skillUsedToCraft.displayName) || "";
    const skillxp = wikiSkillXpRecipeEntry(entry);
    const lines = [
      "{{Recipe",
      `|facility = ${escapeTemplateValue(facility)}`,
      `|recipe = ${escapeTemplateValue(recipeLine)}`,
      skill ? `|skill = ${escapeTemplateValue(skill)}` : "|skill = ",
      skillxp ? `|skillxp = ${skillxp}` : "|skillxp = ",
    ];
    const maxMat = Math.max(consumed.length, 1);
    for (let i = 0; i < Math.min(maxMat, 6); i++) {
      const n = i + 1;
      const slot = consumed[i];
      if (slot) {
        const mat = escapeTemplateValue(slot.displayName || slot.itemId || "");
        const qty = typeof slot.count === "number" ? String(slot.count) : "";
        lines.push(`|mat${n} = ${mat}`);
        lines.push(`|mat${n}qty = ${qty}`);
      } else {
        lines.push(`|mat${n} = `);
        lines.push(`|mat${n}qty = `);
      }
    }

    lines.push(outDisplay ? `|output1 = ${escapeTemplateValue(outDisplay)}` : "|output1 = ");
    if (typeof firstOut.count === "number") {
      lines.push(`|output1qty = ${firstOut.count}`);
    }
    lines.push("}}", "");
    return lines.join("\n");
  }

  /** Plan consumable JSON: buildingPieceToUnlock.summary (requirements, buildXp). */
  function formatRecipeWikiFromPlanEntry(entry) {
    const en = entry.enrichment || {};
    const b = en.buildingPieceToUnlock || {};
    const summ = b.summary || {};
    const props = entry.properties || {};
    const reqs = Array.isArray(summ.requirements) ? summ.requirements : [];
    const planName =
      (props.Name && (props.Name.LocalizedString || props.Name.SourceString)) || "";
    const outDisplay = summ.displayName || "";
    const facility = "Build Menu";
    let recipeLine = planName;
    if (!recipeLine && outDisplay) {
      recipeLine = /^PLAN:\s*/i.test(outDisplay) ? outDisplay : `PLAN: ${outDisplay}`;
    }

    let skill = "";
    let skillxp = "";
    const bx = summ.buildXp && summ.buildXp.row;
    if (bx && Array.isArray(bx.SkillXPList) && bx.SkillXPList[0]) {
      const skObj = bx.SkillXPList[0].Skill;
      skill = skillLabelFromSkillObjectName(skObj && skObj.ObjectName);
      const xp = bx.SkillXPList[0].XP;
      if (typeof xp === "number") {
        skillxp = Number.isInteger(xp) ? String(xp) : String(Math.round(xp * 100) / 100);
      }
    }

    const lines = [
      "{{Recipe",
      `|facility = ${escapeTemplateValue(facility)}`,
      `|recipe = ${escapeTemplateValue(recipeLine || outDisplay || entry.name || "")}`,
      skill ? `|skill = ${escapeTemplateValue(skill)}` : "|skill = ",
      skillxp ? `|skillxp = ${skillxp}` : "|skillxp = ",
    ];
    const numSlots = Math.min(Math.max(reqs.length, 1), 6);
    for (let i = 0; i < numSlots; i++) {
      const n = i + 1;
      const slot = reqs[i];
      if (slot) {
        const mat = escapeTemplateValue(slot.displayName || slot.itemId || "");
        const qty = typeof slot.amount === "number" ? String(slot.amount) : "";
        lines.push(`|mat${n} = ${mat}`);
        lines.push(`|mat${n}qty = ${qty}`);
      } else {
        lines.push(`|mat${n} = `);
        lines.push(`|mat${n}qty = `);
      }
    }
    lines.push(outDisplay ? `|output1 = ${escapeTemplateValue(outDisplay)}` : "|output1 = ");
    lines.push("}}", "");
    return lines.join("\n");
  }

  function previewRecipeDataset(dataset, row) {
    const rid = row.id;
    if (typeof rid === "string" && rid.startsWith("reverse:")) {
      const prev = row.getPreview();
      const paths = (prev && prev.recipePaths) || [];
      const firstPath = paths[0];
      const ent = firstPath && dataset.entries && dataset.entries[firstPath];
      if (ent) {
        return formatRecipeWikiFromRecipeEntry(ent);
      }
      return "{{!-- Wiki {{Recipe}} export needs a recipe row: switch to All recipes or ensure this item appears in RecipeData. --}}\n";
    }
    return formatRecipeWikiFromRecipeEntry(row.getPreview());
  }

  global.rsdwWikiRecipeTemplate = {
    escapeTemplateValue,
    formatRecipeEntry: formatRecipeWikiFromRecipeEntry,
    formatPlanEntry: formatRecipeWikiFromPlanEntry,
    previewRecipeDataset,
  };
})(window);
