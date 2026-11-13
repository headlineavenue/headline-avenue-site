(() => {
  if (window.HeadlineAvenueConfig) return;

  const localHosts = new Set(["localhost", "127.0.0.1"]);
  const isLocal = localHosts.has(window.location.hostname);
  const apiOrigin = isLocal
    ? `http://${window.location.hostname}:8000`
    : "https://api.headlineavenue.com";

  window.HeadlineAvenueConfig = Object.freeze({
    apiOrigin,
    apiBase: `${apiOrigin}/api/v1`,
    isLocal,
    frontendOrigin: window.location.origin
  });
})();
