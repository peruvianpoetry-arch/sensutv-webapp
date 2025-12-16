import os
import json
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List

from flask import (
    Flask, jsonify, render_template_string, request, redirect, make_response
)

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# =========================
# LOGGING
# =========================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger("sensutv")

# =========================
# ENV VARS
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "10000"))

# Link opcional al bot (ej: https://t.me/TuBot?start=join)
BOT_PAY_LINK = os.getenv("BOT_PAY_LINK", "").strip()

# Wasabi info (informativo)
WASABI_BUCKET = os.getenv("WASABI_BUCKET", "sensutv-media").strip()
WASABI_REGION = os.getenv("WASABI_REGION", "eu-central-2").strip()

# Persistencia:
# - Si tienes Render Disk montado, pon DATA_DIR=/var/data en Render
# - Si no, usamos /tmp/data (NO persistente)
PREFERRED_DATA_DIR = os.getenv("DATA_DIR", "/var/data").strip()

def choose_data_dir(preferred: str) -> str:
    try:
        os.makedirs(preferred, exist_ok=True)
        testfile = os.path.join(preferred, ".write_test")
        with open(testfile, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(testfile)
        return preferred
    except Exception as e:
        logger.warning("⚠️ No se pudo usar DATA_DIR=%s (%s). Usando fallback /tmp/data", preferred, e)
        fallback = "/tmp/data"
        os.makedirs(fallback, exist_ok=True)
        logger.info("✅ DATA_DIR fallback activo: %s", fallback)
        return fallback

DATA_DIR = choose_data_dir(PREFERRED_DATA_DIR)

MODELS_FILE = os.path.join(DATA_DIR, "models.json")
UPLOADS_FILE = os.path.join(DATA_DIR, "uploads.json")

# =========================
# HELPERS JSON
# =========================
def _load_json(path: str, default: Any):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.exception("Error leyendo %s: %s", path, e)
        return default

def _save_json(path: str, data: Any):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def load_models() -> Dict[str, Any]:
    return _load_json(MODELS_FILE, {})

def save_models(models: Dict[str, Any]):
    _save_json(MODELS_FILE, models)

def load_uploads() -> Dict[str, Any]:
    return _load_json(UPLOADS_FILE, {"items": []})

def save_uploads(data: Dict[str, Any]):
    _save_json(UPLOADS_FILE, data)

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in [" ", ".", "/", "\\", "|", ":", ";", ",", "+", "&"]:
            out.append("-")
        elif ch in ["_", "-"]:
            out.append(ch)
    res = "".join(out)
    while "--" in res:
        res = res.replace("--", "-")
    return res.strip("-")

def now_yyyymmdd() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

def last_n(items: List[dict], n: int) -> List[dict]:
    return list(reversed(items))[:n]

# =========================
# I18N (WEB)
# =========================
SUPPORTED_LANGS = ["es", "de", "en", "pt"]
DEFAULT_LANG = "es"

T = {
    "es": {
        "brand": "SensuTV",
        "tagline": "Privado • Discreto • Actualizaciones frecuentes",
        "hero_title": "Contenido que no verás en ningún otro lugar 🔥",
        "hero_sub": "Previews gratis. Si quieres lo completo… desbloquea Premium.",
        "btn_free": "Ver previews gratis",
        "btn_premium": "Desbloquear Premium",
        "new_uploads": "Nuevas subidas",
        "models": "Modelos",
        "privacy": "Privacidad",
        "privacy_text": "Sin indexación • Sin rastreadores • Sin links directos",
        "search_ph": "Buscar modelo, país o tag…",
        "empty_models": "Aún no hay modelos. Usa /register en el bot.",
        "empty_uploads": "Aún no hay subidas. Usa /plan para generar registros.",
        "back": "Volver",
        "profile": "Perfil",
        "premium_note": "Premium se activa desde el bot / pago (Stripe).",
        "footer": "⚠️ Acceso privado. No compartas links. Filtraciones pueden rastrearse.",
        "live": "EN VIVO",
        "off": "OFFLINE",
    },
    "de": {
        "brand": "SensuTV",
        "tagline": "Privat • Diskret • Regelmäßige Updates",
        "hero_title": "Inhalte, die du sonst nirgends siehst 🔥",
        "hero_sub": "Gratis Previews. Für alles… Premium freischalten.",
        "btn_free": "Gratis Previews ansehen",
        "btn_premium": "Premium freischalten",
        "new_uploads": "Neueste Uploads",
        "models": "Models",
        "privacy": "Privatsphäre",
        "privacy_text": "Keine Indexierung • Keine Tracker • Keine Direktlinks",
        "search_ph": "Suche nach Model, Land oder Tag…",
        "empty_models": "Noch keine Models. Nutze /register im Bot.",
        "empty_uploads": "Noch keine Uploads. Nutze /plan für Einträge.",
        "back": "Zurück",
        "profile": "Profil",
        "premium_note": "Premium über Bot / Zahlung (Stripe).",
        "footer": "⚠️ Privater Zugang. Links nicht teilen. Leaks können nachvollzogen werden.",
        "live": "LIVE",
        "off": "OFFLINE",
    },
    "en": {
        "brand": "SensuTV",
        "tagline": "Private • Discreet • Frequent updates",
        "hero_title": "Content you won’t see anywhere else 🔥",
        "hero_sub": "Free previews. For full access… unlock Premium.",
        "btn_free": "View free previews",
        "btn_premium": "Unlock Premium",
        "new_uploads": "New uploads",
        "models": "Models",
        "privacy": "Privacy",
        "privacy_text": "Not indexed • No trackers • No direct links",
        "search_ph": "Search model, country or tag…",
        "empty_models": "No models yet. Use /register in the bot.",
        "empty_uploads": "No uploads yet. Use /plan to generate entries.",
        "back": "Back",
        "profile": "Profile",
        "premium_note": "Premium via bot / payment (Stripe).",
        "footer": "⚠️ Private access. Don’t share links. Leaks can be traced.",
        "live": "LIVE",
        "off": "OFFLINE",
    },
    "pt": {
        "brand": "SensuTV",
        "tagline": "Privado • Discreto • Atualizações frequentes",
        "hero_title": "Conteúdo que você não vê em nenhum outro lugar 🔥",
        "hero_sub": "Previews grátis. Para tudo… desbloqueie Premium.",
        "btn_free": "Ver previews grátis",
        "btn_premium": "Desbloquear Premium",
        "new_uploads": "Novos envios",
        "models": "Modelos",
        "privacy": "Privacidade",
        "privacy_text": "Sem indexação • Sem rastreadores • Sem links diretos",
        "search_ph": "Buscar modelo, país ou tag…",
        "empty_models": "Ainda sem modelos. Use /register no bot.",
        "empty_uploads": "Ainda sem envios. Use /plan para gerar entradas.",
        "back": "Voltar",
        "profile": "Perfil",
        "premium_note": "Premium via bot / pagamento (Stripe).",
        "footer": "⚠️ Acesso privado. Não compartilhe links. Vazamentos podem ser rastreados.",
        "live": "AO VIVO",
        "off": "OFFLINE",
    },
}

def normalize_lang(code: Optional[str]) -> str:
    if not code:
        return DEFAULT_LANG
    code = code.lower()
    if code.startswith("pt"):
        return "pt"
    if code.startswith("es"):
        return "es"
    if code.startswith("de"):
        return "de"
    if code.startswith("en"):
        return "en"
    return DEFAULT_LANG

def get_lang_from_request() -> str:
    q = (request.args.get("lang") or "").strip().lower()
    if q in SUPPORTED_LANGS:
        return q
    c = (request.cookies.get("lang") or "").strip().lower()
    if c in SUPPORTED_LANGS:
        return c
    al = request.headers.get("Accept-Language", "")
    first = al.split(",")[0].strip()
    return normalize_lang(first)

# =========================
# FLASK WEB
# =========================
app = Flask(__name__)

@app.after_request
def add_security_headers(resp):
    # Privacidad fuerte (sin trackers)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    # CSP simple (tenemos CSS inline)
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    )
    return resp

