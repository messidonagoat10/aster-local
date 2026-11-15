"""Minimal, streaming client for Ollama's loopback HTTP API."""

from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator, Sequence

import httpx2 as httpx


class OllamaFailure(Exception):
    """A safe-to-display local inference failure with a stable machine code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OllamaClient:
    def __init__(
        self, base_url: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.base_url = base_url
        self.transport = transport

    async def embed(self, model: str, text: str) -> list[float]:
        """Create a semantic vector using Ollama's local embeddings endpoint."""
        if not 1 <= len(text) <= 8000:
            raise OllamaFailure("invalid_embedding_input", "Memory search text must contain 1 to 8000 characters.")
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=3.0),
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": model, "input": text},
                )
        except httpx.ConnectError as exc:
            raise OllamaFailure("ollama_unavailable", "Ollama is not responding. Start it and try again.") from exc
        except httpx.HTTPError as exc:
            raise OllamaFailure("embedding_failed", "Could not communicate with local Ollama embeddings.") from exc
        if response.status_code == 404:
            raise OllamaFailure("embedding_model_missing", f"Install the local embedding model {model!r} first.")
        if response.status_code >= 400:
            raise OllamaFailure("embedding_failed", "Ollama could not create a local memory embedding.")
        try:
            payload = response.json()
            embeddings = payload.get("embeddings")
            vector = embeddings[0]
            if not isinstance(vector, list) or not 1 <= len(vector) <= 4096:
                raise ValueError("Invalid embedding dimensions.")
            result = [float(value) for value in vector]
            if any(not math.isfinite(value) for value in result):
                raise ValueError("Non-finite embedding.")
            return result
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise OllamaFailure("invalid_embedding_response", "Ollama returned an invalid embedding vector.") from exc

    async def status(self, model: str) -> dict[str, object]:
        timeout = httpx.Timeout(5.0, connect=2.0)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.get(f"{self.base_url}/api/tags")
        except httpx.HTTPError:
            return {"ollama": "unavailable", "model": model, "model_available": False}
        if response.status_code != 200:
            return {"ollama": "error", "model": model, "model_available": False}
        try:
            models = response.json().get("models", [])
            names = {entry.get("name") for entry in models if isinstance(entry, dict)}
        except (ValueError, AttributeError, TypeError):
            return {"ollama": "error", "model": model, "model_available": False}
        available = model in names or f"{model}:latest" in names
        return {
            "ollama": "ready",
            "model": model,
            "model_available": available,
            "installed_models": sorted(name for name in names if isinstance(name, str)),
        }

    async def stream_chat(
        self, model: str, messages: Sequence[dict[str, str]]
    ) -> AsyncIterator[str]:
        timeout = httpx.Timeout(90.0, connect=3.0, read=None, write=10.0, pool=5.0)
        payload = {"model": model, "messages": list(messages), "stream": True}
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/api/chat", json=payload
                ) as response:
                    if response.status_code == 404:
                        raise OllamaFailure(
                            "model_missing",
                            f"The model {model!r} is not installed. Run `ollama pull {model}` and retry.",
                        )
                    if response.status_code >= 400:
                        raise OllamaFailure(
                            "ollama_error",
                            f"Ollama returned HTTP {response.status_code}. Check that the local service is healthy.",
                        )
                    got_text = False
                    got_done = False
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise OllamaFailure(
                                "invalid_model_response", "Ollama returned an invalid streaming response."
                            ) from exc
                        if not isinstance(event, dict):
                            raise OllamaFailure(
                                "invalid_model_response", "Ollama returned an invalid streaming response."
                            )
                        if event.get("error"):
                            raise OllamaFailure("ollama_error", "Ollama could not complete the response.")
                        message = event.get("message") or {}
                        if not isinstance(message, dict):
                            raise OllamaFailure(
                                "invalid_model_response", "Ollama returned an invalid streaming response."
                            )
                        content = message.get("content") or ""
                        if content:
                            got_text = True
                            yield str(content)
                        if event.get("done"):
                            got_done = True
                            if not got_text:
                                raise OllamaFailure(
                                    "empty_response", "The model returned an empty response. Try again."
                                )
                            return
                    if not got_done:
                        raise OllamaFailure(
                            "incomplete_response", "The local model stream ended before it completed. Try again."
                        )
        except OllamaFailure:
            raise
        except httpx.ConnectError as exc:
            raise OllamaFailure(
                "ollama_unavailable",
                "Ollama is not responding. Start Ollama, then try again.",
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaFailure(
                "ollama_timeout", "The local model took too long to respond. Try a smaller model or shorter prompt."
            ) from exc
        except httpx.HTTPError as exc:
            raise OllamaFailure("ollama_unavailable", "Could not communicate with local Ollama.") from exc

    async def stream_chat_events(
        self,
        model: str,
        messages: Sequence[dict[str, object]],
        tools: Sequence[dict[str, object]],
    ) -> AsyncIterator[dict[str, object]]:
        """Stream text and return complete structured tool calls from Ollama."""
        timeout = httpx.Timeout(90.0, connect=3.0, read=None, write=10.0, pool=5.0)
        payload = {"model": model, "messages": list(messages), "tools": list(tools), "stream": True}
        pending_calls: dict[str, dict[str, object]] = {}
        got_any = False
        got_done = False
        held_text: list[str] = []
        released_text = False
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                trust_env=False,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    if response.status_code == 404:
                        raise OllamaFailure("model_missing", f"The model {model!r} is not installed. Run `ollama pull {model}` and retry.")
                    if response.status_code >= 400:
                        raise OllamaFailure("ollama_error", f"Ollama returned HTTP {response.status_code}. Check that the local service is healthy.")
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise OllamaFailure("invalid_model_response", "Ollama returned an invalid streaming response.") from exc
                        if not isinstance(event, dict):
                            raise OllamaFailure("invalid_model_response", "Ollama returned an invalid streaming response.")
                        if event.get("error"):
                            raise OllamaFailure("ollama_error", "Ollama could not complete the response.")
                        message = event.get("message") or {}
                        if not isinstance(message, dict):
                            raise OllamaFailure("invalid_model_response", "Ollama returned an invalid streaming response.")
                        content = message.get("content") or ""
                        if content:
                            got_any = True
                            value = str(content)
                            if released_text:
                                yield {"type": "text", "text": value}
                            else:
                                held_text.append(value)
                                candidate = "".join(held_text)
                                stripped = candidate.lstrip()
                                is_json_candidate = not stripped or stripped.startswith("{")
                                xml_prefix = "<tool_call>"
                                is_xml_candidate = stripped.startswith(xml_prefix) or (
                                    stripped.startswith("<") and xml_prefix.startswith(stripped)
                                )
                                if len(candidate) > 12_000 or not (is_json_candidate or is_xml_candidate):
                                    released_text = True
                                    for held in held_text:
                                        yield {"type": "text", "text": held}
                                    held_text.clear()
                        calls = message.get("tool_calls") or []
                        if calls and not isinstance(calls, list):
                            raise OllamaFailure("invalid_model_response", "Ollama returned an invalid tool call.")
                        for index, call in enumerate(calls):
                            if not isinstance(call, dict):
                                continue
                            function = call.get("function") or {}
                            if not isinstance(function, dict) or not isinstance(function.get("name"), str):
                                continue
                            call_id = str(call.get("id") or call.get("index") or index)
                            arguments = function.get("arguments") or {}
                            if isinstance(arguments, str):
                                try:
                                    arguments = json.loads(arguments, object_pairs_hook=_reject_duplicate_keys)
                                except (json.JSONDecodeError, ValueError):
                                    continue
                            if not isinstance(arguments, dict):
                                continue
                            previous = pending_calls.get(call_id, {})
                            merged = dict(previous.get("arguments", {}))
                            merged.update(arguments)
                            pending_calls[call_id] = {"id": call_id, "name": function["name"], "arguments": merged}
                            got_any = True
                        if event.get("done"):
                            got_done = True
                            if held_text:
                                candidate = "".join(held_text).strip()
                                fallback = _fallback_tool_call(candidate)
                                if fallback is not None:
                                    call_id = f"fallback-{len(pending_calls) + 1}"
                                    pending_calls[call_id] = {"id": call_id, **fallback}
                                else:
                                    for held in held_text:
                                        yield {"type": "text", "text": held}
                                held_text.clear()
                            for call in pending_calls.values():
                                yield {"type": "tool_call", **call}
                            if not got_any:
                                raise OllamaFailure("empty_response", "The model returned an empty response. Try again.")
                            return
                    if not got_done:
                        raise OllamaFailure("incomplete_response", "The local model stream ended before it completed. Try again.")
        except OllamaFailure:
            raise
        except httpx.ConnectError as exc:
            raise OllamaFailure("ollama_unavailable", "Ollama is not responding. Start Ollama, then try again.") from exc
        except httpx.TimeoutException as exc:
            raise OllamaFailure("ollama_timeout", "The local model took too long to respond. Try a smaller model or shorter prompt.") from exc
        except httpx.HTTPError as exc:
            raise OllamaFailure("ollama_unavailable", "Could not communicate with local Ollama.") from exc


def _fallback_tool_call(text: str) -> dict[str, object] | None:
    """Accept only a strict JSON or tagged function request as the small-model fallback."""
    if text.startswith("<tool_call>") and text.endswith("</tool_call>"):
        text = text[len("<tool_call>") : -len("</tool_call>")].strip()
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    name = payload.get("name") or payload.get("tool")
    arguments = payload.get("arguments", {})
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return None
    return {"name": name, "arguments": arguments}


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result

