(() => {
  const storageKey = "loup-garou-theme";
  const modes = ["dynamic", "dark", "light"];
  const media = window.matchMedia("(prefers-color-scheme: light)");
  const labels = {
    fr: {dynamic: "Dynamique", dark: "Sombre", light: "Clair"},
    en: {dynamic: "Dynamic", dark: "Dark", light: "Light"},
    tn: {dynamic: "Dynamic", dark: "Dark", light: "Light"},
  };
  const passwordLabels = {
    fr: {show: "Afficher le mot de passe", hide: "Masquer le mot de passe"},
    en: {show: "Show password", hide: "Hide password"},
    tn: {show: "Warri el mot de passe", hide: "5abbi el mot de passe"},
  };
  const icons = {dynamic: "🌗", dark: "🌙", light: "☀️"};

  function language() {
    const code = (document.documentElement.lang || "tn").toLowerCase().split("-")[0];
    return labels[code] ? code : "en";
  }

  function currentPreference() {
    const value = document.documentElement.dataset.theme;
    return modes.includes(value) ? value : "dynamic";
  }

  function resolve(preference) {
    if (preference !== "dynamic") return preference;
    const narrator = document.body?.classList.contains("narrator-page");
    if (narrator) return document.body.classList.contains("day-mode") ? "light" : "dark";
    return media.matches ? "light" : "dark";
  }

  function renderControls(preference) {
    const copy = labels[language()];
    document.querySelectorAll(".theme-toggle").forEach(button => {
      button.querySelector(".theme-toggle-icon").textContent = icons[preference];
      button.querySelector(".theme-toggle-label").textContent = copy[preference];
      button.dataset.mode = preference;
      button.title = `${copy[preference]} · ${copy[modes[(modes.indexOf(preference) + 1) % modes.length]]}`;
      button.setAttribute("aria-label", button.title);
    });
  }

  function apply(preference, persist = true) {
    const resolved = resolve(preference);
    document.documentElement.dataset.theme = preference;
    document.documentElement.dataset.themeResolved = resolved;
    document.documentElement.style.colorScheme = resolved;
    document.querySelectorAll('meta[name="theme-color"]').forEach(meta => {
      meta.content = resolved === "light" ? "#f4eee2" : "#080d12";
    });
    if (persist) {
      try { localStorage.setItem(storageKey, preference); } catch (_) {}
    }
    renderControls(preference);
  }

  function enhancePasswordFields() {
    const copy = passwordLabels[language()];
    document.querySelectorAll('input[type="password"]').forEach((input, index) => {
      if (input.closest(".password-field")) return;
      if (!input.id) input.id = `password-field-${index + 1}`;

      const wrapper = document.createElement("div");
      wrapper.className = "password-field";
      input.before(wrapper);
      wrapper.append(input);

      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "password-toggle";
      toggle.setAttribute("aria-controls", input.id);
      toggle.setAttribute("aria-pressed", "false");
      toggle.setAttribute("aria-label", copy.show);
      toggle.title = copy.show;
      toggle.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.7"></circle><path class="password-hidden-mark" d="M4 4l16 16"></path></svg>`;
      wrapper.append(toggle);

      toggle.addEventListener("click", () => {
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        toggle.classList.toggle("is-visible", show);
        toggle.setAttribute("aria-pressed", String(show));
        toggle.setAttribute("aria-label", show ? copy.hide : copy.show);
        toggle.title = show ? copy.hide : copy.show;
        input.focus({preventScroll: true});
        const end = input.value.length;
        input.setSelectionRange?.(end, end);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    apply(currentPreference(), false);
    enhancePasswordFields();
    if (document.body.classList.contains("narrator-page")) {
      new MutationObserver(() => {
        if (currentPreference() === "dynamic") apply("dynamic", false);
      }).observe(document.body, {attributes: true, attributeFilter: ["class"]});
    }
    document.addEventListener("click", event => {
      const button = event.target.closest(".theme-toggle");
      if (!button) return;
      const current = currentPreference();
      apply(modes[(modes.indexOf(current) + 1) % modes.length]);
    });
  });

  const syncDynamicTheme = () => {
    if (currentPreference() === "dynamic") apply("dynamic", false);
  };
  if (media.addEventListener) media.addEventListener("change", syncDynamicTheme);
  else media.addListener?.(syncDynamicTheme);
})();