@app.get("/robots.txt")
def robots():
    # No indexación en Google
    txt = "User-agent: *\nDisallow: /\n"
    r = make_response(txt, 200)
    r.headers["Content-Type"] = "text/plain; charset=utf-8"
    return r

@app.get("/healthz")
def healthz():
    return "ok", 200

HOME_HTML = """
<!doctype html>
<html lang="{{lang}}">
<head>
  <meta charset="utf-8"/>
  <title>{{t['brand']}}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    :root{
      --bg:#070711;
      --panel:#0f1020;
      --panel2:#13142a;
      --border:#24254a;
      --text:#ffffff;
      --muted:#b7b7cf;
      --accent:#ff3d8a;
      --accent2:#6d28d9;
      --good:#22c55e;
      --warn:#f59e0b;
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;background:
      radial-gradient(1200px 600px at 20% 10%, rgba(255,61,138,.18), transparent 60%),
      radial-gradient(900px 500px at 80% 20%, rgba(109,40,217,.20), transparent 55%),
      var(--bg);
      color:var(--text);
    }
    .wrap{max-width:1100px;margin:0 auto;padding:18px}
    .nav{
      display:flex;gap:12px;align-items:center;justify-content:space-between;
      padding:12px 14px;border:1px solid var(--border);border-radius:18px;
      background:rgba(15,16,32,.7);backdrop-filter: blur(10px);
      position:sticky;top:10px;z-index:10;
    }
    .brand{display:flex;align-items:center;gap:10px}
    .logo{
      width:36px;height:36px;border-radius:14px;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      box-shadow:0 18px 40px rgba(255,61,138,.18);
    }
    .brand h1{font-size:16px;margin:0}
    .tag{font-size:12px;color:var(--muted)}
    .right{display:flex;gap:10px;align-items:center}
    .search{
      width:min(420px, 52vw);
      padding:10px 12px;border-radius:14px;
      border:1px solid var(--border);
      background:rgba(19,20,42,.8);
      color:var(--text);
      outline:none;
    }
    .lang{
      padding:10px 12px;border-radius:14px;
      border:1px solid var(--border);
      background:rgba(19,20,42,.8);
      color:var(--text);
    }
    .hero{
      margin-top:16px;border:1px solid var(--border);
      border-radius:24px;padding:22px;
      background: linear-gradient(180deg, rgba(19,20,42,.95), rgba(7,7,17,.65));
      overflow:hidden;position:relative;
    }
    .hero:before{
      content:"";position:absolute;inset:-2px;
      background: radial-gradient(700px 260px at 20% 30%, rgba(255,61,138,.18), transparent 60%),
                  radial-gradient(700px 260px at 80% 10%, rgba(109,40,217,.18), transparent 55%);
      pointer-events:none;
    }
    .hero-inner{position:relative}
    .hero h2{font-size:32px;margin:0 0 8px 0;line-height:1.15}
    .hero p{margin:0;color:var(--muted);max-width:760px}
    .btns{margin-top:14px;display:flex;flex-wrap:wrap;gap:10px}
    .btn{
      display:inline-flex;align-items:center;justify-content:center;
      padding:12px 16px;border-radius:16px;
      text-decoration:none;font-weight:800;
      border:1px solid transparent;
      transition:transform .15s, opacity .15s;
    }
    .btn:hover{transform:translateY(-1px);opacity:.98}
    .btn1{background:var(--accent2);box-shadow:0 18px 40px rgba(109,40,217,.20)}
    .btn2{background:var(--accent);box-shadow:0 18px 40px rgba(255,61,138,.22)}
    .btnGhost{background:rgba(19,20,42,.65);border-color:var(--border)}
    .section{margin-top:16px}
    .section h3{margin:0 0 10px 0;font-size:16px;color:#e9e9ff}
    .grid{display:grid;grid-template-columns:repeat(auto-fill, minmax(190px, 1fr));gap:14px}
    .card{
      border:1px solid var(--border);border-radius:20px;padding:14px;
      background: linear-gradient(180deg, rgba(19,20,42,.95), rgba(7,7,17,.55));
      transition: transform .18s, box-shadow .18s;
      overflow:hidden;position:relative;
      text-decoration:none;color:inherit;
    }
    .card:hover{transform:scale(1.03);box-shadow:0 22px 48px rgba(255,61,138,.12)}
    .thumb{
      height:120px;border-radius:16px;
      background:
        radial-gradient(220px 120px at 20% 30%, rgba(255,61,138,.20), transparent 60%),
        radial-gradient(220px 120px at 80% 20%, rgba(109,40,217,.22), transparent 55%),
        rgba(9,9,18,.85);
      border:1px solid rgba(255,255,255,.06);
    }
    .pill{
      display:inline-flex;gap:6px;align-items:center;
      font-size:11px;color:#d8d8ff;
      border:1px solid rgba(255,255,255,.10);
      padding:4px 10px;border-radius:999px;
      background:rgba(19,20,42,.55);
      margin-top:10px;
    }
    .meta{margin-top:10px;color:var(--muted);font-size:12px}
    .title{margin-top:8px;font-weight:900}
    .badge{
      position:absolute;top:12px;right:12px;
      padding:6px 10px;border-radius:999px;
      font-size:11px;font-weight:900;
      border:1px solid rgba(255,255,255,.12);
      background:rgba(0,0,0,.35);
    }
    .live{background:rgba(34,197,94,.18);border-color:rgba(34,197,94,.28)}
    .off{background:rgba(245,158,11,.16);border-color:rgba(245,158,11,.24)}
    .privacy{
      display:flex;gap:10px;align-items:flex-start;
      padding:14px;border-radius:20px;border:1px solid var(--border);
      background:rgba(15,16,32,.6);
    }
    .shield{
      width:40px;height:40px;border-radius:16px;
      background:rgba(255,255,255,.06);
      display:flex;align-items:center;justify-content:center;
      border:1px solid rgba(255,255,255,.10);
      font-size:18px;
    }
    .footer{margin:18px 0 10px 0;color:var(--muted);font-size:12px}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="nav">
      <div class="brand">
        <div class="logo"></div>
        <div>
          <h1>{{t['brand']}}</h1>
          <div class="tag">{{t['tagline']}}</div>
        </div>
      </div>
      <div class="right">
        <input id="q" class="search" placeholder="{{t['search_ph']}}" value="{{query}}" />
        <select id="lang" class="lang">
          {% for L in langs %}
            <option value="{{L}}" {% if L==lang %}selected{% endif %}>{{L.upper()}}</option>
          {% endfor %}
        </select>
      </div>
    </div>

    <div class="hero">
      <div class="hero-inner">
        <h2>{{t['hero_title']}}</h2>
        <p>{{t['hero_sub']}}</p>
        <div class="btns">
          <a class="btn btn1" href="/feed?tier=free&lang={{lang}}">{{t['btn_free']}}</a>
          <a class="btn btn2" href="/premium?lang={{lang}}">{{t['btn_premium']}}</a>
          <a class="btn btnGhost" href="/api/models" target="_blank">API</a>
        </div>
        {% if bot_pay_link %}
          <div class="meta">{{t['premium_note']}}</div>
        {% endif %}
      </div>
    </div>

    <div class="section">
      <h3>{{t['new_uploads']}}</h3>
      {% if new_items|length == 0 %}
        <div class="privacy">
          <div class="shield">✨</div>
          <div>
            <div class="title">{{t['empty_uploads']}}</div>
            <div class="meta">Tip: /register → /plan → luego subes a Wasabi.</div>
          </div>
        </div>
      {% else %}
        <div class="grid">
          {% for it in new_items %}
            <div class="card">
              <div class="thumb"></div>
              <div class="pill">{{it.get("model_name","")}} • {{it.get("country","")}}</div>
              <div class="title">{{it.get("title","Nuevo contenido")}}</div>
              <div class="meta">{{it.get("type","")}} • {{it.get("category","")}} • {{it.get("date","")}}</div>
            </div>
          {% endfor %}
        </div>
      {% endif %}
    </div>

    <div class="section">
      <h3>{{t['models']}}</h3>
      {% if models_list|length == 0 %}
        <div class="privacy">
          <div class="shield">🧩</div>
          <div>
            <div class="title">{{t['empty_models']}}</div>
            <div class="meta">Registra la primera modelo desde Telegram.</div>
          </div>
        </div>
      {% else %}
        <div class="grid" id="modelsGrid">
          {% for m in models_list %}
            <a class="card" href="/m/{{m.get('id')}}?lang={{lang}}">
              <div class="badge {% if m.get('live') %}live{% else %}off{% endif %}">
                {% if m.get('live') %}{{t['live']}}{% else %}{{t['off']}}{% endif %}
              </div>
              <div class="thumb"></div>
              <div class="pill">{{m.get("country","")}} • {{m.get("age","?")}}</div>
              <div class="title">{{m.get("name","")}}</div>
              <div class="meta">Tags: {{", ".join(m.get("tags",[])) if m.get("tags") else "-"}}</div>
            </a>
          {% endfor %}
        </div>
      {% endif %}
    </div>

    <div class="section">
      <h3>{{t['privacy']}}</h3>
      <div class="privacy">
        <div class="shield">🛡️</div>
        <div>
          <div class="title">{{t['privacy_text']}}</div>
          <div class="meta">Bucket: <b>{{bucket}}</b> • Region: <b>{{region}}</b></div>
          <div class="meta">DATA_DIR: <b>{{data_dir}}</b></div>
        </div>
      </div>
      <div class="footer">{{t['footer']}}</div>
    </div>
  </div>

  <script>
    const q = document.getElementById("q");
    const langSel = document.getElementById("lang");

    langSel.addEventListener("change", () => {
      const u = new URL(window.location.href);
      u.searchParams.set("lang", langSel.value);
      document.cookie = "lang=" + langSel.value + "; path=/; SameSite=Lax";
      window.location.href = u.toString();
    });

    q.addEventListener("input", () => {
      const query = q.value.toLowerCase().trim();
      const cards = document.querySelectorAll("#modelsGrid a.card");
      cards.forEach(c => {
        const txt = c.innerText.toLowerCase();
        c.style.display = txt.includes(query) ? "" : "none";
      });
    });
  </script>
</body>
</html>
"""

