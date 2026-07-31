# Prompt Cache Atlas — Integration Guide

**One-line summary:** Wrap your LLM calls with a cache check. If it's been asked before, get the answer instantly and save tokens.

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Codex     │     │   Claude    │     │   Hermes    │
│  (local)    │     │  (local)    │     │  (Lightsail)│
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │  HTTP POST /api/cache/check
                           ▼
              ┌───────────────────────────┐
              │  Prompt Cache API         │
              │  (Serveo tunnel — public) │
              │  SQLite per workspace     │
              └───────────────────────────┘
```

**Key point:** Cache API is HTTP. Any agent on any machine can use it. No local setup required on the client side.

---

## Quick Start: Python SDK

File: `zeug_cache.py` (drop this into any project)

```python
"""Zeug Prompt Cache — drop-in caching layer for LLM calls.

Usage:
    from zeug_cache import cached_chat, store_sop, get_sop

    # Wrap any LLM call
    response = cached_chat(
        prompt="Analyze this trade setup...",
        model="claude-sonnet-4",
        workspace="clawpanel",
        fallback_fn=call_your_llm
    )
"""

import os
import hashlib
import requests
from typing import Callable, Optional

DEFAULT_API = "https://3a79f75d8dd511c7-43-98-174-180.serveousercontent.com"
API_BASE = os.environ.get("ZEUG_CACHE_API", DEFAULT_API).rstrip("/")

class ZeugCache:
    """Prompt cache client."""

    def __init__(self, workspace: str = "default", api_base: str = None):
        self.workspace = workspace
        self.api_base = (api_base or API_BASE).rstrip("/")

    def check(self, prompt: str, model: str = None, threshold: float = 0.92) -> Optional[dict]:
        """Check cache for a prompt. Returns cached response or None."""
        try:
            r = requests.post(
                f"{self.api_base}/api/cache/check",
                json={
                    "prompt": prompt,
                    "model": model,
                    "workspace": self.workspace,
                    "threshold": threshold
                },
                timeout=5
            )
            if r.ok:
                data = r.json()
                if data.get("cached"):
                    return data
        except Exception as e:
            print(f"[ZeugCache] check error: {e}")
        return None

    def store(self, prompt: str, response: str, model: str = None) -> bool:
        """Store a prompt-response pair in cache."""
        try:
            r = requests.post(
                f"{self.api_base}/api/cache/store",
                json={
                    "prompt": prompt,
                    "response": response,
                    "model": model,
                    "workspace": self.workspace
                },
                timeout=5
            )
            return r.ok
        except Exception as e:
            print(f"[ZeugCache] store error: {e}")
            return False

    def chat(self, prompt: str, model: str = None, threshold: float = 0.92,
             fallback_fn: Callable = None) -> str:
        """Check cache first, fallback to LLM on miss, then store."""

        # 1. Try cache
        cached = self.check(prompt, model, threshold)
        if cached:
            print(f"[ZeugCache] HIT ({cached['match_type']}) — saved {cached.get('tokens_saved', '?')} tokens")
            return cached["response"]

        # 2. Miss — call LLM
        print(f"[ZeugCache] MISS — calling {model or 'LLM'}")
        if fallback_fn is None:
            raise ValueError("No fallback_fn provided for cache miss")
        response = fallback_fn(prompt)

        # 3. Store for next time
        self.store(prompt, response, model)
        return response

    # ── SOP helpers ──────────────────────────────────────────

    def store_sop(self, name: str, content: str) -> str:
        """Store an SOP, return hash reference."""
        r = requests.post(
            f"{self.api_base}/api/sop/store",
            json={"name": name, "content": content, "workspace": self.workspace},
            timeout=5
        )
        r.raise_for_status()
        return r.json()["sop_hash"]

    def get_sop(self, sop_hash: str) -> str:
        """Retrieve SOP by hash."""
        r = requests.get(
            f"{self.api_base}/api/sop/get",
            params={"hash": sop_hash, "workspace": self.workspace},
            timeout=5
        )
        r.raise_for_status()
        return r.json()["content"]

    def list_sops(self) -> list:
        """List all SOPs for workspace."""
        r = requests.get(
            f"{self.api_base}/api/sop/list",
            params={"workspace": self.workspace},
            timeout=5
        )
        r.raise_for_status()
        return r.json()

    def stats(self) -> dict:
        """Get workspace stats."""
        r = requests.get(
            f"{self.api_base}/api/stats",
            params={"workspace": self.workspace},
            timeout=5
        )
        r.raise_for_status()
        return r.json()


# ── Convenience functions ──────────────────────────────────

def cached_chat(prompt: str, model: str = None, workspace: str = "default",
                threshold: float = 0.92, fallback_fn: Callable = None) -> str:
    """One-shot cached chat."""
    cache = ZeugCache(workspace=workspace)
    return cache.chat(prompt, model, threshold, fallback_fn)

def store_sop(name: str, content: str, workspace: str = "default") -> str:
    """Store an SOP, return hash."""
    return ZeugCache(workspace=workspace).store_sop(name, content)

def get_sop(sop_hash: str, workspace: str = "default") -> str:
    """Get SOP by hash."""
    return ZeugCache(workspace=workspace).get_sop(sop_hash)


