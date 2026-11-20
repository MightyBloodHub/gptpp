const specimen = document.querySelector("[data-specimen]");
const tabList = specimen.querySelector("[data-tabs]");
const tabs = [...tabList.querySelectorAll("button")];
const panels = tabs.map((tab) => document.getElementById(tab.dataset.panel));
const copyButton = specimen.querySelector("[data-copy]");
const status = specimen.querySelector("[data-status]");
let active = 0;
let selectionVersion = 0;
let pendingFeedback;

function selectTab(index, focus = false) {
  active = index;
  selectionVersion += 1;
  clearTimeout(pendingFeedback);
  copyButton.textContent = "Copy";
  status.textContent = "";
  tabs.forEach((tab, position) => {
    const selected = index === position;
    tab.setAttribute("aria-selected", selected);
    tab.tabIndex = selected ? 0 : -1;
    panels[position].hidden = !selected;
  });
  if (focus) tabs[index].focus();
}

tabList.setAttribute("role", "tablist");
tabs.forEach((tab, index) => {
  tab.setAttribute("role", "tab");
  tab.setAttribute("aria-controls", panels[index].id);
  panels[index].setAttribute("role", "tabpanel");
  panels[index].setAttribute("aria-labelledby", tab.id);
  panels[index].tabIndex = 0;
  panels[index].querySelector(".example-label").hidden = true;

  tab.addEventListener("click", () => selectTab(index));
  tab.addEventListener("keydown", (event) => {
    switch (event.key) {
      case "ArrowLeft":
      case "ArrowRight": {
        const direction = event.key === "ArrowRight" ? 1 : -1;
        selectTab((index + direction + tabs.length) % tabs.length, true);
        break;
      }
      case "Home":
        selectTab(0, true);
        break;
      case "End":
        selectTab(tabs.length - 1, true);
        break;
      default:
        return;
    }
    event.preventDefault();
  });
});

copyButton.addEventListener("click", async () => {
  const version = selectionVersion;
  const code = panels[active].querySelector("pre code");
  try {
    await navigator.clipboard.writeText(code.textContent);
    if (version !== selectionVersion) return;
    copyButton.textContent = "Copied";
    status.textContent = "Copied to clipboard.";
  } catch {
    if (version !== selectionVersion) return;
    const range = document.createRange();
    range.selectNodeContents(code);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    copyButton.textContent = "Selected";
    status.textContent = "Text selected. Use your device's copy command.";
  }
  clearTimeout(pendingFeedback);
  pendingFeedback = setTimeout(() => {
    copyButton.textContent = "Copy";
  }, 2200);
});

selectTab(0);
tabList.hidden = false;
copyButton.hidden = false;
