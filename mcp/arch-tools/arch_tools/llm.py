"""local_llm: one chat completion on the llama.cpp router (OpenAI-compatible)."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

from .config import DEFAULT_CHAT_MODEL, Config
from .net import ServiceError, ServiceUnavailable, ToolError, request_json

REQUEST_TIMEOUT_S = 300.0  # model swaps on the router can take a while
START_HINT = "start it with `systemctl --user start llm-server`"

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Remove reasoning blocks: closed <think>…</think>, a dangling '…</think>' prefix (opening tag sent in
    the prompt template) and an unterminated trailing '<think>…' (generation cut off while thinking)."""
    if not text:
        return ""
    text = _THINK_BLOCK.sub("", text)
    lowered = text.lower()
    close = lowered.rfind("</think>")
    if close != -1:
        text = text[close + len("</think>") :]
        lowered = text.lower()
    open_ = lowered.find("<think>")
    if open_ != -1:
        text = text[:open_]
    return text.strip()


async def list_models(client: httpx.AsyncClient, cfg: Config) -> list[str]:
    try:
        payload = await request_json(
            client,
            "GET",
            f"{cfg.llm_base}/v1/models",
            headers=cfg.auth_headers(),
            timeout=httpx.Timeout(15.0, connect=5.0),
            service="LLM server",
        )
    except ServiceUnavailable as exc:
        raise ServiceUnavailable(f"{exc.message}. The local LLM server seems to be down; {START_HINT}") from exc
    names: list[str] = []
    for item in payload.get("data", []) if isinstance(payload, dict) else []:
        if isinstance(item, dict) and item.get("id"):
            names.append(str(item["id"]))
            names.extend(str(a) for a in item.get("aliases") or [] if a)
    return names


async def local_llm(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
    max_tokens: int = 2048,
    temperature: float | None = None,
    cfg: Config | None = None,
    client: httpx.AsyncClient | None = None,
    timeout_s: float = REQUEST_TIMEOUT_S,
) -> dict[str, Any]:
    cfg = cfg or Config.from_env()
    model = (model or DEFAULT_CHAT_MODEL).strip()
    if not prompt or not prompt.strip():
        raise ToolError("prompt must not be empty")
    own_client = client is None
    http = client or httpx.AsyncClient()
    try:
        available = await list_models(http, cfg)
        if model not in available:
            raise ToolError(
                f"unknown model {model!r}",
                hint="choose one of the models served by the router",
                data={"available_models": sorted(set(available))},
            )
        messages = []
        if system and system.strip():
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": int(max_tokens), "stream": False}
        if temperature is not None:
            body["temperature"] = float(temperature)

        deadline = time.monotonic() + timeout_s
        started = time.monotonic()
        while True:
            remaining = max(1.0, deadline - time.monotonic())
            try:
                payload = await request_json(
                    http,
                    "POST",
                    f"{cfg.llm_base}/v1/chat/completions",
                    json_body=body,
                    headers=cfg.auth_headers(),
                    timeout=httpx.Timeout(remaining, connect=10.0),
                    service="LLM server",
                )
                break
            except ServiceUnavailable as exc:
                cause = exc.__cause__
                if isinstance(cause, httpx.TimeoutException) and not isinstance(cause, httpx.ConnectTimeout):
                    raise ServiceUnavailable(
                        f"LLM request timed out after {timeout_s:.0f}s (model {model} may still be loading,"
                        " or the prompt/max_tokens is too large)"
                    ) from exc
                raise ServiceUnavailable(
                    f"{exc.message}. The local LLM server seems to be down; {START_HINT}"
                ) from exc
            except ServiceError as exc:
                # 503 while the router swaps/loads a model: retry until the deadline.
                if exc.data.get("status_code") == 503 and time.monotonic() + 3 < deadline:
                    await asyncio.sleep(2.0)
                    continue
                raise
    finally:
        if own_client:
            await http.aclose()

    try:
        choice = payload["choices"][0]
        message = choice.get("message") or {}
    except (KeyError, IndexError, TypeError) as exc:
        raise ServiceError(f"unexpected chat completion payload: {exc}") from exc
    text = strip_think(message.get("content") or "")
    source = "content"
    if not text:
        reasoning = strip_think(message.get("reasoning_content") or "")
        if reasoning and choice.get("finish_reason") == "length":
            # a thinking model ran out of tokens mid-thought: its reasoning is not an answer
            text, source = "", "empty"
        else:
            text = reasoning
            source = "reasoning_content" if text else "empty"
    result: dict[str, Any] = {
        "model": payload.get("model") or model,
        "text": text,
        "source": source,
        "finish_reason": choice.get("finish_reason"),
        "seconds": round(time.monotonic() - started, 2),
    }
    if payload.get("usage"):
        result["usage"] = {
            k: payload["usage"][k] for k in ("prompt_tokens", "completion_tokens", "total_tokens") if k in payload["usage"]
        }
    if source == "empty":
        result["warning"] = "the model returned no text (try a larger max_tokens)"
    return result
