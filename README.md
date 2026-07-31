# Zeug Prompt Cache Atlas

A working demonstration of semantic prompt caching for AI agents. 

- **Exact-match cache** — SHA-256 hash lookup, sub-millisecond
- **Semantic cache** — cosine similarity via KIE AI embeddings  
- **Live dashboard** — D3.js force-directed graph, real-time stats
- **Seeded demo data** — 6 prompts from Nate B. Jones' token optimization analysis

## Live Demo

*Frontend (static, always works):* `https://sidarau.github.io/prompt-cache-atlas/`

*With live API:* Add `?api=<your-api-url>` to the URL

## Deploy

### 1. API — Render (free)

Click to deploy the Flask API:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Sidarau/prompt-cache-atlas)

Or manually:
1. Create a new Web Service on Render
2. Connect `Sidarau/prompt-cache-atlas`
3. Set runtime: Python 3
4. Build command: `pip install -r requirements.txt`
5. Start command: `gunicorn --bind 0.0.0.0:$PORT --workers 2 app:app`
6. Add env var `KIE_AI_API_KEY` (optional, for semantic search)
7. Add a 1GB disk mount at `/opt/render/project/src` for SQLite persistence

API will be at `https://prompt-cache-api.onrender.com`

### 2. Frontend — Vercel (free)

```bash
npm i -g vercel
vercel --prod
```

Or import `Sidarau/prompt-cache-atlas` on [vercel.com](https://vercel.com) — it's just static HTML.

### 3. Connect

Once the API is live, update the frontend:

```bash
# Option A: query parameter (no rebuild)
https://your-frontend.vercel.app/?api=https://prompt-cache-api.onrender.com

# Option B: hardcode in index.html
const API_BASE = 'https://prompt-cache-api.onrender.com';
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Status check |
| `/api/stats` | GET | Hit rate, tokens saved, top cached |
| `/api/cache/list` | GET | All cached entries |
| `/api/cache/check` | POST | Check cache (exact + semantic) |
| `/api/cache/store` | POST | Store a new response |
| `/api/calls` | GET | Recent call log |

### Example

```bash
# Check cache
curl -X POST https://prompt-cache-api.onrender.com/api/cache/check \
  -H "Content-Type: application/json" \
  -d '{"prompt":"What are the 15 rules to reduce AI token consumption?","threshold":0.95}'

# Store response
curl -X POST https://prompt-cache-api.onrender.com/api/cache/store \
  -H "Content-Type: application/json" \
  -d '{"prompt":"...","response":"...","tokens_in":1200,"tokens_out":350}'
```

## Local Dev

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
# API at http://localhost:8787
# Open index.html in browser for frontend
```

## Architecture

```
iPhone Safari → Vercel (static HTML/JS/D3)
                     ↓ fetch CORS
              Render (Flask + SQLite + KIE embeddings)
```

## License

MIT — Zeug Lab 2026
