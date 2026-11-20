document.querySelectorAll("[data-switch]").forEach((root) => {
  root.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-panel]");
    if (!button || !root.contains(button)) {
      return;
    }
    const id = button.getAttribute("data-panel");
    root.querySelectorAll("button[data-panel]").forEach((item) => {
      const on = item === button;
      item.classList.toggle("on", on);
      item.setAttribute("aria-pressed", on ? "true" : "false");
    });
    root.querySelectorAll("[data-panel-id]").forEach((panel) => {
      panel.hidden = panel.getAttribute("data-panel-id") !== id;
    });
  });
});
