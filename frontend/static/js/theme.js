(() => {
  const storageKey = "loup-garou-theme";
  const modes = ["dynamic", "dark", "light"];
  const media = window.matchMedia("(prefers-color-scheme: light)");
  const labels = {
    fr: {dynamic: "Dynamique", dark: "Sombre", light: "Clair"},
    en: {dynamic: "Dynamic", dark: "Dark", light: "Light"},
    tn: {dynamic: "Dynamic", dark: "Dark", light: "Light"},
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

  document.addEventListener("DOMContentLoaded", () => {
    apply(currentPreference(), false);
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
