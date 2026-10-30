/* OppScout AI: keeps the visitor's profile in this browser only.
 *
 * The profile is read from the form, saved to localStorage, and sent to the
 * server only when the visitor asks for matches. Storage can be blocked or
 * empty (private windows, cleared data), so every access is wrapped and the
 * page works without it.
 */
(function () {
  "use strict";

  var KEY = "oppscout.profile.v1";

  function loadProfile() {
    try {
      var raw = window.localStorage.getItem(KEY);
      var data = raw ? JSON.parse(raw) : null;
      return data && typeof data === "object" ? data : null;
    } catch (e) {
      return null;
    }
  }

  function saveProfile(data) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(data));
      return true;
    } catch (e) {
      return false;
    }
  }

  function clearProfile() {
    try {
      window.localStorage.removeItem(KEY);
    } catch (e) {
      /* nothing to clear */
    }
  }

  function readForm(form) {
    var data = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.name === "csrfmiddlewaretoken" || el.disabled) {
        return;
      }
      if (el.type === "checkbox") {
        if (!data[el.name]) {
          data[el.name] = [];
        }
        if (el.checked) {
          data[el.name].push(el.value);
        }
      } else if (el.type !== "submit" && el.type !== "button") {
        data[el.name] = el.value;
      }
    });
    return data;
  }

  function writeForm(form, data) {
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.name === "csrfmiddlewaretoken" || !(el.name in data)) {
        return;
      }
      var value = data[el.name];
      if (el.type === "checkbox") {
        el.checked = Array.isArray(value) && value.indexOf(el.value) !== -1;
      } else if (el.type !== "submit" && el.type !== "button") {
        el.value = typeof value === "string" ? value : "";
      }
    });
  }

  function init() {
    var form = document.getElementById("profile-form");
    if (!form) {
      return;
    }
    var status = document.getElementById("profile-status");
    var results = document.getElementById("matches");
    var clearButton = document.getElementById("clear-profile");

    function say(message) {
      if (status) {
        status.textContent = message;
      }
    }

    var stored = loadProfile();
    if (stored) {
      writeForm(form, stored);
      say("Loaded your saved profile from this browser.");
    }

    function persist() {
      if (saveProfile(readForm(form))) {
        say("Saved in this browser.");
      } else {
        say("This browser is blocking storage, so your profile will not be remembered.");
      }
    }

    form.addEventListener("input", persist);
    form.addEventListener("change", persist);

    if (clearButton) {
      clearButton.addEventListener("click", function () {
        clearProfile();
        form.reset();
        if (results) {
          results.innerHTML = "";
        }
        say("Profile cleared from this browser.");
      });
    }
  }

  // Eligibility checks: add the saved profile fields to the request.
  // Only the fields the check needs are added; interests, goals and
  // preferences stay in the browser.
  var SENT = ["country", "education_level", "field_of_study",
              "current_qualification", "skills", "experience"];

  document.addEventListener("htmx:configRequest", function (evt) {
    var el = evt.detail.elt;
    if (el && el.id === "saved-form") {
      evt.detail.parameters.slugs = loadSaved().join(",");
      return;
    }
    if (!el || (el.id !== "eligibility-form" && el.id !== "gap-form")) {
      return;
    }
    var stored = loadProfile() || {};
    SENT.forEach(function (name) {
      if (typeof stored[name] === "string" && stored[name]) {
        evt.detail.parameters[name] = stored[name];
      }
    });
  });

  // Saved opportunities: a list of slugs in this browser only.
  var SAVED_KEY = "oppscout.saved.v1";
  var SAVED_MAX = 50;

  function loadSaved() {
    try {
      var raw = window.localStorage.getItem(SAVED_KEY);
      var list = raw ? JSON.parse(raw) : [];
      return Array.isArray(list)
        ? list.filter(function (s) { return typeof s === "string"; }).slice(0, SAVED_MAX)
        : [];
    } catch (e) {
      return [];
    }
  }

  function storeSaved(list) {
    try {
      window.localStorage.setItem(SAVED_KEY, JSON.stringify(list));
      return true;
    } catch (e) {
      return false;
    }
  }

  function storageWorks() {
    try {
      window.localStorage.setItem("oppscout.test", "1");
      window.localStorage.removeItem("oppscout.test");
      return true;
    } catch (e) {
      return false;
    }
  }

  function syncSaveButtons() {
    var saved = loadSaved();
    var usable = storageWorks();
    Array.prototype.forEach.call(document.querySelectorAll("[data-save]"), function (btn) {
      if (!usable) {
        btn.hidden = true;
        return;
      }
      var on = saved.indexOf(btn.getAttribute("data-save")) !== -1;
      btn.hidden = false;
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.textContent = on ? "Saved" : "Save";
    });
  }

  document.addEventListener("click", function (evt) {
    var btn = evt.target.closest ? evt.target.closest("[data-save]") : null;
    if (!btn) {
      return;
    }
    var slug = btn.getAttribute("data-save");
    var saved = loadSaved();
    var at = saved.indexOf(slug);
    if (at === -1) {
      if (saved.length >= SAVED_MAX) {
        btn.textContent = "List full (50)";
        return;
      }
      saved.push(slug);
    } else {
      saved.splice(at, 1);
    }
    storeSaved(saved);
    var list = document.getElementById("saved-list");
    var card = btn.closest(".opp-card");
    if (list && card && list.contains(card) && at !== -1) {
      card.remove();
      if (!list.querySelector(".opp-card")) {
        list.innerHTML = '<div class="empty"><p>You have not saved anything yet.</p></div>';
      }
      return;
    }
    syncSaveButtons();
  });

  document.addEventListener("htmx:afterSwap", syncSaveButtons);
  // Organization form: show only the extra fields that belong to the chosen
  // category. Without JavaScript every extra field stays visible.
  function initOppForm() {
    var form = document.getElementById("opp-form");
    if (!form) {
      return;
    }
    var map = {};
    try {
      map = JSON.parse(form.getAttribute("data-extra-map") || "{}");
    } catch (e) {
      return;
    }
    var select = form.querySelector("[name=category]");
    if (!select) {
      return;
    }
    function apply() {
      var shown = map[select.value] || [];
      Array.prototype.forEach.call(form.querySelectorAll("[data-extra-key]"), function (box) {
        box.hidden = shown.indexOf(box.getAttribute("data-extra-key")) === -1;
      });
    }
    select.addEventListener("change", apply);
    apply();
  }

  document.addEventListener("DOMContentLoaded", initOppForm);
  document.addEventListener("DOMContentLoaded", syncSaveButtons);
  document.addEventListener("DOMContentLoaded", init);
})();
