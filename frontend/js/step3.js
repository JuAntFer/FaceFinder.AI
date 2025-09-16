import { targetFiles } from './step2.js';

const matchBtn = document.getElementById("matchBtn");
const step3Section = document.getElementById("step3");
const progressContainer = document.getElementById("progressContainer");
const progressBar = document.getElementById("progressBar");
const resultContainer = document.getElementById("resultContainer");
const messageStep2 = document.getElementById("messageStep2");
const loaderStep2 = document.getElementById("loaderStep2");
const downloadLink = document.getElementById("downloadLink");
const resetTargetBtn = document.getElementById("resetTargetBtn");

// -------------------------
// Helpers
// -------------------------
function showMessage(msg, type="success") {
  if (messageStep2) {
    messageStep2.textContent = msg;
    messageStep2.className = `message ${type}`;
    messageStep2.style.display = "block";
  }
}

function resetMessage() {
  if (messageStep2) messageStep2.style.display = "none";
}

function clearResults() {
  resultContainer.innerHTML = "";
  downloadLink.href = "#";
  downloadLink.classList.add("hidden");
  resetMessage();
  targetFiles.length = 0;
}

// -------------------------
// Create ZIP of all targets
// -------------------------
async function createTargetZip() {
  if (targetFiles.length === 0) return null;
  const zip = new JSZip();
  targetFiles.forEach(f => zip.file(f.name, f));
  const blob = await zip.generateAsync({ type: "blob" });
  return new File([blob], "all_targets.zip", { type: "application/zip" });
}

// -------------------------
// Extract thumbnails (max 5)
// -------------------------
async function extractThumbnailsFromZip(blob) {
  const thumbs = [];
  let totalCount = 0;
  try {
    const zip = await JSZip.loadAsync(blob);
    const imageFiles = Object.keys(zip.files).filter(fn =>
      /\.(jpg|jpeg|png)$/i.test(fn)
    );
    totalCount = imageFiles.length;

    if (totalCount === 0) return { thumbs, totalCount };

    for (let i = 0; i < Math.min(5, totalCount); i++) {
      const fileName = imageFiles[i];
      const fileData = await zip.files[fileName].async("blob");
      thumbs.push({
        url: URL.createObjectURL(fileData),
        name: fileName
      });
    }
  } catch (err) {
    console.error("Failed to extract thumbnails:", err);
  }
  return { thumbs, totalCount };
}

// -------------------------
// Match Button Click
// -------------------------
matchBtn.addEventListener("click", async () => {
  resetMessage();
  resultContainer.innerHTML = "";

  const step1Data = window.getStep1Data ? window.getStep1Data() : { faces: [], mode: "individually" };

  if (!targetFiles || targetFiles.length === 0) {
    showMessage("Please select at least one target file.", "error");
    return;
  }

  loaderStep2.classList.remove("hidden");
  progressContainer.style.display = "block";
  progressBar.style.width = "0%";

  try {
    const formData = new FormData();
    const zipFile = await createTargetZip();
    if (!zipFile) {
      showMessage("No valid target files to upload.", "error");
      return;
    }
    formData.append("target", zipFile);
    formData.append("mode", step1Data.mode);
    formData.append("selected_indices_str", step1Data.faces.join(","));

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "http://127.0.0.1:8000/match-face-selected/");
    xhr.responseType = "blob";

    xhr.upload.addEventListener("progress", e => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        progressBar.style.width = percent + "%";
      }
    });

    xhr.onload = async () => {
      loaderStep2.classList.add("hidden");
      progressContainer.style.display = "none";

      if (xhr.status >= 200 && xhr.status < 300) {
        const contentType = xhr.getResponseHeader("content-type");
        const blob = xhr.response;

        if (contentType.includes("application/zip")) {
          // Provide ZIP download
          const url = URL.createObjectURL(blob);
          downloadLink.href = url;
          downloadLink.download = "iLoveFaceFinder.zip";
          downloadLink.classList.remove("hidden");

          // Show thumbnails
          const { thumbs, totalCount } = await extractThumbnailsFromZip(blob);
          resultContainer.innerHTML = "";
          if (totalCount > 0) {
            thumbs.forEach(t => {
              const img = document.createElement("img");
              img.src = t.url;
              img.alt = t.name;
              img.style.width = "120px";
              img.style.marginRight = "10px";
              img.style.borderRadius = "6px";
              img.style.boxShadow = "0 2px 5px rgba(0,0,0,0.2)";
              resultContainer.appendChild(img);
            });

            if (totalCount > 5) {
              const moreLabel = document.createElement("span");
              moreLabel.textContent = `... +${totalCount - 5} more`;
              moreLabel.style.fontSize = "14px";
              moreLabel.style.color = "#666";
              moreLabel.style.marginLeft = "10px";
              resultContainer.appendChild(moreLabel);
            }
          } else {
            resultContainer.innerHTML = "<p style='color:#555;font-size:14px;'>No matching photos found.</p>";
          }

          showMessage("Matching completed! Download your results below.");
          step3Section.classList.remove("hidden");
          step3Section.scrollIntoView({ behavior: "smooth" });
        } else {
          showMessage("Server returned unknown file format.", "error");
        }
      } else {
        showMessage(`Matching failed: ${xhr.statusText}`, "error");
      }
    };

    xhr.onerror = () => {
      loaderStep2.classList.add("hidden");
      progressContainer.style.display = "none";
      showMessage("Network error occurred", "error");
    };

    xhr.send(formData);
  } catch (err) {
    loaderStep2.classList.add("hidden");
    progressContainer.style.display = "none";
    showMessage(err.message, "error");
  }
});

// -------------------------
// Reset Target & Step 3
// -------------------------
resetTargetBtn.addEventListener("click", () => {
  clearResults();
  step3Section.classList.add("hidden");
});
