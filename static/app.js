const appState = window.__APP_STATE__ || {};
const shorthandEl = document.getElementById("shorthand");
const outputEl = document.getElementById("output");
const outputWrapEl = document.getElementById("outputWrap");
const consultOutputEl = document.getElementById("consultOutput");

const generateBtn = document.getElementById("generateBtn");
const demoBtn = document.getElementById("demoBtn");
const copyBtn = document.getElementById("copyBtn");
const emailBtn = document.getElementById("emailBtn");

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
const ratingModalEl = document.getElementById("ratingModal");
const ratingModalBackdropEl = document.getElementById("ratingModalBackdrop");
const ratingOptionGridEl = document.getElementById("ratingOptionGrid");
const ratingModalSkipEl = document.getElementById("ratingModalSkip");
const ratingModalStatusEl = document.getElementById("ratingModalStatus");

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
  assumptionHelpEl.textContent = "Edit this assumption to change the generated consult note.";
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

async function performCopyAction() {
  const text = getCurrentOutputText();
  if (!text || !copyBtn) return;

  const original = copyBtn.textContent;
  copyBtn.disabled = true;
  const ok = await copyTextWithFallback(text);
  copyBtn.textContent = ok ? "Copied!" : "Copy failed";
  if (ok) {
    await promptForCopyRating(text);
  }
  setTimeout(() => {
    copyBtn.textContent = original;
    copyBtn.disabled = false;
  }, 1500);
}

