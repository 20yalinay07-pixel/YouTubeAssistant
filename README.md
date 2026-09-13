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

**0) Add your API keys.** This repo does not include a `.env` file (it's in `.gitignore`, for your own safety). Create one in the project root with your own keys:

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

Without this file the backend can't make any AI call. It's loaded automatically on startup via `python-dotenv` — nothing is hardcoded in the source.

**Alternative: one key instead of five.** Signing up for Groq, OmniRoute, AssemblyAI (twice) and Exa separately is real setup friction if you're not the original author. [FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi) is a self-hosted proxy that aggregates 34+ free-tier LLM providers behind a single OpenAI-compatible key:

```bash
curl -fsSL https://freellmapi.co/install.sh | bash
```

Add provider keys and grab your unified key from its dashboard at `http://localhost:3001`, then in your `.env` set just:

```
FREELLMAPI_API_KEY=freellmapi-your-unified-key
```

The backend already treats it as an extra fallback provider (after Groq, OpenRouter, and OmniRoute) — if you skip the other keys entirely, this one alone is enough to make every AI feature work. It requires Docker; if that's not something you want running, stick with the individual keys above.

**1) Backend dependencies:**

```bash
cd YouTubeAssistant/backend
pip install -r requirements.txt
```

**2) PO Token server dependencies** — `pot_server/node_modules` isn't in the repo either (too large; `npm install` regenerates it):

```bash
cd YouTubeAssistant/pot_server
npm install
```

**3) Start the backend:**

```bash
cd YouTubeAssistant/backend
python server.py
```

(Or run `start_hidden.vbs` to bring up everything at once — backend, AI router, and PO Token server — with no visible window.)

Then go to `chrome://extensions` → enable Developer mode → **Load unpacked** → select the project folder (if a previous version is already loaded, just hit ⟳ reload).

### Keeping it running in the background

- **`backend/tray_launcher.py`** starts both the AI router and the backend, and shows an icon in the system tray. Right-click it to restart the server, open the logs, or quit — handy after a code change.
- **`start_hidden.vbs`** launches `tray_launcher.py` with no console window — this is what you'd normally run day to day.
- **`start_server.bat`** is an older, console-visible fallback for troubleshooting; it auto-restarts the backend on crash but has no tray icon.

**To start automatically at Windows login:** press `Win + R`, type `shell:startup`, right-click `start_hidden.vbs` → **Create shortcut**, then move that shortcut into the Startup folder that just opened. From then on the backend and AI router start silently in the background on every login.

**To verify it's running:** double-click `start_hidden.vbs`, wait a few seconds, check for the tray icon (you may need to expand the hidden icons next to the clock), then open `http://127.0.0.1:8000/health` in a browser — a JSON response means it's alive.

**Troubleshooting:** open `backend/tray_launcher.log` (also reachable via right-click the tray icon → "Open Logs") — both the AI router's and the backend's output, plus any errors, accumulate there.

## Extra Features

A gold **⭐ Extra Features** button at the bottom of the main menu toggles two things:

**💬 Unlimited AI Chat** — the chat box under each tab is capped at 3 messages per video per tab by default. This switch removes that cap everywhere at once; it's the same chat boxes, just unlimited. (The limit itself lives in the `FREE_CHAT_MESSAGE_LIMIT` constant in `server.py` if you want a different number.)

**⏩ Auto Ad Skip** — auto-clicks YouTube's own "Skip Ad" button the instant it appears, and briefly speeds up playback during the mandatory pre-skip portion of an ad. It doesn't block ad requests or remove ad elements from the page — it only clicks YouTube's own button and adjusts playback speed, so it isn't expected to trigger the usual ad-blocker warnings. YouTube could still change how it detects this in the future; just turn the switch off if that ever happens.

*A note on "Premium":* since this is a personal local tool, there's no real payment system, account, or license server behind these — building one would need its own backend, payment processing, and auth, which isn't practical here. "Premium" is just a conceptual label; you flip these on and off yourself, there's no actual lock.

## Project layout

```
backend/
  server.py           Flask API — transcript extraction, AI orchestration, translation
  tray_launcher.py     Background launcher (system tray) for backend + PO Token server
  ytdlp_bypass.py      yt-dlp evasion helpers
  requirements.txt
pot_server/            Local Node.js server that defeats YouTube's 429/bot blocking
content.js              Chrome content script — the panel UI itself
manifest.json           Extension manifest (Manifest V3)
start_hidden.vbs        Launches everything with no visible window
start_server.bat        Console-visible fallback launcher (no tray icon)
.env                    Your own API keys (not committed — see Setup)
```

---

*A personal-use project — not published to the Chrome Web Store.*
