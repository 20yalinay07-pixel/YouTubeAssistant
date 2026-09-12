"""
YouTube Assistant - Sistem Tepsisi (Tray) Baslatici

Bildirim alaninda (system tray) bir ikon gosterip hem OmniRoute'u hem
backend'i (Flask sunucusu, server.py) arka planda, HICBIR pencere acmadan
yonetir. Bu ikon uzerinden sunucuyu yeniden baslatabilir veya tamamen
kapatabilirsiniz (orn. kod degisikligi yaptiktan sonra).

NOT: "omniroute serve --daemon" dogrudan bir konsol/cmd penceresi icinden
cagrilirsa, arka plana gecerken zaman zaman KENDI konsolunu kapatirken
CAGIRANI da beraberinde kapatiyor (gozlemlenmis bir OmniRoute hatasi --
bu yuzden onceden ayri bir .bat dosyasindan calistiriliyordu, ama o da
gorunur bir cmd penceresi acip kapaniyormus gibi durdugu icin kafa
karistirdi). Buradan (pythonw.exe ile konsolu OLMAYAN bir surecten,
CREATE_NEW_PROCESS_GROUP ile izole bir surec grubunda) baslatilinca bu
sorun hic yasanmiyor -- ne bir pencere acilir ne de bir seyin kapandigi
hissi olusur. Backend, OmniRoute her nedense calismiyorsa zaten otomatik
olarak Groq/OpenRouter'a duser (bkz. server.py TEXT_PROVIDERS).
"""
import os
import socket
import subprocess
import sys
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
SERVER_PY = os.path.join(BASE_DIR, "server.py")
LOG_PATH = os.path.join(BASE_DIR, "tray_launcher.log")

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200

_log_lock = threading.Lock()


def log(msg: str):
    with _log_lock:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except Exception:
            pass


def _python_w() -> str:
    """server.py alt sureci icin ayni Python kurulumunun pythonw.exe'sini kullanir."""
    exe_dir = os.path.dirname(sys.executable)
    candidate = os.path.join(exe_dir, "pythonw.exe")
    return candidate if os.path.exists(candidate) else sys.executable


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def start_omniroute():
    from shutil import which
    if which("omniroute") is None:
        log("'omniroute' komutu bulunamadi, atlaniyor (Groq/OpenRouter yedekleri kullanilacak).")
        return
    if _port_open("127.0.0.1", 20128):
        log("OmniRoute zaten calisiyor (:20128), tekrar baslatilmadi.")
        return
    log("OmniRoute baslatiliyor (izole surec grubu, penceresiz)...")
    try:
        log_file = open(LOG_PATH, "a", encoding="utf-8")
        # omniroute, npm'in olusturdugu bir .cmd shim'i -- subprocess.Popen(["omniroute", ...])
        # shell=True OLMADAN bunu calistiramaz (WinError 2), cunku CreateProcess bir .cmd
        # dosyasini dogrudan yurutemez.
        subprocess.Popen(
            "omniroute serve --daemon --no-open",
            shell=True,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        )
    except Exception as e:
        log(f"OmniRoute baslatilamadi: {e}")


POT_SERVER_DIR = os.path.join(PROJECT_ROOT, "pot_server")


