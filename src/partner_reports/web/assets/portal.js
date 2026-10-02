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
  var current = document.querySelector(".main-nav [aria-current=page]");
  if (current && current.parentElement.scrollWidth > current.parentElement.clientWidth) {
    current.parentElement.scrollLeft = current.offsetLeft - 16;
  }
  document.querySelectorAll("[data-copy-button]").forEach(function (button) {
    var source = document.querySelector("[data-copy-source]");
    if (!source) return;
    var label = button.textContent;
    button.addEventListener("click", function () {
      source.select();
      var done = function () {
        button.textContent = "Copiado ✓";
        window.setTimeout(function () { button.textContent = label; }, 2000);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(source.value).then(done, function () { document.execCommand("copy"); done(); });
      } else {
        document.execCommand("copy");
        done();
      }
    });
  });
  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var question = event.submitter && event.submitter.getAttribute("data-confirm");
      if (question && !window.confirm(question)) {
        event.preventDefault();
        return;
      }
      var button = event.submitter || form.querySelector("button[type=submit]");
      if (button && form.checkValidity()) {
        window.setTimeout(function () { button.classList.add("is-busy"); button.setAttribute("aria-busy", "true"); }, 0);
      }
    });
  });
})();
