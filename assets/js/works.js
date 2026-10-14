(function () {
  "use strict";

  var isTouch = ("ontouchstart" in window) || navigator.maxTouchPoints > 0;
  if (isTouch) {
    document.documentElement.classList.add("touch");
  }

  var preview = document.getElementById("works-preview");
  var emptyState = document.getElementById("preview-empty");
  var links = document.querySelectorAll(".works-list a[data-slug]");
  var mediaEls = document.querySelectorAll(".works-preview [data-slug]");

  if (!preview || !links.length) return;

  var activeSlug = null;
  var vimeoState = {}; // slug -> { status: loading | ready | failed, player, video }

  function noop() {}

  function playVimeo(el) {
    var slug = el.getAttribute("data-slug");
    var state = vimeoState[slug];

    if (state && state.status === "ready") {
      state.player.setCurrentTime(0).catch(noop);
      state.player.play().catch(noop);
      return;
    }
    if (state && state.status === "failed") {
      if (state.video) {
        try { state.video.currentTime = 0; } catch (err) {}
        state.video.play().catch(noop);
      }
      return;
    }
    if (state) return; // still loading

    state = vimeoState[slug] = { status: "loading" };
    if (!window.PortfolioVimeo) {
      state.status = "failed";
      return;
    }
    // The player is created on first hover and kept, so later hovers are instant.
    window.PortfolioVimeo.mount(el, el.getAttribute("data-vimeo")).then(function (result) {
      state.status = "ready";
      state.player = result.player;
      if (activeSlug !== slug) result.player.pause().catch(noop);
    }).catch(function () {
      state.status = "failed";
      state.video = window.PortfolioVimeo.fallback(el);
      if (state.video && activeSlug !== slug) state.video.pause();
    });
  }

  function pauseVimeo(el) {
    var state = vimeoState[el.getAttribute("data-slug")];
    if (!state) return;
    if (state.status === "ready") state.player.pause().catch(noop);
    if (state.status === "failed" && state.video) state.video.pause();
  }

  function activate(slug) {
    activeSlug = slug;
    mediaEls.forEach(function (el) {
      var match = el.getAttribute("data-slug") === slug;
      el.classList.toggle("is-active", match);
      if (el.hasAttribute("data-vimeo")) {
        if (match) playVimeo(el); else pauseVimeo(el);
      } else if (el.tagName === "VIDEO") {
        if (match) {
          try { el.currentTime = 0; } catch (err) {}
          el.play().catch(noop);
        } else {
          el.pause();
        }
      }
    });
    if (emptyState) emptyState.style.display = "none";
    preview.classList.add("has-active");
  }

  function deactivateAll() {
    activeSlug = null;
    mediaEls.forEach(function (el) {
      el.classList.remove("is-active");
      if (el.hasAttribute("data-vimeo")) pauseVimeo(el);
      else if (el.tagName === "VIDEO") el.pause();
    });
    if (emptyState) emptyState.style.display = "";
    preview.classList.remove("has-active");
  }

  links.forEach(function (link) {
    var slug = link.getAttribute("data-slug");

    if (!isTouch) {
      link.addEventListener("mouseenter", function () { activate(slug); });
      link.addEventListener("focus", function () { activate(slug); });
      link.addEventListener("mouseleave", deactivateAll);
      link.addEventListener("blur", deactivateAll);
    } else {
      // Touch fallback: first tap previews in place, second tap navigates.
      link.addEventListener("click", function (e) {
        var alreadyActive = link.classList.contains("is-active");
        if (!alreadyActive) {
          e.preventDefault();
          links.forEach(function (l) { l.classList.remove("is-active"); });
          link.classList.add("is-active");
          activate(slug);
        }
      });
    }
  });
})();
