// YouTube Assistant - Content Script (Groq + Premium sürümü)
// Reklam engelleme / paywall bypass YOK.
// Her özelliğin altında o özelliğe özgü sohbet kutusu var.
// Öneriler gerçek YouTube videolarıyla ve küçük oynatıcı ile geliyor.

console.log('🤖 YouTube Assistant yüklendi');

const BACKEND_URL = 'http://127.0.0.1:8000';

// Backend'deki LANG_NAME_TO_CODE ile aynı dil paketinden (server.py) türetilmiş,
// panelde gösterilecek dil seçenekleri. Kod (value) backend'in anladığı ISO koduyla
// birebir eşleşir, böylece seçilen dil doğrudan backend'e iletilebilir.
const LANGUAGE_OPTIONS = [
    { code: 'tr', label: '🇹🇷 Türkçe', nameTr: 'Türkçe', nameEn: 'Turkish' },
    { code: 'en', label: '🇬🇧 English', nameTr: 'İngilizce', nameEn: 'English' },
    { code: 'es', label: '🇪🇸 Español', nameTr: 'İspanyolca', nameEn: 'Spanish' },
    { code: 'de', label: '🇩🇪 Deutsch', nameTr: 'Almanca', nameEn: 'German' },
    { code: 'fr', label: '🇫🇷 Français', nameTr: 'Fransızca', nameEn: 'French' },
    { code: 'it', label: '🇮🇹 Italiano', nameTr: 'İtalyanca', nameEn: 'Italian' },
    { code: 'pt', label: '🇵🇹 Português', nameTr: 'Portekizce', nameEn: 'Portuguese' },
    { code: 'ru', label: '🇷🇺 Русский', nameTr: 'Rusça', nameEn: 'Russian' },
    { code: 'ja', label: '🇯🇵 日本語', nameTr: 'Japonca', nameEn: 'Japanese' },
    { code: 'ko', label: '🇰🇷 한국어', nameTr: 'Korece', nameEn: 'Korean' },
    { code: 'zh', label: '🇨🇳 中文', nameTr: 'Çince', nameEn: 'Chinese' },
    { code: 'ar', label: '🇸🇦 العربية', nameTr: 'Arapça', nameEn: 'Arabic' },
    { code: 'hi', label: '🇮🇳 हिन्दी', nameTr: 'Hintçe', nameEn: 'Hindi' },
    { code: 'nl', label: '🇳🇱 Nederlands', nameTr: 'Hollandaca', nameEn: 'Dutch' },
    { code: 'pl', label: '🇵🇱 Polski', nameTr: 'Lehçe', nameEn: 'Polish' },
    { code: 'uk', label: '🇺🇦 Українська', nameTr: 'Ukraynaca', nameEn: 'Ukrainian' },
    { code: 'el', label: '🇬🇷 Ελληνικά', nameTr: 'Yunanca', nameEn: 'Greek' },
    { code: 'sv', label: '🇸🇪 Svenska', nameTr: 'İsveççe', nameEn: 'Swedish' },
    { code: 'fi', label: '🇫🇮 Suomi', nameTr: 'Fince', nameEn: 'Finnish' },
    { code: 'da', label: '🇩🇰 Dansk', nameTr: 'Danca', nameEn: 'Danish' },
    { code: 'no', label: '🇳🇴 Norsk', nameTr: 'Norveççe', nameEn: 'Norwegian' },
    { code: 'cs', label: '🇨🇿 Čeština', nameTr: 'Çekçe', nameEn: 'Czech' },
    { code: 'ro', label: '🇷🇴 Română', nameTr: 'Rumence', nameEn: 'Romanian' },
    { code: 'hu', label: '🇭🇺 Magyar', nameTr: 'Macarca', nameEn: 'Hungarian' },
    { code: 'he', label: '🇮🇱 עברית', nameTr: 'İbranice', nameEn: 'Hebrew' },
    { code: 'fa', label: '🇮🇷 فارسی', nameTr: 'Farsça', nameEn: 'Persian' },
    { code: 'th', label: '🇹🇭 ไทย', nameTr: 'Tayca', nameEn: 'Thai' },
    { code: 'vi', label: '🇻🇳 Tiếng Việt', nameTr: 'Vietnamca', nameEn: 'Vietnamese' },
    { code: 'id', label: '🇮🇩 Bahasa Indonesia', nameTr: 'Endonezce', nameEn: 'Indonesian' },
    { code: 'ms', label: '🇲🇾 Bahasa Melayu', nameTr: 'Malayca', nameEn: 'Malay' },
    { code: 'ur', label: '🇵🇰 اردو', nameTr: 'Urduca', nameEn: 'Urdu' },
    { code: 'bn', label: '🇧🇩 বাংলা', nameTr: 'Bengalce', nameEn: 'Bengali' },
    { code: 'ta', label: '🇮🇳 தமிழ்', nameTr: 'Tamilce', nameEn: 'Tamil' },
    { code: 'sw', label: '🇰🇪 Kiswahili', nameTr: 'Svahilice', nameEn: 'Swahili' },
    { code: 'az', label: '🇦🇿 Azərbaycan', nameTr: 'Azerice', nameEn: 'Azerbaijani' },
    { code: 'ka', label: '🇬🇪 ქართული', nameTr: 'Gürcüce', nameEn: 'Georgian' },
    { code: 'hy', label: '🇦🇲 Հայերեն', nameTr: 'Ermenice', nameEn: 'Armenian' },
    { code: 'bg', label: '🇧🇬 Български', nameTr: 'Bulgarca', nameEn: 'Bulgarian' },
    { code: 'sr', label: '🇷🇸 Српски', nameTr: 'Sırpça', nameEn: 'Serbian' },
    { code: 'hr', label: '🇭🇷 Hrvatski', nameTr: 'Hırvatça', nameEn: 'Croatian' },
];

const SELECTED_LANG_KEY = 'ytai_selected_lang';
const LANG_HINT_SEEN_KEY = 'ytai_lang_hint_seen';

// YouTube'un kendi arayuz dili ayarini (sol ustteki logonun yanindaki ulke/dil
// rozetiyle ayni kaynaktan gelir) algilar. Once ytcfg.get('HL') denenir -- bu,
// YouTube'un SPA'sinin kendi ic durumundaki gercek "host language" degeridir ve
// document.documentElement.lang'dan DAHA GUVENILIRDIR (o oznitelik sayfa ilk
// hidrate olurken bos/yanlis olabiliyor). ytcfg yoksa documentElement.lang'a
// duser. LANGUAGE_OPTIONS icinde karsiligi yoksa null doner.
function detectYouTubeUILang() {
    try {
        let raw = '';
        if (window.ytcfg && typeof window.ytcfg.get === 'function') {
            raw = window.ytcfg.get('HL') || '';
        }
        if (!raw) raw = document.documentElement.lang || '';
        raw = raw.toLowerCase().trim();
        if (!raw) return null;
        const base = raw.split('-')[0].split('_')[0];
        const match = LANGUAGE_OPTIONS.find(o => o.code === base);
        return match ? match.code : null;
    } catch (e) { return null; }
}

function getSelectedLang() {
    try {
        const stored = localStorage.getItem(SELECTED_LANG_KEY);
        if (stored) return stored;
        return detectYouTubeUILang() || 'tr';
    } catch (e) { return 'tr'; }
}

