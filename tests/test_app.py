from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from assistant_core.app import _recommended_model, create_app
from assistant_core.config import Settings
from assistant_core.storage import Store


def test_hardware_recommendation_selects_supported_local_model_tiers():
    gib = 1024**3
    assert _recommended_model(4 * gib) == "qwen3:1.7b"
    assert _recommended_model(16 * gib) == "qwen3:8b"
    assert _recommended_model(32 * gib) == "qwen3:30b"
    assert _recommended_model(64 * gib) == "qwen3:32b"
    assert _recommended_model(16 * gib, 24 * gib) == "qwen3:30b"


class FakeOllama:
    async def status(self, model: str) -> dict[str, object]:
        return {"ollama": "ready", "model": model, "model_available": True}

    async def stream_chat(self, model: str, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        assert messages[-1]["content"] == "Hello Aster"
        yield "Hello"
        yield " there."


def test_websocket_requires_random_session_token_and_streams_text(tmp_path):
    settings = Settings(
        port=8765,
        data_dir=tmp_path,
        database_path=tmp_path / "assistant.sqlite3",
        ollama_url="http://127.0.0.1:11434",
        model="qwen3:4b",
        system_prompt="You are Aster.",
    )
    app = create_app(
        settings,
        store=Store(settings.database_path),
        ollama=FakeOllama(),
        auth_token="test-session-secret",
    )
    origin = "http://127.0.0.1:8765"
    conversation_id = "5c2fd25e-3485-48bf-83f4-69fda53661fb"

    with TestClient(
        app,
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 12345),
    ) as client:
        page = client.get("/")
        assert "<title>Aster Local</title>" in page.text
        assert "{{APP_NAME" not in page.text
        assert 'id="launch-warning"' in page.text
        assert page.headers["X-Content-Type-Options"] == "nosniff"
        assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
        stylesheet = client.get("/assets/style.css")
        assert stylesheet.status_code == 200
        assert b".shell" in stylesheet.content
        response = client.post("/api/session", headers={"Origin": origin}, json={})
        assert response.status_code == 200
        assert response.json()["token"] == "test-session-secret"
        assert client.post("/api/session", headers={"Origin": "http://evil.example"}, json={}).status_code == 403

        ws_headers = {"Origin": origin, "Host": "127.0.0.1:8765"}
        with client.websocket_connect("/ws", headers=ws_headers) as socket:
            socket.send_json({"type": "auth", "token": "wrong"})
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()

        with client.websocket_connect("/ws", headers=ws_headers) as socket:
            socket.send_json({"type": "auth", "token": "test-session-secret"})
            assert socket.receive_json() == {"type": "ready"}
            socket.send_json({"type": "chat", "conversation_id": conversation_id, "text": "Hello Aster"})
            events = [socket.receive_json() for _ in range(4)]

    assert [event["type"] for event in events] == ["start", "delta", "delta", "done"]
    assert "".join(event["text"] for event in events if event["type"] == "delta") == "Hello there."
    assert Store(settings.database_path).get_context(conversation_id, 10)[-1].content == "Hello there."

