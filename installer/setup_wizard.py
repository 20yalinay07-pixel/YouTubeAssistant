"""
YouTube Assistant - Kurulum Sihirbazı

Hiçbir anahtar bu programın içine gömülü DEĞİL ve hiçbir yere gönderilmiyor --
sadece kullanıcının kendi girdiği anahtarlarla proje kök dizininde bir .env
dosyası oluşturuyor/güncelliyor, ardından isterse bağımlılıkları kurup arka
planı başlatıyor. Yayınlanacak .exe bu betiğin PyInstaller ile paketlenmiş hali
(bkz. build_exe.bat) -- kaynağı burada, herkes okuyup doğrulayabilir.
"""
import glob
import os
import shutil
import sys
import subprocess
import tempfile
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "YouTube Assistant - Kurulum Sihirbazı"
STARTUP_SHORTCUT_NAME = "YouTube Assistant.lnk"
GITHUB_README_URL = "https://github.com/20yalinay07-pixel/YouTubeAssistant#readme"
CHROME_CANDIDATE_PATHS = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
]

# (env_key, etiket, kayıt/panel URL'si veya None, yardım metni)
QUICK_PROVIDER = (
    "FREELLMAPI_API_KEY", "FreeLLMAPI (tek anahtar, önerilen)",
    "https://github.com/tashfeenahmed/freellmapi",
    "Docker ile yerelde kurulur, 34+ ücretsiz sağlayıcıyı TEK anahtar arkasında toplar. "
    "Kurulumdan sonra anahtarı http://localhost:3001 panelinden alın.",
)

STANDARD_PROVIDERS = [
    ("GROQ_API_KEY", "Groq (en hızlı, önerilen)", "https://console.groq.com/keys",
     "Ücretsiz hesap, saniyeler içinde anahtar üretir."),
    ("OPENROUTER_API_KEY", "OpenRouter (yedek sağlayıcı)", "https://openrouter.ai/keys",
     "Groq/FreeLLMAPI başarısız olursa devreye giren yedek."),
    ("ASSEMBLYAI_API_KEY_SUMMARIZE", "AssemblyAI - Özetleyici hesabı", "https://www.assemblyai.com/dashboard/signup",
     "İsteğe bağlı; video bölümleme kalitesini artırır."),
    ("ASSEMBLYAI_API_KEY_CHAPTERS", "AssemblyAI - Bölümleyici hesabı", "https://www.assemblyai.com/dashboard/signup",
     "İsteğe bağlı; yukarıdakiyle aynı sayfadan ikinci bir hesap/anahtar."),
    ("EXA_SEARCH_API_KEY", "Exa Search", "https://dashboard.exa.ai/api-keys",
     "İsteğe bağlı; önerilen videoların gerçekten var olduğunu doğrular."),
]

OMNIROUTE_DASHBOARD_URL = "http://localhost:20129"
FREELLMAPI_DASHBOARD_URL = "http://localhost:3001"

OMNIROUTE_KEYS = [
    ("OMNIROUTE_KEY_CHAT", "Chat / genel amaçlı"),
    ("OMNIROUTE_KEY_SUMMARIZE", "Özetleyici"),
    ("OMNIROUTE_KEY_ANALYZE", "Transkriptor"),
    ("OMNIROUTE_KEY_RECOMMENDATIONS", "Video önerici"),
    ("OMNIROUTE_KEY_CHAPTERS", "Video bölümleyici"),
]

ALL_ENV_KEYS = (
    [QUICK_PROVIDER[0]] + [p[0] for p in STANDARD_PROVIDERS] + [k for k, _ in OMNIROUTE_KEYS]
)


def find_project_root() -> str:
    here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    for candidate in (here, os.path.dirname(here)):
        if os.path.isfile(os.path.join(candidate, "backend", "server.py")):
            return candidate
    return here


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATE_PATHS:
        expanded = os.path.expandvars(candidate)
        if os.path.isfile(expanded):
            return expanded
    return ""


