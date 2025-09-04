import { setupDropZone } from "./dragDrop.js";
import { initReferenceUpload } from "./reference.js";
import { initMatcher } from "./matcher.js";

// -----------------------------
// Setup drag & drop zones
// -----------------------------
setupDropZone("referenceDrop", "referenceFile");
setupDropZone("targetDrop", "targetFile");

// -----------------------------
// Initialize reference upload
// -----------------------------
initReferenceUpload();

// -----------------------------
// Initialize matching button
// -----------------------------
initMatcher();
