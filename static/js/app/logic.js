import {
  FONT_FAMILY_OPTIONS,
  FONT_SIZE_OPTIONS,
  applyEditorTypography,
  buildToolbarSelectMarkup,
  execRichTextCommand,
  getToolbarActionTarget,
  initializeToolbarSelectMenus,
  syncToolbarSelectValue,
} from "/static/js/shared/rich_text.js";

const appState = window.__APP_STATE__ || {};
const shorthandEl = document.getElementById("shorthand");
const outputEl = document.getElementById("output");
const outputWrapEl = document.getElementById("outputWrap");
const consultOutputEl = document.getElementById("consultOutput");
const richOutputEl = document.getElementById("richOutput");
const outputFormattingToolbarEl = document.getElementById("outputFormattingToolbar");

const generateBtn = document.getElementById("generateBtn");
const demoBtn = document.getElementById("demoBtn");
const copyBtn = document.getElementById("copyBtn");
const copyBtnBottom = document.getElementById("copyBtnBottom");

const generatingStatusEl = document.getElementById("generatingStatus");
const generatingStatusTextEl = document.getElementById("generatingStatusText");
const generatingStatusSubtextEl = document.getElementById("generatingStatusSubtext");

const noteTypeEl = document.getElementById("noteType");
const noteTypeTriggerEl = document.getElementById("noteTypeTrigger");
const noteTypeTriggerLabelEl = document.getElementById("noteTypeLabelText");
const noteTypeMenuEl = document.getElementById("noteTypeMenu");
const noteTypeOptionEls = Array.from(document.querySelectorAll(".note-type-option"));
const outputLabelEl = document.getElementById("outputLabel");
const templatesNavLinkEl = document.getElementById("templatesNavLink");
const inputTemplateRuntimeEl = document.getElementById("inputTemplateRuntime");
const inputTemplateRuntimeLabelEl = document.getElementById("inputTemplateRuntimeLabel");
const inputTemplateRuntimePillsEl = document.getElementById("inputTemplateRuntimePills");
const outputTemplateRuntimeEl = document.getElementById("outputTemplateRuntime");
const outputTemplateRuntimeLabelEl = document.getElementById("outputTemplateRuntimeLabel");
const outputTemplateRuntimePillsEl = document.getElementById("outputTemplateRuntimePills");
const onboardingModalEl = document.getElementById("onboardingModal");
const onboardingStartBtn = document.getElementById("onboardingStartBtn");
const onboardingTemplatesBtn = document.getElementById("onboardingTemplatesBtn");
const ratingModalEl = document.getElementById("ratingModal");
const ratingModalBackdropEl = document.getElementById("ratingModalBackdrop");
const ratingOptionGridEl = document.getElementById("ratingOptionGrid");
const ratingModalSkipEl = document.getElementById("ratingModalSkip");
const ratingModalStatusEl = document.getElementById("ratingModalStatus");
const recentNotesListEl = document.getElementById("recentNotesList");
const recentNotesEmptyEl = document.getElementById("recentNotesEmpty");

/* -------------------- Template settings / modal -------------------- */

const openTemplateSettingsBtn = document.getElementById("openTemplateSettingsBtn");
const templateModalEl = document.getElementById("templateModal");
const closeTemplateModalBtn = document.getElementById("closeTemplateModalBtn");

const templateHeadingEl = document.getElementById("templateHeading");
const templateEditorEl = document.getElementById("templateEditor");
const saveTemplateBtn = document.getElementById("saveTemplateBtn");
const deleteTemplateBtn = document.getElementById("deleteTemplateBtn");
const templateStatusEl = document.getElementById("templateStatus");

let latestProcedure = "";
let latestCaseFacts = null;
let currentLoadedTemplate = "";
let currentLoadedNoteType = noteTypeEl ? noteTypeEl.value : "consult_note";
let currentConsultSegments = [];
let currentRichSegments = [];
let activeAssumptionIndex = null;
let activeAssumptionEl = null;
let assumptionHideTimeout = null;
let loadingMessageInterval = null;
let activeTemplateSummary = appState.activeTemplateSummary || null;
let lastAppliedTemplateTags = [];
let latestTeachingSignals = null;
let demoTypingTimeout = null;
let demoTypingRunId = 0;
let lastRatedOutputText = "";
let ratingModalResolver = null;
let ratingModalActiveText = "";
let onboardingCompleting = false;

const RECENT_NOTES_STORAGE_KEY = "surginote.recentNotes.v1";
const RECENT_NOTES_SELECTED_KEY = "surginote.recentNotes.selected.v1";
const RATED_NOTES_STORAGE_KEY = "surginote.ratedNotes.v1";
const MAX_RECENT_NOTES = 5;

const loadingSubtexts = [
  "Anesthesia delay.",
  "Waiting for the OR to turn over.",
  "Surgery running behind.",
  "Consent still being witnessed.",
  "Closing skin. Almost there.",
];

const assumptionPopoverEl = outputWrapEl ? document.createElement("div") : null;
const assumptionLabelEl = document.createElement("div");
const assumptionInputEl = document.createElement("input");
const assumptionActionsEl = document.createElement("div");
const assumptionAcceptBtn = document.createElement("button");
const assumptionHelpEl = document.createElement("div");

if (assumptionPopoverEl) {
  assumptionPopoverEl.className = "consult-assumption-popover hidden";
  assumptionLabelEl.className = "consult-assumption-label";
  assumptionLabelEl.textContent = "Assumption";
  assumptionInputEl.className = "consult-assumption-input";
  assumptionInputEl.type = "text";
  assumptionActionsEl.className = "consult-assumption-actions";
  assumptionAcceptBtn.className = "consult-assumption-accept";
  assumptionAcceptBtn.type = "button";
  assumptionAcceptBtn.textContent = "Accept assumption";
  assumptionHelpEl.className = "consult-assumption-help";
  assumptionHelpEl.textContent = "Edit this assumption to change the generated note.";
  assumptionPopoverEl.appendChild(assumptionLabelEl);
  assumptionPopoverEl.appendChild(assumptionInputEl);
  assumptionActionsEl.appendChild(assumptionAcceptBtn);
  assumptionPopoverEl.appendChild(assumptionActionsEl);
  assumptionPopoverEl.appendChild(assumptionHelpEl);
  outputWrapEl.appendChild(assumptionPopoverEl);
}

/* -------------------- Helpers -------------------- */

function humanizeKey(key) {
  if (!key) return "";
  return String(key)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function buildRichToolbarMarkup() {
  return `
    ${buildToolbarSelectMarkup("font-family", FONT_FAMILY_OPTIONS)}
    ${buildToolbarSelectMarkup("font-size", FONT_SIZE_OPTIONS.map((option) => ({ ...option, label: `${option.label}px` })), "rich-editor-select-wrap-size")}
    <button type="button" class="rich-editor-tool" data-editor-command="bold" aria-label="Bold"><strong>B</strong></button>
    <button type="button" class="rich-editor-tool" data-editor-command="italic" aria-label="Italic"><em>I</em></button>
    <button type="button" class="rich-editor-tool" data-editor-command="underline" aria-label="Underline"><u>U</u></button>
    <button type="button" class="rich-editor-tool" data-editor-command="insertUnorderedList" aria-label="Bulleted list">• List</button>
    <button type="button" class="rich-editor-tool" data-editor-command="insertOrderedList" aria-label="Numbered list">1. List</button>
  `;
}

function getActiveOutputEditor() {
  if (noteTypeEl && noteTypeEl.value === "consult_note") {
    return consultOutputEl;
  }
  return richOutputEl;
}

function syncOutputToolbarTypography() {
  if (!outputFormattingToolbarEl) return;
  const activeEditor = getActiveOutputEditor();
  if (!activeEditor) return;
  syncToolbarSelectValue(outputFormattingToolbarEl, "font-family", activeEditor.dataset.fontFamily || "system-ui", FONT_FAMILY_OPTIONS);
  syncToolbarSelectValue(
    outputFormattingToolbarEl,
    "font-size",
    activeEditor.dataset.fontSize || "16px",
    FONT_SIZE_OPTIONS.map((option) => ({ ...option, label: `${option.label}px` }))
  );
}

function applyOutputTypographyFromSummary() {
  const typography = {
    fontFamily: appState.outputTypography?.font_family || "system-ui",
    fontSize: appState.outputTypography?.font_size || "16px",
  };
  if (shorthandEl) {
    shorthandEl.style.fontFamily = typography.fontFamily;
    shorthandEl.style.fontSize = typography.fontSize;
  }
  applyEditorTypography(consultOutputEl, typography);
  applyEditorTypography(richOutputEl, typography);
  syncOutputToolbarTypography();
}

async function performCopyAction() {
  const text = getCurrentOutputText();
  const copyButtons = [copyBtn, copyBtnBottom].filter(Boolean);
  if (!text || !copyButtons.length) return;

  copyButtons.forEach((button) => {
    button.disabled = true;
    button.classList.remove("is-copied", "is-failed");
  });

  const ok = await copyTextWithFallback(text);
  copyButtons.forEach((button) => {
    const labelEl = button.querySelector(".copy-action-label");
    if (labelEl) {
      labelEl.textContent = ok ? "Copied" : "Copy failed";
    } else {
      button.textContent = ok ? "Copied" : "Copy failed";
    }
    button.classList.add(ok ? "is-copied" : "is-failed");
  });

  if (ok) {
    await promptForCopyRating(text);
  }

  setTimeout(() => {
    copyButtons.forEach((button) => {
      const defaultLabel = button.dataset.defaultLabel || "Copy note";
      const labelEl = button.querySelector(".copy-action-label");
      if (labelEl) {
        labelEl.textContent = defaultLabel;
      } else {
        button.textContent = defaultLabel;
      }
      button.disabled = false;
      button.classList.remove("is-copied", "is-failed");
    });
  }, 1500);
}

async function copyTextWithFallback(text) {
  if (!text) return false;

  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) {}

  try {
    const temp = document.createElement("textarea");
    temp.value = text;
    temp.style.position = "fixed";
    temp.style.left = "-9999px";
    document.body.appendChild(temp);
    temp.select();

    const successful = document.execCommand("copy");
    document.body.removeChild(temp);
    return successful;
  } catch (_) {
    return false;
  }
}

