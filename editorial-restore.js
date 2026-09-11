// Headline Avenue editorial selection restore layer.
// Rehydrates the persisted Headline Lab selection and SourceGuard claim trace
// after session-persistence restores a Story Workspace.
document.addEventListener("DOMContentLoaded", () => {
  const runtime = window.HeadlineAvenueRuntime || (window.HeadlineAvenueRuntime = {});
  const localHosts = new Set(["localhost", "127.0.0.1"]);
  if (!localHosts.has(window.location.hostname)) return;

  const API_BASE = "http://127.0.0.1:8000/api/v1";
  const fetcher = window.__haNativeFetch || window.fetch.bind(window);
  let pending = null;
  let restoreSerial = 0;

  const escapeHtml = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function normalizedMode(mode) {
    return String(mode || "balanced").toLowerCase();
  }

  function selectionVariant(state) {
    return {
      mode: normalizedMode(state.mode),
      headline: state.headline || "",
      hook: state.hook || "",
      sourceguard_status: state.sourceguard_status || (state.status === "ready" ? "source_aligned" : "needs_review"),
      verification_level: state.verification_level || "lexical_grounding_v3",
      grounding_score: Number(state.grounding_score || 0),
      reasons: Array.isArray(state.reasons) ? state.reasons : []
    };
  }

  function setClaimTrace(state) {
    const panel = document.querySelector("#story-workspace .sourceguard-panel");
    if (!panel) return;

    const statusNode = panel.querySelector(".panel-title-row > span");
    const review = state.sourceguard_status !== "source_aligned";
    if (statusNode) {
      if (state.status === "approved") {
        statusNode.textContent = "REVIEW OVERRIDE ✓";
        statusNode.classList.add("verified-text");
      } else if (review) {
        statusNode.textContent = "REVIEW REQUIRED";
        statusNode.classList.remove("verified-text");
      } else {
        statusNode.textContent = "SOURCE-ALIGNED ✓";
        statusNode.classList.add("verified-text");
      }
    }

    const rows = panel.querySelectorAll(".claim-detail > div");
    if (rows[0]) {
      rows[0].querySelector("b").textContent = "HEADLINE";
      rows[0].querySelector("span").textContent = state.headline || "Selected editorial headline";
    }
    if (rows[1]) {
      rows[1].querySelector("b").textContent = "EVIDENCE";
      rows[1].querySelector("span").textContent = state.evidence || "Indexed source evidence";
    }
    if (rows[2]) {
      rows[2].querySelector("b").textContent = "LOCATION";
      rows[2].querySelector("span").textContent = state.location || "Indexed source";
    }
    if (rows[3]) {
      rows[3].querySelector("b").textContent = "CONTEXT";
      rows[3].querySelector("span").textContent = state.status === "approved"
        ? "This editorial wording required SourceGuard review and was explicitly approved by an editor. The approval remains attached to the story."
        : review
          ? "Selected editorial wording is saved as a review draft and should be checked by an editor before publication."
          : "Selected editorial wording is source-aligned with the preserved evidence trace.";
    }

    const note = panel.querySelector(".unsupported-box");
    if (note) {
      const reason = Array.isArray(state.reasons) && state.reasons.length ? state.reasons[0] : "";
      if (state.status === "approved") {
        note.innerHTML = "<b>SourceGuard:</b> This wording required review. Editor approval is attached; the original evidence remains preserved separately.";
      } else if (review) {
        note.innerHTML = `<b>SourceGuard:</b> ${escapeHtml(reason || "This wording requires editorial review before publication.")}`;
      } else {
        note.innerHTML = "<b>SourceGuard:</b> Evidence is preserved separately from editorial wording and remains attached to this selection.";
      }
    }
  }

  function applySelectionToHeadlineLab(state) {
    const mode = normalizedMode(state.mode);
    const panel = document.getElementById("editorial-intelligence-panel");
    const card = panel?.querySelector(`.editorial-variant[data-editorial-mode="${CSS.escape(mode)}"]`);
    if (!panel || !card) return false;

    const variant = selectionVariant(state);
    const review = variant.sourceguard_status !== "source_aligned";

    panel.querySelectorAll(".editorial-variant").forEach(item => item.classList.toggle("selected", item === card));
    card.dataset.customHeadline = variant.headline;
    card.dataset.customStatus = variant.sourceguard_status;

    const title = card.querySelector("[data-editorial-headline]");
    const input = card.querySelector("[data-editorial-input]");
    const editor = card.querySelector(".editorial-editor");
    const guard = card.querySelector("[data-editorial-guard]");
    const score = card.querySelector("[data-editorial-score]");
    const hook = card.querySelector("[data-editorial-hook]");
    const use = card.querySelector("[data-use-editorial]");
    const edit = card.querySelector("[data-edit-editorial]");

    if (title) {
      title.textContent = variant.headline;
      title.hidden = false;
    }
    if (input) input.value = variant.headline;
    if (editor) editor.hidden = true;
    if (edit) {
      edit.disabled = false;
      edit.textContent = "Edit";
    }
    if (guard) {
      guard.textContent = review ? `REVIEW ${variant.grounding_score}%` : `GROUNDED ${variant.grounding_score}%`;
      guard.classList.toggle("review", review);
      guard.classList.toggle("aligned", !review);
      guard.title = variant.reasons.join(" ");
    }
    if (score) score.textContent = `${variant.grounding_score}% grounded`;
    if (hook) hook.textContent = variant.hook;
    if (use) {
      use.textContent = state.status === "approved"
        ? "Selected · approved ✓"
        : review ? "Selected review draft ✓" : "Selected ✓";
      use.disabled = true;
    }

    const status = document.getElementById("editorial-status");
    if (status) {
      status.textContent = review ? "REVIEW" : "READY";
      status.classList.toggle("verified-text", !review);
    }

    const rank = document.getElementById("editorial-angle-rank");
    if (rank && state.angle_rank) rank.textContent = String(state.angle_rank).padStart(2, "0");

    const note = document.getElementById("editorial-selected-note");
    if (note) {
      const suffix = state.status === "approved"
        ? "Saved as review draft · Editor approved"
        : review ? "Saved as review draft" : "Grounded by SourceGuard";
      note.hidden = false;
      note.innerHTML = `<b>Selected for Story Pack:</b> ${escapeHtml(variant.headline)} · ${escapeHtml(suffix)}`;
    }

    const storyTitle = document.getElementById("story-title");
    if (storyTitle && variant.headline) storyTitle.textContent = variant.headline;

    runtime.editorialSelection = {
      story_id: state.story_id,
      output_id: state.selection_id,
      title: variant.headline,
      mode,
      status: review ? "needs_review" : "ready",
      selected: variant,
      approval: state.approval || null
    };

    setClaimTrace(state);
    return true;
  }

  function restoreWhenCardsReady(state, serial, attempt = 0) {
    if (serial !== restoreSerial || pending !== state) return;
    if (applySelectionToHeadlineLab(state)) {
      pending = null;
      window.dispatchEvent(new CustomEvent("ha:editorial-selection-restored", { detail: state }));
      return;
    }
    if (attempt < 40) {
      window.setTimeout(() => restoreWhenCardsReady(state, serial, attempt + 1), 100);
    }
  }

  function selectPersistedAngle(state, serial) {
    if (serial !== restoreSerial || pending !== state) return;
    const index = Math.max(0, Number(state.angle_rank || 1) - 1);
    const button = document.querySelector(`#story-workspace .moment-list [data-live-angle="${index}"]`);
    if (button) button.click();
    window.setTimeout(() => restoreWhenCardsReady(state, serial), 80);
  }

  async function fetchSelectionState(storyId) {
    const response = await fetcher(`${API_BASE}/stories/${encodeURIComponent(storyId)}/editorial/selection-state`, {
      headers: { "Accept": "application/json" },
      cache: "no-store"
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return response.json();
  }

  window.addEventListener("ha:story-created", async event => {
    if (!event.detail?.__haRestored) return;
    const storyId = event.detail?.id || runtime.storyId;
    if (!storyId) return;

    const serial = ++restoreSerial;
    try {
      const state = await fetchSelectionState(storyId);
      if (serial !== restoreSerial || !state?.selection_id) return;
      pending = state;
      runtime.editorialRestoredSelection = state;

      // Source Intelligence emits ha:analysis-ready before it performs its
      // default angle-01 selection, so restoration is deferred until that
      // default selection has completed.
      if (runtime.analysis?.angles?.length) {
        window.setTimeout(() => selectPersistedAngle(state, serial), 80);
      }
    } catch (error) {
      console.debug("Editorial selection restore skipped:", error);
    }
  });

  window.addEventListener("ha:analysis-ready", () => {
    if (!pending) return;
    const state = pending;
    const serial = restoreSerial;
    window.setTimeout(() => selectPersistedAngle(state, serial), 80);
  });
});
