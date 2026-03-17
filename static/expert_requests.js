(function () {
  const requestForms = Array.from(document.querySelectorAll(".trainer-request-form[data-request-id]"));
  if (!requestForms.length) return;

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function stripConsultTags(text) {
    return String(text || "").replace(/\[\[(?:\/)?(?:FACT|ASSUMPTION)\]\]/gi, "");
  }

  function sanitizeConsultTagArtifacts(text) {
    return String(text || "").replace(/\r\n?/g, "\n");
  }

  function preprocessConsultTaggedText(text) {
    return sanitizeConsultTagArtifacts(text)
      .replace(/\[\[\s*(FACT|ASSUMPTION)\s*\]\]/gi, "[[$1]]")
      .replace(/\[\[\s*\/\s*(FACT|ASSUMPTION)\s*\]\]/gi, "[[/$1]]");
  }

  function normalizeConsultDisplayText(text) {
    const normalized = sanitizeConsultTagArtifacts(preprocessConsultTaggedText(String(text || "")));
    return stripConsultTags(normalized).replace(/\n{3,}/g, "\n\n").trim();
  }

  function escapeRegExp(text) {
    return String(text || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function isConsultSectionHeading(line) {
    return /^(Reason for Consult|HPI|Past Medical History|Medical History|Past Surgical History|Surgical History|Family History|Social History|Review of Systems|ROS|Objective|Assessment and Plan):?$/i.test(String(line || "").trim());
  }

  function normalizeConsultHeading(line) {
    return String(line || "").trim().replace(/:?\s*$/, ":");
  }

  function decorateConsultHtml(html) {
    return html.replace(
      /(^|<br>)((?:Reason for Consult|HPI|Past Medical History|Medical History|Past Surgical History|Surgical History|Family History|Social History|Review of Systems|ROS|Objective|Assessment and Plan):?)(?=<br>|$)/g,
      '$1<span class="consult-heading">$2</span>'
    ).replace(/(<br><br>)/g, '<br><span class="consult-section-gap"></span>');
  }

  function splitSentences(text) {
    if (!text) return [];
    return String(text).split(/(?<=[.!?])\s+/).filter(Boolean);
  }

  function buildFallbackAssumptionPatterns(caseFacts) {
    const patterns = [];
    const assumptions = caseFacts?.assumptions || {};
    const normalizedInput = String(caseFacts?.normalized_input || "");
    const procedure = caseFacts?.procedure || "";
    const pmh = caseFacts?.clinical_context?.past_medical_history;
    const psh = caseFacts?.clinical_context?.past_surgical_history;
    const haystack = JSON.stringify(caseFacts || {});

    if (assumptions.family_history_default) patterns.push(new RegExp(escapeRegExp(assumptions.family_history_default), "gi"));
    if (assumptions.social_history_default) patterns.push(new RegExp(escapeRegExp(assumptions.social_history_default), "gi"));
    if (assumptions.modifying_factors_default) patterns.push(new RegExp(escapeRegExp(assumptions.modifying_factors_default), "gi"));
    if ((procedure === "laparoscopic_appendectomy" || /appendic/i.test(haystack)) && !/\bright lower quadrant\b/i.test(normalizedInput)) patterns.push(/\bright lower quadrant\b/gi);
    if (/cholecyst/i.test(haystack) && !/\bright upper quadrant\b/i.test(normalizedInput)) patterns.push(/\bright upper quadrant\b/gi);
    if (!pmh) patterns.push(/\bNone reported\.\b/gi);
    if (!psh) patterns.push(/\bNo prior abdominal surgery reported\.\b/gi);
    return patterns;
  }

  function explodeConsultSegments(segments, caseFacts) {
    const expanded = [];
    const fallbackPatterns = buildFallbackAssumptionPatterns(caseFacts);

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
        while (cursor < part.length) {
          let nextMatch = null;
          for (const pattern of fallbackPatterns) {
            pattern.lastIndex = cursor;
            const match = pattern.exec(part);
            if (!match) continue;
            if (!nextMatch || match.index < nextMatch.index) nextMatch = match;
          }
          if (!nextMatch) {
            expanded.push({ type: segment.type, value: part.slice(cursor) });
            break;
          }
          if (nextMatch.index > cursor) {
            expanded.push({ type: segment.type, value: part.slice(cursor, nextMatch.index) });
          }
          expanded.push({ type: "assumption", value: nextMatch[0], accepted: false });
          cursor = nextMatch.index + nextMatch[0].length;
        }
      }
    }
    return expanded;
  }

  function parseConsultTaggedOutput(text, caseFacts) {
    const source = preprocessConsultTaggedText(String(text || ""));
    const regex = /\[\[(FACT|ASSUMPTION)\]\]([\s\S]*?)\[\[\/\1\]\]/g;
    const segments = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(source)) !== null) {
      if (match.index > lastIndex) {
        segments.push({ type: "text", value: sanitizeConsultTagArtifacts(source.slice(lastIndex, match.index)) });
      }
      segments.push({
        type: match[1] === "FACT" ? "fact" : "assumption",
        value: sanitizeConsultTagArtifacts(match[2]),
        accepted: false,
      });
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < source.length) {
      segments.push({ type: "text", value: sanitizeConsultTagArtifacts(source.slice(lastIndex)) });
    }
    if (!segments.length) segments.push({ type: "text", value: sanitizeConsultTagArtifacts(source) });
    return explodeConsultSegments(segments, caseFacts);
  }

  function tokenizeForDiff(text) {
    return String(text || "").match(/\s+|[^\s]+/g) || [];
  }

  function buildDiffTokens(baseText, revisedText) {
    const a = tokenizeForDiff(baseText);
    const b = tokenizeForDiff(revisedText);
    const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));

    for (let i = a.length - 1; i >= 0; i -= 1) {
      for (let j = b.length - 1; j >= 0; j -= 1) {
        dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }

    const ops = [];
    let i = 0;
    let j = 0;
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) {
        ops.push({ type: "same", text: a[i] });
        i += 1;
        j += 1;
      } else if (dp[i + 1][j] >= dp[i][j + 1]) {
        ops.push({ type: "delete", text: a[i] });
        i += 1;
      } else {
        ops.push({ type: "insert", text: b[j] });
        j += 1;
      }
    }
    while (i < a.length) ops.push({ type: "delete", text: a[i++] });
    while (j < b.length) ops.push({ type: "insert", text: b[j++] });
    return ops;
  }

  function renderDiffHtml(baseText, revisedText) {
    const ops = buildDiffTokens(baseText, revisedText);
    if (!ops.length) return "";
    return ops.map((op) => {
      const safe = escapeHtml(op.text).replace(/\n/g, "<br>");
      if (op.type === "insert") return `<span class="tracked-insert">${safe}</span>`;
      if (op.type === "delete") return `<span class="tracked-delete">${safe}</span>`;
      return safe;
    }).join("");
  }

  function initRequestForm(form) {
    const requestId = form.dataset.requestId;
    const noteType = form.dataset.noteType || "consult_note";
    const shorthandEl = form.querySelector('[data-role="expert-shorthand"]');
    const generateBtn = form.querySelector('[data-role="expert-generate-btn"]');
    const draftInputEl = form.querySelector('[data-role="expert-generated-draft"]');
    const correctedOutputEl = form.querySelector('[data-role="expert-corrected-output"]');
    const assumptionsInputEl = form.querySelector('[data-role="expert-accepted-assumptions"]');
    const draftStatusEl = form.querySelector('[data-role="expert-draft-status"]');
    const draftTextEl = form.querySelector('[data-role="expert-draft-text"]');
    const consultDraftEl = form.querySelector('[data-role="expert-consult-draft"]');
    const draftEmptyEl = form.querySelector('[data-role="expert-draft-empty"]');
    const diffPreviewEl = form.querySelector('[data-role="tracked-diff-preview"]');
    const diffEmptyEl = form.querySelector('[data-role="tracked-diff-empty"]');
    const popoverEl = form.querySelector('[data-role="assumption-popover"]');
    const assumptionInputEl = form.querySelector('[data-role="assumption-input"]');
    const assumptionAcceptBtn = form.querySelector('[data-role="assumption-accept"]');

    let caseFacts = null;
    let currentSegments = [];
    let activeAssumptionIndex = null;
    let activeAssumptionEl = null;
    let hideTimeout = null;
    let revisionSeededFromDraft = !correctedOutputEl.value.trim();
    let acceptedAssumptionValues = [];

    try {
      acceptedAssumptionValues = JSON.parse(assumptionsInputEl?.value || "[]");
      if (!Array.isArray(acceptedAssumptionValues)) acceptedAssumptionValues = [];
    } catch (_) {
      acceptedAssumptionValues = [];
    }

    function setDraftStatus(message = "") {
      if (draftStatusEl) draftStatusEl.textContent = message;
    }

    function updateAcceptedAssumptionsInput() {
      if (!assumptionsInputEl) return;
      const accepted = [];
      currentSegments.forEach((segment) => {
        if (segment.type === "assumption" && segment.accepted && String(segment.value || "").trim()) {
          accepted.push(String(segment.value || "").trim());
        }
      });
      assumptionsInputEl.value = JSON.stringify(accepted);
    }

    function syncDraftEmptyState(hasDraft) {
      if (!draftEmptyEl) return;
      draftEmptyEl.classList.toggle("hidden", Boolean(hasDraft));
    }

    function getPlainDraftText() {
      if (noteType === "consult_note") {
        return currentSegments.map((segment) => segment.value).join("");
      }
      return draftInputEl.value || "";
    }

    function syncDiffPreview() {
      const base = normalizeConsultDisplayText(getPlainDraftText());
      const revised = correctedOutputEl.value || "";
      const html = renderDiffHtml(base, revised);
      if (diffPreviewEl) {
        diffPreviewEl.innerHTML = html || "";
      }
      if (diffEmptyEl) {
        diffEmptyEl.classList.toggle("hidden", Boolean(html));
      }
    }

    function hidePopover() {
      if (!popoverEl) return;
      popoverEl.classList.add("hidden");
      activeAssumptionIndex = null;
      activeAssumptionEl = null;
    }

    function findAssumptionSegment(index) {
      let count = -1;
      for (const segment of currentSegments) {
        if (segment.type !== "assumption") continue;
        count += 1;
        if (count === index) return segment;
      }
      return null;
    }

    function renderConsultSegments() {
      let assumptionIndex = -1;
      const html = currentSegments.map((segment) => {
        const safeValue = escapeHtml(segment.value).replace(/\n/g, "<br>");
        if (segment.type === "heading") return `<span class="consult-heading">${safeValue}</span>`;
        if (segment.type === "fact") return `<span class="consult-fact">${safeValue}</span>`;
        if (segment.type === "assumption") {
          assumptionIndex += 1;
          const className = ["consult-assumption", segment.accepted ? "is-accepted" : ""].filter(Boolean).join(" ");
          return `<span class="${className}" data-assumption-index="${assumptionIndex}">${safeValue}</span>`;
        }
        return safeValue;
      }).join("");
      if (consultDraftEl) {
        consultDraftEl.innerHTML = decorateConsultHtml(html);
        consultDraftEl.classList.remove("hidden");
      }
      if (draftTextEl) draftTextEl.classList.add("hidden");
      syncDraftEmptyState(true);
      updateAcceptedAssumptionsInput();
      syncDiffPreview();
    }

    function renderPlainDraft(text) {
      if (draftTextEl) {
        draftTextEl.value = normalizeConsultDisplayText(text);
        draftTextEl.classList.remove("hidden");
      }
      if (consultDraftEl) {
        consultDraftEl.classList.add("hidden");
        consultDraftEl.innerHTML = "";
      }
      syncDraftEmptyState(Boolean(String(text || "").trim()));
      syncDiffPreview();
    }

    function showPopover(targetEl) {
      if (!popoverEl) return;
      const assumptionIndex = Number(targetEl.dataset.assumptionIndex);
      const segment = findAssumptionSegment(assumptionIndex);
      if (!segment || segment.accepted) return;
      activeAssumptionIndex = assumptionIndex;
      activeAssumptionEl = targetEl;
      assumptionInputEl.value = segment.value;
      popoverEl.classList.remove("hidden");
      const formRect = form.getBoundingClientRect();
      const targetRect = targetEl.getBoundingClientRect();
      const top = targetRect.bottom - formRect.top + 10;
      const left = Math.max(12, Math.min(targetRect.left - formRect.left, formRect.width - popoverEl.offsetWidth - 12));
      popoverEl.style.top = `${top}px`;
      popoverEl.style.left = `${left}px`;
    }

    if (correctedOutputEl) {
      correctedOutputEl.addEventListener("input", () => {
        revisionSeededFromDraft = false;
        syncDiffPreview();
      });
    }

    if (consultDraftEl && popoverEl) {
      consultDraftEl.addEventListener("mouseover", (event) => {
        const assumptionEl = event.target.closest(".consult-assumption");
        if (!assumptionEl) return;
        showPopover(assumptionEl);
      });
      consultDraftEl.addEventListener("mouseout", (event) => {
        const assumptionEl = event.target.closest(".consult-assumption");
        if (!assumptionEl) return;
        const relatedTarget = event.relatedTarget;
        if (relatedTarget && popoverEl.contains(relatedTarget)) return;
        if (hideTimeout) clearTimeout(hideTimeout);
        hideTimeout = setTimeout(() => hidePopover(), 120);
      });
      popoverEl.addEventListener("mouseenter", () => {
        if (hideTimeout) clearTimeout(hideTimeout);
      });
      popoverEl.addEventListener("mouseleave", () => {
        if (hideTimeout) clearTimeout(hideTimeout);
        hideTimeout = setTimeout(() => hidePopover(), 120);
      });
      assumptionInputEl.addEventListener("input", () => {
        if (activeAssumptionIndex === null) return;
        const segment = findAssumptionSegment(activeAssumptionIndex);
        if (!segment) return;
        segment.value = assumptionInputEl.value;
        segment.accepted = false;
        if (activeAssumptionEl) {
          activeAssumptionEl.textContent = segment.value;
          activeAssumptionEl.classList.remove("is-accepted");
        }
        draftInputEl.value = currentSegments.map((entry) => entry.value).join("");
        updateAcceptedAssumptionsInput();
        syncDiffPreview();
      });
      assumptionAcceptBtn.addEventListener("click", () => {
        if (activeAssumptionIndex === null) return;
        const segment = findAssumptionSegment(activeAssumptionIndex);
        if (!segment) return;
        segment.accepted = true;
        if (activeAssumptionEl) activeAssumptionEl.classList.add("is-accepted");
        updateAcceptedAssumptionsInput();
        hidePopover();
      });
    }

    if (generateBtn) {
      generateBtn.addEventListener("click", async () => {
        const shorthand = (shorthandEl.value || "").trim();
        if (!shorthand) {
          setDraftStatus("Add shorthand first.");
          return;
        }

        generateBtn.disabled = true;
        generateBtn.textContent = "Generating...";
        setDraftStatus("Building draft...");
        draftInputEl.value = "";
        currentSegments = [];
        updateAcceptedAssumptionsInput();

        try {
          const res = await fetch(`/expert/requests/${requestId}/generate-draft-stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ shorthand }),
          });
          if (!res.ok) {
            let errorMessage = "Unable to generate draft.";
            try {
              const data = await res.json();
              errorMessage = data.error || errorMessage;
            } catch (_) {}
            throw new Error(errorMessage);
          }
          if (!res.body) throw new Error("Streaming not supported in this browser.");

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          let streamedText = "";

          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split("\n\n");
            buffer = events.pop() || "";
            for (const eventBlock of events) {
              const lines = eventBlock.split("\n");
              const dataLines = lines.filter((line) => line.startsWith("data: "));
              if (!dataLines.length) continue;
              let payload;
              try {
                payload = JSON.parse(dataLines.map((line) => line.slice(6)).join(""));
              } catch (_) {
                continue;
              }
              if (payload.type === "meta") caseFacts = payload.case_facts || null;
              if (payload.type === "delta") {
                streamedText += payload.delta;
                draftInputEl.value = streamedText;
                if (noteType === "consult_note") {
                  if (consultDraftEl) {
                    consultDraftEl.classList.remove("hidden");
                    consultDraftEl.innerHTML = decorateConsultHtml(
                      escapeHtml(normalizeConsultDisplayText(stripConsultTags(streamedText))).replace(/\n/g, "<br>")
                    );
                  }
                  if (draftTextEl) draftTextEl.classList.add("hidden");
                } else {
                  renderPlainDraft(streamedText);
                }
              }
              if (payload.type === "error") throw new Error(payload.error || "Generation failed.");
            }
          }

          draftInputEl.value = streamedText;
          if (noteType === "consult_note") {
            currentSegments = parseConsultTaggedOutput(streamedText, caseFacts);
            renderConsultSegments();
          } else {
            renderPlainDraft(streamedText);
          }
          if (revisionSeededFromDraft || !correctedOutputEl.value.trim()) {
            correctedOutputEl.value = normalizeConsultDisplayText(stripConsultTags(streamedText));
            revisionSeededFromDraft = true;
          }
          syncDiffPreview();
          setDraftStatus("Draft ready. Revise it with tracked changes below.");
        } catch (error) {
          console.error(error);
          setDraftStatus(error.message || "Unable to generate draft.");
        } finally {
          generateBtn.disabled = false;
          generateBtn.textContent = "Generate draft";
        }
      });
    }

    form.addEventListener("submit", () => {
      draftInputEl.value = noteType === "consult_note"
        ? currentSegments.map((segment) => segment.value).join("")
        : draftInputEl.value;
      correctedOutputEl.value = correctedOutputEl.value.trim();
      updateAcceptedAssumptionsInput();
    });

    if (draftInputEl.value.trim()) {
      if (noteType === "consult_note") {
        currentSegments = parseConsultTaggedOutput(draftInputEl.value, caseFacts);
        currentSegments.forEach((segment) => {
          if (segment.type === "assumption" && acceptedAssumptionValues.includes(String(segment.value || "").trim())) {
            segment.accepted = true;
          }
        });
        renderConsultSegments();
      } else {
        renderPlainDraft(draftInputEl.value);
      }
    } else {
      syncDraftEmptyState(false);
      syncDiffPreview();
    }
  }

  requestForms.forEach(initRequestForm);
})();
