// Headline Avenue Editorial Intelligence UI v3.
// Differentiates editorial modes, supports regeneration and editable headlines,
// and re-runs SourceGuard while the user edits before anything is persisted.
document.addEventListener("DOMContentLoaded", () => {
  const runtime = window.HeadlineAvenueRuntime || (window.HeadlineAvenueRuntime = {});
  const localHosts = new Set(["localhost", "127.0.0.1"]);
  const isLocal = localHosts.has(window.location.hostname);
  const API_BASE = isLocal ? "http://127.0.0.1:8000/api/v1" : "";
  const fetcher = window.__haNativeFetch || window.fetch.bind(window);

  const cache = new Map();
  const generationByRank = new Map();
  const editTimers = new WeakMap();
  let requestSerial = 0;
  let currentRank = null;
  let currentGeneration = 1;

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
    link.href = "editorial-intelligence.css?v=20260910-0730";
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
      <div class="panel-title-row editorial-title-row">
        <div>
          <span class="panel-kicker">EDITORIAL INTELLIGENCE</span>
          <h3>Headline Lab</h3>
          <p>Turn the selected source-backed angle into publishable wording without losing the evidence trail.</p>
        </div>
        <div class="editorial-title-actions">
          <span id="editorial-status">WAITING</span>
          <button id="editorial-regenerate" class="editorial-regenerate" type="button" disabled>↻ Regenerate</button>
        </div>
      </div>
      <div class="editorial-intro-row">
        <span class="editorial-angle-chip">SELECTED ANGLE <b id="editorial-angle-rank">—</b></span>
        <span>Grounding is a lexical SourceGuard check, not a claim of complete fact verification.</span>
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

  function setRegenerateEnabled(enabled) {
    const button = document.getElementById("editorial-regenerate");
    if (button) button.disabled = !enabled;
  }

  function resetPanel() {
    ensurePanel();
    runtime.editorialSelection = null;
    runtime.editorialVariants = null;
    currentRank = null;
    currentGeneration = 1;
    generationByRank.clear();

    const rank = document.getElementById("editorial-angle-rank");
    if (rank) rank.textContent = "—";

    const variants = document.getElementById("editorial-variants");
    if (variants) {
      variants.innerHTML = '<div class="editorial-loading"><b>Analyzing source first</b>Headline variants will appear after Source Intelligence ranks the evidence.</div>';
    }

    const note = document.getElementById("editorial-selected-note");
    if (note) note.hidden = true;

    setRegenerateEnabled(false);
    setStatus("WAITING");
  }

  function guardLabel(variant) {
    const score = Number(variant.grounding_score || 0);
    return variant.sourceguard_status === "source_aligned"
      ? `GROUNDED ${score}%`
      : `REVIEW ${score}%`;
  }

  function variantCard(variant, rank, generation) {
    const aligned = variant.sourceguard_status === "source_aligned";
    const reason = (variant.reasons || []).join(" ");
    const mode = escapeHtml(variant.mode);
    const headline = escapeHtml(variant.headline);
    const hook = escapeHtml(variant.hook);

    return `
      <article class="editorial-variant"
        data-editorial-mode="${mode}"
        data-editorial-rank="${rank}"
        data-editorial-generation="${generation}"
        data-original-headline="${headline}">
        <div class="editorial-variant-head">
          <span class="editorial-mode">${escapeHtml(variant.label)}</span>
          <span class="editorial-guard ${aligned ? "aligned" : "review"}"
            data-editorial-guard
            title="${escapeHtml(reason)}">${escapeHtml(guardLabel(variant))}</span>
        </div>

        <h4 data-editorial-headline>${headline}</h4>

        <div class="editorial-editor" hidden>
          <label>EDIT HEADLINE</label>
          <textarea maxlength="180" rows="3" data-editorial-input>${headline}</textarea>
          <div class="editorial-edit-meta">
            <span data-editorial-check-state>Start typing — SourceGuard will re-check automatically.</span>
            <button type="button" data-cancel-editorial-edit>Cancel edit</button>
          </div>
        </div>

        <p class="editorial-hook"><b>HOOK</b><span data-editorial-hook>${hook}</span></p>

        <div class="editorial-variant-foot">
          <span class="editorial-score">
            <b data-editorial-score>${Number(variant.grounding_score || 0)}% grounded</b>
            <small>Lexical check · SourceGuard v3</small>
          </span>
          <div class="editorial-card-actions">
            <button type="button" class="editorial-edit" data-edit-editorial>Edit</button>
            <button type="button" class="editorial-use"
              data-use-editorial="${mode}"
              data-angle-rank="${rank}">${aligned ? "Use headline" : "Use draft"}</button>
          </div>
        </div>
      </article>`;
  }

  function renderVariants(result) {
    currentRank = Number(result.angle_rank || 1);
    currentGeneration = Number(result.generation ?? generationByRank.get(currentRank) ?? 1);
    generationByRank.set(currentRank, currentGeneration);

    const rank = document.getElementById("editorial-angle-rank");
    if (rank) rank.textContent = String(currentRank).padStart(2, "0");

    const variants = document.getElementById("editorial-variants");
    if (!variants) return;

    if (!Array.isArray(result.variants) || !result.variants.length) {
      variants.innerHTML = '<div class="editorial-error">No safe editorial variants were generated for this angle. Keep the source extract or review it manually.</div>';
      setRegenerateEnabled(true);
      setStatus("REVIEW");
      return;
    }

    variants.innerHTML = result.variants
      .map(item => variantCard(item, currentRank, currentGeneration))
      .join("");

    setRegenerateEnabled(true);
    setStatus("READY", true);
  }

  async function loadVariants(rank, options = {}) {
    ensurePanel();
    if (!API_BASE || !runtime.storyId || !rank) return;

    currentRank = Number(rank);
    if (!generationByRank.has(currentRank)) generationByRank.set(currentRank, 1);
    if (Number.isInteger(options.generation)) generationByRank.set(currentRank, options.generation);
    currentGeneration = generationByRank.get(currentRank);

    const rankLabel = document.getElementById("editorial-angle-rank");
    if (rankLabel) rankLabel.textContent = String(currentRank).padStart(2, "0");

    const note = document.getElementById("editorial-selected-note");
    if (note) note.hidden = true;

    const cacheKey = `${runtime.storyId}:${currentRank}:${currentGeneration}`;
    if (!options.force && cache.has(cacheKey)) {
      renderVariants(cache.get(cacheKey));
      return;
    }

    const serial = ++requestSerial;
    const variants = document.getElementById("editorial-variants");
    if (variants) {
      variants.innerHTML = '<div class="editorial-loading"><b>Building headline variants</b>Headline Lab is separating the four editorial treatments and checking each against the source.</div>';
    }

    setRegenerateEnabled(false);
    setStatus(options.force ? "REGENERATING…" : "GENERATING…");

    try {
      const response = await fetcher(`${API_BASE}/stories/${encodeURIComponent(runtime.storyId)}/editorial`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({
          angle_rank: currentRank,
          generation: currentGeneration
        })
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
      if (variants) {
        variants.innerHTML = `<div class="editorial-error">Editorial Intelligence could not build headline variants yet. ${escapeHtml(error.message)}</div>`;
      }
      setRegenerateEnabled(true);
      setStatus("REVIEW");
    }
  }

  function updateCardGuard(card, variant) {
    const aligned = variant.sourceguard_status === "source_aligned";
    const guard = card.querySelector("[data-editorial-guard]");
    const score = card.querySelector("[data-editorial-score]");
    const hook = card.querySelector("[data-editorial-hook]");
    const state = card.querySelector("[data-editorial-check-state]");
    const use = card.querySelector("[data-use-editorial]");

    if (guard) {
      guard.textContent = guardLabel(variant);
      guard.classList.toggle("aligned", aligned);
      guard.classList.toggle("review", !aligned);
      guard.title = (variant.reasons || []).join(" ");
    }
    if (score) score.textContent = `${variant.grounding_score}% grounded`;
    if (hook) hook.textContent = variant.hook || "";
    if (state) {
      state.textContent = aligned
        ? "SourceGuard: wording remains source-aligned."
        : (variant.reasons || ["Editorial review recommended."])[0];
      state.classList.toggle("aligned", aligned);
      state.classList.toggle("review", !aligned);
    }
    if (use) {
      const edited = variant.headline !== card.dataset.originalHeadline;
      use.textContent = edited
        ? (aligned ? "Use edited" : "Use review draft")
        : (aligned ? "Use headline" : "Use draft");
    }

    card.dataset.customHeadline = variant.headline;
    card.dataset.customStatus = variant.sourceguard_status;
  }

  async function checkEditedHeadline(card, headline) {
    if (!API_BASE || !runtime.storyId || !headline.trim()) return;

    const rank = Number(card.dataset.editorialRank || currentRank || 1);
    const mode = card.dataset.editorialMode;
    const state = card.querySelector("[data-editorial-check-state]");
    const guard = card.querySelector("[data-editorial-guard]");

    if (state) {
      state.textContent = "Checking against source…";
      state.classList.remove("aligned", "review");
    }
    if (guard) {
      guard.textContent = "CHECKING…";
      guard.classList.remove("aligned", "review");
    }

    const requestHeadline = headline.trim();
    card.dataset.checkingHeadline = requestHeadline;

    try {
      const response = await fetcher(`${API_BASE}/stories/${encodeURIComponent(runtime.storyId)}/editorial/check`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({
          angle_rank: rank,
          mode,
          headline: requestHeadline
        })
      });

      if (!response.ok) {
        let detail = "";
        try { detail = (await response.json())?.detail || ""; } catch {}
        throw new Error(detail || `API ${response.status}`);
      }

      const result = await response.json();
      if (card.dataset.checkingHeadline !== requestHeadline) return;
      updateCardGuard(card, result.selected);
    } catch (error) {
      console.error("Headline SourceGuard check failed:", error);
      if (card.dataset.checkingHeadline !== requestHeadline) return;
      if (state) {
        state.textContent = "Could not run SourceGuard check yet.";
        state.classList.add("review");
      }
      if (guard) {
        guard.textContent = "CHECK FAILED";
        guard.classList.add("review");
      }
      delete card.dataset.customHeadline;
    }
  }

  function scheduleEditCheck(input) {
    const card = input.closest(".editorial-variant");
    if (!card) return;

    const headline = input.value;
    const existing = editTimers.get(input);
    if (existing) window.clearTimeout(existing);

    const timer = window.setTimeout(() => checkEditedHeadline(card, headline), 360);
    editTimers.set(input, timer);
  }

  function beginEdit(button) {
    const card = button.closest(".editorial-variant");
    if (!card) return;

    const editor = card.querySelector(".editorial-editor");
    const headline = card.querySelector("[data-editorial-headline]");
    const input = card.querySelector("[data-editorial-input]");
    if (!editor || !headline || !input) return;

    editor.hidden = false;
    headline.hidden = true;
    button.textContent = "Editing";
    button.disabled = true;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  }

  function cancelEdit(button) {
    const card = button.closest(".editorial-variant");
    if (!card) return;

    const editor = card.querySelector(".editorial-editor");
    const headline = card.querySelector("[data-editorial-headline]");
    const input = card.querySelector("[data-editorial-input]");
    const edit = card.querySelector("[data-edit-editorial]");

    if (input) input.value = card.dataset.originalHeadline || "";
    if (editor) editor.hidden = true;
    if (headline) headline.hidden = false;
    if (edit) {
      edit.disabled = false;
      edit.textContent = "Edit";
    }

    delete card.dataset.customHeadline;
    delete card.dataset.customStatus;
    delete card.dataset.checkingHeadline;

    const result = runtime.editorialVariants?.variants?.find(item => item.mode === card.dataset.editorialMode);
    if (result) updateCardGuard(card, result);
    delete card.dataset.customHeadline;
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
        ? "Selected editorial wording is lexically grounded in the evidence and indexed source shown here."
        : "Selected editorial wording is saved as a review draft and should be checked by an editor before publication.";
    }
  }

  async function useVariant(button) {
    if (!API_BASE || !runtime.storyId) return;

    const card = button.closest(".editorial-variant");
    if (!card) return;

    const mode = button.dataset.useEditorial;
    const angleRank = Number(button.dataset.angleRank || currentRank || 1);
    const generation = Number(card.dataset.editorialGeneration || currentGeneration || 1);
    const editor = card.querySelector(".editorial-editor");
    const input = card.querySelector("[data-editorial-input]");

    const editing = editor && !editor.hidden;
    const customHeadline = editing ? String(input?.value || "").trim() : "";
    const isCustom = Boolean(customHeadline && customHeadline !== card.dataset.originalHeadline);

    if (isCustom && card.dataset.customHeadline !== customHeadline) {
      await checkEditedHeadline(card, customHeadline);
      if (card.dataset.customHeadline !== customHeadline) {
        showToast("Wait for SourceGuard to finish checking this edit.");
        return;
      }
    }

    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Saving…";

    try {
      const endpoint = isCustom ? "editorial/select-custom" : "editorial/select";
      const payload = isCustom
        ? { angle_rank: angleRank, mode, headline: customHeadline }
        : { angle_rank: angleRank, mode, generation };

      const response = await fetcher(`${API_BASE}/stories/${encodeURIComponent(runtime.storyId)}/${endpoint}`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        let detail = "";
        try { detail = (await response.json())?.detail || ""; } catch {}
        throw new Error(detail || `API ${response.status}`);
      }

      const result = await response.json();
      runtime.editorialSelection = result;

      document.querySelectorAll("#editorial-variants .editorial-variant").forEach(item => {
        item.classList.toggle("selected", item === card);
      });

      const title = document.getElementById("story-title");
      if (title) title.textContent = result.title;

      const note = document.getElementById("editorial-selected-note");
      if (note) {
        note.hidden = false;
        note.innerHTML = `<b>Selected for Story Pack:</b> ${escapeHtml(result.title)} · ${
          result.status === "ready" ? "Grounded by SourceGuard" : "Saved as review draft"
        }`;
      }

      setStatus(result.status === "ready" ? "SELECTED ✓" : "REVIEW", result.status === "ready");
      updateClaimTrace(result);
      showToast(
        result.status === "ready"
          ? (isCustom ? "Edited headline checked and saved" : "Headline selected and saved")
          : "Headline saved as a review draft"
      );
    } catch (error) {
      console.error("Could not select editorial variant:", error);
      showToast("Could not save headline — " + error.message);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function regenerate() {
    if (!currentRank || !runtime.storyId) return;
    const nextGeneration = ((generationByRank.get(currentRank) ?? 1) + 1) % 3;
    generationByRank.set(currentRank, nextGeneration);
    loadVariants(currentRank, { force: true, generation: nextGeneration });
  }

  ensureStyles();
  ensurePanel();

  document.getElementById("editorial-intelligence-panel")?.addEventListener("click", event => {
    const use = event.target.closest("[data-use-editorial]");
    if (use) {
      useVariant(use);
      return;
    }

    const edit = event.target.closest("[data-edit-editorial]");
    if (edit) {
      beginEdit(edit);
      return;
    }

    const cancel = event.target.closest("[data-cancel-editorial-edit]");
    if (cancel) {
      cancelEdit(cancel);
      return;
    }

    if (event.target.closest("#editorial-regenerate")) regenerate();
  });

  document.getElementById("editorial-intelligence-panel")?.addEventListener("input", event => {
    const input = event.target.closest("[data-editorial-input]");
    if (input) scheduleEditCheck(input);
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