async function submitCopyFeedback({ text, rating }) {
  const response = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rating: String(rating),
      note_type: noteTypeEl ? noteTypeEl.value : "consult_note",
      shorthand: shorthandEl ? shorthandEl.value : "",
      generated_note: text,
      procedure: latestProcedure || "",
      delivery_action: "copy",
      teaching_signals: latestTeachingSignals || {},
      exact_used_count: countExactBlocksUsed(activeTemplateSummary, text),
    }),
  });

  if (!response.ok) {
    let message = "Unable to save feedback.";
    try {
      const data = await response.json();
      message = data.error || message;
    } catch (_) {}
    throw new Error(message);
  }
}

function buildRatedNoteKey({ noteType, shorthand, text }) {
  return JSON.stringify({
    noteType: String(noteType || "").trim(),
    shorthand: String(shorthand || "").trim(),
    text: String(text || "").trim(),
  });
}

function readRatedNoteKeys() {
  try {
    const raw = window.localStorage.getItem(RATED_NOTES_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(Boolean) : [];
  } catch (_) {
    return [];
  }
}

function writeRatedNoteKeys(keys) {
  try {
    window.localStorage.setItem(RATED_NOTES_STORAGE_KEY, JSON.stringify(keys.slice(-100)));
  } catch (_) {}
}

function hasRatedNote({ noteType, shorthand, text }) {
  const key = buildRatedNoteKey({ noteType, shorthand, text });
  return readRatedNoteKeys().includes(key);
}

function rememberRatedNote({ noteType, shorthand, text }) {
  const key = buildRatedNoteKey({ noteType, shorthand, text });
  const keys = readRatedNoteKeys().filter((item) => item !== key);
  keys.push(key);
  writeRatedNoteKeys(keys);
}

async function promptForCopyRating(text) {
  const noteType = noteTypeEl ? noteTypeEl.value : "consult_note";
  const shorthand = shorthandEl ? shorthandEl.value : "";
  if (!text || text === lastRatedOutputText || hasRatedNote({ noteType, shorthand, text })) return;
  const rating = await openRatingModal(text);
  if (!rating) return;

  try {
    setRatingModalStatus("Saving score...");
    await submitCopyFeedback({ text, rating });
    lastRatedOutputText = text;
    rememberRatedNote({ noteType, shorthand, text });
    closeRatingModal();
  } catch (error) {
    console.error(error);
    if (String(error.message || "").toLowerCase().includes("already")) {
      lastRatedOutputText = text;
      rememberRatedNote({ noteType, shorthand, text });
      closeRatingModal();
      return;
    }
    setRatingOptionState(false);
    setRatingModalStatus(error.message || "Unable to save score.");
  }
}

function setRatingModalStatus(message = "") {
  if (ratingModalStatusEl) {
    ratingModalStatusEl.textContent = message;
  }
}

function closeRatingModal() {
  if (!ratingModalEl) return;
  ratingModalEl.classList.add("hidden");
  ratingModalEl.setAttribute("aria-hidden", "true");
  setRatingModalStatus("");
  ratingModalActiveText = "";
  if (ratingOptionGridEl) {
    ratingOptionGridEl.querySelectorAll(".rating-option").forEach((button) => {
      button.disabled = false;
      button.classList.remove("is-selected");
    });
  }
  ratingModalResolver = null;
}

function showOnboardingModal() {
  if (!onboardingModalEl) return;
  onboardingModalEl.classList.remove("hidden");
  onboardingModalEl.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function hideOnboardingModal() {
  if (!onboardingModalEl) return;
  onboardingModalEl.classList.add("hidden");
  onboardingModalEl.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function setOnboardingButtonsDisabled(disabled) {
  [onboardingStartBtn, onboardingTemplatesBtn].forEach((button) => {
    if (button) button.disabled = disabled;
  });
}

async function completeOnboarding() {
  if (onboardingCompleting) return;
  onboardingCompleting = true;
  setOnboardingButtonsDisabled(true);

  try {
    await fetch("/api/onboarding/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seen: true }),
    });
  } catch (error) {
    console.error("Unable to save onboarding state.", error);
  } finally {
    onboardingCompleting = false;
    setOnboardingButtonsDisabled(false);
  }
}

function setRatingOptionState(disabled) {
  if (!ratingOptionGridEl) return;
  ratingOptionGridEl.querySelectorAll(".rating-option").forEach((button) => {
    button.disabled = disabled;
  });
}

function resolveRatingModal(value = null) {
  if (typeof ratingModalResolver === "function") {
    const resolver = ratingModalResolver;
    ratingModalResolver = null;
    resolver(value);
  } else {
    ratingModalResolver = null;
  }
}

function openRatingModal(text) {
  if (!ratingModalEl) return Promise.resolve(window.prompt("Rate this note from 1 to 10.") || null);
  if (ratingModalResolver) {
    resolveRatingModal(null);
  }

  ratingModalActiveText = text;
  ratingModalEl.classList.remove("hidden");
  ratingModalEl.setAttribute("aria-hidden", "false");
  setRatingModalStatus("");

  if (ratingOptionGridEl) {
    ratingOptionGridEl.querySelectorAll(".rating-option").forEach((button) => {
      button.disabled = false;
      button.classList.remove("is-selected");
    });
    const first = ratingOptionGridEl.querySelector(".rating-option");
    if (first) first.focus();
  }

  return new Promise((resolve) => {
    ratingModalResolver = resolve;
  });
}

function noteTypeLabel(noteType) {
  if (noteType === "op_note") return "Op Note";
  if (noteType === "clinic_note") return "Clinic Note";
  if (noteType === "consult_note") return "Consult Note";
  return "Note";
}

function compactPreview(text, limit = 120) {
  const compact = String(text || "").replace(/\s+/g, " ").trim();
  if (compact.length <= limit) return compact;
  const clipped = compact.slice(0, limit - 1).trimEnd();
  return `${clipped}…`;
}

function sentenceCase(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function extractRecentNoteDiagnosis({ procedure, shorthand, outputText }) {
  if (procedure) {
    return sentenceCase(humanizeKey(procedure));
  }

  const haystack = `${shorthand || ""}\n${outputText || ""}`.toLowerCase();
  const patterns = [
    ["appendicitis", "Appendicitis"],
    ["cholecystitis", "Cholecystitis"],
    ["small bowel obstruction", "Small bowel obstruction"],
    ["diverticulitis", "Diverticulitis"],
    ["hernia", "Hernia"],
    ["breast mass", "Breast mass"],
    ["abscess", "Abscess"],
    ["biliary colic", "Biliary colic"],
  ];

  for (const [needle, label] of patterns) {
    if (haystack.includes(needle)) return label;
  }

  return "";
}

function deriveRecentNotePreview(shorthand) {
  const lines = String(shorthand || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 2);
  if (!lines.length) return "";
  return compactPreview(lines.join("\n"), 140);
}

function deriveRecentNoteTitle({ noteType, procedure, shorthand, outputText }) {
  const diagnosis = extractRecentNoteDiagnosis({ procedure, shorthand, outputText });
  if (diagnosis) {
    return diagnosis;
  }

  const shorthandLine = String(shorthand || "").split("\n").map((line) => line.trim()).find(Boolean);
  if (shorthandLine && shorthandLine.length > 8) {
    return compactPreview(shorthandLine, 64);
  }

  return `${noteTypeLabel(noteType)} draft`;
}

function formatRecentNoteTime(isoString) {
  if (!isoString) return "Just now";
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return "Just now";
  return parsed.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function readRecentNotes() {
  try {
    const raw = window.localStorage.getItem(RECENT_NOTES_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item) => item && item.outputText && item.shorthand);
  } catch (_) {
    return [];
  }
}

function writeRecentNotes(notes) {
  try {
    window.localStorage.setItem(RECENT_NOTES_STORAGE_KEY, JSON.stringify(notes));
  } catch (_) {}
}

function deleteRecentNote(index) {
  const notes = readRecentNotes();
  const note = notes[index];
  if (!note) return;

  const nextNotes = notes.filter((_, itemIndex) => itemIndex !== index);
  writeRecentNotes(nextNotes);
  if (readSelectedRecentNoteKey() === String(note.createdAt || "")) {
    writeSelectedRecentNoteKey("");
  }
  renderRecentNotesDock();
}

function readSelectedRecentNoteKey() {
  try {
    return window.localStorage.getItem(RECENT_NOTES_SELECTED_KEY) || "";
  } catch (_) {
    return "";
  }
}

function writeSelectedRecentNoteKey(value) {
  try {
    if (value) {
      window.localStorage.setItem(RECENT_NOTES_SELECTED_KEY, value);
    } else {
      window.localStorage.removeItem(RECENT_NOTES_SELECTED_KEY);
    }
  } catch (_) {}
}

function renderRecentNotesDock() {
  if (!recentNotesListEl || !recentNotesEmptyEl) return;

  const notes = readRecentNotes();
  const selectedKey = readSelectedRecentNoteKey();
  recentNotesListEl.innerHTML = "";
  recentNotesEmptyEl.classList.toggle("hidden", notes.length > 0);

  if (!notes.length) {
    return;
  }

  notes.forEach((note, index) => {
    const derivedTitle = deriveRecentNoteTitle({
      noteType: note.noteType,
      procedure: note.procedure,
      shorthand: note.shorthand,
      outputText: note.outputText,
    });
    const derivedPreview = deriveRecentNotePreview(note.shorthand) || compactPreview(note.shorthand || note.outputText, 140);

    const row = document.createElement("button");
    row.type = "button";
    row.className = `recent-note-row${selectedKey && selectedKey === String(note.createdAt || "") ? " is-active" : ""}`;
    row.dataset.action = "load";
    row.dataset.index = String(index);
    row.innerHTML = `
      <span class="recent-note-delete" data-action="delete" data-index="${index}" aria-label="Delete recent note" title="Delete recent note">×</span>
      <div class="recent-note-copy">
        <div class="recent-note-top">
          <div class="recent-note-title">${escapeHtml(derivedTitle || note.title || `${noteTypeLabel(note.noteType)} draft`)}</div>
          <span class="recent-note-badge">${escapeHtml(noteTypeLabel(note.noteType))}</span>
        </div>
        <div class="recent-note-meta">${escapeHtml(formatRecentNoteTime(note.createdAt))}</div>
        <div class="recent-note-preview">${escapeHtml(derivedPreview || note.preview || "")}</div>
      </div>
    `;
    recentNotesListEl.appendChild(row);
  });
}

function rememberRecentNote({ noteType, shorthand, outputText, procedure }) {
  const trimmedOutput = String(outputText || "").trim();
  const trimmedShorthand = String(shorthand || "").trim();
  if (!trimmedOutput || !trimmedShorthand) return;

  const nextEntry = {
    noteType: noteType || "consult_note",
    shorthand: trimmedShorthand,
    outputText: trimmedOutput,
    procedure: procedure || "",
    title: deriveRecentNoteTitle({
      noteType,
      procedure,
      shorthand: trimmedShorthand,
      outputText: trimmedOutput,
    }),
    preview: deriveRecentNotePreview(trimmedShorthand) || compactPreview(trimmedShorthand, 140),
    createdAt: new Date().toISOString(),
  };

  const notes = readRecentNotes().filter((item) => !(
    item.noteType === nextEntry.noteType &&
    String(item.shorthand || "").trim() === nextEntry.shorthand
  ));
  notes.unshift(nextEntry);
  writeRecentNotes(notes.slice(0, MAX_RECENT_NOTES));
  writeSelectedRecentNoteKey(nextEntry.createdAt);
  renderRecentNotesDock();
}

async function restoreRecentNote(index) {
  const notes = readRecentNotes();
  const note = notes[index];
  if (!note) return;

  clearDemoTypingAnimation();
  if (shorthandEl) {
    shorthandEl.value = note.shorthand || "";
  }

  const restoredNoteType = note.noteType || "consult_note";
  if (noteTypeEl) {
    noteTypeEl.value = restoredNoteType;
  }
  updateNoteTypeLabels();
  syncNoteTypeDropdown();
  setOutputMode(restoredNoteType);
  latestProcedure = note.procedure || "";
  latestCaseFacts = null;
  writeSelectedRecentNoteKey(String(note.createdAt || ""));

  if (restoredNoteType === "consult_note") {
    currentConsultSegments = parseConsultTaggedOutput(note.outputText || "");
    renderConsultSegments();
  } else {
    clearConsultOutput();
    renderRichOutput(note.outputText || "");
  }

  await loadActiveTemplateSummary(restoredNoteType);

  if (outputWrapEl) {
    outputWrapEl.classList.remove("output-loading");
  }
  renderRecentNotesDock();
}

async function handleRecentNotesClick(event) {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const index = Number(button.dataset.index);
  if (Number.isNaN(index)) return;

  if (button.dataset.action === "load") {
    await restoreRecentNote(index);
    return;
  }

  if (button.dataset.action === "delete") {
    event.preventDefault();
    event.stopPropagation();
    deleteRecentNote(index);
  }
}

function clearDemoTypingAnimation() {
  if (demoTypingTimeout) {
    clearTimeout(demoTypingTimeout);
    demoTypingTimeout = null;
  }
  demoTypingRunId += 1;
}

function scheduleDemoTyping(callback, delay) {
  return new Promise((resolve) => {
    demoTypingTimeout = setTimeout(() => {
      demoTypingTimeout = null;
      callback();
      resolve();
    }, delay);
  });
}

async function animateDemoShorthand(sample) {
  if (!shorthandEl) return true;

  clearDemoTypingAnimation();
  const runId = demoTypingRunId;
  const text = String(sample || "");

  if (generateBtn) generateBtn.disabled = true;
  if (demoBtn) {
    demoBtn.disabled = true;
    demoBtn.textContent = "Building demo...";
  }

  shorthandEl.value = "";
  shorthandEl.focus();
  shorthandEl.setSelectionRange(0, 0);

  for (let i = 0; i < text.length; i += 1) {
    if (runId !== demoTypingRunId) return false;

    shorthandEl.value += text[i];
    shorthandEl.focus();
    shorthandEl.setSelectionRange(shorthandEl.value.length, shorthandEl.value.length);
    shorthandEl.scrollTop = shorthandEl.scrollHeight;

    const nextChar = text[i + 1] || "";
    let delay = 14;
    if (/[.,]/.test(text[i])) delay = 42;
    if (/[\n]/.test(text[i])) delay = 65;
    if (/\s/.test(nextChar)) delay = Math.max(delay, 22);

    await scheduleDemoTyping(() => {}, delay);
  }

  if (runId !== demoTypingRunId) return false;

  if (generateBtn) generateBtn.disabled = false;
  if (demoBtn) {
    demoBtn.disabled = false;
    demoBtn.textContent = "Demo";
  }

  return true;
}

function countExactBlocksUsed(summary, outputText) {
  if (!summary || !Array.isArray(summary.exact_blocks) || !summary.exact_blocks.length) return 0;
  const haystack = String(outputText || "").toLowerCase();
  let count = 0;
  for (const block of summary.exact_blocks) {
    const normalizedBlock = String(block || "").trim().toLowerCase();
    if (normalizedBlock && haystack.includes(normalizedBlock)) {
      count += 1;
    }
  }
  return count;
}

function buildTemplateTagPills(summary, mode = "detected", outputText = "") {
  if (!summary) return [];
  const pills = [];

  if (summary.strict_enabled) {
    pills.push({ label: mode === "applied" ? "FORMAT used" : "FORMAT", tone: "neutral" });
  }
  if ((summary.guide_block_count || 0) > 0) {
    pills.push({
      label: mode === "applied" ? "HABITS used" : "HABITS",
      tone: "neutral",
    });
  }
  if (summary.global_tone_enabled) {
    pills.push({
      label: mode === "applied" ? "TONE used" : "TONE",
      tone: "neutral",
    });
  }
  if ((summary.exact_block_count || 0) > 0) {
    const exactUsedCount = countExactBlocksUsed(summary, outputText);
    pills.push({
      label: mode === "applied"
        ? `Exact phrase used${exactUsedCount || exactUsedCount === 0 ? ` ${exactUsedCount}/${summary.exact_block_count}` : ""}`
        : `${summary.exact_block_count} exact phrase${summary.exact_block_count === 1 ? "" : "s"}`,
      tone: exactUsedCount ? "success" : "neutral",
    });
  }
  if ((summary.placeholder_count || 0) > 0) {
    pills.push({
      label: mode === "applied"
        ? `Template fields used ${summary.placeholder_count}`
        : `${summary.placeholder_count} template field${summary.placeholder_count === 1 ? "" : "s"}`,
      tone: "neutral",
    });
  }

  return pills;
}

function renderTemplateRuntimeRow(containerEl, labelEl, pillsEl, summary, mode = "detected", outputText = "") {
  if (!containerEl || !labelEl || !pillsEl) return;

  const pills = buildTemplateTagPills(summary, mode, outputText);
  if (!summary || !pills.length) {
    containerEl.classList.add("hidden");
    labelEl.textContent = "";
    pillsEl.innerHTML = "";
    return;
  }

  labelEl.textContent = mode === "applied"
    ? `Applied from ${summary.name}`
    : `Using ${summary.name}`;

  pillsEl.innerHTML = pills.map((pill) => (
    `<span class="template-runtime-pill${pill.tone === "accent" ? " is-accent" : ""}${pill.tone === "success" ? " is-success" : ""}">${escapeHtml(pill.label)}</span>`
  )).join("");
  containerEl.classList.remove("hidden");
}

function hasRealShorthandInput() {
  return Boolean(String(shorthandEl ? shorthandEl.value : "").trim());
}

function refreshTemplateRuntimeUI(outputText = "") {
  if (hasRealShorthandInput()) {
    renderTemplateRuntimeRow(
      inputTemplateRuntimeEl,
      inputTemplateRuntimeLabelEl,
      inputTemplateRuntimePillsEl,
      activeTemplateSummary,
      "detected",
      ""
    );
  } else {
    inputTemplateRuntimeEl?.classList.add("hidden");
    if (inputTemplateRuntimeLabelEl) inputTemplateRuntimeLabelEl.textContent = "";
    if (inputTemplateRuntimePillsEl) inputTemplateRuntimePillsEl.innerHTML = "";
  }

  if (outputText && activeTemplateSummary) {
    renderTemplateRuntimeRow(
      outputTemplateRuntimeEl,
      outputTemplateRuntimeLabelEl,
      outputTemplateRuntimePillsEl,
      activeTemplateSummary,
      "applied",
      outputText
    );
    lastAppliedTemplateTags = buildTemplateTagPills(activeTemplateSummary, "applied", outputText);
  } else if (!outputText) {
    outputTemplateRuntimeEl?.classList.add("hidden");
    if (outputTemplateRuntimeLabelEl) outputTemplateRuntimeLabelEl.textContent = "";
    if (outputTemplateRuntimePillsEl) outputTemplateRuntimePillsEl.innerHTML = "";
    lastAppliedTemplateTags = [];
  }
}

async function loadActiveTemplateSummary(noteType) {
  try {
    const res = await fetch(`/api/template-profiles/active/${encodeURIComponent(noteType)}`);
    const data = await res.json();
    if (!res.ok) return;
    activeTemplateSummary = data.profile || null;
  } catch (err) {
    console.error(err);
    activeTemplateSummary = null;
  } finally {
    applyOutputTypographyFromSummary();
    if (noteTypeEl && noteTypeEl.value === "consult_note") {
      if (currentConsultSegments.length) {
        renderConsultSegments();
      } else {
        refreshTemplateRuntimeUI(getCurrentOutputText());
      }
    } else if (outputEl && outputEl.value) {
      renderRichOutput(outputEl.value);
    } else {
      refreshTemplateRuntimeUI(getCurrentOutputText());
    }
  }
}

function isConsultSectionHeading(line) {
  return /^(Reason for Consult|HPI|Past Medical History|Medical History|Past Surgical History|Surgical History|Family History|Social History|Review of Systems|ROS|Objective|Assessment and Plan):?$/i.test(
    String(line || "").trim()
  );
}

function normalizeConsultHeading(line) {
  return String(line || "").trim().replace(/:?\s*$/, ":");
}

function isInlineExamLabel(line) {
  return /^(Gen|HEENT|Pulmonary|Cardiovascular|Abdomen|Labs|Imaging):\s*$/i.test(
    String(line || "").trim()
  );
}

function stopGeneratingStatus() {
  if (loadingMessageInterval) {
    clearInterval(loadingMessageInterval);
    loadingMessageInterval = null;
  }
  if (generatingStatusEl) {
    generatingStatusEl.classList.add("hidden");
  }
  if (generatingStatusTextEl) {
    generatingStatusTextEl.textContent = "";
  }
  if (generatingStatusSubtextEl) {
    generatingStatusSubtextEl.textContent = "";
  }
}

function startGeneratingStatus() {
  if (!generatingStatusEl) return;

  const messages = [...loadingSubtexts];
  let messageIndex = 0;

  generatingStatusEl.classList.remove("hidden");
  if (generatingStatusTextEl) {
    generatingStatusTextEl.textContent = "Generating note...";
  }
  if (generatingStatusSubtextEl) {
    generatingStatusSubtextEl.textContent = messages[0];
  }

  if (loadingMessageInterval) {
    clearInterval(loadingMessageInterval);
  }

  loadingMessageInterval = window.setInterval(() => {
    messageIndex = (messageIndex + 1) % messages.length;
    if (generatingStatusSubtextEl) {
      generatingStatusSubtextEl.textContent = messages[messageIndex];
    }
  }, 2200);
}

function showRetryGeneratingStatus() {
  if (!generatingStatusEl) return;

  if (loadingMessageInterval) {
    clearInterval(loadingMessageInterval);
    loadingMessageInterval = null;
  }

  generatingStatusEl.classList.remove("hidden");
  if (generatingStatusTextEl) {
    generatingStatusTextEl.textContent = "Sorry, need to reprep.";
  }
  if (generatingStatusSubtextEl) {
    generatingStatusSubtextEl.textContent = "Trying that again now.";
  }
}

function syncNoteTypeDropdown() {
  if (!noteTypeEl) return;

  const activeValue = noteTypeEl.value;

  if (noteTypeTriggerLabelEl) {
    noteTypeTriggerLabelEl.textContent = noteTypeLabel(activeValue);
  }

  if (templatesNavLinkEl) {
    templatesNavLinkEl.href = `/templates?note_type=${encodeURIComponent(activeValue)}`;
  }

  noteTypeOptionEls.forEach((optionEl) => {
    const isActive = optionEl.dataset.value === activeValue;
    optionEl.classList.toggle("is-active", isActive);
    optionEl.setAttribute("aria-selected", isActive ? "true" : "false");
  });
}

function closeNoteTypeMenu() {
  if (noteTypeMenuEl) {
    noteTypeMenuEl.classList.add("hidden");
  }
  if (noteTypeTriggerEl) {
    noteTypeTriggerEl.setAttribute("aria-expanded", "false");
    noteTypeTriggerEl.classList.remove("is-open");
  }
}

function openNoteTypeMenu() {
  if (noteTypeMenuEl) {
    noteTypeMenuEl.classList.remove("hidden");
  }
  if (noteTypeTriggerEl) {
    noteTypeTriggerEl.setAttribute("aria-expanded", "true");
    noteTypeTriggerEl.classList.add("is-open");
  }
}

function toggleNoteTypeMenu() {
  if (!noteTypeMenuEl || !noteTypeTriggerEl) return;

  if (noteTypeMenuEl.classList.contains("hidden")) {
    openNoteTypeMenu();
  } else {
    closeNoteTypeMenu();
  }
}

function escapeHtml(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeRegExp(text) {
  return String(text || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function stripConsultTags(text) {
  return String(text || "").replace(/\[\[(?:\/)?(?:FACT|ASSUMPTION)\]\]/g, "");
}

function sanitizeConsultTagArtifacts(text) {
  return String(text || "")
    .replace(/\[\[(?:\/)?(?:FACT|ASSUMPTION)\]\]/g, "")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")")
    .replace(/([A-Za-z0-9)])\(/g, "$1 (")
    .replace(/\)\s*([A-Za-z])/g, ") $1")
    .replace(/[ \t]{2,}/g, " ");
}

function preprocessConsultTaggedText(text) {
  const headingPattern = "(Reason for Consult|HPI|Past Medical History|Medical History|Past Surgical History|Surgical History|Family History|Social History|Review of Systems|ROS|Objective|Assessment and Plan)";

  return String(text || "")
    .replace(/(^|\n)\s*[•*]\s+/g, "$1- ")
    .replace(
      new RegExp(`([.!?])\\s+(${headingPattern})(:?)(?=(?:\\s|\\[\\[(?:FACT|ASSUMPTION)\\]\\]))`, "gi"),
      "$1\n$2$3\n"
    )
    .replace(
      new RegExp(`(^|\\n)\\s*(${headingPattern})(:?)[ \\t]+(?=(?:\\[\\[(?:FACT|ASSUMPTION)\\]\\])?\\S)`, "gi"),
      "$1$2$3\n"
    );
}

function normalizeConsultDisplayText(text) {
  const normalized = sanitizeConsultTagArtifacts(preprocessConsultTaggedText(String(text || "")))
    .replace(/(^|\n)\s*[•*]\s+/g, "$1- ")
    .replace(
      /(^|\n)\s*(Reason for Consult|HPI|Past Medical History|Medical History|Past Surgical History|Surgical History|Family History|Social History|Review of Systems|ROS|Objective|Assessment and Plan)(:?)[ \t]+(?=\S)/gi,
      "$1$2$3\n"
    );
  const lines = normalized.split("\n");
  const sectionHeadingPattern = /^(Reason for Consult|HPI|Past Medical History|Medical History|Past Surgical History|Surgical History|Family History|Social History|Review of Systems|ROS|Objective|Assessment and Plan):?\s*$/i;

  const result = [];

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/g, "");
    const trimmed = line.trim();

    if (!trimmed) {
      result.push("");
      continue;
    }

    if (
      sectionHeadingPattern.test(trimmed) ||
      /^-\s+/.test(trimmed) ||
      /^(Gen|HEENT|Pulmonary|Cardiovascular|Abdomen|Labs|Imaging):/i.test(trimmed)
    ) {
      result.push(isConsultSectionHeading(trimmed) ? `${trimmed.replace(/:?\s*$/, "")}:` : trimmed);
      continue;
    }

    if (!result.length || result[result.length - 1] === "") {
      result.push(trimmed);
      continue;
    }

    if (isConsultSectionHeading(result[result.length - 1])) {
      result.push(trimmed);
      continue;
    }

    result[result.length - 1] = `${result[result.length - 1]} ${trimmed}`.replace(/\s{2,}/g, " ");
  }

  const merged = [];
  for (let index = 0; index < result.length; index += 1) {
    const current = result[index];
    const next = result[index + 1];

    if (
      isInlineExamLabel(current) &&
      next &&
      next.trim() &&
      !isConsultSectionHeading(next) &&
      !isInlineExamLabel(next) &&
      !/^- /.test(next.trim())
    ) {
      merged.push(`${current.trim()} ${next.trim()}`);
      index += 1;
      continue;
    }

    merged.push(current);
  }

  return merged.join("\n");
}

function decorateConsultHtml(html) {
  const withSectionGaps = html.replace(/(<br><br>)/g, '<br><span class="consult-section-gap"></span>');
  if (withSectionGaps.includes("consult-heading")) {
    return withSectionGaps;
  }
  return withSectionGaps.replace(
    /(^|<br>)((?:Reason for Consult|HPI|Past Medical History|Medical History|Past Surgical History|Surgical History|Family History|Social History|Review of Systems|ROS|Objective|Assessment and Plan):?)(?=<br>|$)/g,
    '$1<span class="consult-heading">$2</span>'
  );
}

function parseConsultTaggedOutput(text) {
  const source = preprocessConsultTaggedText(String(text || ""));
  const regex = /\[\[(FACT|ASSUMPTION)\]\]([\s\S]*?)\[\[\/\1\]\]/g;
  const segments = [];
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(source)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        type: "text",
        value: sanitizeConsultTagArtifacts(source.slice(lastIndex, match.index))
      });
    }

    segments.push({
      type: match[1] === "FACT" ? "fact" : "assumption",
      value: sanitizeConsultTagArtifacts(match[2]),
      accepted: false,
    });

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < source.length) {
    segments.push({
      type: "text",
      value: sanitizeConsultTagArtifacts(source.slice(lastIndex))
    });
  }

  if (!segments.length) {
    segments.push({ type: "text", value: sanitizeConsultTagArtifacts(source) });
  }

  return explodeConsultSegments(segments);
}

