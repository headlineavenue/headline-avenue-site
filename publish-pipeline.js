// Headline Avenue controlled publishing pipeline.
// Adds backend preflight, final confirmation, durable per-platform jobs,
// duplicate protection, and a tamper-evident dispatch fingerprint.
document.addEventListener("DOMContentLoaded", () => {
  const localHosts = new Set(["localhost", "127.0.0.1"]);
  if (!localHosts.has(window.location.hostname)) return;

  const runtime = window.HeadlineAvenueRuntime || (window.HeadlineAvenueRuntime = {});
  const fetcher = window.__haNativeFetch || window.fetch.bind(window);
  const API_BASE = "http://127.0.0.1:8000/api/v1";
  const DISPATCH_KEY = "headline-avenue.publish-dispatch.v1";

  injectStyles();

  function showToast(message, timeout = 2600) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), timeout);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function apiJson(url, options = {}) {
    const response = await fetcher(url, options);
    if (!response.ok) {
      let detail = "";
      try {
        const body = await response.json();
        detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail || body);
      } catch {
        try { detail = await response.text(); } catch {}
      }
      const error = new Error(detail || `API ${response.status}`);
      error.status = response.status;
      throw error;
    }
    if (response.status === 204) return null;
    return response.json();
  }

  function getDraft() {
    if (runtime.publishDraft?.id) return runtime.publishDraft;
    try {
      const raw = sessionStorage.getItem("headline-avenue.publish-draft.v1");
      const draft = raw ? JSON.parse(raw) : null;
      if (draft?.id) {
        runtime.publishDraft = draft;
        return draft;
      }
    } catch {}
    return null;
  }

  function selectedDestinations() {
    return [...document.querySelectorAll("[data-publish-destination]:checked")].map(input => input.value);
  }

  function currentMode() {
    const active = document.querySelector("[data-schedule-mode].selected");
    return active?.dataset.scheduleMode || "now";
  }

  function scheduledAt(mode) {
    if (mode !== "later") return null;
    const date = document.getElementById("publish-date")?.value;
    const time = document.getElementById("publish-time")?.value;
    if (!date || !time) return null;
    const value = new Date(`${date}T${time}`);
    if (Number.isNaN(value.getTime())) return null;
    return value.toISOString();
  }

  function buildPlan() {
    const mode = currentMode();
    return {
      destinations: selectedDestinations(),
      mode,
      scheduled_at: scheduledAt(mode),
      title: document.getElementById("publish-title-input")?.value || "",
      caption: document.getElementById("publish-caption-input")?.value || ""
    };
  }

  function platformLabel(value) {
    const key = String(value || "").toLowerCase();
    return { youtube: "YouTube", instagram: "Instagram", tiktok: "TikTok" }[key] || value;
  }

  function timingLabel(preflight) {
    if (preflight.mode === "later" && preflight.scheduled_at) {
      const date = new Date(preflight.scheduled_at);
      return `Scheduled · ${date.toLocaleString()}`;
    }
    return "Queue immediately after confirmation";
  }

  function statusIcon(status) {
    if (status === "pass") return "✓";
    if (status === "warn") return "!";
    return "×";
  }

  function renderPreflightModal(preflight, plan) {
    document.getElementById("ha-preflight-modal")?.remove();
    const overlay = document.createElement("div");
    overlay.id = "ha-preflight-modal";
    overlay.className = "ha-preflight-overlay";
    overlay.innerHTML = `
      <section class="ha-preflight-dialog" role="dialog" aria-modal="true" aria-labelledby="ha-preflight-title">
        <header class="ha-preflight-head">
          <div>
            <span class="ha-preflight-kicker">DISTRIBUTION / FINAL CHECK</span>
            <h2 id="ha-preflight-title">Final distribution preflight</h2>
            <p>Headline Avenue re-checks the exact approved snapshot before platform jobs can be created.</p>
          </div>
          <button class="ha-preflight-close" type="button" aria-label="Close">×</button>
        </header>

        <div class="ha-preflight-story">
          <div class="ha-preflight-story-copy">
            <span>APPROVED STORY SNAPSHOT</span>
            <strong>${escapeHtml(plan.title || "Untitled story")}</strong>
            <small>${escapeHtml(preflight.destinations.map(platformLabel).join(" + ") || "No destination")} · ${escapeHtml(timingLabel(preflight))}</small>
          </div>
          <div class="ha-fingerprint"><span>AUDIT FINGERPRINT</span><b>${escapeHtml(preflight.fingerprint)}</b></div>
        </div>

        <div class="ha-preflight-checks">
          ${preflight.checks.map(check => `
            <article class="ha-preflight-check ${escapeHtml(check.status)}">
              <i>${statusIcon(check.status)}</i>
              <div><b>${escapeHtml(check.label)}</b><small>${escapeHtml(check.detail)}</small></div>
            </article>`).join("")}
        </div>

        <div class="ha-queue-notice">
          <b>Controlled queue mode</b>
          <span>This confirmation creates durable per-platform jobs and an immutable dispatch snapshot. External provider delivery is not enabled yet, so nothing leaves Headline Avenue in this build.</span>
        </div>

        <footer class="ha-preflight-actions">
          <button type="button" class="ha-preflight-back">Back to inspector</button>
          <button type="button" class="ha-preflight-confirm" ${preflight.can_dispatch ? "" : "disabled"}>
            ${preflight.can_dispatch ? `Confirm & queue ${preflight.destinations.length} deliver${preflight.destinations.length === 1 ? "y" : "ies"} →` : "Resolve blocking checks first"}
          </button>
        </footer>
      </section>`;

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add("show"));

    const close = () => {
      overlay.classList.remove("show");
      window.setTimeout(() => overlay.remove(), 150);
    };

    overlay.querySelector(".ha-preflight-close")?.addEventListener("click", close);
    overlay.querySelector(".ha-preflight-back")?.addEventListener("click", close);
    overlay.addEventListener("click", event => { if (event.target === overlay) close(); });

    const confirm = overlay.querySelector(".ha-preflight-confirm");
    confirm?.addEventListener("click", async () => {
      if (!preflight.can_dispatch) return;
      const draft = getDraft();
      if (!draft?.id) return;

      const original = confirm.textContent;
      confirm.disabled = true;
      confirm.textContent = "Creating delivery jobs…";
      try {
        const result = await apiJson(`${API_BASE}/publishing/drafts/${encodeURIComponent(draft.id)}/dispatch`, {
          method: "POST",
          headers: { "Accept": "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ ...plan, confirmed: true })
        });
        try { sessionStorage.setItem(DISPATCH_KEY, JSON.stringify(result)); } catch {}
        close();
        decorateDispatch(result);
        showToast(result.status === "scheduled" ? "Distribution jobs scheduled" : "Distribution jobs queued in Headline Avenue");
      } catch (error) {
        console.error("Publish dispatch failed:", error);
        confirm.disabled = false;
        confirm.textContent = original;
        showToast("Distribution blocked — " + error.message, 4200);
      }
    });
  }

  async function runPreflight() {
    const draft = getDraft();
    if (!draft?.id) {
      showToast("Load a live backend draft before publishing.");
      return;
    }

    const plan = buildPlan();
    if (plan.mode === "draft") {
      showToast("This backend draft is already saved. Choose Now or Schedule when you are ready to distribute.");
      return;
    }

    const submit = document.getElementById("publisher-submit");
    const original = submit?.textContent;
    if (submit) {
      submit.disabled = true;
      submit.textContent = "Running preflight…";
    }

    try {
      const preflight = await apiJson(`${API_BASE}/publishing/drafts/${encodeURIComponent(draft.id)}/preflight`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(plan)
      });
      renderPreflightModal(preflight, plan);
    } catch (error) {
      console.error("Publish preflight failed:", error);
      showToast("Preflight failed — " + error.message, 4200);
    } finally {
      if (submit) {
        submit.disabled = false;
        submit.textContent = original || "Review distribution →";
      }
    }
  }

  function decorateDispatch(dispatch) {
    if (!dispatch?.jobs?.length) return;
    const status = dispatch.status === "scheduled" ? "scheduled" : "queued";
    const row = document.getElementById("ha-live-publish-job");
    if (row) {
      const badge = row.querySelector(".queue-badge");
      if (badge) {
        badge.textContent = status === "scheduled" ? "Scheduled" : "Queued";
        badge.className = `queue-badge ${status === "scheduled" ? "scheduled" : "draft"}`;
      }
      const time = row.querySelector(".publish-job-time");
      if (time) {
        const first = time.querySelector("b");
        const small = time.querySelector("small");
        if (first) first.textContent = status === "scheduled" ? "Scheduled" : "Queued";
        if (small) small.textContent = dispatch.jobs.map(job => `${platformLabel(job.platform)} ${job.status}`).join(" · ");
      }
    }

    const state = document.querySelector(".publish-inspector .inspector-state");
    if (state) state.textContent = status.toUpperCase();

    let note = document.getElementById("ha-dispatch-status");
    const inspector = document.querySelector(".publish-inspector");
    if (!note && inspector) {
      note = document.createElement("div");
      note.id = "ha-dispatch-status";
      note.className = "ha-dispatch-status";
      const checks = inspector.querySelector(".publish-checks");
      if (checks) inspector.insertBefore(note, checks);
      else inspector.appendChild(note);
    }
    if (note) {
      note.innerHTML = `<b>${status === "scheduled" ? "SCHEDULED DISTRIBUTION" : "DISTRIBUTION QUEUED"}</b>
        <span>${dispatch.jobs.map(job => `${escapeHtml(platformLabel(job.platform))}: ${escapeHtml(job.status)}`).join(" · ")}</span>
        <small>Audit ${escapeHtml(dispatch.fingerprint)} · backend queue</small>`;
    }

    const submit = document.getElementById("publisher-submit");
    if (submit) {
      submit.disabled = true;
      submit.textContent = status === "scheduled" ? `Scheduled to ${dispatch.jobs.length} destinations ✓` : `Queued to ${dispatch.jobs.length} destinations ✓`;
    }
  }

  async function restoreDispatchState() {
    const draft = getDraft();
    if (!draft?.story_id) return;
    try {
      const result = await apiJson(`${API_BASE}/publishing/jobs/${encodeURIComponent(draft.story_id)}`, {
        headers: { "Accept": "application/json" }
      });
      const active = (result.jobs || []).filter(job => ["queued", "scheduled", "publishing"].includes(job.status));
      if (!active.length) return;
      decorateDispatch({
        status: active.some(job => job.status === "scheduled") ? "scheduled" : "queued",
        fingerprint: readStoredFingerprint(),
        jobs: active
      });
    } catch (error) {
      console.debug("Publish job restore skipped:", error);
    }
  }

  function readStoredFingerprint() {
    try {
      const raw = sessionStorage.getItem(DISPATCH_KEY);
      const data = raw ? JSON.parse(raw) : null;
      return data?.fingerprint || "PERSISTED";
    } catch {
      return "PERSISTED";
    }
  }

  document.addEventListener("click", event => {
    const submit = event.target.closest("#publisher-submit");
    if (!submit) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (!submit.disabled) runPreflight();
  }, true);

  document.addEventListener("click", event => {
    const save = event.target.closest("#publisher-save-draft");
    if (!save) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    showToast("Publish copy is snapshot-locked. Edit wording in Story Workspace so SourceGuard can review it.", 3800);
  }, true);

  document.querySelector('.app-nav button[data-view="publish"]')?.addEventListener("click", () => {
    window.setTimeout(restoreDispatchState, 120);
  });

  window.setTimeout(restoreDispatchState, 180);

  function injectStyles() {
    if (document.getElementById("ha-publish-pipeline-styles")) return;
    const style = document.createElement("style");
    style.id = "ha-publish-pipeline-styles";
    style.textContent = `
      .ha-preflight-overlay{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;padding:24px;background:rgba(0,4,9,.78);backdrop-filter:blur(10px);opacity:0;transition:opacity .15s ease}
      .ha-preflight-overlay.show{opacity:1}
      .ha-preflight-dialog{width:min(760px,96vw);max-height:90vh;overflow:auto;border:1px solid rgba(82,157,201,.28);border-radius:16px;background:linear-gradient(180deg,#071422 0%,#050c14 100%);box-shadow:0 28px 80px rgba(0,0,0,.56);color:#eaf7ff}
      .ha-preflight-head{display:flex;justify-content:space-between;gap:24px;padding:24px 24px 18px;border-bottom:1px solid rgba(108,164,196,.14)}
      .ha-preflight-head h2{margin:3px 0 6px;font-size:24px}.ha-preflight-head p{margin:0;color:#8ba8ba;font-size:12px;line-height:1.5}
      .ha-preflight-kicker{font-size:10px;letter-spacing:.12em;font-weight:800;color:#ffc928}.ha-preflight-close{border:0;background:transparent;color:#8ba8ba;font-size:26px;cursor:pointer;align-self:flex-start}
      .ha-preflight-story{display:flex;justify-content:space-between;gap:16px;margin:18px 24px;padding:15px;border:1px solid rgba(47,197,255,.2);border-radius:11px;background:rgba(8,35,52,.55)}
      .ha-preflight-story-copy{display:flex;min-width:0;flex-direction:column;gap:5px}.ha-preflight-story-copy span,.ha-fingerprint span{font-size:9px;letter-spacing:.1em;color:#5abfe9;font-weight:800}.ha-preflight-story-copy strong{font-size:15px}.ha-preflight-story-copy small{color:#86a4b5}
      .ha-fingerprint{display:flex;flex:0 0 auto;flex-direction:column;justify-content:center;align-items:flex-end;gap:4px}.ha-fingerprint b{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;color:#8ae8ff;letter-spacing:.07em}
      .ha-preflight-checks{display:grid;grid-template-columns:1fr 1fr;gap:9px;padding:0 24px}.ha-preflight-check{display:flex;gap:10px;align-items:flex-start;padding:11px;border:1px solid rgba(125,165,189,.13);border-radius:10px;background:#07111c}.ha-preflight-check i{display:grid;place-items:center;flex:0 0 22px;height:22px;border-radius:50%;font-style:normal;font-weight:900}.ha-preflight-check div{display:flex;flex-direction:column;gap:3px}.ha-preflight-check b{font-size:11px}.ha-preflight-check small{color:#819cad;line-height:1.35}.ha-preflight-check.pass i{background:rgba(46,216,157,.13);color:#4ce3aa}.ha-preflight-check.warn i{background:rgba(255,200,40,.12);color:#ffd04a}.ha-preflight-check.fail{border-color:rgba(255,102,87,.28)}.ha-preflight-check.fail i{background:rgba(255,102,87,.13);color:#ff806f}
      .ha-queue-notice{display:flex;flex-direction:column;gap:4px;margin:16px 24px 0;padding:12px 13px;border:1px solid rgba(255,200,40,.2);border-radius:10px;background:rgba(60,46,5,.18)}.ha-queue-notice b{font-size:11px;color:#ffd04a}.ha-queue-notice span{color:#9fb1bb;font-size:11px;line-height:1.45}
      .ha-preflight-actions{display:flex;justify-content:flex-end;gap:10px;padding:18px 24px 24px}.ha-preflight-actions button{min-height:40px;border-radius:9px;padding:0 16px;font-weight:800;cursor:pointer}.ha-preflight-back{border:1px solid rgba(121,164,190,.22);background:#07111c;color:#a9c1d0}.ha-preflight-confirm{border:0;background:linear-gradient(90deg,#55d8f5,#2388ff);color:#00101a;min-width:230px}.ha-preflight-confirm:disabled{cursor:not-allowed;opacity:.38}
      .ha-dispatch-status{display:flex;flex-direction:column;gap:4px;margin:10px 0;padding:10px 11px;border:1px solid rgba(70,220,165,.22);border-radius:8px;background:rgba(8,55,42,.22);color:#98f3cf;font-size:10px}.ha-dispatch-status b{font-size:10px;letter-spacing:.05em}.ha-dispatch-status span{color:#c4eee0}.ha-dispatch-status small{color:#6fa792}
      @media(max-width:720px){.ha-preflight-checks{grid-template-columns:1fr}.ha-preflight-story{flex-direction:column}.ha-fingerprint{align-items:flex-start}.ha-preflight-actions{flex-direction:column-reverse}.ha-preflight-actions button{width:100%}}
    `;
    document.head.appendChild(style);
  }
});
