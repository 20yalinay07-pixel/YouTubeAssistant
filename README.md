# YouTube Assistant

**Understand a video before you watch it.**

YouTube Assistant docks a real analysis panel next to every video you open: a deep summary, a topic map, clickable chapters, and genuinely-matched recommendations — before you've even hit play.

A local Chrome extension + Flask backend. No subscription, no server bill — built entirely on free-tier AI providers.

---

## What's in the panel

| Tab | What it does |
|---|---|
| 🧠 **Summary** | Full-video, point-by-point summary with real names, examples, and cause-effect detail — not a one-line brush-off. |
| 📊 **Topic Analysis** | Main topics, sub-sections, target audience, and keywords pulled from the video's own tags. |
| 📑 **Chapters** | Every `[MM:SS]` badge is clickable — jumps the player straight to that second. Timestamps are computed from real caption data, not guessed by the model. |
| 💡 **Recommendations** | Titles are generated, then verified against real YouTube search results — no invented or dead links, only videos you can actually open. Shaped by content type: similar songs for music, similar topics for talks/tutorials. |
| 📝 **Transcript** | Opens in the video's own spoken language by default; a dropdown translates it into 40+ languages on demand. If the video is a song, a one-time note flags that up front. |

Every tab has its own chat box, so you can ask a follow-up right where the context already lives. A response-language picker (~40 languages) at the top of the panel controls what language the AI answers in — the transcript itself always stays in the video's own spoken language.

## Under the hood

The panel looks simple; the plumbing behind it deals with the real limits of running on free-tier AI:

- **Three-way provider fallback** — Groq (fastest) → OmniRoute → OpenRouter. If one hits a rate limit, the next takes over automatically; you never see the failure.
- **429 fix for YouTube itself** — a local PO Token server defeats YouTube's bot/caption-blocking, which used to break transcript fetching outright.
- **Code-computed timestamps** — chapter times are calculated from real caption data in code, not asked of the model. The model only writes the title for a time slot it's handed — it can no longer invent "Chapter 1, Chapter 2."
- **Session memory only** — transcripts and chat history live in RAM for the session; nothing is written to disk.

```
Groq (LPU, fastest)  --429?-->  OmniRoute skipped  -->  OpenRouter fallback
```

## From 104s to 10s

What happens the moment you open a video:

1. **0.0s** — Transcript is extracted (captions first, falls back through three more methods down to audio transcription).
2. **~10–15s** — Summary + Topic Analysis + Recommendations come back from a *single* structured AI call instead of four separate ones — faster and far more token-efficient.
3. **in parallel** — Chapters are computed on a second track at the same time, using real timestamp data, adding no extra wait.
4. **ready** — The whole panel fills at once. Switching tabs never triggers a new loading spinner.

Transcript extraction itself went through its own round of fixes: an outdated API call path that always failed on modern library versions, a subtitle downloader that used to request captions in every language YouTube offers instead of just one, and a playlist parameter in the URL that made yt-dlp try to process an entire playlist instead of the one video. Long-video audio transcription now also runs in parallel chunks instead of one after another.

## Setup

**1) Load the extension.** Go to `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select this project folder (if a previous version is already loaded, just hit ⟳ reload).

**2) Backend dependencies** (the extension talks to a small local Flask server — this still runs on your own machine, so nothing you do here gets billed to anyone):

```bash
cd YouTubeAssistant/backend
pip install -r requirements.txt
```

**3) PO Token server dependencies** — `pot_server/node_modules` isn't in the repo either (too large; `npm install` regenerates it):

```bash
cd YouTubeAssistant/pot_server
npm install
```

**4) Start the backend:**

```bash
cd YouTubeAssistant/backend
python server.py
```

**5) Add your API keys — inside the extension, not a file.** Open any YouTube video, click the gold **⭐ Extra Features** button, expand **🔑 API Anahtarları**, paste in your own key(s), and hit **Kaydet**. Only Groq (or the single FreeLLMAPI key below) is actually required; everything else is an optional extra that's skipped automatically if left blank.

These keys are saved with `chrome.storage.sync` — tied to your Chrome/Google account, not this one computer. Sign into the same Chrome account on another machine, run the same two setup steps there (load the extension, start the local backend), and your keys show up automatically — no `.env` file to copy over, no separate installer to run. The keys are pushed to whichever local backend the extension is currently talking to on every request, so a freshly-started backend picks them up the moment you open a video.

Where to get each one:

| Key | Get it from |
|---|---|
| Groq (recommended) | [console.groq.com/keys](https://console.groq.com/keys) — free, ready in seconds |
| OpenRouter (backup) | [openrouter.ai/keys](https://openrouter.ai/keys) — kicks in if Groq/FreeLLMAPI fail |
| AssemblyAI ×2 (optional) | [assemblyai.com/dashboard/signup](https://www.assemblyai.com/dashboard/signup) — improves chapter quality |
| Exa Search (optional) | [dashboard.exa.ai/api-keys](https://dashboard.exa.ai/api-keys) — verifies recommended videos actually exist |
| OmniRoute ×5 (advanced, optional) | [omniroute.online](https://www.omniroute.online/) — only if you've set it up yourself |

**Alternative: one key instead of five.** Signing up for Groq, AssemblyAI (twice), Exa, and OmniRoute separately is real setup friction if you're not the original author. [FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi) is a self-hosted proxy that aggregates 34+ free-tier LLM providers behind a single OpenAI-compatible key:

```bash
curl -fsSL https://freellmapi.co/install.sh | bash
```

Add provider keys and grab your unified key from its dashboard at `http://localhost:3001`, then paste just that one key into the **FreeLLMAPI** field in the extension's panel. It's treated as an extra fallback provider (after Groq/OpenRouter/OmniRoute) — skip the other keys entirely and this one alone is enough to make every AI feature work. Requires Docker; if that's not something you want running, stick with the individual keys above.

