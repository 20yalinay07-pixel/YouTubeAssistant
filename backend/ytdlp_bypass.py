# -*- coding: utf-8 -*-
"""
YouTube'un HTTP 429 (Too Many Requests) engellemesini aşmak için bugün
denenen/doğrulanan TÜM yt-dlp tekniklerinin tek, merkezi kaynağı.

Bu dosya bir "aile" (ilişkili tekniklerin gruplandığı tek yer) olarak
tasarlandı: her fonksiyonun/argümanın NEDEN var olduğu, hangi görev için
uygun olduğu ve hangi önerilerin test edilip NEDEN reddedildiği burada
belgeleniyor. server.py, bu modüldeki `build_*_args()` fonksiyonlarını
çağırarak argüman listelerini üretir -- aynı argümanları 4 farklı yerde
elle tekrar tekrar yazmak yerine TEK kaynaktan besleniyor.

============================================================================
DOĞRULANMIŞ VE AKTİF TEKNİKLER (gerçek testlerle kanıtlandı, kullanılıyor)
============================================================================

1) --impersonate chrome
   curl_cffi kurulu olduğu için (requirements.txt) yt-dlp gerçek bir
   tarayıcının TLS parmak izini taklit edebiliyor. Bot tespiti/403 riskini
   azaltır.

2) --extractor-args "youtube:player_client=android"
   "web" istemcisi (varsayılan) bu makinenin IP'sinde YouTube tarafından
   429 ile sık sık engelleniyor; "android" istemcisi FARKLI bir hız-limit
   havuzunda olduğu için genelde çalışıyor (doğrulandı).

3) --extractor-args "...;skip=hls,dash"  + --ignore-no-formats
   SADECE format/manifest gerekmeyen çağrılarda (metadata, altyazı, arama):
   yt-dlp'nin HLS/DASH video format manifestini çözmeye çalışmasını
   engeller -- gerçek testte metadata çekme süresini 3.6sn'ye indirdi,
   hatasız. Ses GERÇEKTEN indirilmesi gereken yerlerde (Whisper/Deepgram
   için) BU FLAG KULLANILMAZ, çünkü orada gerçek formatlara ihtiyaç var.

4) --no-playlist
   URL'de kazara &list=... parametresi varsa yt-dlp'nin tüm oynatma
   listesini işlemeye çalışıp takılmasını engeller. Zaten kodun her
   yt-dlp çağrısında mevcut.

5) --sub-langs "en,tr" (SADECE 2 dil, "all" ya da 20 dil DEĞİL)
   yt-dlp GitHub issue #2706 ve #11059: tek videoda ÇOK dilde altyazı
   istemek (özellikle YouTube'un oto-çeviri sistemi yüzünden) YouTube'un
   altyazı-özel 429 rate-limitini tetikliyor. AI zaten transkripti hedef
   dile çeviriyor, kaynak dilin ne olduğu önemli değil -- 2 dil (en geniş
   kapsamlı ikisi) yeterli, MAKSIMUM 3-4 dile çıkılabilir ama asla 10+.

============================================================================
DENENDİ, KANITLANMIŞ FAYDA GÖRÜLMEDİ -- BİLEREK KULLANILMIYOR
============================================================================

X) --force-ipv4
   Doğrudan test edildi (aynı video, aynı hata): 429 hâlâ geldi. Bloğun
   zaten IPv4 üzerinden geldiğini gösteriyor, protokol değişikliği bu
   makinede işe yaramadı.

X) --extractor-args "...;player_skip=js"
   Fresh videoda test edildi: 10.3sn + 429. Kontrol testinde (aynı flag
   OLMADAN, başka taze video) 4.4sn + başarılı. Net bir kazanç göstermedi;
   teorik olarak da altyazı-özel çağrılarda (video/ses formatı indirmiyoruz)
   bu flag'in çözdüğü "imza deşifreleme" sorunu zaten devreye girmiyor.

X) --sub-langs "all"
   Kesinlikle KULLANILMAMALI: YouTube'un oto-çeviri sistemi "all"ı
   potansiyel olarak 100+ dile genişletebilir -- yukarıdaki madde 5'in
   TAM TERSİ, 429 riskini büyük ölçüde artırır.

X) --convert-subs srt
   Gereksiz: kod zaten indirilen .vtt dosyasını kendi Python fonksiyonuyla
   (clean_subtitle_content) doğrudan metne çeviriyor. SRT'ye çevirmek
   fazladan bir ffmpeg adımı ekler, hiçbir fayda sağlamaz (bir video
   oynatıcıya ya da SRT bekleyen başka bir araca dosya vermiyoruz).

X) Genel/rastgele ücretsiz proxy rotasyonu
   Güvenilmez (çoğu zaten YouTube tarafından bloklu), yavaş, bilinmeyen
   bir sunucu üzerinden trafik geçirmek gizlilik riski taşıyor. Kullanıcı
   isterse KENDİ güvendiği bir proxy/VPN'i manuel olarak devreye
   sokabilir (bkz. build_download_args'taki opsiyonel `proxy` parametresi),
   ama otomatik/rastgele rotasyon YAPILMAZ.

============================================================================
Bulgular (bilgi amaçlı, kod değişikliği gerektirmez):
============================================================================
- 429 bloğu genelde VİDEO-ÖZEL/geçici, IP'nin tamamen banlanması değil --
  aynı videoyu defalarca art arda test etmek o videoyu geçici olarak
  kilitliyor, taze bir videoda aynı anda 429 hiç görünmeyebiliyor.
- Altyazı endpoint'i (timedtext), video/ses format endpoint'inden (manifest)
  AYRI bir rate-limit havuzunda -- ikisi bağımsız çalışır, birini düzeltmek
  diğerini düzeltmez.
"""

