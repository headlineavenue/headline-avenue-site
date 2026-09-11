// Headline Avenue Story Workspace -> Publish desk bridge.
// Creates a backend-backed publish draft from the exact active Story Pack and
// overlays that live draft onto the existing distribution-desk prototype UI.
document.addEventListener("DOMContentLoaded", () => {
  const localHosts = new Set(["localhost", "127.0.0.1"]);
  if (!localHosts.has(window.location.hostname)) return;

  const runtime = window.HeadlineAvenueRuntime || (window.HeadlineAvenueRuntime = {});
  const fetcher = window.__haNativeFetch || window.fetch.bind(window);
  const API_BASE = "http://127.0.0.1:8000/api/v1";
  const DRAFT_KEY = "headline-avenue.publish-draft.v1";
  const WORKSPACE_KEY = "headline-avenue.active-workspace.v1";

  function showToast(message) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function readJson(key) {
    try {
      const raw = window.sessionStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function saveDraft(draft) {
    try { window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft)); } catch {}
    runtime.publishDraft = draft;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function prettyFormat(value) {
    return String(value || "")
      .replace(/_/g, " ")
      .replace(/^9:16 video$/i, "9:16 video")
      .replace(/^16:9 video$/i, "16:9 video")
      .replace(/\b\w/g, char => char.toUpperCase());
  }

  function formatSummary(formats) {
    const list = Array.isArray(formats) ? formats.filter(Boolean) : [];
    const primary = list.find(item => String(item).includes("9:16"))
      || list.find(item => String(item).includes("16:9"))
      || list[0]
      || "Story Pack";
    return prettyFormat(primary);
  }

  function normalizeSavedFormats(values) {
    const map = {
      "9:16": "9:16_video",
      "9:16 Video": "9:16_video",
      "16:9": "16:9_video",
      "16:9 Video": "16:9_video",
      "1:1": "1:1_video",
      "1:1 Video": "1:1_video",
      "4:5": "4:5_video",
      "4:5 Video": "4:5_video",
      "Article": "article",
      "Carousel": "carousel",
      "Newsletter": "newsletter",
      "Thread": "thread",
      "Headline": "headline",
      "Summary": "summary",
      "Source Trail": "source_trail",
      "Platform Copy": "platform_copy"
    };
    return [...new Set((Array.isArray(values) ? values : [])
      .map(value => map[String(value).trim()] || String(value).trim().toLowerCase().replace(/\s+/g, "_"))
      .filter(Boolean))];
  }

  function inspectorCheck(draft) {
    const first = document.querySelector(".publish-checks > div:first-child");
    if (!first) return;
    const title = first.querySelector("b");
    const note = first.querySelector("small");
    if (draft.editorial_status === "approved") {
      if (title) title.textContent = "Editor-approved SourceGuard review";
      if (note) note.textContent = "Review override is attached to this Story Pack";
    } else {
      if (title) title.textContent = "SourceGuard passed";
      if (note) note.textContent = "Headline is source-aligned and publish-ready";
    }
  }

  function renderDraft(draft) {
    if (!draft?.id) return;
    saveDraft(draft);

    const list = document.getElementById("publish-job-list");
    if (list) {
      let row = document.getElementById("ha-live-publish-job");
      if (!row) {
        row = document.createElement("article");
        row.id = "ha-live-publish-job";
        list.prepend(row);
      }

      row.className = "publish-job selected";
      row.dataset.publishStatus = "draft";
      row.dataset.jobTitle = draft.headline || "Current Story Pack";
      row.dataset.jobPlatforms = "Not assigned";
      row.dataset.jobTime = "Not scheduled";
      row.innerHTML = `
        <div class="publish-thumb"><span>HA</span><small>LIVE</small></div>
        <div class="publish-job-copy">
          <b>${escapeHtml(draft.headline || "Current Story Pack")}</b>
          <small>${escapeHtml(draft.source_label || "Indexed source")} · ${escapeHtml(formatSummary(draft.formats))}</small>
          <div><span class="queue-badge draft">Backend draft</span><em>${Array.isArray(draft.formats) ? draft.formats.length : 0} assets</em></div>
        </div>
        <div class="publish-platform-dots"><span class="platform-dot yt">YT</span><span class="platform-dot ig">IG</span></div>
        <div class="publish-job-time"><b>Not scheduled</b><small>Created just now</small></div>
        <button class="publish-open" type="button" data-ha-live-publish-open>Review →</button>`;

      document.querySelectorAll(".publish-job").forEach(job => job.classList.toggle("selected", job === row));
      row.hidden = false;
      row.querySelector("[data-ha-live-publish-open]")?.addEventListener("click", () => renderDraft(draft));
    }

    const inspectorState = document.querySelector(".publish-inspector .inspector-state");
    if (inspectorState) {
      inspectorState.textContent = draft.editorial_status === "approved" ? "EDITOR APPROVED" : "READY";
    }

    const title = document.getElementById("publish-title-input");
    if (title) title.value = draft.headline || "";

    const caption = document.getElementById("publish-caption-input");
    if (caption) caption.value = draft.caption || "";

    const previewHook = document.querySelector(".publish-preview .preview-hook");
    if (previewHook) previewHook.textContent = String(draft.headline || "Current Story Pack").toUpperCase();

    const previewCaption = document.querySelector(".publish-preview .preview-caption");
    if (previewCaption) {
      const text = String(draft.caption || draft.headline || "").replace(/\s+/g, " ").trim();
      previewCaption.textContent = text.length > 110 ? text.slice(0, 107) + "…" : text;
    }

    const previewMeta = document.querySelectorAll(".publish-preview .preview-meta span");
    if (previewMeta[0]) previewMeta[0].textContent = `${formatSummary(draft.formats)} · Story Pack`;
    if (previewMeta[1]) previewMeta[1].textContent = `${Array.isArray(draft.formats) ? draft.formats.length : 0} assets`;

    inspectorCheck(draft);

    let liveNote = document.getElementById("ha-live-draft-note");
    const inspector = document.querySelector(".publish-inspector");
    if (!liveNote && inspector) {
      liveNote = document.createElement("div");
      liveNote.id = "ha-live-draft-note";
      liveNote.style.cssText = "margin:0 0 10px;padding:9px 10px;border:1px solid rgba(64,196,255,.28);border-radius:8px;background:rgba(4,29,45,.5);color:#8ce8ff;font-size:11px;line-height:1.4";
      const preview = inspector.querySelector(".publish-preview");
      if (preview) inspector.insertBefore(liveNote, preview);
    }
    if (liveNote) {
      liveNote.innerHTML = `<b>LIVE BACKEND DRAFT</b><br>${escapeHtml(draft.editorial_status === "approved" ? "Editor-approved review attached" : "SourceGuard-ready editorial selection")}`;
    }
  }

  function openPublishView() {
    const nav = document.querySelector('.app-nav button[data-view="publish"]');
    if (nav) nav.click();
    const draftTab = document.querySelector('[data-publish-tab="draft"]');
    if (draftTab) draftTab.click();
  }

  async function apiJson(url, options = {}) {
    const response = await fetcher(url, options);
    if (!response.ok) {
      let detail = "";
      try { detail = (await response.json())?.detail || ""; } catch {}
      const error = new Error(detail || `API ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  async function createDraftFromStory(storyId) {
    return apiJson(`${API_BASE}/publishing/drafts/from-story/${encodeURIComponent(storyId)}`, {
      method: "POST",
      headers: { "Accept": "application/json", "Content-Type": "application/json" }
    });
  }

  async function getLatestDraft(storyId) {
    return apiJson(`${API_BASE}/publishing/drafts/${encodeURIComponent(storyId)}`, {
      headers: { "Accept": "application/json" }
    });
  }

  async function generateSavedPack(storyId, workspaceState) {
    const formats = normalizeSavedFormats(workspaceState?.outputs);
    if (!formats.length) throw new Error("Generate a Story Pack before moving to Publish");

    return apiJson(`${API_BASE}/story-packs/generate`, {
      method: "POST",
      headers: { "Accept": "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ story_id: storyId, formats })
    });
  }

  async function recoverOrCreateDraft(storyId, workspaceState) {
    // Prefer an existing backend draft if browser session storage was lost.
    try {
      return await getLatestDraft(storyId);
    } catch (error) {
      if (error.status !== 404) console.debug("Existing publish draft lookup skipped:", error);
    }

    try {
      return await createDraftFromStory(storyId);
    } catch (error) {
      // Older restored workspaces could display a Story Pack that app-core had
      // regenerated only in the DOM because its private currentStoryId was lost
      // on refresh. Recreate those exact saved formats in the backend once,
      // then retry the publish handoff.
      if (!String(error.message || "").includes("Generate a Story Pack")) throw error;
      await generateSavedPack(storyId, workspaceState);
      return createDraftFromStory(storyId);
    }
  }

  async function handoffToPublish(button) {
    const storyId = runtime.storyId;
    if (!storyId) {
      showToast("No active backend Story to send to Publish.");
      return;
    }

    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Moving to Publish…";

    try {
      const draft = await recoverOrCreateDraft(storyId, readJson(WORKSPACE_KEY));
      saveDraft(draft);
      openPublishView();
      window.requestAnimationFrame(() => renderDraft(draft));
      showToast("Current Story Pack loaded into Publish");
    } catch (error) {
      console.error("Publish handoff failed:", error);
      showToast("Publish handoff failed — " + error.message);
      button.disabled = false;
      button.textContent = original || "Send to Publish →";
    }
  }

  // Run before app-core's prototype handler. The editorial gating listener is
  // registered earlier and still gets first say when a Story is blocked.
  document.addEventListener("click", event => {
    const send = event.target.closest("#send-to-publish");
    if (!send || send.disabled || send.dataset.haGateBlocked === "1") return;
    event.preventDefault();
    event.stopImmediatePropagation();
    handoffToPublish(send);
  }, true);

  document.querySelectorAll("[data-publish-tab]").forEach(tab => {
    tab.addEventListener("click", () => {
      window.setTimeout(() => {
        const live = document.getElementById("ha-live-publish-job");
        if (live) live.hidden = tab.dataset.publishTab !== "draft";
      }, 0);
    });
  });

  document.querySelector('.app-nav button[data-view="publish"]')?.addEventListener("click", () => {
    const saved = readJson(DRAFT_KEY);
    if (saved) window.setTimeout(() => renderDraft(saved), 0);
  });

  // If Publish was active before a refresh, restore the exact backend Story
  // Pack. If an older refresh left the pack only in the UI, the recovery path
  // persists those saved formats first and then creates the live draft.
  const workspaceState = readJson(WORKSPACE_KEY);
  const savedDraft = readJson(DRAFT_KEY);
  if (workspaceState?.activeView === "publish") {
    window.setTimeout(async () => {
      try {
        openPublishView();
        if (savedDraft) {
          renderDraft(savedDraft);
          return;
        }
        if (workspaceState.storyId) {
          runtime.storyId = workspaceState.storyId;
          runtime.sourceId = workspaceState.sourceId || runtime.sourceId || null;
          const draft = await recoverOrCreateDraft(workspaceState.storyId, workspaceState);
          renderDraft(draft);
          showToast("Publish draft restored from backend");
        }
      } catch (error) {
        console.error("Publish restore failed:", error);
        showToast("Could not restore the live Publish draft — " + error.message);
      }
    }, 0);
  }
});
