import {
  FONT_FAMILY_OPTIONS,
  FONT_SIZE_OPTIONS,
  normalizeEditorHtml,
  plainTextToRichHtml,
  htmlToStructuredText,
  applyEditorTypography,
  buildToolbarSelectMarkup,
  execRichTextCommand,
  applyTemplateHighlight,
  clearTemplateHighlight,
  getToolbarActionTarget,
  initializeToolbarSelectMenus,
  syncToolbarSelectValue,
} from "/static/js/shared/rich_text.js";

const workspaceState = window.__TEMPLATE_WORKSPACE__ || {};

const noteTypePillEls = Array.from(document.querySelectorAll(".templates-type-pill"));
const profileListEl = document.getElementById("templateProfileList");
const statusEl = document.getElementById("templateWorkspaceStatus");
const newProfileBtn = document.getElementById("newTemplateProfileBtn");
const saveBtn = document.getElementById("saveTemplateProfileBtn");
const deleteBtn = document.getElementById("deleteTemplateProfileBtn");
const backToAppLinkEl = document.getElementById("templatesBackToAppLink");

const noteTypeSelectEl = document.getElementById("templateProfileNoteType");
const noteTypeTriggerEl = document.getElementById("templateNoteTypeTrigger");
const noteTypeTriggerLabelEl = document.getElementById("templateNoteTypeLabelText");
const noteTypeMenuEl = document.getElementById("templateNoteTypeMenu");
const noteTypeOptionEls = Array.from(document.querySelectorAll(".template-note-type-option"));
const profileNameEl = document.getElementById("templateProfileName");
const strictEditorEl = document.getElementById("templateStrictEditor");
const strictToolbarEl = document.getElementById("templateStrictToolbar");
const workflowNavEls = Array.from(document.querySelectorAll(".templates-workflow-nav-item"));
const workflowPanelEls = Array.from(document.querySelectorAll(".templates-workflow-panel"));
const toneSetupNotesEl = document.getElementById("toneSetupNotes");
const toneSummaryOutputEl = document.getElementById("toneSummaryOutput");
const analyzeToneBtn = document.getElementById("analyzeToneBtn");
const resetToneBtn = document.getElementById("resetToneBtn");

let profiles = Array.isArray(workspaceState.initialProfiles) ? workspaceState.initialProfiles : [];
let selectedNoteType = workspaceState.selectedNoteType || "consult_note";
let activeProfileId = null;
let globalToneProfile = workspaceState.globalToneProfile || null;
let activeWorkflow = "template";
const TEMPLATE_NOTE_TYPE_ORDER = ["consult_note", "clinic_note", "op_note"];

function noteTypeLabel(noteType) {
  if (noteType === "consult_note") return "Consult Note";
  if (noteType === "clinic_note") return "Clinic Note";
  if (noteType === "op_note") return "Op Note";
  return "Note";
}

function syncNoteTypeDropdown() {
  const activeValue = noteTypeSelectEl ? noteTypeSelectEl.value : selectedNoteType;
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
    return;
  }
  closeNoteTypeMenu();
}

function setStatus(message, isError = false) {
  if (!statusEl) return;
  statusEl.textContent = message || "";
  statusEl.classList.toggle("is-error", Boolean(message) && isError);
  statusEl.classList.toggle("is-success", Boolean(message) && !isError);
}

function setActiveWorkflow(nextWorkflow) {
  activeWorkflow = nextWorkflow === "tone" ? "tone" : "template";
  workflowNavEls.forEach((navEl) => {
    const isActive = navEl.dataset.workflowTarget === activeWorkflow;
    navEl.classList.toggle("is-active", isActive);
  });
  workflowPanelEls.forEach((panelEl) => {
    const shouldShow = panelEl.dataset.workflowPanel === activeWorkflow;
    panelEl.classList.toggle("hidden", !shouldShow);
  });
}

function blankProfile(noteType) {
  return {
    id: null,
    note_type: noteType,
    name: "",
    strict_template_text: "",
    strict_template_html: "",
    strict_enabled: 1,
    style_example_text: "",
    style_example_html: "",
    style_enabled: 0,
    is_default: profiles.filter((profile) => profile.note_type === noteType).length === 0 ? 1 : 0,
  };
}

