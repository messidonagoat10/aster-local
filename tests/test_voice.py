import struct

import pytest

from assistant_core.voice import (
    MAX_PCM_BYTES,
    WHISPER_FILES,
    VoiceFailure,
    WhisperTranscriber,
)


class FakeStream:
    def __init__(self):
        self.result = type("Result", (), {"text": "recognized speech"})()
        self.accepted = None

    def accept_waveform(self, sample_rate, waveform):
        self.accepted = (sample_rate, waveform)


class FakeRecognizer:
    def __init__(self):
        self.stream = FakeStream()

    def create_stream(self):
        return self.stream

    def decode_stream(self, stream):
        assert stream is self.stream


def _touch_model(model_dir):
    model_dir.mkdir()
    for filename in WHISPER_FILES:
        (model_dir / filename).write_bytes(b"test")


def test_whisper_pcm_is_normalized_and_decoded_only_in_memory(tmp_path):
    model_dir = tmp_path / "model"
    _touch_model(model_dir)
    recognizer = FakeRecognizer()
    transcriber = WhisperTranscriber(model_dir, recognizer_factory=lambda **_: recognizer)
    pcm = struct.pack("<4h", 0, 8192, -8192, 16384) * 1000

    assert transcriber.transcribe_pcm(pcm) == "recognized speech"
    rate, waveform = recognizer.stream.accepted
    assert rate == 16000
    assert waveform[:4] == [0.0, 0.25, -0.25, 0.5]
    assert list(tmp_path.glob("*.wav")) == []


def test_whisper_rejects_silence_and_audio_over_limit(tmp_path):
    model_dir = tmp_path / "model"
    _touch_model(model_dir)
    transcriber = WhisperTranscriber(model_dir, recognizer_factory=lambda **_: FakeRecognizer())

    with pytest.raises(VoiceFailure, match="could not hear speech"):
        transcriber.transcribe_pcm(b"\x00\x00" * 4000)
    with pytest.raises(VoiceFailure, match="limited to 30 seconds"):
        transcriber.transcribe_pcm(b"\x01\x00" * (MAX_PCM_BYTES // 2 + 1))


def test_whisper_reports_missing_local_model(tmp_path):
    transcriber = WhisperTranscriber(tmp_path / "absent")
    with pytest.raises(VoiceFailure) as error:
        transcriber.transcribe_pcm(b"\x00\x10" * 4000)
    assert error.value.code == "stt_model_missing"
