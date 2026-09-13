# ⭐ Youtube Asistanı - Kurulum ve Notlar (Premium Sürüm)

Bu sürüm önceki (Groq + Chat) sürümün üzerine **⭐ Ekstra Özellikler** menüsü
ekler. Kurulum aynı, sadece dosyalar değişti.

## Kurulum

**0) API anahtarlarını gir** — bu depo `.env` dosyasını GÜVENLİK için
içermez (`.gitignore`'da). Projeyi ilk kez bir bilgisayara indirdiysen, proje
kök klasöründe `.env` adında bir dosya oluşturup şu satırları kendi
anahtarlarınla doldurman gerekir:

```
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
OMNIROUTE_KEY_CHAT=...
OMNIROUTE_KEY_SUMMARIZE=...
OMNIROUTE_KEY_ANALYZE=...
OMNIROUTE_KEY_RECOMMENDATIONS=...
OMNIROUTE_KEY_CHAPTERS=...
ASSEMBLYAI_API_KEY_SUMMARIZE=...
ASSEMBLYAI_API_KEY_CHAPTERS=...
EXA_SEARCH_API_KEY=...
```

Bu dosya olmadan backend hiçbir AI çağrısı yapamaz. Backend başlarken bu
dosyayı otomatik okur (`python-dotenv`), koda hiçbir anahtar yazılmaz.

**1) Backend bağımlılıkları:**

```bash
cd "Youtube Asistanı\backend"
pip install -r requirements.txt
```

**2) PO Token sunucusu bağımlılıkları** — `pot_server/node_modules` da aynı
sebeple depoda yok (çok büyük, `npm install` ile yeniden oluşturulur):

```bash
cd "Youtube Asistanı\pot_server"
npm install
```

**3) Backend'i başlat:**

```bash
cd "Youtube Asistanı\backend"
python server.py
```