function buildToolbarMarkup() {
  return `
    ${buildToolbarSelectMarkup("font-family", FONT_FAMILY_OPTIONS)}
    ${buildToolbarSelectMarkup("font-size", FONT_SIZE_OPTIONS.map((option) => ({ ...option, label: `${option.label}px` })), "rich-editor-select-wrap-size")}
    <button type="button" class="rich-editor-tool" data-editor-command="bold" aria-label="Bold"><strong>B</strong></button>
    <button type="button" class="rich-editor-tool" data-editor-command="italic" aria-label="Italic"><em>I</em></button>
    <button type="button" class="rich-editor-tool" data-editor-command="underline" aria-label="Underline"><u>U</u></button>
    <button type="button" class="rich-editor-tool" data-editor-command="insertUnorderedList" aria-label="Bulleted list">• List</button>
    <button type="button" class="rich-editor-tool" data-editor-command="insertOrderedList" aria-label="Numbered list">1. List</button>
    <button type="button" class="rich-editor-tool rich-editor-tool-mark-exact" data-template-mark="exact" aria-label="Keep exact">Keep exact</button>
    <button type="button" class="rich-editor-tool rich-editor-tool-mark-guide" data-template-mark="guide" aria-label="Recognize and apply">Recognize + apply</button>
    <button type="button" class="rich-editor-tool" data-template-mark="clear" aria-label="Clear mark">Clear</button>
  `;
}

function initializeHighlightToolbar(toolbarEl, editorEl) {
  if (!toolbarEl || !editorEl) return;
  toolbarEl.innerHTML = buildToolbarMarkup();
  syncToolbarSelectValue(toolbarEl, "font-family", editorEl.dataset.fontFamily || "system-ui", FONT_FAMILY_OPTIONS);
  syncToolbarSelectValue(
    toolbarEl,
    "font-size",
    editorEl.dataset.fontSize || "16px",
    FONT_SIZE_OPTIONS.map((option) => ({ ...option, label: `${option.label}px` }))
  );
  initializeToolbarSelectMenus(toolbarEl, (setting, value) => {
    if (setting === "font-family") {
      applyEditorTypography(editorEl, {
        fontFamily: value || "system-ui",
        fontSize: editorEl.dataset.fontSize || "16px",
      });
    } else if (setting === "font-size") {
      applyEditorTypography(editorEl, {
        fontFamily: editorEl.dataset.fontFamily || "system-ui",
        fontSize: value || "16px",
      });
    }
    syncToolbarSelectValue(toolbarEl, "font-family", editorEl.dataset.fontFamily || "system-ui", FONT_FAMILY_OPTIONS);
    syncToolbarSelectValue(
      toolbarEl,
      "font-size",
      editorEl.dataset.fontSize || "16px",
      FONT_SIZE_OPTIONS.map((option) => ({ ...option, label: `${option.label}px` }))
    );
  });

  toolbarEl.addEventListener("mousedown", (event) => {
    const target = event.target.closest("button");
    if (target) {
      event.preventDefault();
    }
  });

  toolbarEl.addEventListener("click", (event) => {
    const commandButton = getToolbarActionTarget(event, toolbarEl);
    if (commandButton) {
      editorEl.focus();
      execRichTextCommand(commandButton.dataset.editorCommand);
      return;
    }
    const actionButton = event.target.closest("[data-template-mark]");
    if (!actionButton || !toolbarEl.contains(actionButton)) return;
    editorEl.focus();
    if (actionButton.dataset.templateMark === "clear") {
      clearTemplateHighlight();
      return;
    }
    applyTemplateHighlight(actionButton.dataset.templateMark);
  });

}

function populateTypographySelect(selectEl, options) {
  if (!selectEl) return;
  selectEl.innerHTML = options.map((option) => (
    `<option value="${option.value}">${option.label}</option>`
  )).join("");
}

function getProfilesForSelectedType() {
  return profiles.filter((profile) => profile.note_type === selectedNoteType);
}

function getActiveProfile() {
  if (activeProfileId === null) return blankProfile(selectedNoteType);
  return profiles.find((profile) => profile.id === activeProfileId) || blankProfile(selectedNoteType);
}