// ==================== ARAYÜZ ÇEVİRİLERİ ====================
// Buton/başlık gibi SABİT arayüz metinleri için. Listede olmayan diller
// otomatik olarak İngilizce'ye düşer (AI cevapları yine backend'de doğru
// dilde üretilir, bu sadece sabit UI metinleri içindir).
const UI_STRINGS = {
    tr: {
        appTitle: '🤖 Youtube Asistanı', backBtn: '← Menü', langLabel: '🌐 Cevap dili:',
        menuSummarize: '🧠 Özet', menuAnalyze: '📊 Konu Analizi', menuChapters: '📑 Bölümler',
        menuRecommendations: '💡 Öneriler', menuTranscript: '📝 Transkript', menuExtra: '⭐ Ekstra Özellikler',
        featSummarize: 'Özet', featAnalyze: 'Konu Analizi', featChapters: 'Bölümler',
        featRecommendations: 'Öneriler', featTranscript: 'Transkript',
        chatAskAbout: (f) => `💬 Bu ${f.toLowerCase()} hakkında soru sor:`,
        chatPlaceholder: 'Örn: Bu video neyi anlatıyor?', chatSend: 'Gönder',
        chatLimitUsed: (u, l, r) => `${u}/${l} ücretsiz mesaj kullanıldı (${r} hakkınız kaldı)`,
        chatUnlimited: '⭐ Sınırsız sohbet aktif', chatLimitPlaceholder: "Limit doldu — Ekstra Özellikler'den Sınırsız Chat'i açın",
        transcriptNoChat: 'ℹ️ Transkriptte sohbet kutusu yok — ham metin gösterilir.',
        chaptersEmpty: 'Bu video için net zaman damgalı bölümler oluşturulamadı.',
        refineBtn: '🔁 Bu sohbete göre yeni öneriler bul',
        loadingRecommendations: 'Öneriler oluşturuluyor ve gerçek videolar aranıyor...',
        loadingRecommendationsRefine: 'Sohbete göre yeni videolar aranıyor...',
        loadingGeneric: 'Transkript alınıyor (altyazı yoksa ses çözümlenir, biraz sürebilir)...',
        loadingPreparing: 'Video hazırlanıyor (transkript bir kez çıkarılıyor)...',
        prepareStatus_starting: 'Başlatılıyor...',
        prepareStatus_subtitle_api: 'Altyazı aranıyor (hızlı yöntem)...',
        prepareStatus_ytdlp_subs: 'Otomatik altyazı indiriliyor...',
        prepareStatus_omniroute_deepgram: 'Altyazı yok — ses indirilip hızlı yapay zeka ile çözümleniyor...',
        prepareStatus_whisper: 'Altyazı yok — ses indirilip yapay zeka ile çözümleniyor (en yavaş adım)...',
        prepareStatus_generating: 'İçerik oluşturuluyor (özet, analiz, bölümler)...',
        prepareStatus_done: 'Hazır, sonuçlar getiriliyor...',
        prepareStatus_failed: 'Transkript bulunamadı...',
        recNoVideo: 'Bu konu için gerçek video bulunamadı.', recWatchOnYoutube: "▶ YouTube'da aç",
        recFoundVideo: 'Bulunan video:', recEmbedError: 'Video oynatılamadı, YouTube\'da izleyin:',
        extraTitle: '⭐ Ekstra Özellikler', extraSubtitle: 'Bir lisans anahtarınız varsa aşağıya girin — plana göre özellikler otomatik açılır.',
        extraLicenseLabel: 'Lisans anahtarı', extraLicensePlaceholder: 'YTAS-XXXX-XXXX-XXXX',
        extraLicenseActivate: 'Etkinleştir', extraLicenseChecking: 'Kontrol ediliyor...',
        extraLicenseValid: (plan) => `✅ Aktif: ${plan}`, extraLicenseInvalid: '❌ Geçersiz veya süresi dolmuş anahtar',
        extraLicenseNone: 'Henüz bir lisansınız yok.', extraLicenseNetworkError: '⚠️ Sunucuya ulaşılamadı, son bilinen durum korunuyor.',
        extraBuyLink: '💳 Premium satın al →',
        extraUnlimitedChatTitle: '💬 Yapay Zeka ile Sınırsız Chat',
        extraUnlimitedChatDesc: (n) => `🧠 Özet, 📊 Analiz, 📑 Bölümler ve 💡 Öneriler altındaki sohbet kutuları normalde video başına ${n} mesajla sınırlıdır. Bunu açtığınızda o sohbet kutularının HEPSİNDE mesaj sınırı kalkar, istediğiniz kadar sorabilirsiniz.`,
        extraAdSkipTitle: '⏩ Reklamları Otomatik Geçme',
        extraAdSkipDesc: '"Reklamı geç" butonu geldiği an otomatik tıklanır; buton gelmeden önce de reklam hızlandırılır. Reklam istekleri engellenmediği/reklam öğeleri silinmediği için YouTube\'un reklam engelleyici uyarısını tetiklemesi beklenmez.',
        errorPrefix: '❌ Hata:', copyBtnTitle: 'Kopyala', langHint: '🌐 Dili buradan değiştirebilirsin',
        transcriptTranslateLabel: 'Transkripti çevir:',
        translateDefaultOption: (name) => name ? `Varsayılan (${name})` : 'Varsayılan (Video Dili)',
        translatingText: 'Çevriliyor...',
    },
    en: {
        appTitle: '🤖 YouTube Assistant', backBtn: '← Menu', langLabel: '🌐 Response language:',
        menuSummarize: '🧠 Summary', menuAnalyze: '📊 Topic Analysis', menuChapters: '📑 Chapters',
        menuRecommendations: '💡 Recommendations', menuTranscript: '📝 Transcript', menuExtra: '⭐ Extra Features',
        featSummarize: 'Summary', featAnalyze: 'Topic Analysis', featChapters: 'Chapters',
        featRecommendations: 'Recommendations', featTranscript: 'Transcript',
        chatAskAbout: (f) => `💬 Ask about this ${f.toLowerCase()}:`,
        chatPlaceholder: 'E.g: What is this video about?', chatSend: 'Send',
        chatLimitUsed: (u, l, r) => `${u}/${l} free messages used (${r} remaining)`,
        chatUnlimited: '⭐ Unlimited chat active', chatLimitPlaceholder: 'Limit reached — open Unlimited Chat in Extra Features',
        transcriptNoChat: 'ℹ️ No chat box for transcript — raw text is shown.',
        chaptersEmpty: 'Could not generate reliable timestamped chapters for this video.',
        refineBtn: '🔁 Find new recommendations based on this chat',
        loadingRecommendations: 'Generating recommendations and searching for real videos...',
        loadingRecommendationsRefine: 'Searching for new videos based on chat...',
        loadingGeneric: 'Fetching transcript (if no subtitles, audio is transcribed, may take a while)...',
        loadingPreparing: 'Preparing video (extracting transcript once)...',
        prepareStatus_starting: 'Starting...',
        prepareStatus_subtitle_api: 'Looking for captions (fast method)...',
        prepareStatus_ytdlp_subs: 'Downloading auto captions...',
        prepareStatus_omniroute_deepgram: 'No captions — downloading audio and transcribing quickly...',
        prepareStatus_whisper: 'No captions — downloading audio and transcribing with AI (slowest step)...',
        prepareStatus_generating: 'Generating content (summary, analysis, chapters)...',
        prepareStatus_done: 'Ready, fetching results...',
        prepareStatus_failed: 'No transcript found...',
        recNoVideo: 'No real video found for this topic.', recWatchOnYoutube: '▶ Open on YouTube',
        recFoundVideo: 'Found video:', recEmbedError: "Video couldn't play, watch on YouTube:",
        extraTitle: '⭐ Extra Features', extraSubtitle: 'If you have a license key, enter it below — features unlock automatically based on your plan.',
        extraLicenseLabel: 'License key', extraLicensePlaceholder: 'YTAS-XXXX-XXXX-XXXX',
        extraLicenseActivate: 'Activate', extraLicenseChecking: 'Checking...',
        extraLicenseValid: (plan) => `✅ Active: ${plan}`, extraLicenseInvalid: '❌ Invalid or expired key',
        extraLicenseNone: "You don't have a license yet.", extraLicenseNetworkError: '⚠️ Could not reach the server, keeping last known status.',
        extraBuyLink: '💳 Buy Premium →',
        extraUnlimitedChatTitle: '💬 AI Unlimited Chat',
        extraUnlimitedChatDesc: (n) => `Chat boxes under 🧠 Summary, 📊 Analysis, 📑 Chapters and 💡 Recommendations are normally limited to ${n} messages per video. Enabling this removes the limit on ALL of them.`,
        extraAdSkipTitle: '⏩ Auto-Skip Ads',
        extraAdSkipDesc: "Clicks YouTube's own 'Skip Ad' button as soon as it appears; speeds up ads before that. Doesn't block ad requests or remove elements, so it shouldn't trigger YouTube's adblock warning.",
        errorPrefix: '❌ Error:', copyBtnTitle: 'Copy', langHint: 'You can change the language here',
        transcriptTranslateLabel: 'Translate transcript:',
        translateDefaultOption: (name) => name ? `Default (${name})` : 'Default (Video Language)',
        translatingText: 'Translating...',
    },
};

// Diğer diller için İngilizce'ye düş
function ui(key, ...args) {
    const lang = getSelectedLang();
    const table = UI_STRINGS[lang] || UI_STRINGS.en;
    const fallback = UI_STRINGS.en;
    const val = table[key] !== undefined ? table[key] : fallback[key];
    return typeof val === 'function' ? val(...args) : val;
}

function setSelectedLang(code) {
    try { localStorage.setItem(SELECTED_LANG_KEY, code); } catch (e) { /* yoksay */ }
}

// Dil seciciye ilk acilista bir kerelik "dili buradan degistirebilirsin" ipucu
// gosterir; localStorage bayragiyla bir daha (sonraki acilislarda) gosterilmez.
function hasSeenLangHint() {
    try { return localStorage.getItem(LANG_HINT_SEEN_KEY) === '1'; } catch (e) { return true; }
}
function hideLangHint() {
    const hint = document.getElementById('lang-hint');
    if (hint) hint.style.display = 'none';
}
function maybeShowLangHint() {
    if (hasSeenLangHint()) return;
    const hint = document.getElementById('lang-hint');
    if (!hint) return;
    hint.style.display = 'block';
    try { localStorage.setItem(LANG_HINT_SEEN_KEY, '1'); } catch (e) { /* yoksay */ }
    const timer = setTimeout(hideLangHint, 6000);
    hint.addEventListener('click', () => { clearTimeout(timer); hideLangHint(); });
}

