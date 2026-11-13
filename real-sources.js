(() => {
  const config = window.HeadlineAvenueConfig;
  if (!config?.apiBase) return;

  const fetcher = window.__haNativeFetch || window.fetch.bind(window);
  let loading = false;
  let sourceType = "all";
  let transcriptionConfig = { configured: false, provider: "deepgram", model: "nova-3" };
  let pollTimer = null;

  const escapeHtml = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const toast = message => {
    const node = document.getElementById("toast");
    if (!node) return;
    node.textContent = message;
    node.classList.add("show");
    window.setTimeout(() => node.classList.remove("show"), 2200);
  };

  const prettyBytes = value => {
    const bytes = Number(value || 0);
    if (!bytes) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
    return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  };

  const relativeTime = value => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Recently";
    const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (seconds < 60) return "Just now";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} hr${hours === 1 ? "" : "s"} ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  };

  const viewType = kind => kind === "pdf" ? "document" : String(kind || "url");

  const kindLabel = kind => ({
    video: "Video",
    audio: "Audio",
    pdf: "PDF",
    article: "Article",
    transcript: "Transcript",
    url: "Web"
  }[kind] || String(kind || "Source"));

  const kindIcon = kind => ({
    video: "▶",
    audio: "◖",
    pdf: "▤",
    article: "≡",
    transcript: "¶",
    url: "↗"
  }[kind] || "⌁");

  const stateFor = item => {
    const status = String(item.status || "");
    if (status === "indexed") {
      return {
        filter: "ready",
        className: "ready",
        label: "✓ Indexed",
        sub: item.has_transcript ? "Transcript ready" : "Source text ready"
      };
    }
    if (["uploaded", "uploading", "queued", "transcription_queued", "transcribing"].includes(status)) {
      const labels = {
        uploaded: "◌ Uploaded",
        uploading: "◌ Uploading",
        queued: "◌ Queued",
        transcription_queued: "◌ Transcript queued",
        transcribing: "◌ Transcribing"
      };
      const subs = {
        uploaded: "Awaiting transcription",
        uploading: "Saving private media",
        queued: "Awaiting indexing",
        transcription_queued: "Waiting for ingestion worker",
        transcribing: "Timestamping speech and speakers"
      };
      return {
        filter: "indexing",
        className: "indexing",
        label: labels[status] || "◌ Processing",
        sub: subs[status] || "Processing source"
      };
    }
    return {
      filter: "attention",
      className: "attention",
      label: "! Review",
      sub: status === "upload_failed"
        ? "Upload failed"
        : status === "transcription_failed"
          ? "Transcription failed"
          : "Ingestion needs attention"
    };
  };

  const sourceOrigin = item => {
    if (item.storage_filename) {
      const size = prettyBytes(item.storage_size);
      return `Private upload${size ? " · " + size : ""}`;
    }
    if (item.original_url) {
      try {
        return new URL(item.original_url).hostname.replace(/^www\./, "");
      } catch {}
    }
    if (item.kind === "transcript") return "Pasted source text";
    return "Workspace source";
  };

  function renderMetrics(payload) {
    const values = {
      "source-metric-indexed": payload.indexed,
      "source-metric-uploaded": payload.uploaded,
      "source-metric-total": payload.total,
      "source-metric-attention": payload.needs_attention,
      "source-health-indexed": payload.indexed,
      "source-health-uploaded": payload.uploaded,
      "source-health-attention": payload.needs_attention
    };
    Object.entries(values).forEach(([id, value]) => {
      const node = document.getElementById(id);
      if (node) node.textContent = String(value ?? 0);
    });

    const health = document.getElementById("source-health-percent");
    if (health) {
      const healthy = Number(payload.indexed || 0) + Number(payload.uploaded || 0);
      health.textContent = payload.total ? `${Math.round((healthy / payload.total) * 100)}%` : "100%";
    }
  }

  function renderTabCounts(items) {
    const counts = { all: items.length, video: 0, audio: 0, article: 0, document: 0, watchlist: 0 };
    items.forEach(item => {
      const type = viewType(item.kind);
      if (type in counts) counts[type] += 1;
    });
    Object.entries(counts).forEach(([type, value]) => {
      const id = type === "all" ? "source-tab-all-count" : `source-tab-${type}-count`;
      const node = document.getElementById(id);
      if (node) node.textContent = String(value);
    });
  }

  function renderRows(payload) {
    const list = document.getElementById("source-library-list");
    if (!list) return;
    const items = Array.isArray(payload.sources) ? payload.sources : [];
    renderTabCounts(items);

    if (!items.length) {
      list.innerHTML = '<div class="source-empty-filter">No sources yet. Upload media, paste a transcript, or add a URL to begin.</div>';
      const footer = document.getElementById("source-library-footer-label");
      if (footer) footer.innerHTML = 'Showing <b id="source-visible-count">0</b> workspace sources';
      applyFilters();
      return;
    }

    list.innerHTML = items.map(item => {
      const state = stateFor(item);
      const type = viewType(item.kind);
      const origin = sourceOrigin(item);
      const canCreate = Boolean(item.has_transcript || item.original_url);
      let createAction = "";
      if (canCreate) {
        createAction = `<button data-source-create-existing data-source-id="${escapeHtml(item.id)}" data-source-title="${escapeHtml(item.title || kindLabel(item.kind) + " source")}" data-source-kind="${escapeHtml(item.kind)}" data-source-url="${escapeHtml(item.original_url || "")}">Create story →</button>`;
      } else if (item.status === "uploaded" || item.status === "transcription_failed") {
        if (transcriptionConfig.configured) {
          createAction = `<button data-source-transcribe data-source-id="${escapeHtml(item.id)}">${item.status === "transcription_failed" ? "Retry transcript" : "Transcribe →"}</button>`;
        } else {
          createAction = '<button disabled title="Configure DEEPGRAM_API_KEY in the backend environment">Set up transcription</button>';
        }
      } else if (item.status === "transcription_queued") {
        createAction = '<button disabled>Queued</button>';
      } else if (item.status === "transcribing") {
        createAction = '<button disabled>Transcribing…</button>';
      } else {
        createAction = '<button disabled title="Source text is not available yet">Await processing</button>';
      }

      return `
        <article class="source-row" tabindex="0"
          data-source-id="${escapeHtml(item.id)}"
          data-type="${escapeHtml(type)}"
          data-status="${escapeHtml(state.filter)}"
          data-stories="${Number(item.story_count || 0)}"
          data-created-at="${new Date(item.created_at).getTime() || 0}"
          data-title="${escapeHtml(item.title || kindLabel(item.kind) + " source")}"
          data-origin="${escapeHtml(origin)}">
          <div class="source-main">
            <span class="source-kind ${escapeHtml(type)}">${kindIcon(item.kind)}</span>
            <div><b>${escapeHtml(item.title || kindLabel(item.kind) + " source")}</b><small>${escapeHtml(origin)}</small></div>
          </div>
          <div><span class="source-type-badge">${escapeHtml(kindLabel(item.kind))}</span></div>
          <div><span class="index-state ${state.className}">${state.label}</span><small class="row-sub">${escapeHtml(state.sub)}</small></div>
          <div class="source-story-count"><b>${Number(item.story_count || 0)}</b><small>stories</small></div>
          <div>${item.status === "indexed" ? '<span class="guard-badge pass">✓ Ready</span>' : '<span class="guard-badge muted">Pending</span>'}</div>
          <div class="source-date"><b>${escapeHtml(relativeTime(item.created_at))}</b><small>${escapeHtml(item.status)}</small></div>
          <div class="source-actions">
            <button data-source-open data-source-id="${escapeHtml(item.id)}">Details</button>
            ${createAction}
          </div>
        </article>`;
    }).join("");

    const footer = document.getElementById("source-library-footer-label");
    if (footer) footer.innerHTML = `Showing <b id="source-visible-count">${items.length}</b> workspace source${items.length === 1 ? "" : "s"}`;

    const summary = document.getElementById("source-ingestion-summary");
    if (summary) {
      const waiting = items.filter(item => ["uploaded", "uploading", "queued", "transcription_queued", "transcribing"].includes(item.status)).length;
      summary.innerHTML = waiting
        ? `<span class="activity-dot blue"></span><div><b>${waiting} source${waiting === 1 ? "" : "s"} awaiting processing</b><small>Uploaded files remain private until transcription/indexing completes.</small></div>`
        : '<span class="activity-dot green"></span><div><b>No ingestion backlog</b><small>All current sources are indexed or require explicit review.</small></div>';
    }

    applyFilters();
  }

  function currentRows() {
    return [...document.querySelectorAll("#source-library-list .source-row")];
  }

  function applyFilters() {
    const search = document.getElementById("source-search-input");
    const status = document.getElementById("source-status-filter");
    const q = (search?.value || "").trim().toLowerCase();
    const statusValue = status?.value || "all";

    const rows = currentRows();
    rows.forEach(row => {
      const typeOk = sourceType === "all" || row.dataset.type === sourceType;
      const statusOk = statusValue === "all" || row.dataset.status === statusValue;
      const hay = `${row.dataset.title || ""} ${row.dataset.origin || ""} ${row.dataset.type || ""}`.toLowerCase();
      row.hidden = !(typeOk && statusOk && (!q || hay.includes(q)));
    });

    const visible = rows.filter(row => !row.hidden);
    const count = document.getElementById("source-visible-count");
    if (count) count.textContent = String(visible.length);
    const empty = document.getElementById("source-empty-filter");
    if (empty) empty.hidden = visible.length !== 0 || rows.length === 0;
  }

  function sortRows() {
    const mode = document.getElementById("source-sort")?.value || "recent";
    const list = document.getElementById("source-library-list");
    const rows = currentRows();
    rows.sort((a, b) => {
      if (mode === "stories") return Number(b.dataset.stories || 0) - Number(a.dataset.stories || 0);
      if (mode === "title") return (a.dataset.title || "").localeCompare(b.dataset.title || "");
      return Number(b.dataset.createdAt || 0) - Number(a.dataset.createdAt || 0);
    });
    rows.forEach(row => list?.appendChild(row));
    applyFilters();
  }

  function schedulePoll(items) {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    const active = items.some(item => ["transcription_queued", "transcribing"].includes(item.status));
    if (active) {
      pollTimer = window.setTimeout(() => loadLibrary(), 2500);
    }
  }

  async function queueTranscription(button) {
    const sourceId = button.dataset.sourceId;
    if (!sourceId) return;
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "Queueing…";
    try {
      const response = await fetcher(`${config.apiBase}/sources/${encodeURIComponent(sourceId)}/transcribe`, {
        method: "POST",
        headers: { "Accept": "application/json" }
      });
      let detail = null;
      try { detail = await response.clone().json(); } catch {}
      if (!response.ok) throw new Error(detail?.detail || `Transcription API ${response.status}`);
      toast("Transcription queued");
      await loadLibrary();
    } catch (error) {
      console.error(error);
      toast(error.message || "Could not queue transcription");
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function createStoryFromSource(button) {
    const sourceId = button.dataset.sourceId;
    const sourceTitle = button.dataset.sourceTitle || "Workspace source";
    const sourceKind = button.dataset.sourceKind || "source";
    const sourceUrl = button.dataset.sourceUrl || "";
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "Creating…";

    try {
      const response = await fetcher(`${config.apiBase}/stories`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: sourceId,
          title: `Story from ${sourceTitle}`
        })
      });
      if (!response.ok) throw new Error(`Story API ${response.status}`);
      const story = await response.json();

      window.HeadlineAvenueRuntime.storyId = story.id;
      window.HeadlineAvenueRuntime.sourceId = sourceId;
      window.HeadlineAvenueOpenWorkspace?.(
        story.title,
        `${sourceTitle} · ${kindLabel(sourceKind)}`,
        sourceUrl,
        { storyId: story.id, sourceId }
      );
      window.dispatchEvent(new CustomEvent("ha:story-created", { detail: story }));
      toast("Story Workspace created from persisted source");
      window.setTimeout(loadLibrary, 250);
    } catch (error) {
      console.error(error);
      toast("Could not create story from source");
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function loadLibrary() {
    if (loading) return;
    loading = true;
    const footer = document.getElementById("source-library-footer-label");
    if (footer) footer.textContent = "Loading workspace sources…";

    try {
      const [configResponse, response] = await Promise.all([
        fetcher(`${config.apiBase}/sources/transcription/config`, {
          headers: { "Accept": "application/json" },
          cache: "no-store"
        }),
        fetcher(`${config.apiBase}/sources/library`, {
          headers: { "Accept": "application/json" },
          cache: "no-store"
        })
      ]);
      if (configResponse.ok) {
        transcriptionConfig = await configResponse.json();
      }
      if (!response.ok) throw new Error(`Source Library API ${response.status}`);
      const payload = await response.json();
      renderMetrics(payload);
      renderRows(payload);
      schedulePoll(Array.isArray(payload.sources) ? payload.sources : []);
    } catch (error) {
      console.warn("Workspace Source Library could not load.", error);
      const list = document.getElementById("source-library-list");
      if (list) list.innerHTML = '<div class="source-empty-filter">Source Library unavailable. Check the API connection and try again.</div>';
      if (footer) footer.textContent = "Workspace Source Library unavailable";
    } finally {
      loading = false;
    }
  }

  function boot() {
    document.querySelectorAll("[data-source-tab]").forEach(tab => {
      tab.addEventListener("click", () => {
        document.querySelectorAll("[data-source-tab]").forEach(item => item.classList.remove("active"));
        tab.classList.add("active");
        sourceType = tab.dataset.sourceTab || "all";
        applyFilters();
      });
    });

    document.getElementById("source-search-input")?.addEventListener("input", applyFilters);
    document.getElementById("source-status-filter")?.addEventListener("change", applyFilters);
    document.getElementById("source-sort")?.addEventListener("change", sortRows);
    document.querySelector('[data-view="sources"]')?.addEventListener("click", loadLibrary);
    document.getElementById("load-more-sources")?.addEventListener("click", loadLibrary);

    document.getElementById("source-library-list")?.addEventListener("click", event => {
      const transcribe = event.target.closest("[data-source-transcribe]");
      if (transcribe) {
        queueTranscription(transcribe);
        return;
      }
      const create = event.target.closest("[data-source-create-existing]");
      if (create) {
        createStoryFromSource(create);
        return;
      }
      const open = event.target.closest("[data-source-open]");
      if (open) {
        const row = open.closest(".source-row");
        toast(`${row?.dataset.title || "Source"} · ${row?.dataset.status || "workspace"}`);
        return;
      }
      if (event.target.closest("button,a,input,select,textarea")) return;
      const row = event.target.closest(".source-row");
      if (!row) return;
      currentRows().forEach(item => item.classList.toggle("selected", item === row));
    });

    window.HeadlineAvenueLoadSourceLibrary = loadLibrary;
    loadLibrary();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
