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

let latestProcedure = "";

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
    ]
      .filter(Boolean)
      .join(" / ");
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

  structuredPreviewEl.innerHTML = rows
    .map(([label, value]) => {
      return `
        <div class="structured-field">
          <div class="structured-field-label">${label}</div>
          <div class="structured-field-value">${value}</div>
        </div>
      `;
    })
    .join("");
}

async function copyTextWithFallback(text) {
  if (!text) return false;

  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) {
    // fall through to legacy copy
  }

  try {
    const temp = document.createElement("textarea");
    temp.value = text;
    temp.style.position = "fixed";
    temp.style.left = "-9999px";
    temp.style.top = "0";
    document.body.appendChild(temp);
    temp.focus();
    temp.select();

    const successful = document.execCommand("copy");
    document.body.removeChild(temp);
    return successful;
  } catch (_) {
    return false;
  }
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
    outputEl.value = "Generating...";

    try {
      const res = await fetch("/generate-note", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ shorthand })
      });

      const data = await res.json();

      if (data.error) {
        outputEl.value = data.error;
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
    } catch (err) {
      outputEl.value = "Error generating note.";
      console.error(err);
    } finally {
      generateBtn.disabled = false;
      generateBtn.textContent = "Generate note";
    }
  });
}

/* -------------------- Copy button -------------------- */

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

/* -------------------- Email button -------------------- */

if (emailBtn) {
  emailBtn.addEventListener("click", () => {
    const text = outputEl.value.trim();

    if (!text) {
      alert("Generate a note first.");
      return;
    }

    const subject = encodeURIComponent(
      latestProcedure
        ? `Operative Note Draft - ${humanizeKey(latestProcedure)}`
        : "Operative Note Draft"
    );

    const body = encodeURIComponent(text);
    const mailto = `mailto:?subject=${subject}&body=${body}`;

    try {
      window.location.href = mailto;
    } catch (err) {
      console.error(err);
      alert("Unable to open email draft. Make sure a mail app is configured on this device.");
    }
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
        headers: {"Content-Type": "application/json"},
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