async function callBackendAPI(endpoint, data) {
    const apiKeys = await getSyncedApiKeys();
    const response = await fetch(`${BACKEND_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...data, api_keys: apiKeys })
    });
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || `HTTP ${response.status}`);
    }
    return await response.json();
}

// ==================== UI: BUTON ====================
// Eklenti SADECE video izleme sayfasında (youtube.com/watch?v=...) görünmeli;
// ana sayfa, arama sonuçları, kanal sayfası vb. yerlerde açılmamalı.
function isVideoWatchPage() {
    return location.pathname === '/watch' && new URLSearchParams(location.search).has('v');
}

function removePanelAndButton() {
    const btn = document.getElementById('youtube-ai-button');
    if (btn) btn.remove();
    const panel = document.getElementById('youtube-ai-panel');
    if (panel) panel.remove();
}

function createAIButton() {
    if (!isVideoWatchPage()) return;
    if (document.getElementById('youtube-ai-button')) return;

    const button = document.createElement('button');
    button.id = 'youtube-ai-button';
    button.innerHTML = ui('appTitle');
    button.style.cssText = `
        position: relative; margin: 12px 0; padding: 10px 16px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white; border: none; border-radius: 8px; font-size: 14px;
        font-weight: 600; cursor: pointer; box-shadow: 0 2px 8px rgba(102,126,234,0.3);
        transition: all 0.3s ease; z-index: 9999;
    `;
    button.onmouseover = () => { button.style.transform = 'translateY(-2px)'; };
    button.onmouseout = () => { button.style.transform = 'translateY(0)'; };
    button.onclick = () => togglePanel();

    const insertButton = () => {
        if (!isVideoWatchPage()) return;
        const titleContainer = document.querySelector('#title.ytd-watch-metadata') ||
                                document.querySelector('#container h1');
        if (titleContainer && !document.getElementById('youtube-ai-button')) {
            titleContainer.parentElement.insertBefore(button, titleContainer.nextSibling);
        }
    };
    insertButton();
    new MutationObserver(insertButton).observe(document.body, { childList: true, subtree: true });
}

// ==================== UI: PANEL (Tarayıcı sekmesi tarzı) ====================
const TAB_ACTIONS = ['summarize', 'analyze', 'chapters', 'recommendations', 'transcript'];
const TAB_ICONS = { summarize: '🧠', analyze: '📊', chapters: '📑', recommendations: '💡', transcript: '📝', extra: '⭐' };
const TAB_LABEL_KEYS = { summarize: 'featSummarize', analyze: 'featAnalyze', chapters: 'featChapters', recommendations: 'featRecommendations', transcript: 'featTranscript' };
const FEATURES_WITHOUT_CHAT = ['transcript'];

function tabLabel(action) {
    if (action === 'extra') return ui('menuExtra').replace('⭐ ', '');
    return ui(TAB_LABEL_KEYS[action]);
}

function findDockTarget() {
    // YouTube'un video oynatıcının hemen sağındaki gerçek sütunu (önerilen
    // videolar/chat'in göründüğü yer). Panel BURAYA yerleşirse "örnekteki gibi"
    // sayfanın doğal bir parçası olarak görünür (floating/sabit kutu değil).
    return document.querySelector('#secondary #secondary-inner') ||
           document.querySelector('#secondary') ||
           null;
}

function createPanel() {
    const existing = document.getElementById('youtube-ai-panel');
    const dockTarget = findDockTarget();

    if (existing) {
        // Video değişmiş olabilir; panel doğru yerde değilse (örn. YouTube
        // #secondary'yi yeniden oluşturduysa) doğru konuma taşı.
        if (dockTarget && existing.parentElement !== dockTarget) {
            dockTarget.prepend(existing);
            applyDockedStyle(existing);
        }
        return;
    }

    const panel = document.createElement('div');
    panel.id = 'youtube-ai-panel';

    const tabButtonsHtml = TAB_ACTIONS.map(action => `
        <button class="yt-ai-tab" data-tab="${action}" title="${tabLabel(action)}">
            <span class="yt-ai-tab-icon">${TAB_ICONS[action]}</span>
            <span class="yt-ai-tab-text">${tabLabel(action)}</span>
        </button>
    `).join('');

    const panelsHtml = TAB_ACTIONS.map(action => buildFeatureTabPanelHTML(action)).join('');

    panel.innerHTML = `
        <div style="padding: 12px 16px; border-bottom: 1px solid rgba(255,255,255,0.1); display:flex; justify-content:space-between; align-items:center; flex-shrink:0;">
            <h3 id="ui-app-title" style="margin:0; color:white; font-size:16px;">${ui('appTitle')}</h3>
            <div style="display:flex; align-items:center; gap:6px;">
                <div id="lang-select-wrap" style="position:relative;">
                    <select id="lang-select" title="${ui('langLabel')}" style="background-color:#20203a; color:#ffffff; border:1px solid rgba(255,255,255,0.25); border-radius:6px; padding:4px 5px; font-size:11px; outline:none; font-family:inherit; max-width:80px;">
                        ${LANGUAGE_OPTIONS.map(o => `<option value="${o.code}" style="background-color:#20203a; color:#ffffff;">${o.label}</option>`).join('')}
                    </select>
                    <div id="lang-hint" style="display:none; position:absolute; top:32px; right:-10px; z-index:20; white-space:nowrap;">
                        <div style="position:relative; background:linear-gradient(135deg,#667eea,#764ba2); color:white; font-size:11px; font-weight:600; padding:7px 10px; border-radius:8px; box-shadow:0 4px 14px rgba(102,126,234,0.5); cursor:pointer;">
                            <div style="position:absolute; top:-6px; right:16px; width:0; height:0; border-left:6px solid transparent; border-right:6px solid transparent; border-bottom:6px solid #667eea;"></div>
                            <span id="lang-hint-text">${ui('langHint')}</span>
                        </div>
                    </div>
                </div>
                <button id="open-settings" title="${ui('menuExtra')}" style="background:none; border:none; color:#ccc; font-size:17px; cursor:pointer; padding:0; width:26px; height:26px; flex-shrink:0; border-radius:6px; transition:background .15s;">⚙️</button>
                <button id="close-panel" style="background:none; border:none; color:white; font-size:22px; cursor:pointer; padding:0; width:26px; height:26px; flex-shrink:0;">×</button>
            </div>
        </div>
        <div id="yt-ai-tabbar" class="yt-ai-tabbar">${tabButtonsHtml}</div>
        <div id="yt-ai-body-wrap" style="position:relative; flex:1; min-height:0;">
            <div id="yt-ai-tab-content-area" style="position:absolute; inset:0; overflow-y:auto; padding: 14px 16px;">
                ${panelsHtml}
            </div>
            <div id="settings-overlay" style="display:none; position:absolute; inset:0; background:linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); overflow-y:auto; padding: 14px 16px; z-index:5;">
                ${buildExtraTabPanelHTML()}
            </div>
        </div>
    `;

    applyDockedStyle(panel, !dockTarget);

    if (dockTarget) {
        dockTarget.prepend(panel);
    } else {
        document.body.appendChild(panel);
    }

    injectStylesOnce();
    wirePanelEvents();
    switchTab('summarize');
    prefetchAllTabs();
}

// Panel iki modda çalışabilir:
//  - Docked (tercih edilen): YouTube'un kendi #secondary sütununa yerleşir,
//    sayfanın doğal bir parçası gibi görünür (örnekteki konum).
//  - Fixed (yedek): #secondary bulunamazsa (örn. Shorts/mobil görünüm) eski
//    sağ-alt köşeye sabit kutu olarak açılır, böylece araç yine de çalışır.
function applyDockedStyle(panel, isFixedFallback) {
    if (isFixedFallback) {
        panel.style.cssText = `
            position: fixed; top: 60px; right: 20px; bottom: 20px;
            width: 440px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.5);
            z-index: 10000; overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: none; flex-direction: column;
        `;
    } else {
        panel.style.cssText = `
            position: relative; width: 100%; box-sizing: border-box;
            height: 640px; margin-bottom: 12px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 12px; box-shadow: 0 4px 16px rgba(0,0,0,0.35);
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: none; flex-direction: column;
        `;
    }
}

function injectStylesOnce() {
    if (document.getElementById('youtube-ai-style')) return;
    const style = document.createElement('style');
    style.id = 'youtube-ai-style';
    style.textContent = `
        @keyframes spin { to { transform: rotate(360deg); } }
        .yt-ai-tabbar {
            display:flex; gap:3px; padding: 0 10px; overflow-x:auto; flex-shrink:0;
            background: rgba(0,0,0,0.22); scrollbar-width: thin;
        }
        .yt-ai-tabbar::-webkit-scrollbar { height: 4px; }
        .yt-ai-tab {
            display:flex; align-items:center; gap:5px; padding: 9px 11px 8px 11px;
            font-size:12px; white-space:nowrap; background: rgba(255,255,255,0.03); color:#999;
            border:none; border-bottom: 2px solid transparent; border-radius: 8px 8px 0 0;
            cursor:pointer; transition: background .15s, color .15s; font-family:inherit;
        }
        .yt-ai-tab:hover { background: rgba(255,255,255,0.08); color: #ccc; }
        .yt-ai-tab.active {
            background: linear-gradient(180deg, rgba(102,126,234,0.28), rgba(118,75,162,0.18));
            color:white; font-weight:600; border-bottom: 2px solid #8b93f0;
        }
        .yt-ai-tab[data-tab="extra"].active { border-bottom-color: #ffd200; }
        .yt-ai-tab-panel { display:none; }
        .yt-ai-tab-panel.active { display:block; }
        .yt-ai-chat-msg { margin: 6px 0; padding: 8px 10px; border-radius: 8px; font-size: 13px; line-height: 1.5; word-wrap: break-word; overflow-wrap: break-word; }
        .yt-ai-chat-user { background: rgba(102,126,234,0.3); color: #fff; margin-left: 20px; }
        .yt-ai-chat-assistant { background: rgba(255,255,255,0.07); color: #eee; margin-right: 20px; }
        .yt-ai-rec-card { background: rgba(255,255,255,0.05); border-radius: 10px; padding: 10px; margin-bottom: 10px; }
        .yt-ai-rec-card iframe { border-radius: 6px; }
        .yt-ai-refine-btn {
            width:100%; padding:10px; border:none; border-radius:9px; cursor:pointer; font-size:12px;
            font-weight:600; color:#3a2a00; background: linear-gradient(135deg,#ffd200,#f7971e);
            box-shadow: 0 3px 10px rgba(247,151,30,0.35); transition: transform .15s, box-shadow .15s;
        }
        .yt-ai-refine-btn:hover { transform: translateY(-1px); box-shadow: 0 5px 14px rgba(247,151,30,0.5); }
        .yt-ai-chat-toggle {
            background:none; border:1px solid rgba(255,255,255,0.25); color:#ccc; border-radius:6px;
            font-size:10px; padding:2px 7px; cursor:pointer; flex-shrink:0;
        }
        .yt-ai-lyric-line { padding: 1px 0; }
        .yt-ai-ts { user-select: none; -webkit-user-select: none; color: #8b93f0; font-weight:600; margin-right: 6px; }
        .yt-ai-lyric { user-select: text; }
        .yt-ai-song-section {
            margin: 10px 0 4px 0; padding: 2px 0; font-weight: 700; font-size: 11px;
            letter-spacing: 0.4px; text-transform: uppercase;
            background: linear-gradient(90deg, #a78bfa, #60a5fa);
            -webkit-background-clip: text; background-clip: text; color: transparent;
        }
        .yt-ai-song-section:first-child { margin-top: 0; }
    `;
    document.head.appendChild(style);
}

function wirePanelEvents() {
    document.getElementById('close-panel').onclick = () => togglePanel();

    const langSelect = document.getElementById('lang-select');
    langSelect.value = getSelectedLang();
    langSelect.addEventListener('change', (e) => {
        setSelectedLang(e.target.value);
        applyUILanguage();
        refetchAllForLanguageChange();
        hideLangHint();
    });
    maybeShowLangHint();

    const gearBtn = document.getElementById('open-settings');
    gearBtn.onmouseover = () => { gearBtn.style.background = 'rgba(255,255,255,0.1)'; };
    gearBtn.onmouseout = () => { gearBtn.style.background = 'none'; };
    gearBtn.onclick = () => toggleSettingsOverlay();

    document.querySelectorAll('.yt-ai-tab').forEach(btn => {
        btn.onclick = () => switchTab(btn.dataset.tab);
    });

    TAB_ACTIONS.forEach(action => wireFeatureTabEvents(action));
    wireExtraTabEvents();
}

// ⚙️ simgesi: Ekstra Özellikler (Sınırsız Chat / Reklam Geçme) artık ayrı bir
// sekme DEĞİL, bu ayar panelinin üstüne overlay olarak açılır/kapanır.
function toggleSettingsOverlay() {
    const overlay = document.getElementById('settings-overlay');
    const isOpen = overlay.style.display === 'block';
    overlay.style.display = isOpen ? 'none' : 'block';
}

function switchTab(tab) {
    document.getElementById('settings-overlay').style.display = 'none';
    document.querySelectorAll('.yt-ai-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    document.querySelectorAll('.yt-ai-tab-panel').forEach(panel => {
        panel.classList.toggle('active', panel.dataset.tabPanel === tab);
    });
}

function togglePanel() {
    createPanel();
    const panel = document.getElementById('youtube-ai-panel');
    const isHidden = (panel.style.display === 'none' || !panel.style.display);
    panel.style.display = isHidden ? 'flex' : 'none';
}

// Dil değişince TÜM görünen arayüz metinlerini (başlık, sekme isimleri) günceller.
// AI cevapları zaten backend'e gönderilen 'lang' parametresiyle doğru dilde üretiliyor;
// bunlar sadece SABİT arayüz metinleri.
function applyUILanguage() {
    const floatBtn = document.getElementById('youtube-ai-button');
    if (floatBtn) floatBtn.innerHTML = ui('appTitle');
    const title = document.getElementById('ui-app-title');
    if (title) title.textContent = ui('appTitle');

    document.querySelectorAll('.yt-ai-tab').forEach(btn => {
        const textEl = btn.querySelector('.yt-ai-tab-text');
        if (textEl) textEl.textContent = tabLabel(btn.dataset.tab);
        btn.title = tabLabel(btn.dataset.tab);
    });

    TAB_ACTIONS.forEach(action => {
        const askEl = document.getElementById(`chat-ask-${action}`);
        if (askEl) askEl.textContent = ui('chatAskAbout', tabLabel(action));
        const inputEl = document.getElementById(`chat-input-${action}`);
        if (inputEl && !inputEl.disabled) inputEl.placeholder = ui('chatPlaceholder');
        const sendEl = document.getElementById(`chat-send-${action}`);
        if (sendEl && !sendEl.disabled) sendEl.textContent = ui('chatSend');
        const refineBtn = document.getElementById(`refine-btn-${action}`);
        if (refineBtn) refineBtn.textContent = ui('refineBtn');
        const noChatEl = document.getElementById(`no-chat-${action}`);
        if (noChatEl) noChatEl.textContent = ui('transcriptNoChat');
    });

    const extraTitle = document.getElementById('extra-title');
    if (extraTitle) extraTitle.textContent = ui('extraTitle');
    const extraSub = document.getElementById('extra-subtitle');
    if (extraSub) extraSub.textContent = ui('extraSubtitle');
    const extraChatTitle = document.getElementById('extra-chat-title');
    if (extraChatTitle) extraChatTitle.textContent = ui('extraUnlimitedChatTitle');
    const extraChatDesc = document.getElementById('extra-chat-desc');
    if (extraChatDesc) extraChatDesc.textContent = ui('extraUnlimitedChatDesc', FREE_CHAT_LIMIT_DISPLAY);
    const extraAdTitle = document.getElementById('extra-ad-title');
    if (extraAdTitle) extraAdTitle.textContent = ui('extraAdSkipTitle');
    const extraAdDesc = document.getElementById('extra-ad-desc');
    if (extraAdDesc) extraAdDesc.textContent = ui('extraAdSkipDesc');

    const langHintText = document.getElementById('lang-hint-text');
    if (langHintText) langHintText.textContent = ui('langHint');
}

// ==================== ÖZELLİK SEKMESİ (sonuç + kapatılabilir sohbet) ====================
function buildFeatureTabPanelHTML(action) {
    const hasChat = !FEATURES_WITHOUT_CHAT.includes(action);
    const unlimitedNow = getPremiumState(PREMIUM_KEYS.unlimitedChat);

    const copyButton = action === 'transcript' ? `
        <button id="copy-btn-${action}" title="${ui('copyBtnTitle')}" style="position:absolute; top:8px; right:8px; width:28px; height:28px; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg,#667eea,#764ba2); border:none; border-radius:7px; cursor:pointer; opacity:0.85; transition:opacity .15s, transform .15s; box-shadow:0 2px 6px rgba(0,0,0,0.25); z-index:2;">
            <svg id="copy-icon-${action}" width="13" height="13" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="pointer-events:none;">
                <rect x="9" y="9" width="12" height="12" rx="2.5" stroke="white" stroke-width="2"/>
                <path d="M5 15H4.5A2.5 2.5 0 0 1 2 12.5v-8A2.5 2.5 0 0 1 4.5 2h8A2.5 2.5 0 0 1 15 4.5V5" stroke="white" stroke-width="2"/>
            </svg>
        </button>
    ` : '';

    const chatBlock = hasChat ? `
        <div id="chat-section-${action}" style="display:none;">
            <div style="border-top:1px solid rgba(255,255,255,0.1); margin: 6px 0 10px 0;"></div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin:0 0 8px 0; gap:8px;">
                <p id="chat-ask-${action}" style="color:#bbb; font-size:12px; margin:0; flex:1;">${ui('chatAskAbout', tabLabel(action))}</p>
                <p id="chat-limit-badge-${action}" style="font-size:10px; margin:0; white-space:nowrap; color:${unlimitedNow ? '#ffd200' : '#999'};">${unlimitedNow ? ui('chatUnlimited') : ui('chatLimitUsed', 0, FREE_CHAT_LIMIT_DISPLAY, FREE_CHAT_LIMIT_DISPLAY)}</p>
                <button id="chat-toggle-${action}" class="yt-ai-chat-toggle">▾</button>
            </div>
            <div id="chat-body-${action}">
                <div id="chat-history-${action}" style="max-height:180px; overflow-y:auto; margin-bottom:8px; word-wrap:break-word;"></div>
                <div style="display:flex; gap:6px;">
                    <input id="chat-input-${action}" type="text" placeholder="${ui('chatPlaceholder')}" style="flex:1; min-width:0; padding:9px 10px; border-radius:8px; border:1px solid rgba(255,255,255,0.2); background:rgba(255,255,255,0.05); color:white; font-size:13px; outline:none;">
                    <button id="chat-send-${action}" style="padding:9px 14px; border:none; border-radius:8px; background:linear-gradient(135deg,#667eea,#764ba2); color:white; font-size:13px; cursor:pointer; flex-shrink:0;">${ui('chatSend')}</button>
                </div>
                <div id="refine-wrap-${action}" style="display:none; margin-top:10px;">
                    <button id="refine-btn-${action}" class="yt-ai-refine-btn">${ui('refineBtn')}</button>
                </div>
            </div>
        </div>
    ` : `
        <p id="no-chat-${action}" style="color:#888; font-size:11px; text-align:center; margin-top:10px;">${ui('transcriptNoChat')}</p>
        <div id="transcript-translate-row" style="display:flex; align-items:center; justify-content:center; gap:8px; margin-top:10px;">
            <span style="color:#999; font-size:11px;">🌐 ${ui('transcriptTranslateLabel')}</span>
            <select id="transcript-translate-select" title="${ui('transcriptTranslateLabel')}" style="background-color:#20203a; color:#ffffff; border:1px solid rgba(255,255,255,0.25); border-radius:6px; padding:4px 6px; font-size:11px; outline:none; font-family:inherit; max-width:150px;">
                <option value="default" style="background-color:#20203a; color:#ffffff;">${ui('translateDefaultOption')}</option>
                ${LANGUAGE_OPTIONS.map(o => `<option value="${o.code}" style="background-color:#20203a; color:#ffffff;">${o.label}</option>`).join('')}
            </select>
        </div>
    `;

    return `
        <div class="yt-ai-tab-panel" data-tab-panel="${action}">
            <div id="loading-${action}" style="text-align:center; color:white; padding: 24px 0;">
                <div style="display:inline-block; width:34px; height:34px; border:4px solid rgba(255,255,255,0.3); border-top-color:white; border-radius:50%; animation: spin 1s linear infinite;"></div>
                <p id="loading-text-${action}" style="margin-top:10px; font-size:12px; color:#bbb;"></p>
            </div>
            <div id="result-wrap-${action}" style="position:relative;">
                <div id="result-${action}" style="display:none; color:white; font-size:13px; line-height:1.6; white-space:pre-wrap; word-wrap:break-word; background:rgba(255,255,255,0.05); border-radius:8px; padding:12px; ${action === 'transcript' ? 'padding-right:40px;' : ''} margin-bottom:14px; max-height:300px; overflow-y:auto;"></div>
                ${copyButton}
            </div>
            <div id="recs-${action}" style="display:none; margin-bottom:14px;"></div>
            ${chatBlock}
        </div>
    `;
}

function wireFeatureTabEvents(action) {
    if (action === 'transcript') {
        const copyBtn = document.getElementById(`copy-btn-${action}`);
        copyBtn.onmouseover = () => { copyBtn.style.opacity = '1'; copyBtn.style.transform = 'scale(1.05)'; };
        copyBtn.onmouseout = () => { copyBtn.style.opacity = '0.85'; copyBtn.style.transform = 'scale(1)'; };
        copyBtn.onclick = () => copyTranscriptText(action);

        const translateSelect = document.getElementById('transcript-translate-select');
        if (translateSelect) translateSelect.onchange = () => handleTranscriptLangChange(translateSelect.value);
        return;
    }

    document.getElementById(`chat-send-${action}`).onclick = () => sendChat(action);
    document.getElementById(`chat-input-${action}`).addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendChat(action);
    });
    // Sohbet, sekme içinden TAŞMASIN diye kendi kutusunda scroll'lu; ayrıca
    // istenirse tamamen kapatılabilir (▾/▸ ile) — panel dışına hiçbir şey çıkmaz.
    document.getElementById(`chat-toggle-${action}`).onclick = (e) => {
        const body = document.getElementById(`chat-body-${action}`);
        const collapsed = body.style.display === 'none';
        body.style.display = collapsed ? 'block' : 'none';
        e.currentTarget.textContent = collapsed ? '▾' : '▸';
    };

    if (action === 'recommendations') {
        document.getElementById(`refine-wrap-${action}`).style.display = 'block';
        document.getElementById(`refine-btn-${action}`).onclick = () => fetchTabData(action, true);
    }

    if (action === 'chapters') {
        document.getElementById(`result-${action}`).addEventListener('click', (e) => {
            const badge = e.target.closest('.yt-ai-chapter-ts');
            if (!badge) return;
            jumpToVideoTime(Number(badge.dataset.seconds));
        });
    }
}

// Muzik videolarinda backend line_mode=true dondurunce her satir "[MM:SS] soz"
// formatindadir. Zaman damgasini kopyalanamaz (user-select:none), sozu
// kopyalanabilir span olarak render eder; kopyala butonu sadece soz spanlerini toplar.
const TRANSCRIPT_LINE_RE = /^\[(\d{1,3}:\d{2}(?::\d{2})?)\]\s?(.*)$/;
// Backend'in ekledigi yapisal etiketler: "[CHORUS]", "[VERSE 1]", "[BRIDGE]" gibi
// -- sadece harf/bosluk/rakamdan olusan, TEK BASINA kendi satirinda duran koseli
// parantez. Gercek [MM:SS] satirlariyla karismasin diye rakam-iki nokta ustuste
// (saat:dakika) formatini ELEMEK icin \d{1,3}:\d{2} deseniyle CAKISMAYAN bir desen.
const SONG_SECTION_RE = /^\[([A-Za-z][A-Za-z ]*\d*)\]$/;

function renderTranscriptResult(result, text, lineMode) {
    if (!lineMode) {
        result.dataset.lineMode = 'false';
        result.textContent = text || '';
        result.style.display = 'block';
        return;
    }
    result.dataset.lineMode = 'true';
    const html = (text || '').split('\n').map(line => {
        const trimmed = line.trim();
        const sectionMatch = trimmed.match(SONG_SECTION_RE);
        if (sectionMatch) {
            return `<div class="yt-ai-song-section">${escapeHtml(trimmed)}</div>`;
        }
        const m = line.match(TRANSCRIPT_LINE_RE);
        if (m) {
            return `<div class="yt-ai-lyric-line"><span class="yt-ai-ts">[${escapeHtml(m[1])}]</span><span class="yt-ai-lyric">${escapeHtml(m[2])}</span></div>`;
        }
        return `<div>${escapeHtml(line)}</div>`;
    }).join('');
    result.innerHTML = html;
    result.style.display = 'block';
}

function copyTranscriptText(action) {
    const result = document.getElementById(`result-${action}`);
    if (!result) return;
    const text = result.dataset.lineMode === 'true'
        ? Array.from(result.querySelectorAll('.yt-ai-lyric')).map(el => el.textContent.trim()).join('\n')
        : (result.textContent || '');

    const showCheck = () => {
        const icon = document.getElementById(`copy-icon-${action}`);
        if (!icon) return;
        icon.innerHTML = `<path d="M4 12.5l5 5L20 6.5" stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`;
        setTimeout(() => {
            const stillThere = document.getElementById(`copy-icon-${action}`);
            if (stillThere) {
                stillThere.innerHTML = `<rect x="9" y="9" width="12" height="12" rx="2.5" stroke="white" stroke-width="2"/><path d="M5 15H4.5A2.5 2.5 0 0 1 2 12.5v-8A2.5 2.5 0 0 1 4.5 2h8A2.5 2.5 0 0 1 15 4.5V5" stroke="white" stroke-width="2"/>`;
            }
        }, 1400);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(showCheck).catch(() => {
            fallbackCopy(text);
            showCheck();
        });
    } else {
        fallbackCopy(text);
        showCheck();
    }
}

function fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* yoksay */ }
    document.body.removeChild(ta);
}

let recCardData = []; // index -> {video_id, backup_video_id, url, _triedBackup}

// ---- YouTube IFrame API (embed hatalarını GÜVENİLİR şekilde yakalamak için) ----
// Önceki sürüm ham <iframe src="..."> + postMessage dinleme kullanıyordu; bu
// YouTube'un resmi el sıkışma protokolünü tam uygulamadığı için "onError"
// mesajları çoğu zaman hiç gelmiyordu (152-4 hatası sessizce kalıyordu).
// Şimdi resmi https://www.youtube.com/iframe_api script'i yükleniyor ve her
// video gerçek bir YT.Player nesnesiyle oynatılıyor -> onError kesin yakalanır.
let ytApiReady = false;
let ytApiLoadingPromise = null;

function loadYouTubeIframeAPI() {
    if (ytApiReady && window.YT && window.YT.Player) return Promise.resolve();
    if (ytApiLoadingPromise) return ytApiLoadingPromise;

    ytApiLoadingPromise = new Promise((resolve) => {
        if (window.YT && window.YT.Player) {
            ytApiReady = true;
            resolve();
            return;
        }
        const previous = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = () => {
            ytApiReady = true;
            if (typeof previous === 'function') previous();
            resolve();
        };
        if (!document.getElementById('yt-ai-iframe-api-script')) {
            const tag = document.createElement('script');
            tag.id = 'yt-ai-iframe-api-script';
            tag.src = 'https://www.youtube.com/iframe_api';
            document.head.appendChild(tag);
        }
    });
    return ytApiLoadingPromise;
}

const ytPlayers = {}; // idx -> YT.Player instance

function createRecPlayer(idx, videoId) {
    const containerId = `rec-player-${idx}`;
    if (!document.getElementById(containerId)) return;
    try {
        ytPlayers[idx] = new YT.Player(containerId, {
            videoId: videoId,
            width: '100%',
            height: '160',
            playerVars: { rel: 0, modestbranding: 1 },
            events: {
                // Hata kodları: 2 (geçersiz id), 5, 100 (bulunamadı/kaldırılmış),
                // 101/150 (embed engelli/yaş sınırı) -> hepsi burada yakalanır.
                onError: () => handleRecEmbedError(idx),
            },
        });
    } catch (e) {
        handleRecEmbedError(idx);
    }
}

function renderRecommendations(recs) {
    const wrap = document.getElementById('recs-recommendations');
    // Önceki video/render'dan kalan player nesnelerini temizle (bellek sızıntısı olmasın)
    Object.keys(ytPlayers).forEach(k => {
        try { ytPlayers[k].destroy(); } catch (e) { /* yoksay */ }
        delete ytPlayers[k];
    });

    // SADECE gerçek bir video bulunmuş öneriler gösterilir -- AI'nın önerdiği
    // ama karşılığında gerçek video bulunamayan başlıklar HİÇ render edilmez
    // (önceden "video bulunamadı" yazan boş bir kart gösteriliyordu, artık
    // öyle bir kart bile açılmıyor).
    const found = (recs || []).filter(r => r.video_id && r.real_title);

    if (found.length === 0) {
        wrap.innerHTML = `<p style="color:#ccc; font-size:13px;">${ui('recNoVideo')}</p>`;
        wrap.style.display = 'block';
        return;
    }

    recCardData = found.map(r => ({ video_id: r.video_id, backup_video_id: r.backup_video_id, url: r.url, _triedBackup: false }));

    wrap.innerHTML = found.map((r, idx) => {
        const link = r.url ? `<a href="${r.url}" target="_blank" style="color:#8ab4f8; font-size:12px; text-decoration:none;">${ui('recWatchOnYoutube')}</a>` : '';
        return `
            <div class="yt-ai-rec-card">
                <p style="color:white; font-weight:600; font-size:13px; margin:0 0 4px 0;">${escapeHtml(r.real_title)}${r.channel ? ' — ' + escapeHtml(r.channel) : ''}</p>
                <p style="color:#ddd; font-size:12px; margin:0 0 8px 0;">${escapeHtml(r.reason || '')}</p>
                <div id="rec-player-wrap-${idx}"><div id="rec-player-${idx}" data-idx="${idx}"></div></div>
                <div style="margin-top:6px;">${link}</div>
            </div>
        `;
    }).join('');
    wrap.style.display = 'block';

    loadYouTubeIframeAPI().then(() => {
        found.forEach((r, idx) => createRecPlayer(idx, r.video_id));
    });
}

// YouTube embed player GERÇEKTEN hata verirse (örn. "Bu video kullanılamıyor" /
// kod 152, 101, 150) önce YEDEK videoya geçer, o da yoksa/hata verirse sadece
// "YouTube'da izle" linkini bırakır. Artık resmi IFrame API üzerinden geldiği
// için bu her zaman tetiklenir (önceki postMessage yöntemi güvenilir değildi).
function handleRecEmbedError(idx) {
    const card = recCardData[idx];
    if (!card) return;
    const wrap = document.getElementById(`rec-player-wrap-${idx}`);
    if (!wrap) return;

    if (ytPlayers[idx]) {
        try { ytPlayers[idx].destroy(); } catch (e) { /* yoksay */ }
        delete ytPlayers[idx];
    }

    if (card.backup_video_id && !card._triedBackup) {
        card._triedBackup = true;
        wrap.innerHTML = `<div id="rec-player-${idx}" data-idx="${idx}"></div>`;
        createRecPlayer(idx, card.backup_video_id);
    } else {
        wrap.innerHTML = `<p style="color:#999; font-size:12px;">${ui('recEmbedError')} <a href="${card.url || ''}" target="_blank" style="color:#8ab4f8;">${ui('recWatchOnYoutube')}</a></p>`;
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// AI ozet/analiz/bolum ciktilarinda bazen "**kalin metin**" gibi basit markdown
// isaretlemesi geliyor; duz metin olarak gosterilince yildizlar oldugu gibi
// goruniyordu. Once HTML-escape edilir (guvenlik), SONRA **..** kaliplari
// <strong> etiketine cevrilir -- boylece kullanici girdisi/AI ciktisi HTML
// injection riski tasimadan kalin gosterilebiliyor.
function renderMarkdownLite(text) {
    const escaped = escapeHtml(text || '');
    return escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

// Bolumler metnindeki "[MM:SS]" / "[H:MM:SS]" zaman damgalarini yakalar (backend
// bolumleri hep bu formatta uretiyor: "[MM:SS] Baslik - aciklama").
const CHAPTER_TIMESTAMP_RE = /\[(\d{1,3}:\d{2}(?::\d{2})?)\]/g;

function timestampToSeconds(ts) {
    const parts = ts.split(':').map(Number);
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    return 0;
}

// YouTube'un kendi <video> elementine dogrudan erisip o saniyeye sarar --
// eklenti zaten sayfaya gomulu (content script) oldugu icin ekstra bir API'ye
// gerek yok, ayni YouTube'un kendi "sonraki bolum" tiklamasi gibi calisir.
function jumpToVideoTime(seconds) {
    const video = document.querySelector('video');
    if (!video) return;
    video.currentTime = seconds;
    video.play().catch(() => { /* otoplay engellenirse sessizce yoksay */ });
}

// renderMarkdownLite ile AYNI (escape + **kalin**) ama ayrica [MM:SS] etiketlerini
// tiklanabilir rozete cevirir -- SADECE Bolumler sekmesinde kullanilir (Ozet/Analiz
// metinlerinde zaman damgasi anlamli olmadigi icin onlar duz renderMarkdownLite kalir).
function renderChaptersWithTimestamps(text) {
    const escaped = escapeHtml(text || '');
    const bolded = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return bolded.replace(CHAPTER_TIMESTAMP_RE, (match, ts) => {
        const seconds = timestampToSeconds(ts);
        return `<span class="yt-ai-chapter-ts" data-seconds="${seconds}" title="${ts}'e git" style="display:inline-block; background:linear-gradient(135deg,#667eea,#764ba2); color:white; font-weight:600; border-radius:5px; padding:1px 7px; margin-right:4px; cursor:pointer; font-size:12px; user-select:none;">${ts}</span>`;
    });
}

function renderChatHistory(action, messages) {
    const box = document.getElementById(`chat-history-${action}`);
    if (!box) return;
    box.innerHTML = messages.map(m =>
        `<div class="yt-ai-chat-msg yt-ai-chat-${m.role === 'user' ? 'user' : 'assistant'}">${escapeHtml(m.content)}</div>`
    ).join('');
    box.scrollTop = box.scrollHeight;
}

const chatMessagesByAction = {}; // sadece görüntü için lokal geçmiş (backend de kendi geçmişini tutuyor)

async function sendChat(action) {
    const input = document.getElementById(`chat-input-${action}`);
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    chatMessagesByAction[action] = chatMessagesByAction[action] || [];
    chatMessagesByAction[action].push({ role: 'user', content: message });
    renderChatHistory(action, chatMessagesByAction[action]);

    const sendBtn = document.getElementById(`chat-send-${action}`);
    sendBtn.disabled = true;
    sendBtn.textContent = '...';

    try {
        const unlimited = getPremiumState(PREMIUM_KEYS.unlimitedChat);
        const data = await callBackendAPI('/api/chat', {
            url: window.location.href,
            feature: action,
            message,
            unlimited,
            lang: getSelectedLang()
        });
        chatMessagesByAction[action].push({ role: 'assistant', content: data.reply });
        renderChatHistory(action, chatMessagesByAction[action]);
        updateChatLimitBadge(action, data);

        if (data.limit_reached) {
            input.disabled = true;
            input.placeholder = ui('chatLimitPlaceholder');
            sendBtn.disabled = true;
            sendBtn.textContent = ui('chatSend');
            return;
        }
    } catch (error) {
        chatMessagesByAction[action].push({ role: 'assistant', content: `${ui('errorPrefix')} ${error.message}` });
        renderChatHistory(action, chatMessagesByAction[action]);
    } finally {
        if (!input.disabled) {
            sendBtn.disabled = false;
            sendBtn.textContent = ui('chatSend');
        }
    }
}

function updateChatLimitBadge(action, data) {
    const badge = document.getElementById(`chat-limit-badge-${action}`);
    if (!badge) return;
    if (data.unlimited) {
        badge.textContent = ui('chatUnlimited');
        badge.style.color = '#ffd200';
    } else if (typeof data.used === 'number' && typeof data.limit === 'number') {
        const remaining = Math.max(0, data.limit - data.used);
        badge.textContent = ui('chatLimitUsed', data.used, data.limit, remaining);
        badge.style.color = remaining === 0 ? '#ff8080' : '#999';
    }
}

function getVideoIdFromCurrentUrl() {
    try {
        return new URLSearchParams(location.search).get('v') || '';
    } catch (e) { return ''; }
}

// /api/prepare çalışırken ~1 saniyede bir gerçek ilerleme durumunu sorar ve
// yükleme metnini günceller — böylece 30 saniye boyunca donuk bir "yükleniyor"
// yazısı yerine "altyazı aranıyor / ses indiriliyor" gibi gerçek adımlar görünür.
async function pollPrepareStatus(videoId, stopSignal) {
    while (!stopSignal.stopped) {
        try {
            const res = await fetch(`${BACKEND_URL}/api/prepare-status?video_id=${encodeURIComponent(videoId)}`);
            if (res.ok) {
                const data = await res.json();
                const text = ui('prepareStatus_' + data.status) || ui('loadingPreparing');
                TAB_ACTIONS.forEach(action => {
                    const loadingText = document.getElementById(`loading-text-${action}`);
                    if (loadingText && loadingText.closest('.yt-ai-tab-panel')) loadingText.textContent = text;
                });
                if (data.status === 'done' || data.status === 'failed') break;
            }
        } catch (e) { /* yoksay, bir sonraki turda tekrar dener */ }
        await new Promise(r => setTimeout(r, 900));
    }
}

// Panel açılır açılmaz TÜM sekmeler PARALEL olarak arka planda getirilir; kullanıcı
// bir sekmeye tıkladığında çoğunlukla veri zaten hazırdır (ışık hızı hissi).
// HIZ İÇİN KRİTİK: Önce transkripti TEK SEFERDE hazırlatıyoruz (/api/prepare).
// Bu olmadan 5 sekme aynı anda ayrı ayrı transkript çıkarmaya çalışırdı (özellikle
// altyazısız videolarda 5 kere ses indirip Whisper çalıştırmak anlamına gelirdi).
// Hazırlık bitince 5 sekme paralel çekilir; artık her biri sadece cache'lenmiş
// transkripti okuyup kendi Groq çağrısını yaptığı için gerçekten hızlıdır.
async function prefetchAllTabs() {
    TAB_ACTIONS.forEach(action => {
        const loadingText = document.getElementById(`loading-text-${action}`);
        if (loadingText) loadingText.textContent = ui('loadingPreparing');
        const loading = document.getElementById(`loading-${action}`);
        if (loading) loading.style.display = 'block';
        const result = document.getElementById(`result-${action}`);
        if (result) result.style.display = 'none';
    });

    const videoId = getVideoIdFromCurrentUrl();
    const stopSignal = { stopped: false };
    if (videoId) pollPrepareStatus(videoId, stopSignal);

    let prepareData = null;
    try {
        prepareData = await callBackendAPI('/api/prepare', { url: window.location.href, lang: getSelectedLang() });
    } catch (error) {
        // Hazırlık başarısız olsa bile sekmeleri tek tek denemeye bırakıyoruz;
        // her biri kendi hata mesajını gösterecek.
    } finally {
        stopSignal.stopped = true;
    }

    // /api/prepare ZATEN özet/analiz/bölüm içeriğini üretip döndürdüyse (normal
    // durum), bu 3 sekmeyi ayrı bir istek + loading yanıp-sönmesi olmadan
    // DOĞRUDAN göster -- veri zaten elimizde, beklemeye gerek yok.
    const directActions = ['summarize', 'analyze', 'chapters'];
    directActions.forEach(action => {
        if (prepareData && prepareData[action === 'summarize' ? 'summary' : action === 'analyze' ? 'analysis' : 'chapters']) {
            applyTabResult(action, prepareData);
        } else {
            fetchTabData(action, false);
        }
    });
    fetchTabData('recommendations', false);
    fetchTabData('transcript', false);
}

// Kullanıcı dili değiştirdiğinde SADECE arayüz etiketleri değil, AI'nin ürettiği
// SONUÇLAR (özet/analiz/bölüm/öneri) da yeni dile göre yeniden üretilir. Sohbet
// geçmişi de görsel olarak sıfırlanır (eski dildeki mesajlar karışık durmasın).
function refetchAllForLanguageChange() {
    TAB_ACTIONS.forEach(action => {
        chatMessagesByAction[action] = [];
        const historyBox = document.getElementById(`chat-history-${action}`);
        if (historyBox) historyBox.innerHTML = '';
        const badge = document.getElementById(`chat-limit-badge-${action}`);
        if (badge && !getPremiumState(PREMIUM_KEYS.unlimitedChat)) {
            badge.textContent = ui('chatLimitUsed', 0, FREE_CHAT_LIMIT_DISPLAY, FREE_CHAT_LIMIT_DISPLAY);
            badge.style.color = '#999';
        }
        const input = document.getElementById(`chat-input-${action}`);
        if (input) { input.disabled = false; input.placeholder = ui('chatPlaceholder'); }
        const sendBtn = document.getElementById(`chat-send-${action}`);
        if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = ui('chatSend'); }
    });
    prefetchAllTabs();
}

// Bir sekmenin sonucunu (fetch'ten ya da /api/prepare cevabında ZATEN hazır
// gelen içerikten) ekrana basar -- loading yanıp-sönmesi yaratmadan, doğrudan.
function applyTabResult(action, data) {
    const loading = document.getElementById(`loading-${action}`);
    const result = document.getElementById(`result-${action}`);
    const chatSection = document.getElementById(`chat-section-${action}`);

    loading.style.display = 'none';
    if (chatSection) chatSection.style.display = 'block';
    if (!chatMessagesByAction[action]) chatMessagesByAction[action] = [];

    if (action === 'summarize') { result.innerHTML = renderMarkdownLite(data.summary); result.style.display = 'block'; }
    else if (action === 'analyze') { result.innerHTML = renderMarkdownLite(data.analysis); result.style.display = 'block'; }
    else if (action === 'chapters') {
        if (data.chapters && data.chapters.trim()) {
            result.innerHTML = renderChaptersWithTimestamps(data.chapters);
        } else {
            result.textContent = ui('chaptersEmpty');
        }
        result.style.display = 'block';
    }
    else if (action === 'recommendations') { renderRecommendations(data.recommendations); }
    else if (action === 'transcript') {
        transcriptOriginal.text = data.transcript;
        transcriptOriginal.lineMode = !!data.line_mode;
        transcriptOriginal.detectedLang = data.detected_lang || null;
        transcriptTranslationCache = {};
        transcriptCurrentLang = 'default';
        renderTranscriptResult(result, data.transcript, !!data.line_mode);
        updateTranscriptTranslateOptions(transcriptOriginal.detectedLang);
    }
}

// Transkriptin algilanan orijinal diline gore cevir dropdown'unu yeniden kurar:
// "Varsayilan" secenegi artik o dilin adini gosterir (orn. "Varsayilan
// (Ingilizce)") ve o dil, ayrica cevrilebilecek diger diller listesinden
// cikarilir (zaten "Varsayilan" onu karsiliyor, tekrar gostermeye gerek yok).
function updateTranscriptTranslateOptions(detectedLang) {
    const select = document.getElementById('transcript-translate-select');
    if (!select) return;
    const uiIsTr = getSelectedLang() === 'tr';
    const match = detectedLang ? LANGUAGE_OPTIONS.find(o => o.code === detectedLang) : null;
    const localizedName = match ? (uiIsTr ? match.nameTr : match.nameEn) : null;
    const defaultLabel = ui('translateDefaultOption', localizedName);
    const otherOptions = detectedLang ? LANGUAGE_OPTIONS.filter(o => o.code !== detectedLang) : LANGUAGE_OPTIONS;
    select.innerHTML = `
        <option value="default">${defaultLabel}</option>
        ${otherOptions.map(o => `<option value="${o.code}">${o.label}</option>`).join('')}
    `;
    select.value = 'default';
}

// Transkript her zaman "varsayilan" (videodaki konusulan orijinal dil) ile
// acilir. Kullanici dropdown'dan baska bir dil secerse, o dile AI ile cevrilir
// (backend: /api/transcript/translate) ve dil bazinda cache'lenir -- ayni
// videoda diller arasi gidip gelince tekrar istek atmaz.
const transcriptOriginal = { text: null, lineMode: false, detectedLang: null };
let transcriptTranslationCache = {};
let transcriptCurrentLang = 'default';

// Backend'in /api/transcript/translate/stream ucundan SSE (Server-Sent Events)
// okur. Parcalar Groq/OpenRouter'dan HANGISI once biterse o sirada gelir (paralel
// isleniyor), ama okuma sirasini bozmamak icin sadece BASTAN itibaren ARDIL
// (bosluksuz) parcalar hazir oldukca disari verilir -- 3. parca 1. parcadan once
// bitse bile, 1. parca gelmeden ekrana hicbir sey basilmaz.
async function streamTranscriptTranslation(lang, onProgress, onDone, onError) {
    let response;
    try {
        const apiKeys = await getSyncedApiKeys();
        response = await fetch(`${BACKEND_URL}/api/transcript/translate/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: window.location.href, lang, api_keys: apiKeys })
        });
    } catch (e) {
        onError(e);
        return;
    }
    if (!response.ok || !response.body) {
        onError(new Error(`HTTP ${response.status}`));
        return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    const chunksByIdx = {};
    let nextIdx = 0;

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split('\n\n');
            buffer = events.pop();
            for (const evt of events) {
                if (!evt.startsWith('data: ')) continue;
                let payload;
                try { payload = JSON.parse(evt.slice(6)); } catch (e) { continue; }
                if (payload.error) { onError(new Error(payload.error)); return; }
                if (payload.done) { onDone(); return; }
                chunksByIdx[payload.chunk_id] = payload.text;
                while (chunksByIdx[nextIdx] !== undefined) {
                    onProgress(nextIdx, chunksByIdx[nextIdx]);
                    nextIdx++;
                }
            }
        }
        onDone();
    } catch (e) {
        onError(e);
    }
}

