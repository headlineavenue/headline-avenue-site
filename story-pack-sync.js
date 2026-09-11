// Headline Avenue backend Story Pack synchronization.
// The original product-demo handler keeps its Story id in a private closure.
// After a hard refresh, session-persistence restores the authoritative id into
// HeadlineAvenueRuntime, so this capture-phase handler makes Story Pack
// generation continue to hit the backend instead of silently falling back to
// prototype-only DOM rows.
document.addEventListener("DOMContentLoaded", () => {
  const localHosts = new Set(["localhost", "127.0.0.1"]);
  if (!localHosts.has(window.location.hostname)) return;

  const runtime = window.HeadlineAvenueRuntime || (window.HeadlineAvenueRuntime = {});
  const fetcher = window.__haNativeFetch || window.fetch.bind(window);
  const API_BASE = "http://127.0.0.1:8000/api/v1";

  function showToast(message) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function requestedFormats() {
    const normalized = {
      "9:16": "9:16_video",
      "16:9": "16:9_video",
      "1:1": "1:1_video",
      "4:5": "4:5_video",
      "Article": "article",
      "Carousel": "carousel",
      "Newsletter": "newsletter",
      "Thread": "thread"
    };
    const selected = [...document.querySelectorAll(".format-grid button.selected")]
      .map(button => button.textContent.trim());
    return [...new Set([
      ...selected.map(value => normalized[value] || value.toLowerCase().replace(/\s+/g, "_")),
      "headline",
      "summary",
      "source_trail",
      "platform_copy"
    ])];
  }

  function pretty(value) {
    return String(value || "")
      .replace(/_/g, " ")
      .replace(/^\d+:\d+ video$/i, match => match.replace(" video", ""))
      .replace(/\b\w/g, char => char.toUpperCase());
  }

  function renderOutputs(outputs) {
    const list = document.getElementById("pack-list");
    if (list) {
      list.innerHTML = outputs.map(output => {
        const status = output?.status === "needs_review" ? "Review required" : "Ready ✓";
        return `<div class="pack-item"><b>${pretty(output?.output_type || output)}</b><span>${status}</span></div>`;
      }).join("");
    }

    const count = document.getElementById("story-output-count");
    if (count) count.textContent = String(outputs.length);

    const needsReview = outputs.some(output => output?.status === "needs_review");
    const state = document.getElementById("story-pack-state");
    if (state) {
      state.textContent = needsReview ? "Review required" : "Ready";
      state.classList.toggle("verified-text", !needsReview);
    }
  }

  async function generateBackendPack(button) {
    const storyId = runtime.storyId;
    if (!storyId) return false;

    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Generating…";

    try {
      const response = await fetcher(`${API_BASE}/story-packs/generate`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ story_id: storyId, formats: requestedFormats() })
      });
      if (!response.ok) {
        let detail = "";
        try { detail = (await response.json())?.detail || ""; } catch {}
        throw new Error(detail || `API ${response.status}`);
      }

      const result = await response.json();
      renderOutputs(result.outputs || []);
      window.dispatchEvent(new CustomEvent("ha:story-pack-generated", { detail: result }));
      showToast("Story Pack generated and saved to backend");
      return true;
    } catch (error) {
      console.error("Backend Story Pack generation failed:", error);
      showToast("Story Pack error — " + error.message);
      return false;
    } finally {
      button.disabled = false;
      button.textContent = original || "Generate Story Pack";
    }
  }

  document.addEventListener("click", event => {
    const button = event.target.closest("#generate-pack");
    if (!button || !runtime.storyId) return;

    // Stop app-core's older closure-based handler. This one uses the restored
    // runtime Story id, so refreshes never downgrade a real Story Pack to a
    // prototype-only pack.
    event.preventDefault();
    event.stopImmediatePropagation();
    generateBackendPack(button);
  }, true);
});
