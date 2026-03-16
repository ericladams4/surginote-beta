const shorthandEl = document.getElementById("shorthand");
const outputEl = document.getElementById("output");

const generateBtn = document.getElementById("generateBtn");
const copyBtn = document.getElementById("copyBtn");
const emailBtn = document.getElementById("emailBtn");

const ratingEl = document.getElementById("rating");
const commentEl = document.getElementById("comment");
const feedbackBtn = document.getElementById("feedbackBtn");
const feedbackStatus = document.getElementById("feedbackStatus");

const metaBox = document.getElementById("metaBox");
const assumptionsEl = document.getElementById("assumptions");
const needsReviewEl = document.getElementById("needsReview");
const procedureBadgeEl = document.getElementById("procedureBadge");

const structuredPreviewBox = document.getElementById("structuredPreviewBox");
const structuredPreviewEl = document.getElementById("structuredPreview");

const generatingStatusEl = document.getElementById("generatingStatus");

const noteTypeEl = document.getElementById("noteType");
const templateHeadingEl = document.getElementById("templateHeading");
const outputLabelEl = document.getElementById("outputLabel");
const templateEditorEl = document.getElementById("templateEditor");
const saveTemplateBtn = document.getElementById("saveTemplateBtn");
const deleteTemplateBtn = document.getElementById("deleteTemplateBtn");
const templateStatusEl = document.getElementById("templateStatus");

let latestProcedure = "";
let currentLoadedTemplate = "";
let currentLoadedNoteType = noteTypeEl ? noteTypeEl.value : "op_note";

/* -------------------- Helpers -------------------- */

