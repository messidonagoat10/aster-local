# Audit me: Aster's network behavior

The app has no telemetry, analytics, account service, cloud model, API key, or automatic update check. With no model-download button pressed and web search disabled, Aster makes **no application-initiated request to the public internet**. The browser and model runtime still run as separate software and have their own update/network policies.

## Destinations and triggers

| Host or destination | Request and payload | Trigger | Can it be disabled? |
| --- | --- | --- | --- |
| `127.0.0.1:<ASTER_PORT>` | The browser loads the bundled UI, authenticates with a random local token, sends chat text and up to 30 seconds of microphone PCM, and reads local settings/history | Aster is open; audio only during push-to-talk | It is the app itself; listener is always loopback-only |
| `127.0.0.1:11434` or the configured loopback Ollama origin | `/api/tags`, `/api/chat`, and optionally `/api/embed`; chat prompts and embedding text remain on this computer | Local health checks/chat; `/api/embed` only when semantic memory is enabled | Health/chat are core; semantic memory is optional |
| Ollama registry/blob hosts | Model manifest and model blob requests by Ollama's own CLI | User downloads a model in Setup or runs `install.ps1` | Yes; do not start a download |
| `github.com/k2-fsa/sherpa-onnx` and its release asset host | The pinned Whisper tiny.en archive only; no user prompt or audio is sent | User clicks **Download speech model** | Yes; speech mode remains unavailable until local model exists |
| `html.duckduckgo.com` | The exact search query in the URL; search results are returned to the local app | Web search is opted in, requested by the model, and the user approves the displayed query | Yes; off by default and each request is confirmed |
| Python package index configured by `uv` | Pinned package archives | User runs `install.ps1` or a development install command | Yes; dependencies are already installed |

## Local code inspection

1. Bind address: [`assistant_core/__main__.py`](assistant_core/__main__.py).
2. Loopback URL validation and cloud-tag rejection: [`assistant_core/config.py`](assistant_core/config.py).
3. HTTP destinations and proxy/redirect policy: [`assistant_core/ollama.py`](assistant_core/ollama.py), [`assistant_core/voice.py`](assistant_core/voice.py), and [`assistant_core/skills.py`](assistant_core/skills.py).
4. Explicit model downloads: `/api/setup/model`, `/api/setup/embedding-model`, and `/api/setup/voice-model` in [`assistant_core/app.py`](assistant_core/app.py).
5. Optional search registration and dangerous confirmation: `create_builtin_registry` and `_web_search` in [`assistant_core/skills.py`](assistant_core/skills.py).
6. Exact package versions and artifact hashes: [`uv.lock`](uv.lock). Third-party licenses: [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).

The Ollama and Python installers are independently maintained. Aster does not control whether those upstream programs perform their own update checks. On this host, the user can also enforce offline operation at the OS firewall after all desired models are present; local loopback inference still needs to remain available.
