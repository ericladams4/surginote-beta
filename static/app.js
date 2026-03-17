const shorthandEl = document.getElementById("shorthand");
const outputEl = document.getElementById("output");
const outputWrapEl = document.getElementById("outputWrap");
const consultOutputEl = document.getElementById("consultOutput");

const generateBtn = document.getElementById("generateBtn");
const demoBtn = document.getElementById("demoBtn");
const copyBtn = document.getElementById("copyBtn");
const emailBtn = document.getElementById("emailBtn");

const ratingEl = document.getElementById("rating");
const commentEl = document.getElementById("comment");
const feedbackBtn = document.getElementById("feedbackBtn");
const feedbackStatus = document.getElementById("feedbackStatus");

const generatingStatusEl = document.getElementById("generatingStatus");
const generatingStatusTextEl = document.getElementById("generatingStatusText");
const generatingStatusSubtextEl = document.getElementById("generatingStatusSubtext");

const noteTypeEl = document.getElementById("noteType");
const noteTypeTriggerEl = document.getElementById("noteTypeTrigger");
const noteTypeTriggerLabelEl = document.getElementById("noteTypeLabelText");
const noteTypeMenuEl = document.getElementById("noteTypeMenu");
const noteTypeOptionEls = Array.from(document.querySelectorAll(".note-type-option"));
const outputLabelEl = document.getElementById("outputLabel");

/* -------------------- Template settings / modal -------------------- */

const openTemplateSettingsBtn = document.getElementById("openTemplateSettingsBtn");
const templateModalEl = document.getElementById("templateModal");
const closeTemplateModalBtn = document.getElementById("closeTemplateModalBtn");

const templateHeadingEl = document.getElementById("templateHeading");
const templateEditorEl = document.getElementById("templateEditor");
const saveTemplateBtn = document.getElementById("saveTemplateBtn");
const deleteTemplateBtn = document.getElementById("deleteTemplateBtn");
const templateStatusEl = document.getElementById("templateStatus");

const openFeedbackBtn = document.getElementById("openFeedbackBtn");
const feedbackModal = document.getElementById("feedbackModal");
const closeFeedbackModalBtn = document.getElementById("closeFeedbackModalBtn");

function openFeedbackModal() {
feedbackModal.classList.remove("hidden");
document.body.classList.add("modal-open");
}

function closeFeedbackModal() {
feedbackModal.classList.add("hidden");
document.body.classList.remove("modal-open");
}

if (openFeedbackBtn) {
openFeedbackBtn.addEventListener("click", openFeedbackModal);
}

if (closeFeedbackModalBtn) {
closeFeedbackModalBtn.addEventListener("click", closeFeedbackModal);
}

let latestProcedure = "";
let latestCaseFacts = null;
let currentLoadedTemplate = "";
let currentLoadedNoteType = noteTypeEl ? noteTypeEl.value : "consult_note";
let currentConsultSegments = [];
let activeAssumptionIndex = null;
let activeAssumptionEl = null;
let assumptionHideTimeout = null;
let loadingMessageInterval = null;

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
const assumptionHelpEl = document.createElement("div");

