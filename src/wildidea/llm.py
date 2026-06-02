"""LLM client for WildIdea. Zero dependencies — uses stdlib urllib only.

Supports any OpenAI-compatible API (OpenRouter, OpenAI, Ollama, etc.)
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Optional


PROVIDERS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
    },
    "xiaomi": {
        "base_url": "https://api.xiaomimimo.com/v1",
        "env_key": "MIMO_API_KEY",
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "env_key": "SILICONFLOW_API_KEY",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "env_key": None,
    },
}


def extract_json(text: str) -> Optional[dict]:
    """Extract first complete JSON object using bracket counting.

    Handles: markdown code blocks, nested objects, trailing text.
    """
    # Try markdown code block first
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Bracket counting
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        if depth == 0:
            try:
                return json.loads(text[start : i + 1])
            except json.JSONDecodeError:
                # Try next '{'
                next_start = text.find("{", start + 1)
                if next_start > start:
                    return extract_json(text[next_start:])
                return None
    return None


class LLMClient:
    """OpenAI-compatible chat client. Zero external dependencies."""

    def __init__(
        self,
        provider: str,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        proxy: Optional[str] = None,
    ):
        self.model = model
        self.proxy = proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

        if base_url:
            self.base_url = base_url.rstrip("/")
        elif provider in PROVIDERS:
            self.base_url = PROVIDERS[provider]["base_url"]
        else:
            raise ValueError(f"Unknown provider '{provider}'. Pass --base-url or use: {list(PROVIDERS.keys())}")

        if api_key:
            self.api_key = api_key
        elif provider in PROVIDERS and PROVIDERS[provider]["env_key"]:
            env = PROVIDERS[provider]["env_key"]
            self.api_key = os.environ.get(env)
            if not self.api_key:
                raise ValueError(f"Set {env} environment variable or pass --api-key")
        else:
            self.api_key = "ollama"  # Ollama doesn't need a real key

    def _post(self, payload: dict, timeout: int = 120) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        if self.proxy:
            handler = urllib.request.ProxyHandler({"https": self.proxy, "http": self.proxy})
            opener = urllib.request.build_opener(handler)
        else:
            opener = urllib.request.build_opener()
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        retries: int = 3,
    ) -> str:
        """Single chat completion call. Returns content string."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        for attempt in range(retries):
            try:
                data = self._post(payload)
                if "error" in data:
                    raise RuntimeError(data["error"].get("message", str(data["error"])))
                msg = data["choices"][0]["message"]
                content = msg.get("content", "") or ""
                # Some reasoning models put output in 'reasoning' when content is empty
                if not content.strip() and msg.get("reasoning"):
                    content = msg["reasoning"]
                return content
            except Exception as e:
                if attempt < retries - 1:
                    import time
                    time.sleep(2 * (attempt + 1))
                    continue
                raise

    def chat_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        retries: int = 3,
    ) -> dict:
        """Chat completion that returns parsed JSON. Uses bracket-counting parser."""
        for attempt in range(retries):
            mt = max_tokens + attempt * 500  # Increase on retry
            content = self.chat(system, user, temperature=temperature, max_tokens=mt)
            parsed = extract_json(content)
            if parsed:
                return parsed
        raise ValueError(f"Failed to parse JSON from LLM response after {retries} attempts")
