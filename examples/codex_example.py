"""Example: Codex / OpenAI integration with Zeug Prompt Cache.

Copy zeug_cache.py to your Codex project directory, then use like this:
"""

from zeug_cache import ZeugCache
import openai

cache = ZeugCache(workspace="clawpanel")


def codex_chat(prompt: str, model: str = "gpt-5.5") -> str:
    """Chat with Codex, cached."""

    def fallback(p):
        # Your actual Codex / OpenAI call
        return openai.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": p}]
        ).choices[0].message.content

    return cache.chat(prompt, model=model, fallback_fn=fallback)


# Usage
if __name__ == "__main__":
    response = codex_chat("Refactor this function to use async/await")
    print(response)