async function handleTranscriptLangChange(lang) {
    const result = document.getElementById('result-transcript');
    const select = document.getElementById('transcript-translate-select');
    if (!result || !transcriptOriginal.text) return;

    transcriptCurrentLang = lang;

    if (lang === 'default') {
        renderTranscriptResult(result, transcriptOriginal.text, transcriptOriginal.lineMode);
        return;
    }

    if (transcriptTranslationCache[lang]) {
        renderTranscriptResult(result, transcriptTranslationCache[lang], false);
        return;
    }

    const prevHTML = result.innerHTML;
    select.disabled = true;
    result.textContent = ui('translatingText');
    result.style.display = 'block';
    const parts = [];

    await streamTranscriptTranslation(
        lang,
        (idx, text) => {
            // Yayin surerken kullanici baska bir dile/varsayilana gecmis olabilir --
            // hala ayni secimdeyse ekrani guncelle, degilse sessizce yok say.
            if (transcriptCurrentLang !== lang) return;
            parts[idx] = text;
            result.textContent = parts.join('\n') + '\n\n⏳';
        },
        () => {
            select.disabled = false;
            if (transcriptCurrentLang !== lang) return;
            const full = parts.join('\n');
            transcriptTranslationCache[lang] = full;
            result.textContent = full;
        },
        (error) => {
            select.disabled = false;
            result.innerHTML = prevHTML;
            select.value = 'default';
            transcriptCurrentLang = 'default';
        }
    );
}