MODEL_HTML = """
<!doctype html>
<html lang="{{lang}}">
<head>
  <meta charset="utf-8"/>
  <title>{{m.get('name','')}} • {{t['brand']}}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body{margin:0;font-family:system-ui,Arial;background:#070711;color:#fff}
    .wrap{max-width:900px;margin:0 auto;padding:18px}
    .top{display:flex;align-items:center;justify-content:space-between;gap:10px}
    .btn{padding:10px 14px;border-radius:14px;border:1px solid #24254a;background:#12132a;color:#fff;text-decoration:none;font-weight:800}
    .card{margin-top:14px;border:1px solid #24254a;border-radius:20px;padding:16px;background:linear-gradient(180deg,#13142a,#070711)}
    .thumb{height:160px;border-radius:16px;background:
      radial-gradient(420px 180px at 20% 30%, rgba(255,61,138,.22), transparent 60%),
      radial-gradient(420px 180px at 80% 10%, rgba(109,40,217,.22), transparent 55%),
      rgba(9,9,18,.85);border:1px solid rgba(255,255,255,.06)}
    .title{font-size:22px;font-weight:900;margin-top:12px}
    .muted{color:#b7b7cf}
    .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-top:12px}
    .item{border:1px solid #24254a;border-radius:18px;padding:12px;background:rgba(19,20,42,.8)}
    .pill{display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid rgba(255,255,255,.10);font-size:12px;color:#ddd}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <a class="btn" href="/?lang={{lang}}">← {{t['back']}}</a>
      <div class="muted">{{t['profile']}} • {{t['brand']}}</div>
    </div>

    <div class="card">
      <div class="thumb"></div>
      <div class="title">{{m.get("name","")}}</div>
      <div class="muted">{{m.get("country","")}} • {{m.get("age","?")}} • Tags: {{", ".join(m.get("tags",[])) if m.get("tags") else "-"}}</div>
    </div>

    <div class="card">
      <div style="font-weight:900;margin-bottom:10px">{{t['new_uploads']}}</div>
      {% if items|length == 0 %}
        <div class="muted">Aún no hay subidas para esta modelo.</div>
      {% else %}
        <div class="grid">
          {% for it in items %}
            <div class="item">
              <div class="pill">{{it.get("type","")}} • {{it.get("category","")}}</div>
              <div style="margin-top:8px;font-weight:900">{{it.get("title","")}}</div>
              <div class="muted" style="margin-top:6px">{{it.get("date","")}}</div>
            </div>
          {% endfor %}
        </div>
      {% endif %}
    </div>
  </div>
</body>
</html>
"""

