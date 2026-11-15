import asyncio
import json

import httpx2
import pytest

from assistant_core.ollama import OllamaClient, OllamaFailure


def test_stream_chat_parses_local_ollama_chunks_and_completion():
    request_seen = []

    def respond(request):
        request_seen.append(request)
        return httpx2.Response(
            200,
            content=(
                b'{"message":{"role":"assistant","content":"Hello"},"done":false}\n'
                b'{"message":{"role":"assistant","content":" there."},"done":false}\n'
                b'{"message":{"role":"assistant","content":""},"done":true}\n'
            ),
        )

    transport = httpx2.MockTransport(respond)
    client = OllamaClient("http://127.0.0.1:11434", transport=transport)

    async def collect():
        return [chunk async for chunk in client.stream_chat("qwen3:4b", [{"role": "user", "content": "Hi"}])]

    chunks = asyncio.run(collect())

    assert chunks == ["Hello", " there."]
    assert request_seen[0].url.host == "127.0.0.1"
    assert request_seen[0].url.path == "/api/chat"
    assert json.loads(request_seen[0].content)["stream"] is True


def test_stream_chat_reports_missing_model_and_incomplete_stream():
    missing = OllamaClient(
        "http://127.0.0.1:11434",
        transport=httpx2.MockTransport(lambda _: httpx2.Response(404)),
    )

    async def collect_missing():
        return [chunk async for chunk in missing.stream_chat("qwen3:4b", [])]

    with pytest.raises(OllamaFailure) as missing_error:
        asyncio.run(collect_missing())
    assert missing_error.value.code == "model_missing"

    incomplete = OllamaClient(
        "http://127.0.0.1:11434",
        transport=httpx2.MockTransport(
            lambda _: httpx2.Response(
                200,
                content=b'{"message":{"content":"partial"},"done":false}\n',
            )
        ),
    )

    async def collect_incomplete():
        return [chunk async for chunk in incomplete.stream_chat("qwen3:4b", [])]

    with pytest.raises(OllamaFailure) as incomplete_error:
        asyncio.run(collect_incomplete())
    assert incomplete_error.value.code == "incomplete_response"


def test_stream_chat_events_returns_structured_tool_calls_after_text():
    request_seen = []

    def respond(request):
        request_seen.append(json.loads(request.content))
        return httpx2.Response(
            200,
            content=(
                b'{"message":{"role":"assistant","content":"Checking that."},"done":false}\n'
                b'{"message":{"role":"assistant","content":"","tool_calls":[{"id":"call-1","function":{"name":"calculator","arguments":{"expression":"2+2"}}}]},"done":true}\n'
            ),
        )

    client = OllamaClient("http://127.0.0.1:11434", transport=httpx2.MockTransport(respond))

    async def collect():
        return [event async for event in client.stream_chat_events("qwen3:4b", [], [{"type": "function"}])]

    events = asyncio.run(collect())

    assert events == [
        {"type": "text", "text": "Checking that."},
        {"type": "tool_call", "id": "call-1", "name": "calculator", "arguments": {"expression": "2+2"}},
    ]
    assert request_seen[0]["tools"] == [{"type": "function"}]


def test_stream_chat_events_accepts_only_strict_small_model_json_tool_fallback():
    body = (
        b'{"message":{"content":"<tool_call>{\\"name\\":\\"calculator\\",\\"arguments\\":{\\"expression\\":\\"2+2\\"}}</tool_call>"},"done":true}\n'
    )
    client = OllamaClient("http://127.0.0.1:11434", transport=httpx2.MockTransport(lambda _: httpx2.Response(200, content=body)))

    async def collect():
        return [event async for event in client.stream_chat_events("qwen3:1.7b", [], [])]

    assert asyncio.run(collect()) == [
        {"type": "tool_call", "id": "fallback-1", "name": "calculator", "arguments": {"expression": "2+2"}}
    ]


def test_stream_chat_events_does_not_treat_duplicate_json_keys_as_a_tool_call():
    body = b'{"message":{"content":"{\\"name\\":\\"calculator\\",\\"name\\":\\"shell_run\\",\\"arguments\\":{}}"},"done":true}\n'
    client = OllamaClient("http://127.0.0.1:11434", transport=httpx2.MockTransport(lambda _: httpx2.Response(200, content=body)))

    async def collect():
        return [event async for event in client.stream_chat_events("qwen3:1.7b", [], [])]

    assert asyncio.run(collect()) == [
        {"type": "text", "text": '{"name":"calculator","name":"shell_run","arguments":{}}'}
    ]


def test_embed_uses_local_api_and_rejects_invalid_vectors():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx2.Response(200, json={"embeddings": [[0.25, 0.75]]})

    client = OllamaClient("http://127.0.0.1:11434", transport=httpx2.MockTransport(respond))
    vector = asyncio.run(client.embed("nomic-embed-text:v1.5", "search_query: local notes"))

    assert vector == [0.25, 0.75]
    assert requests[0].url.host == "127.0.0.1"
    assert requests[0].url.path == "/api/embed"
    assert json.loads(requests[0].content) == {
        "model": "nomic-embed-text:v1.5",
        "input": "search_query: local notes",
    }

    malformed = OllamaClient(
        "http://127.0.0.1:11434",
        transport=httpx2.MockTransport(lambda _: httpx2.Response(200, content=b'{"embeddings":[[NaN]]}')),
    )
    with pytest.raises(OllamaFailure) as error:
        asyncio.run(malformed.embed("nomic-embed-text:v1.5", "query"))
    assert error.value.code == "invalid_embedding_response"
