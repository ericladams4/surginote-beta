import {
  copyBtn,
  copyBtnBottom,
  consultOutputEl,
  richOutputEl,
  assumptionPopoverEl,
  assumptionInputEl,
  assumptionAcceptBtn,
  assumptionRejectBtn,
  ratingOptionGridEl,
  ratingModalBackdropEl,
  ratingModalSkipEl,
  performCopyAction,
  getCurrentOutputText,
  cancelHideAssumptionPopover,
  scheduleHideAssumptionPopover,
  handleConsultMouseOver,
  handleConsultMouseOut,
  handleAssumptionInputChange,
  handleAssumptionAccept,
  handleAssumptionReject,
  handleRatingOptionGridClick,
  dismissRatingModal,
  initializeAppSurface,
  handleDomContentLoaded,
  handleRatingEscape,
} from "./logic.js";

const copyButtons = [copyBtn, copyBtnBottom].filter(Boolean);

copyButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const text = getCurrentOutputText();

    if (!text) {
      alert("Nothing to copy yet.");
      return;
    }
    await performCopyAction();
  });
});

if (consultOutputEl && assumptionPopoverEl) {
  consultOutputEl.addEventListener("mouseover", handleConsultMouseOver);
  consultOutputEl.addEventListener("mouseout", handleConsultMouseOut);
}

if (richOutputEl && assumptionPopoverEl) {
  richOutputEl.addEventListener("mouseover", handleConsultMouseOver);
  richOutputEl.addEventListener("mouseout", handleConsultMouseOut);
}

if (assumptionPopoverEl) {
  assumptionPopoverEl.addEventListener("mouseenter", cancelHideAssumptionPopover);
  assumptionPopoverEl.addEventListener("mouseleave", scheduleHideAssumptionPopover);

  assumptionInputEl.addEventListener("input", handleAssumptionInputChange);
  assumptionAcceptBtn.addEventListener("click", handleAssumptionAccept);
  assumptionRejectBtn.addEventListener("click", handleAssumptionReject);
}

if (ratingOptionGridEl) {
  ratingOptionGridEl.addEventListener("click", handleRatingOptionGridClick);
}

if (ratingModalBackdropEl) {
  ratingModalBackdropEl.addEventListener("click", dismissRatingModal);
}

if (ratingModalSkipEl) {
  ratingModalSkipEl.addEventListener("click", dismissRatingModal);
}

initializeAppSurface();

window.addEventListener("DOMContentLoaded", handleDomContentLoaded);
document.addEventListener("keydown", handleRatingEscape);