def find_python() -> str:
    """PATH'te ara; yoksa winget'in yeni kurduğu ama PATH'i henüz yenilenmemiş
    (bu islem yeniden baslatilmadan Windows PATH degisikligi surece yansimaz)
    olasi Python'u bilinen kurulum konumlarindan bulmaya calis."""
    found = shutil.which("python") or shutil.which("python3")
    if found:
        return found
    base = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python")
    if os.path.isdir(base):
        candidates = sorted(glob.glob(os.path.join(base, "Python3*", "python.exe")), reverse=True)
        if candidates:
            return candidates[0]
    for p in (r"C:\Python313\python.exe", r"C:\Python312\python.exe", r"C:\Python311\python.exe"):
        if os.path.isfile(p):
            return p
    return ""


def find_node() -> str:
    found = shutil.which("node")
    if found:
        return found
    for p in (r"C:\Program Files\nodejs\node.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\nodejs\node.exe")):
        if os.path.isfile(p):
            return p
    return ""


def find_npm_cmd(node_exe: str) -> str:
    """npm, node.exe ile ayni klasordeki bir .cmd shim'i -- PATH'e guvenmek
    yerine node'un bulundugu yerden turetmek winget'in az once kurdugu ama
    PATH'i henuz gormeyen bu surec icin daha guvenilir."""
    if node_exe:
        sibling = os.path.join(os.path.dirname(node_exe), "npm.cmd")
        if os.path.isfile(sibling):
            return sibling
    found = shutil.which("npm")
    return found or "npm"


