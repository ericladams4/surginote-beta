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
    assumptionsEl.textContent = JSON.stringify(data.case_facts.assumptions, null, 2);
    needsReviewEl.textContent = JSON.stringify(data.case_facts.needs_review, null, 2);

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
