import os
import json
import logging
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request

# =========================
# LOGGING
# =========================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
)
logger = logging.getLogger("sensutv-webapp")

# =========================
# ENV VARS
# =========================
PORT = int(os.getenv("PORT", "10000"))
BOT_PAY_LINK = os.getenv("BOT_PAY_LINK", "").strip()  # opcional
WASABI_BUCKET = os.getenv("WASABI_BUCKET", "sensutv-media")
WASABI_REGION = os.getenv("WASABI_REGION", "eu-central-2")

# Persistencia
DATA_DIR = os.getenv("DATA_DIR", "/var/data")

def ensure_data_dir(preferred: str) -> str:
    """Intenta usar /var/data (Render Disk). Si no se puede, cae a /tmp/data."""
    try:
        os.makedirs(preferred, exist_ok=True)
        testfile = os.path.join(preferred, ".write_test")
        with open(testfile, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(testfile)
        return preferred
    except Exception as e:
        fallback = "/tmp/data"
        os.makedirs(fallback, exist_ok=True)
        logger.warning("No se pudo usar DATA_DIR=%s (%s). fallback %s", preferred, e, fallback)
        return fallback

DATA_DIR = ensure_data_dir(DATA_DIR)

MODELS_FILE = os.path.join(DATA_DIR, "models.json")
UPLOADS_FILE = os.path.join(DATA_DIR, "uploads.json")

# =========================
# I18N
# =========================
I18N = {
    "es": {
        "title": "SensuTV",
        "subtitle": "Webapp en Render + bot en Telegram + media en Wasabi.",
        "hero_h": "Entra... y mira lo que otros no ven 🔥",
        "hero_p": "Previews gratis. Si quieres lo completo... desbloquea Premium.",
        "btn_free": "Ver previews gratis",
        "btn_premium": "Desbloquear Premium",
        "bot_link": "Link bot",
        "last": "Últimas subidas (registro)",
        "last_p": "Se alimenta de uploads.json (lo crea el bot con /plan).",
        "status": "Estado",
        "bucket": "Bucket",
        "region": "Región",
        "api": "API",
        "lang": "Idioma",
        "no_items": "Aún no hay registros. Usa el bot y crea rutas con /plan.",
    },
    "de": {
        "title": "SensuTV",
        "subtitle": "Webapp auf Render + Bot in Telegram + Media auf Wasabi.",
        "hero_h": "Komm rein... und sieh, was andere nicht sehen 🔥",
        "hero_p": "Gratis Previews. Für alles... Premium freischalten.",
        "btn_free": "Gratis Previews ansehen",
        "btn_premium": "Premium freischalten",
        "bot_link": "Bot-Link",
        "last": "Neueste Uploads (Log)",
        "last_p": "Kommt aus uploads.json (erzeugt der Bot mit /plan).",
        "status": "Status",
        "bucket": "Bucket",
        "region": "Region",
        "api": "API",
        "lang": "Sprache",
        "no_items": "Noch keine Einträge. Nutze den Bot und erstelle Pfade mit /plan.",
    },
    "pt": {
        "title": "SensuTV",
        "subtitle": "Webapp no Render + bot no Telegram + mídia no Wasabi.",
        "hero_h": "Entra... e vê o que outros não veem 🔥",
        "hero_p": "Previews grátis. Quer completo? Desbloqueia Premium.",
        "btn_free": "Ver previews grátis",
        "btn_premium": "Desbloquear Premium",
        "bot_link": "Link do bot",
        "last": "Últimos envios (registro)",
        "last_p": "Vem de uploads.json (o bot cria com /plan).",
        "status": "Status",
        "bucket": "Bucket",
        "region": "Região",
        "api": "API",
        "lang": "Idioma",
        "no_items": "Ainda não há registros. Use o bot e crie rotas com /plan.",
    },
    "en": {
        "title": "SensuTV",
        "subtitle": "Webapp on Render + bot on Telegram + media on Wasabi.",
        "hero_h": "Enter... and see what others don’t 🔥",
        "hero_p": "Free previews. Want the full access? Unlock Premium.",
        "btn_free": "See free previews",
        "btn_premium": "Unlock Premium",
        "bot_link": "Bot link",
        "last": "Latest uploads (log)",
        "last_p": "Powered by uploads.json (created by the bot via /plan).",
        "status": "Status",
        "bucket": "Bucket",
        "region": "Region",
        "api": "API",
        "lang": "Language",
        "no_items": "No entries yet. Use the bot and generate paths with /plan.",
    },
}

def pick_lang() -> str:
    q = (request.args.get("lang") or "").strip().lower()
    if q in I18N:
        return q
    hdr = (request.headers.get("Accept-Language") or "").lower()
    for code in ["de", "es", "pt", "en"]:
        if code in hdr:
            return code
    return "es"

# =========================
# JSON helpers
# =========================
def _load_json(path: str, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.exception("Error leyendo %s: %s", path, e)
        return default

def _save_json(path: str, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def load_models():
    return _load_json(MODELS_FILE, {})

def load_uploads():
    return _load_json(UPLOADS_FILE, {"items": []})

# =========================
# Flask
# =========================
app = Flask(__name__)

BASE_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{{t["title"]}}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body{font-family:system-ui,Arial;margin:0;background:#0b0b10;color:#fff}
    .wrap{max-width:980px;margin:0 auto;padding:22px}
    .muted{color:#b9b9c9}
    .top{display:flex;align-items:center;justify-content:space-between;gap:12px}
    .lang a{color:#bfa7ff;text-decoration:none;margin-left:10px}
    .card{background:#141421;border:1px solid #2a2a3a;border-radius:18px;padding:18px;margin:14px 0;box-shadow:0 10px 30px rgba(0,0,0,.25)}
    .btn{display:inline-block;padding:12px 16px;border-radius:14px;text-decoration:none;margin-right:10px;font-weight:700}
    .btn1{background:#6d28d9;color:#fff}
    .btn2{background:#ff3d8a;color:#fff}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
    .pill{display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid #2a2a3a;color:#cfcfe6;font-size:12px}
    .mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#cfcfe6;word-break:break-all}
    .hr{height:1px;background:#2a2a3a;margin:14px 0}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h2 style="margin:0">{{t["title"]}}</h2>
        <div class="muted">{{t["subtitle"]}}</div>
      </div>
      <div class="lang">
        <span class="muted">{{t["lang"]}}:</span>
        <!-- ✅ FIX: nada de url_for con **kwargs -->
        <a href="?lang=es">ES</a>
        <a href="?lang=de">DE</a>
        <a href="?lang=pt">PT</a>
        <a href="?lang=en">EN</a>
      </div>
    </div>

    <div class="card">
      <h3 style="margin-top:0">{{t["hero_h"]}}</h3>
      <div class="muted">{{t["hero_p"]}}</div>
      <div style="margin-top:14px">
        <a class="btn btn1" href="/feed?lang={{lang}}&tier=free">{{t["btn_free"]}}</a>
        <a class="btn btn2" href="/premium?lang={{lang}}">{{t["btn_premium"]}}</a>
      </div>
      {% if bot_pay_link %}
      <div style="margin-top:12px" class="muted">
        {{t["bot_link"]}}: <span class="mono">{{bot_pay_link}}</span>
      </div>
      {% endif %}
    </div>

    <div class="card">
      <h3 style="margin-top:0">{{t["last"]}}</h3>
      <div class="muted">{{t["last_p"]}}</div>

      <div class="hr"></div>

      {% if items|length == 0 %}
        <div class="muted">{{t["no_items"]}}</div>
      {% else %}
        <div class="grid" style="margin-top:12px">
          {% for it in items %}
          <div class="card" style="margin:0">
            <div class="pill">{{it.get("model_name","")}} • {{it.get("country","")}}</div>
            <div style="margin-top:10px"><b>{{it.get("title","Nuevo contenido")}}</b></div>
            <div class="muted" style="margin-top:6px">{{it.get("type","")}} • {{it.get("date","")}}</div>
            <div class="mono" style="margin-top:10px">wasabi://{{it.get("bucket","")}}/{{it.get("path","")}}</div>
          </div>
          {% endfor %}
        </div>
      {% endif %}
    </div>

    <div class="card">
      <h3 style="margin-top:0">{{t["status"]}}</h3>
      <div class="muted">{{t["bucket"]}}: <b>{{bucket}}</b> • {{t["region"]}}: <b>{{region}}</b></div>
      <div class="muted">DATA_DIR: <span class="mono">{{data_dir}}</span></div>
      <div class="muted">{{t["api"]}}: <a style="color:#bfa7ff" href="/api/models">/api/models</a> • <a style="color:#bfa7ff" href="/api/uploads">/api/uploads</a></div>
    </div>
  </div>
</body>
</html>
"""

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/")
def home():
    lang = pick_lang()
    t = I18N.get(lang, I18N["es"])
    uploads = load_uploads().get("items", [])
    items = list(reversed(uploads))[:6]
    return render_template_string(
        BASE_HTML,
        t=t,
        lang=lang,
        items=items,
        bot_pay_link=BOT_PAY_LINK,
        bucket=WASABI_BUCKET,
        region=WASABI_REGION,
        data_dir=DATA_DIR,
    )

@app.get("/api/models")
def api_models():
    return jsonify(load_models())

@app.get("/api/uploads")
def api_uploads():
    return jsonify(load_uploads())

@app.get("/feed")
def feed():
    tier = (request.args.get("tier") or "free").strip()
    lang = pick_lang()
    data = load_uploads().get("items", [])
    # (por ahora muestra todo; luego filtramos por tier)
    return jsonify({"ok": True, "tier": tier, "lang": lang, "items": list(reversed(data))})

@app.get("/premium")
def premium():
    lang = pick_lang()
    if BOT_PAY_LINK:
        return jsonify({"ok": True, "lang": lang, "next": BOT_PAY_LINK})
    return jsonify({"ok": False, "lang": lang, "error": "BOT_PAY_LINK not set"}), 400

if __name__ == "__main__":
    logger.info("Starting SensuTV WEBAPP on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False)