async function fetchTabData(action, refine) {
    const loading = document.getElementById(`loading-${action}`);
    const loadingText = document.getElementById(`loading-text-${action}`);
    const result = document.getElementById(`result-${action}`);
    const recsWrap = document.getElementById(`recs-${action}`);
    const chatSection = document.getElementById(`chat-section-${action}`); // transcript'te yok, null olabilir

    loading.style.display = 'block';
    loadingText.textContent = action === 'recommendations'
        ? (refine ? ui('loadingRecommendationsRefine') : ui('loadingRecommendations'))
        : ui('loadingGeneric');
    result.style.display = 'none';
    recsWrap.style.display = 'none';
    if (chatSection) chatSection.style.display = 'none';

    try {
        const payload = { url: window.location.href, lang: getSelectedLang() };
        if (action === 'recommendations' && refine) payload.refine = true;

        const data = await callBackendAPI(`/api/${action}`, payload);
        applyTabResult(action, data);
    } catch (error) {
        loading.style.display = 'none';
        result.textContent = `${ui('errorPrefix')} ${error.message}`;
        result.style.display = 'block';
    }
}

// ==================== ⭐ EKSTRA ÖZELLİKLER (PREMIUM) SEKMESİ ====================
// NOT: Bu, sadece kendi kullanımınız için yerel bir araç olduğundan gerçek bir
// ödeme/lisans sistemi yok. "Premium" burada görsel bir ayrım; iki özellik de
// açma/kapama anahtarıyla siz kontrol edersiniz. Tercihler tarayıcıda
// (localStorage, youtube.com alan adına özel) saklanır, kalıcıdır.

