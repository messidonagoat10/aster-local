"""Offline speech recognition and local operating-system speech output.

The microphone path accepts only bounded 16 kHz mono PCM supplied after an
explicit push-to-talk action. Audio is processed in memory and never stored.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from array import array
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2


WHISPER_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/"
    "sherpa-onnx-whisper-tiny.en.tar.bz2"
)
WHISPER_SHA256 = "2bd6cf965c8bb3e068eff9fa2191387ee63a9dfa2a4e37582a8109641c20005dd"
WHISPER_ARCHIVE_BYTES = 118_071_777
WHISPER_MAX_SECONDS = 30
WHISPER_SAMPLE_RATE = 16_000
WHISPER_FILES = (
    "tiny.en-encoder.int8.onnx",
    "tiny.en-decoder.onnx",
    "tiny.en-tokens.txt",
)
MAX_PCM_BYTES = WHISPER_SAMPLE_RATE * 2 * WHISPER_MAX_SECONDS


class VoiceFailure(Exception):
    """A safe-to-display local speech failure with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class WhisperTranscriber:
    """Lazily load the pinned, local Whisper tiny English recognizer."""

    def __init__(self, model_dir: Path, recognizer_factory: Callable[..., Any] | None = None) -> None:
        self.model_dir = model_dir
        self._recognizer_factory = recognizer_factory
        self._recognizer: Any | None = None
        self._lock = threading.Lock()

    @property
    def installed(self) -> bool:
        return all((self.model_dir / name).is_file() for name in WHISPER_FILES)

    def transcribe_pcm(self, pcm: bytes) -> str:
        if len(pcm) < WHISPER_SAMPLE_RATE // 4:
            raise VoiceFailure("audio_too_short", "Hold the microphone button and speak for at least a moment.")
        if len(pcm) > MAX_PCM_BYTES:
            raise VoiceFailure("audio_too_long", "Voice messages are limited to 30 seconds.")
        if len(pcm) % 2:
            raise VoiceFailure("invalid_audio", "The microphone sent an incomplete audio frame. Try again.")
        if not self.installed:
            raise VoiceFailure("stt_model_missing", "The speech model is missing. Download it from Setup first.")

        if self._recognizer is None:
            with self._lock:
                if self._recognizer is None:
                    self._recognizer = self._load_recognizer()

        samples = array("h")
        samples.frombytes(pcm)
        if sys.byteorder != "little":
            samples.byteswap()
        waveform = [sample / 32768.0 for sample in samples]
        if max((abs(sample) for sample in waveform), default=0.0) < 0.005:
            raise VoiceFailure("no_speech", "I could not hear speech. Check your microphone and try again.")
        try:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(WHISPER_SAMPLE_RATE, waveform)
            self._recognizer.decode_stream(stream)
            result = stream.result.text.strip()
        except Exception as exc:
            raise VoiceFailure("stt_failed", "Local speech recognition failed. Check the diagnostics and retry.") from exc
        if not result:
            raise VoiceFailure("no_transcription", "I could not make out those words. Try speaking more clearly.")
        return result

    def _load_recognizer(self) -> Any:
        factory = self._recognizer_factory
        if factory is None:
            try:
                import sherpa_onnx
            except ImportError as exc:
                raise VoiceFailure(
                    "stt_dependency_missing", "Install the optional voice dependencies with `uv sync --extra voice`."
                ) from exc
            factory = sherpa_onnx.OfflineRecognizer.from_whisper
        return factory(
            encoder=str(self.model_dir / WHISPER_FILES[0]),
            decoder=str(self.model_dir / WHISPER_FILES[1]),
            tokens=str(self.model_dir / WHISPER_FILES[2]),
            num_threads=max(1, min(4, os.cpu_count() or 1)),
            decoding_method="greedy_search",
            provider="cpu",
        )


