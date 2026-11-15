# Security, privacy, and network audit

## Security posture

Aster is designed so its normal chat path stays on one computer. It has no accounts, API keys, telemetry, analytics, ads, cloud inference, or automatic update calls. The app binds to `127.0.0.1` only. Its UI receives a random process-scoped token; API routes require that token, same-origin requests are checked, host headers are restricted, and the WebSocket checks both loopback and the expected origin. The Ollama client accepts a loopback HTTP origin only, disables environment proxy settings, and does not follow redirects.

These controls reduce accidental exposure. They are **not** an OS sandbox: another malicious process running as the signed-in user can generally inspect or control Aster. Do not expose the port through port forwarding, a tunnel, or a reverse proxy.

## Network calls

The application initiates the following connections. Dependencies may have their own behavior; this list describes Aster's code and explicit setup actions.

| Destination | Data sent | Trigger |
| --- | --- | --- |
| `127.0.0.1:<ASTER_PORT>` | Local page, chat, settings, and bounded microphone PCM | The user's browser opens Aster; a microphone request occurs only during push-to-talk |
| `127.0.0.1:11434` or the validated loopback `ASTER_OLLAMA_URL` | Chat prompt, chosen local model tag, semantic-memory query/note text when enabled | Local health checks and chat; embeddings only after the user enables semantic memory |
| Ollama model registry and blob hosts | Model download requested by the Ollama CLI | Only after the user presses a model-download button or runs `install.ps1` |
| `github.com/k2-fsa/sherpa-onnx` release asset | No user content; downloads a pinned 118 MB speech-model archive | Only after the user clicks the speech-model download button; archive size and SHA-256 are verified before extraction |
| `html.duckduckgo.com` | Search query text | Only when web search has been enabled in settings, Aster requests a search, and the user confirms the exact query |
| Python package index | Pinned dependency files requested by `uv` | Only when the user runs the installer or development setup |

There is no hidden weather service. The daily briefing uses local time and Aster's local agenda. The Ollama application is separate software and may have its own update behavior; Aster communicates with its loopback API and does not manage that runtime's settings.

## Data and encryption

- By default, conversations, memories, agenda records, settings, and approved folder paths live in SQLite under `%LOCALAPPDATA%\Aster` (or `ASTER_DATA_DIR`). Local filesystem permissions still matter.
- On Windows, the user can turn on **Encrypt local database with Windows account**. Aster snapshots SQLite into memory and protects the whole database with Windows DPAPI for the current account. The encrypted file is `aster.sqlite3.enc`; Aster does not write a decrypted database or WAL beside it. The key is managed by Windows, so this is not portable between Windows accounts or machines.
- The Windows option is not available on macOS/Linux. On those systems use full-disk encryption and OS account controls.
- Encryption protects a stopped database copied from disk. It does not protect data while Aster is running, exports downloaded as plain JSON, old backups, OS snapshots, prior unencrypted copies, SSD wear-leveling remnants, or a computer compromised under the same account. Converting an old plaintext database unlinks its previous SQLite files but cannot forensically overwrite those storage locations.
- “Forget everything” deletes all app rows, including conversation history, memories and embeddings, agenda items, settings, and approved folders. It is not a secure overwrite guarantee.
- Microphone PCM is capped at 30 seconds, processed in memory, and not saved by Aster. The browser is not continuously listening: the current build has push-to-talk only.
- Local documents are read only from folders explicitly approved by the user. Search currently reads only `.txt`, `.md`, `.csv`, `.json`, and `.log` files up to 2 MB each, visits at most 5,000 paths, and returns bounded snippets. It is lexical retrieval, not a full document parser or a file-system sandbox.
- JSON export intentionally returns readable plaintext for the user to download.

## Permission model and prompt injection

Every tool has a validated schema and a declared permission tier:

- **Safe:** local calculator, time, system status, approved-folder search, clipboard read, agenda read, and memory search.
- **Confirm:** application launch/open, note/task/reminder creation, brightness changes, and other reversible state changes. The browser displays a human-readable action preview before execution.
- **Dangerous:** file deletion, closing an Aster-opened process, locking the screen, and optional web search. Aster asks immediately before each call. No shell execution tool is registered.

The model cannot bypass these checks using a fabricated function name or invalid arguments. Small-model JSON fallback rejects duplicate keys and accepts only strict structured forms. The runtime limits tool rounds and action count. Text from files, clipboard, memory, search, and tool outputs is explicitly marked as untrusted reference material in the prompt. This reduces prompt-injection risk but cannot make a language model perfectly resistant; the model might still be manipulated into giving a misleading answer or proposing an inappropriate action. The user sees and decides every confirmation-gated action.

File access resolves paths against approved roots and rejects symlinks and escapes. File deletion is limited to one regular file and always requires confirmation. The app allowlist is intentionally small. Closing apps only sends a normal close request to process handles Aster started; it does not force-kill arbitrary processes.

## Threat model: what Aster can and cannot protect

**Aster is intended to protect against:** accidental LAN exposure, a model calling undeclared tools, paths outside user-approved roots, silent destructive tool actions, accidental external search, and accidental audio-file retention.

**Aster cannot protect against:** malware or a malicious browser extension under the current OS account; a compromised Python/Ollama install; a malicious local model; incorrect or fabricated model responses; a user approving a harmful action; content injection that affects model reasoning; network behavior of software outside Aster; shoulder-surfing; OS account compromise; forensic recovery from backups, snapshots, or SSD remapping; or denial of service from a large/slow local model.

## Audit checklist

To audit locally:

1. Check `assistant_core/__main__.py` for `host="127.0.0.1"`.
2. Check URL validation in `assistant_core/config.py` and `trust_env=False`, `follow_redirects=False` in `assistant_core/ollama.py`.
3. Search `assistant_core/` for `http://`, `https://`, `fetch(`, and HTTP clients. The outbound destinations in production code are local Ollama, the pinned Whisper download, and the opt-in DuckDuckGo function.
4. Confirm web search is not registered unless its setting is `true`, and that the skill still has dangerous permission.
5. Review every `add(...)` call and permission preview in `assistant_core/skills.py`.
6. Review `uv.lock` hashes and [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
7. Confirm the speech archive checksum in `assistant_core/voice.py`; Aster has not pinned a trusted Qwen3 Ollama blob digest.

## Reporting a vulnerability

Please do not include private conversations, database files, or real personal data in an issue. Describe the affected version, operating system, reproduction steps, and the minimum relevant redacted log. For a security issue, use a private reporting channel provided by the repository host if available.
