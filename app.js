// Headline Avenue frontend bootstrap.
// Keep the proven product-demo interactions in app-core.js and layer the
// source/editorial intelligence integrations on top without duplicating the UI app.
(() => {
  window.HeadlineAvenueRuntime = window.HeadlineAvenueRuntime || {
    sourceId: null,
    storyId: null,
    analysis: null,
    selectedAngle: null,
    editorialVariants: null,
    editorialSelection: null,
    editorialGate: null,
    publishDraft: null
  };

  // Publish desk UX polish: keep the desktop right rail together as one sticky
  // viewport-height unit. The timeline gets its own fixed grid row beneath the
  // inspector, while only the inspector body is allowed to scroll internally.
  // This prevents the timeline from travelling upward behind the sticky card.
  if (!document.getElementById("ha-publish-rail-polish")) {
    const style = document.createElement("style");
    style.id = "ha-publish-rail-polish";
    style.textContent = `
      @media (min-width: 1251px) {
        .publisher-aside {
          position: sticky !important;
          top: 18px !important;
          align-self: start;
          height: calc(100vh - 36px);
          max-height: calc(100vh - 36px);
          min-height: 0;
          grid-template-rows: minmax(0, 1fr) auto;
          gap: 10px;
          overflow: visible !important;
          padding-right: 0;
        }

        .publisher-aside .publish-inspector {
          position: static !important;
          top: auto !important;
          z-index: 2;
          min-height: 0;
          max-height: none;
          overflow-y: auto;
          overscroll-behavior: contain;
          scrollbar-gutter: stable;
          scrollbar-width: thin;
          scrollbar-color: rgba(78, 233, 255, .22) transparent;
        }

        .publisher-aside .publish-inspector > .publish-card-title {
          position: sticky;
          top: 0;
          z-index: 6;
          padding-bottom: 10px;
          background: linear-gradient(180deg, rgba(10, 20, 35, .995), rgba(7, 15, 26, .97));
          border-bottom: 1px solid rgba(255, 255, 255, .055);
          box-shadow: 0 8px 14px rgba(2, 5, 10, .24);
        }

        .publisher-aside .publish-inspector::-webkit-scrollbar {
          width: 7px;
        }

        .publisher-aside .publish-inspector::-webkit-scrollbar-track {
          background: transparent;
        }

        .publisher-aside .publish-inspector::-webkit-scrollbar-thumb {
          background: rgba(78, 233, 255, .18);
          border-radius: 999px;
        }

        .publisher-aside .publish-inspector::-webkit-scrollbar-thumb:hover {
          background: rgba(78, 233, 255, .30);
        }

        .publisher-aside .today-schedule {
          position: relative;
          z-index: 3;
          align-self: end;
        }
      }
    `;
    document.head.appendChild(style);
  }

  const nativeFetch = window.fetch.bind(window);
  window.__haNativeFetch = nativeFetch;

  // Observe the real API records created by the existing Create workflow so
  // the intelligence layers can act on the exact Story that was just saved.
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);

    try {
      const input = args[0];
      const options = args[1] || {};
      const url = typeof input === "string" ? input : input?.url || "";
      const method = String(options.method || input?.method || "GET").toUpperCase();
      const path = new URL(url, window.location.href).pathname.replace(/\/$/, "");

      if (response.ok && method === "POST" && path === "/api/v1/sources") {
        response.clone().json().then(data => {
          if (data?.id) window.HeadlineAvenueRuntime.sourceId = data.id;
        }).catch(() => {});
      }

      if (response.ok && method === "POST" && path === "/api/v1/stories") {
        response.clone().json().then(data => {
          if (!data?.id) return;
          window.HeadlineAvenueRuntime.storyId = data.id;
          window.HeadlineAvenueRuntime.sourceId = data.source_id || window.HeadlineAvenueRuntime.sourceId;
          window.HeadlineAvenueRuntime.editorialSelection = null;
          window.HeadlineAvenueRuntime.editorialGate = null;
          window.HeadlineAvenueRuntime.publishDraft = null;
          window.dispatchEvent(new CustomEvent("ha:story-created", { detail: data }));
        }).catch(() => {});
      }
    } catch (error) {
      console.debug("Headline Avenue runtime observer skipped a response.", error);
    }

    return response;
  };

  let domReady = false;
  document.addEventListener("DOMContentLoaded", () => { domReady = true; }, { once: true });

  const version = "20260911-0105";
  Promise.all([
    nativeFetch(`app-core.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load app-core.js");
      return r.text();
    }),
    nativeFetch(`session-persistence.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load session-persistence.js");
      return r.text();
    }),
    nativeFetch(`story-intelligence.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load story-intelligence.js");
      return r.text();
    }),
    nativeFetch(`editorial-intelligence.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load editorial-intelligence.js");
      return r.text();
    }),
    nativeFetch(`editorial-gating.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load editorial-gating.js");
      return r.text();
    }),
    nativeFetch(`editorial-restore.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load editorial-restore.js");
      return r.text();
    }),
    nativeFetch(`story-pack-sync.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load story-pack-sync.js");
      return r.text();
    }),
    nativeFetch(`publish-bridge.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load publish-bridge.js");
      return r.text();
    }),
    nativeFetch(`publish-recovery-v2.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load publish-recovery-v2.js");
      return r.text();
    }),
    nativeFetch(`publish-pipeline.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load publish-pipeline.js");
      return r.text();
    }),
    nativeFetch(`publish-accounts.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load publish-accounts.js");
      return r.text();
    })
  ]).then(([core, persistence, intelligence, editorial, gating, restore, storyPackSync, publishBridge, publishRecovery, publishPipeline, publishAccounts]) => {
    (0, eval)(core);
    (0, eval)(persistence);
    (0, eval)(intelligence);
    (0, eval)(editorial);
    (0, eval)(gating);
    (0, eval)(restore);
    (0, eval)(storyPackSync);
    (0, eval)(publishBridge);
    (0, eval)(publishRecovery);
    (0, eval)(publishPipeline);
    (0, eval)(publishAccounts);

    // app.js is a defer script. Usually the natural DOMContentLoaded event has
    // not fired yet; if network loading took longer, replay it once so all
    // boot layers initialize in the same order.
    if (domReady) document.dispatchEvent(new Event("DOMContentLoaded"));
  }).catch(error => {
    console.error("Headline Avenue frontend failed to boot:", error);
  });
})();