def run_winget_install(package_id: str, log_fn) -> bool:
    winget = shutil.which("winget")
    if not winget:
        log_fn("HATA: 'winget' bulunamadi (eski bir Windows surumu olabilir). "
               "Elle kurmaniz gerekecek.")
        return False
    cmd = [winget, "install", "--id", package_id, "-e", "--silent",
           "--accept-package-agreements", "--accept-source-agreements"]
    log_fn(f"$ {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired) as e:
        log_fn(f"winget calistirilamadi: {e}")
        return False
    if proc.stdout:
        log_fn(proc.stdout.strip()[-1500:])
    if proc.returncode != 0:
        log_fn(f"winget cikis kodu: {proc.returncode}\n{(proc.stderr or '').strip()[-800:]}")
    return True


def ensure_python(log_fn) -> str:
    python_exe = find_python()
    if python_exe:
        return python_exe
    log_fn("Python bulunamadi, winget ile kuruluyor (birkac dakika surebilir)...")
    run_winget_install("Python.Python.3.12", log_fn)
    python_exe = find_python()
    if not python_exe:
        log_fn("HATA: Python kuruldu gibi gorunuyor ama bulunamadi -- bilgisayari "
               "yeniden baslatip sihirbazi tekrar acmayi deneyin, ya da "
               "https://python.org adresinden elle kurun.")
    return python_exe


def ensure_node(log_fn) -> str:
    node_exe = find_node()
    if node_exe:
        return node_exe
    log_fn("Node.js bulunamadi, winget ile kuruluyor (birkac dakika surebilir)...")
    run_winget_install("OpenJS.NodeJS.LTS", log_fn)
    node_exe = find_node()
    if not node_exe:
        log_fn("HATA: Node.js kuruldu gibi gorunuyor ama bulunamadi -- bilgisayari "
               "yeniden baslatip sihirbazi tekrar acmayi deneyin, ya da "
               "https://nodejs.org adresinden elle kurun.")
    return node_exe


def create_startup_shortcut(target_vbs: str, working_dir: str) -> tuple:
    """Windows Baslangic klasorune bir kisayol koyar (WScript.Shell COM'u --
    pywin32 bagimliligi eklememek icin gecici bir .vbs script ile cscript
    uzerinden cagriliyor, bu proje zaten baska yerlerde de .vbs kullaniyor)."""
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    shortcut_path = os.path.join(startup_dir, STARTUP_SHORTCUT_NAME)
    vbs_content = f'''
Set oWS = WScript.CreateObject("WScript.Shell")
Set oLink = oWS.CreateShortcut("{shortcut_path}")
oLink.TargetPath = "{target_vbs}"
oLink.WorkingDirectory = "{working_dir}"
oLink.Description = "YouTube Assistant - arka plan servisleri"
oLink.Save
'''
    fd, tmp_vbs = tempfile.mkstemp(suffix=".vbs")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(vbs_content)
        proc = subprocess.run(["cscript", "//nologo", tmp_vbs], capture_output=True, text=True)
        if proc.returncode != 0:
            return False, proc.stderr.strip() or "cscript hata verdi."
        return True, shortcut_path
    finally:
        try:
            os.remove(tmp_vbs)
        except OSError:
            pass


def remove_startup_shortcut() -> bool:
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    shortcut_path = os.path.join(startup_dir, STARTUP_SHORTCUT_NAME)
    if os.path.isfile(shortcut_path):
        os.remove(shortcut_path)
        return True
    return False


def load_existing_env(env_path: str) -> dict:
    values = {}
    if not os.path.isfile(env_path):
        return values
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip()
    return values


class SetupWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("680x760")
        self.minsize(560, 500)

        self.project_root = find_project_root()
        self.env_path = os.path.join(self.project_root, ".env")
        self.existing = load_existing_env(self.env_path)
        self.entries = {}
        self.show_keys = tk.BooleanVar(value=False)

        self._build_layout()

    # ---------- UI ----------

    def _build_layout(self):
        header = ttk.Frame(self, padding=(16, 14, 16, 4))
        header.pack(fill="x")
        ttk.Label(header, text="YouTube Assistant Kurulumu", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text=f"Proje klasörü: {self.project_root}",
            foreground="#555",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Button(header, text="Klasörü değiştir…", command=self._change_project_root).pack(anchor="w", pady=(4, 0))

        note = ttk.Label(
            header,
            text="Girdiğiniz anahtarlar sadece bilgisayarınızdaki .env dosyasına yazılır; "
                 "hiçbir yere gönderilmez. Çalışması için en az Groq VEYA FreeLLMAPI "
                 "anahtarlarından biri yeterli, gerisi isteğe bağlıdır.",
            wraplength=630, foreground="#333", justify="left",
        )
        note.pack(anchor="w", pady=(8, 0))

        # Scrollable content area
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=16, pady=8)
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scroll_frame = ttk.Frame(canvas)
        self.scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        self._section_title(self.scroll_frame, "Hızlı yol")
        self._provider_row(
            self.scroll_frame, *QUICK_PROVIDER,
            dashboard_url=FREELLMAPI_DASHBOARD_URL, dashboard_label="↳ Panele git (kurulumdan sonra)",
        )

        self._section_title(self.scroll_frame, "Ayrı ayrı sağlayıcılar (isteğe bağlı, tek tek eklenebilir)")
        for env_key, label, url, help_text in STANDARD_PROVIDERS:
            self._provider_row(self.scroll_frame, env_key, label, url, help_text)

        self._section_title(self.scroll_frame, "OmniRoute (gelişmiş, sadece zaten kuruluysa doldurun)")
        ttk.Label(
            self.scroll_frame,
            text="OmniRoute'u kurmadıysanız bu bölümü tamamen boş bırakabilirsiniz -- otomatik atlanır. "
                 "Anahtarları OmniRoute'un kendi panelinden alın (aşağıdaki \"Panele git\" düğmesi, backend "
                 "çalışırken açar).",
            foreground="#666", wraplength=610, justify="left",
        ).pack(anchor="w", padx=4, pady=(0, 6))
        for env_key, label in OMNIROUTE_KEYS:
            self._simple_row(self.scroll_frame, env_key, label, dashboard_url=OMNIROUTE_DASHBOARD_URL)

        self.install_omniroute = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.scroll_frame,
            text="OmniRoute'u da kur (npm ile otomatik -- gelişmiş, isteğe bağlı; "
                 "Groq/OpenRouter zaten tek başına yeterli)",
            variable=self.install_omniroute,
        ).pack(anchor="w", padx=4, pady=(0, 8))

        ttk.Checkbutton(
            self.scroll_frame, text="Anahtarları göster", variable=self.show_keys,
            command=self._toggle_visibility,
        ).pack(anchor="w", padx=4, pady=(10, 16))

        self.autostart = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.scroll_frame,
            text="Bilgisayar her açıldığında arka planı otomatik başlat (Başlangıç klasörüne kısayol ekler)",
            variable=self.autostart,
        ).pack(anchor="w", padx=4, pady=(0, 16))

        # Bottom action bar
        actions = ttk.Frame(self, padding=(16, 8, 16, 14))
        actions.pack(fill="x")
        ttk.Button(actions, text="Kaydet (.env oluştur/güncelle)", command=self.save_env).pack(side="left")
        ttk.Button(actions, text="Kur ve Başlat", command=self.install_and_start).pack(
            side="left", padx=8
        )
        ttk.Button(actions, text="Uzantı Yükleme Talimatları", command=self._show_extension_help).pack(side="left")
        ttk.Button(actions, text="Kapat", command=self.destroy).pack(side="right")

        self.log = tk.Text(self, height=7, state="disabled", background="#111", foreground="#0f0")
        self.log.pack(fill="x", side="bottom", padx=16, pady=(0, 12))

    def _section_title(self, parent, text):
        ttk.Label(parent, text=text, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(12, 4), padx=4)

    def _provider_row(self, parent, env_key, label, url, help_text, dashboard_url=None, dashboard_label="Panele git"):
        frame = ttk.Frame(parent, padding=(4, 4))
        frame.pack(fill="x")
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text=label, width=34).pack(side="left")
        entry = ttk.Entry(top, show="*")
        entry.insert(0, self.existing.get(env_key, ""))
        entry.pack(side="left", fill="x", expand=True, padx=6)
        self.entries[env_key] = entry
        if url:
            ttk.Button(top, text="Aç", width=6, command=lambda u=url: webbrowser.open(u)).pack(side="left")
        ttk.Label(frame, text=help_text, foreground="#666", wraplength=610, justify="left").pack(
            anchor="w", padx=(4, 0)
        )
        if dashboard_url:
            ttk.Button(
                frame, text=f"↳ {dashboard_label}",
                command=lambda u=dashboard_url: webbrowser.open(u),
            ).pack(anchor="w", padx=(4, 0), pady=(4, 0))

    def _simple_row(self, parent, env_key, label, dashboard_url=None, dashboard_label="Panele git"):
        frame = ttk.Frame(parent, padding=(4, 2))
        frame.pack(fill="x")
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text=label, width=34).pack(side="left")
        entry = ttk.Entry(top, show="*")
        entry.insert(0, self.existing.get(env_key, ""))
        entry.pack(side="left", fill="x", expand=True, padx=6)
        self.entries[env_key] = entry
        if dashboard_url:
            ttk.Button(
                top, text=dashboard_label, width=12,
                command=lambda u=dashboard_url: webbrowser.open(u),
            ).pack(side="left")

    def _toggle_visibility(self):
        show = "" if self.show_keys.get() else "*"
        for entry in self.entries.values():
            entry.configure(show=show)

    def _change_project_root(self):
        chosen = filedialog.askdirectory(title="YoutubeAssistant proje klasörünü seçin")
        if not chosen:
            return
        if not os.path.isfile(os.path.join(chosen, "backend", "server.py")):
            messagebox.showwarning(
                APP_TITLE,
                "Seçilen klasörde backend/server.py bulunamadı -- doğru proje klasörü "
                "olduğundan emin olun.",
            )
            return
        self.project_root = chosen
        self.env_path = os.path.join(self.project_root, ".env")
        self.existing = load_existing_env(self.env_path)
        for key, entry in self.entries.items():
            entry.delete(0, "end")
            entry.insert(0, self.existing.get(key, ""))
        self._log(f"Proje klasörü değiştirildi: {self.project_root}")

    # ---------- actions ----------

    def _log(self, message: str):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def save_env(self):
        values = {key: entry.get().strip() for key, entry in self.entries.items()}
        if not values.get("GROQ_API_KEY") and not values.get("FREELLMAPI_API_KEY"):
            if not messagebox.askyesno(
                APP_TITLE,
                "Ne Groq ne de FreeLLMAPI anahtarı girdiniz -- uygulama hiçbir AI "
                "özelliğini çalıştıramaz. Yine de kaydedilsin mi?",
            ):
                return

        # .env'de olup sihirbazda alanı olmayan satırları koru (elle eklenmiş olabilir).
        extra_lines = []
        if os.path.isfile(self.env_path):
            with open(self.env_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    key = stripped.split("=", 1)[0].strip()
                    if key not in ALL_ENV_KEYS:
                        extra_lines.append(line.rstrip("\n"))

        lines = ["# YouTube Assistant - Kurulum Sihirbazı tarafından oluşturuldu/güncellendi"]
        lines.append("")
        lines.append(f"FREELLMAPI_API_KEY={values.get('FREELLMAPI_API_KEY', '')}")
        lines.append("")
        for env_key, _, _, _ in STANDARD_PROVIDERS:
            lines.append(f"{env_key}={values.get(env_key, '')}")
        lines.append("")
        for env_key, _ in OMNIROUTE_KEYS:
            lines.append(f"{env_key}={values.get(env_key, '')}")
        if extra_lines:
            lines.append("")
            lines.extend(extra_lines)

        try:
            with open(self.env_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as e:
            messagebox.showerror(APP_TITLE, f".env dosyası yazılamadı: {e}")
            return

        self.existing = load_existing_env(self.env_path)
        self._log(f".env kaydedildi: {self.env_path}")
        messagebox.showinfo(APP_TITLE, ".env dosyası kaydedildi.")

    def install_and_start(self):
        self.save_env()
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _run_step(self, cmd, cwd, friendly_name):
        self._log(f"$ {' '.join(cmd)}  (klasör: {cwd})")
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, shell=False,
            )
        except FileNotFoundError:
            self._log(f"HATA: {friendly_name} bulunamadı. Kurulu değilse önce onu kurun.")
            return False
        if proc.stdout:
            self._log(proc.stdout.strip()[-2000:])
        if proc.returncode != 0:
            self._log(f"HATA ({friendly_name}): {proc.stderr.strip()[-1000:]}")
            return False
        return True

    def _install_worker(self):
        backend_dir = os.path.join(self.project_root, "backend")
        pot_dir = os.path.join(self.project_root, "pot_server")

        self._log("Python kontrol ediliyor...")
        python_exe = ensure_python(self._log)
        if not python_exe:
            self._log("Python olmadan devam edilemiyor, kurulum durduruldu.")
            return

        self._log("Node.js kontrol ediliyor...")
        node_exe = ensure_node(self._log)
        if not node_exe:
            self._log("Node.js olmadan devam edilemiyor, kurulum durduruldu.")
            return
        npm_cmd = find_npm_cmd(node_exe)

        self._log("Backend bağımlılıkları kuruluyor (pip)...")
        ok1 = self._run_step([python_exe, "-m", "pip", "install", "-r", "requirements.txt"], backend_dir, "pip")

        self._log("PO Token sunucusu bağımlılıkları kuruluyor (npm)...")
        ok2 = self._run_step([npm_cmd, "install"], pot_dir, "npm")

        if self.install_omniroute.get():
            self._log("OmniRoute kuruluyor (npm -g)...")
            ok3 = self._run_step([npm_cmd, "install", "-g", "omniroute"], self.project_root, "npm (omniroute)")
            if ok3:
                self._log("OmniRoute kuruldu. Kendi sağlayıcı hesaplarınızı bağlamak için "
                           "backend başladıktan sonra http://localhost:20129 panelini açabilirsiniz.")

        if not (ok1 and ok2):
            self._log("Bazı adımlar başarısız oldu -- yukarıdaki hataya bakın.")
            return

        vbs_path = os.path.join(self.project_root, "start_hidden.vbs")
        try:
            os.startfile(vbs_path)
            self._log("Arka plan başlatıldı (sistem tepsisine bakın).")
        except OSError as e:
            self._log(f"start_hidden.vbs başlatılamadı: {e}")
            return

        if self.autostart.get():
            ok, info = create_startup_shortcut(vbs_path, self.project_root)
            if ok:
                self._log(f"Başlangıç kısayolu eklendi: {info}")
            else:
                self._log(f"Başlangıç kısayolu eklenemedi: {info}")

        self._log("Kurulum tamamlandı. Uzantı yükleme sayfası açılıyor...")
        self._open_extension_page()
        webbrowser.open(GITHUB_README_URL)

    def _open_extension_page(self):
        chrome = find_chrome()
        if chrome:
            subprocess.Popen([chrome, "chrome://extensions/"])
        else:
            self._log("Chrome bulunamadı -- tarayıcınızda elle chrome://extensions adresine gidin.")

    def _show_extension_help(self):
        self._open_extension_page()
        messagebox.showinfo(
            APP_TITLE,
            "1) Açılan sekmede sağ üstten 'Geliştirici modu'nu açın.\n"
            "2) 'Paketlenmemiş öğe yükle' deyip şu klasörü seçin:\n"
            f"   {self.project_root}\n"
            "3) Bir YouTube videosu açın; panel otomatik belirir.",
        )


if __name__ == "__main__":
    SetupWizard().mainloop()
