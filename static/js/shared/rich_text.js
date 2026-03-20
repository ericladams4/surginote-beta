const FONT_FAMILY_OPTIONS = [
  { value: "system-ui", label: "System Sans" },
  { value: "Georgia, serif", label: "Georgia" },
  { value: "\"Helvetica Neue\", Helvetica, Arial, sans-serif", label: "Helvetica" },
  { value: "Arial, sans-serif", label: "Arial" },
  { value: "\"Times New Roman\", Times, serif", label: "Times" },
  { value: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace", label: "Monospace" },
];

const FONT_SIZE_OPTIONS = [
  { value: "14px", label: "14" },
  { value: "15px", label: "15" },
  { value: "16px", label: "16" },
  { value: "18px", label: "18" },
  { value: "20px", label: "20" },
];

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function _markToHtml(mark, text) {
  const safeText = escapeHtml(text || "");
  if (mark === "exact") {
    return `<span data-template-mark="exact" class="template-mark template-mark-exact">${safeText}</span>`;
  }
  if (mark === "guide") {
    return `<span data-template-mark="guide" class="template-mark template-mark-guide">${safeText}</span>`;
  }
  return safeText;
}

function _replaceInlineStyleMarkers(text) {
  return String(text || "")
    .replace(/&lt;strong&gt;([\s\S]*?)&lt;\/strong&gt;/gi, "<strong>$1</strong>")
    .replace(/&lt;b&gt;([\s\S]*?)&lt;\/b&gt;/gi, "<strong>$1</strong>")
    .replace(/&lt;em&gt;([\s\S]*?)&lt;\/em&gt;/gi, "<em>$1</em>")
    .replace(/&lt;i&gt;([\s\S]*?)&lt;\/i&gt;/gi, "<em>$1</em>")
    .replace(/&lt;u&gt;([\s\S]*?)&lt;\/u&gt;/gi, "<u>$1</u>");
}

function normalizeEditorHtml(html) {
  const trimmed = String(html || "").trim();
  return trimmed || "<div><br></div>";
}

function plainTextToRichHtml(text) {
  const normalized = String(text || "").replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return "<div><br></div>";
  }

  const blocks = normalized.split(/\n{2,}/);
  return blocks.map((block) => {
    const lines = block.split("\n").map((line) => {
      return _replaceInlineStyleMarkers(escapeHtml(line))
        .replace(/\[\[EXACT\]\]([\s\S]*?)\[\[\/EXACT\]\]/gi, (_, content) => _markToHtml("exact", content))
        .replace(/\[\[GUIDE\]\]([\s\S]*?)\[\[\/GUIDE\]\]/gi, (_, content) => _markToHtml("guide", content));
    });
    return `<div>${lines.join("<br>")}</div>`;
  }).join("");
}

function serializeNode(node, depth = 0) {
  if (!node) return "";
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent || "";
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return "";
  }

  const tag = node.tagName.toLowerCase();

  if (tag === "br") {
    return "\n";
  }

  if (tag === "ul" || tag === "ol") {
    const items = Array.from(node.children).filter((child) => child.tagName && child.tagName.toLowerCase() === "li");
    return items.map((child, index) => {
      const prefix = tag === "ol" ? `${index + 1}. ` : "- ";
      return `${prefix}${serializeNode(child, depth + 1).trim()}`;
    }).join("\n");
  }

  if (tag === "li") {
    return Array.from(node.childNodes).map((child) => serializeNode(child, depth + 1)).join("");
  }

  if (tag === "span") {
    const mark = node.getAttribute("data-template-mark");
    const content = Array.from(node.childNodes).map((child) => serializeNode(child, depth + 1)).join("");
    if (mark === "exact") {
      return `[[EXACT]]${content}[[/EXACT]]`;
    }
    if (mark === "guide") {
      return `[[GUIDE]]${content}[[/GUIDE]]`;
    }
    return content;
  }

  if (tag === "strong" || tag === "b") {
    const content = Array.from(node.childNodes).map((child) => serializeNode(child, depth + 1)).join("");
    return `<strong>${content}</strong>`;
  }

  if (tag === "em" || tag === "i") {
    const content = Array.from(node.childNodes).map((child) => serializeNode(child, depth + 1)).join("");
    return `<em>${content}</em>`;
  }

  if (tag === "u") {
    const content = Array.from(node.childNodes).map((child) => serializeNode(child, depth + 1)).join("");
    return `<u>${content}</u>`;
  }

  const blockTags = new Set(["div", "p", "section", "article", "header", "footer"]);
  if (blockTags.has(tag)) {
    const content = Array.from(node.childNodes).map((child) => serializeNode(child, depth + 1)).join("").trimEnd();
    return content ? `${content}\n` : "";
  }

  return Array.from(node.childNodes).map((child) => serializeNode(child, depth + 1)).join("");
}

