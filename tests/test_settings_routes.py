from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from assistant_core.app import create_app
from assistant_core.config import Settings


class FakeOllama:
    async def status(self, model: str) -> dict[str, object]:
        return {"ollama": "ready", "model": model, "model_available": True}

    async def embed(self, model: str, text: str) -> list[float]:
        assert model == "nomic-embed-text:v1.5"
        return [1.0, 0.0]

    async def stream_chat(self, model: str, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        yield "ok"


class FakeTranscriber:
    installed = False

    def transcribe_pcm(self, pcm: bytes) -> str:
        return ""


class FakeSpeaker:
    def start(self):
        return {"available": False, "voices": [], "reason": "No local speech voice is installed."}

    def speak(self, text, *, voice="", rate=0, pitch=0):
        return None

    def stop(self):
        return None

    def close(self):
        return None


def test_settings_are_authenticated_validated_and_persisted(tmp_path):
    settings = Settings(8765, tmp_path, tmp_path / "assistant.sqlite3", "http://127.0.0.1:11434", "qwen3:4b", "You are Aster.")
    app = create_app(settings, ollama=FakeOllama(), auth_token="secret", transcriber=FakeTranscriber(), speaker=FakeSpeaker())
    headers = {"Origin": "http://127.0.0.1:8765", "Authorization": "Bearer secret"}
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 12345)) as client:
        initial = client.get("/api/settings", headers=headers)
        assert initial.status_code == 200
        assert initial.json()["web_search_enabled"] is False
        assert initial.json()["semantic_memory_enabled"] is False
        updated = client.put(
            "/api/settings",
            headers=headers,
            json={"model": "qwen3:8b", "web_search_enabled": True, "mode": "both", "voice_rate": 2},
        )
        assert updated.status_code == 200
        assert updated.json()["model"] == "qwen3:8b"
        assert updated.json()["web_search_enabled"] is True
        assert updated.json()["voice_rate"] == 2
        semantic = client.put("/api/settings", headers=headers, json={"semantic_memory_enabled": True})
        assert semantic.status_code == 200
        assert semantic.json()["semantic_memory_enabled"] is True
        saved_memory = client.post("/api/memories", headers=headers, json={"content": "I prefer local notes."})
        assert saved_memory.status_code == 201
        assert app.state.store.search_memories_by_embedding([1.0, 0.0]) == ["I prefer local notes."]
        if initial.json()["encryption"]["supported"]:
            encrypted = client.put("/api/encryption", headers=headers, json={"enabled": True})
            assert encrypted.status_code == 200
            assert encrypted.json()["enabled"] is True
            assert client.get("/api/settings", headers=headers).status_code == 200
            plaintext = client.put("/api/encryption", headers=headers, json={"enabled": False})
            assert plaintext.status_code == 200
            assert plaintext.json()["enabled"] is False
        invalid = client.put("/api/settings", headers=headers, json={"model": "qwen3:8b-cloud"})
        assert invalid.status_code == 422
        forbidden = client.get("/api/settings")
        assert forbidden.status_code == 403