function buildFallbackAssumptionPatterns() {
  const patterns = [];
  const assumptions = latestCaseFacts?.assumptions || {};
  const normalizedInput = String(latestCaseFacts?.normalized_input || "");
  const procedure = latestCaseFacts?.procedure || "";
  const pmh = latestCaseFacts?.clinical_context?.past_medical_history;
  const psh = latestCaseFacts?.clinical_context?.past_surgical_history;

  if (assumptions.family_history_default) {
    patterns.push(new RegExp(escapeRegExp(assumptions.family_history_default), "gi"));
  }
  if (assumptions.social_history_default) {
    patterns.push(new RegExp(escapeRegExp(assumptions.social_history_default), "gi"));
  }
  if (assumptions.modifying_factors_default) {
    patterns.push(new RegExp(escapeRegExp(assumptions.modifying_factors_default), "gi"));
  }

  if ((procedure === "laparoscopic_appendectomy" || /appendic/i.test(JSON.stringify(latestCaseFacts || {}))) && !/\bright lower quadrant\b/i.test(normalizedInput)) {
    patterns.push(/\bright lower quadrant\b/gi);
  }
  if (/cholecyst/i.test(JSON.stringify(latestCaseFacts || {})) && !/\bright upper quadrant\b/i.test(normalizedInput)) {
    patterns.push(/\bright upper quadrant\b/gi);
  }
  if (!pmh) {
    patterns.push(/\bNone reported\.\b/gi);
  }
  if (!psh) {
    patterns.push(/\bNo prior abdominal surgery reported\.\b/gi);
  }

  return patterns;
}

