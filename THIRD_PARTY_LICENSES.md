# Third-party components and licenses

All pinned Python dependencies, including optional voice and test dependencies, are recorded with artifact hashes in [`uv.lock`](uv.lock). The table below inventories every locked package in this source release, including the conditional Emscripten transport. Packages and models are not vendored except for the app's own source and static UI.

## Python packages

| Component | Version | License | Use |
| --- | ---: | --- | --- |
| annotated-doc | 0.0.6 | MIT | FastAPI annotations |
| annotated-types | 0.8.0 | MIT | Pydantic constraints |
| anyio | 4.16.0 | MIT | Async runtime |
| aster-local | 0.1.1 | MIT | This project; see `LICENSE` |
| click | 8.5.1 | BSD-3-Clause | Uvicorn command-line support |
| colorama | 0.4.6 | BSD-3-Clause | pytest terminal support on Windows |
| FastAPI | 0.162.7 | MIT | Local HTTP and WebSocket API |
| h11 | 0.16.0 | MIT | HTTP/1.1 implementation |
| httpcore2 | 2.16.0 | BSD-3-Clause | HTTPX2 transport |
| HTTPX2 | 2.16.0 | BSD-3-Clause | Loopback Ollama calls, explicit search, and test client |
| httpx2-jsfetch | 1.0 | BSD-3-Clause | Conditional HTTPX2 transport for Emscripten; not installed on desktop platforms |
| idna | 3.20 | BSD-3-Clause | Hostname handling |
| iniconfig | 2.3.1 | MIT | pytest configuration |
| opentelemetry-api | 1.45.2 | Apache-2.0 | FastAPI dependency; Aster configures no SDK, exporter, instrumentation, or telemetry |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | pytest version handling |
| pluggy | 1.7.0 | MIT | pytest plugin system |
| Pydantic | 2.14.3 | MIT | Request and settings validation |
| pydantic-core | 2.50.4 | MIT | Pydantic validation runtime |
| Pygments | 2.21.0 | BSD-2-Clause | pytest terminal formatting |
| pytest | 9.2.0 | MIT | Optional test dependency (`dev` extra) |
| sherpa-onnx | 2.0.1 | Apache-2.0 | Optional local speech recognition (`voice` extra) |
| sherpa-onnx-core | 2.0.1 | Apache-2.0 | sherpa-onnx runtime component |
| Starlette | 1.10.0 | BSD-3-Clause | ASGI framework layer |
| truststore | 0.10.5 | MIT | HTTPX2 TLS trust integration; Aster's default model calls use loopback HTTP |
| typing-extensions | 4.16.0 | PSF-2.0 | Python typing compatibility |
| typing-inspection | 0.4.5 | MIT | Pydantic type inspection |
| Uvicorn | 0.54.0 | BSD-3-Clause | Local ASGI server |
| websockets | 17.4 | BSD-3-Clause | Uvicorn WebSocket transport for streaming chat |

There are no known non-commercial or share-alike package restrictions in the locked Python dependencies. The package lock hashes the resolved distribution artifacts. A user-installed `uv` is a setup tool, not an Aster runtime dependency; uv is MIT OR Apache-2.0.

## Local models and runtimes

| Component | Version/tag | License | Notes |
| --- | --- | --- | --- |
| Qwen3 instruct models | Ollama tags such as `qwen3:1.7b`, `qwen3:4b`, `qwen3:8b`, `qwen3:14b`, `qwen3:30b`, and `qwen3:32b` | Apache-2.0 | User downloads with Ollama; no weights are bundled. The project source identifies Qwen3 weights as Apache-2.0. Model tags and blob digests are managed by Ollama; Aster does not currently pin a trusted Qwen3 blob hash. |
| Nomic Embed Text v1.5 | `nomic-embed-text:v1.5` | Apache-2.0 | Optional user download for semantic memory; inference uses Ollama's loopback `/api/embed` API. |
| Whisper tiny.en (converted ONNX) | sherpa-onnx `asr-models` release archive | OpenAI Whisper weights: MIT; sherpa-onnx conversion/runtime: Apache-2.0 | Downloaded only on request. Expected archive length is 118,071,777 bytes; SHA-256 is `2bd6cf965c8bb3e068eff9fa2191387ee63a9dfa2a4e37582a8109641c20005dd`. The downloader verifies both before extracting the expected encoder, decoder, and token files. |
| Ollama runtime | User-installed; not pinned by this repository | MIT | Installs and runs local model artifacts separately. Aster talks to its loopback API; review Ollama's own installer, runtime, and update behavior independently. |
| Windows SAPI voices | Installed with Windows or by the user | Windows component / voice-specific terms | Aster does not redistribute a voice. Output is local and requires an installed Windows speech voice. |
| Windows DPAPI | Operating-system component | Windows component | Optional database-at-rest protection tied to the current Windows account; no crypto package is added. |

Qwen3 model and license references: [Qwen3 project](https://github.com/QwenLM/Qwen3) and the [Ollama Qwen3 library](https://ollama.com/library/qwen3). Ollama's official registry exposes the [Nomic model card and Apache-2.0 license blob](https://ollama.com/library/nomic-embed-text). Ollama documents the local [embeddings endpoint](https://docs.ollama.com/capabilities/embeddings). OpenAI states the Whisper code and model weights are [MIT licensed](https://github.com/openai/whisper); sherpa-onnx documents the converted [Whisper tiny.en model](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/whisper/tiny.en.html).

## Deliberately excluded components

- openWakeWord pretrained model assets were not included because the reviewed assets carried a CC BY-NC-SA license that does not satisfy the project's permissive-commercial-use requirement. Aster uses push-to-talk instead.
- No Piper or Kokoro voice weights are bundled. Aster uses installed Windows voices, avoiding unverified voice model redistribution.
- No cloud speech, embedding, or chat API is used.
- The browser UI has no CDN JavaScript, fonts, analytics, or remote image assets.
