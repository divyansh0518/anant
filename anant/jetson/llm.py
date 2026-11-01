"""Thin client for any OpenAI-compatible chat endpoint (Ollama, llama.cpp server, cloud)."""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

import requests

log = logging.getLogger("anant.llm")
_TAG = re.compile(r"^\s*\[(\w+)\]\s*")


class LLM:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout_s: float = 30) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.timeout = model, timeout_s
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 160) -> str:
        try:
            r = requests.post(self.url, headers=self.headers, timeout=self.timeout, json={
                "model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:  # network down, model not loaded, ...
            log.warning("LLM unavailable: %s", e)
            return "[thinking] Sorry, my language model is not responding right now."


def split_expression(reply: str, valid: List[str]) -> Tuple[str, str]:
    """'[happy] Hello!' -> ('happy', 'Hello!'). Unknown or missing tag -> 'neutral'."""
    m = _TAG.match(reply)
    if m and m.group(1).lower() in valid:
        return m.group(1).lower(), reply[m.end():].strip()
    return "neutral", _TAG.sub("", reply).strip()
