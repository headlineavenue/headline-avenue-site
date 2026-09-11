// One-time compatibility recovery for Story Packs created before backend pack
// persistence was wired in. New packs are preserved by story-pack-sync.js.
document.addEventListener("DOMContentLoaded", () => {
  const localHosts = new Set(["localhost", "127.0.0.1"]);
  if (!localHosts.has(window.location.hostname)) return;

  const fetcher = window.__haNativeFetch || window.fetch.bind(window);
  const API_BASE = "http://127.0.0.1:8000/api/v1";
  const WORKSPACE_KEY = "headline-avenue.active-workspace.v1";
  const DRAFT_KEY = "headline-avenue.publish-draft.v1";
  const PACK_KEY = "headline-avenue.last-story-pack.v1";

  function readJson(key) {
    try {
      const raw = window.sessionStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function writeJson(key, value) {
    try { window.sessionStorage.setItem(key, JSON.stringify(value)); } catch {}
  }

  function showToast(message) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 2600);
  }

  function normalize(values) {
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

  const boot = readJson(WORKSPACE_KEY);
  if (boot?.activeView !== "publish" || !boot.storyId) return;

  window.setTimeout(async () => {
    // The normal publish bridge may already have restored successfully.
    if (readJson(DRAFT_KEY)?.id) return;

    try {
      // First prefer any backend draft that may already exist.
      try {
        const existing = await apiJson(`${API_BASE}/publishing/drafts/${encodeURIComponent(boot.storyId)}`);
        writeJson(DRAFT_KEY, existing);
        document.querySelector('.app-nav button[data-view="publish"]')?.click();
        return;
      } catch (error) {
        if (error.status !== 404) throw error;
      }

      let formats = normalize(boot.outputs);
      const savedPack = readJson(PACK_KEY);
      if (!formats.length && savedPack?.storyId === boot.storyId) {
        formats = normalize(savedPack.formats);
      }

      // Legacy sessions from before pack persistence can no longer tell us
      // which UI chips were selected. The old Full Story Pack default used by
      // this prototype was 9:16 + Article + Carousel plus the four editorial
      // companion assets, so use that once to migrate the stranded session.
      if (!formats.length) {
        formats = [
          "9:16_video",
          "article",
          "carousel",
          "headline",
          "summary",
          "source_trail",
          "platform_copy"
        ];
      }

      const pack = await apiJson(`${API_BASE}/story-packs/generate`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" },
        body: JSON.stringify({ story_id: boot.storyId, formats })
      });

      const savedFormats = normalize((pack.outputs || []).map(output => output.output_type));
      writeJson(PACK_KEY, { storyId: boot.storyId, formats: savedFormats, savedAt: Date.now() });
      writeJson(WORKSPACE_KEY, {
        ...boot,
        activeView: "publish",
        outputs: savedFormats,
        packState: "Ready",
        savedAt: Date.now()
      });

      const draft = await apiJson(`${API_BASE}/publishing/drafts/from-story/${encodeURIComponent(boot.storyId)}`, {
        method: "POST",
        headers: { "Accept": "application/json", "Content-Type": "application/json" }
      });

      writeJson(DRAFT_KEY, draft);
      const runtime = window.HeadlineAvenueRuntime || (window.HeadlineAvenueRuntime = {});
      runtime.storyId = boot.storyId;
      runtime.sourceId = boot.sourceId || runtime.sourceId || null;
      runtime.publishDraft = draft;

      // The normal publish bridge listens to this nav click and renders the
      // saved backend draft into the existing Publish desk.
      document.querySelector('.app-nav button[data-view="publish"]')?.click();
      showToast("Recovered the Story Pack and restored the live Publish draft");
    } catch (error) {
      console.error("Legacy Publish recovery failed:", error);
      showToast("Publish recovery still needs attention — " + error.message);
    }
  }, 180);
});