if (assumptionPopoverEl) {
  assumptionPopoverEl.className = "consult-assumption-popover hidden";
  assumptionLabelEl.className = "consult-assumption-label";
  assumptionLabelEl.textContent = "Assumption";
  assumptionInputEl.className = "consult-assumption-input";
  assumptionInputEl.type = "text";
  assumptionHelpEl.className = "consult-assumption-help";
  assumptionHelpEl.textContent = "Edit this assumption to change the generated consult note.";
  assumptionPopoverEl.appendChild(assumptionLabelEl);
  assumptionPopoverEl.appendChild(assumptionInputEl);
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

function noteTypeLabel(noteType) {
  if (noteType === "op_note") return "Op Note";
  if (noteType === "clinic_note") return "Clinic Note";
  if (noteType === "consult_note") return "Consult Note";
  return "Note";
}

function isConsultSectionHeading(line) {
  return /^(Reason for Consult|HPI|Past Medical History|Medical History|Past Surgical History|Surgical History|Family History|Social History|Review of Systems|ROS|Objective|Assessment and Plan):?$/i.test(
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

function syncNoteTypeDropdown() {
  if (!noteTypeEl) return;

  const activeValue = noteTypeEl.value;

  if (noteTypeTriggerLabelEl) {
    noteTypeTriggerLabelEl.textContent = noteTypeLabel(activeValue);
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

function stripConsultTags(text) {
  return String(text || "").replace(/\[\[(?:\/)?(?:FACT|ASSUMPTION)\]\]/g, "");
}

function normalizeConsultDisplayText(text) {
  const normalized = String(text || "")
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

  return result.join("\n");
}

function decorateConsultHtml(html) {
  return html.replace(
    /(^|<br>)((?:Reason for Consult|HPI|Past Medical History|Medical History|Past Surgical History|Surgical History|Family History|Social History|Review of Systems|ROS|Objective|Assessment and Plan):?)(?=<br>|$)/g,
    '$1<span class="consult-heading">$2</span>'
  ).replace(/(<br><br>)/g, '<br><span class="consult-section-gap"></span>');
}

function parseConsultTaggedOutput(text) {
  const source = normalizeConsultDisplayText(String(text || ""));
  const regex = /\[\[(FACT|ASSUMPTION)\]\]([\s\S]*?)\[\[\/\1\]\]/g;
  const segments = [];
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(source)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        type: "text",
        value: source.slice(lastIndex, match.index)
      });
    }

    segments.push({
      type: match[1] === "FACT" ? "fact" : "assumption",
      value: match[2]
    });

    lastIndex = regex.lastIndex;
  }

  if (lastIndex < source.length) {
    segments.push({
      type: "text",
      value: source.slice(lastIndex)
    });
  }

  if (!segments.length) {
    segments.push({ type: "text", value: source });
  }

  return segments;
}

function applyFallbackAssumptionMarkup(html) {
  if (!html || /\bconsult-assumption\b/.test(html)) {
    return html;
  }

  const patterns = [
    /\bright lower quadrant\b/gi,
    /\bright upper quadrant\b/gi,
    /\bnone reported\.\b/gi,
    /\bnon-contributory\.\b/gi,
    /\bdenies alcohol use, tobacco use, drug use\.\b/gi,
    /\bno prior abdominal surgery reported\.\b/gi,
    /\bconstitutional negative except as noted in hpi; cardiovascular, respiratory, genitourinary, neurologic negative; positive for abdominal pain and nausea\.\b/gi,
  ];

  let enhanced = html;
  for (const pattern of patterns) {
    enhanced = enhanced.replace(pattern, (match) => `<span class="consult-assumption">${match}</span>`);
  }
  return enhanced;
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

function showAssumptionPopover(targetEl) {
  if (!assumptionPopoverEl || !outputWrapEl || !consultOutputEl) return;

  cancelHideAssumptionPopover();

  const assumptionIndex = Number(targetEl.dataset.assumptionIndex);
  const segment = findAssumptionSegment(assumptionIndex);
  if (!segment) return;

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
    const safeValue = escapeHtml(segment.value).replace(/\n/g, "<br>");

    if (segment.type === "fact") {
      return `<span class="consult-fact">${safeValue}</span>`;
    }

    if (segment.type === "assumption") {
      assumptionIndex += 1;
      return `<span class="consult-assumption" data-assumption-index="${assumptionIndex}">${safeValue}</span>`;
    }

    return safeValue;
  }).join("");

  consultOutputEl.classList.remove("is-generating");
  consultOutputEl.innerHTML = applyFallbackAssumptionMarkup(decorateConsultHtml(html));
  syncStoredOutputText();
}

