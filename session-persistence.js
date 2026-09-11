// Headline Avenue Story Workspace session persistence.
// Keeps the active local Story Workspace alive across F5 / hard refreshes while
// using the backend as the source of truth for the Story, source, analysis and gate.
document.addEventListener("DOMContentLoaded", () => {
  const localHosts = new Set(["localhost", "127.0.0.1"]);
  if (!localHosts.has(window.location.hostname)) return;

  const runtime = window.HeadlineAvenueRuntime || (window.HeadlineAvenueRuntime = {});
  const fetcher = window.__haNativeFetch || window.fetch.bind(window);
  const API_BASE = "http://127.0.0.1:8000/api/v1";
  const SESSION_KEY = "headline-avenue.active-workspace.v1";
  const bootState = readState();
  let restoring = false;
  let captureTimer = null;

  function readState() {
    try {
      const raw = window.sessionStorage.getItem(SESSION_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function writeState(patch = {}) {
    try {
      const next = { ...readState(), ...patch, savedAt: Date.now() };
      window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
      return next;
    } catch (error) {
      console.debug("Workspace session could not be saved.", error);
      return {};
    }
  }

  function clearState() {
    try { window.sessionStorage.removeItem(SESSION_KEY); } catch {}
  }

  function activeViewName() {
    if (document.getElementById("story-workspace")?.classList.contains("active")) return "workspace";
    const view = document.querySelector(".app-view.active");
    return view?.id?.replace(/^view-/, "") || "home";
  }

  function packOutputsFromDom() {
    return [...document.querySelectorAll("#pack-list .pack-item b")]
      .map(node => node.textContent.trim())
      .filter(Boolean);
  }

  function captureWorkspaceState() {
    if (restoring) return;

    const activeView = activeViewName();
    const patch = { activeView };

    if (runtime.storyId) patch.storyId = runtime.storyId;
    if (runtime.sourceId) patch.sourceId = runtime.sourceId;

    if (activeView === "workspace" || runtime.storyId) {
      const storyTitle = document.getElementById("story-title")?.textContent?.trim();
      const sourceLabel = document.getElementById("story-source-label")?.textContent?.trim();
      const outputs = packOutputsFromDom();
      const packState = document.getElementById("story-pack-state")?.textContent?.trim();

      if (storyTitle) patch.storyTitle = storyTitle;
      if (sourceLabel) patch.sourceLabel = sourceLabel;
      patch.outputs = outputs;
      if (packState) patch.packState = packState;
    }

    writeState(patch);
  }

  function scheduleCapture(delay = 80) {
    if (captureTimer) window.clearTimeout(captureTimer);
    captureTimer = window.setTimeout(captureWorkspaceState, delay);
  }

  function prettyOutput(value) {
    return String(value || "")
      .replace(/_/g, " ")
      .replace(/^\d+:\d+ video$/i, match => match.replace(" video", ""))
      .replace(/\b\w/g, character => character.toUpperCase());
  }

  function restorePack(outputs, packState) {
    if (!Array.isArray(outputs) || !outputs.length) return;

    const list = document.getElementById("pack-list");
    if (list) {
      list.innerHTML = outputs.map(output =>
        `<div class="pack-item"><b>${prettyOutput(output)}</b><span>Ready ✓</span></div>`
      ).join("");
    }

    const count = document.getElementById("story-output-count");
    if (count) count.textContent = String(outputs.length);

    const state = document.getElementById("story-pack-state");
    if (state) {
      state.textContent = packState || "Ready";
      state.classList.add("verified-text");
    }
  }

  function deriveSourceLabel(source, fallback = "") {
    if (fallback) return fallback;
    if (!source) return "Indexed source";
    const kind = String(source.kind || "source");
    const label = kind.charAt(0).toUpperCase() + kind.slice(1);
    if (source.original_url) return `${label} · ${source.original_url}`;
    if (source.transcript_text) return `Transcript · ${source.transcript_text.length.toLocaleString()} characters`;
    return source.title ? `${label} · ${source.title}` : "Indexed source";
  }

  function showRestoredToast() {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = "Story Workspace restored";
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 1800);
  }

  async function apiJson(path) {
    const response = await fetcher(`${API_BASE}${path}`, {
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return response.json();
  }

  async function restoreWorkspace() {
    if (!bootState?.storyId || bootState.activeView !== "workspace") return false;

    restoring = true;
    try {
      const story = await apiJson(`/stories/${encodeURIComponent(bootState.storyId)}`);
      const sourceId = story?.source_id || bootState.sourceId || null;
      let source = null;

      if (sourceId) {
        try { source = await apiJson(`/sources/${encodeURIComponent(sourceId)}`); }
        catch (error) { console.debug("Workspace source restore skipped.", error); }
      }

      runtime.storyId = story.id;
      runtime.sourceId = sourceId;
      runtime.analysis = null;
      runtime.selectedAngle = null;
      runtime.editorialVariants = null;
      runtime.editorialSelection = null;
      runtime.editorialGate = null;

      document.querySelectorAll(".app-view").forEach(view => view.classList.remove("active"));
      document.getElementById("story-workspace")?.classList.add("active");
      document.querySelectorAll(".app-nav button").forEach(button => button.classList.remove("active"));

      const viewTitle = document.getElementById("view-title");
      if (viewTitle) viewTitle.textContent = "Story Workspace";

      const storyTitle = bootState.storyTitle || story.title || "Story Workspace";
      const sourceLabel = deriveSourceLabel(source, bootState.sourceLabel || "");
      const storyTitleNode = document.getElementById("story-title");
      const sourceLabelNode = document.getElementById("story-source-label");
      if (storyTitleNode) storyTitleNode.textContent = storyTitle;
      if (sourceLabelNode) sourceLabelNode.textContent = sourceLabel;

      const save = document.getElementById("save-story");
      if (save) save.textContent = "Saved ✓";

      restorePack(bootState.outputs, bootState.packState);

      writeState({
        activeView: "workspace",
        storyId: story.id,
        sourceId,
        storyTitle,
        sourceLabel,
        outputs: Array.isArray(bootState.outputs) ? bootState.outputs : []
      });

      // Re-run the normal intelligence stack against the persisted Story. The
      // backend restores the authoritative editorial gate / editor approval.
      window.setTimeout(() => {
        window.dispatchEvent(new CustomEvent("ha:story-created", { detail: story }));
        showRestoredToast();
      }, 0);
      return true;
    } catch (error) {
      console.warn("Stored Story Workspace could not be restored.", error);
      clearState();
      return false;
    } finally {
      restoring = false;
    }
  }

  window.addEventListener("ha:story-created", event => {
    const story = event.detail || {};
    const storyId = story.id || runtime.storyId;
    if (!storyId) return;

    runtime.storyId = storyId;
    runtime.sourceId = story.source_id || runtime.sourceId || null;
    writeState({
      activeView: "workspace",
      storyId,
      sourceId: runtime.sourceId,
      storyTitle: document.getElementById("story-title")?.textContent?.trim() || story.title || "Story Workspace",
      sourceLabel: document.getElementById("story-source-label")?.textContent?.trim() || "Indexed source",
      outputs: []
    });
    scheduleCapture(120);
  });

  document.querySelectorAll(".app-nav button").forEach(button => {
    button.addEventListener("click", () => {
      writeState({ activeView: button.dataset.view || "home" });
    }, true);
  });

  const startObservers = () => {
    const root = document.querySelector("main") || document.body;
    const observer = new MutationObserver(() => scheduleCapture());
    observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["class"] });

    window.addEventListener("beforeunload", captureWorkspaceState);
  };

  restoreWorkspace().finally(startObservers);
});
