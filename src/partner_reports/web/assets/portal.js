// Progressive enhancement only: every form works without this file.
(function () {
  "use strict";
  document.querySelectorAll("[data-dropzone]").forEach(function (zone) {
    var input = zone.querySelector("input[type=file]");
    var name = zone.querySelector("[data-dropzone-name]");
    if (!input || !name) return;
    var initial = name.textContent;
    function show() {
      var file = input.files && input.files[0];
      name.textContent = file ? file.name : initial;
      zone.classList.toggle("has-file", Boolean(file));
    }
    ["dragenter", "dragover"].forEach(function (type) {
      zone.addEventListener(type, function () { zone.classList.add("is-over"); });
    });
    ["dragleave", "drop"].forEach(function (type) {
      zone.addEventListener(type, function () { zone.classList.remove("is-over"); });
    });
    input.addEventListener("change", show);
    show();
  });
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector("button[type=submit]");
      if (button && form.checkValidity()) {
        window.setTimeout(function () { button.classList.add("is-busy"); button.setAttribute("aria-busy", "true"); }, 0);
      }
    });
  });
})();