function renderConsultStreamingPreview(markupText) {
  if (!consultOutputEl) return;
  consultOutputEl.classList.add("is-generating");
  consultOutputEl.innerHTML = applyFallbackAssumptionMarkup(decorateConsultHtml(
    escapeHtml(normalizeConsultDisplayText(stripConsultTags(markupText))).replace(/\n/g, "<br>")
  ));
  if (outputEl) {
    outputEl.value = normalizeConsultDisplayText(stripConsultTags(markupText));
  }
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
    throw new Error(errorMessage);
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
        generationTimings = payload.timings || generationTimings;
      }

      if (payload.type === "delta") {
        streamedText += payload.delta;
        if (noteType === "consult_note") {
          renderConsultStreamingPreview(streamedText);
        } else {
          outputEl.value = streamedText;
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
  if (outputWrapEl) outputWrapEl.classList.add("output-loading");
  startGeneratingStatus();

  try {
    await streamGenerateNote(trimmed, noteType);
    stopGeneratingStatus();
  } catch (err) {
    console.error(err);
    if (!getCurrentOutputText()) {
      if (noteType === "consult_note" && consultOutputEl) {
        consultOutputEl.classList.remove("is-generating");
        consultOutputEl.textContent = err.message || "Error generating note.";
        outputEl.value = err.message || "Error generating note.";
        currentConsultSegments = [{ type: "text", value: outputEl.value }];
      } else {
        outputEl.value = err.message || "Error generating note.";
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
    await runNoteGeneration(shorthandEl.value);
  });
}

if (demoBtn) {
  demoBtn.addEventListener("click", async () => {
    const noteType = noteTypeEl ? noteTypeEl.value : "consult_note";
    const sample = demoShorthand(noteType);

    if (shorthandEl) {
      shorthandEl.value = sample;
      shorthandEl.focus();
      shorthandEl.setSelectionRange(sample.length, sample.length);
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

    const original = copyBtn.textContent;
    copyBtn.disabled = true;

    const ok = await copyTextWithFallback(text);

    copyBtn.textContent = ok ? "Copied!" : "Copy failed";

    setTimeout(() => {
      copyBtn.textContent = original;
      copyBtn.disabled = false;
    }, 1500);
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

    const currentNoteType = noteTypeEl ? noteTypeLabel(noteTypeEl.value) : "Note";

    const subject = encodeURIComponent(
      latestProcedure
        ? `${currentNoteType} Draft - ${humanizeKey(latestProcedure)}`
        : `${currentNoteType} Draft`
    );

    const body = encodeURIComponent(text);
    window.location.href = `mailto:?subject=${subject}&body=${body}`;
  });
}

/* -------------------- Feedback -------------------- */

if (feedbackBtn) {
  feedbackBtn.addEventListener("click", async () => {
    const payload = {
      shorthand: shorthandEl.value.trim(),
      procedure: latestProcedure,
      rating: ratingEl.value,
      comment: commentEl.value.trim(),
      generated_note: getCurrentOutputText()
    };

    feedbackBtn.disabled = true;
    feedbackBtn.textContent = "Submitting...";
    if (feedbackStatus) feedbackStatus.textContent = "";

    try {
      const res = await fetch("/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      if (data.error) {
        if (feedbackStatus) feedbackStatus.textContent = data.error;
        return;
      }

      if (feedbackStatus) feedbackStatus.textContent = "Feedback submitted.";
      if (ratingEl) ratingEl.value = "";
      if (commentEl) commentEl.value = "";
    } catch (err) {
      console.error(err);
      if (feedbackStatus) feedbackStatus.textContent = "Error saving feedback.";
    } finally {
      feedbackBtn.disabled = false;
      feedbackBtn.textContent = "Submit feedback";
    }
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
    syncStoredOutputText();

    if (activeAssumptionEl) {
      activeAssumptionEl.innerHTML = escapeHtml(segment.value).replace(/\n/g, "<br>");
    }
  });
}

updateNoteTypeLabels();
syncNoteTypeDropdown();
setOutputMode(noteTypeEl ? noteTypeEl.value : "op_note");

/* -------------------- Init -------------------- */

window.addEventListener("DOMContentLoaded", async () => {
  updateNoteTypeLabels();
  syncNoteTypeDropdown();

  if (templateEditorEl) {
    await loadTemplate();
  }
});
