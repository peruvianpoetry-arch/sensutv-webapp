import os
import json
import logging
from datetime import datetime
from typing import Any, Dict

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
BOT_PAY_LINK = os.getenv("BOT_PAY_LINK", "").strip()

WASABI_BUCKET = os.getenv("WASABI_BUCKET", "sensutv-media")
WASABI_REGION = os.getenv("WASABI_REGION", "eu-central-2")

# Persistencia: intenta /var/data (Disk). Si no, /tmp/data (free)
DEFAULT_DATA_DIR = os.getenv("DATA_DIR", "/var/data")
DATA_DIR = DEFAULT_DATA_DIR

def ensure_data_dir():
    global DATA_DIR
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        testfile = os.path.join(DATA_DIR, ".write_test")
        with open(testfile, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(testfile)
        logger.info("✅ DATA_DIR OK: %s", DATA_DIR)
    except Exception as e:
        logger.warning("⚠️ No se pudo usar DATA_DIR=%s (%s). fallback /tmp/data", DATA_DIR, e)
        DATA_DIR = "/tmp/data"
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info("✅ DATA_DIR fallback activo: %s", DATA_DIR)

ensure_data_dir()

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

def load_uploads() -> Dict[str, Any]:
    return _load_json(UPLOADS_FILE, {"items": []})

# =========================
# FLASK
# =========================
app = Flask(__name__)

HOME_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>SensuTV</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body{font-family:system-ui,Arial;margin:0;background:#0b0b10;color:#fff}
    .wrap{max-width:900px;margin:0 auto;padding:24px}
    .card{background:#141421;border:1px solid #2a2a3a;border-radius:16px;padding:18px;margin:14px 0}
    .btn{display:inline-block;padding:12px 16px;border-radius:14px;text-decoration:none;margin-right:10px}
    .btn1{background:#6d28d9;color:#fff}
    .btn2{background:#ff3d8a;color:#fff}
    .muted{color:#b9b9c9}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
    .pill{display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid #2a2a3a;color:#cfcfe6;font-size:12px}
    .mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#cfcfe6;word-break:break-all}
    a{color:#bfa7ff}
  </style>
</head>
<body>
  <div class="wrap">
    <h2>SensuTV</h2>
    <div class="muted">Webapp en Render + bot en Telegram + media en Wasabi.</div>

    <div class="card">
      <h3>Entra... y mira lo que otros no ven 🔥</h3>
      <div class="muted">Previews gratis. Si quieres lo completo... desbloquea Premium.</div>
      <div style="margin-top:14px">
        <a class="btn btn1" href="/feed?tier=free">Ver previews gratis</a>
        <a class="btn btn2" href="/premium">Desbloquear Premium</a>
      </div>
      {% if bot_pay_link %}
      <div style="margin-top:12px" class="muted">
        Link bot: <span class="mono">{{bot_pay_link}}</span>
      </div>
      {% endif %}
    </div>

    <div class="card">
      <h3>Últimas subidas (registro)</h3>
      <div class="muted">Se alimenta de <span class="mono">uploads.json</span> (lo crea el bot).</div>
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
    </div>

    <div class="card">
      <h3>Estado</h3>
      <div class="muted">
        Bucket: <b>{{bucket}}</b> • Region: <b>{{region}}</b><br/>
        DATA_DIR: <span class="mono">{{data_dir}}</span><br/>
        API: <a href="/api/models">/api/models</a> • <a href="/api/uploads">/api/uploads</a>
      </div>
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
    uploads = load_uploads().get("items", [])
    items = list(reversed(uploads))[:6]
    return render_template_string(
        HOME_HTML,
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
    tier = request.args.get("tier", "free")
    data = load_uploads().get("items", [])
    return jsonify({"tier": tier, "items": list(reversed(data))})

@app.get("/premium")
def premium():
    if BOT_PAY_LINK:
        return jsonify({"ok": True, "next": BOT_PAY_LINK})
    return jsonify({"ok": False, "error": "BOT_PAY_LINK not set"}), 400

if __name__ == "__main__":
    logger.info("Starting SensuTV WEBAPP on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT, debug=False)
