// -------------------------
// Step 2: Target Upload
// -------------------------
const targetDrop = document.getElementById("targetDrop");
const targetFileInput = document.getElementById("targetFile");
const resetTargetBtn = document.getElementById("resetTargetBtn");
const resultContainer = document.getElementById("resultContainer");
const messageStep2 = document.getElementById("messageStep2");
const loaderStep2 = document.getElementById("loaderStep2");

let targetFiles = [];
let displayTargetFiles = [];

// -------------------------
// Helpers
// -------------------------
export function showMessage(msg, type="success") {
  if(messageStep2){
    messageStep2.textContent = msg;
    messageStep2.className = `message ${type}`;
    messageStep2.style.display = "block";
  }
}

export function resetMessage() {
  if(messageStep2) messageStep2.style.display="none";
}

function renderTargetFileList() {
  const info = targetDrop.querySelector(".file-info");
  info.innerHTML = "";
  displayTargetFiles.forEach((item, index) => {
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
      deleteTargetFile(index);
    });

    span.appendChild(fileName);
    span.appendChild(delBtn);
    info.appendChild(span);
  });
}

function deleteTargetFile(index) {
  const item = displayTargetFiles[index];
  if(item.isZip && item.extractedFiles){
    targetFiles = targetFiles.filter(f => !item.extractedFiles.includes(f));
  } else {
    const idx = targetFiles.findIndex(f => f === item.file);
    if(idx > -1) targetFiles.splice(idx, 1);
  }
  displayTargetFiles.splice(index, 1);
  renderTargetFileList();
}

// -------------------------
// Drag & Drop
// -------------------------
targetDrop.addEventListener("click", () => targetFileInput.click());
targetDrop.addEventListener("dragover", e => { e.preventDefault(); targetDrop.classList.add("dragover"); });
targetDrop.addEventListener("dragleave", e => { e.preventDefault(); targetDrop.classList.remove("dragover"); });
targetDrop.addEventListener("drop", e => { e.preventDefault(); targetDrop.classList.remove("dragover"); handleTargetFiles(e.dataTransfer.files); });
targetFileInput.addEventListener("change", e => handleTargetFiles(e.target.files));

// -------------------------
// Handle Target Files
// -------------------------
export async function handleTargetFiles(files){
  resetMessage();
  let added = 0;

  for(let f of files){
    const isImage = f.type.startsWith("image/");
    const isZip = f.name.toLowerCase().endsWith(".zip");

    if(isImage){
      targetFiles.push(f);
      displayTargetFiles.push({file: f, isZip: false});
      added++;
    } else if(isZip){
      const extractedFiles = [];
      try {
        const zip = await JSZip.loadAsync(f);
        const zipImageFiles = Object.keys(zip.files).filter(fn => /\.(jpg|jpeg|png)$/i.test(fn));

        if(zipImageFiles.length === 0){
          showMessage(`ZIP contains no supported images: ${f.name}`, "error");
          continue;
        }

        for(let filename of zipImageFiles){
          const zipEntry = zip.files[filename];
          if(!zipEntry.dir){
            const baseName = filename.split("/").pop().split("\\").pop();
            const blob = await zipEntry.async("blob");
            const file = new File([blob], baseName, {type: blob.type});
            targetFiles.push(file);
            extractedFiles.push(file);
            added++;
          }
        }
        displayTargetFiles.push({file: f, isZip: true, extractedFiles});
      } catch(err){
        console.error(err);
        showMessage(`Failed to read ZIP: ${f.name}`, "error");
      }
    } else {
      showMessage(`Unsupported file: ${f.name}`, "error");
    }
  }

  if(added === 0 && targetFiles.length === 0){
    showMessage("No valid target files were added.", "error");
  }

  renderTargetFileList();
}

// -------------------------
// Reset Target Files
// -------------------------
resetTargetBtn.addEventListener("click", () => {
  targetFiles.length = 0;
  displayTargetFiles.length = 0;
  renderTargetFileList();
  resultContainer.innerHTML = "";
  resetMessage();
});

// -------------------------
// Export targetFiles
// -------------------------
export { targetFiles };
window.getTargetFiles = () => targetFiles;