def start_pot_server():
    """
    yt-dlp'nin altyazi isteklerinde YouTube'un artik zorunlu tuttugu "PO Token"
    (Proof of Origin) uretmesini saglayan yerel HTTP sunucusu (bgutil-ytdlp-pot-
    provider, port 4416). Gercek testle dogrulandi: taze bir videoda hem
    Ingilizce hem Turkce altyazi 429 HIC ALINMADAN indi -- bugune kadarki tum
    denemeler icinde asil calisan tek ucretsiz cozum bu (digerleri sadece
    sistemin etrafini iyilestiriyordu, bu dogrudan PO Token duvarini asiyor).
    yt-dlp, bu sunucu 127.0.0.1:4416'da calisirken OTOMATIK olarak kullanir --
    kodumuzda (ytdlp_bypass.py) hicbir degisiklik gerekmiyor.
    """
    if not os.path.isdir(POT_SERVER_DIR):
        log("pot_server klasoru bulunamadi, PO Token sunucusu atlaniyor.")
        return
    if _port_open("127.0.0.1", 4416):
        log("PO Token sunucusu zaten calisiyor (:4416), tekrar baslatilmadi.")
        return
    log("PO Token sunucusu baslatiliyor (izole surec grubu, penceresiz)...")
    try:
        log_file = open(LOG_PATH, "a", encoding="utf-8")
        subprocess.Popen(
            ["node", "build/main.js"],
            cwd=POT_SERVER_DIR,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        )
    except Exception as e:
        log(f"PO Token sunucusu baslatilamadi: {e}")


class BackendManager:
    def __init__(self):
        self.proc = None
        self.should_run = True
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self.proc and self.proc.poll() is None:
                return
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUNBUFFERED"] = "1"  # print() ciktisi log dosyasina hemen yazilsin (aksi halde arabellege takilip kayboluyor gibi gorunuyor)
            log_file = open(LOG_PATH, "a", encoding="utf-8")
            log("Backend baslatiliyor (server.py)...")
            self.proc = subprocess.Popen(
                [_python_w(), SERVER_PY],
                cwd=BASE_DIR,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )

    def stop(self):
        with self._lock:
            if not self.proc:
                return
            log("Backend durduruluyor...")
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

    def restart(self):
        self.stop()
        time.sleep(0.5)
        self.start()

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def watch_loop(self):
        while True:
            time.sleep(2)
            if not self.should_run:
                continue
            with self._lock:
                dead = self.proc is not None and self.proc.poll() is not None
            if dead:
                log("Backend beklenmedik sekilde durdu, otomatik yeniden baslatiliyor...")
                self.start()


def load_icon_image():
    from PIL import Image
    for name in ("icon48.png", "icon128.png", "icon16.png"):
        path = os.path.join(PROJECT_ROOT, name)
        if os.path.exists(path):
            return Image.open(path)
    # Son care: duz mor kare (dosya bulunamazsa ikon yine de gorunsun)
    return Image.new("RGB", (48, 48), color=(102, 126, 234))


def main():
    import pystray
    from pystray import MenuItem as Item

    backend = BackendManager()

    def on_restart(icon, item):
        threading.Thread(target=backend.restart, daemon=True).start()

    def on_open_log(icon, item):
        try:
            os.startfile(LOG_PATH)
        except Exception:
            pass

    def on_quit(icon, item):
        backend.should_run = False
        backend.stop()
        log("Tray uygulamasi kapatildi.")
        icon.stop()

    def backend_status_text(item):
        return "Backend: Calisiyor (:8000)" if backend.is_running() else "Backend: Durdu"

    def omniroute_status_text(item):
        return "OmniRoute: Calisiyor (:20128)" if _port_open("127.0.0.1", 20128) else "OmniRoute: Calismiyor (Groq/OpenRouter kullanilacak)"

    menu = pystray.Menu(
        Item(backend_status_text, None, enabled=False),
        Item(omniroute_status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        Item("Sunucuyu Yeniden Baslat", on_restart),
        Item("Loglari Ac", on_open_log),
        pystray.Menu.SEPARATOR,
        Item("Kapat", on_quit),
    )

    icon = pystray.Icon("youtube_asistani", load_icon_image(), "YouTube Assistant", menu)

    def setup(icon):
        icon.visible = True
        start_omniroute()
        start_pot_server()
        backend.start()
        threading.Thread(target=backend.watch_loop, daemon=True).start()

    icon.run(setup=setup)


if __name__ == "__main__":
    log("=" * 60)
    log("Tray launcher baslatiliyor...")
    try:
        main()
    except Exception:
        import traceback
        log("FATAL HATA:\n" + traceback.format_exc())
