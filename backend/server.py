"""
Youtube Asistanı Backend - GROQ + PREMIUM SÜRÜMÜ

Yenilikler:
- Her özellik (özet/analiz/bölümler/öneriler) için o özelliğe özgü sohbet kutusu
  -> /api/chat endpoint'i, ilgili özelliğin çıktısını + transkripti bağlam olarak kullanır
- Öneriler artık gerçek YouTube videolarıyla eşleştiriliyor (yt-dlp arama)
  ve küçük oynatıcı (embed) ile birlikte dönüyor
- Basit bellek-içi cache: transkript, özellik sonucu, sohbet geçmişi video+özellik
  bazında saklanır (sunucu yeniden başlatılınca sıfırlanır - normaldir)
"""

import concurrent.futures
import json
import random
import threading
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from openai import OpenAI  # Groq, OpenAI SDK'sı ile uyumlu çalışır
import requests
from langdetect import detect as _langdetect_detect, DetectorFactory as _LangDetectorFactory
_LangDetectorFactory.seed = 0  # sonuclar calistirmalar arasi tutarli olsun diye
from dotenv import load_dotenv

import ytdlp_bypass

# API anahtarlari SADECE proje kokundeki .env dosyasindan okunur (kod icinde
# sabit/hardcoded anahtar TUTULMAZ -- guvenlik nedeniyle, bkz. .env.example).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

# Backend, tepsi (tray) uygulaması üzerinden pythonw.exe ile konsolsuz çalışır.
# Ama yt-dlp/ffmpeg gibi alt süreçler (subprocess.run ile çağrılan) kendi konsol
# subsystem'lerini istedikleri için, Windows bunlar için YENİ, GÖRÜNÜR bir
# conhost.exe penceresi açıyordu -- her video işlenirken (metadata/altyazı/ses
# indirme gibi bir video başına onlarca kez) ekranda kısa kısa pencereler
# belirip kayboluyordu, kötü bir izlenim bırakıyordu. Bunu TEK bir noktadan,
# tüm subprocess.run çağrılarını saran küçük bir sarmalayıcıyla engelliyoruz;
# tek tek her çağrıyı değiştirmek yerine (hata riski daha yüksek).
if os.name == "nt":
    _orig_subprocess_run = subprocess.run

    def _subprocess_run_no_window(*args, **kwargs):
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        return _orig_subprocess_run(*args, **kwargs)

    subprocess.run = _subprocess_run_no_window

app = Flask(__name__)
CORS(app)

# ==================== AYARLAR ====================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Groq zaman zaman model katalogunu degistirip eski ID'leri kaldiriyor (orn.
# "modelX does not exist or you do not have access to it" donmeye basladigi
# oldu). Tek bir sabit ID yerine, ilk calisan modele dusene kadar sirayla
# denenen bir liste kullaniliyor -> Groq katalog degisikliklerinde kirilmaz.
# "llama-3.3-70b-versatile" bu hesapta/anahtarda TUTARLI olarak "does not exist
# or you do not have access to it" donuyor (dogrulandi, her cagrida basarisiz) --
# ONCE denenip her seferinde basarisiz olmasi gereksiz bir round-trip israfi, o
# yuzden calisan model basa alindi.
GROQ_CHAT_MODELS = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
]
GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"  # large-v3'e göre belirgin daha hızlı, kalite farkı küçük

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# OpenRouter'ın ücretsiz model kataloğu zaman zaman değişir. Bu ID çalışmazsa
# openrouter.ai/models?max_price=0 adresinden güncel bir ":free" model ID'si
# alıp buraya yazın.
OPENROUTER_CHAT_MODEL = "openrouter/free"  # OpenRouter'ın kendi otomatik ücretsiz model yönlendiricisi;
# ücretsiz model kataloğu sık değiştiği için sabit bir ID yerine bunu kullanmak
# "model kullanılamıyor / 404" hatalarını önler (liste değişse de otomatik uyum sağlar).
# OpenRouter'da SES (Whisper) endpoint'i YOK -> transkript çıkarımı için yedek
# olarak kullanılamaz, sadece METİN üretimi (özet/analiz/bölüm/öneri/sohbet) için
# yedeklenir.

# Sırasıyla denenecek metin-üretimi sağlayıcıları. Groq önce denenir; başarısız
# olursa (hız limiti, geçici kesinti vb.) otomatik olarak OpenRouter'a geçilir.
OMNIROUTE_BASE_URL = "http://localhost:20128/v1"
OMNIROUTE_CHAT_MODEL = "auto"  # OmniRoute her istek için göreve en uygun modeli kendi seçer

# Kullanıcının OmniRoute'ta göreve özel çıkardığı anahtarlar. Her görev kendi
# anahtarını kullanır (OmniRoute panelinde her anahtara ayrı bir "combo"
# atanabildiği için, örn. özetleyici farklı bir modelle çalışabilir).
OMNIROUTE_FEATURE_KEYS = {
    "chat": os.environ.get("OMNIROUTE_KEY_CHAT", ""),                       # yönetici (genel amaçlı / göreve özel anahtarı olmayan çağrılar)
    "summarize": os.environ.get("OMNIROUTE_KEY_SUMMARIZE", ""),             # özetleyici
    "analyze": os.environ.get("OMNIROUTE_KEY_ANALYZE", ""),                 # transkriptor (en yakın eşleşme)
    "recommendations": os.environ.get("OMNIROUTE_KEY_RECOMMENDATIONS", ""), # video önerici
    "chapters": os.environ.get("OMNIROUTE_KEY_CHAPTERS", ""),               # video bölümleyici
}

# Belirli bir göreve atanmamış OmniRoute çağrıları (örn. uzun video parça-notu
# çıkarımı, birleşik özet+analiz+bölüm+öneri üretimi) varsayılan olarak
# "yönetici" anahtarını kullanır -> anlamsız bir placeholder yerine her zaman
# geçerli, gerçek bir anahtar kullanılmış olur.
OMNIROUTE_API_KEY = os.environ.get("OMNIROUTE_API_KEY", "").strip() or OMNIROUTE_FEATURE_KEYS.get("chat", "local")

# DOGRUDAN saglayici anahtarlari (OmniRoute PROXY'si DEGIL) -- OmniRoute'un
# AssemblyAI ve Exa Search icin kendi proxy/pass-through destegi bozuk oldugu
# dogrulandi (panel testi + /models endpoint'i basarili "upstream gecerli"
# diyor ama gercek istek 401 donuyor, /models "API unavailable, local catalog
# kullaniliyor" uyarisi veriyor -- OmniRoute'un kendi eksikligi). Bu yuzden bu
# iki saglayici icin OmniRoute'u atlayip GERCEK saglayici API'lerini dogrudan
# cagiriyoruz. Anahtarlar OmniRoute panelinde de kayitli olan AYNI hesaplar.
ASSEMBLYAI_API_KEY_SUMMARIZE = os.environ.get("ASSEMBLYAI_API_KEY_SUMMARIZE", "")  # "Ozetleyici" hesabi
ASSEMBLYAI_API_KEY_CHAPTERS = os.environ.get("ASSEMBLYAI_API_KEY_CHAPTERS", "")    # "VideoBolumleyici" hesabi
EXA_SEARCH_API_KEY = os.environ.get("EXA_SEARCH_API_KEY", "")                      # "video önerici" hesabi

# OPSIYONEL 4. yedek: FreeLLMAPI (https://github.com/tashfeenahmed/freellmapi) --
# yerelde Docker ile calisan, 34+ ucretsiz LLM saglayicisini TEK bir OpenAI-uyumlu
# anahtar arkasinda toplayan bagimsiz bir proxy. BU KULLANICI icin zorunlu DEGIL
# (Groq/OmniRoute/OpenRouter zaten calisiyor, siralama degismiyor) -- ama .env'de
# FREELLMAPI_API_KEY tanimlanmazsa asagidaki provider listesinde otomatik atlanir,
# tanimlanirsa en sona (son care) eklenir. Boylece YENI bir kullanici, Groq/
# OmniRoute/AssemblyAI/Exa icin ayri ayri hesap acmak yerine SADECE FreeLLMAPI'yi
# kurup TEK anahtarla projeyi calistirabilir (diger 3 saglayicinin anahtari bos
# oldugu icin otomatik atlanir, FreeLLMAPI tek aktif saglayici olur).
FREELLMAPI_API_KEY = os.environ.get("FREELLMAPI_API_KEY", "").strip()
FREELLMAPI_BASE_URL = os.environ.get("FREELLMAPI_BASE_URL", "http://localhost:3001/v1").strip()

# SIRALAMA ONEMLI: Groq ve OpenRouter ONCE denenir, OmniRoute EN SONA alindi.
# Olcumle dogrulandi: OmniRoute'un sikistirma ("compression") katmani, uzunca
# promptlarda (orn. birlesik ozet+analiz+bolum+oneri uretimi) bazen TAMAMEN
# ALAKASIZ icerik donduruyor (test: bir Python dersi videosu icin "YAGNI
# prensibi"/genel yazilim tavsiyesi gibi konuyla hic ilgisi olmayan bir metin
# geldi) VE 30-70+ saniyeye kadar suruyor. Ayni istek OmniRoute atlanip
# dogrudan Groq'a gidince 3-4 saniyede VE doğru icerikle donuyor. OmniRoute'un
# sikistirmasini API'den kapatmak icin admin yetkisi gerekiyor (401), o yuzden
# en guvenli cozum onu varsayilan/hizli yoldan cikarip son care yapmak oldu.
TEXT_PROVIDERS = [
    {"name": "groq", "api_key": GROQ_API_KEY, "base_url": GROQ_BASE_URL, "models": GROQ_CHAT_MODELS},
    {"name": "openrouter", "api_key": OPENROUTER_API_KEY, "base_url": OPENROUTER_BASE_URL, "models": [OPENROUTER_CHAT_MODEL]},
    {"name": "omniroute", "api_key": OMNIROUTE_API_KEY, "base_url": OMNIROUTE_BASE_URL, "models": [OMNIROUTE_CHAT_MODEL]},
    # Sadece FREELLMAPI_API_KEY .env'de tanimliysa devreye girer (yukaridaki not).
    {"name": "freellmapi", "api_key": FREELLMAPI_API_KEY, "base_url": FREELLMAPI_BASE_URL, "models": ["auto"]},
]

YTDLP_CMD = ["yt-dlp"]

# ==================== BELLEK-İÇİ CACHE ====================
# NOT: Bu basit bir yerel araç olduğu için bellek-içi (in-memory) cache yeterli.
# Sunucu yeniden başlatılınca temizlenir.
TRANSCRIPT_CACHE: dict[str, str] = {}
TRANSCRIPT_LANG_CACHE: dict[str, str] = {}  # video_id -> algilanan orijinal dil kodu (orn. "en")
# AYNI video için ÇAKIŞAN istekler (örn. frontend'de bir hata/çift-tıklama
# yüzünden aynı anda birden fazla /api/prepare çağrısı gitmesi) burada
# SIRAYA ALINIR -- sadece İLK istek gerçekten transkript çıkarır, geri kalanı
# onun sonucunu bekleyip PAYLAŞIR. Böylece backend, frontend'de olası bir
# sorun olsa bile aynı video için paralel 5x yt-dlp/Whisper çağrısı YAPMAZ.
_TRANSCRIPT_FETCH_LOCKS: dict[str, threading.Lock] = {}
_TRANSCRIPT_FETCH_LOCKS_META_LOCK = threading.Lock()


def _get_transcript_fetch_lock(video_id: str) -> threading.Lock:
    with _TRANSCRIPT_FETCH_LOCKS_META_LOCK:
        if video_id not in _TRANSCRIPT_FETCH_LOCKS:
            _TRANSCRIPT_FETCH_LOCKS[video_id] = threading.Lock()
        return _TRANSCRIPT_FETCH_LOCKS[video_id]
MATERIAL_CACHE: dict[str, str] = {}               # video_id -> videonun TAMAMını kapsayan işlenmiş bağlam
FEATURE_CACHE: dict[tuple, object] = {}          # (video_id, feature) -> sonuç
TRANSCRIPT_TRANSLATION_CACHE: dict[tuple, str] = {}  # (video_id, target_lang) -> cevrilmis transkript
# AssemblyAI'nin GERÇEK zaman damgalı "auto_chapters" özelliğinden gelen bölümler
# (arka planda, ana akışı bloklamadan doldurulur -- bkz. _assemblyai_start_chapters_job).
# generate_all_features_combined bu cache'de veri varsa AI'ye zaman damgası
# UYDURTMAK yerine doğrudan bunu kullanır.
ASSEMBLYAI_CHAPTERS_CACHE: dict[str, str] = {}    # video_id -> "[MM:SS] Baslik - aciklama" formatinda hazir metin
_ASSEMBLYAI_JOBS_STARTED: set = set()  # video_id -- ayni video icin (Deepgram+Whisper ikisi de ses indirirse) mukerrer is baslatmayi engeller
CHAT_HISTORY_CACHE: dict[tuple, list] = {}        # (video_id, feature) -> [{"role","content"}, ...]
# (video_id, lang) -> AI'nin ürettiği ham öneri başlıkları (title/reason), henüz
# gerçek YouTube videosuyla eşleştirilmemiş (yt-dlp araması yapılmamış). /api/prepare
# bu adımı ARTIK YAPMIYOR (3-8sn sürüp diğer 4 sekmeyi bloke ediyordu); arama,
# frontend zaten aynı anda çağırdığı /api/recommendations isteğinde yapılır.
RAW_RECOMMENDATIONS_CACHE: dict[tuple, list] = {}

# Modelin bağlam penceresine tek seferde rahatça sığacak yaklaşık karakter sınırı.
# Bunun altındaki transkriptler doğrudan, üstündekiler parçalara bölünerek işlenir
# (böylece SADECE videonun başı değil TAMAMI dikkate alınır).
MAX_DIRECT_CHARS = 90000
CHUNK_CHARS = 45000

FEATURE_LABELS = {
    "summarize": "özet",
    "analyze": "konu analizi",
    "chapters": "bölümlendirme",
    "recommendations": "video önerileri",
}

# Her özellik (özet/analiz/bölümler/öneriler) altındaki sohbet kutusu için
# video+özellik başına ücretsiz mesaj sınırı. "⭐ Ekstra Özellikler -> Yapay
# Zeka ile Sınırsız Chat" açıldığında frontend 'unlimited: true' gönderir ve
# bu sınır uygulanmaz.
FREE_CHAT_MESSAGE_LIMIT = 3


_client_cache: dict = {}


def _client_for(provider: dict, api_key_override: str = None) -> OpenAI:
    name = provider["name"]
    key = api_key_override or provider["api_key"]
    cache_key = (name, key)
    if cache_key not in _client_cache:
        extra_headers = {}
        if name == "openrouter":
            # OpenRouter'ın önerdiği (zorunlu olmayan) tanımlama başlıkları
            extra_headers = {"HTTP-Referer": "https://youtube-asistani.local", "X-Title": "YouTube Assistant"}
        _client_cache[cache_key] = OpenAI(
            api_key=key, base_url=provider["base_url"],
            default_headers=extra_headers or None,
        )
    return _client_cache[cache_key]


def _groq_client() -> OpenAI:
    """Sadece Groq'a özel işlemler (Whisper ses tanıma) için kullanılır; OpenRouter'da ses desteği yok.

    ÖNEMLİ: TEXT_PROVIDERS[0] OmniRoute'tur (metin üretimi sıralaması Omni->Groq->
    OpenRouter şeklinde), Groq DEĞİL. Whisper SADECE gerçek Groq API'sinde var;
    OmniRoute'un audio/transcriptions için Groq kimlik bilgisi yapılandırılı
    olmadığından "No credentials for provider: groq" hatası dönüyordu -- bu yüzden
    burada TEXT_PROVIDERS[0] yerine Groq'un base_url/api_key'i AÇIKÇA kullanılıyor.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY bulunamadı. Proje kökündeki .env dosyasını kontrol edin.")
    return _client_for({"name": "groq", "api_key": GROQ_API_KEY, "base_url": GROQ_BASE_URL})


def extract_video_id(youtube_url: str) -> Optional[str]:
    if not youtube_url or not isinstance(youtube_url, str):
        return None
    url = youtube_url.strip()
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc and "/watch" in parsed.path:
        qs = parse_qs(parsed.query)
        vid = qs.get("v", [None])[0]
        if vid:
            return vid
    if "youtu.be" in parsed.netloc:
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            return parts[0]
    if re.match(r"^[\w-]{11}$", url):
        return url
    return None


def check_ytdlp_available() -> bool:
    try:
        result = subprocess.run(YTDLP_CMD + ["--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
        return result.returncode == 0
    except Exception:
        return False


def check_ffmpeg_available() -> bool:
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
        return result.returncode == 0
    except Exception:
        return False


# ==================== TRANSCRIPT TEMİZLEME ====================
def clean_subtitle_content(content: str) -> str:
    """
    VTT/SRT içeriğinden başlık/zaman damgası/inline etiketleri temizler.
    Örn: "</c><00:00:06.106><c>I </c><00:00:06.319>" gibi kalıntılar kalmaz.
    """
    lines = []
    for raw_line in content.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if "-->" in line:  # zaman aralığı satırı
            continue
        if line.isdigit():  # cue numarası
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "STYLE", "::cue")):
            continue

        # Inline etiketleri temizle: <c>, </c>, <00:00:06.106> vb.
        line = re.sub(r"<[^>]*>", "", line).strip()
        if not line:
            continue
        lines.append(line)

    # Otomatik altyazılarda sık görülen ardışık tekrarları at
    deduped = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)

    return " ".join(deduped).strip()


# [Music], [Applause], (laughter), (kahkaha) gibi SES/OLAY betimlemeleri ve
# ">>" / "»" konuşmacı değişimi işaretleri. Köşeli parantez [...] içeriği
# altyazılarda neredeyse her zaman sözel olmayan bir betimlemedir (müzik,
# alkış, konuşmacı adı vb.), bu yüzden güvenle tamamen kaldırılır. Normal
# parantez (...) ise bilinen ses efekti kelimeleriyle eşleşirse kaldırılır
# (gerçek konuşma içeriğini yanlışlıkla silmemek için serbest parantez
# metni DOKUNULMADAN bırakılır).
_NONVERBAL_PATTERN = re.compile(
    r"\[[^\]]*\]"
    r"|\((?:laugh(?:s|ing|ter)?|applause|clapping|music|cheering|coughs?|sighs?|"
    r"crowd (?:noise|cheering)|background noise|inaudible|silence|"
    r"gülüşme(?:ler)?|kahkaha(?:lar)?|alkış(?:lar)?|müzik|gülüyor|gülerek|"
    r"öksür[üu]k|iç çekme|anlaşılmıyor|sessizlik)\)",
    re.IGNORECASE,
)
_SPEAKER_MARKER_PATTERN = re.compile(r"\s*(?:>>+|»+)\s*")


def strip_nonverbal_and_markers(text: str) -> str:
    """Transkriptten (kahkaha)/[Müzik] gibi notları ve >> konuşmacı işaretlerini kaldırır."""
    if not text:
        return text
    text = _NONVERBAL_PATTERN.sub(" ", text)
    text = _SPEAKER_MARKER_PATTERN.sub(" ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text



# ==================== TRANSCRIPT YÖNTEMLERİ ====================
def get_transcript_youtube_api(video_id: str) -> Optional[str]:
    """
    Videonun kendi dilinde (hangi dilse) altyazıyı bulup getirir.
    NOT: requirements.txt >=1.0.0 pinlendiği için sadece instance tabanlı
    (.list()) API kullanılır -- eski statik list_transcripts() metodu bu
    sürümlerde tamamen kaldırıldığı için HER ZAMAN AttributeError ile
    çöküyordu (asla başarılı olmadan sadece zaman kaybettiriyordu), o
    yüzden kaldırıldı. Tek deneme, hızlı başarısız/başarılı ol.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        def _extract_text(fetched) -> str:
            items = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
            parts = []
            for i in items:
                t = i.get("text") if isinstance(i, dict) else getattr(i, "text", "")
                if t:
                    parts.append(t.replace("\n", " ").strip())
            return " ".join(parts).strip()

        api = YouTubeTranscriptApi()
        all_transcripts = list(api.list(video_id))

        # Video'nun GERCEK konusulan dilini bilmiyoruz (bunu ogrenmek ayri bir
        # API cagrisi gerektirir), ama uygulamamiz zaten tr/en odakli (Yontem 1
        # de --sub-langs ile SADECE bu ikisini istiyor). Eskiden "ilk MANUEL
        # altyazi, yoksa listedeki ILK NE VARSA" mantigi vardi -- bu, listede
        # tr/en varken bile TAMAMEN ALAKASIZ bir dilin (orn. Ispanyolca) secilip
        # donmesine yol acabiliyordu (gercek olayda gozlemlendi: Turkce
        # konusulan bir video icin Ispanyolca altyazi geldi). Simdi once
        # MANUEL tr/en, sonra herhangi bir MANUEL, sonra OTOMATIK tr/en, en son
        # care olarak herhangi biri deneniyor -- boylece dil rastgele degil,
        # ONCELIKLI olarak seciliyor.
        LANG_PRIORITY = ("tr", "en")

        def _pick_by_lang(pool):
            for lang in LANG_PRIORITY:
                for t in pool:
                    if t.language_code == lang:
                        return t
            return pool[0] if pool else None

        manual = [t for t in all_transcripts if not t.is_generated]
        generated = [t for t in all_transcripts if t.is_generated]
        chosen = _pick_by_lang(manual) or _pick_by_lang(generated)

        if chosen is not None:
            text = _extract_text(chosen.fetch())
            if text:
                return text
        return None
    except Exception as e:
        print(f"  [Yöntem 2] başarısız: {e}")
        return None


