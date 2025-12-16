import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, redirect, url_for

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
BOT_PAY_LINK = os.getenv("BOT_PAY_LINK", "").strip()  # ej: https://t.me/TuBot?start=join
WASABI_BUCKET = os.getenv("WASABI_BUCKET", "sensutv-media")
WASABI_REGION = os.getenv("WASABI_REGION", "eu-central-2")

# Persistencia
DATA_DIR = os.getenv("DATA_DIR", "/var/data")
MODELS_FILE = None
UPLOADS_FILE = None

def init_storage():
    global DATA_DIR, MODELS_FILE, UPLOADS_FILE
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info("✅ DATA_DIR activo: %s", DATA_DIR)
    except Exception as e:
        logger.warning("⚠️ No se pudo usar DATA_DIR=%s (%s). fallback /tmp/data", DATA_DIR, e)
        DATA_DIR = "/tmp/data"
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info("✅ DATA_DIR fallback activo: %s", DATA_DIR)

    MODELS_FILE = os.path.join(DATA_DIR, "models.json")
    UPLOADS_FILE = os.path.join(DATA_DIR, "uploads.json")

init_storage()

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
# Idiomas (auto + manual)
# =========================
SUPPORTED = ["es", "de", "pt", "en"]

I18N = {
    "es": {
        "title": "SensuTV",
        "subtitle": "Webapp en Render + bot en Telegram + media en Wasabi.",
        "hero": "Entra… y mira lo que otros no ven 🔥",
        "desc": "Previews gratis. Si quieres lo completo… desbloquea Premium.",
        "btn_free": "Ver previews gratis",
        "btn_premium": "Desbloquear Premium",
        "why_title": "¿Qué es SensuTV?",
        "why_b1": "Contenido organizado por modelo y país",
        "why_b2": "Acceso privado + pagos (Premium) con enlace al bot",
        "why_b3": "Interfaz rápida tipo “catálogo”",
        "latest": "Últimas subidas",
        "latest_note": "Esto se alimenta del registro (uploads.json).",
        "status": "Estado",
        "open_bot": "Abrir bot en Telegram",
        "premium_title": "Premium",
        "premium_desc": "Desbloquea acceso completo desde Telegram.",
        "back": "Volver",
        "no_items": "Aún no hay subidas registradas.",
        "lang": "Idioma",
    },
    "de": {
        "title": "SensuTV",
        "subtitle": "Webapp auf Render + Bot auf Telegram + Media auf Wasabi.",
        "hero": "Komm rein… und sieh, was andere nicht sehen 🔥",
        "desc": "Gratis-Previews. Für alles… Premium freischalten.",
        "btn_free": "Gratis Previews ansehen",
        "btn_premium": "Premium freischalten",
        "why_title": "Was ist SensuTV?",
        "why_b1": "Content nach Model & Land organisiert",
        "why_b2": "Privater Zugang + Premium über Bot-Link",
        "why_b3": "Schneller Katalog-Style",
        "latest": "Neueste Uploads",
        "latest_note": "Das kommt aus dem Upload-Register (uploads.json).",
        "status": "Status",
        "open_bot": "Bot in Telegram öffnen",
        "premium_title": "Premium",
        "premium_desc": "Schalte den vollen Zugriff über Telegram frei.",
        "back": "Zurück",
        "no_items": "Noch keine Uploads registriert.",
        "lang": "Sprache",
    },
    "pt": {
        "title": "SensuTV",
        "subtitle": "Webapp no Render + bot no Telegram + mídia no Wasabi.",
        "hero": "Entra… e vê o que os outros não veem 🔥",
        "desc": "Previews grátis. Quer completo? Libera Premium.",
        "btn_free": "Ver previews grátis",
        "btn_premium": "Liberar Premium",
        "why_title": "O que é SensuTV?",
        "why_b1": "Conteúdo organizado por modelo e país",
        "why_b2": "Acesso privado + Premium via bot",
        "why_b3": "Catálogo rápido e elegante",
        "latest": "Últimos envios",
        "latest_note": "Isso vem do registro (uploads.json).",
        "status": "Status",
        "open_bot": "Abrir bot no Telegram",
        "premium_title": "Premium",
        "premium_desc": "Libere acesso completo pelo Telegram.",
        "back": "Voltar",
        "no_items": "Ainda não há uploads registrados.",
        "lang": "Idioma",
    },
    "en": {
        "title": "SensuTV",
        "subtitle": "Webapp on Render + bot on Telegram + media on Wasabi.",
        "hero": "Come in… and see what others don’t 🔥",
        "desc": "Free previews. Want full access? Unlock Premium.",
        "btn_free": "View free previews",
        "btn_premium": "Unlock Premium",
        "why_title": "What is SensuTV?",
        "why_b1": "Content organized by model and country",
        "why_b2": "Private access + Premium via bot link",
        "why_b3": "Fast catalog-style UI",
        "latest": "Latest uploads",
        "latest_note": "This is driven by the registry (uploads.json).",
        "status": "Status",
        "open_bot": "Open bot on Telegram",
        "premium_title": "Premium",
        "premium_desc": "Unlock full access via Telegram.",
        "back": "Back",
        "no_items": "No uploads registered yet.",
        "lang": "Language",
    },
}

