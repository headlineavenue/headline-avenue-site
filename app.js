// Headline Avenue frontend bootstrap.
// Keep the proven product-demo interactions in app-core.js and layer the
// source-intelligence integration on top without duplicating the full UI app.
(() => {
  window.HeadlineAvenueRuntime = window.HeadlineAvenueRuntime || {
    sourceId: null,
    storyId: null,
    analysis: null
  };

  const nativeFetch = window.fetch.bind(window);
  window.__haNativeFetch = nativeFetch;

  // Observe the real API records created by the existing Create workflow so
  // the intelligence layer can analyze the exact Story that was just saved.
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

  Promise.all([
    nativeFetch("app-core.js?v=20260910-0535", { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load app-core.js");
      return r.text();
    }),
    nativeFetch("story-intelligence.js?v=20260910-0535", { cache: "no-store" }).then(r => {
      if (!r.ok) throw new Error("Could not load story-intelligence.js");
      return r.text();
    })
  ]).then(([core, intelligence]) => {
    (0, eval)(core);
    (0, eval)(intelligence);

    // app.js is a defer script. Usually the natural DOMContentLoaded event has
    // not fired yet; if network loading took longer, replay it once so both
    // boot layers initialize in the same order.
    if (domReady) document.dispatchEvent(new Event("DOMContentLoaded"));
  }).catch(error => {
    console.error("Headline Avenue frontend failed to boot:", error);
  });
})();
