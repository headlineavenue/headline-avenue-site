// Headline Avenue Editorial Intelligence UI.
// Turns a selected source-backed angle into headline/hook options, then persists
// the user's chosen wording without allowing the browser to invent the variant.
document.addEventListener("DOMContentLoaded", () => {
  const runtime = window.HeadlineAvenueRuntime || (window.HeadlineAvenueRuntime = {});
  const localHosts = new Set(["localhost", "127.0.0.1"]);
  const isLocal = localHosts.has(window.location.hostname);
  const API_BASE = isLocal ? "http://127.0.0.1:8000/api/v1" : "";
  const fetcher = window.__haNativeFetch || window.fetch.bind(window);
  const cache = new Map();
  let requestSerial = 0;
  let currentRank = null;

  const escapeHtml = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function showToast(message) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function ensureStyles() {
    if (document.querySelector('link[data-ha-editorial-css]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "editorial-intelligence.css?v=20260910-0635";
    link.dataset.haEditorialCss = "1";
    document.head.appendChild(link);
  }

  function ensurePanel() {
    let panel = document.getElementById("editorial-intelligence-panel");
    if (panel) return panel;

    const guard = document.querySelector("#story-workspace .sourceguard-panel");
    if (!guard) return null;

    panel = document.createElement("article");
    panel.id = "editorial-intelligence-panel";
    panel.className = "workspace-card story-panel editorial-panel";
    panel.innerHTML = `
      <div class="panel-title-row">
        <div>
          <span class="panel-kicker">EDITORIAL INTELLIGENCE</span>
          <h3>Headline Lab</h3>
          <p>Turn the selected source-backed angle into publishable wording without losing the evidence trail.</p>
        </div>
        <span id="editorial-status">WAITING</span>
      </div>
      <div class="editorial-intro-row">
        <span class="editorial-angle-chip">SELECTED ANGLE <b id="editorial-angle-rank">—</b></span>
        <span>Every option is checked against the selected evidence before you use it.</span>
      </div>
      <div id="editorial-variants" class="editorial-variants">
        <div class="editorial-loading"><b>Select a source-backed angle</b>Headline variants will appear here.</div>
      </div>
      <div id="editorial-selected-note" class="editorial-selected-note" hidden></div>`;

    guard.before(panel);
    return panel;
  }

  function setStatus(text, aligned = false) {
    const status = document.getElementById("editorial-status");
    if (!status) return;
    status.textContent = text;
    status.classList.toggle("verified-text", aligned);
  }

  function resetPanel() {
    ensurePanel();
    runtime.editorialSelection = null;
    currentRank = null;
    const rank = document.getElementById("editorial-angle-rank");
    if (rank) rank.textContent = "—";
    const variants = document.getElementById("editorial-variants");
    if (variants) variants.innerHTML = '<div class="editorial-loading"><b>Analyzing source first</b>Headline variants will appear after Source Intelligence ranks the evidence.</div>';
    const note = document.getElementById("editorial-selected-note");
    if (note) note.hidden = true;
    setStatus("WAITING");
  }

  function variantCard(variant, rank) {
    const aligned = variant.sourceguard_status === "source_aligned";
    const buttonLabel = aligned ? "Use headline" : "Use draft";
    const guardLabel = aligned ? `SOURCE-ALIGNED ${variant.grounding_score}%` : "NEEDS REVIEW";
    const reason = (variant.reasons || []).join(" ");

    return `
      <article class="editorial-variant" data-editorial-mode="${escapeHtml(variant.mode)}" data-editorial-rank="${rank}">
        <div class="editorial-variant-head">
          <span class="editorial-mode">${escapeHtml(variant.label)}</span>
          <span class="editorial-guard ${aligned ? "aligned" : "review"}" title="${escapeHtml(reason)}">${escapeHtml(guardLabel)}</span>
        </div>
        <h4>${escapeHtml(variant.headline)}</h4>
        <p class="editorial-hook"><b>HOOK</b>${escapeHtml(variant.hook)}</p>
        <div class="editorial-variant-foot">
          <span class="editorial-score"><b>${variant.grounding_score}% grounding</b>${escapeHtml(variant.verification_level)}</span>
          <button class="editorial-use" data-use-editorial="${escapeHtml(variant.mode)}" data-angle-rank="${rank}">${buttonLabel}</button>
        </div>
      </article>`;
  }

  function renderVariants(result) {
    currentRank = Number(result.angle_rank || 1);
    const rank = document.getElementById("editorial-angle-rank");
    if (rank) rank.textContent = String(currentRank).padStart(2, "0");

    const variants = document.getElementById("editorial-variants");
    if (!variants) return;

    if (!Array.isArray(result.variants) || !result.variants.length) {
      variants.innerHTML = '<div class="editorial-error">No safe editorial variants were generated for this angle. Keep the source extract or review it manually.</div>';
      setStatus("REVIEW");
      return;
    }

    variants.innerHTML = result.variants.map(item => variantCard(item, currentRank)).join("");
    setStatus("READY", true);
  }

  async function loadVariants(rank) {
    ensurePanel();
    if (!API_BASE || !runtime.storyId || !rank) return;

    currentRank = Number(rank);
    const rankLabel = document.getElementById("editorial-angle-rank");
    if (rankLabel) rankLabel.textContent = String(currentRank).padStart(2, "0");

    const note = document.getElementById("editorial-selected-note");
    if (note) note.hidden = true;
    document.querySelectorAll("#editorial-variants .editorial-variant").forEach(card => card.classList.remove("selected"));

    const cacheKey = `${runtime.storyId}:${currentRank}`;
    if (cache.has(cacheKey)) {
      renderVariants(cache.get(cacheKey));
      return;
    }

    const serial = ++requestSerial;
    const variants = document.getElementById("editorial-variants");
    if (variants) variants.innerHTML = '<div class="editorial-loading"><b>Building headline variants</b>SourceGuard is checking the wording against the selected evidence.</div>';
    setStatus("GENERATING…");

    try {
      const response = await fetcher(`${API_BASE}/stories/${encodeURIComponent(runtime.storyId)}/editorial`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ angle_rank: currentRank })
      });
      if (!response.ok) {
        let detail = "";
        try { detail = (await response.json())?.detail || ""; } catch {}
        throw new Error(detail || `API ${response.status}`);
      }
      const result = await response.json();
      if (serial !== requestSerial) return;
      cache.set(cacheKey, result);
      runtime.editorialVariants = result;
      renderVariants(result);
    } catch (error) {
      console.error("Editorial Intelligence failed:", error);
      if (serial !== requestSerial) return;
      if (variants) variants.innerHTML = `<div class="editorial-error">Editorial Intelligence could not build headline variants yet. ${escapeHtml(error.message)}</div>`;
      setStatus("REVIEW");
    }
  }

  function updateClaimTrace(selection) {
    const panel = document.querySelector("#story-workspace .sourceguard-panel");
    if (!panel) return;
    const rows = panel.querySelectorAll(".claim-detail > div");
    if (rows[0]) {
      rows[0].querySelector("b").textContent = "HEADLINE";
      rows[0].querySelector("span").textContent = selection.selected.headline;
    }
    if (rows[3]) {
      rows[3].querySelector("b").textContent = "CONTEXT";
      rows[3].querySelector("span").textContent = selection.selected.sourceguard_status === "source_aligned"
        ? "Selected editorial wording is lexically grounded in the evidence shown above."
        : "Selected editorial wording still requires human review before publication.";
    }
  }

  async function useVariant(button) {
    if (!API_BASE || !runtime.storyId) return;
    const mode = button.dataset.useEditorial;
    const angleRank = Number(button.dataset.angleRank || currentRank || 1);
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Saving…";

    try {
      const response = await fetcher(`${API_BASE}/stories/${encodeURIComponent(runtime.storyId)}/editorial/select`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ angle_rank: angleRank, mode })
      });
      if (!response.ok) {
        let detail = "";
        try { detail = (await response.json())?.detail || ""; } catch {}
        throw new Error(detail || `API ${response.status}`);
      }

      const result = await response.json();
      runtime.editorialSelection = result;
      document.querySelectorAll("#editorial-variants .editorial-variant").forEach(card => {
        card.classList.toggle("selected", card.dataset.editorialMode === result.mode && Number(card.dataset.editorialRank) === angleRank);
      });

      const title = document.getElementById("story-title");
      if (title) title.textContent = result.title;

      const note = document.getElementById("editorial-selected-note");
      if (note) {
        note.hidden = false;
        note.innerHTML = `<b>Selected for Story Pack:</b> ${escapeHtml(result.title)} · ${result.status === "ready" ? "Source-aligned" : "Needs review"}`;
      }

      setStatus(result.status === "ready" ? "SELECTED ✓" : "REVIEW", result.status === "ready");
      updateClaimTrace(result);
      showToast(result.status === "ready" ? "Headline selected and saved" : "Headline saved as a review draft");
    } catch (error) {
      console.error("Could not select editorial variant:", error);
      showToast("Could not save headline — " + error.message);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  ensureStyles();
  ensurePanel();

  document.getElementById("editorial-intelligence-panel")?.addEventListener("click", event => {
    const button = event.target.closest("[data-use-editorial]");
    if (button) useVariant(button);
  });

  window.addEventListener("ha:story-created", resetPanel);
  window.addEventListener("ha:angle-selected", event => {
    const rank = event.detail?.angle?.rank || Number(event.detail?.index || 0) + 1;
    loadVariants(rank);
  });

  if (runtime.analysis?.angles?.length && runtime.storyId) {
    loadVariants(runtime.analysis.angles[0].rank || 1);
  }
});