function expandShorthandForAssumptionChecks(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/\bgb\b/g, " gallbladder ")
    .replace(/\bruq\b/g, " right upper quadrant ")
    .replace(/\brlq\b/g, " right lower quadrant ")
    .replace(/\bllq\b/g, " left lower quadrant ")
    .replace(/\bluq\b/g, " left upper quadrant ")
    .replace(/\bsx\b/g, " symptomatic ")
    .replace(/\blap\b/g, " laparoscopic ")
    .replace(/\bappy\b/g, " appendicitis ")
    .replace(/\bcholedocho\b/g, " choledocholithiasis ")
    .replace(/\bappy\b/g, " appendicitis ")
    .replace(/\bno drain\b/g, " none placed no drains ")
    .replace(/\bno drains\b/g, " none placed no drains ")
    .replace(/\bno comp(?:s|lications)?\b/g, " none intraoperatively no complications ")
    .replace(/\bcomp(?:s|lications)?\b/g, " complications ")
    .replace(/\bebl\s*(\d+)\b/g, " estimated blood loss $1 ml $1 mL ")
    .replace(/\b4 ports?\b/g, " four-port four port 4 ports ")
    .replace(/\bcvs obtained\b/g, " critical view of safety obtained ")
    .replace(/\bgb off liver bed\b/g, " gallbladder dissected off the liver bed gallbladder removed from liver bed ")
    .replace(/\s+/g, " ")
    .trim();
}

