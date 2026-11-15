from contextlib import contextmanager

from fastapi.testclient import TestClient

from assistant_core.app import create_app
from assistant_core.config import Settings
from assistant_core.storage import Store


class ToolOllama:
    def __init__(self, call):
        self.call = call
        self.turn = 0
        self.prompts = []

    async def status(self, model):
        return {"ollama": "ready", "model": model, "model_available": True}

    async def stream_chat(self, model, messages):
        yield "unused"

    async def stream_chat_events(self, model, messages, tools):
        self.prompts.append(messages)
        if self.turn == 0:
            self.turn += 1
            yield {"type": "tool_call", "id": "call-1", "name": self.call[0], "arguments": self.call[1]}
        else:
            yield {"type": "text", "text": "Done, with the local result."}


class FakeTranscriber:
    installed = False

    def transcribe_pcm(self, pcm):
        return ""


class FakeSpeaker:
    def start(self):
        return {"available": False, "voices": [], "reason": "No local speech voice."}

    def speak(self, text, *, voice="", rate=0, pitch=0):
        return None

    def stop(self):
        return None

    def close(self):
        return None


def _app(tmp_path, call):
    settings = Settings(8765, tmp_path, tmp_path / "assistant.sqlite3", "http://127.0.0.1:11434", "qwen3:4b", "You are Aster.")
    model = ToolOllama(call)
    app = create_app(settings, ollama=model, auth_token="session-secret", transcriber=FakeTranscriber(), speaker=FakeSpeaker())
    return app, model


@contextmanager
def _open_chat(client):
    with client.websocket_connect("/ws", headers={"Origin": "http://127.0.0.1:8765", "Host": "127.0.0.1:8765"}) as socket:
        socket.send_json({"type": "auth", "token": "session-secret"})
        assert socket.receive_json() == {"type": "ready"}
        socket.send_json({"type": "chat", "conversation_id": "5c2fd25e-3485-48bf-83f4-69fda53661fb", "text": "Please calculate or save this."})
        assert socket.receive_json()["type"] == "start"
        yield socket


def test_safe_tool_runs_without_confirmation_and_result_is_marked_untrusted(tmp_path):
    app, model = _app(tmp_path, ("calculator", {"expression": "2 + 2"}))
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 12345)) as client:
        with _open_chat(client) as socket:
            events = []
            while True:
                event = socket.receive_json()
                events.append(event)
                if event["type"] == "done":
                    break
    assert any(event["type"] == "tool_result" and event["ok"] for event in events)
    assert all(event["type"] != "confirmation_required" for event in events)
    assert "Untrusted local tool result" in model.prompts[-1][-1]["content"]


def test_note_write_waits_for_confirmation_before_execution(tmp_path):
    app, _ = _app(tmp_path, ("note_create", {"title": "Trip", "content": "Pack a charger"}))
    store = Store(tmp_path / "assistant.sqlite3")
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 12345)) as client:
        with _open_chat(client) as socket:
            prompt = socket.receive_json()
            assert prompt["type"] == "confirmation_required"
            assert "Trip" in prompt["action"]
            socket.send_json({"type": "confirmation_response", "id": prompt["id"], "confirmed": True})
            for _ in range(4):
                event = socket.receive_json()
                if event["type"] == "done":
                    break
    assert store.search_items("note", "Trip")


def test_mismatched_confirmation_id_does_not_authorize_action(tmp_path):
    app, _ = _app(tmp_path, ("note_create", {"title": "Trip", "content": "Pack a charger"}))
    store = Store(tmp_path / "assistant.sqlite3")
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 12345)) as client:
        with _open_chat(client) as socket:
            prompt = socket.receive_json()
            socket.send_json({"type": "confirmation_response", "id": "wrong-id", "confirmed": True})
            for _ in range(4):
                event = socket.receive_json()
                if event["type"] == "done":
                    break
    assert store.search_items("note", "Trip") == []
