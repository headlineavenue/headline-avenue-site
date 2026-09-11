// Headline Avenue editorial gating UI v1.
// REVIEW headlines can be saved and packaged, but cannot move to Publish until
// the wording is revised to SourceGuard-ready or explicitly editor-approved.
document.addEventListener("DOMContentLoaded", () => {
  const runtime = window.HeadlineAvenueRuntime || (window.HeadlineAvenueRuntime = {});
  const localHosts = new Set(["localhost", "127.0.0.1"]);
  const API_BASE = localHosts.has(window.location.hostname)
    ? "http://127.0.0.1:8000/api/v1"
    : "";
  const fetcher = window.__haNativeFetch || window.fetch.bind(window);

  let lastFingerprint = "";
  let syncTimer = null;
  let syncing = false;

  function showToast(message) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2600);
  }

  function ensureStyles() {
    if (document.getElementById("ha-editorial-gate-styles")) return;
    const style = document.createElement("style");
    style.id = "ha-editorial-gate-styles";
    style.textContent = `
      .ha-editorial-gate{margin:0 0 10px;border:1px solid #183249;border-radius:10px;background:#06111c;padding:11px 12px;font-size:11px;line-height:1.45;color:#8fa7bd}
      .ha-editorial-gate[hidden]{display:none!important}
      .ha-editorial-gate strong{display:block;margin-bottom:3px;color:#eef8ff;font-size:12px}
      .ha-editorial-gate.ready{border-color:rgba(45,210,153,.28);background:rgba(6,33,29,.42)}
      .ha-editorial-gate.ready strong{color:#54e2ad}
      .ha-editorial-gate.blocked{border-color:rgba(255,191,48,.30);background:rgba(38,28,5,.48)}
      .ha-editorial-gate.blocked strong{color:#ffd34d}
      .ha-editorial-gate.approved{border-color:rgba(64,196,255,.34);background:rgba(4,29,45,.55)}
      .ha-editorial-gate.approved strong{color:#57d9ff}
      .ha-gate-reason{margin-top:5px;color:#d4bd7d}
      .ha-gate-approval{margin-top:9px;padding-top:9px;border-top:1px solid rgba(255,255,255,.07)}
      .ha-gate-approval textarea{box-sizing:border-box;width:100%;min-height:54px;resize:vertical;border:1px solid #17334a;border-radius:7px;background:#020912;color:#ddecf7;padding:8px;font:inherit;outline:none}
      .ha-gate-approval textarea:focus{border-color:#18bff0}
      .ha-gate-approval button{margin-top:7px;width:100%;border:1px solid #32677f;border-radius:7px;background:#082638;color:#8ce8ff;padding:8px 9px;font-weight:700;cursor:pointer}
      .ha-gate-approval button:disabled{opacity:.5;cursor:wait}
      #send-to-publish.ha-publish-blocked{background:#182230!important;color:#7f93a8!important;border-color:#293847!important;cursor:not-allowed!important;box-shadow:none!important}
      .pack-item .ha-pack-review{color:#ffd34d!important}
      .pack-item .ha-pack-approved{color:#57d9ff!important}
    `;
    document.head.appendChild(style);
  }

  function ensureGateBox() {
    const stack = document.querySelector("#story-workspace .story-action-stack");
    const send = document.getElementById("send-to-publish");
    if (!stack || !send) return null;

    let box = document.getElementById("ha-editorial-gate");
    if (!box) {
      box = document.createElement("div");
      box.id = "ha-editorial-gate";
      box.className = "ha-editorial-gate";
      stack.insertBefore(box, send);
    }
    return box;
  }

  function packExists() {
    const state = (document.getElementById("story-pack-state")?.textContent || "").toLowerCase();
    const list = document.getElementById("pack-list");
    const hasRows = Boolean(list && !list.querySelector(".empty-pack") && list.children.length);
    return state.includes("ready") || state.includes("review") || state.includes("approved") || hasRows;
  }

  function syncPackLabels(status) {
    if (!packExists()) return;
    document.querySelectorAll("#pack-list .pack-item span").forEach(label => {
      label.classList.remove("ha-pack-review", "ha-pack-approved");
      if (status === "review_required") {
        label.textContent = "Review required";
        label.classList.add("ha-pack-review");
      } else if (status === "approved") {
        label.textContent = "Editor approved ✓";
        label.classList.add("ha-pack-approved");
      } else if (status === "ready") {
        label.textContent = "Ready ✓";
      }
    });
  }

  function syncPublishUi(gate) {
    const send = document.getElementById("send-to-publish");
    if (!send) return;

    const status = gate?.status || "headline_required";
    const canPublish = Boolean(gate?.can_publish);
    const hasPack = packExists();
    const shouldBlock = !canPublish || !hasPack;

    send.classList.toggle("ha-publish-blocked", shouldBlock);
    send.dataset.haGateBlocked = !canPublish ? "1" : "0";

    if (!canPublish) {
      send.disabled = true;
      send.textContent = status === "review_required"
        ? "Publish blocked — review required"
        : "Choose headline before publish";
    } else if (!hasPack) {
      send.disabled = true;
      send.textContent = "Generate Story Pack first";
    } else {
      send.disabled = false;
      send.classList.remove("ha-publish-blocked");
      send.dataset.haGateBlocked = "0";
      send.textContent = "Send to Publish →";
    }

    const packState = document.getElementById("story-pack-state");
    if (packState && hasPack) {
      if (status === "review_required") {
        packState.textContent = "Review required";
        packState.classList.remove("verified-text");
      } else if (status === "approved") {
        packState.textContent = "Editor approved";
        packState.classList.add("verified-text");
      } else if (status === "ready") {
        packState.textContent = "Ready";
        packState.classList.add("verified-text");
      }
    }

    syncPackLabels(status);
  }

  function renderGate(gate) {
    runtime.editorialGate = gate;
    const box = ensureGateBox();
    const send = document.getElementById("send-to-publish");
    if (!box || !send) return;

    const status = gate?.status || "headline_required";
    const blockers = Array.isArray(gate?.blockers) ? gate.blockers : [];
    const score = Number.isFinite(Number(gate?.grounding_score)) ? Number(gate.grounding_score) : null;
    const approval = gate?.approval || null;

    box.className = "ha-editorial-gate";

    if (status === "ready") {
      box.classList.add("ready");
      box.innerHTML = `<strong>✓ SourceGuard ready for publish</strong>${score !== null ? `${score}% lexical grounding · ` : ""}No unresolved editorial gate.`;
    } else if (status === "approved") {
      box.classList.add("approved");
      const who = approval?.approved_by ? ` by ${escapeHtml(approval.approved_by)}` : "";
      box.innerHTML = `<strong>✓ Editor-approved review</strong>This headline remains a review override${who}. The approval stays attached to the editorial selection.`;
    } else if (status === "review_required") {
      box.classList.add("blocked");
      box.innerHTML = `
        <strong>⚠ Publish blocked — SourceGuard review required</strong>
        This wording may be saved and packaged for review, but it cannot move directly to Publish.
        ${blockers.length ? `<div class="ha-gate-reason">${escapeHtml(blockers[0])}</div>` : ""}
        <div class="ha-gate-approval">
          <textarea id="ha-approval-note" maxlength="500" placeholder="Add the reason or supporting context for an editor override…"></textarea>
          <button id="ha-approve-editorial" type="button">Approve as editor →</button>
        </div>`;
    } else {
      box.classList.add("blocked");
      box.innerHTML = `<strong>Choose a headline before publishing</strong>Select a Headline Lab option first. Story Packs can still be built as working drafts.`;
    }

    syncPublishUi(gate);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function fetchGate() {
    if (!API_BASE || !runtime.storyId || syncing) return;
    syncing = true;
    try {
      const response = await fetcher(`${API_BASE}/stories/${encodeURIComponent(runtime.storyId)}/editorial/gate`, {
        headers: { "Accept": "application/json" }
      });
      if (!response.ok) return;
      const gate = await response.json();
      const fingerprint = JSON.stringify(gate);
      if (fingerprint !== lastFingerprint || !document.getElementById("ha-editorial-gate")) {
        lastFingerprint = fingerprint;
        renderGate(gate);
      } else {
        // The gate payload can stay identical while the Story Pack DOM changes
        // from Waiting -> Ready. Always resync the publish controls so an
        // editor-approved story unlocks as soon as generated assets exist.
        runtime.editorialGate = gate;
        syncPublishUi(gate);
      }
    } catch (error) {
      console.debug("Editorial gate check skipped:", error);
    } finally {
      syncing = false;
    }
  }

  function scheduleSync(delay = 120) {
    if (syncTimer) window.clearTimeout(syncTimer);
    syncTimer = window.setTimeout(fetchGate, delay);
  }

  async function approveAsEditor() {
    if (!API_BASE || !runtime.storyId) return;
    const note = document.getElementById("ha-approval-note")?.value.trim() || "";
    if (note.length < 5) {
      showToast("Add a short approval reason first.");
      return;
    }

    const button = document.getElementById("ha-approve-editorial");
    const original = button?.textContent;
    if (button) {
      button.disabled = true;
      button.textContent = "Approving…";
    }

    try {
      const response = await fetcher(`${API_BASE}/stories/${encodeURIComponent(runtime.storyId)}/editorial/approve`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ note, approved_by: "Headline Avenue editor" })
      });
      if (!response.ok) {
        let detail = "";
        try { detail = (await response.json())?.detail || ""; } catch {}
        throw new Error(detail || `API ${response.status}`);
      }
      const gate = await response.json();
      lastFingerprint = "";
      renderGate(gate);
      showToast("Review override approved and attached to the story.");
    } catch (error) {
      console.error("Editorial approval failed:", error);
      showToast("Approval failed — " + error.message);
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = original || "Approve as editor →";
      }
    }
  }

  ensureStyles();

  document.addEventListener("click", event => {
    const approval = event.target.closest("#ha-approve-editorial");
    if (approval) {
      event.preventDefault();
      approveAsEditor();
      return;
    }

    const send = event.target.closest("#send-to-publish");
    if (send && send.dataset.haGateBlocked === "1") {
      event.preventDefault();
      event.stopImmediatePropagation();
      const gate = runtime.editorialGate;
      showToast(gate?.status === "review_required"
        ? "Publish blocked — resolve SourceGuard review or add editor approval."
        : "Choose and save a headline before publishing.");
      return;
    }

    if (event.target.closest("[data-use-editorial], #generate-pack")) {
      scheduleSync(500);
      window.setTimeout(() => scheduleSync(50), 1100);
    }
  }, true);

  window.addEventListener("ha:story-created", () => {
    lastFingerprint = "";
    window.setTimeout(() => scheduleSync(50), 250);
  });

  const workspace = document.getElementById("story-workspace");
  if (workspace) {
    const observer = new MutationObserver(mutations => {
      const meaningful = mutations.some(mutation => {
        const target = mutation.target instanceof Element ? mutation.target : mutation.target.parentElement;
        return target && !target.closest("#ha-editorial-gate");
      });
      if (meaningful && runtime.storyId) scheduleSync(180);
    });
    observer.observe(workspace, { childList: true, subtree: true, characterData: true });
  }

  scheduleSync(400);
});
