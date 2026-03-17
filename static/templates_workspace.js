const workspaceState = window.__TEMPLATE_WORKSPACE__ || {};

const noteTypePillEls = Array.from(document.querySelectorAll(".templates-type-pill"));
const profileListEl = document.getElementById("templateProfileList");
const statusEl = document.getElementById("templateWorkspaceStatus");
const newProfileBtn = document.getElementById("newTemplateProfileBtn");
const saveBtn = document.getElementById("saveTemplateProfileBtn");
const deleteBtn = document.getElementById("deleteTemplateProfileBtn");
const backToAppLinkEl = document.getElementById("templatesBackToAppLink");

const profileNameEl = document.getElementById("templateProfileName");
const profileDefaultEl = document.getElementById("templateProfileDefault");
const strictTextEl = document.getElementById("templateStrictText");
const styleEnabledEl = document.getElementById("templateStyleEnabled");
const styleTextEl = document.getElementById("templateStyleText");

let profiles = Array.isArray(workspaceState.initialProfiles) ? workspaceState.initialProfiles : [];
let selectedNoteType = workspaceState.selectedNoteType || "consult_note";
let activeProfileId = null;
let draftMode = "existing";

function noteTypeLabel(noteType) {
  if (noteType === "consult_note") return "Consult Note";
  if (noteType === "clinic_note") return "Clinic Note";
  if (noteType === "op_note") return "Op Note";
  return "Note";
}

function setStatus(message, isError = false) {
  if (!statusEl) return;
  statusEl.textContent = message || "";
  statusEl.classList.toggle("is-error", Boolean(message) && isError);
  statusEl.classList.toggle("is-success", Boolean(message) && !isError);
}

function blankProfile(noteType) {
  return {
    id: null,
    note_type: noteType,
    name: "",
    strict_template_text: "",
    strict_enabled: 1,
    style_example_text: "",
    style_enabled: 1,
    is_default: profiles.filter((profile) => profile.note_type === noteType).length === 0 ? 1 : 0,
  };
}

function getProfilesForSelectedType() {
  return profiles.filter((profile) => profile.note_type === selectedNoteType);
}

function getActiveProfile() {
  if (activeProfileId === null) return blankProfile(selectedNoteType);
  return profiles.find((profile) => profile.id === activeProfileId) || blankProfile(selectedNoteType);
}

function fillEditor(profile) {
  profileNameEl.value = profile.name || "";
  profileDefaultEl.checked = Boolean(profile.is_default);
  strictTextEl.value = profile.strict_template_text || "";
  styleEnabledEl.checked = Boolean(profile.style_enabled);
  styleTextEl.value = profile.style_example_text || "";
  deleteBtn.disabled = !profile.id;
}

function renderProfileList() {
  if (!profileListEl) return;
  const noteTypeProfiles = [...getProfilesForSelectedType()].sort((a, b) => {
    if (Boolean(a.is_default) !== Boolean(b.is_default)) {
      return Boolean(b.is_default) - Boolean(a.is_default);
    }
    return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
  });
  if (!noteTypeProfiles.length) {
    profileListEl.innerHTML = `
      <div class="structured-empty templates-empty-state">
        No saved ${noteTypeLabel(selectedNoteType).toLowerCase()} profiles yet.
      </div>
    `;
    return;
  }

  profileListEl.innerHTML = noteTypeProfiles.map((profile) => `
    <button
      type="button"
      class="template-profile-list-item ${profile.id === activeProfileId ? "is-active" : ""}"
      data-profile-id="${profile.id}"
    >
      <span class="template-profile-title-row">
        <span class="template-profile-title">${profile.name}</span>
        ${profile.is_default ? '<span class="template-profile-badge">Default</span>' : ""}
      </span>
      <span class="template-profile-meta">
        ${profile.strict_enabled ? '<span class="template-profile-chip">STRICT</span>' : ""}
        ${profile.style_enabled ? '<span class="template-profile-chip">STYLE</span>' : ""}
      </span>
    </button>
  `).join("");
}

function syncNoteTypePills() {
  noteTypePillEls.forEach((pillEl) => {
    const isActive = pillEl.dataset.noteType === selectedNoteType;
    pillEl.classList.toggle("is-active", isActive);
    pillEl.setAttribute("aria-selected", isActive ? "true" : "false");
  });

  if (backToAppLinkEl) {
    backToAppLinkEl.href = `/app?note_type=${encodeURIComponent(selectedNoteType)}`;
  }
}

function chooseInitialProfile() {
  const noteTypeProfiles = getProfilesForSelectedType();
  const defaultProfile = noteTypeProfiles.find((profile) => profile.is_default);
  activeProfileId = defaultProfile ? defaultProfile.id : (noteTypeProfiles[0]?.id ?? null);
  draftMode = activeProfileId ? "existing" : "new";
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
  const strictTemplateText = strictTextEl.value.trim();
  return {
    note_type: selectedNoteType,
    name: profileNameEl.value.trim(),
    strict_template_text: strictTemplateText,
    strict_enabled: Boolean(strictTemplateText),
    style_example_text: styleTextEl.value.trim(),
    style_enabled: styleEnabledEl.checked,
    is_default: profileDefaultEl.checked,
  };
}

if (newProfileBtn) {
  newProfileBtn.addEventListener("click", () => {
    activeProfileId = null;
    draftMode = "new";
    fillEditor(blankProfile(selectedNoteType));
    renderProfileList();
    setStatus("New profile ready.");
    profileNameEl.focus();
  });
}

if (profileListEl) {
  profileListEl.addEventListener("click", (event) => {
    const button = event.target.closest(".template-profile-list-item");
    if (!button) return;
    activeProfileId = Number(button.dataset.profileId);
    draftMode = "existing";
    fillEditor(getActiveProfile());
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

if (saveBtn) {
  saveBtn.addEventListener("click", async () => {
    const payload = gatherPayload();
    if (!payload.name) {
      setStatus("Profile name is required.", true);
      return;
    }
    if (!payload.strict_template_text && !payload.style_example_text) {
      setStatus("Add a strict template, a style example, or both.", true);
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
      activeProfileId = savedProfile.id;
      draftMode = "existing";
      renderProfileList();
      fillEditor(savedProfile);
      setStatus("Profile saved.");
    } catch (err) {
      console.error(err);
      setStatus("Unable to save profile.", true);
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save profile";
    }
  });
}

if (deleteBtn) {
  deleteBtn.addEventListener("click", async () => {
    if (!activeProfileId) return;
    const confirmed = window.confirm("Delete this template profile?");
    if (!confirmed) return;

    deleteBtn.disabled = true;
    deleteBtn.textContent = "Deleting...";
    setStatus("");

    try {
      const res = await fetch(`/api/template-profiles/${activeProfileId}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) {
        setStatus(data.error || "Unable to delete profile.", true);
        return;
      }

      profiles = profiles.filter((profile) => profile.id !== activeProfileId);
      chooseInitialProfile();
      renderProfileList();
      setStatus("Profile deleted.");
    } catch (err) {
      console.error(err);
      setStatus("Unable to delete profile.", true);
    } finally {
      deleteBtn.disabled = false;
      deleteBtn.textContent = "Delete profile";
    }
  });
}

syncNoteTypePills();
chooseInitialProfile();
renderProfileList();
