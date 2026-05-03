/**
 * LocationMap.html: wiki tiles + a sidebar of categorized actor pins.
 *
 * Data source: website/tools/LocationMap/CompileLocationMapData.py
 *   -> website/tools/LocationMap/LocationMapData.json
 *
 * CRS / transformation matches map.js (game X,Y -> Leaflet lat,lng as Y,X).
 *
 * Layer model: every leaf bucket (a category with no subcategories, or one
 * specific subcategory under a parent) has its own Leaflet layer. Parent rows
 * are pure UI grouping: their checkbox toggles all children at once and their
 * count is the sum of children. The map only ever renders leaf layers.
 */
const LOCATION_MAP_DATA_URL = "./tools/LocationMap/LocationMapData.json";

const mapEl = document.getElementById("world-map");
const statusEl = document.getElementById("map-status");
const siteLogo = document.getElementById("site-logo");
const searchInput = document.getElementById("locationmap-search");
const categoryListEl = document.getElementById("locationmap-category-list");
const countEl = document.getElementById("locationmap-count");

/** @type {Array} */ let parents = [];
/** @type {Array} */ let leaves = [];

let map = null;

siteLogo.addEventListener("error", () => {
  siteLogo.style.opacity = "0.5";
  siteLogo.title = "Add website/logo.png to display your logo.";
});

function setStatus(text) {
  if (statusEl) statusEl.textContent = text;
}

function createDragonwildsMap(container) {
  const bounds = [
    { lon: 0, lat: -100800 },
    { lon: 302400, lat: 201600 }
  ];
  const mult = 6144 / 302400 / 16;
  const dragonwildsCRS = window.L.extend({}, window.L.CRS.Simple, {
    projection: window.L.Projection.LonLat,
    transformation: new window.L.Transformation(mult, 0, mult, mult * 100800)
  });

  const m = window.L.map(container, {
    crs: dragonwildsCRS,
    maxBounds: bounds,
    zoom: 1,
    minZoom: 0.5,
    maxZoom: 4,
    zoomSnap: 0.5,
    attributionControl: false
  });

  window.L.tileLayer("https://maps.runescape.wiki/dw/tiles/{z}/{x}_{y}.png").addTo(m);
  m.fitBounds(bounds);
  return m;
}

function gameXYToLatLng(x, y) {
  return window.L.latLng(y, x);
}

async function loadJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
  return response.json();
}

function makeIcon(iconUrl) {
  if (!iconUrl) return null;
  return window.L.icon({
    iconUrl,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
    popupAnchor: [0, -8],
    className: "lm-marker-icon"
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  }[ch]));
}

function buildPopupHtml(point, leafLabel) {
  const lines = [
    `<div class="map-context-menu-header">${escapeHtml(leafLabel)}</div>`,
    `<div><strong>${escapeHtml(point.name)}</strong></div>`,
    `<div style="font-family:monospace;font-size:11px;opacity:0.8;">`
      + `x: ${point.x.toFixed(1)}<br>y: ${point.y.toFixed(1)}<br>z: ${point.z.toFixed(1)}</div>`
  ];
  if (point.uaid) {
    lines.push(`<div style="font-family:monospace;font-size:10px;opacity:0.7;">UAID ${escapeHtml(point.uaid)}</div>`);
  }
  return lines.join("");
}

function buildLayer(state, points) {
  const layer = window.L.layerGroup();
  const icon = state.icon_;
  for (const p of points) {
    const m = window.L.marker(gameXYToLatLng(p.x, p.y), icon ? { icon } : undefined);
    m.bindPopup(buildPopupHtml(p, state.label));
    layer.addLayer(m);
  }
  return layer;
}

function tokenize(query) {
  const out = { include: [], exclude: [] };
  if (!query) return out;
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  for (const t of tokens) {
    if (t.startsWith("-") && t.length > 1) out.exclude.push(t.slice(1));
    else out.include.push(t);
  }
  return out;
}

function filterPoints(points, tokens) {
  if (!tokens.include.length && !tokens.exclude.length) return points;
  return points.filter(p => {
    const lc = p.name.toLowerCase();
    for (const ex of tokens.exclude) if (lc.includes(ex)) return false;
    for (const inc of tokens.include) if (!lc.includes(inc)) return false;
    return true;
  });
}

/** Re-render a single leaf's Leaflet layer. Returns the count of points shown. */
function refreshLeafRender(leaf, tokens) {
  const filtered = filterPoints(leaf.points, tokens);
  if (leaf.countEl) {
    leaf.countEl.textContent = filtered.length === leaf.points.length
      ? String(leaf.points.length)
      : `${filtered.length} / ${leaf.points.length}`;
  }
  if (leaf.leafletLayer) {
    map.removeLayer(leaf.leafletLayer);
    leaf.leafletLayer = null;
  }
  if (!leaf.enabled || !filtered.length) return filtered.length;
  leaf.leafletLayer = buildLayer(leaf, filtered);
  leaf.leafletLayer.addTo(map);
  return filtered.length;
}

