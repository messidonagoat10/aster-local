# Contributing to Aster Local

Thanks for helping make Aster easier to use and audit.

## Development setup

1. Install Python 3.11+, `uv`, and Ollama.
2. Run `uv sync --locked --extra voice --extra dev`.
3. Run `uv run --locked --extra dev pytest` before sending a change.
4. For interactive chat, pull a Qwen3 model and run `uv run --locked python -m assistant_core`.

Tests should be deterministic, use fake Ollama responses and temporary databases, and avoid network or model downloads. Hardware-only voice changes need a manual test checklist entry.

## Design requirements

- Keep chat, speech recognition, speech synthesis, and embeddings local by default. Any outbound request must require explicit user action, be narrowly scoped, and be listed in `SECURITY.md`.
- No telemetry, ads, automatic updates, hidden online calls, user tracking, API key requirements, or account gates.
- Every tool needs an input schema, declared permission tier, concise confirmation preview when needed, and tests for invalid inputs and denied calls.
- Never add a raw shell tool. Restrict file access to approved folders and test symlink/path traversal boundaries.
- Treat model output, files, clipboard, memory, search, and tool results as untrusted data. Keep prompt-injection tests and avoid rendering model text as HTML.
- Verify the license and provenance for all new Python packages, model weights, voice assets, and installer components. Update `uv.lock`, `THIRD_PARTY_LICENSES.md`, and the network audit with any changes.
- Keep downloaded model integrity pinned and checked before extraction. If an upstream model cannot be checksum-pinned, state the limitation.
- Keep the UI usable in text-only mode even if microphone, recognition, speech output, or a model is unavailable.
- Use original names and assets. Do not use copyrighted film material or imitate a real person's voice.

## Reports

For issues, include OS, Python, Ollama and model versions, relevant diagnostics, and small reproduction steps. Redact home paths and do not attach conversations, exported data, or audio unless you intend to share them.
