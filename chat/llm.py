"""Client for the local Ollama server (listens only on 127.0.0.1:11434)."""

import os

import requests

SYSTEM_PROMPT = (
    "You are a friendly assistant on a student's Linux server. "
    "Answer briefly and clearly, in the same language the user writes in."
)


class LLMError(Exception):
    """Raised when the model server does not give a usable answer."""


class OllamaClient:
    def __init__(self, base_url, model, timeout=150, max_tokens=400):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    @classmethod
    def from_env(cls):
        return cls(
            base_url=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
            model=os.environ.get("OLLAMA_MODEL", "gemma3:1b"),
        )

    def chat(self, messages):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            "stream": False,
            "options": {"num_predict": self.max_tokens},
        }
        try:
            response = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
            content = response.json()["message"]["content"]
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            raise LLMError(str(exc)) from exc
        return content.strip() or "(the model returned an empty reply)"
