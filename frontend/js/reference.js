import { showLoader, hideLoader, showMessage } from "./utils.js";

export let selectedFaceIndices = [];

export function initReferenceUpload() {
  document.getElementById("uploadReferenceBtn").addEventListener("click", async () => {
    const fileInput = document.getElementById("referenceFile");
    if (!fileInput.files.length) return showMessage("Select a reference image!", "error");

    const formData = new FormData();
    formData.append("reference", fileInput.files[0]);

    try {
      showLoader();
      const res = await fetch("http://127.0.0.1:8000/reference-faces/", { method: "POST", body: formData });
      const data = await res.json();
      hideLoader();

      const container = document.getElementById("facesContainer");
      container.innerHTML = "";

      if (!data.faces.length) return showMessage("No faces detected in reference image", "error");

      // Display detected faces
      data.faces.forEach(face => {
        const img = document.createElement("img");
        img.src = `data:image/jpeg;base64,${face.thumbnail_b64}`;
        img.dataset.index = face.index;
        img.addEventListener("click", () => {
          img.classList.toggle("selected");
          selectedFaceIndices = Array.from(container.querySelectorAll(".selected")).map(i => i.dataset.index);
        });
        container.appendChild(img);
      });

      // ✅ Reveal mode selection section
      const modeSection = document.getElementById("modeSection");
      if (modeSection) modeSection.classList.remove("hidden");

      // Reveal Step 2
      document.getElementById("step2").classList.remove("hidden");

      showMessage("Reference uploaded successfully! Select the faces and mode.", "success");

    } catch (err) {
      hideLoader();
      showMessage("Error uploading reference image", "error");
    }
  });
}
