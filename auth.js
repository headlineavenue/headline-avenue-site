(() => {
  const config = window.HeadlineAvenueConfig;
  if (!config) throw new Error("Headline Avenue runtime configuration is missing");

  const auth = {
    user: null,
    workspaces: [],
    activeWorkspaceId: null,
    csrfToken: null
  };
  window.HeadlineAvenueAuth = auth;

  let resolveReady;
  window.HeadlineAvenueAuthReady = new Promise(resolve => { resolveReady = resolve; });
  let readyResolved = false;

  const savedWorkspaceKey = "headline-avenue.active-workspace-id";

  async function authApi(path, options = {}) {
    const response = await fetch(`${config.apiBase}${path}`, {
      ...options,
      credentials: "include",
      headers: {
        "Accept": "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {})
      }
    });

    let body = null;
    if (response.status !== 204) {
      try { body = await response.json(); } catch {}
    }
    if (!response.ok) {
      const error = new Error(body?.detail || `Authentication request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  function chooseWorkspace(data) {
    const stored = window.localStorage.getItem(savedWorkspaceKey);
    const validStored = data.workspaces?.some(item => item.workspace_id === stored);
    return validStored ? stored : data.active_workspace_id;
  }

  function applySession(data) {
    auth.user = data.user;
    auth.workspaces = Array.isArray(data.workspaces) ? data.workspaces : [];
    auth.activeWorkspaceId = chooseWorkspace(data);
    auth.csrfToken = data.csrf_token;
    if (auth.activeWorkspaceId) {
      window.localStorage.setItem(savedWorkspaceKey, auth.activeWorkspaceId);
    }
    syncAccountChrome();
    if (!readyResolved) {
      readyResolved = true;
      resolveReady(auth);
      window.dispatchEvent(new CustomEvent("ha:auth-ready", { detail: auth }));
    } else {
      window.dispatchEvent(new CustomEvent("ha:workspace-changed", { detail: auth }));
    }
  }

  function injectStyles() {
    if (document.getElementById("ha-auth-styles")) return;
    const style = document.createElement("style");
    style.id = "ha-auth-styles";
    style.textContent = `
      .ha-auth-gate{position:fixed;inset:0;z-index:20000;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at 30% 10%,rgba(25,118,210,.12),transparent 36%),#02050a;color:#eaf7ff;font-family:Inter,system-ui,sans-serif}
      .ha-auth-card{width:min(430px,94vw);border:1px solid rgba(95,231,255,.16);border-radius:20px;padding:28px;background:linear-gradient(180deg,#091625,#050b12);box-shadow:0 30px 100px rgba(0,0,0,.58)}
      .ha-auth-brand{display:flex;align-items:center;gap:12px;margin-bottom:22px}.ha-auth-brand img{width:42px;height:42px;border-radius:11px}.ha-auth-brand b{display:block;font-size:15px;letter-spacing:.08em}.ha-auth-brand small{color:#678398;font-size:10px;letter-spacing:.12em}
      .ha-auth-tabs{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:4px;border:1px solid rgba(255,255,255,.06);border-radius:11px;background:rgba(255,255,255,.02);margin-bottom:18px}.ha-auth-tabs button{border:0;border-radius:8px;padding:9px;background:transparent;color:#708a9f;font-weight:800;font-size:10px;cursor:pointer}.ha-auth-tabs button.active{background:rgba(61,196,255,.1);color:#8be9ff}
      .ha-auth-card h1{margin:0 0 6px;font-size:22px}.ha-auth-card>p{margin:0 0 18px;color:#7892a6;font-size:11px;line-height:1.5}.ha-auth-form{display:grid;gap:11px}.ha-auth-field{display:grid;gap:5px}.ha-auth-field span{color:#7892a6;font-size:9px;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.ha-auth-field input{width:100%;box-sizing:border-box;border:1px solid rgba(255,255,255,.09);border-radius:10px;padding:11px 12px;background:#050c14;color:#edf9ff;outline:none}.ha-auth-field input:focus{border-color:rgba(95,231,255,.38);box-shadow:0 0 0 3px rgba(95,231,255,.05)}
      .ha-auth-submit{margin-top:4px;border:0;border-radius:10px;padding:11px 14px;background:linear-gradient(135deg,#5fe7ff,#1679ff);color:#001018;font-weight:900;cursor:pointer}.ha-auth-submit:disabled{opacity:.55;cursor:wait}.ha-auth-error{min-height:16px;color:#ff9a9a;font-size:10px;line-height:1.4}.ha-auth-note{margin-top:14px;color:#587287;font-size:9px;line-height:1.5}
      .ha-account-tools{display:flex;align-items:center;gap:8px;margin-left:10px}.ha-workspace-select,.ha-signout{border:1px solid rgba(255,255,255,.08);border-radius:8px;background:#07111c;color:#9bb2c3;font-size:9px;padding:6px 8px}.ha-signout{cursor:pointer}.ha-signout:hover{color:#eaf7ff;border-color:rgba(95,231,255,.22)}
      @media(max-width:720px){.ha-auth-gate{padding:12px}.ha-auth-card{padding:21px}.ha-account-tools{display:none}}
    `;
    document.head.appendChild(style);
  }

  function gateMarkup(mode = "login") {
    const register = mode === "register";
    return `
      <div class="ha-auth-gate" id="ha-auth-gate">
        <section class="ha-auth-card">
          <div class="ha-auth-brand"><img src="assets/headline-avenue-logo.png" alt=""><div><b>HEADLINE AVENUE</b><small>EDITORIAL OS</small></div></div>
          <div class="ha-auth-tabs"><button type="button" data-auth-mode="login" class="${register ? "" : "active"}">Sign in</button><button type="button" data-auth-mode="register" class="${register ? "active" : ""}">Create account</button></div>
          <h1>${register ? "Create your workspace" : "Welcome back"}</h1>
          <p>${register ? "Start a private editorial workspace for sources, stories and connected publishing accounts." : "Sign in to your Headline Avenue workspace."}</p>
          <form class="ha-auth-form" data-auth-form="${mode}">
            ${register ? '<label class="ha-auth-field"><span>Name</span><input name="display_name" autocomplete="name" required minlength="2"></label><label class="ha-auth-field"><span>Workspace name</span><input name="workspace_name" required minlength="2" placeholder="Headline Avenue"></label>' : ""}
            <label class="ha-auth-field"><span>Email</span><input name="email" type="email" autocomplete="email" required></label>
            <label class="ha-auth-field"><span>Password</span><input name="password" type="password" autocomplete="${register ? "new-password" : "current-password"}" required minlength="${register ? "12" : "1"}"></label>
            <div class="ha-auth-error" data-auth-error></div>
            <button class="ha-auth-submit" type="submit">${register ? "Create workspace" : "Sign in"}</button>
          </form>
          <div class="ha-auth-note">Sessions are stored server-side. Social platform credentials remain backend-only.</div>
        </section>
      </div>`;
  }

  function showGate(mode = "login") {
    injectStyles();
    document.getElementById("ha-auth-gate")?.remove();
    document.body.insertAdjacentHTML("beforeend", gateMarkup(mode));

    document.querySelectorAll("[data-auth-mode]").forEach(button => {
      button.addEventListener("click", () => showGate(button.dataset.authMode));
    });

    document.querySelector("[data-auth-form]")?.addEventListener("submit", handleSubmit);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const mode = form.dataset.authForm;
    const button = form.querySelector(".ha-auth-submit");
    const error = form.querySelector("[data-auth-error]");
    const data = Object.fromEntries(new FormData(form).entries());

    button.disabled = true;
    button.textContent = mode === "register" ? "Creating…" : "Signing in…";
    error.textContent = "";

    try {
      await authApi(mode === "register" ? "/auth/register" : "/auth/login", {
        method: "POST",
        body: JSON.stringify(data)
      });

      // Re-read the session from the server instead of trusting only the login
      // response. This catches browsers that block the cross-origin session
      // cookie before the rest of the application starts.
      const verified = await authApi("/auth/me");
      applySession(verified);
      document.getElementById("ha-auth-gate")?.remove();
    } catch (err) {
      error.textContent = err.status === 401
        ? "Email or password is incorrect."
        : err.message;
      button.disabled = false;
      button.textContent = mode === "register" ? "Create workspace" : "Sign in";
    }
  }

  function syncAccountChrome() {
    const userCard = document.querySelector(".app-user");
    if (!userCard || !auth.user) return;

    const initials = auth.user.display_name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(part => part[0]?.toUpperCase() || "")
      .join("") || "HA";

    const avatar = userCard.querySelector(":scope > span");
    const name = userCard.querySelector("b");
    const subtitle = userCard.querySelector("small");
    if (avatar) avatar.textContent = initials;
    if (name) name.textContent = auth.user.display_name;

    const active = auth.workspaces.find(item => item.workspace_id === auth.activeWorkspaceId);
    if (subtitle) subtitle.textContent = active?.workspace_name || "Workspace";

    let tools = document.querySelector(".ha-account-tools");
    if (!tools) {
      tools = document.createElement("div");
      tools.className = "ha-account-tools";
      userCard.insertAdjacentElement("afterend", tools);
    }

    const workspaceOptions = auth.workspaces.map(item =>
      `<option value="${item.workspace_id}" ${item.workspace_id === auth.activeWorkspaceId ? "selected" : ""}>${escapeHtml(item.workspace_name)}</option>`
    ).join("");

    tools.innerHTML = `
      ${auth.workspaces.length > 1 ? `<select class="ha-workspace-select" aria-label="Active workspace">${workspaceOptions}</select>` : ""}
      <button type="button" class="ha-signout">Sign out</button>`;

    tools.querySelector(".ha-workspace-select")?.addEventListener("change", event => {
      auth.activeWorkspaceId = event.target.value;
      window.localStorage.setItem(savedWorkspaceKey, auth.activeWorkspaceId);
      auth.csrfToken = null;
      window.location.reload();
    });

    tools.querySelector(".ha-signout")?.addEventListener("click", logout);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function logout() {
    try {
      await authApi("/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": auth.csrfToken || "" }
      });
    } catch (error) {
      console.warn("Headline Avenue logout request failed:", error);
    } finally {
      auth.user = null;
      auth.workspaces = [];
      auth.activeWorkspaceId = null;
      auth.csrfToken = null;
      window.sessionStorage.clear();
      window.location.reload();
    }
  }

  window.HeadlineAvenueLogout = logout;

  injectStyles();
  authApi("/auth/me")
    .then(applySession)
    .catch(error => {
      if (error.status !== 401) console.warn("Headline Avenue session check failed:", error);
      showGate("login");
    });
})();
