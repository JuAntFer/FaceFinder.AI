let selectedFaceIndices = [];

document.getElementById("uploadReferenceBtn").addEventListener("click", async () => {
    const fileInput = document.getElementById("referenceFile");
    if (!fileInput.files.length) return alert("Select a reference image!");

    const formData = new FormData();
    formData.append("reference", fileInput.files[0]);

    const res = await fetch("http://127.0.0.1:8000/reference-faces/", {
        method: "POST",
        body: formData
    });

    const data = await res.json();
    const container = document.getElementById("facesContainer");
    container.innerHTML = "";

    if (!data.faces.length) return alert("No faces found in reference image");

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

    document.getElementById("step2").classList.remove("hidden");
});

document.getElementById("matchBtn").addEventListener("click", async () => {
    const refFile = document.getElementById("referenceFile").files[0];
    const targetFile = document.getElementById("targetFile").files[0];
    if (!refFile || !targetFile) return alert("Select reference and target files!");
    if (!selectedFaceIndices.length) return alert("Select at least one face!");

    const mode = document.querySelector('input[name="mode"]:checked').value;
    const formData = new FormData();
    formData.append("reference", refFile);
    formData.append("target", targetFile);
    formData.append("selected_indices_str", selectedFaceIndices.join(","));
    formData.append("mode", mode);

    const res = await fetch("http://127.0.0.1:8000/match-face-selected/", {
        method: "POST",
        body: formData
    });

    if (targetFile.name.endsWith(".zip")) {
        const data = await res.json();
        if (data.job_id) {
            document.getElementById("step3").classList.remove("hidden");
            checkJobStatus(data.job_id);
        }
    } else {
        const blob = await res.blob();
        const imgUrl = URL.createObjectURL(blob);
        const container = document.getElementById("resultContainer");
        container.innerHTML = `<img src="${imgUrl}" />`;
    }
});

async function checkJobStatus(jobId) {
    const statusDiv = document.getElementById("jobStatus");
    const link = document.getElementById("downloadLink");

    const interval = setInterval(async () => {
        const res = await fetch(`http://127.0.0.1:8000/jobs/${jobId}`);
        const data = await res.json();
        statusDiv.innerText = `Status: ${data.status}`;
        if (data.status === "done") {
            clearInterval(interval);
            link.href = `http://127.0.0.1:8000/download/${jobId}`;
            link.classList.remove("hidden");
        } else if (data.status === "error") {
            clearInterval(interval);
            statusDiv.innerText = `Error: ${data.result}`;
        }
    }, 2000);
}
