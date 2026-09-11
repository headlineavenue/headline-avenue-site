// Headline Avenue destination manager.
// This layer makes the Publish > Manage control functional while keeping
// external posting disabled until provider OAuth adapters are wired.
document.addEventListener("DOMContentLoaded", () => {
  const manageButton = document.getElementById("manage-destinations");
  if (!manageButton) return;

  injectStyles();

  const platforms = [
    {
      id: "youtube",
      name: "YouTube",
      badge: "YT",
      state: "Prototype connection",
      tone: "connected",
      account: "Headline Avenue",
      detail: "Internal queue is enabled. Live OAuth + YouTube upload delivery is the next provider step.",
      permissions: "Upload videos · channel identity",
      action: "Prepare OAuth"
    },
    {
      id: "instagram",
      name: "Instagram",
      badge: "IG",
      state: "Prototype connection",
      tone: "connected",
      account: "@headlineavenue",
      detail: "Internal queue is enabled. Meta authorization and Reels publishing are not live yet.",
      permissions: "Publish Reels · account identity",
      action: "Prepare OAuth"
    },
    {
      id: "tiktok",
      name: "TikTok",
      badge: "TT",
      state: "Sandbox",
      tone: "sandbox",
      account: "@headlineavenu",
      detail: "TikTok remains sandbox-only. Login Kit and Content Posting authorization will be wired before production delivery.",
      permissions: "user.info.basic · video.publish",
      action: "Configure sandbox"
    }
  ];

  function showToast(message, timeout = 3200) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), timeout);
  }

  function closeModal() {
    const overlay = document.getElementById("ha-destination-manager");
    if (!overlay) return;
    overlay.classList.remove("show");
    window.setTimeout(() => overlay.remove(), 150);
  }

  function openModal(focusPlatform = null) {
    document.getElementById("ha-destination-manager")?.remove();

    const overlay = document.createElement("div");
    overlay.id = "ha-destination-manager";
    overlay.className = "ha-destination-overlay";
    overlay.innerHTML = `
      <section class="ha-destination-dialog" role="dialog" aria-modal="true" aria-labelledby="ha-destination-title">
        <header class="ha-destination-head">
          <div>
            <span class="ha-destination-kicker">PUBLISH / AUTHORIZED DESTINATIONS</span>
            <h2 id="ha-destination-title">Manage connected accounts</h2>
            <p>Control which platform accounts Headline Avenue may use for user-approved distribution.</p>
          </div>
          <button class="ha-destination-close" type="button" aria-label="Close">×</button>
        </header>

        <div class="ha-destination-safety">
          <span>CONTROLLED DELIVERY</span>
          <b>No content is sent from this screen.</b>
          <small>Publishing still requires Story Pack approval, destination selection, preflight, and final confirmation.</small>
        </div>

        <div class="ha-destination-list">
          ${platforms.map(platform => `
            <article class="ha-provider ${focusPlatform === platform.id ? "focused" : ""}" data-provider="${platform.id}">
              <div class="ha-provider-icon ${platform.id}">${platform.badge}</div>
              <div class="ha-provider-copy">
                <div class="ha-provider-title">
                  <strong>${platform.name}</strong>
                  <span class="${platform.tone}">${platform.state}</span>
                </div>
                <b>${platform.account}</b>
                <p>${platform.detail}</p>
                <small>${platform.permissions}</small>
              </div>
              <button type="button" data-provider-action="${platform.id}">${platform.action}</button>
            </article>`).join("")}
        </div>

        <div class="ha-destination-next">
          <div>
            <span>NEXT INTEGRATION LAYER</span>
            <b>Provider OAuth + token-safe backend authorization</b>
            <small>Once enabled, each provider will connect through its own consent flow and Headline Avenue will store authorization server-side only.</small>
          </div>
          <span class="ha-destination-lock">LOCKED</span>
        </div>

        <footer class="ha-destination-foot">
          <span>Revocation and account switching will live here once provider authorization is enabled.</span>
          <button type="button" class="ha-destination-done">Done</button>
        </footer>
      </section>`;

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add("show"));

    overlay.querySelector(".ha-destination-close")?.addEventListener("click", closeModal);
    overlay.querySelector(".ha-destination-done")?.addEventListener("click", closeModal);
    overlay.addEventListener("click", event => {
      if (event.target === overlay) closeModal();
    });

    overlay.querySelectorAll("[data-provider-action]").forEach(button => {
      button.addEventListener("click", () => {
        const provider = platforms.find(item => item.id === button.dataset.providerAction);
        if (!provider) return;
        showToast(`${provider.name} authorization is staged next — no external account action was taken.`);
      });
    });
  }

  manageButton.addEventListener("click", event => {
    event.preventDefault();
    openModal();
  });

  document.querySelectorAll(".destination-card[data-destination]").forEach(card => {
    card.addEventListener("dblclick", event => {
      event.preventDefault();
      event.stopPropagation();
      openModal(String(card.dataset.destination || "").toLowerCase());
    });
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closeModal();
  });

  function injectStyles() {
    if (document.getElementById("ha-destination-manager-styles")) return;
    const style = document.createElement("style");
    style.id = "ha-destination-manager-styles";
    style.textContent = `
      .ha-destination-overlay{position:fixed;inset:0;z-index:10020;display:grid;place-items:center;padding:24px;background:rgba(0,4,9,.8);backdrop-filter:blur(10px);opacity:0;transition:opacity .15s ease}
      .ha-destination-overlay.show{opacity:1}
      .ha-destination-dialog{width:min(760px,96vw);max-height:90vh;overflow:auto;border:1px solid rgba(71,181,235,.24);border-radius:18px;background:linear-gradient(180deg,#091625 0%,#050c14 100%);box-shadow:0 30px 90px rgba(0,0,0,.58);color:#ecf8ff}
      .ha-destination-head{display:flex;justify-content:space-between;gap:24px;padding:24px 24px 18px;border-bottom:1px solid rgba(255,255,255,.07)}
      .ha-destination-head h2{margin:4px 0 6px;font-size:23px}.ha-destination-head p{margin:0;color:#88a2b5;font-size:12px;line-height:1.5}
      .ha-destination-kicker{font-size:9px;letter-spacing:.13em;font-weight:900;color:#ffd24a}.ha-destination-close{border:0;background:transparent;color:#8299aa;font-size:26px;cursor:pointer}
      .ha-destination-safety{display:grid;gap:4px;margin:18px 24px 10px;padding:13px 14px;border:1px solid rgba(80,229,161,.17);border-radius:11px;background:rgba(80,229,161,.045)}
      .ha-destination-safety span,.ha-destination-next span:first-child{font-size:9px;letter-spacing:.11em;font-weight:900;color:#58dda1}.ha-destination-safety b{font-size:12px}.ha-destination-safety small{color:#7792a5;line-height:1.45}
      .ha-destination-list{display:grid;gap:9px;padding:10px 24px 18px}.ha-provider{display:grid;grid-template-columns:42px minmax(0,1fr) auto;gap:13px;align-items:center;padding:14px;border:1px solid rgba(255,255,255,.075);border-radius:13px;background:rgba(255,255,255,.018);transition:.16s}
      .ha-provider.focused{border-color:rgba(78,233,255,.34);box-shadow:0 0 0 2px rgba(78,233,255,.05)}.ha-provider-icon{width:40px;height:40px;display:grid;place-items:center;border-radius:10px;font-size:10px;font-weight:900;border:1px solid rgba(255,255,255,.08)}
      .ha-provider-icon.youtube{color:#ff8b8b;background:rgba(255,70,70,.06)}.ha-provider-icon.instagram{color:#dfa1ff;background:rgba(205,105,255,.06)}.ha-provider-icon.tiktok{color:#7feeff;background:rgba(0,225,255,.05)}
      .ha-provider-copy{display:grid;min-width:0}.ha-provider-title{display:flex;align-items:center;gap:8px}.ha-provider-title strong{font-size:13px}.ha-provider-title span{padding:3px 6px;border-radius:999px;font-size:8px;font-weight:800}.ha-provider-title .connected{color:#61e2a8;background:rgba(80,229,161,.07)}.ha-provider-title .sandbox{color:#ffd24a;background:rgba(255,210,74,.07)}
      .ha-provider-copy>b{margin-top:4px;color:#a8bbca;font-size:10px}.ha-provider-copy p{margin:5px 0;color:#718a9d;font-size:10px;line-height:1.45}.ha-provider-copy small{color:#587287;font-size:9px}.ha-provider>button{padding:9px 10px;border:1px solid rgba(78,233,255,.16);border-radius:9px;background:rgba(0,183,255,.055);color:#7edfff;font-size:9px;cursor:pointer;white-space:nowrap}.ha-provider>button:hover{background:rgba(0,183,255,.1);color:#dff8ff}
      .ha-destination-next{display:flex;justify-content:space-between;gap:18px;align-items:center;margin:0 24px 18px;padding:14px;border:1px dashed rgba(255,255,255,.1);border-radius:12px;background:rgba(0,0,0,.12)}.ha-destination-next>div{display:grid;gap:4px}.ha-destination-next b{font-size:11px}.ha-destination-next small{max-width:540px;color:#6f8798;font-size:9px;line-height:1.45}.ha-destination-lock{flex:0 0 auto;padding:5px 7px;border-radius:7px;background:rgba(255,210,74,.055);color:#ffd24a!important;font-size:8px!important}
      .ha-destination-foot{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 24px;border-top:1px solid rgba(255,255,255,.065)}.ha-destination-foot span{color:#667f92;font-size:9px}.ha-destination-done{padding:9px 16px;border:0;border-radius:9px;background:linear-gradient(135deg,#5fe7ff,#1679ff);color:#001018;font-weight:900;font-size:10px;cursor:pointer}
      @media(max-width:650px){.ha-destination-overlay{padding:10px}.ha-provider{grid-template-columns:38px 1fr}.ha-provider>button{grid-column:1/-1;width:100%}.ha-destination-next{align-items:flex-start}.ha-destination-foot{align-items:flex-start;flex-direction:column}.ha-destination-done{width:100%}}
    `;
    document.head.appendChild(style);
  }
});
