// frontend/js/dragDrop.js

import { showMessage } from "./utils.js";

export function setupDropZone(dropZoneId, fileInputId, allowMultiple = true, onFileChange = null) {
  const dropZone = document.getElementById(dropZoneId);
  const fileInput = document.getElementById(fileInputId);
  let filesList = [];

  const renderFilesList = () => {
    let listContainer = dropZone.querySelector(".files-list");
    if (!listContainer) {
      listContainer = document.createElement("div");
      listContainer.className = "files-list";
      listContainer.style.marginTop = "10px";
      dropZone.appendChild(listContainer);
    }
    listContainer.innerHTML = "";

    filesList.forEach((file, idx) => {
      const row = document.createElement("div");
      Object.assign(row.style, { display: "flex", alignItems: "center", marginBottom: "4px", position: "relative" });

      const nameSpan = document.createElement("span");
      nameSpan.textContent = file.name;
      nameSpan.style.flex = "1";

      const delBtn = document.createElement("button");
      delBtn.textContent = "×";
      Object.assign(delBtn.style, { background: "#dc3545", color: "white", border: "none", borderRadius: "50%", width: "20px", height: "20px", cursor: "pointer", marginLeft: "6px" });

      delBtn.addEventListener("click", () => {
        const removed = filesList.splice(idx, 1)[0];
        syncFileInput();
        renderFilesList();
        showMessage(`Removed "${removed.name}"`, "info");
        if (onFileChange) onFileChange(filesList);
      });

      row.appendChild(nameSpan);
      row.appendChild(delBtn);
      listContainer.appendChild(row);
    });
  };

  const syncFileInput = () => {
    const dt = new DataTransfer();
    filesList.forEach(f => dt.items.add(f));
    fileInput.files = dt.files;
    if (onFileChange) onFileChange(filesList);
  };

  const handleFiles = (newFiles) => {
    newFiles.forEach(f => {
      if (!filesList.some(existing => existing.name === f.name)) {
        if (!allowMultiple) filesList = [f];
        else filesList.push(f);
      }
    });
    syncFileInput();
    renderFilesList();
    newFiles.forEach(f => showMessage(`Added "${f.name}"`, "success"));
  };

  const resetDropZone = () => {
    filesList = [];
    fileInput.value = "";
    renderFilesList();
    showMessage("Drop zone reset", "info");
    if (onFileChange) onFileChange(filesList);
  };

  dropZone.addEventListener("click", () => fileInput.click());
  dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("dragover"); });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
  dropZone.addEventListener("drop", e => { e.preventDefault(); dropZone.classList.remove("dragover"); handleFiles(Array.from(e.dataTransfer.files)); });
  fileInput.addEventListener("change", () => handleFiles(Array.from(fileInput.files)));

  renderFilesList();
  return { resetDropZone };
}
