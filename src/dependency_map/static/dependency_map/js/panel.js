function initTabs() {
    var root = document.getElementById("djdt-depmap");
    if (!root) return;

    root.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-depmap-tab]");
        if (!btn) return;

        var tab = btn.getAttribute("data-depmap-tab");
        var reqPane = document.getElementById("djdt-depmap-request");
        var allPane = document.getElementById("djdt-depmap-all");

        if (reqPane) reqPane.style.display = tab === "request" ? "" : "none";
        if (allPane) allPane.style.display = tab === "all" ? "" : "none";

        root.querySelectorAll(".dm-tab").forEach(function (b) {
            b.classList.toggle("active", b === btn);
        });
    });
}

var djDebug = document.getElementById("djDebug");
initTabs();
djDebug.addEventListener("djdt.panel.render", function (event) {
    if (event.detail.panelId === "DependenciesPanel") {
        initTabs();
    }
});
