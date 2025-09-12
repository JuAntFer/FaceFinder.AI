// frontend/js/app.js
import { setupDropZone } from "./dragDrop.js";
import { initReferenceUpload, resetReference } from "./reference.js";
import { initMatcher } from "./matcher.js";
import { showMessage } from "./utils.js";

// -----------------------------
// Setup drag & drop zones
// -----------------------------
const referenceDrop = setupDropZone("referenceDrop", "referenceFile", true);
const targetDrop = setupDropZone("targetDrop", "targetFile", true);

// -----------------------------
// Initialize reference upload
// -----------------------------
initReferenceUpload(referenceDrop);

// -----------------------------
// Initialize matching button
// -----------------------------
initMatcher(referenceDrop, targetDrop);

// -----------------------------
// Reset Buttons
// -----------------------------
const resetReferenceBtn = document.createElement("button");
resetReferenceBtn.textContent = "Reset Reference";
resetReferenceBtn.className = "reset-btn";
resetReferenceBtn.addEventListener("click", () => resetReference(referenceDrop));
document.getElementById("step1").appendChild(resetReferenceBtn);

const resetTargetBtn = document.createElement("button");
resetTargetBtn.textContent = "Reset Target";
resetTargetBtn.className = "reset-target-btn";
resetTargetBtn.addEventListener("click", () => {
  if (targetDrop && typeof targetDrop.resetDropZone === "function") {
    targetDrop.resetDropZone();
  }
  document.getElementById("targetFile").value = "";
  document.getElementById("resultContainer").innerHTML = "";
  document.getElementById("step3").classList.add("hidden");
  showMessage("Target reset successfully.", "success");
});
document.getElementById("step2").appendChild(resetTargetBtn);

// -----------------------------
// Global Progress Bar
// -----------------------------
const progressContainer = document.createElement("div");
progressContainer.id = "progressContainer";
Object.assign(progressContainer.style, {
  width: "100%",
  background: "#eee",
  borderRadius: "6px",
  margin: "10px 0",
  display: "none",
});

const progressBar = document.createElement("div");
progressBar.id = "progressBar";
Object.assign(progressBar.style, {
  height: "12px",
  width: "0%",
  backgroundColor: "#007BFF",
  borderRadius: "6px",
  transition: "width 0.3s ease",
});

progressContainer.appendChild(progressBar);
document.querySelector("main").insertBefore(progressContainer, document.getElementById("message"));

// -----------------------------
// Progress Bar Utility Functions
// -----------------------------
export function showProgress(show = true) {
  progressContainer.style.display = show ? "block" : "none";
  if (!show) progressBar.style.width = "0%";
}

export function updateProgress(percent = 0) {
  progressBar.style.width = `${Math.min(Math.max(percent, 0), 100)}%`;
}
