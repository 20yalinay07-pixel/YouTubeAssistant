"""
YouTube Assistant - Licensing Server
=====================================
Bagimsiz, HERKESE ACIK (public) olarak barindirilmasi gereken kucuk bir Flask
servisi. Yerel `backend/server.py`'den TAMAMEN AYRI -- o hala kullanicinin
kendi bilgisayarinda, sadece kendi AI anahtarlariyla calisir. BU servis
sadece "bu lisans anahtari gecerli mi, hangi ozellikleri aciyor" sorusunu
cevaplar ve Lemon Squeezy'den gelen odeme olaylarini isler.

Admin paneli BILEREK burada DEGIL -- ayri ve HIC deploy edilmeyen
`licensing_admin/` klasorunde (bkz. o klasorun README/docstring'i). Boylece
bu herkese acik servisin internetten erisilebilir HICBIR admin/sifre
endpoint'i olmuyor, saldiri yuzeyi kuculuyor.

Lemon Squeezy magazasi: https://digitalhelperforall.lemonsqueezy.com

Ortam degiskenleri (.env veya hosting panelinden):
  DATABASE_URL                -- SQLAlchemy baglanti string'i (varsayilan: yerel sqlite, gelistirme icin)
  LEMONSQUEEZY_WEBHOOK_SECRET  -- Lemon Squeezy panelinde webhook olustururken belirlenen "Signing secret"
  FLASK_SECRET_KEY             -- oturum (session) cookie'lerini imzalamak icin rastgele bir metin
  LS_CHECKOUT_URL_BUNDLE/CHAT/ADSKIP -- her urunun checkout linki
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
CORS(app)  # eklenti (chrome-extension://...) buradan istek atacak

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///licenses.db")
# Render/Heroku tarzi platformlar bazen "postgres://" verir, SQLAlchemy 2.x "postgresql://" ister.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

LEMONSQUEEZY_WEBHOOK_SECRET = os.environ.get("LEMONSQUEEZY_WEBHOOK_SECRET", "")

# Lemon Squeezy'de 3 urunu (Bundle $40, Ad Skip $15, Unlimited Chat $30)
# olusturduktan sonra HER BIRININ checkout linkini buraya yapistirin (urun
# sayfasinda "Copy checkout URL" ile alinir). Bos birakilirsa "Subscribe"
# butonlari tikladiginda hicbir yere gitmez -- bu yuzden gercek linkleri
# eklemeden siteyi paylasmayin.
CHECKOUT_URLS = {
    "bundle": os.environ.get("LS_CHECKOUT_URL_BUNDLE", "#"),
    "adskip": os.environ.get("LS_CHECKOUT_URL_ADSKIP", "#"),
    "chat": os.environ.get("LS_CHECKOUT_URL_CHAT", "#"),
}

# Fiyatlandirma sadece BILGI amacli burada tutulur (gercek fiyat/faturalama
# Lemon Squeezy panelinde yonetilir) -- admin panelinde gosterim icin.
PLAN_INFO = {
    "bundle": {"label": "Bundle (Unlimited Chat + Ad Skip)", "price_usd": 40, "features": ["unlimited_chat", "ad_skip"]},
    "chat": {"label": "Unlimited Chat", "price_usd": 30, "features": ["unlimited_chat"]},
    "adskip": {"label": "Ad Skip", "price_usd": 15, "features": ["ad_skip"]},
}


class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    license_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    plan = db.Column(db.String(32), nullable=False)  # "bundle" | "chat" | "adskip"
    status = db.Column(db.String(32), nullable=False, default="active")  # active | cancelled | expired | past_due
    ls_subscription_id = db.Column(db.String(64), nullable=True, index=True)
    ls_customer_id = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    renews_at = db.Column(db.DateTime, nullable=True)
    manual_override = db.Column(db.Boolean, default=False)  # admin elle actiysa/kapattiysa, webhook bunu EZMESIN

    def features(self) -> dict:
        plan_features = PLAN_INFO.get(self.plan, {}).get("features", [])
        return {
            "unlimited_chat": self.status == "active" and "unlimited_chat" in plan_features,
            "ad_skip": self.status == "active" and "ad_skip" in plan_features,
        }

    def to_dict(self) -> dict:
        return {
            "license_key": self.license_key,
            "email": self.email,
            "plan": self.plan,
            "status": self.status,
            "features": self.features(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "renews_at": self.renews_at.isoformat() if self.renews_at else None,
        }


with app.app_context():
    db.create_all()


def generate_license_key() -> str:
    # Okunakli, tirak-ayirmali bir anahtar: YTAS-XXXX-XXXX-XXXX
    raw = secrets.token_hex(6).upper()
    return f"YTAS-{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


# ==================== PAZARLAMA / FIYATLANDIRMA SAYFASI ====================

@app.route("/")
def landing_page():
    return render_template("landing.html", checkout_urls=CHECKOUT_URLS)


# ==================== EKLENTININ CAGIRDIGI UC NOKTA ====================

@app.route("/api/license/verify", methods=["POST"])
def verify_license():
    data = request.get_json(silent=True) or {}
    key = (data.get("license_key") or "").strip().upper()
    if not key:
        return jsonify({"valid": False, "error": "license_key gerekli"}), 400

    lic = License.query.filter_by(license_key=key).first()
    if not lic:
        return jsonify({"valid": False, "error": "Lisans anahtari bulunamadi"}), 404

    return jsonify({
        "valid": lic.status == "active",
        "status": lic.status,
        "plan": lic.plan,
        "features": lic.features(),
    })


# ==================== LEMON SQUEEZY WEBHOOK ====================
# Lemon Squeezy panelinde: Settings -> Webhooks -> bu servisin
# https://.../webhook/lemonsqueezy adresini ekleyin, gonderilecek olaylar:
# subscription_created, subscription_updated, subscription_cancelled,
# subscription_expired, subscription_resumed, subscription_payment_failed.
# "Signing secret" alanindaki degeri LEMONSQUEEZY_WEBHOOK_SECRET olarak girin.

def _verify_ls_signature(raw_body: bytes, signature_header: str) -> bool:
    if not LEMONSQUEEZY_WEBHOOK_SECRET:
        return False
    digest = hmac.new(LEMONSQUEEZY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature_header or "")


# Lemon Squeezy "variant" (urun) adi -> bizim plan koduna eslesme. Kendi
# Lemon Squeezy panelinizde urun/variant adlarini bunlarla ES GECIRIN, ya da
# asagidaki sozlugu kendi gercek variant ID'lerinizle guncelleyin.
LS_VARIANT_TO_PLAN = {
    # "123456": "bundle",
    # "123457": "chat",
    # "123458": "adskip",
}


def _plan_from_payload(payload: dict) -> str:
    attrs = payload.get("data", {}).get("attributes", {})
    variant_id = str(attrs.get("variant_id") or "")
    if variant_id in LS_VARIANT_TO_PLAN:
        return LS_VARIANT_TO_PLAN[variant_id]
    # Yedek: variant/urun adinda gecen anahtar kelimeye bak.
    name = (attrs.get("variant_name") or attrs.get("product_name") or "").lower()
    if "bundle" in name or "paket" in name:
        return "bundle"
    if "chat" in name or "sohbet" in name:
        return "chat"
    if "ad" in name or "reklam" in name:
        return "adskip"
    return "bundle"  # bilinmiyorsa en genis pakete dus (kullaniciyi magdur etmemek icin)


@app.route("/webhook/lemonsqueezy", methods=["POST"])
def lemonsqueezy_webhook():
    raw_body = request.get_data()
    signature = request.headers.get("X-Signature", "")
    if not _verify_ls_signature(raw_body, signature):
        return jsonify({"error": "Gecersiz imza"}), 401

    payload = request.get_json(silent=True) or {}
    event_name = payload.get("meta", {}).get("event_name", "")
    attrs = payload.get("data", {}).get("attributes", {})
    email = (attrs.get("user_email") or attrs.get("customer_email") or "").strip().lower()
    subscription_id = str(payload.get("data", {}).get("id") or "")
    customer_id = str(attrs.get("customer_id") or "")
    ls_status = attrs.get("status", "")  # "active" | "cancelled" | "expired" | "past_due" | "on_trial" | "paused"
    renews_at_raw = attrs.get("renews_at")

    if not email or not subscription_id:
        return jsonify({"error": "email/subscription_id eksik"}), 400

    lic = License.query.filter_by(ls_subscription_id=subscription_id).first()

    if event_name == "subscription_created":
        if not lic:
            lic = License(
                license_key=generate_license_key(),
                email=email,
                plan=_plan_from_payload(payload),
                status="active",
                ls_subscription_id=subscription_id,
                ls_customer_id=customer_id,
            )
            db.session.add(lic)
    elif lic and not lic.manual_override:
        # active / cancelled / expired / past_due / on_trial / paused -> dogrudan yansit
        lic.status = "active" if ls_status in ("active", "on_trial") else ls_status

    if lic and renews_at_raw:
        try:
            lic.renews_at = datetime.fromisoformat(renews_at_raw.replace("Z", "+00:00"))
        except Exception:
            pass

    db.session.commit()
    return jsonify({"ok": True})


# ==================== SATIN ALMA SONRASI: LISANS ANAHTARINI GOSTER ====================
# Lemon Squeezy checkout "redirect URL" ayarina bu sayfayi verin:
#   https://.../success?email={{ checkout.email }}

@app.route("/success", methods=["GET", "POST"])
def success_page():
    email = (request.values.get("email") or "").strip().lower()
    lic = License.query.filter_by(email=email).order_by(License.created_at.desc()).first() if email else None
    return render_template("success.html", license=lic, email=email, searched=bool(email))


@app.route("/health")
def health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