function collectAssumptionValues(value, bucket) {
  if (!value) return;
  if (Array.isArray(value)) {
    value.forEach((item) => collectAssumptionValues(item, bucket));
    return;
  }
  if (typeof value === "object") {
    Object.values(value).forEach((item) => collectAssumptionValues(item, bucket));
    return;
  }
  const normalized = String(value).trim();
  if (!normalized || normalized.length < 3) return;
  bucket.add(normalized);
}

function buildGenericAssumptionPatterns() {
  const patterns = buildFallbackAssumptionPatterns();
  const seen = new Set();
  const normalizedInput = expandShorthandForAssumptionChecks(
    latestCaseFacts?.normalized_input || shorthandEl?.value || ""
  );
  const blockedValues = new Set([
    "preoperative",
    "postoperative",
    "operative",
    "operation",
    "procedure",
    "none",
    "none placed",
    "none noted",
    "gallbladder",
    "appendix",
    "patient",
    "abdomen",
  ]);
  collectAssumptionValues(latestCaseFacts?.assumptions || {}, seen);

  seen.forEach((value) => {
    const normalizedValue = String(value || "").trim().toLowerCase();
    if (!normalizedValue) return;
    if (blockedValues.has(normalizedValue)) return;
    if (normalizedValue.length < 4) return;
    if (/^approximately\s+\d+\s*(ml|mL)$/i.test(normalizedValue)) return;
    if (normalizedInput && normalizedInput.includes(normalizedValue)) return;
    patterns.push(new RegExp(escapeRegExp(value), "gi"));
  });

  return patterns.sort((a, b) => String(b.source || "").length - String(a.source || "").length);
}

function parseRichAssumptionSegments(text) {
  const source = String(text || "").replace(/\r\n/g, "\n");
  if (!source) return [];

  const patterns = buildGenericAssumptionPatterns();
  if (!patterns.length) {
    return [{ type: "text", value: source }];
  }

  const segments = [];
  let cursor = 0;

  while (cursor < source.length) {
    let nextMatch = null;

    for (const pattern of patterns) {
      pattern.lastIndex = cursor;
      const match = pattern.exec(source);
      if (!match) continue;
      if (
        !nextMatch ||
        match.index < nextMatch.index ||
        (match.index === nextMatch.index && match[0].length > nextMatch[0].length)
      ) {
        nextMatch = match;
      }
    }

    if (!nextMatch) {
      segments.push({ type: "text", value: source.slice(cursor) });
      break;
    }

    if (nextMatch.index > cursor) {
      segments.push({ type: "text", value: source.slice(cursor, nextMatch.index) });
    }

    segments.push({
      type: "assumption",
      value: nextMatch[0],
      accepted: false,
    });
    cursor = nextMatch.index + nextMatch[0].length;
  }

  return segments.filter((segment) => segment.value);
}

function explodeConsultSegments(segments) {
  const expanded = [];
  const fallbackPatterns = buildFallbackAssumptionPatterns();

  for (const segment of segments) {
    const parts = String(segment.value || "").split(/(\n)/);

    for (const part of parts) {
      if (!part) continue;

      if (part === "\n") {
        expanded.push({ type: "text", value: "\n" });
        continue;
      }

      const trimmed = part.trim();
      if (isConsultSectionHeading(trimmed)) {
        expanded.push({ type: "heading", value: normalizeConsultHeading(trimmed) });
        continue;
      }

      if (segment.type === "assumption" || !trimmed) {
        expanded.push({
          type: segment.type,
          value: part,
          accepted: segment.type === "assumption" ? Boolean(segment.accepted) : undefined,
        });
        continue;
      }

      let cursor = 0;
      let working = part;

      while (cursor < working.length) {
        let nextMatch = null;
        let nextPattern = null;

        for (const pattern of fallbackPatterns) {
          pattern.lastIndex = cursor;
          const match = pattern.exec(working);
          if (!match) continue;
          if (!nextMatch || match.index < nextMatch.index) {
            nextMatch = match;
            nextPattern = pattern;
          }
        }

        if (!nextMatch) {
          expanded.push({ type: segment.type, value: working.slice(cursor) });
          break;
        }

        if (nextMatch.index > cursor) {
          expanded.push({ type: segment.type, value: working.slice(cursor, nextMatch.index) });
        }

        expanded.push({ type: "assumption", value: nextMatch[0], accepted: false });
        cursor = nextMatch.index + nextMatch[0].length;
      }
    }
  }

  return expanded;
}

function getConsultPlainText() {
  return currentConsultSegments.map((segment) => segment.value).join("");
}

function syncStoredOutputText() {
  if (!outputEl) return;
  if (noteTypeEl && noteTypeEl.value === "consult_note") {
    outputEl.value = normalizeRichOutputText(consultOutputEl ? (consultOutputEl.innerText || consultOutputEl.textContent || "") : getConsultPlainText());
    return;
  }

  if (richOutputEl) {
    outputEl.value = normalizeRichOutputText(richOutputEl.innerText || richOutputEl.textContent || "");
  }
}

function normalizeRichOutputText(text) {
  return String(text || "").replace(/\r\n/g, "\n").replace(/\u00a0/g, " ");
}

function hideAssumptionPopover() {
  if (!assumptionPopoverEl) return;
  assumptionPopoverEl.classList.add("hidden");
  activeAssumptionIndex = null;
  activeAssumptionEl = null;
}

function scheduleHideAssumptionPopover() {
  if (assumptionHideTimeout) clearTimeout(assumptionHideTimeout);
  assumptionHideTimeout = setTimeout(() => {
    hideAssumptionPopover();
  }, 120);
}

function cancelHideAssumptionPopover() {
  if (assumptionHideTimeout) {
    clearTimeout(assumptionHideTimeout);
    assumptionHideTimeout = null;
  }
}

function findAssumptionSegment(index) {
  let assumptionIndex = -1;
  const sourceSegments = noteTypeEl && noteTypeEl.value === "consult_note"
    ? currentConsultSegments
    : currentRichSegments;

  for (const segment of sourceSegments) {
    if (segment.type !== "assumption") continue;
    assumptionIndex += 1;
    if (assumptionIndex === index) return segment;
  }

  return null;
}

function buildExactPhrasePatterns() {
  const blocks = Array.isArray(activeTemplateSummary?.exact_blocks)
    ? activeTemplateSummary.exact_blocks
    : [];

  return blocks
    .map((block) => String(block || "").trim())
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .map((block) => new RegExp(escapeRegExp(block), "gi"));
}

function splitSegmentByExactPhrases(text) {
  const source = String(text || "");
  const patterns = buildExactPhrasePatterns();

  if (!source || !patterns.length) {
    return [{ value: source, isExactPhrase: false }];
  }

  const pieces = [];
  let cursor = 0;

  while (cursor < source.length) {
    let nextMatch = null;

    for (const pattern of patterns) {
      pattern.lastIndex = cursor;
      const match = pattern.exec(source);
      if (!match) continue;

      if (
        !nextMatch ||
        match.index < nextMatch.index ||
        (match.index === nextMatch.index && match[0].length > nextMatch[0].length)
      ) {
        nextMatch = match;
      }
    }

    if (!nextMatch) {
      pieces.push({ value: source.slice(cursor), isExactPhrase: false });
      break;
    }

    if (nextMatch.index > cursor) {
      pieces.push({ value: source.slice(cursor, nextMatch.index), isExactPhrase: false });
    }

    pieces.push({ value: nextMatch[0], isExactPhrase: true });
    cursor = nextMatch.index + nextMatch[0].length;
  }

  return pieces.filter((piece) => piece.value);
}

