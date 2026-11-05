"use strict";

const CONFIG = window.ENROLL_CONFIG || { API_BASE: "", EXAM: "" };

const POSES = [
  { key: "straight", label: "Straight", prompt: "Look straight at the camera" },
  { key: "left", label: "Left", prompt: "Turn your head slightly to your LEFT" },
  { key: "right", label: "Right", prompt: "Turn your head slightly to your RIGHT" },
];

const state = {
  fullName: "",
  studentNo: "",
  photos: [null, null, null],
  active: 0,
  stream: null,
  cameraReady: false,
};

const els = {};
[
  "steps", "screen-details", "screen-scan", "screen-done",
  "fullName", "studentNo", "consent", "detailsError", "toScan",
  "slots", "video", "camStatus", "posePrompt", "captureBtn",
  "submitBtn", "scanError", "backToDetails", "doneSummary", "receipt",
  "enrollAnother", "overlay", "overlayText", "scanIntro",
].forEach((id) => (els[id] = document.getElementById(id)));

// ---- navigation ----------------------------------------------------------

function showScreen(n) {
  els["screen-details"].hidden = n !== 1;
  els["screen-scan"].hidden = n !== 2;
  els["screen-done"].hidden = n !== 3;
  [...els.steps.children].forEach((li) => {
    const s = Number(li.dataset.step);
    li.classList.toggle("active", s === n);
    li.classList.toggle("done", s < n);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showError(el, msg) {
  el.textContent = msg;
  el.hidden = !msg;
}

// ---- step 1: details -----------------------------------------------------

els.toScan.addEventListener("click", () => {
  const name = els.fullName.value.trim();
  const no = els.studentNo.value.trim().toUpperCase();
  if (!name) return showError(els.detailsError, "Please enter your full name.");
  if (!no) return showError(els.detailsError, "Please enter your index number.");
  if (!els.consent.checked) return showError(els.detailsError, "Please tick the consent box to continue.");
  showError(els.detailsError, "");
  state.fullName = name;
  state.studentNo = no;
  showScreen(2);
  startCamera();
});

els.backToDetails.addEventListener("click", () => {
  stopCamera();
  showScreen(1);
});

// ---- step 2: camera + capture -------------------------------------------

async function startCamera() {
  state.cameraReady = false;
  els.camStatus.classList.remove("ready");
  els.camStatus.textContent = "Starting camera…";
  els.captureBtn.disabled = true;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    els.camStatus.textContent = "Camera needs a secure (HTTPS) connection. Open this page over https:// or localhost.";
    return;
  }
  try {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 960 }, height: { ideal: 1280 } },
      audio: false,
    });
    els.video.srcObject = state.stream;
    await els.video.play();
    state.cameraReady = true;
    els.camStatus.classList.add("ready");
    updateScanUI();
  } catch (err) {
    const map = {
      NotAllowedError: "Camera permission was denied. Allow camera access in your browser, then tap Back and Continue again.",
      NotFoundError: "No camera was found on this device.",
      NotReadableError: "The camera is busy in another app. Close it and try again.",
    };
    els.camStatus.textContent = map[err.name] || "Could not start the camera. " + (err.message || "");
  }
}

function stopCamera() {
  if (state.stream) {
    state.stream.getTracks().forEach((t) => t.stop());
    state.stream = null;
  }
  state.cameraReady = false;
}

function capture() {
  const v = els.video;
  if (!state.cameraReady || !v.videoWidth) return;
  const maxDim = 720; // keep uploads small for mobile data
  const scale = Math.min(1, maxDim / Math.max(v.videoWidth, v.videoHeight));
  const w = Math.round(v.videoWidth * scale);
  const h = Math.round(v.videoHeight * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  // Mirror to match the selfie preview AND the orientation live attendance uses.
  ctx.translate(w, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(v, 0, 0, w, h);
  state.photos[state.active] = canvas.toDataURL("image/jpeg", 0.9);

  const next = state.photos.findIndex((p) => !p);
  state.active = next === -1 ? state.active : next;
  renderSlots();
  updateScanUI();
}

function renderSlots() {
  [...els.slots.children].forEach((slot, i) => {
    const filled = Boolean(state.photos[i]);
    slot.classList.toggle("filled", filled);
    slot.classList.toggle("active", i === state.active);
    slot.innerHTML = filled
      ? `<img src="${state.photos[i]}" alt="${POSES[i].label} photo" /><span class="tick">✓</span>`
      : `<span class="slot-num">${i + 1}</span><span class="slot-label">${POSES[i].label}</span>`;
  });
}

function updateScanUI() {
  const allFilled = state.photos.every(Boolean);
  els.posePrompt.textContent = allFilled
    ? "All 3 photos captured — review and submit, or tap a photo to retake."
    : POSES[state.active].prompt;
  els.captureBtn.disabled = !state.cameraReady;
  els.captureBtn.textContent = state.photos[state.active] ? "📸 Retake this photo" : "📸 Capture";
  els.submitBtn.disabled = !allFilled;
}

els.captureBtn.addEventListener("click", capture);
els.slots.addEventListener("click", (e) => {
  const slot = e.target.closest(".slot");
  if (!slot) return;
  state.active = Number(slot.dataset.index);
  renderSlots();
  updateScanUI();
});

// ---- submit --------------------------------------------------------------

function showOverlay(text) {
  els.overlayText.textContent = text;
  els.overlay.hidden = false;
}
function hideOverlay() {
  els.overlay.hidden = true;
}

els.submitBtn.addEventListener("click", async () => {
  showError(els.scanError, "");
  showOverlay("Saving your face…");
  const payload = {
    full_name: state.fullName,
    student_no: state.studentNo,
    photos: state.photos.map((image, i) => ({ step: POSES[i].key, image })),
  };
  if (CONFIG.EXAM) payload.exam = CONFIG.EXAM;

  try {
    const res = await fetch(`${CONFIG.API_BASE}/enroll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      const problems = detail && detail.problems ? detail.problems : typeof detail === "string" ? [detail] : null;
      throw new Error(problems ? problems.join(" ") : `Enrollment failed (${res.status}).`);
    }
    hideOverlay();
    stopCamera();
    showDone(data);
  } catch (err) {
    hideOverlay();
    showError(els.scanError, err.message || "Could not reach the server. Check your connection and try again.");
  }
});

// ---- step 3: done --------------------------------------------------------

function showDone(data) {
  els.doneSummary.textContent = `${data.full_name} is now registered for face attendance.`;
  const rows = [
    ["Name", data.full_name],
    ["Index number", data.student_no],
    ["Face samples", String(data.samples_saved)],
  ];
  if (data.registered_exam) rows.push(["Registered for", data.registered_exam]);
  els.receipt.innerHTML = rows
    .map(([k, v]) => `<div><span>${k}</span><span>${escapeHtml(v)}</span></div>`)
    .join("");
  showScreen(3);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

els.enrollAnother.addEventListener("click", () => {
  state.fullName = "";
  state.studentNo = "";
  state.photos = [null, null, null];
  state.active = 0;
  els.fullName.value = "";
  els.studentNo.value = "";
  els.consent.checked = false;
  showError(els.scanError, "");
  renderSlots();
  showScreen(1);
});

// init
renderSlots();
showScreen(1);
