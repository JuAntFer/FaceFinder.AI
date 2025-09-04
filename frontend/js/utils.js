export function showLoader() {
  document.getElementById("loader").classList.remove("hidden");
}

export function hideLoader() {
  document.getElementById("loader").classList.add("hidden");
}

export function showMessage(text, type = "success") {
  const msg = document.getElementById("message");
  msg.innerText = text;
  msg.className = `message ${type}`;
  msg.style.display = "block";
  setTimeout(() => msg.style.display = "none", 4000);
}