from typing import Optional

# Tum "sadece format/manifest gerekmeyen" cagrilarda ortak evasion argumanlari.
_EVASION_ARGS = ["--impersonate", "chrome"]

# En genis kapsamli 2 dil -- bkz. yukaridaki madde 5. Elle "all" ya da uzun bir
# liste ile DEGISTIRME, bu bilerek boyle birakildi.
DEFAULT_SUB_LANGS = "en,tr"


def build_no_format_args(extra_extractor_args: str = "") -> list:
    """
    Format/manifest indirmeye HİÇ gerek olmayan çağrılar (metadata, altyazı,
    arama) için ortak evasion argümanlarını döndürür: chrome impersonation +
    android client + hls/dash manifest atlama + format-yok hatasını yok say.
    `extra_extractor_args` ile ekstra youtube: alt-argümanları eklenebilir
    (örn. "player_skip=configs" -- ama bkz. yukarıdaki player_skip=js notu,
    kanıtlanmış fayda olmadan eklenmemeli).
    """
    extractor_arg = "youtube:player_client=android;skip=hls,dash"
    if extra_extractor_args:
        extractor_arg += ";" + extra_extractor_args
    return _EVASION_ARGS + [
        "--extractor-args", extractor_arg,
        "--ignore-no-formats",
        "--no-playlist",
    ]


def build_download_args(proxy: Optional[str] = None) -> list:
    """
    GERÇEK ses/video indirme gereken çağrılar (Whisper/Deepgram için ses
    indirme) için argümanlar -- skip=hls,dash BURADA KULLANILMAZ, çünkü
    gerçek formatlara ihtiyaç var. `proxy` verilirse (örn. kullanıcının
    kendi güvendiği bir proxy/VPN'i varsa) yt-dlp'ye iletilir; varsayılan
    None -- otomatik/rastgele proxy rotasyonu KASITLI OLARAK yapılmaz.
    """
    args = _EVASION_ARGS + [
        "--extractor-args", "youtube:player_client=android",
        "--no-playlist",
    ]
    if proxy:
        args += ["--proxy", proxy]
    return args


def build_subtitle_args(output_template: str, video_url: str, sub_langs: str = DEFAULT_SUB_LANGS) -> list:
    """Altyazı-özel (write-subs/write-auto-subs) tam komut argümanları."""
    return build_no_format_args() + [
        "--write-auto-subs", "--write-subs", "--sub-langs", sub_langs,
        "--skip-download",
        "--output", output_template,
        video_url,
    ]


def build_metadata_args(video_url: str) -> list:
    """Sadece --dump-json metadata çekmek için tam komut argümanları."""
    return build_no_format_args() + [
        "--dump-json", "--skip-download", "--no-warnings", video_url,
    ]


def build_search_args(query: str, want_results: int = 5) -> list:
    """ytsearchN: ile video arama için tam komut argümanları."""
    return build_no_format_args() + [
        f"ytsearch{want_results}:{query}", "--dump-json", "--skip-download", "--no-warnings",
    ]
