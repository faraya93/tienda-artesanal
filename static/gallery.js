(function () {
  var gallery = document.querySelector("[data-gallery]");
  if (!gallery) return;

  var slides = Array.prototype.slice.call(gallery.querySelectorAll(".gallery-slide"));
  var thumbs = Array.prototype.slice.call(gallery.querySelectorAll(".thumb"));
  var stage = gallery.querySelector(".gallery-stage");
  if (!slides.length || !stage) return;

  var index = 0;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  gallery.classList.add("is-ready");
  if (slides.length < 2) gallery.classList.add("is-single");
  stage.tabIndex = 0;

  function show(next) {
    index = (next + slides.length) % slides.length;
    slides.forEach(function (slide, slideIndex) {
      var active = slideIndex === index;
      slide.classList.toggle("is-active", active);
      slide.setAttribute("aria-hidden", active ? "false" : "true");
      var video = slide.querySelector("video");
      if (!video) return;
      if (!active) {
        video.pause();
      } else if (!reduceMotion) {
        var play = video.play();
        if (play && play.catch) play.catch(function () {});
      }
    });
    thumbs.forEach(function (thumb, thumbIndex) {
      var active = thumbIndex === index;
      thumb.classList.toggle("is-active", active);
      if (active) thumb.setAttribute("aria-current", "true");
      else thumb.removeAttribute("aria-current");
    });
  }

  var prev = gallery.querySelector("[data-prev]");
  var next = gallery.querySelector("[data-next]");
  if (prev) prev.addEventListener("click", function () { show(index - 1); });
  if (next) next.addEventListener("click", function () { show(index + 1); });

  thumbs.forEach(function (thumb) {
    thumb.addEventListener("click", function () {
      show(Number(thumb.getAttribute("data-index")) || 0);
    });
  });

  stage.addEventListener("keydown", function (event) {
    if (event.key === "ArrowRight") show(index + 1);
    if (event.key === "ArrowLeft") show(index - 1);
  });

  var startX = 0;
  var startY = 0;
  stage.addEventListener("touchstart", function (event) {
    startX = event.changedTouches[0].clientX;
    startY = event.changedTouches[0].clientY;
  }, { passive: true });
  stage.addEventListener("touchend", function (event) {
    var dx = event.changedTouches[0].clientX - startX;
    var dy = event.changedTouches[0].clientY - startY;
    if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) return;
    show(index + (dx < 0 ? 1 : -1));
  }, { passive: true });

  show(0);
})();
