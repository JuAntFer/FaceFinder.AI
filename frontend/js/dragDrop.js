import { showMessage } from "./utils.js";

export function setupDropZone(dropZoneId, fileInputId) {
  const dropZone = document.getElementById(dropZoneId);
  const fileInput = document.getElementById(fileInputId);

  // Helper: update drop zone label
  function updateDropZoneLabel(fileName) {
    const label = dropZone.querySelector(".drop-label");
    if (label) {
      label.textContent = fileName ? `✅ ${fileName} uploaded` : "Click or drag a file here";
    }
  }

  // Click → open file chooser
  dropZone.addEventListener("click", () => fileInput.click());

  // Highlight when dragging
  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });

  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));

  // Handle drop
  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    fileInput.files = e.dataTransfer.files;

    if (fileInput.files.length) {
      updateDropZoneLabel(fileInput.files[0].name);
      showMessage(`File "${fileInput.files[0].name}" uploaded successfully!`);
    }
  });

  // Handle manual selection via input
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) {
      updateDropZoneLabel(fileInput.files[0].name);
      showMessage(`File "${fileInput.files[0].name}" selected!`);
    }
  });
}
