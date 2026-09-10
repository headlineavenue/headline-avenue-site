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
    editorialGate: null
  };

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

  const version = "20260910-1515";
  Promise.all([
    nativeFetch(`app-core.js?v=${version}`, { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load app-core.js");
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
    })
  ]).then(([core, intelligence, editorial, gating]) => {
    (0, eval)(core);
    (0, eval)(intelligence);
    (0, eval)(editorial);
    (0, eval)(gating);

    // app.js is a defer script. Usually the natural DOMContentLoaded event has
    // not fired yet; if network loading took longer, replay it once so all
    // boot layers initialize in the same order.
    if (domReady) document.dispatchEvent(new Event("DOMContentLoaded"));
  }).catch(error => {
    console.error("Headline Avenue frontend failed to boot:", error);
  });
})();
