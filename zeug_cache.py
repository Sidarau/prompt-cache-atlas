"""Zeug Prompt Cache — drop-in caching layer for LLM calls.

Usage:
    from zeug_cache import ZeugCache, cached_chat

    cache = ZeugCache(workspace="clawpanel")

    # Wrap any LLM call
    response = cache.chat(
        prompt="Analyze this trade setup...",
        model="claude-sonnet-4",
        fallback_fn=call_your_llm
    )

    # Store and retrieve SOPs by hash
    sop_hash = cache.store_sop("Trading SOP", "2000 tokens of instructions...")
    sop = cache.get_sop(sop_hash)

Environment:
    ZEUG_CACHE_API — API endpoint (default: serveo tunnel)
    ZEUG_CACHE_WORKSPACE — Default workspace (default: "default")
"""

import os
import requests
from typing import Callable, Optional

DEFAULT_API = "https://3a79f75d8dd511c7-43-98-174-180.serveousercontent.com"
API_BASE = os.environ.get("ZEUG_CACHE_API", DEFAULT_API).rstrip("/")
DEFAULT_WORKSPACE = os.environ.get("ZEUG_CACHE_WORKSPACE", "default")


class ZeugCache:
    """Prompt cache client. Works from any machine with internet access."""

    def __init__(self, workspace: str = None, api_base: str = None):
        self.workspace = workspace or DEFAULT_WORKSPACE
        self.api_base = (api_base or API_BASE).rstrip("/")

    def check(self, prompt: str, model: str = None, threshold: float = 0.92) -> Optional[dict]:
        """Check cache for a prompt. Returns cached response dict or None."""
        try:
            r = requests.post(
                f"{self.api_base}/api/cache/check",
                json={
                    "prompt": prompt,
                    "model": model,
                    "workspace": self.workspace,
                    "threshold": threshold,
                },
                timeout=5,
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
                    "workspace": self.workspace,
                },
                timeout=5,
            )
            return r.ok
        except Exception as e:
            print(f"[ZeugCache] store error: {e}")
            return False

    def chat(self, prompt: str, model: str = None, threshold: float = 0.92,
             fallback_fn: Callable = None) -> str:
        """Check cache first, fallback to LLM on miss, then store result.

        Args:
            prompt: The prompt to send
            model: Model identifier (for cache scoping)
            threshold: Semantic similarity threshold (0.0-1.0)
            fallback_fn: Function to call on cache miss. Must accept (prompt) -> str.

        Returns:
            The response string (from cache or fallback)
        """
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
            timeout=5,
        )
        r.raise_for_status()
        return r.json()["sop_hash"]

    def get_sop(self, sop_hash: str) -> str:
        """Retrieve SOP by hash."""
        r = requests.get(
            f"{self.api_base}/api/sop/get",
            params={"hash": sop_hash, "workspace": self.workspace},
            timeout=5,
        )
        r.raise_for_status()
        return r.json()["content"]

    def list_sops(self) -> list:
        """List all SOPs for workspace."""
        r = requests.get(
            f"{self.api_base}/api/sop/list",
            params={"workspace": self.workspace},
            timeout=5,
        )
        r.raise_for_status()
        return r.json()

    def stats(self) -> dict:
        """Get workspace stats."""
        r = requests.get(
            f"{self.api_base}/api/stats",
            params={"workspace": self.workspace},
            timeout=5,
        )
        r.raise_for_status()
        return r.json()


# ── Convenience functions ──────────────────────────────────

def cached_chat(prompt: str, model: str = None, workspace: str = None,
                threshold: float = 0.92, fallback_fn: Callable = None) -> str:
    """One-shot cached chat."""
    cache = ZeugCache(workspace=workspace)
    return cache.chat(prompt, model, threshold, fallback_fn)


def store_sop(name: str, content: str, workspace: str = None) -> str:
    """Store an SOP, return hash."""
    return ZeugCache(workspace=workspace).store_sop(name, content)


def get_sop(sop_hash: str, workspace: str = None) -> str:
    """Get SOP by hash."""
    return ZeugCache(workspace=workspace).get_sop(sop_hash)


if __name__ == "__main__":
    # Quick test
    cache = ZeugCache(workspace="test")
    print("Stats:", cache.stats())