const FREE_CHAT_LIMIT_DISPLAY = 3; // backend'deki FREE_CHAT_MESSAGE_LIMIT ile aynı olmalı (sadece gösterim için)

// GERÇEK lisans doğrulaması: kendi sunucumuz YOK -- doğrudan Lemon Squeezy'nin
// kendi "License API"sine soruyoruz (kendi anahtar üretimlerini/saklamalarını
// KULLANIYORUZ, kendi webhook+veritabanımızı KURMUYORUZ). Bu, tek bir yerde
// tek bir "gerçek" lisans kaynağı olmasını garanti eder -- iki ayrı sistem
// (bizim + Lemon Squeezy'nin) birbirinden habersiz farklı anahtarlar üretip
// kafa karıştırmasın diye BİLEREK bu şekilde kuruldu.
const LICENSE_MARKETING_URL = 'https://digitalhelperforall.lemonsqueezy.com';
const LS_LICENSE_API_BASE = 'https://api.lemonsqueezy.com/v1/licenses';

// Lemon Squeezy'de 3 urunu (Bundle/Unlimited Chat/Ad Skip) olusturduktan
// sonra HER BIRININ variant ID'sini buraya yazin -- urun sayfasinin
// URL'sinde veya Lemon Squeezy API'sinde gorunur (sayisal bir ID, orn. 123456).
// Doldurulmadan gercek anahtarlarin hangi ozelligi actigi BILINEMEZ (en genis
// pakete dusulur, magdur etmemek icin).
const LS_VARIANT_TO_PLAN = {
    // 123456: 'bundle',
    // 123457: 'chat',
    // 123458: 'adskip',
};

