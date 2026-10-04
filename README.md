# 🌾 AI Voice Farmer Assistant

An agricultural advisor a farmer can **talk to**. The farmer speaks (or shows a crop photo) in Telugu, Hindi or English. **Gemini** reasons over their farm profile, crop stage, local weather and past conversations. **Murf AI** speaks the answer back in a natural voice.

```
🎙️ Speak → 🧠 Gemini understands → 🌱 agricultural reasoning → 🌦 weather + crop-stage context
→ 📷 image analysis → 🌐 regional language → 🔊 Murf voice → 💾 farmer memory → 📅 tasks → 🚨 alerts
```

---

## 1. Architecture

```
┌──────────────────────── Browser (React, mobile-first) ────────────────────────┐
│ Web Speech API (te-IN/hi-IN/en-IN) ──┐     Camera / file input ──┐             │
│ MediaRecorder fallback ──────────────┤                           │             │
│                                      ▼                           ▼             │
│  services/api.js  ── only talks to /api/* (no API keys in the frontend) ──     │
└───────────────────────────────────────┬─────────────────────────────────────────┘
                                        │ HTTP (Vite proxy in dev)
┌───────────────────────────── FastAPI backend ───────────────────────────────────┐
│ routes/  chat · image · voice · farmer · weather · reminders · alerts · diary   │
│                                                                                 │
│ memory_service ── builds context: profile + crop stage + weather + remembered   │
│                   facts + recent conversations + saved advice + diary + tasks   │
│ gemini_service ── structured JSON answers (Pydantic schema), model fallback     │
│ vision_service ── validates/stores photos → Gemini vision part                  │
│ murf_service ──── voice/style selection, speech-ready text, disk cache          │
│ weather_service ─ Open-Meteo forecast → spray/irrigation/heat/rain risk flags   │
│ calendar_service ─ crop stage timelines + stage tasks                           │
│ SQLAlchemy ────── SQLite (dev) / PostgreSQL (set DATABASE_URL)                  │
└──────────┬───────────────────────┬─────────────────────────┬────────────────────┘
           ▼                       ▼                         ▼
     Google Gemini            Murf AI TTS              Open-Meteo (no key)
```

**One question, end to end**

1. The farmer taps 🎙️. The browser turns speech into text (or the backend transcribes it with Gemini).
2. `POST /api/chat` loads the farmer profile, computes the crop stage, fetches the weather and pulls memory.
3. Gemini returns a structured `AdvisorAnswer` with these fields: `mode` (quick / explain / emergency), the five sections, the emergency block, `speech_text`, `new_memory_facts` and `needs_followup`.
4. The answer is saved. New facts go into memory. An emergency also creates an urgent alert.
5. The UI shows the answer cards straight away, then calls `POST /api/voice/generate`.
6. Murf generates speech in the right voice and style. The audio is cached on disk and plays automatically.

---

## 2. Folder structure

```
backend/
  app/
    main.py                 FastAPI app, CORS, /media static files, serves frontend/dist in production
    config/settings.py      env vars, languages, storage paths
    routes/                 chat.py (chat + image/analyze), voice.py, farmer.py, weather.py,
                            reminders.py (+ calendar), alerts.py, diary.py, uploads.py, deps.py
    services/               gemini_service.py, murf_service.py, weather_service.py, vision_service.py,
                            memory_service.py, calendar_service.py
    models/                 models.py (SQLAlchemy tables), schemas.py (API + Gemini output schemas)
    database/               db.py (engine/session), seed.py (demo farmer), reset.py
    utils/                  speech.py (text prep + chunking for Murf), rate_limit.py
  storage/                  farmer.db (local SQLite), audio/ (Murf cache)   [git-ignored]
  .env / .env.example
frontend/
  src/
    App.jsx                 app state, ask flow, hash routing
    components/             MicButton, AnswerCard, AudioButton, Layout (header, bottom nav)
    pages/                  Home, Ask, CropCheck, Weather, Tasks, Alerts, Diary, Tips, History, Profile
    services/api.js         all backend calls
    hooks/                  useSpeechInput, useVoicePlayer, useApp
    utils/                  i18n (en/te/hi), weatherText, stages, format
setup.bat · start.bat · reset-demo.bat
```

