' Youtube Asistani - Gizli Baslatici (sistem tepsisi ikonlu)
' Backend'i + OmniRoute'u ARKA PLANDA, konsol penceresi ACMADAN baslatir ve
' bildirim alaninda (saat yanindaki simgeler) bir ikon gosterir. O ikondan
' sunucuyu yeniden baslatabilir veya kapatabilirsiniz (orn. kod degisikligi
' yaptiktan sonra). Cift tiklayarak veya Windows Baslangic klasorune
' kisayolunu koyarak kullanin.

' NOT: Bu bilgisayarda BIRDEN FAZLA Python kurulumu var; bare "pythonw.exe"
' PATH sirasina gore YANLIS kuruluma (pystray/flask kurulu OLMAYAN) gidebilir.
' Bu yuzden gereken paketlerin kurulu oldugu kurulumun TAM yolu kullaniliyor.
PYTHONW_PATH = "C:\Users\Admin\AppData\Local\Programs\Python\Python312\pythonw.exe"

Set WshShell = CreateObject("WScript.Shell")
strPath = WScript.ScriptFullName
strFolder = Left(strPath, InStrRev(strPath, "\"))

Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(PYTHONW_PATH) Then
    PYTHONW_PATH = "pythonw.exe"  ' yedek: sistemde bulunamazsa PATH'e guven
End If

WshShell.Run """" & PYTHONW_PATH & """ """ & strFolder & "backend\tray_launcher.py""", 0, False