/** Update parent row count + tri-state checkbox based on current leaves. */
function refreshParentRow(parent, leafShownByKey) {
  if (!parent.parentCountEl) return;
  let totalAll = 0;
  let totalShown = 0;
  let anyEnabled = false;
  let allEnabled = true;
  for (const leaf of parent.leaves) {
    totalAll += leaf.points.length;
    totalShown += leafShownByKey.get(leaf.key) || 0;
    if (leaf.enabled) anyEnabled = true;
    else allEnabled = false;
  }
  parent.parentCountEl.textContent = totalShown === totalAll
    ? String(totalAll)
    : `${totalShown} / ${totalAll}`;
  if (parent.parentCheckbox && parent.hasSubcategories) {
    parent.parentCheckbox.checked = anyEnabled;
    parent.parentCheckbox.indeterminate = anyEnabled && !allEnabled;
  }
}

function refreshAll() {
  const tokens = tokenize(searchInput.value);
  const leafShownByKey = new Map();
  let grandShown = 0;
  let grandTotal = 0;
  for (const leaf of leaves) {
    const shown = refreshLeafRender(leaf, tokens);
    leafShownByKey.set(leaf.key, leaf.enabled ? shown : 0);
    grandTotal += leaf.points.length;
    if (leaf.enabled) grandShown += shown;
  }
  for (const parent of parents) refreshParentRow(parent, leafShownByKey);
  countEl.textContent = `${grandShown.toLocaleString()} of ${grandTotal.toLocaleString()} pins shown`;
}

/* --- DOM construction ----------------------------------------------------- */

function makeRow({ checkbox, iconUrl, label, expandable, expanded, indent }) {
  const li = document.createElement("li");
  li.className = "map-chunk-list-item";
  li.style.display = "flex";
  li.style.alignItems = "center";
  li.style.gap = "6px";
  if (indent) li.style.paddingLeft = `${indent}px`;

  let expandBtn = null;
  if (expandable) {
    expandBtn = document.createElement("button");
    expandBtn.type = "button";
    expandBtn.className = "locationmap-expand-btn";
    expandBtn.setAttribute("aria-label", "Toggle subcategories");
    expandBtn.style.cssText = "background:none;border:none;cursor:pointer;color:inherit;font:inherit;width:16px;padding:0;";
    expandBtn.textContent = expanded ? "\u25BE" : "\u25B8";
    li.appendChild(expandBtn);
  } else {
    const spacer = document.createElement("span");
    spacer.style.cssText = "display:inline-block;width:16px;";
    li.appendChild(spacer);
  }

  li.appendChild(checkbox);

  if (iconUrl) {
    const iconImg = document.createElement("img");
    iconImg.src = iconUrl;
    iconImg.alt = "";
    iconImg.width = 16;
    iconImg.height = 16;
    iconImg.style.flex = "0 0 auto";
    li.appendChild(iconImg);
  }

  const labelEl = document.createElement("label");
  labelEl.htmlFor = checkbox.id;
  labelEl.style.flex = "1 1 auto";
  labelEl.style.cursor = "pointer";
  labelEl.textContent = label;
  li.appendChild(labelEl);

  const countSpan = document.createElement("span");
  countSpan.style.cssText = "opacity:0.7;font-family:monospace;font-size:12px;";
  li.appendChild(countSpan);

  return { li, expandBtn, countSpan };
}

