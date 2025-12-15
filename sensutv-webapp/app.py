import os, json, hmac, hashlib, time
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
DATA_DIR = os.environ.get("DATA_DIR", "/var/data")
ACCESS_FILE = os.path.join(DATA_DIR, "access.json")

def validate_init_data(init_data: str) -> dict | None:
    if not TELEGRAM_BOT_TOKEN or not init_data:
        return None

    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)
    if not received_hash:
        return None

    check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    secret_key = hashlib.sha256(TELEGRAM_BOT_TOKEN.encode()).digest()
    computed_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()

    if computed_hash != received_hash:
        return None
    return data

def load_access() -> dict:
    try:
        with open(ACCESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def is_premium(user_id: str) -> tuple[bool, int]:
    access = load_access()
    rec = access.get(str(user_id))
    if not rec:
        return (False, 0)
    exp = int(rec.get("expires", 0))
    return (exp > int(time.time()), exp)

@app.get("/")
def home():
    return render_template("index.html")

@app.post("/api/session")
def api_session():
    body = request.get_json(silent=True) or {}
    init_data = body.get("initData", "")
    data = validate_init_data(init_data)

    # MODO PRUEBA: si aún no pones TELEGRAM_TOKEN en Render, funciona igual (modo mock)
    if data is None:
        return jsonify({
            "ok": True,
            "mode": "mock",
            "user": {"id": "0000", "first_name": "Guest"},
            "premium": False,
            "expires": 0
        })

    user_raw = json.loads(data.get("user", "{}"))
    uid = str(user_raw.get("id"))
    premium, exp = is_premium(uid)

    return jsonify({
        "ok": True,
        "mode": "real",
        "user": {"id": uid, "first_name": user_raw.get("first_name", "")},
        "premium": premium,
        "expires": exp
    })

@app.get("/api/content")
def api_content():
    catalog = {
        "free": [
            {
                "id": "f1",
                "type": "video",
                "title": "Preview 01",
                "thumb": os.environ.get("WASABI_THUMB_1", ""),
                "url": os.environ.get("WASABI_FREE_1", ""),
                "limitSeconds": 10
            }
        ],
        "premium": [
            {
                "id": "p1",
                "type": "video",
                "title": "Full 01",
                "thumb": os.environ.get("WASABI_THUMB_2", ""),
                "url": os.environ.get("WASABI_PREMIUM_1", "")
            }
        ],
        "models": [
            {"id": "aurora", "name": "Aurora", "flag": "🇧🇷", "cover": os.environ.get("WASABI_MODEL_AURORA", "")}
        ]
    }
    return jsonify({"ok": True, "catalog": catalog})

@app.post("/api/checkout_link")
def api_checkout_link():
    link = os.environ.get("BOT_PAY_LINK", "https://t.me/tu_bot")
    return jsonify({"ok": True, "url": link})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
