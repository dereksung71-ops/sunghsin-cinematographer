(function () {
  "use strict";

  var root = document.documentElement;

  function apply(lang) {
    root.setAttribute("data-lang", lang);
    root.lang = lang === "zh" ? "zh-Hant" : "en";
    var buttons = document.querySelectorAll("[data-set-lang]");
    Array.prototype.forEach.call(buttons, function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-set-lang") === lang));
    });
  }

  apply(root.getAttribute("data-lang") || "en");

  document.addEventListener("click", function (e) {
    var button = e.target.closest && e.target.closest("[data-set-lang]");
    if (!button) return;
    var lang = button.getAttribute("data-set-lang");
    try { localStorage.setItem("lang", lang); } catch (err) {}
    apply(lang);
  });
})();
