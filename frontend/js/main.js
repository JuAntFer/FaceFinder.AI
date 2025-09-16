// -------------------------
// Imports
// -------------------------
import './step1.js';
import './step2.js';
import './step3.js';

// -------------------------
// Elements
// -------------------------
const step1Section = document.getElementById("step1");
const step2Section = document.getElementById("step2");

const nextStepBtn = document.getElementById("nextStepBtn");
const prevStepBtn = document.getElementById("prevStepBtn");

// -------------------------
// Step 1 data placeholders
// -------------------------
let selectedFaces = [];
let selectedMode = "individually";

// -------------------------
// Navigation Buttons
// -------------------------
nextStepBtn.addEventListener("click", () => {
  // Get selected mode
  const modeRadio = document.querySelector('input[name="mode"]:checked');
  selectedMode = modeRadio ? modeRadio.value : "individually";

  // Collect selected faces
  selectedFaces = Array.from(document.querySelectorAll("#facesContainer img.selected"))
                       .map(img => parseInt(img.dataset.index));

  // Show Step 2 below Step 1
  step2Section.classList.remove("hidden");
  step2Section.scrollIntoView({ behavior: "smooth" });

  console.log("Step 1 data:", { selectedMode, selectedFaces });
});

prevStepBtn.addEventListener("click", () => {
  step1Section.scrollIntoView({ behavior: "smooth" });
});

// -------------------------
// Expose Step 1 data for Step 2 & 3
// -------------------------
window.getStep1Data = function() {
  return {
    mode: selectedMode,
    faces: selectedFaces
  };
};
