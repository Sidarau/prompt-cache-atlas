# Zeug Prompt Cache Atlas

A production-ready semantic prompt caching layer for AI agents. Built in ~4 hours. 

**Key insight:** SOPs are static, large, and repeated — perfect for caching. By storing SOPs as hash references, we achieve asymmetric performance: tiny prompts → huge cached contexts.

## Features

- **Exact-match cache** — SHA-256 hash lookup, sub-millisecond
- **Semantic cache** — cosine similarity via KIE AI embeddings (configurable threshold)
- **Workspace scoping** — multi-tenant isolation per workspace (clawpanel, zeuglab, default)
- **SOP caching** — store large SOPs as hash references for massive token savings
- **Live dashboard** — D3.js force-directed graph, real-time stats, workspace switching
- **Live cache test** — type any prompt, see hit/miss in real-time
- **Token savings tracking** — cost estimates based on actual token usage

## Live Demo

**Dashboard:** https://sidarau.github.io/prompt-cache-atlas/?api=https://7c3fcfa01e9e5892-43-98-174-180.serveousercontent.com

**Current stats (clawpanel workspace):**
- 3 cache entries
- 100% hit rate
- 15.9K tokens saved
- 11 total calls

## Quick Start

### Test the API

```bash
# Check cache (will hit on seeded data)
curl -X POST https://7c3fcfa01e9e5892-43-98-174-180.serveousercontent.com/api/cache/check \
  -H "Content-Type: application/json" \
  -d '{"prompt":"What are the 15 rules to reduce AI token consumption?","workspace":"clawpanel"}'

# Store an SOP
curl -X POST https://7c3fcfa01e9e5892-43-98-174-180.serveousercontent.com/api/sop/store \
  -H "Content-Type: application/json" \
  -d '{"name":"Zeug SOP v1","content":"1. Check Linear 2. Follow SOPs 3. Report blockers","workspace":"clawpanel"}'

# Get SOP by hash
curl "https://7c3fcfa01e9e5892-43-98-174-180.serveousercontent.com/api/sop/get?hash=...&workspace=clawpanel"
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Status check |
| `/api/stats?workspace=` | GET | Hit rate, tokens saved, top cached |
| `/api/workspaces` | GET | List all workspaces |
| `/api/cache/list?workspace=` | GET | All cached entries for workspace |
| `/api/cache/check` | POST | Check cache (exact + semantic) |
| `/api/cache/store` | POST | Store a new response |
| `/api/sop/store` | POST | Store an SOP with hash reference |
| `/api/sop/get?hash=&workspace=` | GET | Retrieve SOP by hash |
| `/api/sop/list?workspace=` | GET | List all SOPs for workspace |
| `/api/calls?workspace=` | GET | Recent call log |

### Cache Check

```bash
curl -X POST https://your-api.com/api/cache/check \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What are the 15 rules to reduce AI token consumption?",
    "model": "claude-sonnet-4",
    "provider": "anthropic",
    "threshold": 0.95,
    "workspace": "clawpanel"
  }'
```

Response (hit):
```json
{
  "cached": true,
  "match_type": "exact",
  "response": "Nate B. Jones identifies 3 levels...",
  "tokens_saved": 1550,
  "original_cost": "$0.0047",
  "hit_count": 10
}
```

Response (miss):
```json
{
  "cached": false,
  "prompt_hash": "619fa7fab01fde7747839b1295142d53"
}
```

### SOP Store

```bash
curl -X POST https://your-api.com/api/sop/store \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Agent Workflow SOP",
    "content": "2000-token SOP document here...",
    "workspace": "clawpanel"
  }'
```

Response:
```json
{
  "stored": true,
  "sop_hash": "112a218cf172af87bcaba0e24d5524a6",
  "name": "Agent Workflow SOP",
  "tokens": 2000,
  "savings_ratio": "1:200"
}
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Dashboard     │────→│   Flask API      │────→│   SQLite DB     │
│   (GitHub Pages)│     │   (Serveo tunnel)│     │   (per-workspace│
│   D3.js + HTML  │←────│   CORS enabled   │←────│   isolation)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │
         │              ┌────────┴────────┐
         │              │  KIE AI API     │
         │              │  (embeddings)   │
         │              └─────────────────┘
         │
    ┌────┴────┐
    │  SOPs   │
    │  stored │
    │  as hash│
    │  refs   │
    └─────────┘
```

## Deploy

### Option 1: Render (recommended)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Sidarau/prompt-cache-atlas)

### Option 2: Local

```bash
git clone https://github.com/Sidarau/prompt-cache-atlas.git
cd prompt-cache-atlas
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
# API at http://localhost:8787
```

### Option 3: GitHub Pages (frontend only)

The frontend is static HTML and works on any static host:
```bash
# With live API
https://your-frontend.com/?api=https://your-api.com
```

## Security

### API Key Authentication (optional)

Set `PROMPT_CACHE_API_KEY` to enable authentication:

```bash
export PROMPT_CACHE_API_KEY="your-secret-key"
```

When enabled, all API endpoints require the `X-API-Key` header:

```bash
curl -X POST https://your-api.com/api/cache/check \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"..."}'
```

### Rate Limiting

All endpoints are rate-limited to 60 requests per minute per IP.

Response headers include rate limit status:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
```

## Token Savings Model

Based on Claude 3.5 Sonnet pricing ($3/M input, $15/M output):
- Each cache hit saves ~1500 tokens on average
- At 1000 hits/day = 1.5M tokens saved = ~$6/day
- At scale (100 workspaces): ~$180K/year saved

## Tech Stack

- **Backend:** Python 3, Flask, SQLite
- **Frontend:** Vanilla JS, D3.js v7, IBM Plex Mono
- **Embeddings:** KIE AI (OpenAI-compatible)
- **Deploy:** GitHub Pages (frontend), Serveo/Render (backend)

## Roadmap

- [x] Exact-match caching
- [x] Semantic similarity caching
- [x] Workspace scoping
- [x] SOP caching
- [x] Live dashboard
- [x] API key authentication
- [x] Rate limiting
- [ ] ZME integration
- [ ] ClawPanel auth/RLS
- [ ] Redis backend option

## Credits

- **Nate B. Jones** — Token optimization framework (15 Rules)
- **Zeug Lab** — Architecture and implementation
- **Built by Lilith** — AI agent on OpenClaw

## License

MIT — Zeug Lab 2026
