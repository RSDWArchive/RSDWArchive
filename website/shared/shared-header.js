/* RSDWArchive shared header injector.
 *
 * Renders the fixed header and footer into:
 *   <div id="rsdw-header-mount"></div>
 *   <div id="rsdw-footer-mount"></div>
 *
 * Pages declare their active viewer with <body data-archive-page="item-data">.
 * Search pages add data-search-placeholder; map pages add data-map-status.
 */
(function () {
  "use strict";

  var ARCHIVE_PAGES = [
    { id: "location-data", name: "LocationData", pageLabel: "Location Data", href: "/location-data/" },
    { id: "map", name: "Chunk Map", pageLabel: "Chunk Map", href: "/map/" },
    { id: "location-map", name: "Interactive Map", pageLabel: "Interactive Map", href: "/location-map/" },
    { id: "loot-data", name: "LootData", pageLabel: "Loot Data", href: "/loot-data/" },
    { id: "name-data", name: "NameData", pageLabel: "Name Data", href: "/name-data/" },
    { id: "npc-data", name: "NPCData", pageLabel: "NPC Data", href: "/npc-data/" },
    { id: "item-data", name: "ItemData", pageLabel: "Item Data", href: "/item-data/" },
    { id: "plan-data", name: "PlanData", pageLabel: "Plan Data", href: "/plan-data/" },
    { id: "progression-data", name: "ProgressionData", pageLabel: "Progression Data", href: "/progression-data/" },
    { id: "quest-data", name: "QuestData", pageLabel: "Quest Data", href: "/quest-data/" },
    { id: "recipe-data", name: "RecipeData", pageLabel: "Recipe Data", href: "/recipe-data/" },
    { id: "spell-data", name: "SpellData", pageLabel: "Spell Data", href: "/spell-data/" },
    { id: "vestige-data", name: "VestigeData", pageLabel: "Vestige Data", href: "/vestige-data/" }
  ];

  var REPO_URL = "https://github.com/RSDWArchive/RSDWArchive";
  var PAGE_ICON = "/shared/assets/page-icons/archive-viewer.png";
  var DISCORD_LINKS = [
    { name: "Official", href: "https://discord.com/invite/rsdragonwilds" },
    { name: "Wiki", href: "https://discord.com/invite/rsdwwiki" },
    { name: "Creative & Sharing", href: "https://discord.gg/hPJfrZxPss" }
  ];

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        var value = attrs[key];
        if (value === null || value === undefined) return;
        if (key === "class") node.className = value;
        else if (key === "text") node.textContent = value;
        else node.setAttribute(key, value);
      });
    }
    (children || []).forEach(function (child) {
      if (child == null) return;
      if (typeof child === "string") node.appendChild(document.createTextNode(child));
      else node.appendChild(child);
    });
    return node;
  }

  function pageLabelFor(activePage) {
    if (!activePage || activePage === "home") return "Home";
    for (var i = 0; i < ARCHIVE_PAGES.length; i++) {
      if (ARCHIVE_PAGES[i].id === activePage) {
        return ARCHIVE_PAGES[i].pageLabel || ARCHIVE_PAGES[i].name;
      }
    }
    return "";
  }

  function closeMenu(menu, toggle) {
    if (!menu || !toggle) return;
    menu.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }

  function renderCenter(body, activePage) {
    var searchPlaceholder = body.getAttribute("data-search-placeholder");
    if (searchPlaceholder !== null) {
      return el("div", { class: "rsdw-header-search" }, [
        el("label", { class: "rsdw-sr", for: "file-search" }, [
          body.getAttribute("data-search-label") || "Search"
        ]),
        el("input", {
          id: "file-search",
          class: "rsdw-header-search__input",
          type: "search",
          placeholder: searchPlaceholder || "Search...",
          autocomplete: "off",
          spellcheck: "false"
        })
      ]);
    }

    var mapStatus = body.getAttribute("data-map-status");
    if (mapStatus !== null) {
      return el("p", {
        id: "map-status",
        class: "map-toolbar-status",
        role: "status",
        "aria-live": "polite"
      }, [mapStatus || "Loading..."]);
    }

    return el("div", { class: "rsdw-page-title" }, [pageLabelFor(activePage)]);
  }

  function renderHeader(activePage) {
    var body = document.body;
    var header = el("header", { class: "rsdw-header", role: "banner" });

    header.appendChild(
      el("a", { class: "rsdw-brand", href: "/", "aria-label": "RSDW Archive home" }, [
        el("span", { class: "rsdw-brand__logo" }, [
          el("img", { id: "site-logo", src: "/shared/assets/logo.png", alt: "" })
        ]),
        el("span", { class: "rsdw-brand__title" }, ["RSDW Archive"])
      ])
    );

    header.appendChild(renderCenter(body, activePage));

    var actions = el("div", { class: "rsdw-actions" });

    var discordWrap = el("div", { class: "rsdw-tools" });
    var discordToggle = el("button", {
      class: "rsdw-iconbtn",
      id: "discord-toggle",
      type: "button",
      "aria-haspopup": "menu",
      "aria-expanded": "false",
      "aria-label": "Open Discord menu",
      title: "Discord"
    }, [el("img", { src: "/shared/assets/tool-icons/discord.png", alt: "" })]);
    var discordMenu = el("div", {
      class: "rsdw-tools__menu",
      id: "discord-dropdown",
      role: "menu",
      hidden: ""
    }, DISCORD_LINKS.map(function (link) {
      return el("a", {
        href: link.href,
        role: "menuitem",
        target: "_blank",
        rel: "noopener noreferrer"
      }, [link.name]);
    }));
    discordWrap.appendChild(discordToggle);
    discordWrap.appendChild(discordMenu);
    actions.appendChild(discordWrap);

    actions.appendChild(
      el("a", {
        class: "rsdw-iconbtn",
        href: REPO_URL,
        target: "_blank",
        rel: "noopener noreferrer",
        "aria-label": "Open GitHub repository",
        title: "GitHub"
      }, [el("img", { src: "/shared/assets/github.svg", alt: "" })])
    );

    var toolsWrap = el("div", { class: "rsdw-tools" });
    var toolsToggle = el("button", {
      class: "rsdw-iconbtn",
      id: "tools-toggle",
      type: "button",
      "aria-haspopup": "menu",
      "aria-expanded": "false",
      "aria-label": "Open archive viewer menu",
      title: "Archive viewers"
    }, [el("img", { src: "/shared/assets/tools-menu.png", alt: "" })]);
    var toolsMenu = el("div", {
      class: "rsdw-tools__menu rsdw-archive-menu",
      id: "tools-dropdown",
      role: "menu",
      hidden: ""
    }, ARCHIVE_PAGES.map(function (page) {
      var attrs = {
        href: page.href,
        role: "menuitem",
        "data-archive-page": page.id
      };
      if (page.id === activePage) attrs.class = "is-active";
      return el("a", attrs, [
        el("img", { src: PAGE_ICON, alt: "" }),
        page.name
      ]);
    }));
    toolsWrap.appendChild(toolsToggle);
    toolsWrap.appendChild(toolsMenu);
    actions.appendChild(toolsWrap);
    header.appendChild(actions);

    toolsToggle.addEventListener("click", function (event) {
      event.stopPropagation();
      var open = toolsMenu.hidden;
      toolsMenu.hidden = !open;
      toolsToggle.setAttribute("aria-expanded", String(open));
      if (open) closeMenu(discordMenu, discordToggle);
    });
    discordToggle.addEventListener("click", function (event) {
      event.stopPropagation();
      var open = discordMenu.hidden;
      discordMenu.hidden = !open;
      discordToggle.setAttribute("aria-expanded", String(open));
      if (open) closeMenu(toolsMenu, toolsToggle);
    });
    document.addEventListener("click", function (event) {
      if (!toolsWrap.contains(event.target)) closeMenu(toolsMenu, toolsToggle);
      if (!discordWrap.contains(event.target)) closeMenu(discordMenu, discordToggle);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      if (!toolsMenu.hidden) {
        closeMenu(toolsMenu, toolsToggle);
        toolsToggle.focus();
      }
      if (!discordMenu.hidden) {
        closeMenu(discordMenu, discordToggle);
        discordToggle.focus();
      }
    });

    return header;
  }

  function renderFooter() {
    return el("footer", { class: "rsdw-footer" }, [
      el("p", null, ["Game files & assets are property of Jagex Ltd."]),
      el("p", null, [
        el("a", { href: "/" }, ["Archive"]),
        " - ",
        el("a", { href: "https://rsdwbuilds.com", target: "_blank", rel: "noopener" }, ["Builds"]),
        " - ",
        el("a", { href: "https://rsdwmodel.com", target: "_blank", rel: "noopener" }, ["Model"]),
        " - ",
        el("a", { href: "https://rsdwtools.com", target: "_blank", rel: "noopener" }, ["Tools"])
      ])
    ]);
  }

  function init() {
    document.documentElement.classList.add("rsdw");
    var activePage = document.body.getAttribute("data-archive-page") || "";
    var headerMount = document.getElementById("rsdw-header-mount");
    var footerMount = document.getElementById("rsdw-footer-mount");

    if (headerMount) headerMount.replaceWith(renderHeader(activePage));
    else document.body.insertBefore(renderHeader(activePage), document.body.firstChild);
    if (footerMount) footerMount.replaceWith(renderFooter());
  }

  window.RSDW_ARCHIVE_PAGES = ARCHIVE_PAGES;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
