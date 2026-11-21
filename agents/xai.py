"""Minimal xAI Responses API client (standard library only).

POST https://api.x.ai/v1/responses with server-side tools such as x_search.
Docs: https://docs.x.ai/docs/guides/tools/search-tools
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

XAI_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-4.7"


class XAIError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"xAI API HTTP {status}: {body[:800]}")
        self.status = status
        self.body = body


@dataclass
class Result:
    text: str
    model: str
    usage: dict = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    @property
    def cost_usd(self) -> float | None:
        u = self.usage or {}
        if u.get("cost_in_usd_ticks") is not None:
            return u["cost_in_usd_ticks"] / 1e10
        if u.get("cost_in_nano_usd") is not None:
            return u["cost_in_nano_usd"] / 1e9
        return None

    def usage_line(self) -> str:
        u = self.usage or {}
        tools = u.get("server_side_tool_usage_details") or {}
        cost = self.cost_usd
        bits = [f"model {self.model}",
                f"tokens in/out {u.get('input_tokens', '?')}/{u.get('output_tokens', '?')}"]
        if tools:
            bits.append("tools " + ", ".join(f"{k}={v}" for k, v in tools.items() if v))
        bits.append(f"cost ${cost:.4f}" if cost is not None else "cost n/a")
        return " · ".join(bits)


def x_search_tool(from_date: str | None = None, handles: list[str] | None = None) -> dict:
    tool: dict = {"type": "x_search"}
    if from_date:
        tool["from_date"] = from_date
    if handles:
        tool["allowed_x_handles"] = [h.lstrip("@") for h in handles][:20]
    return tool


def parse_response(data: dict) -> tuple[str, list[str]]:
    """Return (final text, cited URLs) from a Responses API payload."""
    texts: list[str] = []
    urls: list[str] = []
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") in ("output_text", "text") and part.get("text"):
                texts.append(part["text"])
            for a in part.get("annotations") or []:
                if a.get("url") and a["url"] not in urls:
                    urls.append(a["url"])
    if not texts and isinstance(data.get("output_text"), str):
        texts.append(data["output_text"])
    for u in data.get("citations") or []:
        if isinstance(u, str) and u not in urls:
            urls.append(u)
    return "\n".join(texts).strip(), urls


def respond(user_input: str, *, instructions: str, model: str | None = None,
            tools: list[dict] | None = None, max_turns: int | None = None,
            api_key: str | None = None, timeout: int = 900, retries: int = 3) -> Result:
    key = api_key or os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        raise XAIError(0, "XAI_API_KEY is not set")
    model = model or os.environ.get("XAI_MODEL", "").strip() or DEFAULT_MODEL
    body: dict = {
        "model": model,
        "instructions": instructions,
        "input": [{"role": "user", "content": user_input}],
        "include": ["no_inline_citations"],
    }
    if tools:
        body["tools"] = tools
    if max_turns:
        body["max_turns"] = max_turns

    attempt = 0
    while True:
        attempt += 1
        req = urllib.request.Request(
            XAI_URL, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "User-Agent": "x-bot-agents"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            break
        except urllib.error.HTTPError as e:
            err = XAIError(e.code, e.read().decode(errors="replace"))
            # Optional fields the API may reject: drop them once and retry.
            if e.code in (400, 422) and "include" in body and "include" in err.body:
                body.pop("include")
                continue
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(15 * attempt)
                continue
            raise err from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(15 * attempt)
                continue
            raise XAIError(0, f"network error: {e}") from None

    text, urls = parse_response(data)
    return Result(text=text, model=data.get("model", model), usage=data.get("usage") or {}, sources=urls)