@app.get("/")
def home():
    lang = get_lang_from_request()
    t = T.get(lang, T[DEFAULT_LANG])

    models = load_models()
    uploads = load_uploads().get("items", [])

    query = (request.args.get("q") or "").strip().lower()
    models_list = list(models.values())

    if query:
        def hit(m):
            txt = " ".join([
                m.get("name",""),
                m.get("country",""),
                " ".join(m.get("tags", [])),
            ]).lower()
            return query in txt
        models_list = [m for m in models_list if hit(m)]

    new_items = last_n(uploads, 8)

    return render_template_string(
        HOME_HTML,
        lang=lang,
        langs=SUPPORTED_LANGS,
        t=t,
        query=query,
        models_list=models_list,
        new_items=new_items,
        bot_pay_link=BOT_PAY_LINK,
        bucket=WASABI_BUCKET,
        region=WASABI_REGION,
        data_dir=DATA_DIR,
    )

@app.get("/m/<model_id>")
def model_page(model_id: str):
    lang = get_lang_from_request()
    t = T.get(lang, T[DEFAULT_LANG])

    model_id = slugify(model_id)
    models = load_models()
    m = models.get(model_id)
    if not m:
        return redirect(f"/?lang={lang}")

    uploads = load_uploads().get("items", [])
    items = [it for it in uploads if it.get("model_id") == model_id]
    items = last_n(items, 12)

    return render_template_string(
        MODEL_HTML,
        lang=lang,
        t=t,
        m=m,
        items=items,
    )

