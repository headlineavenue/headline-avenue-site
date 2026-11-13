(() => {
  if (window.HeadlineAvenueConfig) return;

  const localHosts = new Set(["localhost", "127.0.0.1"]);
  const isLocal = localHosts.has(window.location.hostname);
  const apiOrigin = isLocal
    ? "http://127.0.0.1:8000"
    : "https://headline-avenue-site-production.up.railway.app";

  window.HeadlineAvenueConfig = Object.freeze({
    apiOrigin,
    apiBase: `${apiOrigin}/api/v1`,
    isLocal,
    frontendOrigin: window.location.origin
  });
})();