function buildExactPhraseHtml(text) {
  return splitSegmentByExactPhrases(text).map((piece) => {
    const safeValue = escapeHtml(piece.value).replace(/\n/g, "<br>");
    if (!piece.isExactPhrase) return safeValue;
    return `<span class="consult-exact-phrase">${safeValue}</span>`;
  }).join("");
}

function showAssumptionPopover(targetEl) {
  if (!assumptionPopoverEl || !outputWrapEl) return;

  cancelHideAssumptionPopover();

  const assumptionIndex = Number(targetEl.dataset.assumptionIndex);
  const segment = findAssumptionSegment(assumptionIndex);
  if (!segment || segment.accepted) return;

  activeAssumptionIndex = assumptionIndex;
  activeAssumptionEl = targetEl;
  assumptionInputEl.value = segment.value;
  assumptionPopoverEl.classList.remove("hidden");

  const wrapRect = outputWrapEl.getBoundingClientRect();
  const targetRect = targetEl.getBoundingClientRect();

  const desiredTop = targetRect.bottom - wrapRect.top + 10;
  const desiredLeft = targetRect.left - wrapRect.left;
  const maxLeft = Math.max(12, wrapRect.width - assumptionPopoverEl.offsetWidth - 12);

  assumptionPopoverEl.style.top = `${desiredTop}px`;
  assumptionPopoverEl.style.left = `${Math.min(Math.max(12, desiredLeft), maxLeft)}px`;
}

function renderConsultSegments() {
  if (!consultOutputEl) return;

  let assumptionIndex = -1;
  const html = currentConsultSegments.map((segment) => {
    const pieces = splitSegmentByExactPhrases(segment.value);

    if (segment.type === "heading") {
      return pieces.map((piece) => {
        const safeValue = escapeHtml(piece.value).replace(/\n/g, "<br>");
        const className = piece.isExactPhrase
          ? "consult-heading consult-exact-phrase"
          : "consult-heading";
        return `<span class="${className}">${safeValue}</span>`;
      }).join("");
    }

    if (segment.type === "fact") {
      return pieces.map((piece) => {
        const safeValue = escapeHtml(piece.value).replace(/\n/g, "<br>");
        const className = piece.isExactPhrase
          ? "consult-fact consult-exact-phrase"
          : "consult-fact";
        return `<span class="${className}">${safeValue}</span>`;
      }).join("");
    }

    if (segment.type === "assumption") {
      assumptionIndex += 1;
      return pieces.map((piece) => {
        const safeValue = escapeHtml(piece.value).replace(/\n/g, "<br>");
        const className = [
          "consult-assumption",
          piece.isExactPhrase ? "consult-exact-phrase" : "",
          segment.accepted ? "is-accepted" : "",
        ].filter(Boolean).join(" ");
        return `<span class="${className}" data-assumption-index="${assumptionIndex}">${safeValue}</span>`;
      }).join("");
    }

    return pieces.map((piece) => {
      const safeValue = escapeHtml(piece.value).replace(/\n/g, "<br>");
      if (!piece.isExactPhrase) return safeValue;
      return `<span class="consult-exact-phrase">${safeValue}</span>`;
    }).join("");
  }).join("");

  consultOutputEl.classList.remove("is-generating");
  consultOutputEl.innerHTML = decorateConsultHtml(html);
  syncStoredOutputText();
  refreshTemplateRuntimeUI(getConsultPlainText());
}

function renderRichSegments(segments, { isGenerating = false } = {}) {
  if (!richOutputEl || !outputEl) return;

  let assumptionIndex = -1;
  const html = segments.map((segment) => {
    const pieces = splitSegmentByExactPhrases(segment.value);
    if (segment.type === "assumption") {
      assumptionIndex += 1;
      return pieces.map((piece) => {
        const safeValue = escapeHtml(piece.value).replace(/\n/g, "<br>");
        const className = [
          "consult-assumption",
          piece.isExactPhrase ? "consult-exact-phrase" : "",
          segment.accepted ? "is-accepted" : "",
        ].filter(Boolean).join(" ");
        return `<span class="${className}" data-assumption-index="${assumptionIndex}">${safeValue}</span>`;
      }).join("");
    }

    return pieces.map((piece) => {
      const safeValue = escapeHtml(piece.value).replace(/\n/g, "<br>");
      if (!piece.isExactPhrase) return safeValue;
      return `<span class="consult-exact-phrase">${safeValue}</span>`;
    }).join("");
  }).join("");

  richOutputEl.classList.toggle("is-generating", isGenerating);
  richOutputEl.innerHTML = html;
  syncStoredOutputText();
  refreshTemplateRuntimeUI(outputEl.value);
  richOutputEl.scrollTop = richOutputEl.scrollHeight;
}

function renderRichOutput(text, { isGenerating = false } = {}) {
  if (!richOutputEl || !outputEl) return;

  const normalizedText = String(text || "").replace(/\r\n/g, "\n");
  outputEl.value = normalizedText;
  if (isGenerating) {
    currentRichSegments = [];
    richOutputEl.classList.toggle("is-generating", true);
    richOutputEl.innerHTML = buildExactPhraseHtml(normalizedText);
    refreshTemplateRuntimeUI(normalizedText);
    richOutputEl.scrollTop = richOutputEl.scrollHeight;
    return;
  }

  currentRichSegments = parseRichAssumptionSegments(normalizedText);
  renderRichSegments(currentRichSegments);
}

function renderConsultStreamingPreview(markupText) {
  if (!consultOutputEl) return;
  consultOutputEl.classList.add("is-generating");
  consultOutputEl.innerHTML = decorateConsultHtml(
    escapeHtml(normalizeConsultDisplayText(stripConsultTags(markupText))).replace(/\n/g, "<br>")
  );
  if (outputEl) {
    outputEl.value = normalizeConsultDisplayText(stripConsultTags(markupText));
  }
  refreshTemplateRuntimeUI(outputEl ? outputEl.value : "");
}

function clearConsultOutput() {
  currentConsultSegments = [];
  if (consultOutputEl) {
    consultOutputEl.classList.remove("is-generating");
    consultOutputEl.innerHTML = "";
  }
  if (outputEl) {
    outputEl.value = "";
  }
  hideAssumptionPopover();
  refreshTemplateRuntimeUI("");
}

function clearRichOutput() {
  currentRichSegments = [];
  if (!richOutputEl) return;
  richOutputEl.classList.remove("is-generating");
  richOutputEl.innerHTML = "";
}

function setOutputMode(noteType) {
  const isConsult = noteType === "consult_note";

  if (consultOutputEl) {
    consultOutputEl.classList.toggle("hidden", !isConsult);
  }

  if (richOutputEl) {
    richOutputEl.classList.toggle("hidden", isConsult);
  }

  if (outputEl) {
    outputEl.classList.add("hidden");
  }

  if (!isConsult) {
    hideAssumptionPopover();
  }

  syncOutputToolbarTypography();
}

function getCurrentOutputText() {
  return outputEl ? outputEl.value.trim() : "";
}

function templatePlaceholder(noteType) {
  if (noteType === "op_note") {
    return "Example:\n\nPreoperative Diagnosis:\nPostoperative Diagnosis:\nProcedure:\nFindings:\nDescription of Procedure:\nEstimated Blood Loss:\nSpecimen:\nDrains:\nComplications:\nDisposition:";
  }
  if (noteType === "clinic_note") {
    return "Example:\n\nChief Complaint:\nHPI:\nRelevant Workup:\nAssessment:\nPlan:";
  }
  if (noteType === "consult_note") {
    return "Example:\n\nReason for Consult:\n{reason_for_consult}\n\nHPI:\n{hpi}\n\nPast Medical History:\n{pmh}\n\nPast Surgical History:\n{psh}\n\nFamily History:\n{fh}\n\nSocial History:\n{sh}\n\nReview of Systems:\n{ros}\n\nObjective:\n{objective}\n\nAssessment and Plan:\n{assessment}\n\n{plan}";
  }
  return "Paste your preferred template here.";
}

function shorthandPlaceholder(noteType) {
  if (noteType === "op_note") {
    return "29yoF. Gallstone pancreatitis s/p ERCP w/ stone retrieval. Lap chole 3 ports uncomplicated.";
  }
  if (noteType === "clinic_note") {
    return "52yoF seen for symptomatic cholelithiasis. Intermittent RUQ pain after meals x 4 months. Ultrasound with gallstones. Discussed laparoscopic cholecystectomy, risks/benefits reviewed, patient wishes to proceed.";
  }
  if (noteType === "consult_note") {
    return "67yoM admitted to medicine. Surgery consulted for abdominal pain and emesis. Diffuse severe sharp abdominal pain starting 24 hours ago associated with non-bloody non-bilious emesis, no specific exacerbating or alleviating factors. CT with SBO and transition point. Mild diffuse tenderness, no peritonitis. Recommend bowel rest, IVF, serial abdominal exams.";
  }
  return "Describe the encounter in shorthand or free text.";
}

function demoShorthand(noteType) {
  if (noteType === "op_note") {
    return "89 yo M hx CABG, Afib on Eliquis, exlap for free air on CT and shock, perforated gastric ulcer in antrum s/p mod Graham patch, intubated, on pressors back to ICU";
  }
  if (noteType === "clinic_note") {
    return "24yo M here 2 wks s/p lap appy. Doing fine. Can resume normal activities. f/u PRN.";
  }
  return "33yo F hx GERD obesity prior c-section here w/ choledocho s/p ERCP 3/17 tbili down to 2.4 from 6. vitals wnl. npo at mn. robo chole tmrw.";
}