function applyEditorFontSettings() {
  const typography = {
    fontFamily: "system-ui",
    fontSize: "16px",
  };
  applyEditorTypography(strictEditorEl, typography);
  if (strictToolbarEl) {
    syncToolbarSelectValue(strictToolbarEl, "font-family", typography.fontFamily, FONT_FAMILY_OPTIONS);
    syncToolbarSelectValue(
      strictToolbarEl,
      "font-size",
      typography.fontSize,
      FONT_SIZE_OPTIONS.map((option) => ({ ...option, label: `${option.label}px` }))
    );
  }
}

function fillEditor(profile) {
  profileNameEl.value = profile.name || "";
  const strictHtml = profile.strict_template_html || plainTextToRichHtml(profile.strict_template_text || "");
  strictEditorEl.innerHTML = normalizeEditorHtml(strictHtml);
  applyEditorFontSettings();
  deleteBtn.disabled = !profile.id;
}

function renderProfileList() {
  if (!profileListEl) return;
  const allProfiles = [...profiles].sort((a, b) => {
    const noteTypeRank = TEMPLATE_NOTE_TYPE_ORDER.indexOf(a.note_type) - TEMPLATE_NOTE_TYPE_ORDER.indexOf(b.note_type);
    if (noteTypeRank !== 0) return noteTypeRank;
    if (Boolean(a.is_default) !== Boolean(b.is_default)) {
      return Boolean(b.is_default) - Boolean(a.is_default);
    }
    return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
  });

  if (!allProfiles.length) {
    profileListEl.innerHTML = `
      <div class="structured-empty templates-empty-state">
        No saved templates yet.
      </div>
    `;
    return;
  }

  const groupedMarkup = TEMPLATE_NOTE_TYPE_ORDER.map((noteType) => {
    const groupProfiles = allProfiles.filter((profile) => profile.note_type === noteType);
    if (!groupProfiles.length) return "";

    return `
      <section class="template-profile-group">
        <div class="template-profile-group-label">${noteTypeLabel(noteType)}</div>
        <div class="template-profile-group-list">
          ${groupProfiles.map((profile) => `
            <button
              type="button"
              class="template-profile-list-item ${profile.id === activeProfileId ? "is-active" : ""}"
              data-profile-id="${profile.id}"
            >
              <span class="template-profile-delete" data-action="delete-profile" data-profile-id="${profile.id}" aria-label="Delete saved template" title="Delete saved template">×</span>
              <span class="template-profile-title-row">
                <span class="template-profile-title">${profile.name}</span>
                ${profile.is_default ? '<span class="template-profile-badge">Default</span>' : ""}
              </span>
              <span class="template-profile-meta">
                ${profile.strict_enabled ? '<span class="template-profile-chip">FORMAT</span>' : ""}
              </span>
            </button>
          `).join("")}
        </div>
      </section>
    `;
  }).join("");

  profileListEl.innerHTML = groupedMarkup;
}

