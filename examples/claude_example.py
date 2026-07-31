"""Example: Anthropic Claude integration with Zeug Prompt Cache.

Copy zeug_cache.py to your Claude project directory, then use like this:
"""

from zeug_cache import ZeugCache
import anthropic

cache = ZeugCache(workspace="clawpanel")
client = anthropic.Anthropic()


def claude_chat(prompt: str, model: str = "claude-sonnet-4") -> str:
    """Chat with Claude, cached."""

    def fallback(p):
        # Your actual Claude call
        return client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": p}]
        ).content[0].text

    return cache.chat(prompt, model=model, fallback_fn=fallback)


# Usage
if __name__ == "__main__":
    response = claude_chat("Explain quantum computing in simple terms")
    print(response)
