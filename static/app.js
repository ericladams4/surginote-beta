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

    metaBox.classList.remove("hidden");
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
