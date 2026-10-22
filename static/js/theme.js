(function () {
  const STORAGE_KEY = "rhziz-theme";

  function getStoredTheme() {
    return localStorage.getItem(STORAGE_KEY);
  }

  function getSystemTheme() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function getTheme() {
    return getStoredTheme() || getSystemTheme();
  }

  function applyTheme(theme) {
    var root = document.documentElement;
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-bs-theme", theme);
    root.style.colorScheme = theme;
    localStorage.setItem(STORAGE_KEY, theme);
  }

  window.toggleTheme = function () {
    var current = document.documentElement.getAttribute("data-theme") || getTheme();
    applyTheme(current === "dark" ? "light" : "dark");
  };

  applyTheme(getTheme());

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (event) {
    if (!getStoredTheme()) {
      applyTheme(event.matches ? "dark" : "light");
    }
  });
})();