---

## 3. Backend API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/chat` | `{message, language}` → structured advice. `{more_details_for: id}` → detailed explanation of an earlier answer |
| POST | `/api/image/analyze` | multipart `image` + optional `question` + `language` → photo diagnosis ("Ask with photo") |
| POST | `/api/voice/generate` | `{text, language, voice: "male"/"female"/voiceId, speed, pitch, purpose}` → `{audio_url, voice_id, style}` |
| POST | `/api/voice/transcribe` | multipart `audio` → `{text, language}` (Gemini fallback for browsers without speech recognition) |
| GET | `/api/voice/voices?language=te-IN` | Murf voices that can speak that language |
| GET / PUT | `/api/farmer/profile` | farmer profile (PUT geocodes the village or district for weather) |
| GET | `/api/farmer/dashboard` | profile, crop stage, weather, crop health, tasks and unread alerts in one call |
| GET | `/api/farmer/history?saved_only=` | past conversations |
| POST | `/api/farmer/history/{id}/save` | save or unsave a recommendation |
| GET | `/api/farmer/memory` | facts the assistant remembers |
| GET | `/api/weather?lat=&lon=` | forecast and risk flags (defaults to the farmer's location) |
| GET | `/api/calendar` | crop stage timeline, current stage, suggested tasks |
| GET / POST | `/api/reminders` | list or create tasks. `POST /api/reminders/auto?language=` creates 14 days of stage tasks |
| PATCH / DELETE | `/api/reminders/{id}` | mark a task done, or delete it |
| GET / POST | `/api/alerts` | list alerts; create one manually `{text, priority}` or let Gemini write them `{auto: true}` |
| POST | `/api/alerts/{id}/audio` | Murf audio for an alert, voiced by its priority |
| POST / GET | `/api/diary`, `/api/diary/trends` | voice farm diary, and the trend across entries |
| GET | `/api/health` | which services are configured |

Interactive docs: http://localhost:8000/docs

---

## 4. Gemini integration (`services/gemini_service.py`)

- **System prompt**: the agricultural-assistant instruction from the spec, plus rules on hedged language, no invented dosages, schemes or weather, using memory, and native script.
- **Structured output**: `response_schema=AdvisorAnswer` (Pydantic), so the UI always gets the same sections:
  - *What I noticed*
  - *Possible reason*
  - *What you can do*
  - *Important warning*
  - *What to monitor*
  - plus the emergency fields, a speech-ready `speech_text`, an English `summary_en` and `new_memory_facts`.
- **Farmer modes**: Gemini picks `quick`, `explain` or `emergency` for each answer. Emergency keywords in English, Telugu and Hindi add a hint to the prompt. "More details" forces explain mode.
- **Follow-up questions**: if the information isn't enough, Gemini sets `needs_followup` and asks one question. The UI shows it prominently and Murf speaks it.
- **Vision**: the photo is sent as a `Part.from_bytes` together with the transcribed question. Gemini lists visible symptoms first, then possible causes with severity, and asks for more photos if needed.
- **Memory**: each answer adds facts such as "Chilli plants had white insects on 2026-10-04". The next prompt includes these facts, the recent conversation summaries, saved advice and the diary. When the farmer says "the problem is still there", the assistant recalls the earlier report.
- **Other uses**: diary extraction, diary trends, personalized alerts, transcription, and translating task titles.
- **Reliability**: when a model returns 404, 429 or 5xx, or times out, the backend tries the next model. It goes through `GEMINI_MODEL` and then `GEMINI_FALLBACK_MODELS`, twice, with a back-off. Gemini returned "high demand" 503s often during testing, so keep several fallbacks configured.

## 5. Murf integration (`services/murf_service.py`)

Murf is called **only from the backend**. The key is in `backend/.env` and never reaches the browser.

- **Speech-ready text**: Gemini writes `speech_text` for listening (short sentences, no lists or symbols). Then `utils/speech.py` removes any leftover markdown, emojis, section labels and URLs. Text over Murf's limit is split at sentence boundaries and the MP3 parts are joined.
- **Voice selection** (language × gender):

  | Language | Female | Male |
  |---|---|---|
  | English (en-IN) | `en-IN-isha` | `en-IN-rohan` |
  | Hindi (hi-IN) | `hi-IN-shweta` | `hi-IN-shaan` |
  | Telugu (te-IN) | `ta-IN-iniya` + `multiNativeLocale: te-IN` | first multilingual voice that supports Telugu (currently `en-US-wayne`) |

  Murf has no native Telugu voice yet. Telugu is spoken by multilingual voices using `multiNativeLocale`. A caller can also pass any Murf `voiceId`.
- **Voice personality**: the `purpose` field sets the style and the rate.

  | Purpose | Used for | Style | Rate |
  |---|---|---|---|
  | `normal` | everyday answers | Conversational | normal |
  | `emergency` | urgent alerts and emergencies | Promo (clear, energetic) | +6 |
  | `reminder` | reminders and normal alerts | Calm | −8 |
  | `educational` | farming tips, "More details" | Narration | −5 |

  When a voice doesn't have the preferred style, it falls back to Conversational. The farmer's speed setting (0.7×–1.3×) is added on top.
- **Caching**: audio is saved as `storage/audio/<sha256>.mp3`, keyed on the text, voice, style and rate. Replaying an answer costs no Murf credits.
- **Retries**: 5xx, 429 and timeouts are retried up to three times. Murf returned an occasional 504 during testing.

## 6. Database

SQLAlchemy 2.x models in `app/models/models.py`: `farmers`, `conversations` (stores the full structured answer as JSON), `memory_facts`, `reminders`, `alerts`, `diary_entries` and `uploads` (crop photos are stored in the database, so they survive restarts on hosts like Render).

SQLite is the default. For PostgreSQL, set `DATABASE_URL=postgresql+psycopg://user:pass@host/db` and install `psycopg[binary]`. Tables are created on startup, and demo farmer #1 (Ravi, chilli, Guntur, Telugu) is seeded automatically.

The app is single-farmer for now: `routes/deps.py:FARMER_ID`. Adding authentication means swapping that constant for the logged-in user.

---

## 7. Setup (Windows)

Requirements: Python 3.11+ and Node 18+.

```bat
setup.bat          :: creates backend\.venv, installs Python + npm packages, creates backend\.env
                   :: put GEMINI_API_KEY and MURF_API_KEY in backend\.env
start.bat          :: backend on :8000, frontend on :5173, opens the browser
```

Manual setup (any OS):

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env    # add keys
.venv/Scripts/python -m uvicorn app.main:app --port 8000

cd ../frontend
npm install
npm run dev             # http://localhost:5173
```

**Production / single port**: run `npm run build` in `frontend/`. FastAPI then serves `frontend/dist` at http://localhost:8000.

**Voice input** needs Chrome or Edge (desktop or Android) for instant speech recognition in te-IN, hi-IN and en-IN. Other browsers record audio and transcribe it with Gemini. The microphone and camera only work on `localhost` or HTTPS.

**Reset the demo**: stop the backend, run `reset-demo.bat`, then start again.

---

## 7b. Deploy: Netlify (frontend) + Render (backend)

Netlify serves the React app. Its functions can't run Python, so the FastAPI backend runs on Render's free tier. The browser calls the Render API directly, which avoids Netlify's proxy timeout on slow Gemini and Murf calls.

```
Phone/browser ──▶ https://<site>.netlify.app        (React build on Netlify's CDN)
      │
      └──API──▶ https://<service>.onrender.com      (FastAPI on Render)
                    ├─ Gemini, Murf
                    └─ PostgreSQL (Render free DB)
```

| File | Purpose |
|---|---|
| `netlify.toml` | build `frontend/` → publish `dist`, SPA fallback, mic/camera permissions header, asset caching |
| `render.yaml` | Render Blueprint: Python web service (`backend/`), free PostgreSQL, env vars, health check |
| `frontend/.env.example` | `VITE_API_BASE`: the Render URL baked into the build. The Netlify build fails with a clear error if it's missing |

**Steps**

1. **Push to GitHub** (`.env` files are git-ignored, so your keys are never committed):
   ```bash
   git add . && git commit -m "AI Voice Farmer Assistant"
   git branch -M main
   git remote add origin https://github.com/<you>/ai-voice-farmer-assistant.git
   git push -u origin main
   ```
2. **Backend on Render**:
   - Go to https://dashboard.render.com, then **New → Blueprint**, and pick the repo. It reads `render.yaml`.
   - Enter the secrets it asks for:
     - `GEMINI_API_KEY`
     - `MURF_API_KEY`
     - `CORS_ORIGINS` (put your Netlify URL here once you know it; for now `https://*.netlify.app` sites are already allowed through `CORS_ORIGIN_REGEX`)
   - Deploy. Copy the service URL, e.g. `https://farmer-assistant-api.onrender.com`, and check that `/api/health` returns `"gemini":true,"murf":true`.
3. **Frontend on Netlify**:
   - Go to https://app.netlify.com, then **Add new site → Import an existing project**, and pick the repo. The build settings come from `netlify.toml`.
   - Under **Site configuration → Environment variables**, add `VITE_API_BASE` = your Render URL.
   - Deploy, then open `https://<site>.netlify.app`. HTTPS is automatic, which the mic and camera need.
4. **Lock CORS to your site** (recommended): on Render, set `CORS_ORIGINS=https://<site>.netlify.app` and `CORS_ORIGIN_REGEX=` (empty).

Without GitHub, the Netlify part can also be done by drag and drop:
- run `set VITE_API_BASE=https://<service>.onrender.com && npm run build` in `frontend/`
- drop the `frontend/dist` folder on https://app.netlify.com/drop

Render still needs the Git repo.

**Production notes**
- **Cold starts**: a free Render service sleeps after 15 minutes idle, and the first request then takes about 30–50 s. The app shows a "Starting the farm assistant…" banner meanwhile. Open the site a minute before a demo, or use a paid instance.
- **Storage**:
  - conversations, memory, alerts, diary, tasks and crop photos are in PostgreSQL, so they survive restarts
  - Murf audio is only a disk cache; after a restart it's regenerated on demand
  - Render's free PostgreSQL expires after 30 days; switch `DATABASE_URL` to Neon or Supabase for longer.
- **Cost protection**: endpoints that spend Gemini or Murf credits are limited to `RATE_LIMIT_PER_MINUTE` (default 30) per IP, because the API URL is public.
- **Keys**: set them only in Render's dashboard. The frontend bundle contains just the Render URL.

---

## 8. Testing

**Automated end-to-end test**: 22 checks against the running backend, using the real Gemini, Murf and Open-Meteo services:

```bat
cd backend
.venv\Scripts\python tests\smoke_test.py --image tests\sample_leaf.jpg
reset-demo.bat   :: afterwards, from the project root, to clear the test data
```

It covers profile, weather, calendar, Telugu chat, Murf voices (Telugu, Hindi, English, cache), speech-to-text, memory follow-up, more details, saving advice, emergency mode, photo diagnosis, diary trends, alerts with audio, and auto tasks.

Manual API checks (backend running):

```bash
curl localhost:8000/api/health
curl localhost:8000/api/farmer/dashboard
curl -X POST localhost:8000/api/chat -H "Content-Type: application/json" \
     -d '{"message":"Is today suitable for spraying?","language":"en-IN"}'
curl -X POST localhost:8000/api/voice/generate -H "Content-Type: application/json" \
     -d '{"text":"Check your field moisture today.","language":"en-IN","purpose":"reminder"}'
curl -X POST localhost:8000/api/image/analyze -F "image=@leaf.jpg" -F "question=What is this?" -F "language=te-IN"
curl -X POST localhost:8000/api/alerts -H "Content-Type: application/json" -d '{"auto":true}'
```

What was verified while building this, with live Gemini, Murf and Open-Meteo:

| Scenario | Result |
|---|---|
| Telugu chilli whitefly question | Telugu answer in all 5 sections. It told the farmer not to spray because the forecast showed a 71% chance of rain in the next 6 hours |
| "The problem is still there" (next message) | Recalled the earlier white-insect report and asked whether it had spread across the 3 acres |
| Flood message | `emergency` mode: immediate actions, what not to do, evidence to collect, contact RBK / Kisan Call Centre 1800-180-1551 |
| Photo of whitefly-infested leaf + Telugu voice question | Possible whitefly or mealybug, medium severity, hedged wording, asked for an underside photo, disclaimer shown |
| Non-crop photo | Did not guess; asked for a clear photo of the leaves |
| Telugu diary note | Structured as crop Chilli, "white spots on some leaves", severity low |
| Auto alerts | Telugu weather, pest and irrigation alerts with urgent, warning and normal priorities |
| Murf voices | Telugu (female and male), Hindi (Promo style for urgent), English. About 5–15 s per clip, then cached |
| UI at 390 px phone width | No horizontal overflow, no console errors, light and dark themes |

---

## 9. Demo workflow (hackathon script)

Before the demo: run `reset-demo.bat`, then `start.bat`, and open the app in Chrome.

1. **Home**: show *నా పొలం* (My Farm): chilli (Teja), growth stage, 3 acres, Guntur weather, rain chance, irrigation advice. The language is తెలుగు.
2. **🎙️ Speak**: tap the big mic and say: *"నా మిరప పంట ఆకులపై తెల్లటి పురుగులు కనిపిస్తున్నాయి. ఏం చేయాలి?"*
   - The recognized text appears. The answer cards appear in about 5 s, and the Murf Telugu voice plays automatically.
   - Point out that the answer used the real forecast ("don't spray now, rain is likely").
   - Tap **⭐ సేవ్** to save the recommendation.
3. **Memory**: say *"సమస్య ఇంకా అలాగే ఉంది"* ("the problem is still there"). It recalls the earlier report and asks one follow-up question.
4. **📷 + 🎙️ Ask with photo**: open *నా పంటను చూడండి*, take or upload a leaf photo, record "ఈ ఆకులు ఎందుకు ఇలా అవుతున్నాయి?", and tap *పంటను పరిశీలించండి*. You get a hedged diagnosis with severity, next steps and a spoken answer.
5. **🌦 Weather**: spray suitability with reasons, irrigation advice and risk flags, all in Telugu. Tap a question chip ("ఈరోజు పిచికారీ చేయవచ్చా?") for a spoken answer.
6. **🔊 Alerts**: tap *Create today's alerts*. Gemini writes personalized alerts, and the urgent one is spoken at once in the clear, urgent voice.
7. **Optional**:
   - an emergency message such as a flood, to show the 🚨 FARM EMERGENCY banner
   - the **📅 tasks** calendar with auto-generated Telugu tasks
   - the **📔 diary** with a spoken note and *Show trend*
   - switch to हिन्दी or English: the UI, answers and voice all change.

---

## 10. Security and safety notes

- Gemini and Murf keys stay in `backend/.env`, which is git-ignored and never sent to the browser. Rotate any key that has been shared in chat or in screenshots.
- Uploaded photos are type-checked and size-limited (10 MB).
- The assistant never presents itself as a certified officer. Diagnoses are hedged, chemical advice points to product labels and local officers, and photo answers carry a disclaimer.
- Weather in answers comes only from the Open-Meteo data passed in. Gemini is told not to invent forecasts, schemes or dosages.
