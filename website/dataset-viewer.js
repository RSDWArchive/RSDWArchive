/**
 * Shared UI for RSDW Archive dataset pages (flat list + search + JSON preview + copy).
 * Expects the same DOM layout as NPCData.html / LootData.html.
 */
(function (global) {
  const MAX_RESULTS = 500;
  const DEBOUNCE_MS = 90;

  function debounce(fn, ms) {
    let t = null;
    return function debounced(...args) {
      if (t) {
        clearTimeout(t);
      }
      t = setTimeout(() => {
        fn.apply(null, args);
      }, ms);
    };
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

  function bindToolsMenu(toolsToggleBtn, toolsDropdownEl) {
    if (!toolsToggleBtn || !toolsDropdownEl) {
      return;
    }
    function setOpen(open) {
      toolsDropdownEl.hidden = !open;
      toolsToggleBtn.setAttribute("aria-expanded", String(open));
    }
    toolsToggleBtn.addEventListener("click", () => {
      setOpen(toolsDropdownEl.hidden);
    });
    document.addEventListener("click", (event) => {
      if (!(event.target instanceof Node)) {
        return;
      }
      if (!toolsDropdownEl.contains(event.target) && !toolsToggleBtn.contains(event.target)) {
        setOpen(false);
      }
    });
  }

  /**
   * @param {object} options
   * @param {string} options.dataUrl - relative path to JSON
   * @param {string} options.loadingSubtitle
   * @param {function(any): string} options.buildSubtitle - (data) => subtitle string
   * @param {function(any): Array<{id:string,label:string,haystack:string,getPreview:()=>any,previewTitle?:string}>} [options.buildRows]
   * @param {function(any, object): string} [options.formatPreview] - (data, row) => text; default JSON.stringify getPreview()
   * @param {function(any, object): string} [options.wikiPreview] - if set with `#toggle-preview-format`, switches preview/copy between JSON and wiki text
   * @param {object} [options.viewTabs] - `{ defaultTab, tabs: Record<string, function(data): array> }` with buttons `[data-rsdw-view-tab]`
   * @param {object} [options.tableSelect] - `{ selectId, buildRows(data, tablePath), formatOptionLabel?(key), ... }` to narrow rows (e.g. ProgressionData)
   * @param {function(any, object=): (string|undefined)} [options.loadedSummary] - (data, meta?) => short hero line for `#home-status` / initial `#status`; meta may include `tab`, `tablePath`, `rowCount`
   * @param {string} [options.fileNameToggleId] - element id for Show/Hide File Names (`row.label` default; `row.listLabelExpanded` replaces whole label when on; else `row.listFileLeaf` appends with em dash)
   */
  function initFlatDatasetViewer(options) {
    const {
      dataUrl,
      loadingSubtitle,
      buildSubtitle,
      buildRows,
      formatPreview,
      viewTabs,
      tableSelect,
      loadedSummary,
      fileNameToggleId,
      wikiPreview,
    } = options;

    const searchInput = document.getElementById("file-search");
    const statusEl = document.getElementById("status");
    const resultsEl = document.getElementById("results");
    const resultsViewer = document.querySelector(".results-viewer");
    const landingMessageEl = document.getElementById("landing-message");
    const homeStatusEl = document.getElementById("home-status");
    const homeSubtitleEl = document.getElementById("home-subtitle");
    const selectedPathEl = document.getElementById("selected-path");
    const fileContentEl = document.getElementById("file-content");
    const siteLogo = document.getElementById("site-logo");
    const toolsToggleBtn = document.getElementById("tools-toggle");
    const toolsDropdownEl = document.getElementById("tools-dropdown");
    const copyPreviewBtn = document.getElementById("copy-preview");
    const copyToastEl = document.getElementById("copy-toast");
    const togglePreviewFormatBtn = document.getElementById("toggle-preview-format");

    let allRows = [];
    let filteredRows = [];
    let selectedIndex = -1;
    let currentPayload = null;
    let datasetPayload = null;
    let debounceTimer = null;
    let copyToastTimer = null;
    let showFileNames = false;
    let previewIsWiki = false;
    const fileNameToggleBtn = fileNameToggleId ? document.getElementById(fileNameToggleId) : null;
    const hasWikiPreview = typeof wikiPreview === "function";

    if (siteLogo) {
      siteLogo.addEventListener("error", () => {
        siteLogo.style.opacity = "0.5";
        siteLogo.title = "Add website/logo.png to display your logo.";
      });
    }

    bindToolsMenu(toolsToggleBtn, toolsDropdownEl);

    function formatRowListLabel(row) {
      if (showFileNames) {
        if (typeof row.listLabelExpanded === "string" && row.listLabelExpanded.trim()) {
          return row.listLabelExpanded.trim();
        }
        const leaf = row.listFileLeaf;
        if (typeof leaf === "string" && leaf.length > 0 && leaf !== row.label) {
          return `${row.label} — ${leaf}`;
        }
      }
      return row.label;
    }

    function updateStatus(text) {
      if (statusEl) {
        statusEl.textContent = text;
      }
    }
    function updateHomeStatus(text) {
      if (homeStatusEl) {
        homeStatusEl.textContent = text;
      }
    }
    function updateHomeSubtitle(text) {
      if (homeSubtitleEl) {
        homeSubtitleEl.textContent = text;
      }
    }
    function setLandingVisible(visible) {
      if (landingMessageEl) {
        landingMessageEl.hidden = !visible;
      }
      if (statusEl) {
        statusEl.style.display = visible ? "none" : "block";
      }
    }

    function updatePreviewFormatButtonLabel() {
      if (!togglePreviewFormatBtn || !hasWikiPreview) {
        return;
      }
      togglePreviewFormatBtn.textContent = previewIsWiki ? "Wiki" : "JSON";
    }

    function getPreviewPanelText() {
      if (!currentPayload) {
        return "";
      }
      if (hasWikiPreview && previewIsWiki) {
        try {
          return wikiPreview(datasetPayload, currentPayload);
        } catch {
          return "";
        }
      }
      const obj = currentPayload.getPreview();
      if (typeof formatPreview === "function") {
        return formatPreview(datasetPayload, currentPayload);
      }
      return JSON.stringify(obj, null, 2);
    }

    function showCopyToast(message, isError) {
      if (!copyToastEl) {
        return;
      }
      if (copyToastTimer) {
        clearTimeout(copyToastTimer);
      }
      copyToastEl.textContent = message;
      copyToastEl.classList.toggle("error", Boolean(isError));
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

    function renderList() {
      if (!resultsEl) {
        return;
      }
      resultsEl.innerHTML = "";
      const slice = filteredRows.slice(0, MAX_RESULTS);
      slice.forEach((row, idx) => {
        const li = document.createElement("li");
        const btn = document.createElement("button");
        btn.type = "button";
        btn.dataset.idx = String(idx);
        btn.textContent = formatRowListLabel(row);
        btn.addEventListener("click", () => {
          openRow(idx);
        });
        li.appendChild(btn);
        resultsEl.appendChild(li);
      });
      const capped = filteredRows.length > MAX_RESULTS;
      const suffix = capped
        ? ` (showing first ${MAX_RESULTS.toLocaleString()} of ${filteredRows.length.toLocaleString()})`
        : "";
      updateStatus(`${filteredRows.length.toLocaleString()} matches${suffix}.`);
    }

    function openRow(indexInSlice) {
      if (indexInSlice < 0 || indexInSlice >= Math.min(filteredRows.length, MAX_RESULTS)) {
        return;
      }
      const row = filteredRows[indexInSlice];
      currentPayload = row;
      selectedIndex = indexInSlice;
      if (selectedPathEl) {
        let header = row.id;
        if (typeof row.previewTitle === "string" && row.previewTitle.trim()) {
          header = row.previewTitle.trim();
        } else if (typeof row.label === "string" && row.label.trim()) {
          header = row.label.trim();
        }
        selectedPathEl.textContent = header;
      }
      if (fileContentEl) {
        fileContentEl.textContent = getPreviewPanelText();
      }
      if (copyPreviewBtn) {
        copyPreviewBtn.disabled = false;
      }
      if (togglePreviewFormatBtn && hasWikiPreview) {
        togglePreviewFormatBtn.disabled = false;
        updatePreviewFormatButtonLabel();
      }
    }

    function runFilter() {
      const q = (searchInput && searchInput.value ? searchInput.value : "").trim().toLowerCase();
      if (!q) {
        filteredRows = allRows.slice();
      } else {
        filteredRows = allRows.filter((r) => r.haystack.toLowerCase().includes(q));
      }
      selectedIndex = -1;
      currentPayload = null;
      if (fileContentEl) {
        fileContentEl.textContent = "Search and click an entry to preview compiled data.";
      }
      if (selectedPathEl) {
        selectedPathEl.textContent = "Select an entry";
      }
      if (copyPreviewBtn) {
        copyPreviewBtn.disabled = true;
      }
      previewIsWiki = false;
      if (togglePreviewFormatBtn && hasWikiPreview) {
        togglePreviewFormatBtn.disabled = true;
        updatePreviewFormatButtonLabel();
      }
      if (resultsViewer) {
        resultsViewer.classList.add("visible");
      }
      setLandingVisible(false);
      renderList();
    }

    const debouncedFilter = debounce(runFilter, DEBOUNCE_MS);

    async function boot() {
      updateHomeStatus("Loading…");
      updateStatus("Loading…");
      if (loadingSubtitle) {
        updateHomeSubtitle(loadingSubtitle);
      }
      try {
        const response = await fetch(dataUrl);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const parsed = await response.json();
        datasetPayload = parsed;

        function applyHeroLine(extra) {
          let heroLine = "Loaded.";
          if (typeof loadedSummary === "function") {
            try {
              const s = loadedSummary(parsed, extra || {});
              if (typeof s === "string" && s.trim()) {
                heroLine = s.trim();
              }
            } catch (_) {
              // keep default
            }
          }
          updateHomeStatus(heroLine);
          updateStatus(heroLine);
        }

        function ensureRowArray(rows) {
          if (!Array.isArray(rows)) {
            throw new Error("buildRows must return an array");
          }
          return rows;
        }

        if (tableSelect && typeof tableSelect.buildRows === "function") {
          const sel = document.getElementById(tableSelect.selectId);
          const rebuildFromTable = () => {
            const key = sel && sel.value ? sel.value : "";
            allRows = ensureRowArray(tableSelect.buildRows(parsed, key));
            applyHeroLine({ tablePath: key, rowCount: allRows.length });
            runFilter();
          };
          if (sel) {
            while (sel.options.length > 1) {
              sel.remove(1);
            }
            const tkeys = Object.keys(parsed.tables || {}).sort();
            const formatOptionLabel =
              typeof tableSelect.formatOptionLabel === "function"
                ? tableSelect.formatOptionLabel
                : null;
            tkeys.forEach((k) => {
              const opt = document.createElement("option");
              opt.value = k;
              let text;
              if (formatOptionLabel) {
                try {
                  text = formatOptionLabel(k);
                } catch (_) {
                  text = null;
                }
              }
              if (text == null || text === "") {
                text = k.includes("/") ? k.split("/").pop() : k;
              }
              opt.textContent = text || k;
              sel.appendChild(opt);
            });
            sel.addEventListener("change", rebuildFromTable);
          }
          rebuildFromTable();
        } else if (viewTabs && viewTabs.tabs && viewTabs.defaultTab) {
          const tabKeys = Object.keys(viewTabs.tabs);
          if (tabKeys.length === 0) {
            throw new Error("viewTabs.tabs must be non-empty");
          }
          const defaultTabKey =
            typeof viewTabs.defaultTab === "string" && viewTabs.tabs[viewTabs.defaultTab]
              ? viewTabs.defaultTab
              : tabKeys[0];
          const tabButtons = document.querySelectorAll("[data-rsdw-view-tab]");
          function applyViewTab(key) {
            const fn = viewTabs.tabs[key];
            if (typeof fn !== "function") {
              return;
            }
            allRows = ensureRowArray(fn(parsed));
            tabButtons.forEach((btn) => {
              const k = btn.getAttribute("data-rsdw-view-tab");
              const on = k === key;
              btn.classList.toggle("active", on);
              btn.setAttribute("aria-selected", on ? "true" : "false");
            });
            applyHeroLine({ tab: key, rowCount: allRows.length });
            runFilter();
          }
          tabButtons.forEach((btn) => {
            btn.addEventListener("click", () => {
              const k = btn.getAttribute("data-rsdw-view-tab");
              if (k) {
                applyViewTab(k);
              }
            });
          });
          applyViewTab(defaultTabKey);
        } else if (typeof buildRows === "function") {
          allRows = ensureRowArray(buildRows(parsed));
          applyHeroLine({ rowCount: allRows.length });
          runFilter();
        } else {
          throw new Error("Provide buildRows, viewTabs, or tableSelect");
        }

        updateHomeSubtitle(buildSubtitle(parsed));
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        updateHomeStatus(`Failed to load: ${msg}`);
        updateStatus(`Failed to load: ${msg}`);
        setLandingVisible(true);
      }
    }

    if (searchInput) {
      searchInput.addEventListener("input", () => {
        debouncedFilter();
      });
    }

    if (copyPreviewBtn) {
      copyPreviewBtn.addEventListener("click", async () => {
        if (!currentPayload) {
          return;
        }
        try {
          await copyTextToClipboard(getPreviewPanelText());
          showCopyToast("Copied to clipboard.");
        } catch {
          showCopyToast("Unable to copy.", true);
        }
      });
    }

    if (togglePreviewFormatBtn && hasWikiPreview) {
      togglePreviewFormatBtn.addEventListener("click", () => {
        previewIsWiki = !previewIsWiki;
        updatePreviewFormatButtonLabel();
        if (currentPayload && fileContentEl) {
          fileContentEl.textContent = getPreviewPanelText();
        }
      });
      togglePreviewFormatBtn.setAttribute("type", "button");
      togglePreviewFormatBtn.disabled = true;
      updatePreviewFormatButtonLabel();
    }

    if (fileNameToggleBtn) {
      fileNameToggleBtn.addEventListener("click", () => {
        showFileNames = !showFileNames;
        fileNameToggleBtn.textContent = showFileNames ? "Hide File Names" : "Show File Names";
        fileNameToggleBtn.setAttribute("aria-pressed", showFileNames ? "true" : "false");
        renderList();
      });
      fileNameToggleBtn.setAttribute("type", "button");
      fileNameToggleBtn.setAttribute("aria-pressed", "false");
      fileNameToggleBtn.textContent = showFileNames ? "Hide File Names" : "Show File Names";
    }

    boot();
  }

  global.rsdwInitFlatDatasetViewer = initFlatDatasetViewer;
  global.rsdwDatasetViewerConstants = { MAX_RESULTS, DEBOUNCE_MS };
})(window);