def _get_transcript_items_with_timestamps(video_id: str) -> list:
    """
    (start, text) çiftlerinin listesini döndürür; hem eski hem yeni
    youtube-transcript-api sürümüyle uyumludur. Bölümlendirme (chapters)
    özelliği için kullanılır.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:
        return []

    def _pick(transcript_list):
        chosen = None
        for t in transcript_list:
            if not t.is_generated:
                chosen = t
                break
        if chosen is None:
            for t in transcript_list:
                chosen = t
                break
        return chosen

    def _normalize(fetched):
        raw = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else fetched
        out = []
        for i in raw:
            if isinstance(i, dict):
                out.append((i.get("start", 0), i.get("text", "")))
            else:
                out.append((getattr(i, "start", 0), getattr(i, "text", "")))
        return out

    # Yeni API (v1.0+)
    try:
        api = YouTubeTranscriptApi()
        chosen = _pick(api.list(video_id))
        if chosen is not None:
            items = _normalize(chosen.fetch())
            if items:
                return items
    except Exception:
        pass

    # Eski API (statik metodlar)
    try:
        chosen = _pick(YouTubeTranscriptApi.list_transcripts(video_id))
        if chosen is not None:
            items = _normalize(chosen.fetch())
            if items:
                return items
    except Exception:
        pass

    return []


def get_transcript_ytdlp_subtitles(video_url: str, video_id: str) -> Optional[str]:
    """
    Mevcut altyazıyı indirip temizler.

    HIZ İÇİN: önce ayrı bir "--list-subs" isteğiyle dilleri listeleyip SONRA
    indirmek yerine (bu iki ayrı yt-dlp süreci = iki ayrı metadata çekme +
    olası ekstra timeout demekti), en yaygın ~20 dili TEK bir "--sub-langs"
    çağrısında doğrudan istiyoruz. yt-dlp mevcut olmayan dilleri sessizce
    atlar, mevcut olanı indirir -- tek round-trip'e iniyor. "--no-playlist"
    ekliyoruz; URL'de radio/mix/liste parametresi (&list=... gibi) varsa
    yt-dlp'nin tüm listeyi işlemeye çalışıp takılmasını önler.
    """
    if not check_ytdlp_available():
        return None
    tmp_dir = tempfile.mkdtemp(prefix="ytai_subs_")
    try:
        # ONEMLI: 20 dil istemek YouTube'un "tek videoda cok fazla altyazi
        # istegi" rate-limitini (429) tetikliyor (bkz. yt-dlp issue #2706, #11059) --
        # her istenen dil, otomatik-ceviri altyazisi olan bir video icin AYRI bir
        # timedtext istegine donusuyor, 20 dil = 20 art arda istek = 429 riski.
        # AI zaten transkripti hedef dile CEVIRIYOR, o yuzden kaynak dilin ne
        # oldugu onemli degil -- sadece 2 dil (en genis kapsamli ikisi) yeterli.
        # Kucuk rastgele gecikme (0.2-0.8sn): istegin hep sifir-gecikmeyle,
        # mekanik bir hizda gelmesini onler -- gercek trafikte tam bu duzeydeki
        # duzenlilik bot tespitini kolaylastirir. Hizi gozle gorulur sekilde
        # etkilemez, ayni videoyu tekrar isteme riskini (429 tetikleyici) azaltir.
        time.sleep(random.uniform(0.2, 0.8))
        output_template = os.path.join(tmp_dir, "%(id)s.%(ext)s")

        subprocess.run(
            YTDLP_CMD + ytdlp_bypass.build_subtitle_args(output_template, video_url),
            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        all_files = list(Path(tmp_dir).glob(f"{video_id}*.vtt")) + list(Path(tmp_dir).glob(f"{video_id}*.srt"))
        if not all_files:
            return None

        manual = [f for f in all_files if "-orig" not in f.name]
        pool = manual if manual else all_files
        # Yalnizca en/tr istendigi icin (bkz. yukaridaki --sub-langs), ikisi de
        # indiyse HANGISININ secilecegi eskiden glob/dosya-sistemi sirasina
        # bagliydi -- bu da Turkce konusulan bir videoda Ingilizce (ya da tam
        # tersi) gelme riski yaratiyordu. Simdi acikca 'tr' dosyasi varsa o
        # tercih ediliyor.
        tr_match = [f for f in pool if ".tr." in f.name or f.name.endswith(".tr.vtt") or f.name.endswith(".tr.srt")]
        chosen = tr_match[0] if tr_match else pool[0]

        with open(chosen, "r", encoding="utf-8") as f:
            content = f.read()

        text = clean_subtitle_content(content)
        return text or None
    except Exception as e:
        stderr_detail = getattr(e, "stderr", None)
        if stderr_detail:
            print(f"  [Yöntem 1] başarısız: {e}\n    yt-dlp stderr: {stderr_detail.strip()[-500:]}")
        else:
            print(f"  [Yöntem 1] başarısız: {e}")
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


LANG_NAME_TO_CODE = {
    "afrikaans": "af", "albanian": "sq", "amharic": "am", "arabic": "ar",
    "armenian": "hy", "assamese": "as", "azerbaijani": "az", "bashkir": "ba",
    "basque": "eu", "belarusian": "be", "bengali": "bn", "bosnian": "bs",
    "breton": "br", "bulgarian": "bg", "burmese": "my", "cantonese": "yue",
    "castilian": "es", "catalan": "ca", "chinese": "zh", "croatian": "hr",
    "czech": "cs", "danish": "da", "dutch": "nl", "english": "en",
    "estonian": "et", "faroese": "fo", "finnish": "fi", "flemish": "nl",
    "french": "fr", "galician": "gl", "georgian": "ka", "german": "de",
    "greek": "el", "gujarati": "gu", "haitian": "ht", "hausa": "ha",
    "hawaiian": "haw", "hebrew": "he", "hindi": "hi", "hungarian": "hu",
    "icelandic": "is", "indonesian": "id", "italian": "it", "japanese": "ja",
    "javanese": "jw", "kannada": "kn", "kazakh": "kk", "khmer": "km",
    "korean": "ko", "lao": "lo", "latin": "la", "latvian": "lv",
    "lingala": "ln", "lithuanian": "lt", "luxembourgish": "lb",
    "macedonian": "mk", "malagasy": "mg", "malay": "ms", "malayalam": "ml",
    "maltese": "mt", "maori": "mi", "marathi": "mr", "mongolian": "mn",
    "nepali": "ne", "norwegian": "no", "nynorsk": "nn", "occitan": "oc",
    "pashto": "ps", "persian": "fa", "polish": "pl", "portuguese": "pt",
    "punjabi": "pa", "romanian": "ro", "russian": "ru", "sanskrit": "sa",
    "serbian": "sr", "shona": "sn", "sindhi": "sd", "sinhala": "si",
    "slovak": "sk", "slovenian": "sl", "somali": "so", "spanish": "es",
    "sundanese": "su", "swahili": "sw", "swedish": "sv", "tagalog": "tl",
    "tajik": "tg", "tamil": "ta", "tatar": "tt", "telugu": "te",
    "thai": "th", "tibetan": "bo", "turkish": "tr", "turkmen": "tk",
    "ukrainian": "uk", "urdu": "ur", "uzbek": "uz", "vietnamese": "vi",
    "welsh": "cy", "yiddish": "yi", "yoruba": "yo",
}

# Kod -> İngilizce dil adı (LANG_NAME_TO_CODE'un tersi). Cevap dili talimatı
# oluştururken kullanılır (örn. "es" -> "spanish").
CODE_TO_LANG_NAME = {v: k for k, v in LANG_NAME_TO_CODE.items()}
CODE_TO_LANG_NAME["tr"] = "turkish"


def lang_instruction(lang_code: Optional[str]) -> str:
    """AI'ya hangi dilde cevap vermesi gerektiğini söyleyen talimat cümlesi üretir."""
    code = (lang_code or "tr").lower().strip()
    # Zayif/kucuk modeller (orn. ucretsiz yedek modeller) Ingilizce terimleri
    # kelime kelime cevirip dogal olmayan kaliplar uretebiliyor (gozlemlendi:
    # "character arc" -> "karakter arki" gibi). Butun saglayicilar icin ortak
    # bir guvenlik agi olarak dogal/deyimsel ceviri talebi ekleniyor.
    natural_translation_note = (
        " İngilizce terim/deyimleri birebir kelime kelime çevirme (örn. 'character "
        "arc' için uydurma 'karakter arkı' gibi); o dilde doğal ve yaygın kullanılan "
        "karşılığını kullan, gerekirse terimi olduğu gibi bırak."
    )
    if code == "tr":
        return "Türkçe yanıt ver." + natural_translation_note
    name = CODE_TO_LANG_NAME.get(code, code)
    return f"Respond in {name.capitalize()} language, not Turkish. (ISO code: {code})" + natural_translation_note


# "Bu bir şarkı" bilgilendirme notu için birkaç yaygın dilde çeviri.
# Listede olmayan diller için İngilizce'ye düşülür.
SONG_NOTE_TRANSLATIONS = {
    "tr": "🎵 Bu içerik bir şarkı/müzik parçası gibi görünüyor.",
    "en": "🎵 This content appears to be a song/music track.",
    "es": "🎵 Este contenido parece ser una canción/pista musical.",
    "de": "🎵 Dieser Inhalt scheint ein Lied/Musikstück zu sein.",
    "fr": "🎵 Ce contenu semble être une chanson/piste musicale.",
    "it": "🎵 Questo contenuto sembra essere una canzone/traccia musicale.",
    "pt": "🎵 Este conteúdo parece ser uma música/faixa musical.",
    "ru": "🎵 Похоже, это песня/музыкальный трек.",
    "ja": "🎵 この内容は曲・音楽トラックのようです。",
    "ko": "🎵 이 콘텐츠는 노래/음악 트랙으로 보입니다.",
    "ar": "🎵 يبدو أن هذا المحتوى أغنية/مقطوعة موسيقية.",
    "hi": "🎵 यह सामग्री एक गीत/संगीत ट्रैक प्रतीत होती है।",
    "zh": "🎵 这个内容看起来像是一首歌/音乐曲目。",
}


def get_song_note(lang_code: Optional[str]) -> str:
    code = (lang_code or "tr").lower().strip()
    return SONG_NOTE_TRANSLATIONS.get(code, SONG_NOTE_TRANSLATIONS["en"])


_SONG_LABEL_ONLY_RE = re.compile(r"^\[[A-Za-z][A-Za-z ]*\d*\]$")


def add_song_structure_labels(timestamped_lyrics: str) -> str:
    """
    Zaman damgali sarki sozu satirlarina (tekrar eden nakarat/koro = CHORUS,
    farkli kitalar = VERSE 1/VERSE 2, kopru = BRIDGE, nakarat oncesi =
    PRECHORUS gibi) yapisal etiketler ekler -- gercek lirik sitelerindeki gibi.
    SADECE etiket satirlari EKLENIR; mevcut [MM:SS] satirlari asla degistirilmez/
    silinmez/siralari bozulmaz (dogrulanir; uyusmazsa orijinal metin degismeden
    donuyor, yani en kotu ihtimalle etiketsiz ama HER ZAMAN doğru transkript
    gosterilir).
    """
    if not timestamped_lyrics or not timestamped_lyrics.strip():
        return timestamped_lyrics

    original_lines = [l for l in timestamped_lyrics.split("\n") if l.strip()]
    if len(original_lines) < 4:
        return timestamped_lyrics  # cok kisa, bolumlere ayirmaya deger yok

    try:
        raw = _chat_completion(
            "Sen bir şarkı sözü yapısı analiz asistanısın. Sadece istenen formatta yanıt ver.",
            f"""Aşağıda [MM:SS] zaman damgalı şarkı sözü satırları var. Görevin: tekrar eden
bölümleri (nakarat = CHORUS) ve farklı bölümleri (kıta = VERSE 1, VERSE 2, ... köprü =
BRIDGE, nakarat öncesi = PRECHORUS, giriş = INTRO, kapanış = OUTRO) tespit edip, HER
YENİ BÖLÜMDEN HEMEN ÖNCE kendi satırında SADECE köşeli parantezli etiketi ekle
(örn. [CHORUS], [VERSE 1], [BRIDGE]).

KURALLAR (ÇOK ÖNEMLİ, kesinlikle uy):
- Mevcut [MM:SS] ile başlayan satırların HİÇBİRİNİ değiştirme, silme veya sırasını değiştirme.
- SADECE aralarına etiket satırları ekle; başka hiçbir metin/açıklama ekleme.
- Etiketler İngilizce ve büyük harfle olsun: [INTRO], [VERSE 1], [VERSE 2], [PRECHORUS],
  [CHORUS], [BRIDGE], [OUTRO] gibi.
- Aynı nakarat metni tekrar geçiyorsa yine [CHORUS] etiketiyle işaretle.

Satırlar:
{timestamped_lyrics}""",
            max_tokens=min(4000, len(timestamped_lyrics) + 800),
            temperature=0.2,
            feature="chat",
        )
    except Exception:
        return timestamped_lyrics

    result_lines = [l for l in raw.split("\n") if l.strip()]
    result_original_only = [l for l in result_lines if not _SONG_LABEL_ONLY_RE.match(l.strip())]
    if result_original_only != original_lines:
        # AI bir satiri degistirdi/kaybetti/ekledi -- guvenli tarafta kal, etiketsiz dondur.
        return timestamped_lyrics
    return "\n".join(result_lines)


LIMIT_MESSAGE_TRANSLATIONS = {
    "tr": "⭐ Bu bölüm için ücretsiz sohbet limitine ulaştınız ({limit} mesaj). Sınırsız sohbet etmek için '⭐ Ekstra Özellikler' menüsünden 'Yapay Zeka ile Sınırsız Chat'i açabilirsiniz.",
    "en": "⭐ You've reached the free chat limit for this section ({limit} messages). Open 'AI Unlimited Chat' in the '⭐ Extra Features' menu to remove the limit.",
    "es": "⭐ Has alcanzado el límite de chat gratuito para esta sección ({limit} mensajes). Abre 'Chat Ilimitado con IA' en el menú '⭐ Funciones Extra' para quitar el límite.",
    "de": "⭐ Sie haben das kostenlose Chat-Limit für diesen Bereich erreicht ({limit} Nachrichten). Öffnen Sie 'KI Unbegrenzter Chat' im Menü '⭐ Zusatzfunktionen', um das Limit aufzuheben.",
    "fr": "⭐ Vous avez atteint la limite de chat gratuite pour cette section ({limit} messages). Ouvrez 'Chat IA illimité' dans le menu '⭐ Fonctionnalités supplémentaires' pour lever la limite.",
    "it": "⭐ Hai raggiunto il limite di chat gratuita per questa sezione ({limit} messaggi). Apri 'Chat IA illimitata' nel menu '⭐ Funzioni extra' per rimuovere il limite.",
    "pt": "⭐ Você atingiu o limite de chat gratuito para esta seção ({limit} mensagens). Abra 'Chat IA Ilimitado' no menu '⭐ Recursos Extras' para remover o limite.",
    "ru": "⭐ Вы достигли лимита бесплатных сообщений для этого раздела ({limit} сообщений). Откройте «Безлимитный чат с ИИ» в меню «⭐ Дополнительные функции», чтобы снять лимит.",
    "ja": "⭐ このセクションの無料チャット上限に達しました（{limit}件）。制限を解除するには「⭐ 追加機能」メニューの「AI無制限チャット」を開いてください。",
    "ko": "⭐ 이 섹션의 무료 채팅 한도에 도달했습니다 ({limit}개 메시지). 제한을 해제하려면 '⭐ 추가 기능' 메뉴에서 'AI 무제한 채팅'을 여세요.",
    "ar": "⭐ لقد وصلت إلى حد الدردشة المجانية لهذا القسم ({limit} رسائل). افتح 'دردشة ذكاء اصطناعي غير محدودة' من قائمة '⭐ ميزات إضافية' لإزالة الحد.",
    "hi": "⭐ आप इस सेक्शन के लिए मुफ़्त चैट सीमा तक पहुँच गए हैं ({limit} संदेश)। सीमा हटाने के लिए '⭐ अतिरिक्त सुविधाएँ' मेनू में 'AI असीमित चैट' खोलें।",
    "zh": "⭐ 您已达到此部分的免费聊天上限（{limit}条消息）。请在'⭐ 附加功能'菜单中打开'AI无限聊天'以取消限制。",
}


def get_limit_message(lang_code: Optional[str], limit: int) -> str:
    code = (lang_code or "tr").lower().strip()
    template = LIMIT_MESSAGE_TRANSLATIONS.get(code, LIMIT_MESSAGE_TRANSLATIONS["en"])
    return template.format(limit=limit)

# Bazı diller için, sık karışan/yanlış duyulan kelime ve ifadeleri doğru
# yazımıyla içeren "ipucu" cümleleri. Whisper'ın 'prompt' parametresine eklenir;
# model bu kelimelerin doğru yazımını görünce fonetik olarak benzer sesleri o
# kelimelere yormaya daha yatkın olur.
#
# YENİ SORUNLU KELİME/İFADE EKLEMEK İÇİN: aşağıdaki "terms" listesine sadece
# doğru yazılmış haliyle ekleyin (örn. "Reis ya" yanlış "Değil ya" algılanıyorsa
# listeye "Reis ya" eklenir), server.py'de başka bir yer değiştirmeye gerek yok.
VOCAB_HINTS = {
    "tr": {
        "base": "Bu videoda günlük konuşma dili, argo ve kısaltmalar kullanılıyor. "
                "Aşağıdaki ifadeler sık geçiyor, bunları doğru şekilde yaz:",
        "terms": [
            "Selam", "SLM", "iğrendim", "enayi", "Reis ya", "as eyw",
            "aynen", "yani", "abi", "kanka", "tamam", "helal", "vay be",
            "yok artık", "off ya", "valla", "hakikaten", "kesinlikle",
            "pot basıyorum", "pot kırdım",
        ],
    },
    "en": {
        "base": "This is casual spoken English with slang and abbreviations. "
                "The following words/phrases appear often, spell them correctly:",
        "terms": [
            "disgusting", "gullible", "naive", "gonna", "wanna", "yeah",
            "cool", "alright", "dude", "for real", "no way",
        ],
    },
}


TITLE_CACHE: dict[str, str] = {}
METADATA_CACHE: dict[str, dict] = {}  # video_id -> {"title": str, "is_music": bool}