async def download_whisper_model(model_dir: Path) -> None:
    """Fetch only the pinned model archive after an explicit user action."""
    model_dir.mkdir(parents=True, exist_ok=True)
    if all((model_dir / name).is_file() for name in WHISPER_FILES):
        return
    fd, archive_name = tempfile.mkstemp(prefix="aster-whisper-", suffix=".tar.bz2", dir=model_dir)
    os.close(fd)
    archive_path = Path(archive_name)
    stage_dir = model_dir / ".whisper-staging"
    try:
        digest = hashlib.sha256()
        byte_count = 0
        timeout = httpx2.Timeout(120.0, connect=15.0, read=120.0, write=30.0, pool=10.0)
        async with httpx2.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=True) as client:
            async with client.stream("GET", WHISPER_URL) as response:
                if response.status_code != 200:
                    raise VoiceFailure("download_failed", f"The speech model server returned HTTP {response.status_code}.")
                with archive_path.open("wb") as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        byte_count += len(chunk)
                        if byte_count > WHISPER_ARCHIVE_BYTES:
                            raise VoiceFailure("download_size_mismatch", "The speech model archive was larger than expected.")
                        digest.update(chunk)
                        output.write(chunk)
        if byte_count != WHISPER_ARCHIVE_BYTES or digest.hexdigest() != WHISPER_SHA256:
            raise VoiceFailure("checksum_mismatch", "The speech model checksum did not match. The download was discarded.")

        stage_dir.mkdir(exist_ok=True)
        extracted: set[str] = set()
        with tarfile.open(archive_path, mode="r:bz2") as archive:
            for member in archive.getmembers():
                if not member.isfile() or Path(member.name).name not in WHISPER_FILES:
                    continue
                filename = Path(member.name).name
                source = archive.extractfile(member)
                if source is None:
                    continue
                with source, (stage_dir / filename).open("wb") as target:
                    shutil.copyfileobj(source, target)
                extracted.add(filename)
        if extracted != set(WHISPER_FILES):
            raise VoiceFailure("invalid_model_archive", "The speech model archive did not contain the expected files.")
        for filename in WHISPER_FILES:
            os.replace(stage_dir / filename, model_dir / filename)
    except httpx2.HTTPError as exc:
        raise VoiceFailure("download_failed", "Could not download the speech model. Check your connection and retry.") from exc
    finally:
        archive_path.unlink(missing_ok=True)
        shutil.rmtree(stage_dir, ignore_errors=True)


class WindowsSapiSpeaker:
    """Use local Windows SAPI voices without creating or saving audio files."""

    def __init__(self, worker_path: Path | None = None) -> None:
        self.worker_path = worker_path or Path(__file__).with_name("sapi_worker.ps1")
        self.process: subprocess.Popen[str] | None = None
        self._write_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._ready = threading.Event()
        self._events: list[dict[str, Any]] = []
        self._event_lock = threading.Lock()
        self._error: str | None = None

    @property
    def supported(self) -> bool:
        return sys.platform == "win32" and self.worker_path.is_file()

    def start(self) -> dict[str, Any]:
        if not self.supported:
            return {"available": False, "voices": [], "reason": "Local SAPI speech is available on Windows only."}
        if self.process is None or self.process.poll() is not None:
            powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("pwsh")
            if not powershell:
                return {"available": False, "voices": [], "reason": "PowerShell is unavailable; Windows local speech cannot start."}
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                self.process = subprocess.Popen(
                    [powershell, "-NoLogo", "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass", "-File", str(self.worker_path)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=flags,
                )
            except OSError:
                return {"available": False, "voices": [], "reason": "Could not start Windows local speech."}
            self._ready.clear()
            self._error = None
            self._reader = threading.Thread(target=self._read_events, name="aster-sapi-reader", daemon=True)
            self._reader.start()
            if not self._ready.wait(timeout=5) or self._error:
                self.stop_worker()
                return {"available": False, "voices": [], "reason": self._error or "Windows local speech did not start in time."}
        with self._event_lock:
            ready = next((event for event in self._events if event.get("event") == "ready"), {})
        return {"available": True, "voices": ready.get("voices", []), "engine": "Windows SAPI (local installed voices)"}

    def speak(self, text: str, *, voice: str = "", rate: int = 0, pitch: int = 0) -> None:
        if not text.strip():
            return
        status = self.start()
        if not status["available"]:
            raise VoiceFailure("tts_unavailable", str(status["reason"]))
        self._send({"type": "speak", "text": text[:4000], "voice": voice, "rate": max(-10, min(10, rate)), "pitch": max(-10, min(10, pitch))})

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            try:
                self._send({"type": "stop"})
            except (OSError, BrokenPipeError, VoiceFailure):
                self.stop_worker()

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            try:
                self._send({"type": "quit"})
                self.process.wait(timeout=2)
            except (OSError, BrokenPipeError, subprocess.TimeoutExpired, VoiceFailure):
                self.stop_worker()
        self.process = None

    def stop_worker(self) -> None:
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    def _send(self, payload: dict[str, Any]) -> None:
        with self._write_lock:
            process = self.process
            if process is None or process.poll() is not None or process.stdin is None:
                raise VoiceFailure("tts_unavailable", "Windows local speech is not running.")
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()

    def _read_events(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                with self._event_lock:
                    self._events.append(event)
                    if event.get("event") == "ready":
                        self._ready.set()
                    if event.get("event") == "error" and not self._ready.is_set():
                        self._error = str(event.get("message", "Speech startup failed."))
                        self._ready.set()


async def transcribe_async(transcriber: WhisperTranscriber, pcm: bytes) -> str:
    """Move CPU-bound inference off the event loop."""
    return await asyncio.to_thread(transcriber.transcribe_pcm, pcm)