function humanizeKey(key) {
  if (!key) return "";
  return String(key)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(value) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function formatAssumptions(assumptions, needsReview) {
  const lines = [];

  for (const [key, value] of Object.entries(assumptions || {})) {
    lines.push(`${humanizeKey(key)}: ${formatValue(value)}`);
  }

  if ((needsReview || []).length > 0) {
    lines.push("");
    lines.push("Review needed:");
    for (const item of needsReview) {
      lines.push(`- ${item}`);
    }
  }

  return lines.join("\n");
}

function buildStructuredPreview(caseFacts, procedureLabel) {
  if (!structuredPreviewEl) return;

  const demographics = caseFacts.demographics || {};
  const operative = caseFacts.operative_details || {};
  const assumptions = caseFacts.assumptions || {};
  const rows = [];

  rows.push(["Procedure", procedureLabel || "Unknown"]);

  if (demographics.age || demographics.sex) {
    const ageSex = [
      demographics.age ? `${demographics.age}` : null,
      demographics.sex ? humanizeKey(demographics.sex) : null
    ].filter(Boolean).join(" / ");
    rows.push(["Patient", ageSex]);
  }

  if (operative.laterality) rows.push(["Laterality", humanizeKey(operative.laterality)]);
  if (operative.defect_type) rows.push(["Defect type", humanizeKey(operative.defect_type)]);
  if (operative.ports) rows.push(["Ports", `${operative.ports}`]);
  if (operative.complexity) rows.push(["Complexity", humanizeKey(operative.complexity)]);
  if (operative.mesh_mentioned !== undefined) {
    rows.push(["Mesh mentioned", formatValue(operative.mesh_mentioned)]);
  }

  for (const [key, value] of Object.entries(assumptions)) {
    rows.push([humanizeKey(key), formatValue(value)]);
  }

  if (rows.length === 0) {
    structuredPreviewEl.innerHTML = `<div class="structured-empty">No structured fields available yet.</div>`;
    return;
  }

  structuredPreviewEl.innerHTML = rows.map(([label, value]) => `
    <div class="structured-field">
      <div class="structured-field-label">${label}</div>
      <div class="structured-field-value">${value}</div>
    </div>
  `).join("");
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

/* -------------------- Note type / template UX -------------------- */

function noteTypeLabel(noteType) {
  if (noteType === "op_note") return "Op Note";
  if (noteType === "clinic_note") return "Clinic Note";
  if (noteType === "consult_note") return "Consult Note";
  return "Note";
}

function templatePlaceholder(noteType) {
  if (noteType === "op_note") {
    return "Example: Preoperative Diagnosis, Postoperative Diagnosis, Procedure, Findings, Description of Procedure, EBL, Specimen, Drains, Complications.";
  }
  if (noteType === "clinic_note") {
    return "Example: Chief Complaint, HPI, Relevant Workup, Assessment, Plan.";
  }
  if (noteType === "consult_note") {
    return "Example: Reason for Consult, HPI, Exam, Labs/Imaging, Assessment, Recommendations.";
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
    return "67yoM admitted with SBO. Surgery consulted for abdominal pain, distention, emesis. CT with transition point in mid abdomen. Mild tenderness, no peritonitis. Recommend nonoperative management with bowel rest, IVF, serial abdominal exams.";
  }
  return "Describe the encounter in shorthand or free text.";
}

function updateNoteTypeLabels() {
  if (!noteTypeEl) return;

  const label = noteTypeLabel(noteTypeEl.value);

  if (templateHeadingEl) {
    templateHeadingEl.textContent = `Template for ${label}`;
  }

  if (outputLabelEl) {
    outputLabelEl.textContent = `Generated ${label}`;
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

    if (hasUnsavedTemplateChanges()) {
      const confirmed = window.confirm(
        `You have unsaved template changes for ${noteTypeLabel(currentLoadedNoteType)}. Discard them and switch?`
      );

      if (!confirmed) {
        noteTypeEl.value = currentLoadedNoteType;
        return;
      }
    }

    await loadTemplate(nextType);
  });
}

/* -------------------- Generate note -------------------- */

if (generateBtn) {
  generateBtn.addEventListener("click", async () => {
    const shorthand = shorthandEl.value.trim();

    if (!shorthand) {
      alert("Please enter shorthand first.");
      return;
    }

    generateBtn.disabled = true;
    generateBtn.textContent = "Generating...";
    outputEl.value = "";
    outputEl.classList.add("output-loading");

    if (generatingStatusEl) {
      generatingStatusEl.textContent = "Generating note...";
    }

    try {
      const res = await fetch("/generate-note", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shorthand,
          note_type: noteTypeEl ? noteTypeEl.value : "op_note"
        })
      });

      const data = await res.json();

      if (data.error) {
        outputEl.value = data.error;
        if (generatingStatusEl) generatingStatusEl.textContent = "";
        return;
      }

      outputEl.value = data.note || "";
      latestProcedure = data.case_facts?.procedure || "";

      if (procedureBadgeEl && data.case_facts?.confidence?.procedure !== undefined) {
        procedureBadgeEl.textContent =
          `${data.procedure_label} (confidence: ${data.case_facts.confidence.procedure})`;
      }

      if (assumptionsEl) {
        assumptionsEl.textContent = formatAssumptions(
          data.case_facts?.assumptions,
          data.case_facts?.needs_review
        );
      }

      if (needsReviewEl) {
        needsReviewEl.textContent = (data.case_facts?.needs_review || []).join("\n");
      }

      buildStructuredPreview(data.case_facts || {}, data.procedure_label);

      if (metaBox) metaBox.classList.remove("hidden");
      if (structuredPreviewBox) structuredPreviewBox.classList.remove("hidden");

      if (generatingStatusEl) generatingStatusEl.textContent = "";
    } catch (err) {
      outputEl.value = "Error generating note.";
      console.error(err);
      if (generatingStatusEl) generatingStatusEl.textContent = "";
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = "Generate note";
      outputEl.classList.remove("output-loading");
    }
  });
}

/* -------------------- Copy -------------------- */

if (copyBtn) {
  copyBtn.addEventListener("click", async () => {
    const text = outputEl.value.trim();

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
    const text = outputEl.value.trim();

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
      generated_note: outputEl.value.trim()
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

/* -------------------- Init -------------------- */

window.addEventListener("DOMContentLoaded", () => {
  updateNoteTypeLabels();
  loadTemplate();
});