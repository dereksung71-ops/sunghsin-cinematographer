(function () {
  "use strict";

  var API_URL = "https://player.vimeo.com/api/player.js";
  var apiPromise = null;

  function loadApi() {
    if (window.Vimeo && window.Vimeo.Player) return Promise.resolve();
    if (apiPromise) return apiPromise;
    apiPromise = new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = API_URL;
      s.async = true;
      s.onload = function () {
        window.Vimeo && window.Vimeo.Player ? resolve() : reject(new Error("Vimeo API missing"));
      };
      s.onerror = function () { reject(new Error("Vimeo API blocked")); };
      document.head.appendChild(s);
    });
    return apiPromise;
  }

  // Background mode: autoplay, muted, looped, no controls or title.
  function playerSrc(id) {
    return "https://player.vimeo.com/video/" + id +
      "?background=1&autoplay=1&muted=1&loop=1&autopause=0&playsinline=1&dnt=1&app_id=58479";
  }

  // Adds a Vimeo player to `container`. Resolves once it is really playing;
  // rejects (and removes the iframe) if it errors or doesn't start in time
  // — e.g. the video is private on Vimeo, or Vimeo is unreachable.
  function mount(container, id, timeoutMs) {
    return loadApi().then(function () {
      return new Promise(function (resolve, reject) {
        var iframe = document.createElement("iframe");
        iframe.className = "vimeo-frame";
        iframe.setAttribute("allow", "autoplay; picture-in-picture");
        iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
        iframe.setAttribute("title", "");
        iframe.setAttribute("tabindex", "-1");
        iframe.setAttribute("aria-hidden", "true");
        iframe.src = playerSrc(id);
        container.appendChild(iframe);

        var player = new window.Vimeo.Player(iframe);
        var settled = false;
        var timer = setTimeout(function () { fail(new Error("timeout")); }, timeoutMs || 7000);

        function fail(err) {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          try { player.destroy().catch(function () {}); } catch (e) {}
          iframe.remove();
          reject(err);
        }

        // A real Vimeo player reports "loaded"/"play". A private or blocked video
        // never does, which is how we know to use the fallback instead.
        function ok() {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          resolve({ player: player, iframe: iframe });
        }
        player.on("loaded", ok);
        player.on("play", ok);
        player.on("playing", ok);
        // Fade the player in only once frames are actually moving.
        ["play", "playing", "timeupdate"].forEach(function (name) {
          player.on(name, function () { iframe.classList.add("is-playing"); });
        });
        player.on("error", function () { fail(new Error("player error")); });
      });
    });
  }

  // Plays the film's own video file instead (only if one was published).
  function fallback(container) {
    var src = container.getAttribute("data-fallback-src");
    if (!src) return null;
    var video = document.createElement("video");
    video.className = "vimeo-fallback";
    video.muted = true;
    video.loop = true;
    video.playsInline = true;
    video.setAttribute("playsinline", "");
    var source = document.createElement("source");
    source.src = src;
    source.type = container.getAttribute("data-fallback-type") || "video/mp4";
    video.appendChild(source);
    container.appendChild(video);
    var p = video.play();
    if (p && p.catch) p.catch(function () {});
    return video;
  }

  window.PortfolioVimeo = { mount: mount, fallback: fallback };

  // Home hero and project-page trailers: start as soon as the page opens.
  function initAuto() {
    var boxes = document.querySelectorAll(".vimeo-auto[data-vimeo]");
    Array.prototype.forEach.call(boxes, function (box) {
      mount(box, box.getAttribute("data-vimeo")).catch(function (err) {
        box.classList.add("vimeo-failed");
        box.setAttribute("data-fail", (err && err.message) || "unknown");
        fallback(box);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAuto);
  } else {
    initAuto();
  }
})();
