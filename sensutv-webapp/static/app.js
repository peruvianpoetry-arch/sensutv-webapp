const tg = window.Telegram?.WebApp;
if (tg) tg.ready();

const state = {
  session: { premium:false, user:{id:""} },
  catalog: { free:[], premium:[], models:[] },
  tab: "home",
};

const screen = document.getElementById("screen");
const tagline = document.getElementById("tagline");

async function postJSON(url, data){
  const res = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(data)});
  return res.json();
}
async function getJSON(url){
  const res = await fetch(url);
  return res.json();
}

async function init(){
  const initData = tg?.initData || "";
  const sess = await postJSON("/api/session", { initData });
  state.session = sess;

  const content = await getJSON("/api/content");
  state.catalog = content.catalog || state.catalog;

  render();
}
init();

function setTab(tab){
  state.tab = tab;
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  render();
}
document.querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => setTab(b.dataset.tab)));

document.getElementById("goPay").addEventListener("click", async () => {
  const r = await postJSON("/api/checkout_link", {});
  if (tg) tg.openTelegramLink(r.url);
  else window.open(r.url, "_blank");
});

function render(){
  const premium = !!state.session.premium;
  tagline.textContent = premium ? "PREMIUM • acceso completo" : "FREE • previews calientes";

  if (state.tab === "home") return renderHome(premium);
  if (state.tab === "free") return renderFree();
  if (state.tab === "premium") return renderPremium(premium);
  if (state.tab === "account") return renderAccount(premium);
}

function renderHome(premium){
  screen.innerHTML = `
    <section class="hero">
      <h1>${premium ? "Bienvenido al Club 💎" : "Entra… y mira lo que otros no ven 🔥"}</h1>
      <p>${premium ? "Tu acceso está activo. Explora el feed completo."
                   : "Previews gratis. Si quieres lo completo… desbloquea Premium por 5€."}</p>
      <div class="row">
        <button class="btn ghost" id="btnFree">Ver previews gratis</button>
        <button class="btn primary" id="btnPay">${premium ? "Ir a Premium" : "🔥 Desbloquear Premium"}</button>
      </div>
    </section>

    <div style="height:12px"></div>

    <div class="card">
      <div style="font-weight:900; margin-bottom:10px;">Top Previews</div>
      <div class="grid" id="topGrid"></div>
    </div>
  `;

  document.getElementById("btnFree").onclick = () => setTab("free");
  document.getElementById("btnPay").onclick = () => premium ? setTab("premium") : UI.openModal("Desbloquear 💎", "Acceso completo 30 días • 5€");

  const top = (state.catalog.free || []).slice(0,4);
  const grid = document.getElementById("topGrid");
  grid.innerHTML = top.map(tileHTML("FREE")).join("");
  grid.querySelectorAll("[data-id]").forEach(el => el.onclick = () => openItem(el.dataset.id, "free"));
}

function renderFree(){
  const free = state.catalog.free || [];
  screen.innerHTML = `
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div style="font-weight:900;">Previews Gratis</div>
        <div style="color:#b8b8c2; font-size:12px;">${free.length} items</div>
      </div>
      <div class="grid" id="freeGrid"></div>
    </div>
  `;
  const grid = document.getElementById("freeGrid");
  grid.innerHTML = free.map(tileHTML("FREE")).join("");
  grid.querySelectorAll("[data-id]").forEach(el => el.onclick = () => openItem(el.dataset.id, "free"));
}

function renderPremium(premium){
  if (!premium){
    screen.innerHTML = `
      <div class="card cardGlow">
        <div style="font-weight:900; font-size:18px;">💎 Premium</div>
        <div style="color:#b8b8c2; margin:8px 0 14px;">
          Contenido completo • 30 días • 5€
        </div>
        <button class="btn primary" onclick="UI.openModal('Desbloquear 💎','Acceso completo 30 días • 5€')">🔥 Unirme Premium</button>
        <div style="height:10px"></div>
        <button class="btn ghost" onclick="setTab('free')">Ver previews primero</button>
      </div>
    `;
    return;
  }

  const items = state.catalog.premium || [];
  screen.innerHTML = `
    <div class="card">
      <div style="font-weight:900;">Feed Premium</div>
      <div class="grid" id="premGrid"></div>
    </div>
  `;
  const grid = document.getElementById("premGrid");
  grid.innerHTML = items.map(tileHTML("HOT")).join("");
  grid.querySelectorAll("[data-id]").forEach(el => el.onclick = () => openItem(el.dataset.id, "premium"));
}

function renderAccount(premium){
  const u = state.session.user || {};
  screen.innerHTML = `
    <div class="card">
      <div style="font-weight:900;">Cuenta</div>
      <div style="color:#b8b8c2; margin-top:6px;">User ID: ${u.id || "-"}</div>
      <div style="margin-top:10px;">Estado: <b>${premium ? "💎 Premium activo" : "FREE"}</b></div>
      <div style="height:12px"></div>
      <button class="btn primary" onclick="${premium ? "setTab('premium')" : "UI.openModal('Desbloquear 💎','Acceso completo 30 días • 5€')"}">
        ${premium ? "Ir a Premium" : "🔥 Unirme Premium"}
      </button>
    </div>
  `;
}

function tileHTML(label){
  return (item) => {
    const thumb = item.thumb || item.url || "";
    const title = item.title || "";
    return `
      <div class="tile" data-id="${item.id}">
        ${thumb ? `<img src="${thumb}" alt="">` : `<div style="height:100%"></div>`}
        <div class="badge ${label==='HOT'?'hot':''}">${label}</div>
        <div class="caption">${title}</div>
      </div>
    `;
  };
}

function openItem(id, type){
  const premium = !!state.session.premium;
  const arr = type === "premium" ? (state.catalog.premium||[]) : (state.catalog.free||[]);
  const item = arr.find(x => x.id === id);
  if (!item) return;

  if (type === "premium" && !premium){
    UI.openModal("🔒 Bloqueado", "Desbloquea Premium • 30 días • 5€");
    return;
  }

  const isVideo = item.type === "video";
  const limit = item.limitSeconds || 0;

  screen.innerHTML = `
    <div class="card cardGlow">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div style="font-weight:900;">${item.title}</div>
        <button class="iconbtn" id="backBtn">←</button>
      </div>
      <div style="height:12px"></div>
      ${isVideo
        ? `<video id="player" src="${item.url}" controls playsinline style="width:100%; border-radius:18px; border:1px solid rgba(255,255,255,.10);"></video>`
        : `<img src="${item.url}" style="width:100%; border-radius:18px; border:1px solid rgba(255,255,255,.10);" />`
      }
      <div style="height:12px"></div>
      ${(!premium && type==="free")
        ? `<button class="btn primary" id="unlockBtn">🔥 Ver completo (Premium)</button>`
        : ``
      }
    </div>
  `;

  document.getElementById("backBtn").onclick = () => setTab(type === "premium" ? "premium" : "free");

  const unlockBtn = document.getElementById("unlockBtn");
  if (unlockBtn) unlockBtn.onclick = () => UI.openModal("Desbloquear 💎", "Acceso completo 30 días • 5€");

  if (isVideo && !premium && limit > 0){
    const v = document.getElementById("player");
    v.muted = true;
    v.play().catch(()=>{});
    v.addEventListener("timeupdate", () => {
      if (v.currentTime >= limit){
        v.pause();
        UI.openModal("¿Quieres ver más? 🔥", "Desbloquea Premium • 30 días • 5€");
      }
    });
  }
}

window.setTab = setTab;