**Prefer a `.env` file instead** (self-hosting, scripting, or just old habits)? It still works exactly as before — same variable names as the table above (`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OMNIROUTE_KEY_CHAT/SUMMARIZE/ANALYZE/RECOMMENDATIONS/CHAPTERS`, `ASSEMBLYAI_API_KEY_SUMMARIZE/CHAPTERS`, `EXA_SEARCH_API_KEY`, `FREELLMAPI_API_KEY`), loaded automatically via `python-dotenv` at startup. Anything the extension pushes in simply takes priority over it while the extension is running.

### Keeping the backend running in the background

- **`backend/tray_launcher.py`** starts both the AI router and the backend, and shows an icon in the system tray. Right-click it to restart the server, open the logs, or quit — handy after a code change. Run it directly (`python tray_launcher.py`) or via a shortcut you create yourself.
- **To start automatically at Windows login:** create a shortcut to `tray_launcher.py` (or a small `.vbs`/`.bat` wrapper of your own) and drop it into the Startup folder (`Win + R` → `shell:startup`).
- **To verify it's running:** open `http://127.0.0.1:8000/health` in a browser — a JSON response means it's alive.
- **Troubleshooting:** open `backend/tray_launcher.log` (also reachable via right-click the tray icon → "Open Logs") — the AI router's and the backend's output, plus any errors, accumulate there.

## Extra Features

A gold **⭐ Extra Features** button at the bottom of the main menu toggles two things:

**💬 Unlimited AI Chat** — the chat box under each tab is capped at 3 messages per video per tab by default. This switch removes that cap everywhere at once; it's the same chat boxes, just unlimited. (The limit itself lives in the `FREE_CHAT_MESSAGE_LIMIT` constant in `server.py` if you want a different number.)

**⏩ Auto Ad Skip** — auto-clicks YouTube's own "Skip Ad" button the instant it appears, and briefly speeds up playback during the mandatory pre-skip portion of an ad. It doesn't block ad requests or remove ad elements from the page — it only clicks YouTube's own button and adjusts playback speed, so it isn't expected to trigger the usual ad-blocker warnings. YouTube could still change how it detects this in the future; just turn the switch off if that ever happens.

Unlocking them for real (as paid subscriptions) is covered next.

## Premium: selling Ad-Skip and Unlimited Chat

The ⭐ Extra Features can be sold as real paid subscriptions — with **no backend of our own at all**. The extension talks directly to [Lemon Squeezy's License API](https://docs.lemonsqueezy.com/help/licensing/license-api), which generates, stores, and validates the license keys. This keeps there being exactly one source of truth for "is this key valid" — no separate database, no webhook server, no admin login exposed to the internet.

```
Buyer's browser --checkout--> Lemon Squeezy (hosted store + checkout)
                                     |
                              generates a license key
                                     |
Extension ---- POST api.lemonsqueezy.com/v1/licenses/activate / validate ----> unlocks features
```

- Card data never touches this project's code — checkout happens entirely on Lemon Squeezy's hosted page.
- **You** control the payout bank account/card in Lemon Squeezy's own dashboard (Settings → Payouts) — not something this app builds a screen for.
- Subscribers, revenue, and refunds are all visible in Lemon Squeezy's own dashboard — no separate admin panel to run or secure.

**1) Create your 3 products** in your [Lemon Squeezy store](https://digitalhelperforall.lemonsqueezy.com):

| Product | Price |
|---|---|
| Bundle (unlimited chat + ad skip) | $40/month |
| Unlimited Chat only | $30/month |
| Ad Skip only | $15/month |

For each product's variant, turn on **"Generate license key"** in its settings (do *not* leave it off — the extension depends on this). Recommended: leave the activation limit high or unlimited, since one buyer may reinstall the extension or use more than one browser.

**2) Get each variant's ID.** Open a product in the Lemon Squeezy dashboard — the variant ID is the numeric ID shown in the URL or in the product's API response.

**3) Wire the variant IDs to plans.** In `content.js`, fill in the mapping near the top of the Extra Features section:

```js
const LS_VARIANT_TO_PLAN = {
    123456: 'bundle',
    123457: 'chat',
    123458: 'adskip',
};
```

That's it — no deployment, no database, no server to keep running. A buyer subscribes on your Lemon Squeezy store, gets their license key by email (Lemon Squeezy sends this automatically), pastes it into the ⭐ Extra Features panel, and the extension calls Lemon Squeezy directly to activate it and unlock exactly what they paid for. Every 12 hours it silently re-validates, so a cancelled subscription stops working within that window.

## Project layout

```
backend/
  server.py           Flask API — transcript extraction, AI orchestration, translation
  tray_launcher.py     Background launcher (system tray) for backend + PO Token server
  ytdlp_bypass.py      yt-dlp evasion helpers
  requirements.txt
pot_server/            Local Node.js server that defeats YouTube's 429/bot blocking
content.js              Chrome content script — the panel UI itself: license verification, the
                        API-keys panel (chrome.storage.sync), and the AI feature tabs
manifest.json           Extension manifest (Manifest V3)
.env                    Optional — only if you prefer a file over the extension's own panel (see Setup)
```

---

*A personal-use project — not published to the Chrome Web Store.*
