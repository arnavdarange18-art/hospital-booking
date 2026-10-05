// Progressive enhancement only: every page still works with JavaScript turned off.
(function () {
  "use strict";

  // Toasts: auto-dismiss, and close on request.
  function dismiss(toast) {
    toast.classList.add("is-leaving");
    setTimeout(function () {
      toast.remove();
    }, 260);
  }
  document.querySelectorAll("[data-toast]").forEach(function (toast) {
    var delay = toast.classList.contains("toast--error") ? 9000 : 5000;
    setTimeout(function () {
      if (toast.isConnected) dismiss(toast);
    }, delay);
    var close = toast.querySelector("[data-toast-close]");
    if (close) close.addEventListener("click", function () { dismiss(toast); });
  });

  // Slot picker: nothing is bookable until a time is chosen, then say exactly what will happen.
  document.querySelectorAll("[data-picker]").forEach(function (form) {
    var summary = form.querySelector("[data-summary]");
    var submit = form.querySelector("[data-submit]");
    var who = form.getAttribute("data-who") || "";
    if (!summary || !submit) return;
    submit.disabled = true;
    form.querySelectorAll('input[name="start"]').forEach(function (radio) {
      radio.addEventListener("change", function () {
        summary.textContent = radio.getAttribute("data-label") + (who ? " with " + who : "");
        submit.disabled = false;
      });
    });
  });

  // Password visibility toggle.
  document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
    var input = document.getElementById(button.getAttribute("data-toggle-password"));
    if (!input) return;
    button.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      button.setAttribute("aria-pressed", String(show));
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      button.querySelector("[data-eye]").hidden = show;
      button.querySelector("[data-eye-off]").hidden = !show;
    });
  });

  // Date inputs that jump straight to the chosen day.
  document.querySelectorAll("[data-autosubmit]").forEach(function (input) {
    input.addEventListener("change", function () {
      if (input.value && input.form) input.form.submit();
    });
  });

  // Ask before cancelling or removing anything.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) event.preventDefault();
    });
  });

  // Close the account menu when clicking elsewhere or pressing Escape.
  var menu = document.querySelector(".user-menu");
  if (menu) {
    document.addEventListener("click", function (event) {
      if (!menu.contains(event.target)) menu.removeAttribute("open");
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") menu.removeAttribute("open");
    });
  }

  // Admin user table: filter by role and by text.
  var table = document.querySelector("[data-user-table]");
  if (table) {
    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));
    var roleButtons = document.querySelectorAll("[data-role-filter]");
    var search = document.querySelector("[data-user-search]");
    var empty = document.querySelector("[data-no-match]");
    var role = "all";

    var apply = function () {
      var text = search ? search.value.trim().toLowerCase() : "";
      var shown = 0;
      rows.forEach(function (row) {
        var match =
          (role === "all" || row.getAttribute("data-role") === role) &&
          (!text || row.textContent.toLowerCase().indexOf(text) !== -1);
        row.hidden = !match;
        if (match) shown += 1;
      });
      if (empty) empty.hidden = shown !== 0;
    };

    roleButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        role = button.getAttribute("data-role-filter");
        roleButtons.forEach(function (other) {
          other.setAttribute("aria-pressed", String(other === button));
          other.classList.toggle("is-on", other === button);
        });
        apply();
      });
    });
    if (search) search.addEventListener("input", apply);
  }

  // Keep the selected day visible in the date strip.
  var selected = document.querySelector(".strip .day.is-selected");
  if (selected && selected.parentElement) {
    var strip = selected.parentElement;
    strip.scrollLeft = selected.offsetLeft - strip.offsetLeft - 8;
  }
})();
