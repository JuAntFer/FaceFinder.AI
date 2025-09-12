// frontend/js/reference.js
import { showLoader, hideLoader, showMessage } from "./utils.js";

export let selectedFaceIndices = [];
export let uploadedReferences = []; // all uploaded files
let globalFaceIndex = 0; // unique ID for faces across multiple uploads

export function initReferenceUpload(refDropZone) {
  const facesContainer = document.getElementById("facesContainer");
  const step2 = document.getElementById("step2");
  const modeSection = document.getElementById("modeSection");

  // -----------------------------
  // Update uploadedReferences when dragDrop changes
  // -----------------------------
  if (refDropZone && refDropZone.resetDropZone) {
    refDropZone.onFileChange = (newFiles) => {
      // Use newFiles as the source of truth
      uploadedReferences = [...newFiles];

      // Remove faces belonging to deleted files
      const remainingFileNames = uploadedReferences.map(f => f.name);
      const wrappers = Array.from(facesContainer.children);
      wrappers.forEach(wrapper => {
        const img = wrapper.querySelector("img");
        const sourceName = img.title.replace("From: ", "");
        if (!remainingFileNames.includes(sourceName)) {
          wrapper.remove();
          selectedFaceIndices = selectedFaceIndices.filter(
            idx => idx !== parseInt(img.dataset.index)
          );
        }
      });
    };
  }

  // -----------------------------
  // Upload Button
  // -----------------------------
  const uploadBtn = document.getElementById("uploadReferenceBtn");
  uploadBtn.addEventListener("click", async () => {
    if (!uploadedReferences.length) {
      return showMessage("Select at least one reference file!", "error");
    }

    const formData = new FormData();
    uploadedReferences.forEach(f => formData.append("references", f));

    try {
      showLoader();
      const res = await fetch("http://127.0.0.1:8000/reference-faces/", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      hideLoader();

      if (!data.faces.length)
        return showMessage("No faces detected in reference images", "error");

      data.faces.forEach(face => {
        const wrapper = document.createElement("div");
        wrapper.style.position = "relative";
        wrapper.style.display = "inline-block";
        wrapper.style.margin = "5px";

        const img = document.createElement("img");
        img.src = `data:image/jpeg;base64,${face.thumbnail_b64}`;
        img.dataset.index = globalFaceIndex++;
        img.title = `From: ${face.ref_source}`;
        img.style.width = "100px";
        img.style.height = "100px";
        img.style.objectFit = "cover";
        img.style.border = "2px solid transparent";
        img.style.cursor = "pointer";

        img.addEventListener("click", () => {
          img.classList.toggle("selected");
          img.style.border = img.classList.contains("selected")
            ? "2px solid #007BFF"
            : "2px solid transparent";
          selectedFaceIndices = Array.from(
            facesContainer.querySelectorAll(".selected")
          ).map(i => parseInt(i.dataset.index));
        });

        const delBtn = document.createElement("button");
        delBtn.textContent = "×";
        Object.assign(delBtn.style, {
          position: "absolute",
          top: "2px",
          right: "2px",
          background: "#dc3545",
          color: "white",
          border: "none",
          borderRadius: "50%",
          cursor: "pointer",
        });

        delBtn.addEventListener("click", () => {
          wrapper.remove();
          selectedFaceIndices = selectedFaceIndices.filter(
            idx => idx !== parseInt(img.dataset.index)
          );
          // Remove the file from uploadedReferences if no other faces from it remain
          const fileName = face.ref_source;
          const remainingFaces = Array.from(facesContainer.querySelectorAll("img"))
            .map(i => i.title.replace("From: ", ""));
          if (!remainingFaces.includes(fileName)) {
            uploadedReferences = uploadedReferences.filter(f => f.name !== fileName);
          }
        });

        wrapper.appendChild(img);
        wrapper.appendChild(delBtn);
        facesContainer.appendChild(wrapper);
      });

      if (modeSection) modeSection.classList.remove("hidden");
      step2.classList.remove("hidden");
      showMessage("Reference(s) uploaded successfully! Select faces and mode.", "success");

    } catch (err) {
      hideLoader();
      console.error(err);
      showMessage("Error uploading reference files", "error");
    }
  });
}

// -----------------------------
// Reset references
// -----------------------------
export function resetReference(refDropZone = null) {
  uploadedReferences = [];
  selectedFaceIndices = [];
  globalFaceIndex = 0;
  document.getElementById("facesContainer").innerHTML = "";
  if (refDropZone && typeof refDropZone.resetDropZone === "function") {
    refDropZone.resetDropZone();
  }
  document.getElementById("step2").classList.add("hidden");
  document.getElementById("modeSection").classList.add("hidden");
  showMessage("Reference reset successfully.", "success");
}

