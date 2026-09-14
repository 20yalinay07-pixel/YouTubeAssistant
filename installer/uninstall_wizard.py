"""
YouTube Assistant - Kaldırma Aracı

Ne yapar: (1) Başlangıç klasöründeki otomatik-başlatma kısayolunu siler,
(2) arka planda çalışan tray_launcher.py / pot_server süreçlerini durdurur.
Proje klasörünü ve .env içindeki anahtarlarınızı SİLMEZ -- onları isterseniz
elle silin, geri dönüşü olmayan bir işlem otomatik yapılmıyor.

Uninstall.bat ile aynı mantık; bu sürüm PyInstaller ile Uninstall.exe olarak
paketlenir (bkz. build_exe.bat) böylece uzantının simgesiyle çift tıklanabilir
bir dosya olarak dağıtılabilir.
"""
import os
import subprocess
import tkinter as tk
from tkinter import messagebox

APP_TITLE = "YouTube Assistant - Kaldırma"
STARTUP_SHORTCUT_NAME = "YouTube Assistant.lnk"


def remove_startup_shortcut(log) -> None:
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    shortcut_path = os.path.join(startup_dir, STARTUP_SHORTCUT_NAME)
    if os.path.isfile(shortcut_path):
        try:
            os.remove(shortcut_path)
            log("[OK] Başlangıç kısayolu kaldırıldı.")
        except OSError as e:
            log(f"[HATA] Başlangıç kısayolu silinemedi: {e}")
    else:
        log("[-] Başlangıç kısayolu zaten yok.")


def stop_background_processes(log) -> None:
    log("Arka plan servisleri durduruluyor (varsa)...")
    ps_cmd = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -match 'tray_launcher\\.py|pot_server' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=30)
        log("[OK] Servisler durduruldu (çalışıyorsa).")
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"[HATA] Servisler durdurulamadı: {e}")


def run_uninstall(log) -> None:
    log("YouTube Assistant kaldırılıyor...\n")
    remove_startup_shortcut(log)
    stop_background_processes(log)
    log(
        "\nTamamlandı. Proje klasörünü ve içindeki .env dosyanızı (API "
        "anahtarlarınız) bu işlem SİLMEDİ -- tamamen kaldırmak isterseniz "
        "bu klasörü elle silebilirsiniz."
    )


def main() -> None:
    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("560x360")
    root.minsize(480, 300)

    tk.Label(root, text="YouTube Assistant Kaldırma", font=("Segoe UI", 13, "bold")).pack(
        anchor="w", padx=14, pady=(14, 4)
    )
    tk.Label(
        root,
        text="Otomatik başlatma kısayolunu kaldırır ve arka plan servislerini durdurur.\n"
             "Proje klasörünüzü ve .env dosyanızı SİLMEZ.",
        justify="left", wraplength=520,
    ).pack(anchor="w", padx=14)

    log_box = tk.Text(root, height=12, state="disabled", background="#111", foreground="#0f0")
    log_box.pack(fill="both", expand=True, padx=14, pady=10)

    def log(message: str) -> None:
        log_box.configure(state="normal")
        log_box.insert("end", message + "\n")
        log_box.see("end")
        log_box.configure(state="disabled")
        root.update_idletasks()

    actions = tk.Frame(root)
    actions.pack(fill="x", padx=14, pady=(0, 14))
    tk.Button(actions, text="Kaldır", command=lambda: run_uninstall(log)).pack(side="left")
    tk.Button(actions, text="Kapat", command=root.destroy).pack(side="right")

    root.mainloop()


if __name__ == "__main__":
    main()
