from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from assistant_core.app import create_app
from assistant_core.config import Settings


class FakeOllama:
    async def status(self, model: str) -> dict[str, object]:
        return {"ollama": "ready", "model": model, "model_available": True}

    async def stream_chat(self, model: str, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        yield "A response."


class FakeTranscriber:
    installed = True

    def transcribe_pcm(self, pcm: bytes) -> str:
        return "A local voice test."


class FakeSpeaker:
    available = True

    def __init__(self):
        self.spoken = []

    def start(self):
        if not self.available:
            return {"available": False, "voices": [], "reason": "No local voice is installed."}
        return {"available": True, "voices": ["Test Voice"]}

    def speak(self, text, *, voice="", rate=0, pitch=0):
        self.spoken.append((text, voice, rate, pitch))

    def stop(self):
        return None

    def close(self):
        return None


def test_transcribe_route_is_authenticated_bounded_and_never_persists_audio(tmp_path):
    settings = Settings(
        port=8765,
        data_dir=tmp_path,
        database_path=tmp_path / "assistant.sqlite3",
        ollama_url="http://127.0.0.1:11434",
        model="qwen3:4b",
        system_prompt="You are Aster.",
    )
    speaker = FakeSpeaker()
    app = create_app(settings, ollama=FakeOllama(), auth_token="session-secret", transcriber=FakeTranscriber(), speaker=speaker)
    origin = {"Origin": "http://127.0.0.1:8765", "Authorization": "Bearer session-secret"}
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 12345)) as client:
        assert client.post(
            "/api/transcribe", headers={"Content-Type": "application/octet-stream"}, content=b"\x00\x00"
        ).status_code == 403
        result = client.post(
            "/api/transcribe",
            headers={**origin, "Content-Type": "application/octet-stream"},
            content=b"\x00\x01",
        )
        assert result.status_code == 200
        assert result.json() == {"text": "A local voice test."}
        wrong_type = client.post(
            "/api/transcribe", headers={**origin, "Content-Type": "application/json"}, content=b"{}"
        )
        assert wrong_type.status_code == 415
        too_large = client.post(
            "/api/transcribe",
            headers={**origin, "Content-Type": "application/octet-stream"},
            content=b"\x00" * 1_000_001,
        )
        assert too_large.status_code == 413
        status = client.get("/api/voice/status", headers=origin).json()
        assert status["audio_saved"] is False
        assert status["speech_model_installed"] is True
        assert client.post("/api/speech/test", json={}).status_code == 403
        test_result = client.post("/api/speech/test", headers=origin, json={"voice": "Test Voice", "rate": 2, "pitch": -1})
        assert test_result.status_code == 200
        assert test_result.json()["started"] is True
        assert speaker.spoken == [("Aster local speech is ready.", "Test Voice", 2, -1)]
        invalid_voice = client.post("/api/speech/test", headers=origin, json={"voice": "Not Installed"})
        assert invalid_voice.status_code == 422
    assert not list(tmp_path.glob("*.wav"))


def test_speaker_test_reports_missing_local_voice(tmp_path):
    settings = Settings(
        port=8765,
        data_dir=tmp_path,
        database_path=tmp_path / "assistant.sqlite3",
        ollama_url="http://127.0.0.1:11434",
        model="qwen3:4b",
        system_prompt="You are Aster.",
    )
    speaker = FakeSpeaker()
    speaker.available = False
    app = create_app(settings, ollama=FakeOllama(), auth_token="session-secret", transcriber=FakeTranscriber(), speaker=speaker)
    origin = {"Origin": "http://127.0.0.1:8765", "Authorization": "Bearer session-secret"}
    with TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 12345)) as client:
        result = client.post("/api/speech/test", headers=origin, json={})
        assert result.status_code == 503
        assert result.json()["detail"] == "No local voice is installed."
        assert not speaker.spoken
