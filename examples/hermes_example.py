"""Example: Hermes / Remote agent integration with Zeug Prompt Cache.

Hermes runs on AWS Lightsail. Just needs `requests` installed and zeug_cache.py copied.

ssh hermes
pip install requests
scp zeug_cache.py hermes:~/project/
"""

from zeug_cache import ZeugCache

# Works from anywhere — the API is HTTP and public via Serveo
cache = ZeugCache(workspace="clawpanel")


def hermes_kimi_chat(prompt: str) -> str:
    """Hermes calling Kimi API with caching."""

    def fallback(p):
        # Your Kimi API call (however you call it on Hermes)
        import requests
        r = requests.post(
            "https://agent-gw.kimi.com/coding/v1/chat/completions",
            headers={"Authorization": "Bearer YOUR_KIMI_KEY"},
            json={"model": "kimi-k3", "messages": [{"role": "user", "content": p}]}
        )
        return r.json()["choices"][0]["message"]["content"]

    return cache.chat(prompt, model="kimi-k3", fallback_fn=fallback)


# Usage
if __name__ == "__main__":
    response = hermes_kimi_chat("Summarize this transcript: ...")
    print(response)