function updateNoteTypeLabels() {
  if (!noteTypeEl) return;

  const label = noteTypeLabel(noteTypeEl.value);

  if (outputLabelEl) {
    outputLabelEl.textContent = `Generated ${label}`;
  }

  if (templateHeadingEl) {
    templateHeadingEl.textContent = `Template for ${label}`;
  }

  if (templateEditorEl) {
    templateEditorEl.placeholder = templatePlaceholder(noteTypeEl.value);
  }

  if (shorthandEl) {
    shorthandEl.placeholder = shorthandPlaceholder(noteTypeEl.value);
  }
}

function hasUnsavedTemplateChanges() {
  if (!templateEditorEl) return false;
  return templateEditorEl.value.trim() !== (currentLoadedTemplate || "").trim();
}

/* -------------------- Template modal controls -------------------- */

function openTemplateModal() {
  if (!templateModalEl) return;
  templateModalEl.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeTemplateModal() {
  if (!templateModalEl) return;
  templateModalEl.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

if (openTemplateSettingsBtn) {
  openTemplateSettingsBtn.addEventListener("click", async () => {
    await loadTemplate();
    openTemplateModal();
  });
}

if (closeTemplateModalBtn) {
  closeTemplateModalBtn.addEventListener("click", () => {
    if (hasUnsavedTemplateChanges()) {
      const confirmed = window.confirm("You have unsaved template changes. Close anyway?");
      if (!confirmed) return;
    }
    closeTemplateModal();
  });
}

if (templateModalEl) {
  templateModalEl.addEventListener("click", (e) => {
    if (e.target === templateModalEl) {
      if (hasUnsavedTemplateChanges()) {
        const confirmed = window.confirm("You have unsaved template changes. Close anyway?");
        if (!confirmed) return;
      }
      closeTemplateModal();
    }
  });
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && templateModalEl && !templateModalEl.classList.contains("hidden")) {
    if (hasUnsavedTemplateChanges()) {
      const confirmed = window.confirm("You have unsaved template changes. Close anyway?");
      if (!confirmed) return;
    }
    closeTemplateModal();
  }
});

/* -------------------- Templates -------------------- */

async function loadTemplate(noteTypeOverride = null) {
  if (!noteTypeEl || !templateEditorEl || !templateStatusEl) return;

  const noteType = noteTypeOverride || noteTypeEl.value;

  if (noteTypeEl.value !== noteType) {
    noteTypeEl.value = noteType;
  }

  updateNoteTypeLabels();
  templateStatusEl.textContent = "";

  try {
    const res = await fetch(`/api/templates/${noteType}`);
    const data = await res.json();

    if (!res.ok) {
      templateStatusEl.textContent = data.error || "Unable to load template.";
      return;
    }

    if (data.template && data.template.content) {
      templateEditorEl.value = data.template.content;
      currentLoadedTemplate = data.template.content;
      templateStatusEl.textContent = "Template loaded.";
    } else {
      templateEditorEl.value = "";
      currentLoadedTemplate = "";
      templateStatusEl.textContent = "No saved template for this note type.";
    }

    currentLoadedNoteType = noteType;
  } catch (err) {
    console.error(err);
    templateStatusEl.textContent = "Unable to load template.";
  }
}