function performEmailAction() {
  const text = getCurrentOutputText();
  if (!text) return;

  const currentNoteType = noteTypeEl ? noteTypeLabel(noteTypeEl.value) : "Note";
  const subject = encodeURIComponent(
    latestProcedure
      ? `${currentNoteType} Draft - ${humanizeKey(latestProcedure)}`
      : `${currentNoteType} Draft`
  );
  const body = encodeURIComponent(text);
  window.location.href = `mailto:?subject=${subject}&body=${body}`;
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

async function promptForCopyRating(text) {
  if (!text || text === lastRatedOutputText) return;
  const rating = await openRatingModal(text);
  if (!rating) return;

  try {
    setRatingModalStatus("Saving score...");
    await submitCopyFeedback({ text, rating });
    lastRatedOutputText = text;
    closeRatingModal();
  } catch (error) {
    console.error(error);
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
    pills.push({ label: mode === "applied" ? "STRICT used" : "STRICT", tone: "neutral" });
  }
  if (summary.style_enabled) {
    pills.push({ label: mode === "applied" ? "STYLE used" : "STYLE", tone: "neutral" });
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

function refreshTemplateRuntimeUI(outputText = "") {
  renderTemplateRuntimeRow(
    inputTemplateRuntimeEl,
    inputTemplateRuntimeLabelEl,
    inputTemplateRuntimePillsEl,
    activeTemplateSummary,
    "detected",
    ""
  );

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
    refreshTemplateRuntimeUI(getCurrentOutputText());
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
  return html.replace(
    /(^|<br>)((?:Reason for Consult|HPI|Past Medical History|Medical History|Past Surgical History|Surgical History|Family History|Social History|Review of Systems|ROS|Objective|Assessment and Plan):?)(?=<br>|$)/g,
    '$1<span class="consult-heading">$2</span>'
  ).replace(/(<br><br>)/g, '<br><span class="consult-section-gap"></span>');
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
  outputEl.value = getConsultPlainText();
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

  for (const segment of currentConsultSegments) {
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

function showAssumptionPopover(targetEl) {
  if (!assumptionPopoverEl || !outputWrapEl || !consultOutputEl) return;

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

function setOutputMode(noteType) {
  const isConsult = noteType === "consult_note";

  if (consultOutputEl) {
    consultOutputEl.classList.toggle("hidden", !isConsult);
  }

  if (outputEl) {
    outputEl.classList.toggle("hidden", isConsult);
  }

  if (!isConsult) {
    hideAssumptionPopover();
  }
}

function getCurrentOutputText() {
  if (noteTypeEl && noteTypeEl.value === "consult_note") {
    return getConsultPlainText().trim();
  }

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
    return "42yoF sx cholelithiasis, postprandial RUQ pain. Lap chole 4 ports, CVS obtained, GB off liver bed, EBL 10, no drain, no comps.";
  }
  if (noteType === "clinic_note") {
    return "56yoF biliary colic x 6 mos, worse fatty meals. US +stones no cholecystitis. Wants lap chole, r/b/a reviewed, proceed scheduling.";
  }
  return "34yoM no PMH here w/ 18h LQ pain, nausea, anorexia. CT uncomplicated appy. WBC 14. Mild LQ ttp no diffuse peritonitis. Admit, NPO, ceftriaxone/Flagyl, lap appy in AM.";
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
          outputEl.value = streamedText;
          refreshTemplateRuntimeUI(streamedText);
          outputEl.scrollTop = outputEl.scrollHeight;
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
  }

  if (generationTimings) {
    console.info("SurgiNote generation timings", generationTimings);
  }

  return streamedText;
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
  if (emailBtn) emailBtn.disabled = true;
  generateBtn.textContent = "Generating...";
  if (demoBtn) demoBtn.textContent = "Loading demo...";
  setOutputMode(noteType);

  outputEl.value = "";
  clearConsultOutput();
  refreshTemplateRuntimeUI("");
  if (outputWrapEl) outputWrapEl.classList.add("output-loading");
  startGeneratingStatus();

  try {
    let lastError = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        await streamGenerateNote(trimmed, noteType);
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
        currentConsultSegments = [];
        refreshTemplateRuntimeUI("");
        showRetryGeneratingStatus();
        await new Promise((resolve) => window.setTimeout(resolve, 900));
      }
    }
    if (lastError) {
      throw lastError;
    }
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
        outputEl.value = err.message || "Error generating note.";
        refreshTemplateRuntimeUI(outputEl.value);
      }
    }
    stopGeneratingStatus();
  } finally {
    generateBtn.disabled = false;
    if (demoBtn) demoBtn.disabled = false;
    if (copyBtn) copyBtn.disabled = false;
    if (emailBtn) emailBtn.disabled = false;
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

/* -------------------- Copy -------------------- */

if (copyBtn) {
  copyBtn.addEventListener("click", async () => {
    const text = getCurrentOutputText();

    if (!text) {
      alert("Nothing to copy yet.");
      return;
    }
    await performCopyAction();
  });
}

/* -------------------- Email -------------------- */

if (emailBtn) {
  emailBtn.addEventListener("click", () => {
    const text = getCurrentOutputText();

    if (!text) {
      alert("Generate a note first.");
      return;
    }
    performEmailAction();
  });
}

if (consultOutputEl && assumptionPopoverEl) {
  consultOutputEl.addEventListener("mouseover", (event) => {
    const assumptionEl = event.target.closest(".consult-assumption");
    if (!assumptionEl || !consultOutputEl.contains(assumptionEl)) return;
    showAssumptionPopover(assumptionEl);
  });

  consultOutputEl.addEventListener("mouseout", (event) => {
    const assumptionEl = event.target.closest(".consult-assumption");
    if (!assumptionEl) return;

    const relatedTarget = event.relatedTarget;
    if (relatedTarget && assumptionPopoverEl.contains(relatedTarget)) {
      return;
    }

    scheduleHideAssumptionPopover();
  });

  assumptionPopoverEl.addEventListener("mouseenter", cancelHideAssumptionPopover);
  assumptionPopoverEl.addEventListener("mouseleave", scheduleHideAssumptionPopover);

  assumptionInputEl.addEventListener("input", () => {
    if (activeAssumptionIndex === null) return;

    const segment = findAssumptionSegment(activeAssumptionIndex);
    if (!segment) return;

    segment.value = assumptionInputEl.value;
    segment.accepted = false;
    syncStoredOutputText();

    if (activeAssumptionEl) {
      activeAssumptionEl.innerHTML = escapeHtml(segment.value).replace(/\n/g, "<br>");
      activeAssumptionEl.classList.remove("is-accepted");
    }
  });

  assumptionAcceptBtn.addEventListener("click", () => {
    if (activeAssumptionIndex === null) return;
    const segment = findAssumptionSegment(activeAssumptionIndex);
    if (!segment) return;
    segment.accepted = true;
    if (activeAssumptionEl) {
      activeAssumptionEl.classList.add("is-accepted");
    }
    hideAssumptionPopover();
  });
}

if (ratingOptionGridEl) {
  ratingOptionGridEl.addEventListener("click", async (event) => {
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
  });
}

if (ratingModalBackdropEl) {
  ratingModalBackdropEl.addEventListener("click", () => {
    resolveRatingModal(null);
    closeRatingModal();
  });
}

if (ratingModalSkipEl) {
  ratingModalSkipEl.addEventListener("click", () => {
    resolveRatingModal(null);
    closeRatingModal();
  });
}

if (noteTypeEl && appState.initialNoteType && ["consult_note", "clinic_note", "op_note"].includes(appState.initialNoteType)) {
  noteTypeEl.value = appState.initialNoteType;
}

updateNoteTypeLabels();
syncNoteTypeDropdown();
setOutputMode(noteTypeEl ? noteTypeEl.value : "op_note");
refreshTemplateRuntimeUI("");

/* -------------------- Init -------------------- */

window.addEventListener("DOMContentLoaded", async () => {
  if (noteTypeEl && appState.initialNoteType && ["consult_note", "clinic_note", "op_note"].includes(appState.initialNoteType)) {
    noteTypeEl.value = appState.initialNoteType;
  }
  updateNoteTypeLabels();
  syncNoteTypeDropdown();
  refreshTemplateRuntimeUI("");

  await loadActiveTemplateSummary(noteTypeEl ? noteTypeEl.value : "consult_note");

  if (templateEditorEl) {
    await loadTemplate();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && ratingModalEl && !ratingModalEl.classList.contains("hidden")) {
    resolveRatingModal(null);
    closeRatingModal();
  }
});
