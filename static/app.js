const generateBtn = document.getElementById("generateBtn");
const shorthandEl = document.getElementById("shorthand");
const outputEl = document.getElementById("output");
const metaBox = document.getElementById("metaBox");
const assumptionsEl = document.getElementById("assumptions");
const needsReviewEl = document.getElementById("needsReview");
const procedureBadgeEl = document.getElementById("procedureBadge");
const copyBtn = document.getElementById("copyBtn");
const emailBtn = document.getElementById("emailBtn");
const feedbackBtn = document.getElementById("feedbackBtn");
const ratingEl = document.getElementById("rating");
const commentEl = document.getElementById("comment");
const feedbackStatusEl = document.getElementById("feedbackStatus");

const structuredPreviewBox = document.getElementById("structuredPreviewBox");
const structuredPreviewEl = document.getElementById("structuredPreview");

function formatAssumptions(assumptions, needsReview) {
  const lines = [];

  for (const [key, value] of Object.entries(assumptions || {})) {
    lines.push(`${key}: ${value}`);
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

function humanizeKey(key) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(value) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function buildStructuredPreview(caseFacts, procedureLabel) {
  const demographics = caseFacts.demographics || {};
  const operative = caseFacts.operative_details || {};
  const assumptions = caseFacts.assumptions || {};

  const rows = [];

  rows.push(["Procedure", procedureLabel || "Unknown"]);

  if (demographics.age || demographics.sex) {
    const ageSex = [demographics.age ? `${demographics.age}` : null, demographics.sex ? humanizeKey(demographics.sex) : null]
      .filter(Boolean)
      .join(" / ");
    rows.push(["Patient", ageSex]);
  }

  if (operative.laterality) rows.push(["Laterality", humanizeKey(operative.laterality)]);
  if (operative.defect_type) rows.push(["Defect type", humanizeKey(operative.defect_type)]);
  if (operative.ports) rows.push(["Ports", `${operative.ports}`]);
  if (operative.complexity) rows.push(["Complexity", humanizeKey(operative.complexity)]);
  if (operative.mesh_mentioned !== undefined) rows.push(["Mesh mentioned", formatValue(operative.mesh_mentioned)]);

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

let latestProcedure = "";

if (generateBtn) {
  generateBtn.addEventListener("click", async () => {
    const shorthand = shorthandEl.value.trim();
    if (!shorthand) return;

    outputEl.value = "Generating...";

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

    outputEl.value = data.note;
    latestProcedure = data.case_facts.procedure || "";

    procedureBadgeEl.textContent = `${data.procedure_label} (confidence: ${data.case_facts.confidence.procedure})`;

    assumptionsEl.textContent = formatAssumptions(
      data.case_facts.assumptions,
      data.case_facts.needs_review
    );

    needsReviewEl.textContent = (data.case_facts.needs_review || []).join("\n");

    buildStructuredPreview(data.case_facts, data.procedure_label);

    metaBox.classList.remove("hidden");
    structuredPreviewBox.classList.remove("hidden");
  });
}

if (copyBtn) {
  copyBtn.addEventListener("click", async () => {
    await navigator.clipboard.writeText(outputEl.value);
  });
}

if (emailBtn) {
  emailBtn.addEventListener("click", () => {
    const subject = encodeURIComponent("Operative note draft");
    const body = encodeURIComponent(outputEl.value);
    window.location.href = `mailto:?subject=${subject}&body=${body}`;
  });
}

if (feedbackBtn) {
  feedbackBtn.addEventListener("click", async () => {
    const payload = {
      shorthand: shorthandEl.value.trim(),
      procedure: latestProcedure,
      rating: ratingEl.value,
      comment: commentEl.value.trim()
    };

    const res = await fetch("/feedback", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    feedbackStatusEl.textContent = data.status === "ok" ? "Feedback saved" : "Error saving feedback";
  });
}