if (saveTemplateBtn) {
  saveTemplateBtn.addEventListener("click", async () => {
    if (!noteTypeEl || !templateEditorEl || !templateStatusEl) return;

    templateStatusEl.textContent = "";

    try {
      const res = await fetch(`/api/templates/${noteTypeEl.value}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: templateEditorEl.value.trim()
        })
      });

      const data = await res.json();

      if (!res.ok) {
        templateStatusEl.textContent = data.error || "Unable to save template.";
        return;
      }

      currentLoadedTemplate = templateEditorEl.value.trim();
      currentLoadedNoteType = noteTypeEl.value;
      templateStatusEl.textContent = "Template saved.";
    } catch (err) {
      console.error(err);
      templateStatusEl.textContent = "Unable to save template.";
    }
  });
}

if (deleteTemplateBtn) {
  deleteTemplateBtn.addEventListener("click", async () => {
    if (!noteTypeEl || !templateEditorEl || !templateStatusEl) return;

    const confirmed = window.confirm(`Delete saved template for ${noteTypeLabel(noteTypeEl.value)}?`);
    if (!confirmed) return;

    templateStatusEl.textContent = "";

    try {
      const res = await fetch(`/api/templates/${noteTypeEl.value}`, {
        method: "DELETE"
      });

      const data = await res.json();

      if (!res.ok) {
        templateStatusEl.textContent = data.error || "Unable to delete template.";
        return;
      }

      templateEditorEl.value = "";
      currentLoadedTemplate = "";
      currentLoadedNoteType = noteTypeEl.value;
      templateStatusEl.textContent = "Template deleted.";
    } catch (err) {
      console.error(err);
      templateStatusEl.textContent = "Unable to delete template.";
    }
  });
}

if (noteTypeEl) {
  noteTypeEl.addEventListener("change", async () => {
    const nextType = noteTypeEl.value;
    syncNoteTypeDropdown();

    updateNoteTypeLabels();
    setOutputMode(nextType);

    if (templateModalEl && !templateModalEl.classList.contains("hidden") && hasUnsavedTemplateChanges()) {
      const confirmed = window.confirm(
        `You have unsaved template changes for ${noteTypeLabel(currentLoadedNoteType)}. Discard them and switch?`
      );

      if (!confirmed) {
        noteTypeEl.value = currentLoadedNoteType;
        syncNoteTypeDropdown();
        updateNoteTypeLabels();
        setOutputMode(currentLoadedNoteType);
        return;
      }
    }

    if (templateEditorEl) {
      await loadTemplate(nextType);
    }

    await loadActiveTemplateSummary(nextType);
  });
}

if (noteTypeTriggerEl) {
  noteTypeTriggerEl.addEventListener("click", () => {
    toggleNoteTypeMenu();
  });
}

noteTypeOptionEls.forEach((optionEl) => {
  optionEl.addEventListener("click", () => {
    if (!noteTypeEl) return;
    const nextValue = optionEl.dataset.value;
    if (!nextValue || nextValue === noteTypeEl.value) {
      closeNoteTypeMenu();
      return;
    }
    noteTypeEl.value = nextValue;
    noteTypeEl.dispatchEvent(new Event("change", { bubbles: true }));
    closeNoteTypeMenu();
  });
});

document.addEventListener("click", (event) => {
  if (!noteTypeTriggerEl || !noteTypeMenuEl) return;
  if (noteTypeTriggerEl.contains(event.target) || noteTypeMenuEl.contains(event.target)) return;
  closeNoteTypeMenu();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeNoteTypeMenu();
  }
});

/* -------------------- Generate note (streaming) -------------------- */

async function streamGenerateNote(shorthand, noteType) {
  const res = await fetch("/generate-note-stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      shorthand,
      note_type: noteType
    })
  });

  if (!res.ok) {
    let errorMessage = "Error generating note.";
    try {
      const data = await res.json();
      errorMessage = data.error || errorMessage;
    } catch (_) {}
    const error = new Error(errorMessage);
    error.status = res.status;
    throw error;
  }

  if (!res.body) {
    throw new Error("Streaming not supported in this browser.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamedText = "";
  let generationTimings = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const eventBlock of events) {
      const lines = eventBlock.split("\n");
      const dataLines = lines.filter(line => line.startsWith("data: "));
      if (!dataLines.length) continue;

      const payloadText = dataLines.map(line => line.slice(6)).join("");
      if (!payloadText) continue;

      let payload;
      try {
        payload = JSON.parse(payloadText);
      } catch (_) {
        continue;
      }

      if (payload.type === "meta") {
        latestProcedure = payload.case_facts?.procedure || "";
        latestCaseFacts = payload.case_facts || null;
        latestTeachingSignals = payload.teaching_signals || latestTeachingSignals;
        generationTimings = payload.timings || generationTimings;
      }

      if (payload.type === "delta") {
        streamedText += payload.delta;
        if (noteType === "consult_note") {
          renderConsultStreamingPreview(streamedText);
        } else {
          renderRichOutput(streamedText, { isGenerating: true });
        }
      }

      if (payload.type === "error") {
        throw new Error(payload.error || "Streaming failed.");
      }

      if (payload.type === "done") {
        generationTimings = payload.timings || generationTimings;
      }
    }
  }

  if (noteType === "consult_note") {
    currentConsultSegments = parseConsultTaggedOutput(streamedText);
    renderConsultSegments();
  } else {
    renderRichOutput(streamedText);
  }

  if (generationTimings) {
    console.info("SurgiNote generation timings", generationTimings);
  }

  return streamedText;
}

async function generateNoteFallback(shorthand, noteType) {
  const res = await fetch("/generate-note", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      shorthand,
      note_type: noteType
    })
  });

  let data = null;
  try {
    data = await res.json();
  } catch (_) {}

  if (!res.ok) {
    const error = new Error((data && data.error) || "Error generating note.");
    error.status = res.status;
    throw error;
  }

  const noteText = String((data && data.note) || "");
  if (!noteText.trim()) {
    throw new Error("Generation returned an empty note.");
  }
  latestProcedure = (data && data.case_facts && data.case_facts.procedure) || latestProcedure;
  latestCaseFacts = (data && data.case_facts) || latestCaseFacts;
  latestTeachingSignals = (data && data.teaching_signals) || latestTeachingSignals;

  if (noteType === "consult_note") {
    currentConsultSegments = parseConsultTaggedOutput(noteText);
    renderConsultSegments();
  } else {
    renderRichOutput(noteText);
  }

  return noteText;
}

async function runNoteGeneration(shorthand) {
  const trimmed = (shorthand || "").trim();
  latestTeachingSignals = null;
  lastRatedOutputText = "";

  if (!trimmed) {
    alert("Please enter shorthand first.");
    return;
  }

  const noteType = noteTypeEl ? noteTypeEl.value : "op_note";

  generateBtn.disabled = true;
  if (demoBtn) demoBtn.disabled = true;
  if (copyBtn) copyBtn.disabled = true;
  if (copyBtnBottom) copyBtnBottom.disabled = true;
  generateBtn.textContent = "Generating...";
  if (demoBtn) demoBtn.textContent = "Loading demo...";
  setOutputMode(noteType);

  outputEl.value = "";
  clearConsultOutput();
  clearRichOutput();
  refreshTemplateRuntimeUI("");
  if (outputWrapEl) outputWrapEl.classList.add("output-loading");
  startGeneratingStatus();

  try {
    let lastError = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const streamedText = await streamGenerateNote(trimmed, noteType);
        if (!String(streamedText || "").trim()) {
          await generateNoteFallback(trimmed, noteType);
        }
        lastError = null;
        break;
      } catch (err) {
        lastError = err;
        const shouldRetry = attempt === 0 && (!err.status || err.status >= 500);
        if (!shouldRetry) {
          throw err;
        }

        outputEl.value = "";
        clearConsultOutput();
        clearRichOutput();
        currentConsultSegments = [];
        refreshTemplateRuntimeUI("");
        showRetryGeneratingStatus();
        await new Promise((resolve) => window.setTimeout(resolve, 900));
      }
    }
    if (lastError) {
      throw lastError;
    }
    rememberRecentNote({
      noteType,
      shorthand: trimmed,
      outputText: getCurrentOutputText(),
      procedure: latestProcedure,
    });
    stopGeneratingStatus();
  } catch (err) {
    console.error(err);
    if (!getCurrentOutputText()) {
      if (noteType === "consult_note" && consultOutputEl) {
        consultOutputEl.classList.remove("is-generating");
        consultOutputEl.textContent = err.message || "Error generating note.";
        outputEl.value = err.message || "Error generating note.";
        currentConsultSegments = [{ type: "text", value: outputEl.value }];
        refreshTemplateRuntimeUI(outputEl.value);
      } else {
        renderRichOutput(err.message || "Error generating note.");
      }
    }
    stopGeneratingStatus();
  } finally {
    generateBtn.disabled = false;
    if (demoBtn) demoBtn.disabled = false;
    if (copyBtn) copyBtn.disabled = false;
    if (copyBtnBottom) copyBtnBottom.disabled = false;
    generateBtn.textContent = "Generate note";
    if (demoBtn) demoBtn.textContent = "Demo";
    if (outputWrapEl) outputWrapEl.classList.remove("output-loading");
  }
}

if (generateBtn) {
  generateBtn.addEventListener("click", async () => {
    clearDemoTypingAnimation();
    await runNoteGeneration(shorthandEl.value);
  });
}

if (demoBtn) {
  demoBtn.addEventListener("click", async () => {
    const noteType = noteTypeEl ? noteTypeEl.value : "consult_note";
    const sample = demoShorthand(noteType);
    const didFinishTyping = await animateDemoShorthand(sample);
    if (!didFinishTyping) return;
    if (generateBtn) {
      generateBtn.click();
      return;
    }
    await runNoteGeneration(sample);
  });
}

function handleConsultMouseOver(event) {
  const assumptionEl = event.target.closest(".consult-assumption");
  const activeEditor = getActiveOutputEditor();
  if (!assumptionEl || !activeEditor || !activeEditor.contains(assumptionEl)) return;
  showAssumptionPopover(assumptionEl);
}

function handleConsultMouseOut(event) {
  const assumptionEl = event.target.closest(".consult-assumption");
  if (!assumptionEl) return;

  const relatedTarget = event.relatedTarget;
  if (relatedTarget && assumptionPopoverEl && assumptionPopoverEl.contains(relatedTarget)) {
    return;
  }

  scheduleHideAssumptionPopover();
}

function handleAssumptionInputChange() {
  if (activeAssumptionIndex === null) return;

  const segment = findAssumptionSegment(activeAssumptionIndex);
  if (!segment) return;

  segment.value = assumptionInputEl.value;
  segment.accepted = false;
  syncStoredOutputText();

  if (activeAssumptionEl) {
    activeAssumptionEl.innerHTML = buildExactPhraseHtml(segment.value);
    activeAssumptionEl.classList.remove("is-accepted");
  }
}

function handleAssumptionAccept() {
  if (activeAssumptionIndex === null) return;
  const segment = findAssumptionSegment(activeAssumptionIndex);
  if (!segment) return;
  segment.accepted = true;
  if (activeAssumptionEl) {
    activeAssumptionEl.classList.add("is-accepted");
  }
  hideAssumptionPopover();
}

function handleRatingOptionGridClick(event) {
  if (!ratingOptionGridEl) return;
  const button = event.target.closest(".rating-option");
  if (!button) return;
  const rating = button.dataset.rating;
  if (!rating) return;
  ratingOptionGridEl.querySelectorAll(".rating-option").forEach((item) => {
    item.classList.remove("is-selected");
  });
  setRatingOptionState(true);
  button.classList.add("is-selected");
  resolveRatingModal(rating);
}

function dismissRatingModal() {
  resolveRatingModal(null);
  closeRatingModal();
}

function applyInitialNoteTypeSelection() {
  if (noteTypeEl && appState.initialNoteType && ["consult_note", "clinic_note", "op_note"].includes(appState.initialNoteType)) {
    noteTypeEl.value = appState.initialNoteType;
  }
}

function initializeAppSurface() {
  applyInitialNoteTypeSelection();
  updateNoteTypeLabels();
  syncNoteTypeDropdown();
  setOutputMode(noteTypeEl ? noteTypeEl.value : "op_note");
  refreshTemplateRuntimeUI("");
  renderRecentNotesDock();
  if (recentNotesListEl) {
    recentNotesListEl.addEventListener("click", handleRecentNotesClick);
  }

  if (outputFormattingToolbarEl) {
    outputFormattingToolbarEl.innerHTML = buildRichToolbarMarkup();
    initializeToolbarSelectMenus(outputFormattingToolbarEl, (setting, value) => {
      const editor = getActiveOutputEditor();
      if (!editor) return;
      if (setting === "font-family") {
        applyEditorTypography(editor, {
          fontFamily: value || "system-ui",
          fontSize: editor.dataset.fontSize || "16px",
        });
      } else if (setting === "font-size") {
        applyEditorTypography(editor, {
          fontFamily: editor.dataset.fontFamily || "system-ui",
          fontSize: value || "16px",
        });
      }
      syncOutputToolbarTypography();
    });

    outputFormattingToolbarEl.addEventListener("mousedown", (event) => {
      const target = event.target.closest("button");
      if (target) {
        event.preventDefault();
      }
    });

    outputFormattingToolbarEl.addEventListener("click", (event) => {
      const actionButton = getToolbarActionTarget(event, outputFormattingToolbarEl);
      if (!actionButton) return;
      const editor = getActiveOutputEditor();
      if (!editor) return;
      editor.focus();
      execRichTextCommand(actionButton.dataset.editorCommand);
      syncStoredOutputText();
      refreshTemplateRuntimeUI(outputEl ? outputEl.value : "");
    });
  }

  if (richOutputEl) {
    richOutputEl.addEventListener("input", () => {
      syncStoredOutputText();
      refreshTemplateRuntimeUI(outputEl ? outputEl.value : "");
    });

    richOutputEl.addEventListener("blur", () => {
      if (noteTypeEl && noteTypeEl.value !== "consult_note") {
        renderRichOutput(outputEl ? outputEl.value : "");
      }
    });
  }

  if (consultOutputEl) {
    consultOutputEl.addEventListener("input", () => {
      syncStoredOutputText();
      refreshTemplateRuntimeUI(outputEl ? outputEl.value : "");
    });
  }

  if (shorthandEl) {
    shorthandEl.addEventListener("input", () => {
      refreshTemplateRuntimeUI(outputEl ? outputEl.value : "");
    });
  }

  applyOutputTypographyFromSummary();

  if (appState.showOnboarding) {
    showOnboardingModal();
  }
}

async function handleDomContentLoaded() {
  applyInitialNoteTypeSelection();
  updateNoteTypeLabels();
  syncNoteTypeDropdown();
  refreshTemplateRuntimeUI("");

  await loadActiveTemplateSummary(noteTypeEl ? noteTypeEl.value : "consult_note");

  if (templateEditorEl) {
    await loadTemplate();
  }
}

if (onboardingStartBtn) {
  onboardingStartBtn.addEventListener("click", async () => {
    await completeOnboarding();
    appState.showOnboarding = false;
    hideOnboardingModal();
  });
}

if (onboardingTemplatesBtn) {
  onboardingTemplatesBtn.addEventListener("click", async () => {
    const noteType = noteTypeEl ? noteTypeEl.value : appState.initialNoteType || "consult_note";
    await completeOnboarding();
    appState.showOnboarding = false;
    window.location.assign(`/templates?note_type=${encodeURIComponent(noteType)}`);
  });
}

function handleRatingEscape(event) {
  if (event.key === "Escape" && onboardingModalEl && !onboardingModalEl.classList.contains("hidden")) {
    return;
  }
  if (event.key === "Escape" && ratingModalEl && !ratingModalEl.classList.contains("hidden")) {
    dismissRatingModal();
  }
}

export {
  appState,
  copyBtn,
  copyBtnBottom,
  consultOutputEl,
  richOutputEl,
  assumptionPopoverEl,
  assumptionInputEl,
  assumptionAcceptBtn,
  ratingOptionGridEl,
  ratingModalBackdropEl,
  ratingModalSkipEl,
  noteTypeEl,
  ratingModalEl,
  performCopyAction,
  getCurrentOutputText,
  cancelHideAssumptionPopover,
  scheduleHideAssumptionPopover,
  handleConsultMouseOver,
  handleConsultMouseOut,
  handleAssumptionInputChange,
  handleAssumptionAccept,
  handleRatingOptionGridClick,
  dismissRatingModal,
  initializeAppSurface,
  handleDomContentLoaded,
  handleRatingEscape,
};
