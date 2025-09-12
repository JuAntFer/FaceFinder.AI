// frontend/js/utils.js

// -----------------------------
// Loader
// -----------------------------
export function showLoader() {
  const loader = document.getElementById("loader");
  if (loader) loader.classList.remove("hidden");
}

export function hideLoader() {
  const loader = document.getElementById("loader");
  if (loader) loader.classList.add("hidden");
}

// -----------------------------
// Message notifications
// -----------------------------
export function showMessage(text, type = "info", duration = 4000) {
  let msgDiv = document.getElementById("message");

  // Create message container if missing
  if (!msgDiv) {
    msgDiv = document.createElement("div");
    msgDiv.id = "message";
    msgDiv.className = "message";
    document.body.appendChild(msgDiv);
  }

  // Reset previous styles
  msgDiv.className = `message ${type}`;
  msgDiv.innerText = text;
  msgDiv.style.display = "block";

  // Auto-hide after duration
  setTimeout(() => {
    if (msgDiv) msgDiv.style.display = "none";
  }, duration);
}

// -----------------------------
// Progress bar helper
// -----------------------------
export function updateProgress(percent) {
  let progressBar = document.getElementById("progressBar");

  // Create progress bar if missing
  if (!progressBar) {
    const container = document.createElement("div");
    container.id = "progressContainer";
    container.style.width = "100%";
    container.style.background = "#eee";
    container.style.borderRadius = "6px";
    container.style.margin = "10px 0";

    progressBar = document.createElement("div");
    progressBar.id = "progressBar";
    progressBar.style.height = "12px";
    progressBar.style.width = "0%";
    progressBar.style.backgroundColor = "#007BFF";
    progressBar.style.borderRadius = "6px";
    progressBar.style.transition = "width 0.3s ease";

    container.appendChild(progressBar);
    document.body.appendChild(container);
  }

  progressBar.style.width = `${percent}%`;
}