def get_video_metadata(video_url: str) -> dict:
    """
    Video başlığı, kanal adı, açıklama (kısaltılmış), etiketler ve "bu bir
    şarkı mı" bilgisini TEK seferde (tek yt-dlp çağrısıyla) çeker, cache'ler.
    Bu bilgiler zaten çekilen JSON içinde geldiği için EKSTRA ağ isteği
    gerektirmez -> öneri/analiz gibi işlemlerde ekstra gecikme yaratmadan
    "kanal adı/açıklama neyse video da o bağlamdadır" tespitini sağlar
    (örn. bir tribute/AMV kanalının açıklaması gerçek temayı netleştirir).

    is_music tespiti yt-dlp'nin 'categories' (örn. "Music") ve 'genre'
    alanlarına bakarak yapılır; kesin değildir ama YouTube'un kendi
    sınıflandırmasına dayanır.
    """
    vid = extract_video_id(video_url)
    if vid and vid in METADATA_CACHE:
        return METADATA_CACHE[vid]

    meta = {"title": "", "is_music": False, "channel": "", "description": "", "tags": []}
    if not check_ytdlp_available():
        return meta
    try:
        result = subprocess.run(
            YTDLP_CMD + ytdlp_bypass.build_metadata_args(video_url),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return meta
        data = json.loads(result.stdout.strip().split("\n")[0])
        title = (data.get("title") or "").strip()
        categories = data.get("categories") or []
        genre = (data.get("genre") or "") or (data.get("album") or "")
        is_music = ("Music" in categories) or bool(genre) or bool(data.get("track")) or bool(data.get("artist"))
        channel = (data.get("uploader") or data.get("channel") or "").strip()
        description = (data.get("description") or "").strip()[:600]  # kısa tutulur, hız + prompt boyutu için
        tags = (data.get("tags") or [])[:15]

        meta = {
            "title": title, "is_music": is_music,
            "channel": channel, "description": description, "tags": tags,
        }
        if vid:
            METADATA_CACHE[vid] = meta
            if title:
                TITLE_CACHE[vid] = title
        return meta
    except Exception:
        return meta


def get_video_title(video_url: str) -> str:
    """Video başlığını hızlıca çeker (indirme yapmaz), video_id bazında cache'lenir."""
    vid = extract_video_id(video_url)
    if vid and vid in TITLE_CACHE:
        return TITLE_CACHE[vid]

    if not check_ytdlp_available():
        return ""
    try:
        result = subprocess.run(
            YTDLP_CMD + ytdlp_bypass.build_metadata_args(video_url),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return ""
        data = json.loads(result.stdout.strip().split("\n")[0])
        title = (data.get("title") or "").strip()
        if vid and title:
            TITLE_CACHE[vid] = title
        return title
    except Exception:
        return ""


def build_whisper_prompt(video_title: str, language_code: str) -> Optional[str]:
    """Video başlığı + (varsa) o dile özel kelime dağarcığı ipucunu birleştirir."""
    parts = []
    if video_title:
        parts.append(video_title)
    if language_code:
        hint = VOCAB_HINTS.get(language_code.lower())
        if hint:
            terms_str = ", ".join(f'"{t}"' for t in hint["terms"])
            parts.append(f"{hint['base']} {terms_str}.")
    combined = " ".join(parts).strip()
    return combined or None


# Whisper bazı nadir ifadeleri sistematik olarak yanlış duyabiliyor (örn. "as eyw" ->
# "as eiv"). Bu sözlük SADECE günlük konuşmada nadir geçen, çakışma riski düşük
# ifadeler için güvenlidir — otomatik olarak doğru haline çevrilir.
#
# UYARI: "değil ya" gibi ÇOK YAYGIN ifadeleri buraya EKLEMEYİN. Öyle bir kural,
# gerçekten "değil ya" denen başka cümleleri de yanlışlıkla değiştirir. Bu yüzden
# "Reis ya" <-> "Değil ya" karışıklığı burada DÜZELTİLMİYOR; onun için yukarıdaki
# VOCAB_HINTS ipucuna güveniliyor (daha yumuşak, kesin olmayan bir çözüm).
#
# YENİ GÜVENLİ DÜZELTME EKLEMEK İÇİN: (regex_deseni, doğru_hali) şeklinde ekleyin.
TRANSCRIPT_CORRECTIONS = {
    "tr": [
        (r"\bas\s+eiv\b", "as eyw"),
        (r"\brendim\b", "iğrendim"),
        (r"\bpot[ıi]yorum\b", "pot basıyorum"),
        (r"\bpot[ıi]rd[ıi]m\b", "pot kırdım"),
    ],
    "en": [],
}


def apply_known_corrections(text: str, language_code: Optional[str]) -> str:
    if not text or not language_code:
        return text
    rules = TRANSCRIPT_CORRECTIONS.get(language_code.lower(), [])
    for pattern, replacement in rules:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


ASSEMBLYAI_BASE = "https://api.assemblyai.com/v2"


def _assemblyai_format_chapters(chapters: list) -> str:
    """AssemblyAI'nin auto_chapters cikisini bizim '[MM:SS] Baslik - aciklama'
    formatimiza cevirir. 'start' milisaniye cinsinden gelir."""
    lines = []
    for ch in chapters:
        start_ms = ch.get("start", 0)
        secs = int(start_ms / 1000)
        mins, secs = divmod(secs, 60)
        headline = ch.get("headline") or ch.get("gist") or ""
        summary = ch.get("summary") or ""
        lines.append(f"[{mins:02d}:{secs:02d}] {headline} - {summary}")
    return "\n".join(lines)


def _assemblyai_poll_and_cache(transcript_id: str, video_id: str, api_key: str, timeout: int = 90) -> None:
    """Arka planda (ayri thread'de) AssemblyAI isini bitene kadar yoklar; bitince
    GERCEK zaman damgali bolumleri ASSEMBLYAI_CHAPTERS_CACHE'e yazar. Ana istek
    akisini HIC bloklamaz -- is zamaninda bitmezse sessizce hicbir sey olmaz,
    normal AI-tahminli bolumler zaten paralel yolda uretiliyor olur."""
    try:
        t0 = time.time()
        while time.time() - t0 < timeout:
            resp = requests.get(
                f"{ASSEMBLYAI_BASE}/transcript/{transcript_id}",
                headers={"authorization": api_key}, timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status")
            if status == "completed":
                chapters = data.get("chapters") or []
                if chapters:
                    formatted = _assemblyai_format_chapters(chapters)
                    ASSEMBLYAI_CHAPTERS_CACHE[video_id] = formatted
                    # AI'nin tahmin ettigi bolumler bu is baslamadan ONCE zaten
                    # cache'e/FEATURE_CACHE'e yazilmis olabilir (bkz. tasarim notu:
                    # bu is ana akisi bloklamiyor). Is simdi bitince, hangi dil(ler)
                    # icin zaten bir bolum cache'lenmisse GERCEK zaman damgali
                    # versiyonla geriye donuk olarak degistiriyoruz -- kullanici
                    # sekmeyi tekrar actiginda/yeniledinde artik gercek olani gorur.
                    for cache_key in list(FEATURE_CACHE.keys()):
                        if len(cache_key) == 3 and cache_key[0] == video_id and cache_key[2] == "chapters":
                            FEATURE_CACHE[cache_key] = ensure_chapter_linebreaks(formatted)
                    print(f"  ✅ AssemblyAI gerçek zaman damgalı bölümler hazır ({video_id})")
                return
            if status == "error":
                print(f"  ⚠️ AssemblyAI bölümlendirme hatası: {data.get('error')}")
                return
            time.sleep(2)
        print(f"  ⚠️ AssemblyAI bölümlendirme zaman aşımına uğradı ({video_id})")
    except Exception as e:
        print(f"  ⚠️ AssemblyAI bölümlendirme başarısız: {e}")


def start_assemblyai_chapters_job(audio_path: str, video_id: str) -> None:
    """
    Ses dosyasini AssemblyAI'ye YUKLER ve auto_chapters isini BASLATIR (senkron,
    hizli -- sadece upload+istek), sonra GERCEK sonucu beklemeden (poll) arka
    plan thread'ine devrediyor. Boylece ana transkript/ozet akisi hic
    yavaslamiyor; is zamaninda biterse bolumler gercek zaman damgasiyla gelir,
    bitmezse mevcut AI-tahminli yontem zaten calismaya devam eder.

    OmniRoute UZERINDEN DEGIL -- AssemblyAI'nin kendi API'sine dogrudan (bkz.
    ASSEMBLYAI_API_KEY_CHAPTERS tanimindaki not, OmniRoute'un bu saglayici icin
    proxy destegi bozuk).
    """
    if not ASSEMBLYAI_API_KEY_CHAPTERS or video_id in ASSEMBLYAI_CHAPTERS_CACHE or video_id in _ASSEMBLYAI_JOBS_STARTED:
        return
    _ASSEMBLYAI_JOBS_STARTED.add(video_id)
    try:
        with open(audio_path, "rb") as f:
            upload_resp = requests.post(
                f"{ASSEMBLYAI_BASE}/upload",
                headers={"authorization": ASSEMBLYAI_API_KEY_CHAPTERS},
                data=f, timeout=60,
            )
        upload_resp.raise_for_status()
        audio_url = upload_resp.json()["upload_url"]

        tr_resp = requests.post(
            f"{ASSEMBLYAI_BASE}/transcript",
            headers={"authorization": ASSEMBLYAI_API_KEY_CHAPTERS, "content-type": "application/json"},
            json={"audio_url": audio_url, "auto_chapters": True},
            timeout=30,
        )
        tr_resp.raise_for_status()
        transcript_id = tr_resp.json()["id"]

        threading.Thread(
            target=_assemblyai_poll_and_cache,
            args=(transcript_id, video_id, ASSEMBLYAI_API_KEY_CHAPTERS),
            daemon=True,
        ).start()
    except Exception as e:
        print(f"  ⚠️ AssemblyAI bölümlendirme işi başlatılamadı: {e}")


def get_transcript_omniroute_deepgram(video_url: str) -> Optional[str]:
    """
    yt-dlp (Yöntem 1/2) altyazı bulamadığında, Groq Whisper'a (Yöntem 4, en
    yavaş -- tam ses indirme + transkripsiyon) düşmeden ÖNCE OmniRoute
    üzerinden Deepgram'ı dener (genelde daha hızlı). OmniRoute'un
    "transkriptor" anahtarı ÜZERİNDEN (feature'a özel key_override ile)
    "deepgram/nova-2" modeli kullanılır -- doğrulandı, çalışıyor. OmniRoute
    çalışmıyorsa veya Deepgram kimlik bilgisi geçersizse (bkz. AssemblyAI'nin
    şu an OmniRoute tarafında geçersiz olması) sessizce None döner, zincir
    Whisper'a devam eder.
    """
    if not check_ytdlp_available() or not OMNIROUTE_API_KEY:
        return None
    tmp_dir = tempfile.mkdtemp(prefix="ytai_dg_audio_")
    try:
        audio_template = os.path.join(tmp_dir, "audio.%(ext)s")
        print("  [Yöntem 3] Ses indiriliyor (Deepgram için)...")
        subprocess.run(
            YTDLP_CMD + ytdlp_bypass.build_download_args() + [
                "--format", "(bestaudio[acodec^=opus]/bestaudio)/best",
                "--extract-audio", "--audio-format", "mp3",
                "--audio-quality", "0",
                "--output", audio_template, video_url,
            ],
            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
        )
        audio_files = list(Path(tmp_dir).glob("audio.*"))
        if not audio_files:
            return None
        audio_path = str(audio_files[0])

        # Ses zaten indi -- ayni dosyayi kullanarak AssemblyAI'nin GERCEK zaman
        # damgali bolumlendirme isini de arka planda baslat (fire-and-forget,
        # ana akisi HIC bloklamaz, bkz. start_assemblyai_chapters_job).
        start_assemblyai_chapters_job(audio_path, extract_video_id(video_url))

        key_override = OMNIROUTE_FEATURE_KEYS.get("analyze")  # "transkriptor" anahtarı
        client = _client_for({"name": "omniroute", "api_key": key_override or OMNIROUTE_API_KEY, "base_url": OMNIROUTE_BASE_URL})
        print("  [Yöntem 3] OmniRoute (Deepgram) ile transkript çıkarılıyor...")
        with open(audio_path, "rb") as f:
            tr = client.audio.transcriptions.create(model="deepgram/nova-2", file=f)
        text = (getattr(tr, "text", None) or "").strip()
        return text or None
    except Exception as e:
        stderr_detail = getattr(e, "stderr", None)
        if stderr_detail:
            print(f"  [Yöntem 3] Deepgram başarısız: {e}\n    yt-dlp stderr: {stderr_detail.strip()[-500:]}")
        else:
            print(f"  [Yöntem 3] Deepgram başarısız: {e}")
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def get_transcript_ytdlp_whisper(video_url: str) -> Optional[str]:
    """
    Şive/aksan kaynaklı hatalı tanımayı azaltmak için (hem kısa hem uzun videolarda):
    - Dil SADECE BİR KEZ, kısa bir örnekten algılanır, sonra TÜM transkripsiyon
      çağrılarına açıkça verilir. (Aksi halde model her seferinde dili yeniden
      tahmin eder; kısa/aksanlı kesitlerde yanlış tahmin kaliteyi düşürür.)
    - Video başlığı + o dile özel "doğru yazım" ipucu cümlesi (VOCAB_HINTS)
      Whisper'ın 'prompt' parametresine veriliyor; bu, "iğrendim/enayi/SLM" gibi
      fonetik olarak karışan kelimelerin doğru yazılma ihtimalini artırır.
    - Uzun videolarda ses parçaları 5 saniye ÖRTÜŞMELİ kesilir, kelime kaybı önlenir.
    - Dil eşleme tablosu (LANG_NAME_TO_CODE) Whisper'ın desteklediği ~90+ dili kapsar.
    """
    if not check_ytdlp_available() or not GROQ_API_KEY:
        return None
    tmp_dir = tempfile.mkdtemp(prefix="ytai_audio_")
    try:
        audio_template = os.path.join(tmp_dir, "audio.%(ext)s")
        print("  [Yöntem 4] Ses indiriliyor (en iyi ses kalitesiyle)...")
        subprocess.run(
            YTDLP_CMD + ytdlp_bypass.build_download_args() + [
                "--format", "(bestaudio[acodec^=opus]/bestaudio)/best",
                "--extract-audio", "--audio-format", "mp3",
                "--audio-quality", "0",  # en yüksek kalite -> şive/aksan ayrımı için önemli
                "--output", audio_template, video_url,
            ],
            check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
        )
        audio_files = list(Path(tmp_dir).glob("audio.*"))
        if not audio_files:
            return None

        audio_path = str(audio_files[0])

        # Ses zaten indi -- ayni dosyayi kullanarak AssemblyAI'nin GERCEK zaman
        # damgali bolumlendirme isini de arka planda baslat (fire-and-forget,
        # ana akisi HIC bloklamaz, bkz. start_assemblyai_chapters_job).
        start_assemblyai_chapters_job(audio_path, extract_video_id(video_url))

        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        client = _groq_client()
        video_title = get_video_title(video_url)
        ffmpeg_ok = check_ffmpeg_available()

        def transcribe_one(path: str, language: str = None, prompt: str = None, use_verbose: bool = False):
            def _do_call():
                with open(path, "rb") as f:
                    kwargs = {"model": GROQ_WHISPER_MODEL, "file": f, "temperature": 0}
                    if prompt:
                        kwargs["prompt"] = prompt
                    if language:
                        kwargs["language"] = language
                    if use_verbose:
                        kwargs["response_format"] = "verbose_json"
                    return client.audio.transcriptions.create(**kwargs)

            tr = _call_with_retry(_do_call, max_retries=2, base_delay=2.0, max_wait=6.0)
            text = (getattr(tr, "text", None) or "").strip()
            detected_lang = getattr(tr, "language", None) if use_verbose else None
            return text, detected_lang

        # ---- ADIM 1: Dili SADECE BİR KEZ, kısa bir örnekten tespit et ----
        detected_lang = None
        sample_path = audio_path
        if ffmpeg_ok:
            candidate_sample = os.path.join(tmp_dir, "lang_sample.mp3")
            try:
                subprocess.run(
                    ["ffmpeg", "-i", audio_path, "-t", "45", "-c", "copy", "-loglevel", "error", candidate_sample],
                    check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
                )
                sample_path = candidate_sample
            except Exception:
                sample_path = audio_path
        try:
            _, detected_lang = transcribe_one(sample_path, prompt=video_title or None, use_verbose=True)
            if detected_lang:
                detected_lang = LANG_NAME_TO_CODE.get(detected_lang.lower().strip(), detected_lang)
                print(f"  🌐 Algılanan dil (tüm ses için sabitlendi): {detected_lang}")
        except Exception as e:
            print(f"  ⚠️ Dil algılama başarısız, dil zorlanmadan devam edilecek: {e}")

        final_prompt = build_whisper_prompt(video_title, detected_lang)

        # ---- ADIM 2: Dosya limit içindeyse tek seferde, dil+ipucu ile transkribe et ----
        if size_mb <= 24 or not ffmpeg_ok:
            if size_mb > 24:
                print(f"  ⚠️ Ses dosyası {size_mb:.1f}MB, ffmpeg yok, parçalanamıyor; tek seferde deneniyor (kesilebilir).")
            print("  [Yöntem 4] Groq Whisper ile transkript çıkarılıyor (videonun tamamı)...")
            text, _ = transcribe_one(audio_path, language=detected_lang, prompt=final_prompt)
            text = apply_known_corrections(text, detected_lang)
            return text or None

        # ---- ADIM 3: Büyük dosya -> videonun TAMAMINI kapsamak için örtüşmeli parçala ----
        print(f"  ℹ️ Ses dosyası {size_mb:.1f}MB, videonun tamamını işlemek için parçalara bölünüyor...")

        total_duration = None
        try:
            duration_probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
            )
            total_duration = float(duration_probe.stdout.strip())
        except Exception as e:
            print(f"  ⚠️ ffprobe ile süre alınamadı (örtüşmesiz parçalamaya geçiliyor): {e}")
            total_duration = None

        chunk_len, overlap = 600, 5
        chunk_paths = []
        if total_duration:
            start = 0.0
            idx = 0
            while start < total_duration:
                idx += 1
                out_path = os.path.join(tmp_dir, f"chunk_{idx:03d}.mp3")
                subprocess.run(
                    ["ffmpeg", "-ss", str(max(0, start - (overlap if idx > 1 else 0))),
                     "-i", audio_path, "-t", str(chunk_len + overlap),
                     "-c", "copy", "-loglevel", "error", out_path],
                    check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                )
                chunk_paths.append(out_path)
                start += chunk_len
        else:
            # Süre alınamazsa eski (örtüşmesiz) yönteme geri dön
            chunk_pattern = os.path.join(tmp_dir, "chunk_%03d.mp3")
            subprocess.run(
                ["ffmpeg", "-i", audio_path, "-f", "segment", "-segment_time", str(chunk_len),
                 "-c", "copy", "-loglevel", "error", chunk_pattern],
                check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
            )
            chunk_paths = [str(p) for p in sorted(Path(tmp_dir).glob("chunk_*.mp3"))]

        if not chunk_paths:
            print("  ⚠️ Parçalama başarısız, tam dosya ile deneniyor...")
            text, _ = transcribe_one(audio_path, language=detected_lang, prompt=final_prompt)
            text = apply_known_corrections(text, detected_lang)
            return text or None

        # Parçalar birbirinden bağımsız olduğu için PARALEL transkribe edilir
        # (sıralı yapmak, video uzunluğuyla doğru orantılı bekleme demekti;
        # paralel işlem toplam süreyi büyük ölçüde kısaltır). Sonuçlar, doğru
        # sırayla birleştirmek için parça indeksine göre saklanır.
        print(f"  ℹ️ {len(chunk_paths)} ses parçası paralel olarak transkribe ediliyor (dil: {detected_lang or 'otomatik'})...")
        results = [None] * len(chunk_paths)

        def _transcribe_chunk(idx_path):
            idx, chunk_path = idx_path
            try:
                part_text, _ = transcribe_one(chunk_path, language=detected_lang, prompt=final_prompt)
                part_text = apply_known_corrections(part_text, detected_lang)
                print(f"    -> Ses parçası {idx + 1}/{len(chunk_paths)} tamamlandı")
                return idx, part_text
            except Exception as chunk_err:
                print(f"    ⚠️ Parça {idx + 1} başarısız: {chunk_err}")
                return idx, None

        max_workers = min(3, len(chunk_paths))  # turbo modelle 3'e çıkarıldı, hâlâ rate-limit güvenli
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for idx, part_text in executor.map(_transcribe_chunk, enumerate(chunk_paths)):
                results[idx] = part_text

        parts = [p for p in results if p]
        full_text = " ".join(parts).strip()
        return full_text or None
    except Exception as e:
        stderr_detail = getattr(e, "stderr", None)
        if stderr_detail:
            print(f"  [Yöntem 4] başarısız: {e}\n    yt-dlp stderr: {stderr_detail.strip()[-500:]}")
        else:
            print(f"  [Yöntem 4] başarısız: {e}")
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def clean_transcript_text(text: str) -> str:
    """
    Transkriptin SADECE söylenen sözleri içermesini sağlar; sahne/ses notlarını
    ve konuşmacı değişim işaretlerini temizler:
    - (kahkaha), (gülüşmeler), (laughs), [Music], [Applause] gibi notlar silinir
    - ">>" gibi konuşmacı değişim işaretleri silinir
    - Fazla boşluklar toparlanır
    Bu, hangi yöntemle alınmış olursa olsun (YouTube API / yt-dlp altyazı /
    Whisper) TÜM transkriptlere tek noktadan uygulanır.
    """
    if not text:
        return text
    text = re.sub(r"\[[^\]\n]{0,60}\]", " ", text)   # [Music], [Applause], [gülüşmeler] vb.
    text = re.sub(r"\([^)\n]{0,60}\)", " ", text)     # (kahkaha), (laughs), (gülüşmeler) vb.
    text = re.sub(r">{2,}", " ", text)                # >> konuşmacı değişim işareti
    text = re.sub(r"\s+", " ", text).strip()
    return text


PREPARE_STATUS: dict[str, str] = {}  # video_id -> o an çalışan adımın kısa açıklaması (frontend polling için)


def get_transcript_smart(video_url: str, video_id: str, lang: str = None) -> Optional[str]:
    # NOT: 'lang' parametresi artık kullanılmıyor (geriye dönük uyumluluk için duruyor).
    # Transkript videonun kendi konuşulan dilinde, otomatik algılanarak alınır.
    if video_id in TRANSCRIPT_CACHE:
        PREPARE_STATUS[video_id] = "done"
        return TRANSCRIPT_CACHE[video_id]

    with _get_transcript_fetch_lock(video_id):
        # Kilit beklenirken başka bir istek işi zaten bitirmiş olabilir.
        if video_id in TRANSCRIPT_CACHE:
            PREPARE_STATUS[video_id] = "done"
            return TRANSCRIPT_CACHE[video_id]

        print(f"\n📹 Transcript alınıyor: {video_id}")
        # 4 yöntem sırayla, önceliğimiz her zaman yt-dlp altyazı indirme (1), o
        # çalışmazsa youtube-transcript-api'ye (2), sonra OmniRoute'taki hazır
        # ajanlara (3), en son Whisper'a (4) düşülür: (1) yt-dlp altyazı indirme --
        # --impersonate chrome + android client ile evasion donanımlı, YouTube'un
        # engellemesine karşı en dayanıklı yöntem (2) youtube-transcript-api --
        # evasion'sız, düz HTTP istemcisi, (1) başarısız olursa hızlı ek deneme
        # (3) OmniRoute (Deepgram) -- altyazı yoksa, Whisper'dan önce denenen
        # hızlı ses çözümleme (4) Whisper ile ses çözümleme -- son çare. Her
        # yöntem TEK SEFER denenir, başarısız olursa hemen sıradakine geçilir --
        # gereksiz ekstra deneme YOK, hız için.
        step_labels = ["ytdlp_subs", "subtitle_api", "omniroute_deepgram", "whisper"]
        for i, fn in enumerate([
            lambda: get_transcript_ytdlp_subtitles(video_url, video_id),
            lambda: get_transcript_youtube_api(video_id),
            lambda: get_transcript_omniroute_deepgram(video_url),
            lambda: get_transcript_ytdlp_whisper(video_url),
        ], start=1):
            PREPARE_STATUS[video_id] = step_labels[i - 1]
            print(f"  [{i}/4] deneniyor...")
            t = fn()
            if t:
                t = clean_transcript_text(t)
                print(f"  ✅ Yöntem {i} başarılı")
                TRANSCRIPT_CACHE[video_id] = t
                PREPARE_STATUS[video_id] = "done"
                return t

        print("  ❌ Hiçbir yöntem transkript bulamadı\n")
        PREPARE_STATUS[video_id] = "failed"
        return None


def _call_with_retry(fn, max_retries: int = 4, base_delay: float = 2.5, max_wait: float = 10.0):
    """
    Groq'un geçici hız limiti (rate limit / 429) hatalarını kullanıcıya hemen
    hata olarak göstermek yerine otomatik bekleyip yeniden dener. Groq'un hata
    mesajı genelde "try again in X.Ys" içerir; varsa o süre kadar (biraz payla),
    yoksa artan bir süre (4s, 8s, 12s...) beklenir, en fazla max_wait saniye.
    Rate limit DIŞI hatalarda hemen tekrar fırlatılır (gereksiz beklemeye gerek yok).
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            last_err = e
            is_rate_limit = "rate_limit" in msg.lower() or "429" in msg or "rate limit" in msg.lower()
            if not is_rate_limit or attempt == max_retries - 1:
                raise
            wait = min(base_delay * (attempt + 1), max_wait)
            match = re.search(r"try again in ([\d.]+)s", msg, re.IGNORECASE)
            if match:
                try:
                    wait = min(float(match.group(1)) + 0.5, max_wait)
                except Exception:
                    pass
            print(f"  ⏳ Groq hız limiti, {wait:.1f}s bekleniyor ve otomatik yeniden deneniyor "
                  f"(deneme {attempt + 1}/{max_retries})...")
            time.sleep(wait)
    raise last_err


def _chat_completion(system_prompt: str, user_prompt: str, history: list = None,
                      max_tokens: int = 1000, temperature: float = 0.7, feature: str = None,
                      skip_providers: set = None) -> str:
    """
    Metin üretimi için sırasıyla OmniRoute -> Groq -> OpenRouter dener; biri
    başarısız olursa (hız limiti, geçici kesinti vb.) otomatik sıradakine geçer.
    'feature' verilirse (örn. "summarize") ve OmniRoute'ta o göreve özel bir
    anahtar tanımlıysa (OMNIROUTE_FEATURE_KEYS), OmniRoute isteği o anahtarla
    yapılır -> kullanıcının OmniRoute'ta göreve göre ayarladığı combo devreye girer.
    """
    # Bazı (özellikle otomatik yönlendirilen ücretsiz) modeller düşünme
    # sürecini/planını normal cevaba karıştırıp sızdırabiliyor (örn. "We need
    # to segment the video into..." gibi paragraflar). Bunu TEK merkezden
    # (her çağrının sistem promptuna eklenerek) engellemeye çalışıyoruz.
    system_prompt = (
        f"{system_prompt} SADECE istenen nihai cevabı yaz; düşünme sürecini, "
        "planını, kendi kendine konuşmanı veya 'reasoning'ini asla gösterme/yazma."
    )
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    # SIRALAMA: varsayilan olarak Groq/OpenRouter ONCE denenir (OmniRoute'un
    # sikistirma katmani uzun/tekrarli promptlarda bazen bozuk/alakasiz icerik
    # dondurdugu icin -- olcumle dogrulandi). AMA kullanicinin OmniRoute'ta bu
    # gorev (feature) icin OZEL olarak sectigi bir kombinasyon/AI varsa
    # (OMNIROUTE_FEATURE_KEYS'te tanimliysa), o BILEREK yapilmis tercihi
    # ONCELIKLENDIRIYORUZ -- OmniRoute'u bu cagri icin listenin basina aliyoruz.
    # Bozuk/alakasiz sonuc gelirse zaten cagiran taraf (bkz. _chat_completion_on_topic,
    # generate_all_features_combined, build_recommendations) skip_providers={"omniroute"}
    # ile Groq'a otomatik duser, yani guvenilirlik kaybolmuyor.
    providers = TEXT_PROVIDERS
    if feature and feature in OMNIROUTE_FEATURE_KEYS and not (skip_providers and "omniroute" in skip_providers):
        providers = sorted(providers, key=lambda p: 0 if p["name"] == "omniroute" else 1)

    last_err = None
    tried_any = False
    for provider in providers:
        if skip_providers and provider["name"] in skip_providers:
            continue
        if not provider["api_key"]:
            continue
        tried_any = True

        key_override = None
        if provider["name"] == "omniroute" and feature and feature in OMNIROUTE_FEATURE_KEYS:
            key_override = OMNIROUTE_FEATURE_KEYS[feature]
        client = _client_for(provider, key_override)

        provider_err = None
        models = provider["models"]
        for i, model_id in enumerate(models):
            def _do_call(c=client, m=model_id):
                # stream=False AÇIKÇA gönderiliyor: OmniRoute, istek gövdesinde
                # 'stream' alanı YOKSA varsayılan olarak SSE stream döndürüyor;
                # bu da OpenAI istemcisinin normal (stream olmayan) yanıt
                # beklerken "Connection error" almasına yol açıyordu. Açıkça
                # False göndermek gerçek (application/json) yanıt garantiler.
                response = c.chat.completions.create(
                    model=m, messages=messages, temperature=temperature, max_tokens=max_tokens,
                    stream=False,
                )
                text = response.choices[0].message.content or ""
                if CCR_ARTIFACT_RE.search(text):
                    raise RuntimeError(
                        "OmniRoute compression artifact leaked into response "
                        "(unresolved [CCR retrieve hash=...]) — sağlayıcı/model atlanıyor"
                    )
                return text

            try:
                # Sağlayıcı başına kısa bir retry bütçesi (fazla beklemeden diğerine geç)
                result = _call_with_retry(_do_call, max_retries=1, base_delay=1.5, max_wait=4.0)
                if provider["name"] != TEXT_PROVIDERS[0]["name"] or model_id != models[0]:
                    print(f"  🔁 {provider['name']} ({model_id}) ile devam edildi")
                return result
            except Exception as e:
                provider_err = e
                msg = str(e).lower()
                is_model_error = "model_not_found" in msg or "does not exist" in msg or "decommission" in msg
                if is_model_error and i < len(models) - 1:
                    print(f"  ⚠️ {provider['name']}: '{model_id}' kullanılamıyor, sıradaki modele geçiliyor")
                    continue
                break

        print(f"  ⚠️ {provider['name']} başarısız: {provider_err}")
        last_err = provider_err
        continue

    if not tried_any:
        raise RuntimeError("Hiçbir AI sağlayıcısı yapılandırılmamış (.env dosyası boş/eksik görünüyor).")
    raise last_err


def get_full_context_material(video_id: str, transcript: str) -> str:
    """
    TÜM işlemler (özet/analiz/bölümler/öneriler/sohbet) için kullanılan ortak bağlam.

    Transkript modelin bağlam penceresine rahatça sığıyorsa doğrudan kullanılır.
    Sığmıyorsa (uzun video) videonun TAMAMI parçalara bölünüp HER parçadan geçen
    konular/isimler/terimler çıkarılır ve birleştirilir -> nihai özet/analiz/öneri
    SADECE videonun başındaki bilgiye değil, videonun TAMAMINA dayanır.

    Sonuç video_id bazında cache'lenir, yani bu işlem video başına sadece bir kez
    yapılır (tüm özellikler ve sohbet mesajları aynı cache'lenmiş materyali kullanır).
    """
    if video_id in MATERIAL_CACHE:
        return MATERIAL_CACHE[video_id]

    if len(transcript) <= MAX_DIRECT_CHARS:
        MATERIAL_CACHE[video_id] = transcript
        return transcript

    print(f"  ℹ️ Transkript uzun ({len(transcript)} karakter) — videonun TAMAMI için PARALEL parçalanıp işleniyor...")
    chunks = [transcript[i:i + CHUNK_CHARS] for i in range(0, len(transcript), CHUNK_CHARS)]
    results = [None] * len(chunks)

    def _process_chunk(idx_chunk):
        idx, chunk = idx_chunk
        try:
            note = _chat_completion(
                "Sen bir video transkript analiz asistanısın. Sana verilen metin, uzun bir videonun bir bölümüdür.",
                f"""Bu, videonun {idx + 1}. parçası (toplam {len(chunks)} parça). Bu parçada geçen ÖNEMLİ konuları,
olayları, isimleri, terimleri ve söylenenleri madde madde, kısa ve öz şekilde (transkriptin kendi dilinde
değil, Türkçe) listele. Hiçbir şey uydurma, sadece bu parçada geçenleri yaz.

Parça:
{chunk}""",
                max_tokens=700, temperature=0.3,
                feature="chat",
            )
            return idx, f"[Video Parçası {idx + 1}/{len(chunks)}]\n{note}"
        except Exception as e:
            print(f"    ⚠️ Parça {idx + 1} işlenemedi: {e}")
            return idx, None

    max_workers = min(4, len(chunks))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, note in executor.map(_process_chunk, enumerate(chunks)):
            results[idx] = note

    notes = [n for n in results if n]
    combined = "\n\n".join(notes).strip()
    # Son bir güvenlik sınırı (aşırı uzun videolarda notlar da çok büyürse)
    if len(combined) > MAX_DIRECT_CHARS:
        combined = combined[:MAX_DIRECT_CHARS]

    MATERIAL_CACHE[video_id] = combined or transcript[:MAX_DIRECT_CHARS]
    print(f"  ✅ Video tamamından {len(chunks)} parça (paralel) halinde bağlam çıkarıldı.")
    return MATERIAL_CACHE[video_id]


# Bir kelimeyi "anlamlı" saymak için stopword listesi (cok yaygin/genel
# kelimeler baslikla rastlantisal ortusebilir, bunlar elenir).
_TOPIC_GUARD_STOPWORDS = {
    "daha", "önce", "sonra", "böyle", "gibi", "için", "video", "kanal",
    "resmi", "official", "channel", "which", "there", "their", "about",
    "with", "from", "this", "that", "olan", "olan", "değil", "türkçe",
}
_TOPIC_GUARD_WORD_RE = re.compile(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]{5,}")


def _extract_significant_words(text: str) -> set:
    words = _TOPIC_GUARD_WORD_RE.findall(text or "")
    return {w.lower() for w in words} - _TOPIC_GUARD_STOPWORDS


def _looks_on_topic(generated_text: str, video_title: str) -> bool:
    """Üretilen metin, videonun GERÇEK başlığındaki en az bir anlamlı
    kelimeyle örtüşüyor mu? Başlıkta anlamlı kelime yoksa kontrol edilemez,
    geçerli sayılır (yanlış pozitif üretmemek için)."""
    title_words = _extract_significant_words(video_title)
    if not title_words:
        return True
    gen_words = _extract_significant_words(generated_text)
    return bool(title_words & gen_words)


def _chat_completion_on_topic(system_prompt: str, user_prompt: str, video_title: str,
                               max_tokens: int = 1000, temperature: float = 0.7, feature: str = None) -> str:
    """
    _chat_completion'ı çağırır; sonuç video başlığıyla TAMAMEN ALAKASIZ görünüyorsa
    (OmniRoute'un bağlam sıkıştırma katmanının farklı bir konuyla karıştırdığı
    gözlemlendi -- örn. bir "Leona" videosu için "Jax" ya da "senior developer/YAGNI"
    içerikli yanıt döndürmüştü) OmniRoute atlanıp BİR KEZ daha denenir.
    """
    result = _chat_completion(system_prompt, user_prompt, max_tokens=max_tokens, temperature=temperature, feature=feature)
    if not _looks_on_topic(result, video_title):
        print(f"  ⚠️ Üretim video başlığıyla alakasız göründü (OmniRoute sıkıştırma sorunu olabilir), OmniRoute atlanıp tekrar deneniyor")
        result = _chat_completion(system_prompt, user_prompt, max_tokens=max_tokens, temperature=temperature,
                                   skip_providers={"omniroute"})
    return result


def _handle_groq_error(e: Exception, video_id: str = None):
    msg = str(e)
    payload = {"error": msg}
    if video_id:
        payload["video_id"] = video_id
    if "rate_limit" in msg.lower() or "429" in msg:
        has_backup = bool(OPENROUTER_API_KEY)
        if has_backup:
            payload["error"] = ("⚠️ Hem Groq hem OpenRouter şu anda çok yoğun/limitli, birkaç kez otomatik "
                                 "yeniden denendi ama yine de olmadı. Lütfen 30-60 saniye bekleyip tekrar deneyin.")
        else:
            payload["error"] = ("⚠️ Groq şu anda çok yoğun, birkaç kez otomatik yeniden denendi ama yine de "
                                 "olmadı. Lütfen 30-60 saniye bekleyip tekrar deneyin, ya da OpenRouter gibi "
                                 "ikinci bir yedek sağlayıcı ekleyin (.env dosyasına).")
        return jsonify(payload), 429
    if "model" in msg.lower() and ("not found" in msg.lower() or "decommission" in msg.lower()):
        payload["error"] = ("⚠️ Model adı geçersiz. server.py'deki GROQ_CHAT_MODELS veya "
                             "OPENROUTER_CHAT_MODEL değişkenini güncelleyin.")
        return jsonify(payload), 500
    return jsonify(payload), 500


# ==================== YT-DLP İLE GERÇEK VİDEO ARAMA ====================
# Öneri arama sonuçlarının AI'nın önerdiği konuyla GERÇEKTEN alakalı olup
# olmadığını (yerel, AI çağrısı olmadan, hızlı) kontrol etmek için kullanılır --
# embed-güvenliği tek başına yeterli değil: "kariyer değişikliği" araması bir
# oyun kariyer modu videosuyla embed-güvenli şekilde eşleşebiliyordu, konuyla
# hiç alakası olmasa bile. Basit kelime-örtüşmesi, tamamen alakasız sonuçları
# (sıfır ortak anlamlı kelime) eler.
_RELEVANCE_STOPWORDS = {
    "bir", "bu", "şu", "ve", "ile", "için", "nasıl", "gibi", "olan", "olması",
    "olur", "en", "çok", "de", "da", "ki", "mı", "mi", "mu", "mü", "ne", "her",
    "the", "a", "an", "of", "and", "for", "how", "to", "in", "on", "with", "your",
    # AI'nın kendi urettigi kalip/sablon kelimeleri (bkz. prompt: "[Konu] Rehberi",
    # "[Konu] Nasil Oynanir") -- bunlar YouTube'da SAYISIZ alakasiz videoda gectigi
    # icin gercek konu alakasi GOSTERMEZ, sayima dahil edilmemeli.
    "rehber", "rehberi", "rehberleri", "kılavuz", "kılavuzu", "yapılır", "oynanır",
    "derlemesi", "derleme", "konuşmaları", "konuşması", "videoları", "videosu",
}


def _significant_words(text: str) -> list:
    words = re.sub(r"[^\w\s]", " ", (text or "").lower(), flags=re.UNICODE).split()
    return [w for w in words if len(w) >= 4 and w not in _RELEVANCE_STOPWORDS]


def _shares_root(a: str, b: str) -> bool:
    """Turkce ek farklarini tolere etmek icin GERCEK ortak on-ek uzunlugunu olcer
    (sabit ilk-N-karakter kesmesi degil -- o yontem 'baslangic'/'baslar' gibi ortak
    kisa kok tasiyan ama ALAKASIZ kelime ciftlerini de yanlislikla eslestiriyordu).
    Tam esitlik her zaman gecerli (kisa ama tam kelimeler icin, orn. 'apple'); aksi
    halde en az 6 ortak onculu karakter aranir."""
    if a == b:
        return True
    shared = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        shared += 1
    return shared >= 6


def _title_relevance_score(query_title: str, candidate_title: str) -> int:
    """Ortak anlamlı kelime sayısı (Türkçe ek farklarını tolere etmek için gerçek
    ortak-önek uzunluğuna bakılır, örn. 'kariyer' ~ 'kariyeri'). Şablon/genel
    kelimeler (_RELEVANCE_STOPWORDS) çıkarıldıktan sonra bile TEK kelime örtüşmesi
    zayıf bir sinyal olabilir; çağıran taraf bu yüzden en az 2 eşleşme şartı arıyor."""
    q_words = _significant_words(query_title)
    c_words = _significant_words(candidate_title)
    if not q_words or not c_words:
        return 0
    matches = 0
    for qw in q_words:
        for cw in c_words:
            if _shares_root(qw, cw):
                matches += 1
                break
    return matches


def exa_search_candidates(query: str, want: int = 2) -> list:
    """
    Exa Search'ün nöral (anlam tabanlı) aramasıyla gerçek YouTube video adayı
    bulur -- yt-dlp'nin kelime eşleşmeli ytsearch'ünden çok daha isabetli
    (test edildi: "Steve Jobs Stanford commencement speech" için 787ms'de 3
    doğru sonuç döndü). OmniRoute üzerinden DEĞİL, Exa'nın kendi API'sine
    doğrudan bağlanıyor (bkz. EXA_SEARCH_API_KEY tanımının yanındaki not --
    OmniRoute'un bu sağlayıcı için proxy desteği bozuk). Sonuç bulunamazsa
    (anahtar/ağ sorunu) boş liste döner, çağıran taraf ytdlp_search_candidates'a
    düşer.
    """
    if not EXA_SEARCH_API_KEY:
        return []
    try:
        r = requests.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": EXA_SEARCH_API_KEY, "Content-Type": "application/json"},
            json={"query": query, "numResults": want + 1, "includeDomains": ["youtube.com", "youtu.be"]},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        out = []
        for item in results:
            vid = extract_video_id(item.get("url", ""))
            if not vid:
                continue
            out.append({
                "video_id": vid,
                "real_title": item.get("title") or query,
                "channel": "",
                "url": item.get("url") or f"https://www.youtube.com/watch?v={vid}",
            })
            if len(out) >= want:
                break
        return out
    except Exception as e:
        print(f"  [Exa] '{query}' için arama başarısız: {e}")
        return []


def ytdlp_search_candidates(query: str, want: int = 2) -> list:
    """
    Verilen sorgu için YouTube'da gerçek video adayları bulur. "Bu video
    kullanılamıyor" (embed kısıtlı/yaş sınırlı/özel) hatası riski taşıyan
    sonuçları elemeye çalışır ve en iyi `want` kadar adayı sırayla döndürür
    (ilki birincil, ikincisi frontend'de embed hatası olursa otomatik
    geçilecek yedek olarak kullanılır).
    """
    if not check_ytdlp_available():
        return []
    try:
        result = subprocess.run(
            YTDLP_CMD + ytdlp_bypass.build_search_args(query, want_results=5),
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        if result.returncode != 0 or not result.stdout.strip():
            if result.stderr:
                print(f"  [Arama] '{query}' için yt-dlp hatası: {result.stderr.strip()[:300]}")
            return []

        candidates = []
        for line in result.stdout.strip().split("\n"):
            try:
                candidates.append(json.loads(line))
            except Exception:
                continue
        if not candidates:
            return []

        def _risk_score(c: dict) -> int:
            # Düşük skor = daha güvenli (embed hatası riski düşük)
            score = 0
            if c.get("playable_in_embed") is False:
                score += 20
            if (c.get("age_limit") or 0) > 0:
                score += 10
            availability = (c.get("availability") or "").lower()
            if availability and availability not in ("public", "unlisted"):
                score += 15
            if c.get("live_status") in ("is_live", "is_upcoming"):
                score += 15
            return score

        # Once tamamen alakasiz sonuclari ele (sifir ortak anlamli kelime),
        # sonra kalanlari alaka (once) + embed-guvenligi (sonra) sirasina gore diz.
        scored = []
        for c in candidates:
            relevance = _title_relevance_score(query, c.get("title", ""))
            if relevance < 2:  # tek kelime ortusmesi cok zayif bir sinyal, en az 2 sart
                continue
            scored.append((relevance, c))
        scored.sort(key=lambda rc: (-rc[0], _risk_score(rc[1])))
        candidates = [c for _, c in scored]

        out = []
        for c in candidates[:want]:
            vid = c.get("id")
            if not vid:
                continue
            out.append({
                "video_id": vid,
                "real_title": c.get("title", query),
                "channel": c.get("uploader") or c.get("channel") or "",
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        return out
    except Exception as e:
        print(f"  [Arama] '{query}' için video bulunamadı: {e}")
        return []


def ytdlp_search_one(query: str) -> Optional[dict]:
    """Geriye dönük uyumluluk için: sadece ilk (birincil) adayı döndürür."""
    candidates = ytdlp_search_candidates(query, want=1)
    return candidates[0] if candidates else None


def quick_web_search(query: str, max_results: int = 3) -> str:
    """
    API anahtarı gerektirmeyen, HIZLI bir web araması (DuckDuckGo HTML).
    Amaç: video başlığı yanıltıcıysa (örn. bir anime şarkısının adı "Treachery"
    diye günlük bir kelimeymiş gibi durabiliyor ama aslında bir anime OST'i)
    önerileri gerçek bağlama göre üretmek. Sonuç bulunamazsa/hata olursa boş
    döner ve akışı BLOKLAMAZ (öneriler yine de üretilir, sadece bağlamsız).
    """
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=4,
        )
        if resp.status_code != 200 or not resp.text:
            return ""

        # Basit regex ile snippet metinlerini çıkar (bs4 bağımlılığı eklemeden)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
        if not snippets:
            snippets = re.findall(r'class="result__a"[^>]*>(.*?)</a>', resp.text, re.DOTALL)

        clean = []
        for s in snippets[:max_results]:
            text = re.sub(r"<[^>]+>", "", s)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                clean.append(text)

        return " | ".join(clean)
    except Exception as e:
        print(f"  ⚠️ Web araması başarısız (atlanıyor, hız için akış devam ediyor): {e}")
        return ""


def _extract_json_value(text: str, open_ch: str, close_ch: str) -> Optional[str]:
    """
    Metin içinde parantez dengesini sayarak İLK geçerli JSON değerini bulur.
    Bazı modeller (özellikle otomatik yönlendirilen ücretsiz "reasoning"
    modelleri) JSON'dan ÖNCE/SONRA düşünme sürecini düz metin olarak
    ekleyebiliyor; bu da json.loads'un doğrudan başarısız olmasına neden
    oluyordu (öneriler/bölümler bomboş dönüyordu).
    """
    start = text.find(open_ch)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_recommendations_json(raw: str) -> list:
    """Groq'un döndürdüğü metni [{'title','reason'}] listesine çevir."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    cleaned = _extract_json_value(cleaned, "[", "]") or cleaned
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return [{"title": str(x.get("title", "")).strip(), "reason": str(x.get("reason", "")).strip()}
                     for x in data if x.get("title")]
    except Exception:
        pass

    # Fallback: satır satır regex ile ayıkla
    items = []
    blocks = re.split(r"\n\s*\n|---", cleaned)
    for b in blocks:
        title_m = re.search(r'(?:"?title"?\s*[:=]\s*"?|BAŞLIK\s*:\s*)([^\n"]+)', b, re.IGNORECASE)
        reason_m = re.search(r'(?:"?reason"?\s*[:=]\s*"?|NEDEN\s*:\s*)([^\n"]+)', b, re.IGNORECASE)
        if title_m:
            items.append({
                "title": title_m.group(1).strip().strip(',"'),
                "reason": reason_m.group(1).strip().strip(',"') if reason_m else "",
            })
    return items


def parse_combined_features_json(raw: str) -> Optional[dict]:
    """generate_all_features_combined'ın döndürdüğü JSON metnini sözlüğe çevirir."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    cleaned = _extract_json_value(cleaned, "{", "}") or cleaned
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


# AI bolum basliklarini bazen ayni satira art arda yazabiliyor (orn.
# "...aciklama [05:10] Baslik2 ..."). Her [MM:SS] zaman damgasinin kendi
# satirinda baslamasini garanti eden basit bir post-process regex.
CHAPTER_TIMESTAMP_RE = re.compile(r"[ \t]*(\[\d{1,3}:\d{2}(?::\d{2})?\])")

# OmniRoute'un baglam sikistirma ("compression") ozelligi, buyukce promptlari
# bazen modele göndermeden önce "[CCR retrieve hash=...]" gibi bir referansla
# degistiriyor; ama bu API'yi düz OpenAI-uyumlu istemciyle kullanan bizim gibi
# bir cagiran bu hash'i "geri cozemez", model de eldeki gercek icerigi
# goremeyip bos/reddeden bir cevap uretiyor. Boyle bir sizinti tespit edilirse
# bu, saglayici/model basarisiz sayilip bir sonrakine gecilir.
CCR_ARTIFACT_RE = re.compile(r"\[CCR\s+retrieve\s+hash=", re.IGNORECASE)


def _coerce_text(value) -> str:
    """AI yanitindaki bir alan (orn. "chapters") string yerine yanlislikla
    liste/baska bir tur donerse, guvenli sekilde duz metne cevirir. Boyle bir
    uyumsuzluk daha once "expected string or bytes-like object, got 'list'"
    hatasiyla TUM birlesik uretimi comduruyordu."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_coerce_text(v) for v in value)
    if value is None:
        return ""
    return str(value)


def ensure_chapter_linebreaks(text: str) -> str:
    text = _coerce_text(text)
    if not text:
        return text
    text = CHAPTER_TIMESTAMP_RE.sub(r"\n\1", text)
    text = re.sub(r"\n{2,}", "\n", text)
    text = text.strip()

    # Bazı modeller (özellikle otomatik yönlendirilen ücretsiz "reasoning"
    # modelleri) düşünme sürecini düz metin olarak cevaba karıştırabiliyor
    # (örn. "We need to segment the video into..."). SADECE gerçek [MM:SS]/
    # [H:MM:SS] zaman damgasıyla başlayan satırlar kabul edilir. Eskiden zaman
    # damgasız ama " - " içeren kısa satırlar da kabul ediliyordu -- bu da
    # modelin "Bölüm 1 - ...", "Bölüm 2 - ..." gibi UYDURMA (gerçek zaman
    # damgası olmayan) başlıkları sessizce geçirmesine yol açan delikti
    # (gerçek olayda gözlemlendi, kullanıcı bildirdi). Hiçbir satır gecerli
    # degilse ARTIK ham metne düşülmez -- bos donup frontend "bölüm bulunamadı"
    # mesajı göstersin, yanıltıcı "Bölüm 1" göstermekten iyidir.
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if re.match(r"^\[\d{1,3}:\d{2}(?::\d{2})?\]", line):
            lines.append(line)
    return "\n".join(lines)


def generate_real_timestamped_chapters(video_id: str, lang: str) -> Optional[str]:
    """
    Bolumleri LLM'in TAHMIN ETMESI yerine, youtube-transcript-api'nin GERCEK
    zaman damgali (start, text) verisinden (_get_transcript_items_with_timestamps,
    zaten var -- muzik/line_mode icin kullaniliyordu) hesaplanan SABIT ankraj
    noktalariyla uretir. LLM'e zaman damgasi HIC SORULMAZ -- sadece o ankrajdaki
    icerik icin kisa bir baslik/aciklama yazdirilir, zaman damgasini KOD hesaplar.
    Boylece "Bolum 1", "Bolum 2" gibi UYDURMA zaman damgasi ARTIK MUMKUN DEGIL.

    Video icin altyazi zaman verisi yoksa (orn. sadece ses transkripsiyonuyla
    metin cikarildiysa, hic yazili altyazi/CC izi yoksa) None doner, cagiran
    taraf eski (AssemblyAI veya LLM tahminli) yontemlere duser -- durum daha
    kotu HALE GETIRILMEZ, sadece bu iyilestirme uygulanamaz.
    """
    try:
        items = _get_transcript_items_with_timestamps(video_id)
        if len(items) < 5:
            return None
        duration = items[-1][0]
        if duration < 90:  # 1.5 dakikadan kisa videoyu bolmeye gerek yok
            return None

        num_chapters = max(3, min(8, int(duration // 180)))
        anchors = [round(duration * i / num_chapters) for i in range(num_chapters)]

        # Her ankraj icin, o noktadan sonraki ~45 saniyelik konusma metnini
        # topla -- o bolumun neyi kapsadigini LLM'e gostermek icin baglam.
        contexts = []
        for anchor in anchors:
            window_text = " ".join(
                text for start, text in items if anchor <= start < anchor + 45
            ).strip()
            if not window_text:
                later = [text for start, text in items if start >= anchor]
                window_text = " ".join(later[:3]).strip()
            contexts.append(window_text[:280])

        items_desc = "\n".join(f"{i}: {ctx}" for i, ctx in enumerate(contexts) if ctx)
        if not items_desc:
            return None

        prompt = (
            f"Asagida bir videonun {num_chapters} farkli anina ait konusma metni "
            "parcalari var (indeks: metin). Her biri icin KISA bir bolum basligi "
            "ve kisa bir aciklama yaz. ZAMAN DAMGASI YAZMA -- sadece baslik ve "
            f"aciklama iste, zaman zaten biliniyor.\n\n{items_desc}\n\n"
            'SADECE su JSON dizisini dondur, baska hicbir sey yazma: '
            '[{"index": 0, "baslik": "...", "aciklama": "..."}, ...]'
        )
        system_prompt = f"Sen bir video bolumlendirme asistanisin. {lang_instruction(lang)}"
        # feature=None (varsayilan Groq/OpenRouter sirasi) KASITLI: ceviride
        # gozlemlendigi gibi OmniRoute uzun/yapisal promptlarda alakasiz icerik
        # dondurebiliyor -- burada da yapisal (JSON, index eslesmeli) bir cikti
        # istiyoruz, ayni riski almamak icin.
        raw = _chat_completion(system_prompt, prompt, max_tokens=1200, temperature=0.3)
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        cleaned = _extract_json_value(cleaned, "[", "]") or cleaned
        parsed = json.loads(cleaned)
        if not isinstance(parsed, list):
            return None

        by_index = {}
        for item in parsed:
            if isinstance(item, dict) and "index" in item:
                by_index[item["index"]] = item

        lines = []
        for i, anchor in enumerate(anchors):
            entry = by_index.get(i)
            if not entry:
                continue
            title = str(entry.get("baslik", "")).strip()
            desc = str(entry.get("aciklama", "")).strip()
            if not title:
                continue
            mins, secs = divmod(anchor, 60)
            if mins >= 60:
                h, mins = divmod(mins, 60)
                ts = f"{h}:{mins:02d}:{secs:02d}"
            else:
                ts = f"{mins:02d}:{secs:02d}"
            line = f"[{ts}] {title}"
            if desc:
                line += f" - {desc}"
            lines.append(line)

        return "\n".join(lines) if lines else None
    except Exception as e:
        print(f"  ⚠️ Gerçek zaman damgalı bölüm üretimi başarısız: {e}")
        return None


def generate_all_features_combined(video_id: str, transcript: str, meta: dict, lang: str) -> dict:
    """
    HIZ + RATE-LİMİT İÇİN KRİTİK: Özet, analiz, bölümler ve öneri başlıkları
    4 AYRI çağrı yerine TEK bir AI çağrısında üretilir. Bu hem toplam API
    çağrı sayısını (dolayısıyla Groq/OpenRouter hız-limitine takılma riskini)
    ~4 kat azaltır hem de kullanıcı bir sekmeye tıkladığında sonucun ZATEN
    hazır olmasını sağlar (sekme başına ayrı bekleme olmaz).
    """
    material = get_full_context_material(video_id, transcript)
    metadata_context = format_metadata_context(meta)
    content_type = detect_content_type(meta)
    video_title = meta.get("title") or ""
    lang_name = CODE_TO_LANG_NAME.get((lang or "tr").lower(), "turkish")

    timestamped = None
    try:
        items = _get_transcript_items_with_timestamps(video_id)
        if items:
            lines = []
            for start, text in items:
                start = int(start)
                mins, secs = divmod(start, 60)
                lines.append(f"[{mins:02d}:{secs:02d}] {text.replace(chr(10), ' ').strip()}")
            timestamped = "\n".join(lines)
    except Exception:
        pass

    content_type_instruction = {
        "music": (
            "Bu içerik bir ŞARKI/MÜZİK PARÇASI. Öneriler BENZER ŞARKILAR olsun (aynı sanatçı/tür/"
            "anime-film-oyun OST'i/benzer tema) — bilgilendirici/analiz videosu önerme."
        ),
        "fan_edit": (
            "Bu içerik bir AMV/MV/EDIT/TRIBUTE videosu (bir eserin görüntüleri + şarkı, hayran kurgusu). "
            "YouTube kategorisi yanlış olabilir ama içerik ÖZÜNDE MÜZİK/KURGU eksenlidir. Öneriler BENZER "
            "EDIT/AMV/MÜZİK videoları olsun. KESİNLİKLE karakter analizi/lore/inceleme videosu önerme. "
            "ÇOK ÖNEMLİ: Elindeki transkript SADECE şarkının sözleridir, videoda GÖRSEL olarak ne "
            "gösterildiğini YANSITMAZ (örn. bir 'Transformers Dance Again' videosunda transkript sadece "
            "şarkının kendi (alakasız) konusunu anlatır, ama video GÖRSEL olarak Transformers sahneleri "
            "gösterir). Özet/analiz/bölümleri SADECE şarkı sözlerinin konusunu anlatarak yazma — video "
            "başlığından/kanal adından/açıklamasından anladığın GERÇEK GÖRSEL/TEMATİK içeriği (hangi eser, "
            "hangi karakterler/sahneler) MUTLAKA öne çıkar, şarkı sözü sadece EŞLİK EDEN müzik olarak geçsin."
        ),
        "info": (
            "Bu içerik bir BİLGİLENDİRME/EĞİTİM videosu. Öneriler BENZER KONULU bilgilendirme videoları "
            "olsun — şarkı/müzik/AMV önerme."
        ),
    }[content_type]

    prompt = f"""Aşağıdaki YouTube videosu için 4 farklı çıktıyı TEK SEFERDE üret ve SADECE geçerli bir JSON
nesnesi olarak döndür. Başka hiçbir açıklama/markdown/metin ekleme.

=== VİDEONUN GERÇEK KİMLİĞİ (başlıktan/transkriptten DAHA ÖNCELİKLİ) ===
Video başlığı: {video_title or "(bilinmiyor)"}
{metadata_context if metadata_context else "(kanal adı/açıklama/etiket bilgisi alınamadı)"}
=== KİMLİK BİLGİSİ SONU ===

İÇERİK TÜRÜ: {content_type_instruction}

KURAL: Video başlığı/transkripti tek başına yanıltıcı olabilir (örn. bir şarkı/anime adı gündelik bir kelimeymiş
gibi görünebilir, ya da bir AMV/edit videosu başka ünlü bir esere isim benzerliğiyle karıştırılabilir). Kanal
adı/açıklama bilgisi varsa ona öncelik ver.

Video içeriği (tamamı):
{material}
{("Zaman damgalı transkript (Bölümler için kullan, gerçek zaman damgalarını koru):" + chr(10) + timestamped[:20000]) if timestamped else ""}

YAZIM KALİTESİ (ÇOK ÖNEMLİ, "summary" ve "analysis" alanları için geçerli): Yüzeysel/genel geçiştirme
YAZMA. Her madde SOMUT olsun -- videoda geçen isim/örnek/olay/sebep-sonuç ilişkisini kullan. 'X hakkında
konuşuluyor' gibi tek cümlelik özetlerden KESİNLİKLE KAÇIN. Video zengin bir konuyu (örn. bir karakterin
gelişimi, çok aşamalı bir süreç, bir tez) işliyorsa bunu kendi aşamalarına ayırarak derinlemesine işle.
Video uzun/zenginse çıktı da buna paralel uzun ve zengin olsun, kısaltmaya ÇALIŞMA.

SADECE şu JSON formatında döndür (tüm metin içerikleri {lang_name} dilinde yazılsın):
{{
  "summary": "Videonun tamamını kapsayan, derinlemesine ve somut detaylı özet (madde madde, gerekirse madde başına emoji)",
  "analysis": "📌 ANA KONULAR (3-5 madde, somut detaylarla)\\n📋 ALT BAŞLIKLAR VE DETAYLAR (maddeler halinde, her biri başlık + somut açıklama; karmaşık konularda aşamalara/bölümlere ayırarak numaralandır)\\n👥 HEDEF KİTLE\\n🔑 ANAHTAR KELİMELER (yukarıdaki 'Etiketler' listesi verildiyse ONLARI kullan/önceliklendir, UYDURMA anahtar kelime üretme; etiket verilmediyse SADECE video içeriğinden gerçekten çıkarılabilecek kelimeleri yaz)",
  "recommendations": [
    {{"title": "gerçek içerik üreticilerinin kullandığı DOĞAL/GENEL bir başlık kalıbı (örn. '[Konu] Rehberi', '[Konu] Nasıl Oynanır', '[Sanatçı] - [Şarkı]') -- bu videodaki uydurma/aşırı spesifik bir detayı (sayı, tek bir an vb.) ASLA başlığa koyma, gerçek arama sonucu bulma ihtimalini sıfırlar", "reason": "neden önerildiği (kısa)"}}
  ]
}}
"recommendations" listesinde TAM OLARAK 5 öğe olsun."""

    _ECHO_MARKERS = ("KESİNLİKLE KAÇIN", "YETERSİZ", "somut detaylarıyla", "ÇOK ÖNEMLİ")
    # Kisa bir kalibin (1-12 karakter) art arda 5+ kez tekrarlanmasi -- zayif
    # modellerin (gozlemlendi: OpenRouter ucretsiz) bazen dustugu sonsuz tekrar
    # dongusu belirtisi (orn. "__=__(__(__=__(...").
    _DEGENERATE_LOOP_RE = re.compile(r"(.{1,12}?)\1{4,}")
    # Turkce/hedef dil metninde MESRU bir sebebi olmayan CJK (Cince/Japonca/Kore)
    # karakter blogu -- ayni zayif model modelinin gozlemlenen baska bir bozulma
    # belirtisi (orn. "一生", "使用的", "特に", "同学" gibi alakasiz karakterler
    # Turkce cumlelerin icine karisiyordu).
    _CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")

    def _field_is_clean(val) -> bool:
        if not isinstance(val, str):
            return True  # bos/eksik alan ayrica _has_valid_summary'de yakalanir
        if any(marker in val for marker in _ECHO_MARKERS):
            return False
        if _DEGENERATE_LOOP_RE.search(val):
            return False
        if _CJK_RE.search(val):
            return False
        return True

    def _has_valid_summary(p):
        val = p.get("summary") if p else None
        # 20 karakterlik alt sinir: gercek olayda gozlemlendi -- asiri yuk/kota
        # altindaki zayif bir yedek model, gecerli JSON + bos-olmayan (orn. 3
        # karakterlik) bir "summary" dondurebiliyor; bu eski kontrolden (sadece
        # bos mu diye bakan) SESSIZCE geciyordu. Gercek bir video ozeti bundan
        # cok daha uzun olur, bu yuzden bariz-kirpilmis/bozuk ciktilari da yakalar.
        if not isinstance(val, str) or len(val.strip()) < 20:
            return False
        # Model talimat metnimizi ICERIGE KOPYALADIYSA veya sonsuz tekrar/CJK
        # karisimi gibi bozulma belirtileri varsa (zayif modellerde gozlemlendi)
        # gecersiz sayilir -- cagiran taraf zaten skip_providers ile tekrar dener.
        # "analysis" alani da ayni sekilde kontrol edilir, cunku bozulma orada da
        # gorulebiliyor (bkz. "summary" gecerli ama "analysis" bozuk olan gercek
        # bir vaka).
        if not _field_is_clean(val):
            return False
        analysis_val = p.get("analysis") if p else None
        if not isinstance(analysis_val, str) or len(analysis_val.strip()) < 20:
            return False
        if not _field_is_clean(analysis_val):
            return False
        return True

    system_prompt = f"Sen bir YouTube video analiz asistanısın. SADECE istenen JSON formatında yanıt ver, başka metin ekleme. Her şey {lang_name} dilinde olsun."
    # GUNCELLEME: feature="chat" artik BILEREK VERILIYOR (eskiden verilmiyordu).
    # Eski olcum (OmniRoute ~44.9sn vs Groq-once ~13-14sn) OmniRoute'un sikistirma/
    # dogrulama sorunlari DUZELTILMEDEN ONCE yapilmisti. Bugun: (1) OmniRoute'un
    # "Yanit dogrulama" katmani kaldirildi + zeroLatencyOptimizationsEnabled acildi,
    # (2) Mistral->Gemini combo'lari kuruldu. Yeniden olculdu: Groq bu cagri
    # boyutunda (bu video icin 11292 token istendi) HER SEFERINDE 8000 TPM limitini
    # asip yavas OpenRouter yedegine dusuyordu -> 104.0sn. Ayni cagri OmniRoute
    # (Yonetici/Mistral->Gemini) uzerinden 14.6sn'de tamamlandi -- yaklasik 7x
    # daha hizli. Gecersiz/bos JSON donerse zaten asagida OmniRoute atlanip
    # Groq/OpenRouter ile tekrar deneniyor, yani guvenilirlik kaybolmuyor.
    raw = _chat_completion(system_prompt, prompt, max_tokens=6000, temperature=0.4, feature="chat")
    parsed = parse_combined_features_json(raw)

    # Gözlem: OmniRoute'un bağlam sıkıştırma katmanı bazen bu çağrıyı TAMAMEN
    # ALAKASIZ bir konuyla (örn. bir "Leona" League of Legends videosu için
    # "senior developer / YAGNI prensibi" içerikli bir yanıt) karıştırıyor.
    # Bu yanıt GEÇERLİ JSON olduğu için parse başarılı sayılıyor ama beklenen
    # "summary" alanı hiç yok/boş/yanlış tipte (örn. liste) -> tüm sekmeler
    # sessizce BOŞ dönüyordu (hata da vermiyordu). Şema doğrulaması: "summary"
    # gerçek/dolu bir metin değilse, OmniRoute'u atlayıp BİR KEZ daha deneniyor.
    if not _has_valid_summary(parsed):
        print("  ⚠️ Birleşik üretim boş/uyumsuz döndü (OmniRoute sıkıştırma sorunu olabilir), OmniRoute atlanıp tekrar deneniyor")
        raw = _chat_completion(system_prompt, prompt, max_tokens=6000, temperature=0.3, skip_providers={"omniroute"})
        parsed = parse_combined_features_json(raw)

    if not _has_valid_summary(parsed):
        raise RuntimeError("AI yanıtı JSON formatında ayrıştırılamadı/boş döndü, tek tek üretime düşülecek")
    return parsed


def enrich_recommendation_items(items: list) -> list:
    """Öneri başlıklarını (title/reason) gerçek YouTube videolarıyla eşleştirir (paralel, non-LLM)."""
    items = items[:5]
    results = [None] * len(items)

    def _search_one(idx_item):
        idx, item = idx_item
        title = item.get("title", "")
        # Once Exa'nin anlam-tabanli aramasi denenir (daha isabetli); anahtar/ag
        # sorunu olursa yt-dlp'nin kelime-eslesmeli aramasina sessizce dusulur.
        candidates = exa_search_candidates(title, want=2)
        if not candidates:
            candidates = ytdlp_search_candidates(title, want=2)
        return idx, candidates

    if items:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(items))) as executor:
            for idx, candidates in executor.map(_search_one, enumerate(items)):
                item = items[idx]
                card = {"title": item.get("title", ""), "reason": item.get("reason", "")}
                if candidates:
                    card.update(candidates[0])
                    if len(candidates) > 1:
                        card["backup_video_id"] = candidates[1]["video_id"]
                results[idx] = card

    return [r for r in results if r]


def build_recommendations(video_id: str, transcript: str, extra_context: str = "", lang: str = "tr") -> list:
    material = get_full_context_material(video_id, transcript)
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # IŞIK HIZI bağlam: kanal adı, açıklama ve etiketler zaten metadata çekilirken
    # (EKSTRA ağ isteği olmadan) geliyor. Bunlar genelde videonun GERÇEKTE ne
    # olduğunu (örn. "Transformers x Drift tribute AMV" gibi bir tribute/edit
    # kanalı olduğunu) web aramasından daha hızlı ve net ortaya koyar. Web araması
    # SADECE açıklama/etiket yetersizse (kısa/boşsa) devreye girer -> gereksiz
    # ağ isteği yapılmaz, akış yavaşlamaz.
    meta = get_video_metadata(video_url)
    video_title = meta.get("title") or get_video_title(video_url)
    description = meta.get("description") or ""
    tags = meta.get("tags") or []
    channel = meta.get("channel") or ""
    metadata_context = format_metadata_context(meta)

    content_type = detect_content_type(meta)  # "music" | "fan_edit" | "info"

    web_context = ""
    # Açıklama/etiket zaten yeterli bağlam veriyorsa web aramasına GEREK YOK (hız).
    needs_web_search = len(description) < 40 and not tags
    if needs_web_search and video_title:
        snippet = quick_web_search(video_title)
        if snippet:
            web_context = f"\n\nİnternet araştırması ('{video_title}' hakkında, videonun GERÇEKTE ne olduğunu anlamak için): {snippet}"

    content_type_instruction = {
        "music": (
            "Bu içerik bir ŞARKI/MÜZİK PARÇASI. Önerilerin de BENZER ŞARKILAR olsun (aynı sanatçı/tür/"
            "anime-film-oyun OST'i/benzer tema/benzer ruh hali gibi) — bilgilendirici/eğitim/analiz videosu önerme."
        ),
        "fan_edit": (
            "Bu içerik bir AMV/MV/EDIT/TRIBUTE videosu — yani bir eserin (anime/dizi/film/oyun) görüntüleri "
            "üzerine bir ŞARKI eşlenerek yapılmış hayran kurgusu (fan edit). YouTube bunu 'Film & Animation' "
            "gibi yanlış bir kategoriye koymuş olabilir ama içerik ÖZÜNDE MÜZİK/KURGU eksenlidir. "
            "Önerilerin de BENZER EDIT/AMV/MÜZİK videoları olsun (aynı eserden başka edit'ler, aynı şarkı "
            "kullanılan başka edit'ler, benzer temalı AMV'ler). KESİNLİKLE karakter analizi, lore anlatımı, "
            "inceleme/yorum (analysis/review/lore/explained) videosu ÖNERME — bunlar bu tür bir video için "
            "alakasızdır."
        ),
        "info": (
            "Bu içerik bir BİLGİLENDİRME/EĞİTİM videosu. Önerilerin de BENZER KONULU bilgilendirme/eğitim "
            "videoları olsun — şarkı/müzik/AMV/edit önerme."
        ),
    }[content_type]

    prompt = f"""Bu video içeriğine göre 5 farklı, gerçekten YouTube'da bulunabilecek video KONUSU/başlık fikri öner.
Öneriler somut ve YouTube'da aranabilir bir video başlığı/konusu şeklinde olsun (uydurma link değil, sadece konu
öner). Öneriler MUTLAKA aşağıda verilen videonun GERÇEK içeriğine ve kimliğine dayansın.

ÇOK ÖNEMLİ (arama başarısı için): Öneriler bu videodaki uydurma/aşırı spesifik detaylara (örn. belirli bir hasar
sayısı, belirli bir eşya kombinasyonu, tek bir maçtaki an) DEĞİL, gerçek içerik üreticilerinin GERÇEKTEN kullandığı
DOĞAL ve GENEL başlık kalıplarına dayansın (örn. "[Konu/Karakter] Rehberi", "[Konu] En İyi Build 2026",
"[Konu] Nasıl Oynanır", "[Konu] Montaj/Highlights", "[Sanatçı] - [Şarkı]" gibi). Uydurma bir sayı veya çok dar bir
detay içeren başlık üretme -- bu, YouTube'da gerçek bir video bulma ihtimalini neredeyse sıfıra indirir.

=== VİDEONUN GERÇEK KİMLİĞİ (BUNA GÜVEN, başlıktan/transkriptten DAHA ÖNCELİKLİ) ===
Video başlığı: {video_title or "(bilinmiyor)"}
{metadata_context if metadata_context else "(kanal adı/açıklama/etiket bilgisi alınamadı)"}
{web_context}
=== KİMLİK BİLGİSİ SONU ===

İÇERİK TÜRÜ: {content_type_instruction}

KURAL: Yukarıdaki kanal adı/açıklama/etiket bilgisi mevcutsa, video hakkındaki kararını SADECE başlığa göre değil
ÖNCELİKLE bu bilgiye göre ver. Video başlığı/transkripti tek başına yanıltıcı olabilir. Örnekler:
- Bir şarkı/anime/dizi adı günlük bir kelimeymiş gibi görünebilir (örn. "Treachery" bir anime OST'i olabilir).
- Bir video, bir karakter/tema adını taşıyan bir TRIBUTE/EDIT/AMV videosu olabilir ama o isim başka bir
  ünlü esere de ait olabilir (örn. "Transformers - Drift" karakteri tribute'ü, "Tokyo Drift" filmiyle
  KARIŞTIRILMAMALI — bunlar alakasız şeyler).
- "Arcane" gibi bir esere yapılan bir müzik/edit videosuna, o esere dair "karakter analizi/lore" videoları
  ÖNERME; bunun yerine benzer müzik/edit videoları öner.
Video gerçekte neyse öneriler de o bağlamda olsun — kelimenin gündelik anlamına veya başka ünlü bir esere
yüzeysel isim benzerliğine göre alakasız öneri üretme.

Video içeriği (tamamı):
{material}

{extra_context}

YUKARIDAKİ VİDEO İÇERİĞİNE GÖRE (başka hiçbir konudan değil): SADECE şu formatta geçerli bir JSON array döndür,
başka hiçbir açıklama/markdown/metin ekleme (title/reason alanları hariç her şey İngilizce anahtar kelime olsun,
ama title ve reason içerikleri {CODE_TO_LANG_NAME.get((lang or 'tr').lower(), 'turkish')} dilinde olsun). TAM OLARAK
5 öğe olsun:
[{{"title": "...", "reason": "..."}}, {{"title": "...", "reason": "..."}}, {{"title": "...", "reason": "..."}}, {{"title": "...", "reason": "..."}}, {{"title": "...", "reason": "..."}}]"""

    system_prompt = f"Sen bir içerik öneri asistanısın. Sadece istenen JSON formatında yanıt ver. {lang_instruction(lang)}"
    raw = _chat_completion(system_prompt, prompt, max_tokens=800, temperature=0.8, feature="recommendations")
    items = parse_recommendations_json(raw)[:5]
    if not items:
        # Gözlem: OmniRoute'un bağlam sıkıştırma ("compression") aşaması, tekrar
        # eden içerik (örn. şarkı sözleri) barındıran uzun promptlarda ARA SIRA
        # isteği TAMAMEN ALAKASIZ bir bağlamla (örn. programlama eğitim video
        # başlıkları) karıştırıyor — hem OmniRoute'un göreve özel "recommendations"
        # anahtarında hem de varsayılan anahtarda aynı şekilde gözlemlendi, yani
        # anahtara özel bir ayar değil, sıkıştırma katmanının kendisiyle ilgili.
        # Bu yüzden ikinci denemede OmniRoute'u TAMAMEN ATLAYIP doğrudan Groq/
        # OpenRouter'a (bu sıkıştırma katmanından geçmeyen sağlayıcılar) düşülüyor.
        print("  ⚠️ Öneriler boş/uyumsuz döndü (OmniRoute sıkıştırma sorunu olabilir), OmniRoute atlanıp Groq/OpenRouter ile tekrar deneniyor")
        raw = _chat_completion(system_prompt, prompt, max_tokens=800, temperature=0.8, skip_providers={"omniroute"})
        items = parse_recommendations_json(raw)[:5]

    # 5 video aramasını SIRAYLA değil PARALEL yapıyoruz -> önceden 5x arama süresi
    # kadar (10-20sn) bekleniyordu, artık hepsi aynı anda başlıyor (~3-5sn).
    results = [None] * len(items)

    def _search_one(idx_item):
        idx, item = idx_item
        candidates = ytdlp_search_candidates(item["title"], want=2)
        return idx, candidates

    if items:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(items))) as executor:
            for idx, candidates in executor.map(_search_one, enumerate(items)):
                item = items[idx]
                card = {"title": item["title"], "reason": item["reason"]}
                if candidates:
                    card.update(candidates[0])
                    if len(candidates) > 1:
                        card["backup_video_id"] = candidates[1]["video_id"]
                results[idx] = card

    enriched = [r for r in results if r]
    return enriched


# ==================== API ====================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "groq_configured": bool(GROQ_API_KEY),
        "ytdlp_available": check_ytdlp_available(),
        "ffmpeg_available": check_ffmpeg_available(),
    })


@app.route("/api/prepare-status", methods=["GET"])
def api_prepare_status():
    """
    Frontend /api/prepare çalışırken bunu ~1 saniyede bir "poll" eder; hangi
    adımda olunduğunu (altyazı aranıyor / yt-dlp altyazı / ses indirme-Whisper)
    gösterip 30 saniye boyunca donuk bir spinner yerine gerçek ilerleme
    hissi verir. Ek işlem yapmaz, sadece PREPARE_STATUS'u okur.
    """
    video_id = request.args.get("video_id", "")
    status = PREPARE_STATUS.get(video_id, "starting")
    return jsonify({"video_id": video_id, "status": status})


@app.route("/api/prepare", methods=["POST"])
def api_prepare():
    """
    HIZ + RATE-LİMİT İÇİN KRİTİK: Video açılır açılmaz frontend TEK SEFERLİK
    bu endpoint'i çağırır. Burada:
      1) Transkript + metadata çıkarılıp cache'lenir (5 sekme tekrar çıkarmaz)
      2) Özet+Analiz+Bölümler+Öneri başlıkları TEK bir AI çağrısında üretilir
         (4 ayrı çağrı yerine -> hem hız hem hız-limiti riski için kritik)
      3) Öneri başlıkları için gerçek video eşleştirmesi (non-LLM, paralel) yapılır
    Sonuç video_id+dil bazında cache'lenir; sekmeler bu cache'i okuyunca ek
    bekleme olmadan anında görünür. Aynı dile tekrar dönülürse de anında gelir.
    """
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    lang = data.get("lang", "tr")
    if not url:
        return jsonify({"error": "url gerekli"}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Geçersiz YouTube URL"}), 400

    metadata_executor = None
    metadata_future = None
    if video_id not in METADATA_CACHE:
        metadata_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        metadata_future = metadata_executor.submit(get_video_metadata, url)

    transcript = get_transcript_smart(url, video_id)

    if metadata_future:
        try:
            metadata_future.result(timeout=15)
        except Exception:
            pass
        metadata_executor.shutdown(wait=False)

    if not transcript:
        return jsonify({
            "error": "Transkript bulunamadı (altyazı yok ve ses indirilemedi).",
            "video_id": video_id,
            "ready": False,
        }), 404

    # Uzun videolarda parça-notu çıkarımını burada tetikleyip cache'e yaz.
    get_full_context_material(video_id, transcript)

    # Bu video+dil kombinasyonu daha önce hazırlanmışsa (örn. daha önce
    # ziyaret edilmiş bir dile geri dönüldüyse) TEKRAR AI ÇAĞRISI YAPMA.
    already_ready = (
        all((video_id, lang, feat) in FEATURE_CACHE for feat in ("summarize", "analyze", "chapters"))
        and ((video_id, lang, "recommendations") in FEATURE_CACHE or (video_id, lang) in RAW_RECOMMENDATIONS_CACHE)
    )
    if already_ready:
        # Icerik dogrudan buraya eklenir -- frontend ayrica /api/summarize vb.
        # cagirip bosuna bir "yukleniyor" yanip-sonmesi yaratmasin, hazir olan
        # her sey TEK cevapta gelsin.
        return jsonify({
            "video_id": video_id, "ready": True, "length": len(transcript), "cached": True,
            "summary": FEATURE_CACHE.get((video_id, lang, "summarize")),
            "analysis": FEATURE_CACHE.get((video_id, lang, "analyze")),
            "chapters": FEATURE_CACHE.get((video_id, lang, "chapters")),
        })

    meta = METADATA_CACHE.get(video_id, {})
    # Transkript bulundu (PREPARE_STATUS zaten "done") ama asil AI uretimi
    # (ozet/analiz/bolum/oneri TEK cagrida) HENUZ basliyor -- bu asama bazen
    # Groq'un dakikalik token limitine takilip yavas OpenRouter yedegine
    # dusebiliyor (30sn-1dk surebilir). Ayri bir durum olmadan frontend hala
    # "Hazir, sonuclar getiriliyor..." gosterip kullaniciyi yanlis bilgilendiriyordu.
    PREPARE_STATUS[video_id] = "generating"
    try:
        # Bolumler icin GERCEK zaman damgali uretim (generate_real_timestamped_chapters),
        # ana ozet/analiz/oneri cagrisiyla PARALEL calistirilir -- ek bekleme
        # SIFIR (ikisi ayni anda basliyor). AssemblyAI'nin gercek-zamanli
        # bolumleri > bu yontem > LLM'in TEK cagridaki tahmini (en son care).
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as prep_executor:
            combined_future = prep_executor.submit(generate_all_features_combined, video_id, transcript, meta, lang)
            chapters_future = prep_executor.submit(generate_real_timestamped_chapters, video_id, lang)
            combined = combined_future.result()
            try:
                real_timestamped_chapters = chapters_future.result(timeout=25)
            except Exception:
                real_timestamped_chapters = None

        FEATURE_CACHE[(video_id, lang, "summarize")] = _coerce_text(combined.get("summary", ""))
        FEATURE_CACHE[(video_id, lang, "analyze")] = _coerce_text(combined.get("analysis", ""))
        # Oncelik: AssemblyAI'nin gercek zaman damgali bolumleri (varsa) >
        # youtube-transcript-api'nin gercek zaman verisinden hesaplanan bolumler >
        # LLM'in TEK cagridaki tahmini (son care, artik "Bolum 1" gibi zaman
        # damgasiz satirlar ensure_chapter_linebreaks tarafindan eleniyor).
        real_chapters = ASSEMBLYAI_CHAPTERS_CACHE.get(video_id) or real_timestamped_chapters
        FEATURE_CACHE[(video_id, lang, "chapters")] = ensure_chapter_linebreaks(
            real_chapters if real_chapters else combined.get("chapters", "")
        )
        # HIZ: video eşleştirme (yt-dlp araması) burada YAPILMIYOR — bu adım tek
        # başına 3-8sn sürüp diğer 4 sekmeyi (özet/analiz/bölüm/transkript) gereksiz
        # yere bekletiyordu. Ham başlıklar burada saklanır; gerçek arama, frontend
        # zaten AYNI ANDA (paralel) çağırdığı /api/recommendations isteğinde yapılır.
        RAW_RECOMMENDATIONS_CACHE[(video_id, lang)] = combined.get("recommendations", [])
        for feat in ("summarize", "analyze", "chapters"):
            CHAT_HISTORY_CACHE.setdefault((video_id, lang, feat), [])
    except Exception as e:
        # Birleşik üretim başarısız olursa sorun değil: sekmeler kendi
        # endpoint'lerine düşüp TEK TEK üretmeyi dener (daha yavaş ama çalışır).
        print(f"  ⚠️ Birleşik üretim başarısız, sekmeler tek tek üretecek: {e}")

    return jsonify({
        "video_id": video_id, "ready": True, "length": len(transcript),
        # Bu 3'u zaten yukarida (basarili olduysa) uretilip cache'lendi --
        # frontend'in ayri bir istekle + loading yanip-sonmesiyle tekrar
        # cekmesine gerek yok, dogrudan buradan gelsin.
        "summary": FEATURE_CACHE.get((video_id, lang, "summarize")),
        "analysis": FEATURE_CACHE.get((video_id, lang, "analyze")),
        "chapters": FEATURE_CACHE.get((video_id, lang, "chapters")),
    })


def format_metadata_context(meta: dict) -> str:
    """Kanal adı/açıklama/etiket bilgisini prompt'a eklenecek kısa bir bağlam metnine çevirir."""
    if not meta:
        return ""
    parts = []
    channel = meta.get("channel") or ""
    description = meta.get("description") or ""
    tags = meta.get("tags") or []
    if channel:
        parts.append(f"Kanal adı: {channel}")
    if description:
        parts.append(f"Video açıklaması: {description}")
    if tags:
        parts.append(f"Etiketler: {', '.join(tags)}")
    return "\n".join(parts)


# AMV/MV/edit/tribute videoları YouTube tarafından genelde "Film & Animation" gibi
# yanlış kategoriye konur (is_music=False çıkar) ama içerik ÖZÜNDE müzik/kurgu
# eksenlidir. Başlık/açıklama/etikette bu kelimeler geçiyorsa "fan_edit" say.
FAN_EDIT_KEYWORDS = [
    "amv", "mv", "gmv", "cmv", "edit", "tribute", "fanmade", "fan made",
    "music video", "müzik videosu", "fan edit", "kurgu",
]


def detect_content_type(meta: dict) -> str:
    """
    Anahtar kelime tabanlı basit içerik türü tahmini:
      'music'    -> gerçek bir şarkı/müzik yüklemesi (YouTube kategorisi 'Music')
      'fan_edit' -> AMV/MV/edit/tribute (müzik eşliğinde görsel kurgu)
      'info'     -> bilgilendirme/eğitim/analiz videosu
    """
    if meta.get("is_music"):
        return "music"

    title = (meta.get("title") or "").lower()
    description = (meta.get("description") or "").lower()
    tags = " ".join(meta.get("tags") or []).lower()
    combined = f" {title} {description} {tags} "

    for kw in FAN_EDIT_KEYWORDS:
        if re.search(rf"(?<![a-zçğıöşü]){re.escape(kw)}(?![a-zçğıöşü])", combined):
            return "fan_edit"

    return "info"


def _transcript_and_metadata_or_404(url):
    """
    IŞIK HIZI ilkesi TÜM bölümler için: transkript ve video metadata'sı (kanal
    adı/açıklama/etiket) AYNI ANDA (paralel) çekilir. Metadata, transkript
    beklenirken zaten "boşta" geçen sürede çekildiği için ek bir bekleme
    YARATMAZ, ama her bölümün (özet/analiz/bölüm/öneri) videonun kanal
    adı/açıklamasına bakarak daha isabetli sonuç üretmesini sağlar (örn. bir
    "tribute/edit/AMV" kanalı olduğunu anlayıp başlıktaki isim benzerliğine
    kanmama gibi).
    """
    video_id = extract_video_id(url)
    if not video_id:
        return None, None, (jsonify({"error": "Geçersiz YouTube URL"}), 400)

    metadata_executor = None
    metadata_future = None
    if video_id not in METADATA_CACHE:
        metadata_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        metadata_future = metadata_executor.submit(get_video_metadata, url)

    transcript = get_transcript_smart(url, video_id)

    if metadata_future:
        try:
            metadata_future.result(timeout=15)
        except Exception:
            pass
        metadata_executor.shutdown(wait=False)

    if not transcript:
        return None, None, (jsonify({
            "error": "Transkript bulunamadı (altyazı yok ve ses indirilemedi).",
            "video_id": video_id
        }), 404)

    meta = METADATA_CACHE.get(video_id, {})
    return (video_id, transcript), meta, None


def detect_transcript_language(video_id: str, text: str) -> str:
    """
    Transkriptin konusuldugu ORIJINAL dili hizlica algilar (AI cagrisi YOK,
    yerel/istatistiksel bir kutuphane kullanir -- ~1ms). Video basina
    cache'lenir. "zh-cn"/"zh-tw" gibi bolge etiketli kodlari LANGUAGE_OPTIONS
    ile eslesmesi icin "zh" gibi taban koda indirger.
    """
    if video_id in TRANSCRIPT_LANG_CACHE:
        return TRANSCRIPT_LANG_CACHE[video_id]
    try:
        code = _langdetect_detect((text or "")[:2000]).split("-")[0].lower()
    except Exception:
        code = "en"
    TRANSCRIPT_LANG_CACHE[video_id] = code
    return code


def _transcript_or_404(url):
    video_id = extract_video_id(url)
    if not video_id:
        return None, (jsonify({"error": "Geçersiz YouTube URL"}), 400)
    transcript = get_transcript_smart(url, video_id)
    if not transcript:
        return None, (jsonify({
            "error": "Transkript bulunamadı (altyazı yok ve ses indirilemedi).",
            "video_id": video_id
        }), 404)
    return (video_id, transcript), None


_TRANSLATION_START = "===CEVIRI_BASLA==="
_TRANSLATION_END = "===CEVIRI_BITTI==="


def _extract_delimited_translation(raw: str) -> str:
    """
    Bazi zayif/yedek modeller (gozlemlendi: OpenRouter ucretsiz yedek) 'dusunme
    surecini' cikti oncesine sizdirabiliyor (orn. "Here's a thinking process:
    1. Analyze..."). Modelden ceviriyi ozel sinirlayicilar arasina koymasini
    istiyoruz, boylece hangi model/saglayici cevap verirse versin (sizinti
    olsa bile) SADECE gercek ceviriyi cikarabiliyoruz.
    """
    start_idx = raw.find(_TRANSLATION_START)
    end_idx = raw.find(_TRANSLATION_END)
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return raw[start_idx + len(_TRANSLATION_START):end_idx].strip()
    # Sinirlayicilar yoksa (model onlari da atladiysa) oldugu gibi don --
    # en azindan bos donmez, nadir durumda sizinti kalabilir ama veri kaybolmaz.
    return raw.strip()


# Ceviri icin cok daha kucuk parca boyutu -- genel CHUNK_CHARS (45000) ile tek
# seferde cevrilmeye calisildiginda model (feature="chat") talimati yok sayip
# metni OZETLEDI (12305 karakterlik transkript -> 180 karakterlik ozet cikti,
# gercek olayda gozlemlendi). Kucuk parcalarla model "ozetleyecek yer" bulamiyor.
TRANSLATE_CHUNK_CHARS = 2000


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_into_chunks(text: str, max_chars: int) -> list:
    """
    Metni max_chars'i asmayan parcalara boler. Once satir sinirlarindan
    dener; bircok transkript (orn. altyazidan degil, konusma metninden
    gelen) HIC newline icermeyebilir -- bu durumda tek "satir" tum metin
    kadar uzun kalir ve hicbir bolme olmaz (gercek olayda gozlemlendi:
    0 newline'li 12305 karakterlik metin, tek parca olarak kaldi ve model
    bunu ozetledi). Bu yuzden hala max_chars'i asan her parca, cumle
    sinirlarindan (nokta/soru/unlem + bosluk) tekrar bolunur.
    """
    def _pack(pieces, sep):
        out, cur, cur_len = [], [], 0
        for p in pieces:
            if cur_len + len(p) > max_chars and cur:
                out.append(sep.join(cur))
                cur, cur_len = [], 0
            cur.append(p)
            cur_len += len(p) + len(sep)
        if cur:
            out.append(sep.join(cur))
        return out

    line_chunks = _pack(text.split("\n"), "\n")

    chunks = []
    for lc in line_chunks:
        if len(lc) <= max_chars:
            chunks.append(lc)
            continue
        sentences = _SENTENCE_SPLIT_RE.split(lc)
        sentence_chunks = _pack(sentences, " ")
        for sc in sentence_chunks:
            if len(sc) <= max_chars:
                chunks.append(sc)
            else:
                # Tek bir "cumle" bile hala cok uzunsa (noktalama yoksa),
                # son care olarak sabit boyutta sert bolme yap.
                for i in range(0, len(sc), max_chars):
                    chunks.append(sc[i:i + max_chars])
    return chunks


def _build_translate_prompt(target_lang: str, strict: bool) -> str:
    name = CODE_TO_LANG_NAME.get(target_lang.lower().strip(), target_lang)
    base = (
        f"Sen bir profesyonel çeviri asistanısın. Verilen metni {name.capitalize()} diline "
        "ÇEVİR. Özetleme, kısaltma, birleştirme, yorum ekleme YAPMA -- metindeki HER cümleyi "
        "ayrı ayrı, birebir çevir. Çıktının uzunluğu kaynak metinle orantılı olmalı "
        "(kaynaktaki cümle sayısı kadar çevrilmiş cümle olmalı). "
        f"Çeviriyi TAM OLARAK '{_TRANSLATION_START}' ile başlat ve "
        f"'{_TRANSLATION_END}' ile bitir; bu iki işaretin dışına HİÇBİR ŞEY yazma "
        "(düşünme süreci, açıklama, giriş cümlesi YASAK)."
    )
    if strict:
        base += (
            " UYARI: Önceki denemede metni ÖZETLEDİN, bu YASAK. Bu kez metnin TAMAMINI, "
            "hiçbir cümleyi atlamadan, kısaltmadan çevir."
        )
    return base


def _translate_chunk(chunk: str, target_lang: str) -> str:
    """
    Tek bir parcayi hedef dile cevirir. Hem translate_transcript_text (tam
    metni bekleyip tek seferde donen eski/basit yol) hem de streaming
    endpoint'i (/api/transcript/translate/stream -- her parca bitince aninda
    frontend'e SSE ile akitir) BU fonksiyonu paylasir, mantik tekrari yok.
    """
    # max_tokens=1500 (TRANSLATE_CHUNK_CHARS=2000lik bir parca icin bolca yeterli,
    # cevrilmis metin nadiren 2500 karakteri/~800 token'i asar) KASITLI KUCUK:
    # Groq, TPM (dakika basi token) limitini GERCEK kullanima gore degil, max_tokens
    # ile TALEP EDILEN degere gore hesapliyor -- 4000 ile her paralel istek ~4700
    # token "rezerve ediyordu" (8000 TPM'in cogu), bu da paralel ceviri parcalarinin
    # cogunun 429 alip yavas OpenRouter'a dusmesine yol aciyordu (olcumle gozlemlendi).
    raw = _chat_completion(_build_translate_prompt(target_lang, False), chunk, max_tokens=1500, temperature=0.3)  # feature=None kasitli:
    # OmniRoute'un uzun/tekrarli promptlarda bozuk/alakasiz icerik dondurdugu bilinen bir sorun
    # (bkz. _chat_completion yorumu) -- ceviri tam bu senaryoya giriyor, gozlemlendi (gercekte)
    # tamamen alakasiz bir metin uretti. feature="chat" OmniRoute'u basa aldigi icin BUNU KULLANMA;
    # varsayilan siralama (Groq/OpenRouter once) daha guvenilir.
    result = _extract_delimited_translation(raw)
    # Cevrilmis metin, kaynagin %45'inden kisa cikarsa muhtemelen ozetlenmis --
    # bir kez daha, daha sert bir uyariyla dene.
    if len(result) < len(chunk) * 0.45:
        raw_retry = _chat_completion(_build_translate_prompt(target_lang, True), chunk, max_tokens=1500, temperature=0.2, skip_providers={"omniroute"})
        result_retry = _extract_delimited_translation(raw_retry)
        if len(result_retry) > len(result):
            result = result_retry
    # Iki denemeden sonra HALA neredeyse bos donduyse (gozlemlendi: saglayicilar
    # asiri yuk/kota altindayken bos/gecersiz cevap verebiliyor), cevrilmemis
    # orijinali kullan -- bilgi SESSIZCE kaybolmasin, kullaniciya bos bir bosluk
    # yerine en azindan okunabilir (kaynak dilde) metin gitsin.
    if len(result) < len(chunk) * 0.15:
        return chunk
    return result


def translate_transcript_text(text: str, target_lang: str) -> str:
    """
    Transkripti hedef dile CEVIRIR (ozetlemez/kisaltmaz, sadece dil cevirisi).
    Her zaman TRANSLATE_CHUNK_CHARS boyutunda kucuk parcalara bolup her parcayi
    PARALEL cevirir -- buyuk tek blok modelin metni ozetlemesine yol aciyordu.
    Tum metni TEK SEFERDE isteyen cagiranlar icindir (streaming olmayan yol).
    """
    chunks = _split_into_chunks(text, TRANSLATE_CHUNK_CHARS)
    results = [None] * len(chunks)
    max_workers = min(5, len(chunks))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, translated in executor.map(lambda ic: (ic[0], _translate_chunk(ic[1], target_lang)), enumerate(chunks)):
            results[idx] = translated
    return "\n".join(results)


@app.route("/api/transcript/translate", methods=["POST"])
def api_transcript_translate():
    """Transkripti (zaten cikarilmis/cache'lenmis olani) hedef dile cevirir, cache'ler."""
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    target_lang = data.get("lang", "tr")
    if not url:
        return jsonify({"error": "url gerekli"}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Geçersiz YouTube URL"}), 400

    cache_key = (video_id, target_lang)
    if cache_key in TRANSCRIPT_TRANSLATION_CACHE:
        return jsonify({"video_id": video_id, "translated_transcript": TRANSCRIPT_TRANSLATION_CACHE[cache_key]})

    result, err = _transcript_or_404(url)
    if err:
        return err
    video_id, transcript = result

    try:
        translated = translate_transcript_text(transcript, target_lang)
        TRANSCRIPT_TRANSLATION_CACHE[cache_key] = translated
        return jsonify({"video_id": video_id, "translated_transcript": translated})
    except Exception as e:
        return _handle_groq_error(e, video_id)


@app.route("/api/transcript/translate/stream", methods=["POST"])
def api_transcript_translate_stream():
    """
    /api/transcript/translate ile AYNI ceviriyi yapar, ama SSE (Server-Sent
    Events) ile her parca bitigi an akitir -- kullanici TUM ceviri (68s'e kadar
    surebilir) bitmeden ilk paragraflari okumaya baslar. Dogruluk/bicimlendirme
    AYNEN korunur (ozetleme/kirpma YOK); sadece TESLIMAT kademeli.
    """
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    target_lang = data.get("lang", "tr")
    if not url:
        return jsonify({"error": "url gerekli"}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Geçersiz YouTube URL"}), 400

    cache_key = (video_id, target_lang)

    def generate():
        # Zaten cache'de tam ceviri varsa, tek parca gibi aninda akit (bekleme yok).
        if cache_key in TRANSCRIPT_TRANSLATION_CACHE:
            yield f"data: {json.dumps({'chunk_id': 0, 'total': 1, 'text': TRANSCRIPT_TRANSLATION_CACHE[cache_key]})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
            return

        result, err = _transcript_or_404(url)
        if err:
            yield f"data: {json.dumps({'error': 'Transkript bulunamadı.'})}\n\n"
            return
        _, transcript = result

        chunks = _split_into_chunks(transcript, TRANSLATE_CHUNK_CHARS)
        max_workers = min(5, len(chunks))
        results = [None] * len(chunks)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_idx = {executor.submit(_translate_chunk, chunk, target_lang): idx for idx, chunk in enumerate(chunks)}
                for future in concurrent.futures.as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        translated = future.result()
                    except Exception as e:
                        translated = f"[Çeviri hatası: {e}]"
                    results[idx] = translated
                    yield f"data: {json.dumps({'chunk_id': idx, 'total': len(chunks), 'text': translated})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        TRANSCRIPT_TRANSLATION_CACHE[cache_key] = "\n".join(results)
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/transcript", methods=["POST"])
def api_transcript():
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    lang = data.get("lang", "tr")
    if not url:
        return jsonify({"error": "url gerekli"}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Gecersiz YouTube URL"}), 400

    meta = get_video_metadata(url)
    is_music = bool(meta.get("is_music"))

    # Muzik videolarinda, altyazi/caption zaman damgalari mevcutsa transkript
    # satir satir [MM:SS] soz formatinda doner (line_mode=True); frontend bu
    # durumda zaman damgasini kopyalanamaz, sozu kopyalanabilir span olarak gosterir.
    line_mode = False
    display_text = None
    if is_music:
        try:
            items = _get_transcript_items_with_timestamps(video_id)
        except Exception:
            items = []
        lines = []
        for start, text in items:
            text = (text or "").replace("\n", " ").strip()
            if not text:
                continue
            start = int(start)
            mins, secs = divmod(start, 60)
            lines.append(f"[{mins:02d}:{secs:02d}] {text}")
        if lines:
            labeled = add_song_structure_labels("\n".join(lines))
            display_text = f"{get_song_note(lang)}\n\n" + labeled
            line_mode = True

    if display_text is None:
        result, err = _transcript_or_404(url)
        if err:
            return err
        video_id, transcript = result
        display_text = transcript
        if is_music:
            display_text = f"{get_song_note(lang)}\n\n{transcript}"

    raw_for_lang = TRANSCRIPT_CACHE.get(video_id) or display_text
    detected_lang = detect_transcript_language(video_id, raw_for_lang)

    return jsonify({
        "video_id": video_id,
        "transcript": display_text,
        "length": len(display_text),
        "is_music": is_music,
        "line_mode": line_mode,
        "detected_lang": detected_lang,
    })


@app.route("/api/summarize", methods=["POST"])
def api_summarize():
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    lang = data.get("lang", "tr")
    if not url:
        return jsonify({"error": "url gerekli"}), 400

    video_id_quick = extract_video_id(url)
    if video_id_quick and (video_id_quick, lang, "summarize") in FEATURE_CACHE:
        return jsonify({"video_id": video_id_quick, "summary": FEATURE_CACHE[(video_id_quick, lang, "summarize")]})

    result, meta, err = _transcript_and_metadata_or_404(url)
    if err:
        return err
    video_id, transcript = result
    try:
        material = get_full_context_material(video_id, transcript)
        metadata_context = format_metadata_context(meta)
        summary = _chat_completion_on_topic(
            "Sen bir YouTube video özet asistanısın. Ana noktaları kısa ve öz maddeler halinde özetle. "
            "Elindeki bağlam videonun TAMAMINI kapsıyor; sadece başlangıcına değil, videonun sonuna kadar "
            "geçen tüm önemli konulara da yer ver. Video başlığı yanıltıcı olabilir (örn. bir tribute/edit/AMV "
            "videosu başka bir ünlü esere isim benzerliğiyle karıştırılabilir); varsa kanal adı/açıklama/etiket "
            f"bilgisini videonun GERÇEKTE ne olduğunu anlamak için kullan. {lang_instruction(lang)}",
            f"""Bu videonun içeriğini (tamamını) özetle:

{metadata_context}

Video içeriği:
{material}""",
            video_title=meta.get("title") or "",
            max_tokens=1200,
            feature="summarize",
        )
        FEATURE_CACHE[(video_id, lang, "summarize")] = summary
        CHAT_HISTORY_CACHE[(video_id, lang, "summarize")] = []
        return jsonify({"video_id": video_id, "summary": summary})
    except Exception as e:
        return _handle_groq_error(e, video_id)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    lang = data.get("lang", "tr")
    if not url:
        return jsonify({"error": "url gerekli"}), 400

    video_id_quick = extract_video_id(url)
    if video_id_quick and (video_id_quick, lang, "analyze") in FEATURE_CACHE:
        return jsonify({"video_id": video_id_quick, "analysis": FEATURE_CACHE[(video_id_quick, lang, "analyze")]})

    result, meta, err = _transcript_and_metadata_or_404(url)
    if err:
        return err
    video_id, transcript = result
    try:
        material = get_full_context_material(video_id, transcript)
        metadata_context = format_metadata_context(meta)
        analysis = _chat_completion_on_topic(
            "Sen bir içerik analiz asistanısın. Elindeki bağlam videonun TAMAMINI kapsıyor; "
            "analizini sadece videonun başında geçenlere değil, tamamına dayandır. Video başlığı yanıltıcı "
            "olabilir; varsa kanal adı/açıklama/etiket bilgisini videonun GERÇEKTE ne olduğunu anlamak için "
            f"kullan. {lang_instruction(lang)}",
            f"""Bu video içeriğini analiz et:

📌 ANA KONULAR (3-5 madde)
📋 ALT BAŞLIKLAR VE DETAYLAR
👥 HEDEF KİTLE
🔑 ANAHTAR KELİMELER

{metadata_context}

Video içeriği (tamamı):
{material}""",
            video_title=meta.get("title") or "",
            max_tokens=1500,
            feature="analyze",
        )
        FEATURE_CACHE[(video_id, lang, "analyze")] = analysis
        CHAT_HISTORY_CACHE[(video_id, lang, "analyze")] = []
        return jsonify({"video_id": video_id, "analysis": analysis})
    except Exception as e:
        return _handle_groq_error(e, video_id)


@app.route("/api/chapters", methods=["POST"])
def api_chapters():
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    lang = data.get("lang", "tr")
    if not url:
        return jsonify({"error": "url gerekli"}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Geçersiz YouTube URL"}), 400

    if (video_id, lang, "chapters") in FEATURE_CACHE:
        return jsonify({"video_id": video_id, "chapters": FEATURE_CACHE[(video_id, lang, "chapters")]})

    # IŞIK HIZI: metadata (kanal/açıklama/etiket) transkript/zaman damgası
    # işlenirken PARALEL çekiliyor, ek bekleme yaratmıyor.
    metadata_executor = None
    metadata_future = None
    if video_id not in METADATA_CACHE:
        metadata_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        metadata_future = metadata_executor.submit(get_video_metadata, url)

    try:
        formatted_text = None
        try:
            items = _get_transcript_items_with_timestamps(video_id)
            lines = []
            for start, text in items:  # TÜM cue'lar kullanılıyor, videonun sadece başı değil tamamı
                start = int(start)
                mins, secs = divmod(start, 60)
                lines.append(f"[{mins:02d}:{secs:02d}] {text.replace(chr(10), ' ').strip()}")
            formatted_text = "\n".join(lines) if lines else None
        except Exception:
            pass

        if not formatted_text:
            transcript = get_transcript_smart(url, video_id)
            if not transcript:
                if metadata_future:
                    metadata_executor.shutdown(wait=False)
                return jsonify({"error": "Transkript bulunamadı", "video_id": video_id}), 404
            formatted_text = transcript  # zaman damgası yoksa tam metin, aşağıda parçalanır

        if metadata_future:
            try:
                metadata_future.result(timeout=15)
            except Exception:
                pass
            metadata_executor.shutdown(wait=False)
        meta = METADATA_CACHE.get(video_id, {})
        metadata_context = format_metadata_context(meta)

        if len(formatted_text) <= MAX_DIRECT_CHARS:
            chapters = _chat_completion_on_topic(
                "Sen bir video bölümlendirme uzmanısın. Bölümlendirmeyi videonun TAMAMINI (baştan sona) "
                f"dikkate alarak yap. {lang_instruction(lang)}",
                f"""Bu video içeriğini (tamamını) 5-8 anlamlı bölüme ayır.
Her bölüm için: [MM:SS] Bölüm Başlığı - Kısa açıklama (zaman damgası yoksa sadece başlık-açıklama yaz).

{metadata_context}

İçerik:
{formatted_text}""",
                video_title=meta.get("title") or "",
                feature="chapters",
            )
        else:
            # Uzun video: TAMAMINI kapsamak için parçalara bölüp her parçadan gerçek
            # zaman damgalarıyla bölüm adayları çıkar, sonra sırayla birleştir.
            print(f"  ℹ️ Bölümlendirme için içerik uzun ({len(formatted_text)} karakter), parçalara bölünüyor...")
            lines_all = formatted_text.split("\n")
            line_chunks, cur, cur_len = [], [], 0
            for line in lines_all:
                if cur_len + len(line) > CHUNK_CHARS and cur:
                    line_chunks.append("\n".join(cur))
                    cur, cur_len = [], 0
                cur.append(line)
                cur_len += len(line)
            if cur:
                line_chunks.append("\n".join(cur))

            all_chapter_parts = []
            for idx, lc in enumerate(line_chunks, start=1):
                print(f"    -> Bölüm parçası {idx}/{len(line_chunks)} işleniyor...")
                part = _chat_completion(
                    f"Sen bir video bölümlendirme uzmanısın. {lang_instruction(lang)}",
                    f"""Aşağıda videonun {idx}. parçası (toplam {len(line_chunks)} parça) var, zaman damgalarıyla.
Bu parçada geçen 2-4 anlamlı bölümü şu formatta listele:
[MM:SS] Bölüm Başlığı - Kısa açıklama

İçerik:
{lc}""",
                    max_tokens=500, temperature=0.5,
                    feature="chapters",
                )
                all_chapter_parts.append(part.strip())
            chapters = "\n".join(all_chapter_parts)

        chapters = ensure_chapter_linebreaks(chapters)
        FEATURE_CACHE[(video_id, lang, "chapters")] = chapters
        CHAT_HISTORY_CACHE[(video_id, lang, "chapters")] = []
        return jsonify({"video_id": video_id, "chapters": chapters})
    except Exception as e:
        return _handle_groq_error(e, video_id)


@app.route("/api/recommendations", methods=["POST"])
def api_recommendations():
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    refine = data.get("refine", False)
    lang = data.get("lang", "tr")
    if not url:
        return jsonify({"error": "url gerekli"}), 400

    vid_guess = extract_video_id(url)
    if not refine and vid_guess and (vid_guess, lang, "recommendations") in FEATURE_CACHE:
        return jsonify({"video_id": vid_guess, "recommendations": FEATURE_CACHE[(vid_guess, lang, "recommendations")]})

    # /api/prepare zaten AI ile başlık/sebep üretmiş olabilir (RAW_RECOMMENDATIONS_CACHE).
    # Varsa TEKRAR AI çağrısı/transkript bekleme YAPMADAN sadece video eşleştirme (arama)
    # adımını burada tamamlıyoruz -> bu istek diğer sekmelerle zaten paralel çalışıyor,
    # üstelik artık kendi içinde de en hızlı yolu (AI çağrısı atlanır) izliyor.
    if not refine and vid_guess:
        pending_raw = RAW_RECOMMENDATIONS_CACHE.pop((vid_guess, lang), None)
        if pending_raw is not None:
            enriched = enrich_recommendation_items(pending_raw)
            FEATURE_CACHE[(vid_guess, lang, "recommendations")] = enriched
            CHAT_HISTORY_CACHE.setdefault((vid_guess, lang, "recommendations"), [])
            return jsonify({"video_id": vid_guess, "recommendations": enriched})

    # HIZ: video başlığı/türü bilgisini (metadata) transkript alma işlemiyle
    # AYNI ANDA çekmeye başlıyoruz. Önceden bu, transkript bittikten SONRA
    # ayrıca çekiliyordu (build_recommendations içinde) -> ekstra bekleme
    # demekti. Artık ikisi paralel yürüyor, sonuç zaten cache'e düşüyor.
    metadata_executor = None
    metadata_future = None
    if vid_guess and vid_guess not in METADATA_CACHE:
        metadata_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        metadata_future = metadata_executor.submit(get_video_metadata, url)

    result, err = _transcript_or_404(url)

    if metadata_future:
        try:
            metadata_future.result(timeout=15)  # cache'e yazması için bekle, ~15sn üstü nadir
        except Exception:
            pass
        metadata_executor.shutdown(wait=False)

    if err:
        return err
    video_id, transcript = result

    try:
        extra_context = ""
        if refine:
            history = CHAT_HISTORY_CACHE.get((video_id, lang, "recommendations"), [])
            if history:
                convo = "\n".join(f"{h['role']}: {h['content']}" for h in history[-6:])
                extra_context = f"\nKullanıcıyla önceki sohbet (bunu dikkate alarak farklı/uygun öneriler ver):\n{convo}"

        recs = build_recommendations(video_id, transcript, extra_context, lang=lang)
        FEATURE_CACHE[(video_id, lang, "recommendations")] = recs
        CHAT_HISTORY_CACHE.setdefault((video_id, lang, "recommendations"), [])
        return jsonify({"video_id": video_id, "recommendations": recs})
    except Exception as e:
        return _handle_groq_error(e, video_id)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """
    Bir özelliğin (summarize/analyze/chapters/recommendations) sonucu hakkında
    soru-cevap. Bağlam: videonun TAMAMINI kapsayan işlenmiş materyal (MATERIAL_CACHE)
    + ilgili özelliğin çıktısı. Kısaltılmış transkript DEĞİL, tüm video dikkate alınır.

    ÜCRETSİZ KULLANICI: video+özellik başına en fazla FREE_CHAT_MESSAGE_LIMIT mesaj.
    PREMIUM (frontend 'unlimited: true' gönderirse): sınır uygulanmaz.
    """
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    feature = data.get("feature")
    message = data.get("message", "").strip()
    unlimited = bool(data.get("unlimited"))
    lang = data.get("lang", "tr")

    if not url or not feature or not message:
        return jsonify({"error": "url, feature ve message gerekli"}), 400

    if feature not in FEATURE_LABELS:
        return jsonify({"error": "Geçersiz feature"}), 400

    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"error": "Geçersiz YouTube URL"}), 400

    transcript = TRANSCRIPT_CACHE.get(video_id, "")
    material = get_full_context_material(video_id, transcript) if transcript else ""
    feature_result = FEATURE_CACHE.get((video_id, lang, feature))
    if feature_result is None:
        return jsonify({"error": "Önce ilgili özelliği çalıştırın (örn. önce Özet oluşturun)."}), 400

    history = CHAT_HISTORY_CACHE.setdefault((video_id, lang, feature), [])
    used = sum(1 for h in history if h["role"] == "user")

    if not unlimited and used >= FREE_CHAT_MESSAGE_LIMIT:
        return jsonify({
            "limit_reached": True,
            "used": used,
            "limit": FREE_CHAT_MESSAGE_LIMIT,
            "reply": get_limit_message(lang, FREE_CHAT_MESSAGE_LIMIT),
        })

    if feature == "recommendations":
        feature_text = "\n".join(
            f"- {r['title']}" + (f" ({r.get('real_title')})" if r.get("real_title") else "") + f": {r['reason']}"
            for r in feature_result
        )
    else:
        feature_text = str(feature_result)

    label = FEATURE_LABELS[feature]
    system_prompt = f"""Sen bir YouTube video asistanısın. Kullanıcıyla bu videonun {label} kısmı hakkında sohbet ediyorsun.
Elindeki bilgiler videonun BAŞINDAN SONUNA KADAR TAMAMINI kapsar, sadece başlangıcını değil. {lang_instruction(lang)}

--- OLUŞTURULAN {label.upper()} ---
{feature_text}

--- VİDEO İÇERİĞİ (TAMAMI, gerekirse özetlenmiş notlar halinde) ---
{material}

Kurallar:
- Sorulara bu bilgilere dayanarak, kısa ve net cevap ver. Cevap verirken videonun sadece başındaki değil,
  ortasında/sonunda geçen bilgileri de göz önünde bulundur.
- Öneriler hakkında konuşuyorsan, kullanıcı bir videoyu beğendiğini söylerse ona benzer başka konu/video fikirleri öner.
- Elindeki bilgide olmayan bir şeyi soruyorsa, bilmediğini söyle, uydurma."""

    try:
        reply = _chat_completion(system_prompt, message, history=history, max_tokens=700, feature=feature)
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        # Sohbet geçmişi çok uzamasın diye son 20 mesajı tut
        if len(history) > 20:
            CHAT_HISTORY_CACHE[(video_id, lang, feature)] = history[-20:]
        new_used = used + 1
        return jsonify({
            "reply": reply,
            "used": new_used,
            "limit": FREE_CHAT_MESSAGE_LIMIT,
            "unlimited": unlimited,
        })
    except Exception as e:
        return _handle_groq_error(e, video_id)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    ytdlp_ok = check_ytdlp_available()
    ffmpeg_ok = check_ffmpeg_available()

    print("\n" + "=" * 70)
    print("🚀 YouTube Assistant Backend - GROQ + OPENROUTER YEDEKLEMELİ SÜRÜM")
    print("=" * 70)
    print(f"📡 Sunucu: http://127.0.0.1:{port}")
    print(f"✅ Groq (birincil): {'Yapılandırıldı (' + GROQ_API_KEY[:12] + '...)' if GROQ_API_KEY else '❌ BULUNAMADI'}")
    print(f"🔁 OpenRouter (yedek): {'Yapılandırıldı (' + OPENROUTER_API_KEY[:12] + '...)' if OPENROUTER_API_KEY else '⚪ Yok (isteğe bağlı, .env dosyasına eklenebilir)'}")
    print(f"🧠 Groq modelleri (sırayla denenir): {', '.join(GROQ_CHAT_MODELS)}")
    if OPENROUTER_API_KEY:
        print(f"🧠 OpenRouter modeli: {OPENROUTER_CHAT_MODEL}")
    print(f"🎤 Whisper (SADECE Groq'ta var): {GROQ_WHISPER_MODEL}")
    print(f"🎬 yt-dlp: {'✅ Yüklü' if ytdlp_ok else '❌ Bulunamadı'}")
    print(f"🎞️  ffmpeg: {'✅ Yüklü' if ffmpeg_ok else '❌ Bulunamadı'}")
    print("\n🔁 Yeni: Groq yoğun/başarısız olursa metin üretimi OTOMATİK OpenRouter'a geçer")
    print("🔒 Not: Tüm sohbet/transkript verisi sadece BELLEKTE (RAM) tutulur, diske/kalıcı depoya yazılmaz")
    print("💬 Her özellik için sohbet kutusu (/api/chat)")
    print(f"⭐ PREMIUM - Sohbet kutuları varsayılan {FREE_CHAT_MESSAGE_LIMIT} mesajla sınırlı, açılınca sınırsız")
    print("🎯 Şive/aksan fark etmeksizin tüm dillerde ses tanıma (Whisper, dil zorlanmıyor)")
    print("🔎 Öneriler için hızlı web araştırması (video başlığı yanıltıcıysa gerçek bağlamı bulur)")
    print("🚫 Embed edilemeyen ('video kullanılamıyor') videolar öneri aramasında elenir")
    print("🌐 Panelde dil seçici — tüm cevaplar (özet/analiz/bölüm/öneri/chat) seçilen dilde")
    print("🎵 Transkriptte 'bu bir şarkı' notu + şarkıya şarkı, bilgilendirmeye bilgilendirme önerisi")
    print("🎬 Öneri videoları paralel aranıyor + birincil+yedek video ile embed hatası azaltıldı")
    print("🎯 Kanal adı/açıklama/etiket bağlamı TÜM bölümlerde (ek ağ isteği olmadan, paralel) kullanılıyor")
    print("🚀 /api/prepare ile transkript video başına BİR KEZ çıkarılıp cache'lenir (5 sekme tekrar çıkarmaz)")
    print("⚡ whisper-large-v3-turbo + paralel parça işleme + daha kısa retry süresi")
    print("📼 Uzun videolarda ses otomatik parçalanıp TAMAMI transkribe ediliyor")
    print("🧩 Özet/Analiz/Bölümler/Öneriler/Sohbet videonun SADECE başını değil TAMAMINI dikkate alıyor")
    print("🔗 Yeni: Öneriler gerçek YouTube videolarıyla eşleştiriliyor")
    if not GROQ_API_KEY:
        print("\n⚠️  .env dosyasında GROQ_API_KEY bulunamadı veya boş!")
    print("=" * 70 + "\n")

    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)  # threaded=True: SSE streaming baglantisi (translate) acikken diger istekler (chat, prepare vb.) bloklanmasin