function planFromLemonSqueezyVariant(variantId) {
    return LS_VARIANT_TO_PLAN[variantId] || 'bundle';
}

const PREMIUM_KEYS = {
    unlimitedChat: 'ytai_premium_unlimited_chat_enabled',
    adSkip: 'ytai_premium_adskip_enabled',
};
const LICENSE_KEY_STORAGE = 'ytai_license_key';
const LICENSE_PLAN_STORAGE = 'ytai_license_plan';
// Lemon Squeezy'nin "activate" cagrisi bir "instance" olusturur ve bir ID doner --
// bu ID'yi saklayip sonraki dogrulamalarda kullanmazsak, her sayfa yenilemede
// yeniden activate cagirmak zorunda kalirdik (activation_limit'e carpabilir).
const LICENSE_INSTANCE_ID_STORAGE = 'ytai_license_instance_id';

// Kullanicinin kendi AI saglayici anahtarlari artik .env dosyasina degil
// chrome.storage.sync'e yaziliyor -- Chrome hesabina baglandigi icin ayni
// hesapla giris yapilan HER bilgisayarda otomatik gorunur, elle .env
// duzenlemeye veya ayri bir kurulum sihirbazi calistirmaya gerek kalmaz.
// Yerel backend bu anahtarlari KENDISI SAKLAMAZ -- her API cagrisinda
// (bkz. callBackendAPI) birlikte gonderilir, backend surec-genelinde
// bellekte tutar (bkz. server.py: _apply_key_overrides).
const SYNCED_API_KEYS_STORAGE = 'ytai_api_keys';
const SYNCED_API_KEY_FIELDS = [
    { key: 'GROQ_API_KEY', label: 'Groq (önerilen)' },
    { key: 'OPENROUTER_API_KEY', label: 'OpenRouter (yedek)' },
    { key: 'FREELLMAPI_API_KEY', label: 'FreeLLMAPI (tek anahtar alternatifi)' },
    { key: 'ASSEMBLYAI_API_KEY_SUMMARIZE', label: 'AssemblyAI - Özetleyici' },
    { key: 'ASSEMBLYAI_API_KEY_CHAPTERS', label: 'AssemblyAI - Bölümleyici' },
    { key: 'EXA_SEARCH_API_KEY', label: 'Exa Search' },
    { key: 'OMNIROUTE_KEY_CHAT', label: 'OmniRoute - Chat' },
    { key: 'OMNIROUTE_KEY_SUMMARIZE', label: 'OmniRoute - Özetleyici' },
    { key: 'OMNIROUTE_KEY_ANALYZE', label: 'OmniRoute - Transkriptor' },
    { key: 'OMNIROUTE_KEY_RECOMMENDATIONS', label: 'OmniRoute - Video önerici' },
    { key: 'OMNIROUTE_KEY_CHAPTERS', label: 'OmniRoute - Video bölümleyici' },
];

function getSyncedApiKeys() {
    return new Promise((resolve) => {
        try {
            chrome.storage.sync.get([SYNCED_API_KEYS_STORAGE], (result) => {
                resolve((result && result[SYNCED_API_KEYS_STORAGE]) || {});
            });
        } catch (e) { resolve({}); }
    });
}

function setSyncedApiKeys(keys) {
    return new Promise((resolve) => {
        try {
            chrome.storage.sync.set({ [SYNCED_API_KEYS_STORAGE]: keys }, () => resolve(true));
        } catch (e) { resolve(false); }
    });
}

async function pushApiKeysToBackend(keys) {
    try {
        const res = await fetch(`${BACKEND_URL}/api/keys/sync`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_keys: keys }),
        });
        return res.ok;
    } catch (e) {
        return false;
    }
}

function getStoredInstanceId() {
    try { return localStorage.getItem(LICENSE_INSTANCE_ID_STORAGE) || ''; } catch (e) { return ''; }
}

// GEÇİCİ: Lemon Squeezy mağaza başvurumuzu reddetti (hesap satışa açılamadı),
// yani şu an gerçek bir ödeme/lisans akışı YOK. Ürün de henüz kimse tarafından
// bilinmediği için, satılamayan bir özelliği kilitli tutmanın anlamı yok --
// ⭐ Extra Features herkese ÜCRETSİZ açık. Lemon Squeezy tarafı (ileride bir
// itiraz/başka bir işlemci ile) tekrar aktif olursa, bu iki değeri false'a
// çevirip verifyLicenseKey akışını (aşağıda hâlâ duruyor, silinmedi) yeniden
// bağlamak yeterli.
const LIVE_PREMIUM_STATE = { unlimitedChat: true, adSkip: true };

function getPremiumState(key) {
    if (key === PREMIUM_KEYS.unlimitedChat) return LIVE_PREMIUM_STATE.unlimitedChat;
    if (key === PREMIUM_KEYS.adSkip) return LIVE_PREMIUM_STATE.adSkip;
    return false;
}
function setPremiumState(key, value) {
    if (key === PREMIUM_KEYS.unlimitedChat) LIVE_PREMIUM_STATE.unlimitedChat = !!value;
    else if (key === PREMIUM_KEYS.adSkip) LIVE_PREMIUM_STATE.adSkip = !!value;
}
function getStoredLicenseKey() {
    try { return localStorage.getItem(LICENSE_KEY_STORAGE) || ''; } catch (e) { return ''; }
}

// Lemon Squeezy License API'sinin GEREKSINIMLERI (kendi belgelerinden):
// - Content-Type: application/x-www-form-urlencoded (JSON DEGIL)
// - Accept: application/json
// - Anahtar durumu: "inactive" (hic aktivasyonu yok) | "active" (>=1 aktivasyon
//   var) | "expired" | "disabled". YENI SATIN ALINAN bir anahtar BASLANGICTA
//   "inactive" -- SADECE validate cagirmak yetmez, "active" olmasi icin ONCE
//   activate cagrilmasi SART.
async function callLemonSqueezyLicenseAPI(endpoint, params) {
    const res = await fetch(`${LS_LICENSE_API_BASE}/${endpoint}`, {
        method: 'POST',
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams(params).toString(),
    });
    return res.json();
}

// Lisans anahtarını doğrudan Lemon Squeezy'ye sorar, sonucu localStorage'a
// yazar (getPremiumState hâlâ AYNI PREMIUM_KEYS'i okur -- bu yüzden chat/
// ad-skip'i kullanan mevcut kod hiç değişmeden çalışmaya devam eder). Ağ
// hatasında son bilinen durumu KORUR, kullanıcıyı geçici bir bağlantı
// sorununda cezalandırmaz.
async function verifyLicenseKey(key) {
    if (!key) {
        setPremiumState(PREMIUM_KEYS.unlimitedChat, false);
        setPremiumState(PREMIUM_KEYS.adSkip, false);
        localStorage.removeItem(LICENSE_PLAN_STORAGE);
        localStorage.removeItem(LICENSE_INSTANCE_ID_STORAGE);
        return { valid: false };
    }
    try {
        let data;
        const storedInstanceId = getStoredInstanceId();
        if (storedInstanceId) {
            // Daha once bu tarayicida aktiflestirilmis -- sadece dogrula, YENIDEN
            // activate CAGIRMA (gereksiz bir aktivasyon daha tuketir).
            data = await callLemonSqueezyLicenseAPI('validate', { license_key: key, instance_id: storedInstanceId });
        } else {
            // Ilk kez giriliyor: "inactive" -> "active" GECISI icin activate SART.
            data = await callLemonSqueezyLicenseAPI('activate', { license_key: key, instance_name: 'YouTube Assistant Extension' });
            if (data && data.instance && data.instance.id) {
                localStorage.setItem(LICENSE_INSTANCE_ID_STORAGE, data.instance.id);
            }
        }

        const status = data && data.license_key ? data.license_key.status : null;
        const isValid = !!(data && (data.valid || data.activated)) && status === 'active';
        const variantId = data && data.meta ? data.meta.variant_id : null;
        const plan = isValid ? planFromLemonSqueezyVariant(variantId) : '';
        const features = {
            unlimited_chat: isValid && (plan === 'bundle' || plan === 'chat'),
            ad_skip: isValid && (plan === 'bundle' || plan === 'adskip'),
        };

        setPremiumState(PREMIUM_KEYS.unlimitedChat, features.unlimited_chat);
        setPremiumState(PREMIUM_KEYS.adSkip, features.ad_skip);
        localStorage.setItem(LICENSE_PLAN_STORAGE, plan);
        return { valid: isValid, status, plan, features, error: data && data.error };
    } catch (e) {
        console.warn('Lemon Squeezy lisans servisine ulaşılamadı, son bilinen durum korunuyor:', e);
        return { valid: null, networkError: true };
    }
}

