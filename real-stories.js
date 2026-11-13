(() => {
  const config = window.HeadlineAvenueConfig;
  if (!config?.apiBase) return;

  const fetcher = window.__haNativeFetch || window.fetch.bind(window);
  let loading = false;

  const escapeHtml = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const prettyKind = value => {
    const kind = String(value || "source").toLowerCase();
    return {
      url: "Web",
      video: "Video",
      audio: "Audio",
      article: "Article",
      pdf: "PDF",
      transcript: "Transcript"
    }[kind] || kind.charAt(0).toUpperCase() + kind.slice(1);
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

  const rowStatus = item => {
    if (item.publish_status === "scheduled" || item.story_status === "scheduled") {
      return { key: "scheduled", label: "Scheduled", className: "scheduled" };
    }
    if (item.story_status === "needs_review" || item.sourceguard_status === "needs_review") {
      return { key: "review", label: "Needs review", className: "review" };
    }
    return { key: "active", label: "Active", className: "active" };
  };

  const guardBadge = item => {
    if (item.sourceguard_status === "supported") {
      return '<span class="guard-badge pass">✓ Supported</span>';
    }
    if (item.sourceguard_status === "needs_review") {
      return '<span class="guard-badge warn">! Review</span>';
    }
    return '<span class="guard-badge muted">Pending</span>';
  };

  const publishBadge = item => {
    const status = String(item.publish_status || "drafting");
    if (status === "scheduled") {
      const count = Number(item.scheduled_count || 0);
      return `<span class="publish-state ready">${count || 1} scheduled</span>`;
    }
    if (status === "queued") return '<span class="publish-state ready">Queued</span>';
    if (status === "published") return '<span class="publish-state ready">Published</span>';
    if (status === "blocked") return '<span class="publish-state holding">Blocked</span>';
    return '<span class="publish-state drafting">Drafting</span>';
  };

  function renderMetrics(payload) {
    const values = {
      "story-metric-active": payload.active,
      "story-metric-review": payload.needs_review,
      "story-metric-packs": payload.story_packs,
      "story-metric-scheduled": payload.scheduled,
      "story-tab-all-count": payload.total,
      "story-tab-active-count": payload.active,
      "story-tab-review-count": payload.needs_review,
      "story-tab-scheduled-count": payload.scheduled
    };
    Object.entries(values).forEach(([id, value]) => {
      const node = document.getElementById(id);
      if (node) node.textContent = String(value ?? 0);
    });
  }

  function renderRows(payload) {
    const list = document.getElementById("stories-list");
    if (!list) return;

    const stories = Array.isArray(payload.stories) ? payload.stories : [];
    if (!stories.length) {
      list.innerHTML = "";
      const empty = document.getElementById("story-empty-filter");
      if (empty) {
        empty.hidden = false;
        empty.textContent = "No stories yet. Create your first story from a source.";
      }
      const footer = document.getElementById("story-desk-footer-label");
      if (footer) footer.innerHTML = 'Showing <b id="story-visible-count">0</b> workspace stories';
      window.HeadlineAvenueRefreshStoryDesk?.();
      return;
    }

    list.innerHTML = stories.map((item, index) => {
      const status = rowStatus(item);
      const score = Math.round(Number(item.signal_score || 0));
      const scoreClass = score >= 90 ? " high" : "";
      const sourceTitle = item.source_title || `${prettyKind(item.source_kind)} source`;
      const sourceSubtitle = `${prettyKind(item.source_kind)} · ${item.source_status || "indexed"}`;
      const action = status.key === "review" ? "Review →" : "Open →";
      return `
        <article class="newsroom-row${index === 0 ? " selected" : ""}" tabindex="0"
          data-story-id="${escapeHtml(item.id)}"
          data-source-id="${escapeHtml(item.source_id)}"
          data-status="${status.key}"
          data-topic="general"
          data-score="${score}"
          data-created-at="${new Date(item.created_at).getTime() || 0}"
          data-title="${escapeHtml(item.title)}"
          data-source="${escapeHtml(sourceTitle)}">
          <div class="story-cell-main">
            <span class="story-signal${scoreClass}">${score || "—"}</span>
            <div>
              <b>${escapeHtml(item.title)}</b>
              <small>${escapeHtml(relativeTime(item.created_at))} · ${escapeHtml(item.story_status || "draft")}</small>
            </div>
          </div>
          <div class="source-cell">
            <b>${escapeHtml(sourceTitle)}</b>
            <small>${escapeHtml(sourceSubtitle)}</small>
          </div>
          <div><span class="desk-status ${status.className}">${status.label}</span></div>
          <div>${guardBadge(item)}</div>
          <div class="output-count"><b>${Number(item.output_count || 0)}</b><small>assets</small></div>
          <div>${publishBadge(item)}</div>
          <div>
            <button class="row-action" data-open-story
              data-story-id="${escapeHtml(item.id)}"
              data-source-id="${escapeHtml(item.source_id)}"
              data-story-title="${escapeHtml(item.title)}"
              data-story-source="${escapeHtml(sourceTitle + " · " + prettyKind(item.source_kind))}">${action}</button>
          </div>
        </article>`;
    }).join("");

    const footer = document.getElementById("story-desk-footer-label");
    if (footer) {
      footer.innerHTML = `Showing <b id="story-visible-count">${stories.length}</b> workspace stor${stories.length === 1 ? "y" : "ies"}`;
    }

    const empty = document.getElementById("story-empty-filter");
    if (empty) {
      empty.hidden = true;
      empty.textContent = "No stories match these filters.";
    }

    window.HeadlineAvenueRefreshStoryDesk?.();
  }

  function renderInsights(payload) {
    const aside = document.querySelector("#view-stories .desk-insights");
    if (!aside) return;

    const stories = Array.isArray(payload.stories) ? payload.stories : [];
    const supported = stories.filter(item => item.sourceguard_status === "supported").length;
    const latest = stories.slice(0, 3);

    const attentionBody = payload.needs_review
      ? `<button data-jump-review><span class="attention-icon">!</span><div><b>${payload.needs_review} stor${payload.needs_review === 1 ? "y needs" : "ies need"} review</b><small>SourceGuard or editorial approval</small></div><em>Review</em></button>`
      : '<div class="activity-item"><span class="activity-dot green"></span><div><b>No review blockers</b><small>Workspace desk is clear</small></div></div>';

    const recentBody = latest.length
      ? latest.map(item => `<div class="activity-item"><span class="activity-dot blue"></span><div><b>${escapeHtml(item.title)}</b><small>${escapeHtml(relativeTime(item.created_at))} · ${escapeHtml(item.story_status)}</small></div></div>`).join("")
      : '<div class="activity-item"><span class="activity-dot blue"></span><div><b>No recent stories</b><small>Create a story to begin the desk history.</small></div></div>';

    aside.innerHTML = `
      <article class="insight-card attention">
        <div class="insight-head"><span>NEEDS ATTENTION</span><b>${payload.needs_review}</b></div>
        ${attentionBody}
      </article>

      <article class="insight-card">
        <div class="insight-head"><span>WORKSPACE PULSE</span><small>LIVE</small></div>
        <div class="pulse-stat"><span>Total stories</span><b>${payload.total}</b></div>
        <div class="pulse-stat"><span>Generated assets</span><b>${payload.story_packs}</b></div>
        <div class="pulse-stat"><span>SourceGuard supported</span><b class="green">${supported}</b></div>
        <div class="pulse-stat"><span>Scheduled stories</span><b>${payload.scheduled}</b></div>
      </article>

      <article class="insight-card">
        <div class="insight-head"><span>RECENT ACTIVITY</span><small>WORKSPACE</small></div>
        ${recentBody}
      </article>`;

    aside.querySelector("[data-jump-review]")?.addEventListener("click", () => {
      document.querySelector('[data-story-tab="review"]')?.click();
    });
  }

  async function loadDesk() {
    if (loading) return;
    loading = true;
    const footer = document.getElementById("story-desk-footer-label");
    if (footer) footer.textContent = "Loading workspace stories…";

    try {
      const response = await fetcher(`${config.apiBase}/stories/desk`, {
        headers: { "Accept": "application/json" },
        cache: "no-store"
      });
      if (!response.ok) throw new Error(`Story Desk API ${response.status}`);
      const payload = await response.json();
      renderMetrics(payload);
      renderRows(payload);
      renderInsights(payload);
    } catch (error) {
      console.warn("Workspace Story Desk could not load.", error);
      const list = document.getElementById("stories-list");
      if (list) list.innerHTML = '<div class="story-empty-filter">Story Desk unavailable. Check the API connection and try again.</div>';
      if (footer) footer.textContent = "Workspace Story Desk unavailable";
      ["story-metric-active","story-metric-review","story-metric-packs","story-metric-scheduled",
       "story-tab-all-count","story-tab-active-count","story-tab-review-count","story-tab-scheduled-count"]
        .forEach(id => { const node = document.getElementById(id); if (node) node.textContent = "—"; });
    } finally {
      loading = false;
    }
  }

  function boot() {
    document.querySelector('[data-view="stories"]')?.addEventListener("click", loadDesk);
    document.getElementById("load-more-stories")?.addEventListener("click", loadDesk);
    window.addEventListener("ha:story-created", event => {
      if (event.detail?.__haOpenedFromDesk) return;
      window.setTimeout(loadDesk, 180);
    });
    window.HeadlineAvenueLoadStoryDesk = loadDesk;
    loadDesk();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
