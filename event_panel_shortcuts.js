/* Event shortcut: open the requested panel before scrolling to its filters. */
(function () {
  "use strict";
  function attachEventShortcuts() {
    document.querySelectorAll('a[data-feature-open-panel]').forEach(function (link) {
      link.addEventListener("click", function (event) {
        var panelId = link.getAttribute("data-feature-open-panel");
        if (!["releasePanel", "promoPanel", "purchasePanel"].includes(panelId)) return;
        var panel = document.getElementById(panelId);
        if (!panel || typeof selectInfoPanel !== "function") return;
        if (!selectInfoPanel(panelId)) return;
        event.preventDefault();
        var filter = panel.querySelector(".release-tools") || panel;
        filter.scrollIntoView({ behavior: "auto", block: "start" });
      });
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attachEventShortcuts, { once: true });
  } else {
    attachEventShortcuts();
  }
})();