function buildExtraTabPanelHTML() {
    const chatOn = getPremiumState(PREMIUM_KEYS.unlimitedChat);
    const adSkipOn = getPremiumState(PREMIUM_KEYS.adSkip);

    return `
        <div style="display:flex; justify-content:space-between; align-items:center; margin:0 0 4px 0;">
            <h4 id="extra-title" style="color:#ffd200; margin:0; font-size:15px;">${ui('extraTitle')}</h4>
            <button id="close-settings" style="background:none; border:none; color:#ccc; font-size:20px; cursor:pointer; padding:0; width:24px; height:24px;">×</button>
        </div>
        <p id="extra-subtitle" style="color:#999; font-size:11px; margin:0 0 12px 0;">${ui('extraSubtitle')}</p>

        <div style="background:rgba(79,214,163,0.08); border:1px solid rgba(79,214,163,0.25); border-radius:10px; padding:12px; margin-bottom:14px;">
            <p style="color:#4fd6a3; font-weight:600; font-size:12px; margin:0;">🎉 Şu anda herkese ücretsiz</p>
            <p style="color:#bbb; font-size:11px; margin:6px 0 0;">Aşağıdaki iki özellik geçici olarak lisans anahtarı gerekmeden herkese açık.</p>
        </div>

        <div style="background:${chatOn ? 'rgba(255,210,0,0.06)' : 'rgba(255,255,255,0.03)'}; border:1px solid ${chatOn ? 'rgba(255,210,0,0.18)' : 'rgba(255,255,255,0.08)'}; border-radius:10px; padding:12px; margin-bottom:12px; opacity:${chatOn ? '1' : '0.7'};">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <p id="extra-chat-title" style="color:white; font-weight:600; font-size:13px; margin:0;">${ui('extraUnlimitedChatTitle')}</p>
                <span style="font-size:11px; font-weight:700; color:${chatOn ? '#4fd6a3' : '#666'};">${chatOn ? '✓' : '—'}</span>
            </div>
            <p id="extra-chat-desc" style="color:#bbb; font-size:11px; margin:0;">${ui('extraUnlimitedChatDesc', FREE_CHAT_LIMIT_DISPLAY)}</p>
        </div>

        <div style="background:${adSkipOn ? 'rgba(255,210,0,0.06)' : 'rgba(255,255,255,0.03)'}; border:1px solid ${adSkipOn ? 'rgba(255,210,0,0.18)' : 'rgba(255,255,255,0.08)'}; border-radius:10px; padding:12px; opacity:${adSkipOn ? '1' : '0.7'};">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <p id="extra-ad-title" style="color:white; font-weight:600; font-size:13px; margin:0;">${ui('extraAdSkipTitle')}</p>
                <span style="font-size:11px; font-weight:700; color:${adSkipOn ? '#4fd6a3' : '#666'};">${adSkipOn ? '✓' : '—'}</span>
            </div>
            <p id="extra-ad-desc" style="color:#bbb; font-size:11px; margin:0;">${ui('extraAdSkipDesc')}</p>
        </div>

        <details style="background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); border-radius:10px; padding:12px; margin-top:12px;">
            <summary style="color:#bbb; font-size:12px; cursor:pointer; outline:none;">🔑 API Anahtarları</summary>
            <p style="color:#777; font-size:10px; margin:8px 0; line-height:1.4;">
                Sadece Groq (veya tek başına FreeLLMAPI) yeterlidir, gerisi isteğe bağlıdır.
                Buraya girilenler bu bilgisayarda değil, Chrome hesabınıza (chrome.storage.sync)
                kaydedilir -- aynı hesapla giriş yaptığınız diğer bilgisayarlarda da otomatik görünür,
                .env dosyası düzenlemeye gerek kalmaz.
            </p>
            <div id="api-keys-fields">
                ${SYNCED_API_KEY_FIELDS.map(({ key, label }) => `
                    <div style="margin-bottom:6px;">
                        <label style="color:#999; font-size:10px; display:block; margin-bottom:2px;">${label}</label>
                        <input id="api-key-input-${key}" type="password"
                            style="width:100%; box-sizing:border-box; padding:6px 8px; border-radius:6px; border:1px solid rgba(255,255,255,0.15); background:rgba(255,255,255,0.05); color:white; font-size:11px; font-family:ui-monospace,monospace; outline:none;">
                    </div>
                `).join('')}
            </div>
            <button id="api-keys-save-btn" style="margin-top:6px; padding:7px 14px; border:none; border-radius:8px; background:linear-gradient(135deg,#ffd200,#ff9d00); color:#1a1a1a; font-weight:700; font-size:12px; cursor:pointer;">Kaydet</button>
            <p id="api-keys-status" style="font-size:11px; margin:8px 0 0;"></p>
        </details>
    `;
}

function refreshExtraTabFeatureBadges() {
    const chatOn = getPremiumState(PREMIUM_KEYS.unlimitedChat);
    const adSkipOn = getPremiumState(PREMIUM_KEYS.adSkip);
    TAB_ACTIONS.forEach(action => {
        const badge = document.getElementById(`chat-limit-badge-${action}`);
        if (!badge) return;
        if (chatOn) {
            badge.textContent = ui('chatUnlimited');
            badge.style.color = '#ffd200';
        } else {
            badge.textContent = ui('chatLimitUsed', 0, FREE_CHAT_LIMIT_DISPLAY, FREE_CHAT_LIMIT_DISPLAY);
            badge.style.color = '#999';
        }
    });
    if (adSkipOn) startAdAutoSkip(); else stopAdAutoSkip();
}

function wireExtraTabEvents() {
    document.getElementById('close-settings').onclick = () => toggleSettingsOverlay();

    // API anahtarları alanlarını chrome.storage.sync'ten doldur (input'lar
    // buildExtraTabPanelHTML'de senkron/boş çizildiği için buradan asenkron
    // olarak dolduruluyor).
    getSyncedApiKeys().then((keys) => {
        SYNCED_API_KEY_FIELDS.forEach(({ key }) => {
            const field = document.getElementById(`api-key-input-${key}`);
            if (field && keys[key]) field.value = keys[key];
        });
    });

    const apiKeysSaveBtn = document.getElementById('api-keys-save-btn');
    const apiKeysStatus = document.getElementById('api-keys-status');
    if (apiKeysSaveBtn) {
        apiKeysSaveBtn.onclick = async () => {
            const keys = {};
            SYNCED_API_KEY_FIELDS.forEach(({ key }) => {
                const field = document.getElementById(`api-key-input-${key}`);
                if (field) keys[key] = field.value.trim();
            });
            apiKeysSaveBtn.disabled = true;
            apiKeysStatus.style.color = '#999';
            apiKeysStatus.textContent = 'Kaydediliyor...';

            await setSyncedApiKeys(keys);
            const pushed = await pushApiKeysToBackend(keys);

            apiKeysStatus.style.color = pushed ? '#4fd6a3' : '#ff9d00';
            apiKeysStatus.textContent = pushed
                ? '✅ Kaydedildi ve senkronize edildi -- Chrome hesabınızdaki diğer bilgisayarlarda da otomatik görünecek.'
                : '⚠️ Chrome hesabınıza kaydedildi ama yerel backend\'e ulaşılamadı (arka plan servisi çalışıyor mu?).';
            apiKeysSaveBtn.disabled = false;
        };
    }
}

// GEÇİCİ OLARAK DEVRE DIŞI: LIVE_PREMIUM_STATE artık varsayılan olarak true
// (bkz. tanımı) -- Lemon Squeezy mağazası aktif olmadığı için gerçek bir
// lisans akışı yok. Bu kontrolü şimdi çalıştırırsak, eskiden bir anahtar
// girmiş olan (artık hiçbir işe yaramayan) kullanıcılarda Lemon Squeezy'den
// dönecek "invalid/inactive" sonucu ücretsiz varsayılanı YANLIŞLIKLA false'a
// çevirirdi. Lemon Squeezy tekrar aktif olduğunda bu bloğu geri açmak yeterli
// (verifyLicenseKey fonksiyonu hâlâ aşağıda duruyor, silinmedi).
// (function initLicenseRecheck() {
//     const key = getStoredLicenseKey();
//     if (!key) return;
//     verifyLicenseKey(key).then(() => {
//         refreshExtraTabFeatureBadges();
//         const container = document.getElementById('settings-overlay');
//         if (container) {
//             container.innerHTML = buildExtraTabPanelHTML();
//             wireExtraTabEvents();
//         }
//     });
// })();

// ---- Reklamları otomatik geçme ----
// Sadece YouTube'un KENDİ "Reklamı geç" butonuna otomatik tıklar ve reklam
// sırasında oynatma hızını artırır. Reklam isteklerini engellemez, reklam
// öğesini DOM'dan silmez -> anti-adblock tespitini tetiklemesi beklenmez.
let adSkipInterval = null;

function startAdAutoSkip() {
    if (adSkipInterval) return;
    adSkipInterval = setInterval(() => {
        try {
            const skipSelectors = [
                '.ytp-ad-skip-button', '.ytp-ad-skip-button-modern',
                '.ytp-skip-ad-button', 'button.ytp-ad-skip-button-container',
            ];
            for (const sel of skipSelectors) {
                const btn = document.querySelector(sel);
                if (btn) { btn.click(); break; }
            }

            const player = document.querySelector('.html5-video-player');
            const video = document.querySelector('video');
            const adShowing = player && player.classList.contains('ad-showing');
            if (video && adShowing && video.playbackRate < 8) {
                video.playbackRate = 16;
            } else if (video && !adShowing && video.playbackRate !== 1) {
                video.playbackRate = 1;
            }
        } catch (e) { /* sessizce geç */ }
    }, 500);
}

function stopAdAutoSkip() {
    if (adSkipInterval) {
        clearInterval(adSkipInterval);
        adSkipInterval = null;
    }
    const video = document.querySelector('video');
    if (video && video.playbackRate !== 1) video.playbackRate = 1;
}

// Sayfa yüklendiğinde, kullanıcı daha önce aktif ettiyse otomatik başlat
if (getPremiumState(PREMIUM_KEYS.adSkip)) {
    startAdAutoSkip();
}

// Chrome hesabında senkronize edilmiş API anahtarları varsa, yerel backend'e
// (yeni bir bilgisayarda ilk kez çalışıyor olabilir, henüz hiç anahtarı yok)
// PROAKTİF olarak gönder -- kullanıcı hiçbir AI özelliğine tıklamadan önce bile
// backend doğru şekilde yapılandırılmış olsun. Backend ayakta değilse (henüz
// başlamamışsa) sessizce başarısız olur, bir sonraki gerçek API çağrısında
// (callBackendAPI zaten her istekte anahtarları gönderir) otomatik düzelir.
getSyncedApiKeys().then((keys) => {
    if (keys && Object.keys(keys).length) {
        pushApiKeysToBackend(keys);
    }
});

// ==================== BAŞLAT ====================
// Panel'i (docked konumdaysa) buton gerekmeden otomatik açar. #secondary
// sayfa yüklenirken geç oluşabildiği için birkaç kez dener.
function autoOpenPanel(retriesLeft) {
    if (!isVideoWatchPage()) return;
    const dockTarget = findDockTarget();
    if (!dockTarget) {
        if (retriesLeft > 0) {
            setTimeout(() => autoOpenPanel(retriesLeft - 1), 500);
        }
        return;
    }
    createPanel();
    const panel = document.getElementById('youtube-ai-panel');
    if (panel) panel.style.display = 'flex';
}

function init() {
    if (!isVideoWatchPage()) {
        removePanelAndButton();
    } else {
        createAIButton();
        autoOpenPanel(20); // ~10 saniyeye kadar #secondary'yi bekler
    }
}

// TEK SEFERLİK gözlemci: video URL'si değiştiğinde paneli yeniden kurar.
// ÖNEMLİ: Bu ÖNCEDEN init()'in İÇİNDEYDİ ve init() her çağrıldığında (her
// video değişiminde) YENİ bir MutationObserver ekleyip eskisini hiç
// kaldırmıyordu. Birkaç video değişiminden sonra onlarca gözlemci birikip,
// YouTube'un video DEĞİŞMESE BİLE sürekli yaptığı DOM güncellemelerinde
// (reklam/öneri/engagement paneli değişiklikleri) HEPSİ tetikleniyordu --
// bu da aynı 5 API isteğinin (özet/analiz/bölüm/öneri/transkript) saniyede
// onlarca kez, üst üste binen/yarışan çağrılarla atılmasına yol açıyordu.
// Sonuç: sekmeler birbiriyle tutarsız görünüyordu (özette yanlış şampiyon,
// bölümlerde "transkript yok" gibi) çünkü farklı anlarda başlayan farklı
// isteklerin sonuçları rastgele sırayla ekrana yazılıyordu. Gözlemci artık
// SADECE BİR KEZ, sayfa yüklenirken kuruluyor.
let lastUrl = location.href;
new MutationObserver(() => {
    if (location.href !== lastUrl) {
        lastUrl = location.href;
        setTimeout(init, 1000);

        if (!isVideoWatchPage()) {
            removePanelAndButton();
            return;
        }
        // Video değişti -> panel yeniden oluşturulup otomatik açılır ki
        // yeni videonun bilgileri ışık hızında (paralel) yeniden çekilsin.
        const panel = document.getElementById('youtube-ai-panel');
        if (panel) panel.remove();
        autoOpenPanel(20);
    }
}).observe(document.body, { childList: true, subtree: true });

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