function buildSidebar() {
  categoryListEl.innerHTML = "";

  for (const parent of parents) {
    const parentCheckbox = document.createElement("input");
    parentCheckbox.type = "checkbox";
    parentCheckbox.id = `cat-${parent.key}`;

    const { li, expandBtn, countSpan } = makeRow({
      checkbox: parentCheckbox,
      iconUrl: parent.icon,
      label: parent.label,
      expandable: parent.hasSubcategories,
      expanded: parent.expanded,
      indent: 0
    });
    categoryListEl.appendChild(li);

    parent.parentCheckbox = parentCheckbox;
    parent.parentCountEl = countSpan;
    parent.expandBtn = expandBtn;

    parentCheckbox.addEventListener("change", () => {
      const desired = parentCheckbox.checked;
      for (const leaf of parent.leaves) {
        leaf.enabled = desired;
        if (leaf.checkbox && leaf.checkbox !== parentCheckbox) {
          leaf.checkbox.checked = desired;
        }
      }
      refreshAll();
    });

    if (parent.hasSubcategories) {
      const childList = document.createElement("ul");
      childList.className = "map-chunk-list locationmap-subcategory-list";
      childList.style.cssText = "list-style:none;margin:0;padding:0;";
      childList.hidden = !parent.expanded;
      categoryListEl.appendChild(childList);
      parent.childListEl = childList;

      for (const leaf of parent.leaves) {
        const leafCheckbox = document.createElement("input");
        leafCheckbox.type = "checkbox";
        leafCheckbox.id = `sub-${leaf.key.replace(/[^a-z0-9_-]/gi, "_")}`;
        leafCheckbox.checked = leaf.enabled;

        const row = makeRow({
          checkbox: leafCheckbox,
          iconUrl: leaf.icon,
          label: leaf.label,
          expandable: false,
          expanded: false,
          indent: 22
        });
        childList.appendChild(row.li);

        leaf.listItem = row.li;
        leaf.checkbox = leafCheckbox;
        leaf.countEl = row.countSpan;

        leafCheckbox.addEventListener("change", () => {
          leaf.enabled = leafCheckbox.checked;
          refreshAll();
        });
      }

      if (expandBtn) {
        expandBtn.addEventListener("click", () => {
          parent.expanded = !parent.expanded;
          expandBtn.textContent = parent.expanded ? "\u25BE" : "\u25B8";
          if (parent.childListEl) parent.childListEl.hidden = !parent.expanded;
        });
      }
    } else {
      // For leaf-only categories, the parent's checkbox IS the leaf's checkbox.
      const leaf = parent.leaves[0];
      leaf.listItem = li;
      leaf.checkbox = parentCheckbox;
      leaf.countEl = countSpan;
    }
  }
}

/* --- Data ingestion ------------------------------------------------------- */

function ingest(payload) {
  const cats = (payload && payload.categories) || {};
  parents = [];
  leaves = [];

  for (const catKey of Object.keys(cats)) {
    const c = cats[catKey] || {};
    const parent = {
      key: catKey,
      label: c.label || catKey,
      icon: c.icon || null,
      leaves: [],
      hasSubcategories: !!c.subcategories,
      expanded: false,
      parentCheckbox: null,
      parentCountEl: null,
      childListEl: null,
      expandBtn: null
    };

    if (c.subcategories) {
      for (const subKey of Object.keys(c.subcategories)) {
        const s = c.subcategories[subKey] || {};
        const points = Array.isArray(s.points) ? s.points : [];
        const leaf = {
          key: `${catKey}/${subKey}`,
          parentKey: catKey,
          label: s.label || subKey,
          icon: s.icon || null,
          points,
          icon_: makeIcon(s.icon),
          leafletLayer: null,
          enabled: false,
          listItem: null,
          checkbox: null,
          countEl: null
        };
        parent.leaves.push(leaf);
        leaves.push(leaf);
      }
    } else {
      const points = Array.isArray(c.points) ? c.points : [];
      const leaf = {
        key: catKey,
        parentKey: catKey,
        label: c.label || catKey,
        icon: c.icon || null,
        points,
        icon_: makeIcon(c.icon),
        leafletLayer: null,
        enabled: false,
        listItem: null,
        checkbox: null,
        countEl: null
      };
      parent.leaves.push(leaf);
      leaves.push(leaf);
    }

    parents.push(parent);
  }

  parents.sort((a, b) => sumPoints(b) - sumPoints(a));
}

function sumPoints(parent) {
  let n = 0;
  for (const leaf of parent.leaves) n += leaf.points.length;
  return n;
}

async function init() {
  if (!window.L) {
    setStatus("Leaflet failed to load.");
    return;
  }
  map = createDragonwildsMap(mapEl);

  let payload;
  try {
    setStatus("Loading actor pins\u2026");
    payload = await loadJson(LOCATION_MAP_DATA_URL);
  } catch (err) {
    console.error(err);
    setStatus("Failed to load LocationMapData.json \u2014 run tools/LocationMap/CompileLocationMapData.py.");
    return;
  }

  ingest(payload);
  buildSidebar();

  setStatus(`Loaded ${parents.length} categories, ${leaves.length} leaf layers.`);
  searchInput.addEventListener("input", () => refreshAll());
  setupIconSizeSlider();
  refreshAll();
}

function setupIconSizeSlider() {
  const slider = document.getElementById("locationmap-icon-size");
  const valueEl = document.getElementById("locationmap-icon-size-value");
  if (!slider) return;
  const STORAGE_KEY = "locationmap.iconSize";
  const apply = (px) => {
    document.documentElement.style.setProperty("--lm-icon-size", `${px}px`);
    if (valueEl) valueEl.textContent = String(px);
  };
  let initial = parseInt(localStorage.getItem(STORAGE_KEY) || "", 10);
  if (!Number.isFinite(initial) || initial < 8 || initial > 64) initial = 20;
  slider.value = String(initial);
  apply(initial);
  slider.addEventListener("input", () => {
    const px = parseInt(slider.value, 10) || 20;
    apply(px);
    try { localStorage.setItem(STORAGE_KEY, String(px)); } catch (_) { /* ignore */ }
  });
}

init();
