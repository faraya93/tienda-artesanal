(function () {
  var form = document.querySelector("[data-product-form]");
  if (!form) return;

  var list = form.querySelector("[data-media-list]");
  var input = form.querySelector('input[name="new_media"]');
  var zone = form.querySelector("[data-dropzone]");
  var message = form.querySelector("[data-media-message]");
  var pick = form.querySelector("[data-pick]");
  if (!list || !input || !zone) return;

  var filesById = new Map();
  var sequence = 0;
  var dragged = null;

  form.classList.add("is-enhanced");
  zone.hidden = false;
  input.setAttribute("aria-hidden", "true");
  input.tabIndex = -1;

  function counts() {
    var items = list.querySelectorAll("li");
    var images = 0;
    var videos = 0;
    items.forEach(function (item) {
      if (item.getAttribute("data-type") === "video") videos += 1;
      else images += 1;
    });
    return { images: images, videos: videos };
  }

  function kind(file) {
    var name = (file.name || "").toLowerCase();
    if (/\.(jpe?g|png|webp)$/.test(name)) return "image";
    if (/\.(mp4|webm)$/.test(name)) return "video";
    return null;
  }

  function normalize() {
    list.querySelectorAll('li[data-type="video"]').forEach(function (item) {
      list.appendChild(item);
    });
    var firstImage = list.querySelector('li[data-type="image"]');
    list.querySelectorAll("li").forEach(function (item) {
      item.classList.toggle("is-cover", item === firstImage);
    });
  }

  function addFiles(fileList) {
    var notes = [];
    Array.prototype.forEach.call(fileList, function (file) {
      var type = kind(file);
      if (!type) {
        notes.push(file.name + " no es jpg, png, webp, mp4 ni webm.");
        return;
      }
      var current = counts();
      if (type === "image" && current.images >= 6) {
        notes.push("Máximo 6 imágenes.");
        return;
      }
      if (type === "video" && current.videos >= 1) {
        notes.push("Solo un video.");
        return;
      }
      sequence += 1;
      var id = "n" + sequence;
      filesById.set(id, file);
      var item = document.createElement("li");
      item.draggable = true;
      item.setAttribute("data-new-id", id);
      item.setAttribute("data-type", type);
      if (type === "image") {
        var img = document.createElement("img");
        img.src = URL.createObjectURL(file);
        img.alt = "";
        item.appendChild(img);
      } else {
        var video = document.createElement("video");
        video.muted = true;
        video.playsInline = true;
        video.src = URL.createObjectURL(file);
        item.appendChild(video);
      }
      var remove = document.createElement("button");
      remove.type = "button";
      remove.setAttribute("data-remove", "1");
      remove.textContent = "Quitar";
      item.appendChild(remove);
      list.appendChild(item);
    });
    if (message) message.textContent = notes.join(" ");
    normalize();
  }

  list.addEventListener("click", function (event) {
    var button = event.target.closest("[data-remove]");
    if (!button) return;
    var item = button.closest("li");
    if (item.getAttribute("data-new-id")) filesById.delete(item.getAttribute("data-new-id"));
    item.remove();
    normalize();
  });

  list.addEventListener("dragstart", function (event) {
    var item = event.target.closest("li");
    if (!item) return;
    dragged = item;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", "reorder");
  });
  list.addEventListener("dragover", function (event) {
    event.preventDefault();
    var item = event.target.closest("li");
    if (!item || !dragged || item === dragged) return;
    var rect = item.getBoundingClientRect();
    var before = event.clientY < rect.top + rect.height / 2;
    list.insertBefore(dragged, before ? item : item.nextSibling);
  });
  list.addEventListener("drop", function (event) {
    if (event.dataTransfer.files && event.dataTransfer.files.length) {
      event.preventDefault();
      addFiles(event.dataTransfer.files);
    }
  });
  list.addEventListener("dragend", function () {
    dragged = null;
    normalize();
  });

  if (pick) {
    pick.addEventListener("click", function (event) {
      event.stopPropagation();
      input.click();
    });
  }
  zone.addEventListener("click", function (event) {
    if (event.target.closest("button, a, input")) return;
    input.click();
  });
  zone.addEventListener("dragover", function (event) {
    event.preventDefault();
    zone.classList.add("is-over");
  });
  zone.addEventListener("dragleave", function () { zone.classList.remove("is-over"); });
  zone.addEventListener("drop", function (event) {
    event.preventDefault();
    zone.classList.remove("is-over");
    addFiles(event.dataTransfer.files);
  });
  input.addEventListener("change", function () {
    addFiles(input.files);
    input.value = "";
  });

  form.addEventListener("submit", function () {
    normalize();
    var transfer = new DataTransfer();
    var tokens = [];
    var nextIndex = 0;
    list.querySelectorAll("li").forEach(function (item) {
      if (item.getAttribute("data-existing-id")) {
        tokens.push("e:" + item.getAttribute("data-existing-id"));
      } else if (filesById.has(item.getAttribute("data-new-id"))) {
        tokens.push("n:" + nextIndex);
        transfer.items.add(filesById.get(item.getAttribute("data-new-id")));
        nextIndex += 1;
      }
    });
    form.querySelector("[name=media_order]").value = tokens.join(",");
    form.querySelector("[name=media_order_set]").value = "1";
    input.files = transfer.files;
  });

  normalize();
})();
