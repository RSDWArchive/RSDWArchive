/* RSDWArchive Discord menu toggle.
 *
 * Wires up the Discord button (#discord-toggle) and dropdown
 * (#discord-dropdown) inserted in each page's <header>. Mirrors the
 * existing tools-toggle/tools-dropdown behavior (hidden + aria state +
 * outside-click + Escape).
 */
(function () {
  "use strict";

  function init() {
    var toggle = document.getElementById("discord-toggle");
    var menu = document.getElementById("discord-dropdown");
    if (!toggle || !menu) return;

    function setOpen(open) {
      menu.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
    }

    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      setOpen(menu.hidden);
    });

    document.addEventListener("click", function (e) {
      if (!(e.target instanceof Node)) return;
      if (!menu.contains(e.target) && !toggle.contains(e.target)) {
        setOpen(false);
      }
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !menu.hidden) {
        setOpen(false);
        toggle.focus();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