def pick_lang():
    q = (request.args.get("lang") or "").strip().lower()
    if q in SUPPORTED:
        return q
    header = (request.headers.get("Accept-Language") or "").lower()
    for code in SUPPORTED:
        if code in header:
            return code
    return "es"

# =========================
# UI (HTML)
# =========================
BASE_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>{{t["title"]}}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body{font-family:system-ui,Arial;margin:0;background:#0b0b10;color:#fff}
    .wrap{max-width:980px;margin:0 auto;padding:22px}
    .top{display:flex;align-items:center;justify-content:space-between;gap:12px}
    .brand h1{margin:0;font-size:34px;letter-spacing:.2px}
    .brand .sub{color:#b9b9c9;margin-top:6px}
    .lang a{color:#bfa7ff;text-decoration:none;margin-left:10px;font-size:14px}
    .card{background:#141421;border:1px solid #2a2a3a;border-radius:18px;padding:18px;margin:14px 0;box-shadow:0 10px 30px rgba(0,0,0,.25)}
    .hero{padding:22px}
    .hero h2{margin:0 0 10px 0;font-size:28px}
    .muted{color:#b9b9c9}
    .btnrow{display:flex;flex-wrap:wrap;gap:10px;margin-top:14px}
    .btn{display:inline-block;padding:12px 16px;border-radius:14px;text-decoration:none;font-weight:700}
    .btn1{background:#6d28d9;color:#fff}
    .btn2{background:#ff3d8a;color:#fff}
    .btn3{background:#1f2937;color:#fff;border:1px solid #2a2a3a}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
    .pill{display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid #2a2a3a;color:#cfcfe6;font-size:12px}
    .mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#cfcfe6;word-break:break-all}
    .item{background:#11111a;border:1px solid #2a2a3a;border-radius:16px;padding:14px}
    ul{margin:10px 0 0 18px;color:#cfcfe6}
    footer{margin:18px 0;color:#8791a6;font-size:12px}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div class="brand">
        <h1>{{t["title"]}}</h1>
        <div class="sub">{{t["subtitle"]}}</div>
      </div>
      <div class="lang">
        <span class="muted">{{t["lang"]}}:</span>
        <a href="{{url_for(request.endpoint, **request.view_args, lang='es')}}{% if request.query_string %}&{% endif %}">ES</a>
        <a href="{{url_for(request.endpoint, **request.view_args, lang='de')}}{% if request.query_string %}&{% endif %}">DE</a>
        <a href="{{url_for(request.endpoint, **request.view_args, lang='pt')}}{% if request.query_string %}&{% endif %}">PT</a>
        <a href="{{url_for(request.endpoint, **request.view_args, lang='en')}}{% if request.query_string %}&{% endif %}">EN</a>
      </div>
    </div>

    {{content|safe}}

    <footer>
      Bucket: <b>{{bucket}}</b> • Region: <b>{{region}}</b> • DATA_DIR: <span class="mono">{{data_dir}}</span>
    </footer>
  </div>
</body>
</html>
"""

def render_page(content_html: str):
    lang = pick_lang()
    t = I18N[lang]
    return render_template_string(
        BASE_HTML,
        content=content_html,
        t=t,
        bucket=WASABI_BUCKET,
        region=WASABI_REGION,
        data_dir=DATA_DIR,
    )

# =========================
# Flask App
# =========================
app = Flask(__name__)

@app.get("/healthz")
def healthz():
    return "ok", 200

@app.get("/")
def home():
    lang = pick_lang()
    t = I18N[lang]

    uploads = load_uploads().get("items", [])
    items = list(reversed(uploads))[:6]

    latest_html = ""
    if not items:
        latest_html = f'<div class="muted">{t["no_items"]}</div>'
    else:
        cards = []
        for it in items:
            cards.append(f"""
              <div class="item">
                <div class="pill">{it.get("model_name","")} • {it.get("country","")}</div>
                <div style="margin-top:10px"><b>{it.get("title","Nuevo contenido")}</b></div>
                <div class="muted" style="margin-top:6px">{it.get("type","")} • {it.get("date","")}</div>
                <div class="mono" style="margin-top:10px">{it.get("bucket","")}/{it.get("path","")}</div>
              </div>
            """)
        latest_html = f'<div class="grid">{"".join(cards)}</div>'

    bot_line = ""
    if BOT_PAY_LINK:
        bot_line = f'<div class="muted" style="margin-top:12px">Bot: <span class="mono">{BOT_PAY_LINK}</span></div>'

    content = f"""
      <div class="card hero">
        <h2>{t["hero"]}</h2>
        <div class="muted">{t["desc"]}</div>

        <div class="btnrow">
          <a class="btn btn1" href="/feed?lang={lang}">{t["btn_free"]}</a>
          <a class="btn btn2" href="/premium?lang={lang}">{t["btn_premium"]}</a>
        </div>
        {bot_line}
      </div>

      <div class="card">
        <h3>{t["why_title"]}</h3>
        <ul>
          <li>{t["why_b1"]}</li>
          <li>{t["why_b2"]}</li>
          <li>{t["why_b3"]}</li>
        </ul>
      </div>

      <div class="card">
        <h3>{t["latest"]}</h3>
        <div class="muted">{t["latest_note"]}</div>
        <div style="margin-top:12px">{latest_html}</div>
      </div>
    """
    return render_page(content)

@app.get("/feed")
def feed():
    lang = pick_lang()
    t = I18N[lang]
    uploads = load_uploads().get("items", [])
    items = list(reversed(uploads))[:50]

    if not items:
        body = f'<div class="card"><h3>{t["btn_free"]}</h3><div class="muted">{t["no_items"]}</div><div class="btnrow"><a class="btn btn3" href="/?lang={lang}">{t["back"]}</a></div></div>'
        return render_page(body)

    cards = []
    for it in items:
        cards.append(f"""
          <div class="item">
            <div class="pill">{it.get("model_name","")} • {it.get("country","")}</div>
            <div style="margin-top:10px"><b>{it.get("title","Nuevo contenido")}</b></div>
            <div class="muted" style="margin-top:6px">{it.get("type","")} • {it.get("category","")} • {it.get("date","")}</div>
            <div class="mono" style="margin-top:10px">{it.get("bucket","")}/{it.get("path","")}</div>
          </div>
        """)

    body = f"""
      <div class="card">
        <h3>{t["btn_free"]}</h3>
        <div class="muted">{t["latest_note"]}</div>
        <div style="margin-top:12px" class="grid">
          {''.join(cards)}
        </div>
        <div class="btnrow" style="margin-top:16px">
          <a class="btn btn3" href="/?lang={lang}">{t["back"]}</a>
          <a class="btn btn2" href="/premium?lang={lang}">{t["btn_premium"]}</a>
        </div>
      </div>
    """
    return render_page(body)

@app.get("/premium")
def premium():
    lang = pick_lang()
    t = I18N[lang]
    bot_btn = ""
    if BOT_PAY_LINK:
        bot_btn = f'<a class="btn btn2" href="{BOT_PAY_LINK}">{t["open_bot"]}</a>'
    else:
        bot_btn = '<div class="muted">BOT_PAY_LINK no está configurado en Render.</div>'

    body = f"""
      <div class="card hero">
        <h2>{t["premium_title"]}</h2>
        <div class="muted">{t["premium_desc"]}</div>
        <div class="btnrow">
          {bot_btn}
          <a class="btn btn3" href="/?lang={lang}">{t["back"]}</a>
        </div>
      </div>
    """
    return render_page(body)

# API (para uso interno)
@app.get("/api/models")
def api_models():
    return jsonify(load_models())

@app.get("/api/uploads")
def api_uploads():
    return jsonify(load_uploads())

if __name__ == "__main__":
    logger.info("Starting SensuTV WEBAPP on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False)
