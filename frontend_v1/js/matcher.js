import { showLoader, hideLoader, showMessage } from "./utils.js";
import { selectedFaceIndices } from "./reference.js";

export function initMatcher() {
  const matchBtn = document.getElementById("matchBtn");
  const newTargetBtn = document.getElementById("newTargetBtn");
  const resultContainer = document.getElementById("resultContainer");

  matchBtn.addEventListener("click", async () => {
    const refFile = document.getElementById("referenceFile").files[0];
    const targetFile = document.getElementById("targetFile").files[0];
    if (!refFile || !targetFile) return showMessage("Select reference and target files!", "error");
    if (!selectedFaceIndices.length) return showMessage("Select at least one face!", "error");

    const mode = document.querySelector('input[name="mode"]:checked').value;

    const formData = new FormData();
    formData.append("reference", refFile);
    formData.append("target", targetFile);
    formData.append("selected_indices_str", selectedFaceIndices.join(","));
    formData.append("mode", mode);

    try {
      showLoader();
      const res = await fetch("http://127.0.0.1:8000/match-face-selected/", { method: "POST", body: formData });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        hideLoader();
        return showMessage(errData.detail || "Error matching faces", "error");
      }

      if (targetFile.name.toLowerCase().endsWith(".zip")) {
        const data = await res.json();
        hideLoader();
        if (data.job_id) {
          document.getElementById("step3").classList.remove("hidden");
          checkJobStatus(data.job_id); // ← now defined below
          showMessage("Processing ZIP in background...", "success");
        } else {
          showMessage("Error starting job. Check backend logs.", "error");
        }
      } else {
        const blob = await res.blob();
        hideLoader();
        const imgUrl = URL.createObjectURL(blob);
        resultContainer.innerHTML = `<img src="${imgUrl}" />`;
        showMessage("Face match complete!", "success");
        newTargetBtn.classList.remove("hidden");
      }
    } catch (err) {
      hideLoader();
      console.error(err);
      showMessage("Error matching faces. Check console for details.", "error");
    }
  });

  // -----------------------------
  // Poll job status for ZIP files
  // -----------------------------
  async function checkJobStatus(jobId) {
    const statusDiv = document.getElementById("jobStatus");
    const downloadLink = document.getElementById("downloadLink");

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://127.0.0.1:8000/jobs/${jobId}`);
        const data = await res.json();
        statusDiv.innerText = `Status: ${data.status}`;

        if (data.status === "done") {
          clearInterval(interval);
          downloadLink.href = `http://127.0.0.1:8000/download/${jobId}`;
          downloadLink.classList.remove("hidden");
          showMessage("Job completed! You can download the ZIP.", "success");
        } else if (data.status === "error") {
          clearInterval(interval);
          statusDiv.innerText = `Error: ${data.result}`;
          showMessage("Job failed. Check logs.", "error");
        }
      } catch (err) {
        clearInterval(interval);
        showMessage("Error checking job status", "error");
      }
    }, 2000);
  }

  // -----------------------------
  // Handle uploading a new target
  // -----------------------------
  newTargetBtn.addEventListener("click", () => {
    const targetInput = document.getElementById("targetFile");
    targetInput.value = "";
    targetInput.files = null;

    document.getElementById("targetDrop").querySelector(".file-info").textContent = "";
    resultContainer.innerHTML = "";
    document.getElementById("step3").classList.add("hidden");
    newTargetBtn.classList.add("hidden");
    showMessage("You can now upload a new target dataset.", "success");
  });
}
