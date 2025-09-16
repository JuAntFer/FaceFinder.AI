// -------------------------
// Step 1: Reference Upload
// -------------------------
export const step1 = (() => {
  const referenceDrop = document.getElementById("referenceDrop");
  const referenceFileInput = document.getElementById("referenceFile");
  const uploadReferenceBtn = document.getElementById("uploadReferenceBtn");
  const resetStepBtn = document.getElementById("resetStepBtn");
  const nextStepBtn = document.getElementById("nextStepBtn");
  const facesContainer = document.getElementById("facesContainer");
  const modeSection = document.getElementById("modeSection");
  const messageBox = document.getElementById("message");
  const loader = document.getElementById("loader");

  let referenceFiles = [];
  let displayFiles = [];

  const BACKEND_URL =  "https://facefinder-ai.onrender.com";

  // -------------------------
  // UI Helpers
  // -------------------------
  function showMessage(msg, type="success") {
    messageBox.textContent = msg;
    messageBox.className = `message ${type}`;
    messageBox.style.display = "block";
  }

  function resetMessage() {
    messageBox.style.display = "none";
  }

  function renderFileList() {
    const info = referenceDrop.querySelector(".file-info");
    info.innerHTML = "";
    displayFiles.forEach((item, index) => {
      const span = document.createElement("span");
      span.style.marginRight = "8px";
      span.style.display = "inline-flex";
      span.style.alignItems = "center";

      const fileName = document.createElement("span");
      fileName.textContent = item.file.name;

      const delBtn = document.createElement("button");
      delBtn.textContent = "×";
      delBtn.style.marginLeft = "4px";
      delBtn.style.padding = "0 4px";
      delBtn.style.cursor = "pointer";
      delBtn.style.border = "none";
      delBtn.style.background = "#dc3545";
      delBtn.style.color = "#fff";
      delBtn.style.borderRadius = "3px";
      delBtn.addEventListener("click", e => {
        e.stopPropagation();
        deleteFile(index);
      });

      span.appendChild(fileName);
      span.appendChild(delBtn);
      info.appendChild(span);
    });
  }

  function deleteFile(index) {
    const item = displayFiles[index];
    if(item.isZip && item.extractedFiles){
      referenceFiles = referenceFiles.filter(f => !item.extractedFiles.includes(f));
    } else {
      referenceFiles = referenceFiles.filter(f => f !== item.file);
    }
    displayFiles.splice(index, 1);
    renderFileList();
  }

  // -------------------------
  // Drag & Drop Handlers
  // -------------------------
  referenceDrop.addEventListener("click", () => referenceFileInput.click());
  referenceDrop.addEventListener("dragover", e => { e.preventDefault(); referenceDrop.classList.add("dragover"); });
  referenceDrop.addEventListener("dragleave", e => { e.preventDefault(); referenceDrop.classList.remove("dragover"); });
  referenceDrop.addEventListener("drop", e => { e.preventDefault(); referenceDrop.classList.remove("dragover"); handleFiles(e.dataTransfer.files); });
  referenceFileInput.addEventListener("change", e => handleFiles(e.target.files));

  // -------------------------
  // Handle uploaded files
  // -------------------------
  async function handleFiles(files) {
    resetMessage();
    for(let f of files){
      const isImage = f.type.startsWith("image/");
      const isZip = f.name.toLowerCase().endsWith(".zip");

      if(isImage){
        referenceFiles.push(f);
        displayFiles.push({ file: f, isZip: false });
      } else if(isZip){
        const extractedFiles = [];
        try{
          const zip = await JSZip.loadAsync(f);
          const zipImageFiles = Object.keys(zip.files).filter(fn => /\.(jpg|jpeg|png)$/i.test(fn));
          if(zipImageFiles.length === 0){
            showMessage(`ZIP contains no supported images: ${f.name}`, "error");
            continue;
          }

          for(const filename of zipImageFiles){
            const zipEntry = zip.files[filename];
            if(!zipEntry.dir){
              const blob = await zipEntry.async("blob");
              const file = new File([blob], zipEntry.name.split("/").pop(), { type: blob.type });
              referenceFiles.push(file);
              extractedFiles.push(file);
            }
          }

          displayFiles.push({ file: f, isZip: true, extractedFiles });
        } catch(err){
          console.error(err);
          showMessage(`Failed to read ZIP: ${f.name}`, "error");
        }
      } else {
        showMessage(`Unsupported file: ${f.name}`, "error");
      }
    }
    renderFileList();
  }

  // -------------------------
  // Upload references to backend
  // -------------------------
  async function uploadReferences(){
    resetMessage();
    if(!referenceFiles.length){
      showMessage("Please select files.", "error");
      return;
    }

    loader.classList.remove("hidden");
    try{
      const formData = new FormData();
      referenceFiles.forEach(f => formData.append("references", f));

      const response = await fetch(`${BACKEND_URL}/reference-faces/`, { method: "POST", body: formData });
      if(!response.ok){
        const err = await response.json();
        throw new Error(err.detail || "Upload failed");
      }

      const data = await response.json();
      if(!data.faces.length){
        showMessage("No faces detected.", "error");
        return;
      }

      // Display faces
      facesContainer.innerHTML = "";
      data.faces.forEach(face => {
        const img = document.createElement("img");
        img.src = `data:image/jpeg;base64,${face.thumbnail_b64}`;
        img.dataset.index = face.index;
        img.onclick = () => img.classList.toggle("selected");
        facesContainer.appendChild(img);
      });

      modeSection.classList.remove("hidden");
      nextStepBtn.classList.remove("hidden");
      showMessage(`Detected ${data.faces.length} face(s). Click to select which ones to keep.`);

    } catch(err){
      showMessage(err.message, "error");
    } finally {
      loader.classList.add("hidden");
    }
  }

  // -------------------------
  // Reset Step 1
  // -------------------------
  resetStepBtn.addEventListener("click", () => {
    // Clear memory
    referenceFiles.length = 0;
    displayFiles.length = 0;

    // Reset UI
    facesContainer.innerHTML = "";
    modeSection.classList.add("hidden");
    nextStepBtn.classList.add("hidden");
    renderFileList();
    resetMessage();

    // Reset input and mode selection
    referenceFileInput.value = "";
    const modeRadios = document.querySelectorAll('input[name="mode"]');
    modeRadios.forEach(r => r.checked = r.value === "individually");
  });

  uploadReferenceBtn.addEventListener("click", uploadReferences);

  // -------------------------
  // Clear memory on unload
  // -------------------------
  window.addEventListener("beforeunload", () => {
    referenceFiles.length = 0;
    displayFiles.length = 0;
  });

  // -------------------------
  // Expose Step 1 data
  // -------------------------
  return {
    getSelectedFaces: () => Array.from(facesContainer.querySelectorAll("img.selected")).map(img => Number(img.dataset.index)),
    getMode: () => document.querySelector('input[name="mode"]:checked')?.value || "individually",
    nextStepBtn
  };
})();