if __name__ == "__main__":
    # Quick test
    cache = ZeugCache(workspace="test")
    print("Stats:", cache.stats())
```

---

## Integration by Harness

### 1. Codex / OpenAI (local)

Drop `zeug_cache.py` next to your Codex project. Wrap the completion call:

```python
from zeug_cache import ZeugCache
import openai

cache = ZeugCache(workspace="clawpanel")

def codex_chat(prompt: str, model: str = "gpt-5.5") -> str:
    """Codex with prompt caching."""

    def fallback(p):
        return openai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": p}]
        ).choices[0].message.content

    return cache.chat(prompt, model=model, fallback_fn=fallback)

# Usage
response = codex_chat("Refactor this function to use async/await")
```

### 2. Claude (local)

```python
from zeug_cache import ZeugCache
import anthropic

cache = ZeugCache(workspace="clawpanel")
client = anthropic.Anthropic()

def claude_chat(prompt: str, model: str = "claude-sonnet-4") -> str:
    def fallback(p):
        return client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": p}]
        ).content[0].text

    return cache.chat(prompt, model=model, fallback_fn=fallback)
```

### 3. Hermes (Lightsail / remote)

Hermes just needs the SDK file + `requests` installed:

```bash
# On Hermes
pip install requests
# Copy zeug_cache.py to your project
scp zeug_cache.py hermes:~/project/
```

```python
from zeug_cache import ZeugCache

# Same code, works from anywhere with internet
cache = ZeugCache(workspace="clawpanel")

# If Hermes calls Kimi API:
def kimi_chat(prompt: str) -> str:
    def fallback(p):
        # your Kimi API call here
        return call_kimi_api(p)
    return cache.chat(prompt, model="kimi-k3", fallback_fn=fallback)
```

### 4. Lilith (OpenClaw — that's me)

I already have access. I can cache my own calls:

```python
from zeug_cache import ZeugCache

cache = ZeugCache(workspace="clawpanel")

# Before calling KIE API for a repeated analysis:
cached = cache.check("Summarize this video transcript...", model="kimi-k3")
if cached:
    return cached["response"]
# else: call API, then cache.store()
```

---

## Workspace Strategy

| Workspace | Used by | What to cache |
|-----------|---------|--------------|
| `clawpanel` | ClawPanel, trading agents | Trade analysis prompts, SOPs |
| `zeuglab` | Content pipeline | Video analysis, transcript summaries |
| `default` | General experiments | Everything else |
| `test` | CI/tests | Throwaway data |

Switch workspaces by changing the `workspace` parameter. Each is isolated.

---

## SOP Caching Pattern

Store large SOPs once, reference by hash forever:

```python
# One-time: store your SOP
SOP_HASH = cache.store_sop(
    name="Trading Analysis SOP",
    content="""1. Check market regime
2. Identify support/resistance
3. Calculate risk/reward
4. ... (2000 tokens of instructions)"""
)
# SOP_HASH = "a1b2c3d4..."

# Every call: retrieve + prepend to prompt
sop = cache.get_sop(SOP_HASH)
prompt = f"{sop}\n\nAnalyze this setup: {user_input}"
response = cache.chat(prompt, model="claude-sonnet-4", fallback_fn=call_llm)
```

**Savings:** 2000 tokens × every call = massive.

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ZEUG_CACHE_API` | `https://3a79f75d8dd511c7-43-98-174-180.serveousercontent.com` | API endpoint |
| `ZEUG_CACHE_WORKSPACE` | `default` | Default workspace |

```bash
# On Hermes — point to the same API
export ZEUG_CACHE_API="https://3a79f75d8dd511c7-43-98-174-180.serveousercontent.com"
export ZEUG_CACHE_WORKSPACE="clawpanel"
```

---

## Health Checks

```bash
# API health
curl https://3a79f75d8dd511c7-43-98-174-180.serveousercontent.com/api/health

# Workspace stats
curl "https://3a79f75d8dd511c7-43-98-174-180.serveousercontent.com/api/stats?workspace=clawpanel"

# List cached prompts
curl "https://3a79f75d8dd511c7-43-98-174-180.serveousercontent.com/api/cache/list?workspace=clawpanel"
```

---

## Dashboard

Live dashboard with your workspace data:

```
https://sidarau.github.io/prompt-cache-atlas/?api=https://3a79f75d8dd511c7-43-98-174-180.serveousercontent.com
```

Add `?workspace=clawpanel` to scope to a workspace (if supported by your frontend version).

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Connection timeout` | Check Serveo tunnel is up. API runs on clawpanel instance. |
| `404 on /api/cache/check` | API path changed? Check `API_BASE` URL. |
| `Workspace not found` | First call auto-creates workspace. Or seed it with a store call. |
| `Cache never hits` | Lower threshold (default 0.92). Or prompts are too different. |
| `SOP hash not found` | Wrong workspace. SOPs are scoped per-workspace. |

---

## Files

| File | Purpose |
|------|---------|
| `zeug_cache.py` | Drop-in Python SDK |
| `INTEGRATION.md` | This document |
| `app.py` | Flask API (runs on clawpanel) |
| `index.html` | Dashboard frontend |

---

*Built by Lilith · Zeug Lab · 2026*