(Ya da tek seferde her şeyi başlatmak için `start_hidden.vbs` çalıştır —
backend'i, AI yönlendiriciyi ve PO Token sunucusunu penceresiz açar.)

Sonra `chrome://extensions` → Geliştirici modu → Paketlenmemiş öğe yükle →
**Youtube Asistanı** klasörünü seçin (önceki eklenti yüklüyse ⟳ yenile
yeterli).

---

## ⭐ Ekstra Özellikler nedir?

Ana menünün en altında sarı/altın renkli **⭐ Ekstra Özellikler** butonuna
tıklayınca iki özellik açılıyor, her birinin yanında bir açma/kapama anahtarı var:

### 1. 💬 Yapay Zeka ile Sınırsız Chat

🧠 Özet, 📊 Analiz, 📑 Bölümler ve 💡 Öneriler altındaki sohbet kutuları
**varsayılan olarak video+özellik başına 3 mesajla sınırlıdır** (her birinin
altında "X/3 ücretsiz mesaj kullanıldı" yazısını görürsünüz). Bu anahtarı
açtığınızda o sohbet kutularının **hepsinde** sınır kalkar, istediğiniz kadar
soru sorabilirsiniz. Ayrı bir chat kutusu değildir — mevcut kutuları sınırsız
hale getirir. Backend'de `/api/chat` isteğine `unlimited: true` gönderilerek
çalışır (`FREE_CHAT_MESSAGE_LIMIT` sabiti `server.py`'de, isterseniz 3 yerine
başka bir sayı yapabilirsiniz).

### 2. ⏩ Reklamları Otomatik Geçme

Açtığınızda:
- YouTube'un **kendi** "Reklamı geç" butonu ekrana gelir gelmez otomatik tıklanır
- Buton gelmeden önceki zorunlu reklam kısmında video oynatma hızı geçici olarak
  artırılır (reklam bitince otomatik normale döner)

**Not:** Bu özellik reklam isteklerini engellemez, reklam öğesini sayfadan
silmez — sadece YouTube'un kendi sunduğu "geç" butonuna tıklar ve oynatma
hızını değiştirir. Bu yüzden daha önce gördüğünüz "reklam engelleyiciler
Hizmet Şartları'nı ihlal ediyor" tarzı uyarıyı tetiklemesi beklenmez. Yine de
YouTube bu davranışı ileride farklı şekilde algılayabilir; bir sorun
yaşarsanız anahtarı kapatmanız yeterli.

---

## "Premium" hakkında dürüst bir not

Bu tamamen **sizin kişisel kullanımınız için yerel bir araç** olduğundan
gerçek bir ödeme sistemi / kullanıcı hesabı / lisans sunucusu kurmadım —
bunun için ayrı bir backend, ödeme altyapısı (Stripe vb.) ve kimlik doğrulama
gerekir, bu araç için pratik değil. "Premium" burada sadece görsel/kavramsal
bir ayrım: iki özelliği istediğiniz zaman kendiniz açıp kapatabiliyorsunuz,
gerçek bir kilit yok. İsterseniz basit bir "kod girerek açma" mekanizması da
ekleyebilirim (yine gerçek bir ödeme doğrulaması olmaz, sadece ek bir adım
olur) — isterseniz söyleyin.

---

## ⚡ Hız Düzeltmeleri (Transkript artık çok daha hızlı)

Önceden bazı videolarda transkript çıkarma 10 dakikaya kadar sürebiliyordu.
Üç kök sebep düzeltildi:

1. **Yöntem 1 (youtube-transcript-api) hatası:** Kurulu kütüphane sürümünüz
   yeni nesil (v1.0+) API kullanıyor, kod ise eski statik metodları
   çağırıyordu (`list_transcripts` hatası). Artık kod hem eski hem yeni
   sürümü otomatik algılayıp doğru şekilde çalışıyor.
2. **Yöntem 2 (yt-dlp altyazı) 45 saniye timeout:** İki sebepten yavaştı:
   - `--sub-langs all` ile YouTube'un sunduğu **tüm** (bazen 100+) dildeki
     altyazıyı indirmeye çalışıyordu. Artık önce mevcut dilleri hızlıca
     listeleyip **sadece birini** indiriyor.
   - URL'nizde `&list=...` (radio/mix/playlist) parametresi vardı; yt-dlp
     bu durumda tüm listeyi işlemeye çalışabiliyordu. Artık tüm yt-dlp
     çağrılarına `--no-playlist` eklendi, sadece tek video işleniyor.
3. **Yöntem 3 (Whisper) parçaların sırayla işlenmesi:** Uzun videolarda ses
   parçaları artık **paralel** (aynı anda en fazla 4 parça) transkribe
   ediliyor; önceden tamamen sıralıydı, video ne kadar uzunsa o kadar
   bekleniyordu.

---

## 🔁 Backend'i Komut Çalıştırmadan Otomatik Açık Tutma (Sistem Tepsisi İkonlu)

Klasörde şu dosyalar var:

- **`backend/tray_launcher.py`** — hem OmniRoute'u hem backend'i başlatır,
  bildirim alanında (saat yanındaki simgeler) bir **ikon** gösterir. O
  ikona sağ tıklayınca: sunucuyu yeniden başlatma, logları açma ve kapatma
  seçenekleri çıkar (örn. kod değişikliği yaptıktan sonra kapatıp yeniden
  açmak için).
- **`start_hidden.vbs`** — `tray_launcher.py`'yi **konsol penceresi
  açmadan** başlatır. Günlük kullanım için asıl çalıştırmanız gereken
  dosya budur.
- **`start_server.bat`** — eski, konsol pencereli/tray'siz alternatif
  (sorun giderme/debug için elde tutuluyor); backend çökerse 3 saniye
  sonra otomatik yeniden başlatır ama tray ikonu YOK.

Tray özelliği için gereken paket (`pystray`) `requirements.txt`'e eklendi;
`pip install -r requirements.txt` çalıştırdıysanız zaten kurulu olmalı.

### A) Windows açılışında otomatik başlatma (önerilen)

1. `Win + R` → `shell:startup` yazıp Enter'a basın (bu, Başlangıç klasörünü açar)
2. `start_hidden.vbs` dosyasına **sağ tık → Kısayol Oluştur**
3. Oluşan kısayolu (`start_hidden.vbs - Kısayol` gibi) o Başlangıç klasörüne taşıyın/kopyalayın

Bundan sonra **Windows'a her giriş yaptığınızda backend + OmniRoute
otomatik, arka planda başlayacak ve bildirim alanında bir ikon
görünecek** — `python server.py` komutunu elle çalıştırmanıza gerek kalmaz.

**Test etmek için:** `start_hidden.vbs` dosyasına şimdi çift tıklayın, birkaç
saniye bekleyin, bildirim alanında ikonu (saat yanındaki ok/simgeler
kısmında, gerekirse ok'a tıklayıp gizli simgeleri açın) kontrol edin,
sonra tarayıcıdan `http://127.0.0.1:8000/health` adresini açın — bir JSON
yanıtı görüyorsanız çalışıyor demektir.

**Sorun giderme:** Bir şey çalışmıyorsa `backend/tray_launcher.log`
dosyasını açın (ikona sağ tık → "Loglari Ac" ile de açılabilir) — hem
OmniRoute hem backend'in çıktısı ve varsa hatalar orada birikir.

### B) Görev Zamanlayıcı (Task Scheduler) ile daha sağlam kurulum (opsiyonel)

Yukarıdaki yöntem "Windows'a giriş yapınca" başlar. Bilgisayar açık ama siz
oturum açmadan da (örn. uzaktan bağlantı senaryoları) çalışmasını isterseniz:

1. `Win + R` → `taskschd.msc` → Enter
2. Sağda **Temel Görev Oluştur** → isim verin (örn. "Youtube Asistanı")
3. Tetikleyici: **Bilgisayar başlatıldığında**
4. Eylem: **Bir program başlat** → Program: `wscript.exe`, Argümanlar:
   `"C:\...\Youtube Asistanı\start_hidden.vbs"` (tam yolu kendinize göre yazın)
5. Sihirbazı bitirdikten sonra oluşturduğunuz görevi çift tıklayıp
   **"Kullanıcı oturum açmasa da çalıştır"** seçeneğini işaretleyin (Windows
   şifrenizi tekrar girmeniz istenebilir)

> **Not:** Gerçek "7/24" için bilgisayarınızın da açık (uyku/kapalı değil)
> olması gerekir — bu ayarlar sadece "siz elle komut çalıştırmadan otomatik
> başlasın" sorununu çözer. Bilgisayar kapalıyken elbette çalışmaz; tam 7/24
> için sunucuyu bir bulut sağlayıcısında (VPS) barındırmanız gerekir, o ayrı
> bir kurulumdur, isterseniz onu da anlatabilirim.

---

## 🌐 Dil Seçici + Şarkı Tespiti + Akıllı Öneriler (Yeni)

- **Dil seçici:** Panelin üstünde, sadece ana menü açıkken görünen bir "🌐 Cevap dili" seçim kutusu var (~40 dil). Bir özellik seçtiğinizde bu kutu kaybolur; seçtiğiniz dil hafızada kalır ve o özelliğin çıktısı (özet/analiz/bölümler/öneriler/sohbet) **seçtiğiniz dilde** gelir. Transkriptin kendisi her zaman videonun konuşulduğu dilde kalır (o değişmez, sadece AI'nin yorumları/cevapları seçilen dilde olur).
- **Şarkı tespiti:** Transkript çıkarırken video Music kategorisindeyse (yt-dlp metadata) üstte "🎵 Bu içerik bir şarkı/müzik parçası gibi görünüyor" notu (seçtiğiniz dilde) bir kez gösterilir.
- **Akıllı öneriler:** Öneriler artık içerik türüne göre şekilleniyor — video bir şarkıysa benzer şarkılar, bilgilendirme/eğitim videosuysa benzer konulu bilgilendirme videoları öneriliyor.

---

## 📂 Dosya Yapısı

```
Youtube Asistanı/
├── backend/
│   ├── server.py        ← Hız düzeltmeleri + mesaj limiti + Premium sınırsız chat
│   └── requirements.txt
├── content.js            ← Ekstra Özellikler menüsü eklendi
├── manifest.json
├── GroqAPI_Key.txt
├── icon16.png / icon48.png / icon128.png
├── start_server.bat      ← YENİ: backend'i başlatır, çökerse yeniden başlatır
├── start_hidden.vbs       ← YENİ: konsol penceresi açmadan arka planda başlatır
└── KURULUM.md
```