function htmlToStructuredText(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(`<div>${html || ""}</div>`, "text/html");
  const root = doc.body.firstElementChild;
  if (!root) return "";

  const text = Array.from(root.childNodes).map((child) => serializeNode(child)).join("");
  return text
    .replace(/\u00a0/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function applyEditorTypography(editorEl, typography = {}) {
  if (!editorEl) return;
  const fontFamily = typography.fontFamily || "system-ui";
  const fontSize = typography.fontSize || "16px";
  editorEl.dataset.fontFamily = fontFamily;
  editorEl.dataset.fontSize = fontSize;
  editorEl.style.fontFamily = fontFamily;
  editorEl.style.fontSize = fontSize;
}

function execRichTextCommand(command, value = null) {
  document.execCommand("styleWithCSS", false, true);
  document.execCommand(command, false, value);
}

function applyTemplateHighlight(mark) {
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount || selection.isCollapsed) return false;
  const range = selection.getRangeAt(0);
  const text = range.toString();
  if (!text.trim()) return false;
  const wrapper = document.createElement("span");
  wrapper.setAttribute("data-template-mark", mark);
  wrapper.className = `template-mark template-mark-${mark}`;
  wrapper.textContent = text;
  range.deleteContents();
  range.insertNode(wrapper);
  selection.removeAllRanges();
  return true;
}

function clearTemplateHighlight() {
  const selection = window.getSelection();
  if (!selection || !selection.rangeCount) return false;
  const anchorNode = selection.anchorNode;
  const markedParent = anchorNode && anchorNode.parentElement
    ? anchorNode.parentElement.closest("[data-template-mark]")
    : null;
  if (!markedParent) return false;
  const textNode = document.createTextNode(markedParent.textContent || "");
  markedParent.replaceWith(textNode);
  return true;
}

function buildToolbarSelectMarkup(setting, options, extraClass = "") {
  const normalizedOptions = Array.isArray(options) ? options : [];
  const initial = normalizedOptions[0] || { value: "", label: "" };
  const optionMarkup = normalizedOptions.map((option) => (
    `<button type="button" class="rich-editor-select-option" data-editor-setting="${setting}" data-value="${escapeHtml(option.value)}" role="option" aria-selected="${option.value === initial.value ? "true" : "false"}">${escapeHtml(option.label)}</button>`
  )).join("");
  const nativeOptions = normalizedOptions.map((option) => (
    `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`
  )).join("");
  const classes = ["rich-editor-select-wrap", "rich-editor-select-shell", extraClass].filter(Boolean).join(" ");
  return `
    <div class="${classes}" data-editor-setting="${setting}">
      <button type="button" class="rich-editor-select-trigger" aria-haspopup="listbox" aria-expanded="false">
        <span class="rich-editor-select-trigger-label">${escapeHtml(initial.label)}</span>
      </button>
      <div class="rich-editor-select-menu hidden" role="listbox" aria-label="${escapeHtml(setting)}">
        ${optionMarkup}
      </div>
      <select class="rich-editor-select app-select-native-hidden" data-editor-setting="${setting}" aria-hidden="true" tabindex="-1">
        ${nativeOptions}
      </select>
    </div>
  `;
}

function syncToolbarSelectValue(toolbarEl, setting, value, options) {
  if (!toolbarEl || !setting) return;
  const normalizedOptions = Array.isArray(options) ? options : [];
  const shell = toolbarEl.querySelector(`.rich-editor-select-shell[data-editor-setting="${setting}"]`);
  if (!shell) return;
  const resolved = normalizedOptions.find((option) => option.value === value) || normalizedOptions[0];
  if (!resolved) return;
  const labelEl = shell.querySelector(".rich-editor-select-trigger-label");
  const nativeSelect = shell.querySelector(".rich-editor-select");
  if (labelEl) labelEl.textContent = resolved.label;
  if (nativeSelect) nativeSelect.value = resolved.value;
  shell.querySelectorAll(".rich-editor-select-option").forEach((optionEl) => {
    const isActive = optionEl.dataset.value === resolved.value;
    optionEl.classList.toggle("is-active", isActive);
    optionEl.setAttribute("aria-selected", isActive ? "true" : "false");
  });
}

function initializeToolbarSelectMenus(toolbarEl, onSelect) {
  if (!toolbarEl) return;

  function closeAllMenus() {
    toolbarEl.querySelectorAll(".rich-editor-select-shell").forEach((shell) => {
      shell.classList.remove("is-open");
      const trigger = shell.querySelector(".rich-editor-select-trigger");
      const menu = shell.querySelector(".rich-editor-select-menu");
      if (trigger) trigger.setAttribute("aria-expanded", "false");
      if (menu) menu.classList.add("hidden");
    });
  }

  toolbarEl.addEventListener("click", (event) => {
    const trigger = event.target.closest(".rich-editor-select-trigger");
    if (trigger && toolbarEl.contains(trigger)) {
      const shell = trigger.closest(".rich-editor-select-shell");
      const isOpen = shell && shell.classList.contains("is-open");
      closeAllMenus();
      if (shell && !isOpen) {
        shell.classList.add("is-open");
        trigger.setAttribute("aria-expanded", "true");
        const menu = shell.querySelector(".rich-editor-select-menu");
        if (menu) menu.classList.remove("hidden");
      }
      return;
    }

    const option = event.target.closest(".rich-editor-select-option");
    if (option && toolbarEl.contains(option)) {
      const shell = option.closest(".rich-editor-select-shell");
      const setting = option.dataset.editorSetting;
      const value = option.dataset.value;
      if (shell && setting && typeof onSelect === "function") {
        onSelect(setting, value);
      }
      closeAllMenus();
      return;
    }

    if (!event.target.closest(".rich-editor-select-shell")) {
      closeAllMenus();
    }
  });

  document.addEventListener("click", (event) => {
    if (!toolbarEl.contains(event.target)) {
      closeAllMenus();
    }
  });
}

function getToolbarActionTarget(event, toolbarEl) {
  const actionButton = event.target.closest("[data-editor-command]");
  if (actionButton && toolbarEl.contains(actionButton)) {
    return actionButton;
  }
  return null;
}

export {
  FONT_FAMILY_OPTIONS,
  FONT_SIZE_OPTIONS,
  normalizeEditorHtml,
  plainTextToRichHtml,
  htmlToStructuredText,
  applyEditorTypography,
  execRichTextCommand,
  applyTemplateHighlight,
  clearTemplateHighlight,
  buildToolbarSelectMarkup,
  syncToolbarSelectValue,
  initializeToolbarSelectMenus,
  getToolbarActionTarget,
};