@app.get("/api/models")
def api_models():
    return jsonify(load_models())

@app.get("/api/uploads")
def api_uploads():
    return jsonify(load_uploads())

@app.get("/feed")
def feed():
    tier = request.args.get("tier", "free")
    data = load_uploads().get("items", [])
    return jsonify({"tier": tier, "items": list(reversed(data))})

@app.get("/premium")
def premium():
    # Por ahora: mandamos al bot si hay BOT_PAY_LINK
    if BOT_PAY_LINK:
        return redirect(BOT_PAY_LINK)
    return jsonify({"ok": False, "error": "BOT_PAY_LINK not set"}), 400

def run_flask():
    logger.info("Starting Flask on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False)

# =========================
# TELEGRAM BOT (PTB v20.8)
# =========================
S_MODEL_NAME, S_COUNTRY, S_AGE, S_TAGS, S_TYPE, S_CATEGORY = range(6)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "✅ *SensuTV Bot activo*\n\n"
        "Comandos:\n"
        "• /register → registrar una modelo (nombre, país, edad, tags)\n"
        "• /models → lista de modelos\n"
        "• /plan → generar la *ruta exacta* para subir en Wasabi\n"
        "• /last → últimas rutas generadas\n\n"
        f"📦 Bucket Wasabi: `{WASABI_BUCKET}`\n"
        f"🌍 Region: `{WASABI_REGION}`\n"
        f"💾 DATA_DIR: `{DATA_DIR}`\n"
        "\n🌐 Web: abre tu URL de Render (/) para ver la interfaz."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def cmd_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    models = load_models()
    if not models:
        await update.message.reply_text("Aún no hay modelos registradas. Usa /register")
        return
    lines = ["📋 *Modelos registradas:*"]
    for k, v in models.items():
        tags = ", ".join(v.get("tags", [])) if v.get("tags") else "-"
        lines.append(
            f"• *{v.get('name','')}* ({v.get('country','')}) — edad: {v.get('age','?')} — tags: {tags}\n"
            f"  ID: `{k}`  |  Perfil: `/m/{k}`"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uploads = load_uploads().get("items", [])
    if not uploads:
        await update.message.reply_text("No hay registros aún. Usa /plan para generar rutas.")
        return
    last = last_n(uploads, 10)
    lines = ["🕒 *Últimas rutas generadas:*"]
    for it in last:
        lines.append(f"• {it.get('date','')} — *{it.get('model_name','')}* — `{it.get('path','')}`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

# ---- REGISTER FLOW ----
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Nombre de la modelo (ej: Aurora):")
    return S_MODEL_NAME

async def register_model_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["model_name"] = (update.message.text or "").strip()
    await update.message.reply_text("País (ej: Brasil, Perú, Alemania):")
    return S_COUNTRY

async def register_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["country"] = (update.message.text or "").strip()
    await update.message.reply_text("Edad (solo número, ej: 23):")
    return S_AGE

async def register_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    age = "".join([c for c in txt if c.isdigit()])
    context.user_data["age"] = age if age else "?"
    await update.message.reply_text("Tags separadas por coma (ej: latina, milf, cosplay):")
    return S_TAGS

async def register_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").strip()
    tags = [slugify(x) for x in raw.split(",") if x.strip()]

    name = context.user_data.get("model_name", "").strip()
    country = context.user_data.get("country", "").strip()
    age = context.user_data.get("age", "?")

    model_id = slugify(name) or f"model-{int(time.time())}"

    models = load_models()
    models[model_id] = {
        "id": model_id,
        "name": name,
        "country": country,
        "age": age,
        "tags": tags,
        # opcional para futuro: live status
        "live": False,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    save_models(models)

    await update.message.reply_text(
        f"✅ Registrada: *{name}*\nID: `{model_id}`\nPaís: {country}\nEdad: {age}\nTags: {', '.join(tags) if tags else '-'}\n\n"
        "👉 Ahora usa /plan para generar rutas.",
        parse_mode=ParseMode.MARKDOWN,
    )
    context.user_data.clear()
    return ConversationHandler.END

# ---- PLAN FLOW ----
async def plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    models = load_models()
    if not models:
        await update.message.reply_text("Primero registra una modelo con /register")
        return ConversationHandler.END

    lines = ["Elige modelo (escribe el *ID* exacto):"]
    for k, v in models.items():
        lines.append(f"• `{k}` = {v.get('name','')} ({v.get('country','')})")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    return S_MODEL_NAME

async def plan_pick_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    model_id = slugify((update.message.text or "").strip())
    models = load_models()
    if model_id not in models:
        await update.message.reply_text("❌ ID no válido. Copia/pega el ID exacto.")
        return S_MODEL_NAME

    context.user_data["plan_model_id"] = model_id
    await update.message.reply_text("Tipo de archivo: escribe `video` o `foto`")
    return S_TYPE

async def plan_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ttype = slugify((update.message.text or "").strip())
    if ttype not in ["video", "foto"]:
        await update.message.reply_text("Escribe solo: `video` o `foto`")
        return S_TYPE
    context.user_data["plan_type"] = ttype
    await update.message.reply_text("Categoría (ej: free, premium, teaser, cosplay, latina):")
    return S_CATEGORY

async def plan_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat = slugify((update.message.text or "").strip()) or "general"
    model_id = context.user_data["plan_model_id"]
    ttype = context.user_data["plan_type"]

    models = load_models()
    m = models[model_id]
    date = now_yyyymmdd()

    country_slug = slugify(m.get("country", "unknown")) or "unknown"
    path = f"{country_slug}/{model_id}/{ttype}/{cat}/{date}/"

    uploads = load_uploads()
    uploads["items"].append({
        "bucket": WASABI_BUCKET,
        "region": WASABI_REGION,
        "model_id": model_id,
        "model_name": m.get("name", ""),
        "country": m.get("country", ""),
        "type": ttype,
        "category": cat,
        "date": date,
        "title": f"{m.get('name','')} • {ttype} • {cat}",
        "path": path,
        "created_at": datetime.utcnow().isoformat() + "Z",
    })
    save_uploads(uploads)

    msg = (
        "✅ *Ruta generada*\n\n"
        f"Modelo: *{m.get('name','')}*\n"
        f"Tipo: *{ttype}*\n"
        f"Categoría: *{cat}*\n"
        f"Fecha: *{date}*\n\n"
        f"📦 Bucket: `{WASABI_BUCKET}`\n"
        f"🧭 Ruta: `{path}`\n\n"
        "👉 Sube tus archivos a esa carpeta en Wasabi.\n"
        "La web lo mostrará como ‘nuevo contenido’ (sin exponer links directos).\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Cancelado.")
    return ConversationHandler.END

def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Falta TELEGRAM_TOKEN en Render (Environment).")

    # Flask en thread separado
    web_thread = threading.Thread(target=run_flask, daemon=True)
    web_thread.start()

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("models", cmd_models))
    application.add_handler(CommandHandler("last", cmd_last))

    register_conv = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            S_MODEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_model_name)],
            S_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_country)],
            S_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_age)],
            S_TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_tags)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    plan_conv = ConversationHandler(
        entry_points=[CommandHandler("plan", plan_start)],
        states={
            S_MODEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_pick_model)],
            S_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_type)],
            S_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_category)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    application.add_handler(register_conv)
    application.add_handler(plan_conv)

    logger.info("Telegram bot starting polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
