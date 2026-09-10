// Headline Avenue Source Intelligence UI integration.
// Uses the v2 backend analysis as evidence-first editorial intelligence.
document.addEventListener("DOMContentLoaded", () => {
  const runtime = window.HeadlineAvenueRuntime || (window.HeadlineAvenueRuntime = {});
  const localHosts = new Set(["localhost", "127.0.0.1"]);
  const isLocal = localHosts.has(window.location.hostname);
  const API_BASE = isLocal ? "http://127.0.0.1:8000/api/v1" : "";
  let activeAnalysis = null;
  let selectedAngleIndex = 0;
  let lastAnalyzedStoryId = null;

  const escapeHtml = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const storyPanel = () => document.querySelector("#story-workspace .story-left .story-panel:first-child");
  const momentList = () => storyPanel()?.querySelector(".moment-list");
  const detectedLabel = () => storyPanel()?.querySelector(".panel-title-row > span");
  const guardPanel = () => document.querySelector("#story-workspace .sourceguard-panel");
  const guardStatus = () => guardPanel()?.querySelector(".panel-title-row > span");
  const contextItems = () => [...document.querySelectorAll("#story-workspace .story-context-strip > div")];

  function setToolbarStatus(text) {
    const el = document.querySelector("#story-workspace .story-status");
    if (!el) return;
    el.innerHTML = '<span class="status-dot"></span>' + escapeHtml(text);
  }

  function setContext(index, count, heading, detail) {
    const item = contextItems()[index];
    if (!item) return;
    const icon = item.querySelector(".context-icon");
    const b = item.querySelector("b");
    const small = item.querySelector("small");
    if (icon && count !== null && count !== undefined) icon.textContent = count;
    if (b && heading) b.textContent = heading;
    if (small && detail) small.textContent = detail;
  }

  function resetIntelligence() {
    if (!isLocal) return;
    activeAnalysis = null;
    runtime.analysis = null;
    runtime.selectedAngle = null;
    runtime.selectedAngleIndex = 0;
    const list = momentList();
    if (list) list.innerHTML = '<div class="empty-pack">Create a source-backed story to run Source Intelligence.</div>';
    if (detectedLabel()) detectedLabel().textContent = "Waiting";
    setContext(2, "—", "Story angles", "Source-backed analysis runs after creation");

    const panel = guardPanel();
    if (panel) {
      const status = guardStatus();
      if (status) {
        status.textContent = "WAITING";
        status.classList.remove("verified-text");
      }
      const rows = panel.querySelectorAll(".claim-detail > div");
      if (rows[0]) { rows[0].querySelector("b").textContent = "ANGLE"; rows[0].querySelector("span").textContent = "Waiting for source analysis"; }
      if (rows[1]) rows[1].querySelector("span").textContent = "Evidence will appear here";
      if (rows[2]) { rows[2].querySelector("b").textContent = "LOCATION"; rows[2].querySelector("span").textContent = "—"; }
      if (rows[3]) rows[3].querySelector("span").textContent = "SourceGuard will trace the selected angle to its source evidence.";
    }
  }

  function setLoading() {
    const list = momentList();
    if (list) {
      list.innerHTML = [0, 1, 2].map(index =>
        '<button class="moment" disabled><strong>··</strong><span><b>' +
        (index === 0 ? "Analyzing source" : "Ranking evidence") +
        '</b><small>Source Intelligence v2</small></span><em>Working</em></button>'
      ).join("");
    }
    if (detectedLabel()) detectedLabel().textContent = "Analyzing…";
    setContext(2, "…", "Story angles", "Ranking evidence-backed opportunities");
    setToolbarStatus("ANALYZING SOURCE");

    const status = guardStatus();
    if (status) {
      status.textContent = "TRACING…";
      status.classList.remove("verified-text");
    }
  }

  function formatScore(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return Number.isInteger(number) ? String(number) : number.toFixed(1);
  }

  function formatSourceDetail(result) {
    const chars = Number(result?.source_characters || 0).toLocaleString();
    const method = result?.extraction_method === "provided_text"
      ? "Provided text indexed"
      : result?.extraction_method === "readable_webpage"
        ? "Public page extracted"
        : "Source indexed";
    return chars && chars !== "0" ? `${method} · ${chars} characters` : method;
  }

  function renderClaimTrace(angle, result) {
    if (!angle) return;
    const panel = guardPanel();
    if (!panel) return;

    const status = guardStatus();
    if (status) {
      const direct = angle.verification_level === "direct_extract";
      status.textContent = direct ? "DIRECT EXTRACT ✓" : "SUPPORTED ✓";
      status.classList.add("verified-text");
    }

    const rows = panel.querySelectorAll(".claim-detail > div");
    if (rows[0]) {
      rows[0].querySelector("b").textContent = "ANGLE";
      rows[0].querySelector("span").textContent = angle.title || angle.claim || "Selected story angle";
    }
    if (rows[1]) {
      rows[1].querySelector("b").textContent = "EVIDENCE";
      rows[1].querySelector("span").textContent = angle.excerpt || angle.claim || "Direct source evidence";
    }
    if (rows[2]) {
      rows[2].querySelector("b").textContent = "LOCATION";
      rows[2].querySelector("span").textContent = angle.location || "Indexed source";
    }
    if (rows[3]) {
      rows[3].querySelector("b").textContent = "CONTEXT";
      rows[3].querySelector("span").textContent = angle.verification_level === "direct_extract"
        ? "This angle is a direct extract from the indexed source. Editorial wording should preserve this meaning."
        : (result?.sourceguard?.context || angle.claim || "Trace this angle to its source before publication.");
    }

    const note = panel.querySelector(".unsupported-box");
    if (note) note.innerHTML = '<b>SourceGuard:</b> Evidence is preserved separately from editorial wording. Headline and hook generation will be checked against this source trace before publication.';
  }

  function selectAngle(index) {
    if (!activeAnalysis?.angles?.length) return;
    const angles = activeAnalysis.angles;
    selectedAngleIndex = Math.max(0, Math.min(index, angles.length - 1));
    const selectedAngle = angles[selectedAngleIndex];
    runtime.selectedAngleIndex = selectedAngleIndex;
    runtime.selectedAngle = selectedAngle;
    document.querySelectorAll("#story-workspace .moment-list .moment").forEach((button, i) => {
      button.classList.toggle("active", i === selectedAngleIndex);
    });
    renderClaimTrace(selectedAngle, activeAnalysis);
    window.dispatchEvent(new CustomEvent("ha:angle-selected", {
      detail: {
        storyId: runtime.storyId || activeAnalysis.story_id,
        index: selectedAngleIndex,
        angle: selectedAngle,
        analysis: activeAnalysis
      }
    }));
  }

  function renderAnalysis(result) {
    activeAnalysis = result;
    runtime.analysis = result;
    runtime.storyId = result?.story_id || runtime.storyId;
    runtime.sourceId = result?.source_id || runtime.sourceId;
    selectedAngleIndex = 0;
    const angles = Array.isArray(result?.angles) ? result.angles : [];
    const list = momentList();

    if (list) {
      if (!angles.length) {
        list.innerHTML = '<div class="empty-pack">No strong source-backed angle was detected. Add more source material or review the source manually.</div>';
      } else {
        list.innerHTML = angles.map((angle, index) => {
          const verification = angle.verification_level === "direct_extract" ? "Direct source extract" : "Source-backed candidate";
          return '<button class="moment' + (index === 0 ? " active" : "") + '" data-live-angle="' + index + '">' +
            '<strong>' + escapeHtml(formatScore(angle.score)) + '</strong>' +
            '<span><b>' + escapeHtml(angle.title || angle.claim || "Story angle") + '</b>' +
            '<small>' + escapeHtml(angle.location || verification) + '</small></span>' +
            '<em>' + escapeHtml(angle.signal || verification) + '</em></button>';
        }).join("");
      }
    }

    if (detectedLabel()) detectedLabel().textContent = `${angles.length} detected`;
    setContext(0, "✓", "Source indexed", formatSourceDetail(result));
    setContext(1, "✓", "SourceGuard ready", "Evidence remains separate from editorial wording");
    setContext(2, String(angles.length), "Story angles", angles.length ? "Evidence-backed and ranked" : "Manual review recommended");
    setToolbarStatus("SOURCE ANALYZED");

    window.dispatchEvent(new CustomEvent("ha:analysis-ready", { detail: result }));

    if (angles.length) selectAngle(0);
    else {
      runtime.selectedAngle = null;
      const status = guardStatus();
      if (status) {
        status.textContent = "REVIEW NEEDED";
        status.classList.remove("verified-text");
      }
    }
  }

  async function analyzeStory(storyId) {
    if (!API_BASE || !storyId || storyId === lastAnalyzedStoryId) return;
    lastAnalyzedStoryId = storyId;
    setLoading();

    try {
      const response = await fetch(`${API_BASE}/stories/${encodeURIComponent(storyId)}/analyze`, {
        method: "POST",
        headers: { "Accept": "application/json" }
      });
      if (!response.ok) {
        let detail = "";
        try { detail = (await response.json())?.detail || ""; } catch {}
        throw new Error(detail || `API ${response.status}`);
      }
      renderAnalysis(await response.json());
    } catch (error) {
      console.error("Source Intelligence analysis failed:", error);
      lastAnalyzedStoryId = null;
      const list = momentList();
      if (list) list.innerHTML = '<div class="empty-pack">Source Intelligence could not analyze this source yet. The Story is still saved and can be reviewed manually.</div>';
      if (detectedLabel()) detectedLabel().textContent = "Review needed";
      setContext(2, "!", "Story angles", "Analysis needs editorial review");
      setToolbarStatus("SOURCE INDEXED");
      const status = guardStatus();
      if (status) {
        status.textContent = "REVIEW NEEDED";
        status.classList.remove("verified-text");
      }
    }
  }

  momentList()?.addEventListener("click", event => {
    const button = event.target.closest("[data-live-angle]");
    if (!button) return;
    selectAngle(Number(button.dataset.liveAngle));
  });

  window.addEventListener("ha:story-created", event => {
    const storyId = event.detail?.id || runtime.storyId;
    if (storyId) analyzeStory(storyId);
  });

  if (isLocal) resetIntelligence();
});