function syncNoteTypePills() {
  noteTypePillEls.forEach((pillEl) => {
    const isActive = pillEl.dataset.noteType === selectedNoteType;
    pillEl.classList.toggle("is-active", isActive);
    pillEl.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  if (noteTypeSelectEl) {
    noteTypeSelectEl.value = selectedNoteType;
  }
  syncNoteTypeDropdown();

  if (backToAppLinkEl) {
    backToAppLinkEl.href = `/app?note_type=${encodeURIComponent(selectedNoteType)}`;
  }
}

function chooseInitialProfile() {
  const noteTypeProfiles = getProfilesForSelectedType();
  const defaultProfile = noteTypeProfiles.find((profile) => profile.is_default);
  activeProfileId = defaultProfile ? defaultProfile.id : (noteTypeProfiles[0]?.id ?? null);
  fillEditor(getActiveProfile());
}

async function loadProfiles(noteType) {
  selectedNoteType = noteType;
  syncNoteTypePills();
  setStatus("");
  if (window.history && window.history.replaceState) {
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("note_type", noteType);
    window.history.replaceState({}, "", nextUrl.toString());
  }

  try {
    const res = await fetch(`/api/template-profiles?note_type=${encodeURIComponent(noteType)}`);
    const data = await res.json();
    if (!res.ok) {
      setStatus(data.error || "Unable to load profiles.", true);
      return;
    }

    profiles = [
      ...profiles.filter((profile) => profile.note_type !== noteType),
      ...(data.profiles || []),
    ];
    chooseInitialProfile();
    renderProfileList();
  } catch (err) {
    console.error(err);
    setStatus("Unable to load profiles.", true);
  }
}

function gatherPayload() {
  const strictTemplateHtml = normalizeEditorHtml(strictEditorEl.innerHTML);
  const strictTemplateText = htmlToStructuredText(strictTemplateHtml);
  const activeProfile = getActiveProfile();
  return {
    note_type: selectedNoteType,
    name: profileNameEl.value.trim(),
    strict_template_text: strictTemplateText,
    strict_template_html: strictTemplateHtml,
    strict_enabled: Boolean(strictTemplateText),
    style_example_text: "",
    style_example_html: "",
    style_enabled: false,
    is_default: activeProfileId
      ? Boolean(activeProfile.is_default)
      : profiles.filter((profile) => profile.note_type === selectedNoteType).length === 0,
  };
}

function renderToneSummary() {
  if (!toneSummaryOutputEl) return;
  const summary = (globalToneProfile && globalToneProfile.tone_summary) || "";
  const traits = Array.isArray(globalToneProfile?.tone_traits) ? globalToneProfile.tone_traits : [];
  if (!summary) {
    toneSummaryOutputEl.textContent = "No tone profile yet. Paste a few notes and analyze them to build one.";
    return;
  }
  toneSummaryOutputEl.textContent = `${summary}${traits.length ? `\n\n${traits.map((item) => `- ${item}`).join("\n")}` : ""}`;
}

async function deleteProfileById(profileId) {
  if (!profileId) return;
  const confirmed = window.confirm("Delete this template profile?");
  if (!confirmed) return;

  if (deleteBtn) {
    deleteBtn.disabled = true;
    deleteBtn.textContent = "Deleting...";
  }
  setStatus("");

  try {
    const res = await fetch(`/api/template-profiles/${profileId}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) {
      setStatus(data.error || "Unable to delete profile.", true);
      return;
    }

    profiles = profiles.filter((profile) => profile.id !== profileId);
    if (activeProfileId === profileId) {
      chooseInitialProfile();
    }
    renderProfileList();
    setStatus("Profile deleted.");
  } catch (err) {
    console.error(err);
    setStatus("Unable to delete profile.", true);
  } finally {
    if (deleteBtn) {
      deleteBtn.disabled = false;
      deleteBtn.textContent = "Delete profile";
    }
  }
}

if (newProfileBtn) {
  newProfileBtn.addEventListener("click", () => {
    activeProfileId = null;
    fillEditor(blankProfile(selectedNoteType));
    renderProfileList();
    setStatus("New profile ready.");
    profileNameEl.focus();
  });
}

if (profileListEl) {
  profileListEl.addEventListener("click", async (event) => {
    const deleteAction = event.target.closest('[data-action="delete-profile"]');
    if (deleteAction) {
      event.preventDefault();
      event.stopPropagation();
      await deleteProfileById(Number(deleteAction.dataset.profileId));
      return;
    }

    const button = event.target.closest(".template-profile-list-item");
    if (!button) return;
    const nextProfileId = Number(button.dataset.profileId);
    const profile = profiles.find((item) => item.id === nextProfileId);
    if (!profile) return;
    activeProfileId = nextProfileId;
    selectedNoteType = profile.note_type || selectedNoteType;
    syncNoteTypePills();
    fillEditor(profile);
    renderProfileList();
    setStatus("");
  });
}

noteTypePillEls.forEach((pillEl) => {
  pillEl.addEventListener("click", () => {
    if (pillEl.dataset.noteType === selectedNoteType) return;
    loadProfiles(pillEl.dataset.noteType);
  });
});

if (noteTypeSelectEl) {
  noteTypeSelectEl.addEventListener("change", () => {
    const nextType = noteTypeSelectEl.value || "consult_note";
    if (nextType === selectedNoteType) return;
    loadProfiles(nextType);
  });
}

if (noteTypeTriggerEl) {
  noteTypeTriggerEl.addEventListener("click", () => {
    toggleNoteTypeMenu();
  });
}

noteTypeOptionEls.forEach((optionEl) => {
  optionEl.addEventListener("click", () => {
    if (!noteTypeSelectEl) return;
    const nextValue = optionEl.dataset.value;
    if (!nextValue || nextValue === noteTypeSelectEl.value) {
      closeNoteTypeMenu();
      return;
    }
    noteTypeSelectEl.value = nextValue;
    noteTypeSelectEl.dispatchEvent(new Event("change", { bubbles: true }));
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

workflowNavEls.forEach((navEl) => {
  navEl.addEventListener("click", () => {
    setActiveWorkflow(navEl.dataset.workflowTarget || "template");
  });
});

if (saveBtn) {
  saveBtn.addEventListener("click", async () => {
    const payload = gatherPayload();
    if (!payload.name) {
      setStatus("Profile name is required.", true);
      return;
    }
    if (!payload.strict_template_text) {
      setStatus("Paste a note or template and mark the key parts you want SurgiNote to learn.", true);
      return;
    }

    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
    setStatus("");

    try {
      const url = activeProfileId ? `/api/template-profiles/${activeProfileId}` : "/api/template-profiles";
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(data.error || "Unable to save profile.", true);
        return;
      }

      const savedProfile = data.profile;
      profiles = profiles.filter((profile) => profile.id !== savedProfile.id);
      if (savedProfile.is_default) {
        profiles = profiles.map((profile) => (
          profile.note_type === savedProfile.note_type
            ? { ...profile, is_default: 0 }
            : profile
        ));
      }
      profiles.push(savedProfile);
      renderProfileList();
      activeProfileId = null;
      fillEditor(blankProfile(selectedNoteType));
      renderProfileList();
      setStatus(`Profile "${savedProfile.name}" saved. Ready for a new one.`);
      profileNameEl.focus();
    } catch (err) {
      console.error(err);
      setStatus("Unable to save profile.", true);
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = "Submit profile";
    }
  });
}

if (deleteBtn) {
  deleteBtn.addEventListener("click", async () => {
    if (!activeProfileId) return;
    await deleteProfileById(activeProfileId);
  });
}

if (analyzeToneBtn) {
  analyzeToneBtn.addEventListener("click", async () => {
    const notesText = String(toneSetupNotesEl ? toneSetupNotesEl.value : "").trim();
    if (!notesText) {
      setStatus("Paste a few de-identified notes first.", true);
      return;
    }

    analyzeToneBtn.disabled = true;
    analyzeToneBtn.textContent = "Analyzing...";
    setStatus("");

    try {
      const res = await fetch("/api/tone-profile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes_text: notesText }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus(data.error || "Unable to analyze tone.", true);
        return;
      }
      globalToneProfile = data.profile || null;
      renderToneSummary();
      setStatus("Tone profile saved.");
    } catch (err) {
      console.error(err);
      setStatus("Unable to analyze tone.", true);
    } finally {
      analyzeToneBtn.disabled = false;
      analyzeToneBtn.textContent = "Analyze tone";
    }
  });
}

if (resetToneBtn) {
  resetToneBtn.addEventListener("click", async () => {
    const confirmed = window.confirm("Delete your saved global tone profile?");
    if (!confirmed) return;

    resetToneBtn.disabled = true;
    try {
      await fetch("/api/tone-profile", { method: "DELETE" });
      globalToneProfile = null;
      if (toneSetupNotesEl) toneSetupNotesEl.value = "";
      renderToneSummary();
      setStatus("Tone profile deleted.");
    } catch (err) {
      console.error(err);
      setStatus("Unable to delete tone profile.", true);
    } finally {
      resetToneBtn.disabled = false;
    }
  });
}

syncNoteTypePills();
initializeHighlightToolbar(strictToolbarEl, strictEditorEl);
setActiveWorkflow("template");
chooseInitialProfile();
renderProfileList();
renderToneSummary();
if (toneSetupNotesEl && globalToneProfile?.notes_text) {
  toneSetupNotesEl.value = globalToneProfile.notes_text;
}

fillEditor(getActiveProfile());
