# Roadmap and phase report

This tracks the implementation in this repository. “Done” means the feature has code and automated coverage; hardware-specific behavior is also called out where it could not be exercised on the development host.

## Phase 1 — text core: implemented

- [x] Ollama loopback streaming with model availability and error handling
- [x] Multi-turn SQLite history
- [x] User-managed notes with keyword search and optional Ollama semantic embeddings
- [x] Export, selective deletion, and delete-all
- [x] Local session token, localhost binding, origin/Host checks
- [x] Model-size recommendation from system memory and NVIDIA VRAM detection
- [x] Tests for storage, conversation flow, model parsing, and request security

## Phase 2 — voice: implemented with a deliberate push-to-talk scope

- [x] Local Whisper tiny.en recognition, manually run against a real local audio fixture
- [x] Browser microphone capture with visible listening state, bounded 30-second turns, local silence detection, and no recording files
- [x] Setup microphone input check and fixed-phrase speaker test using selected local voice controls
- [x] Local Windows SAPI output with voice, rate, pitch controls, sentence-wise streaming, and stop on PTT
- [x] Friendly errors for missing model, silence, empty transcription, no device permission, and unavailable speaker
- [x] Manual checklist: [VOICE_TEST_CHECKLIST.md](VOICE_TEST_CHECKLIST.md)
- [ ] Wake word: omitted because reviewed downloadable weights were not permissively licensed for the project's intended use
- [ ] Actual speaker playback on the current host: no usable installed SAPI voice was detected
- [ ] macOS/Linux speech adapters and always-on listening

## Phase 3 — permissioned skills: implemented for a reviewed Windows-first set

- [x] Skill registry, schemas, safe/confirm/dangerous tiers, action previews, and per-call confirmation
- [x] Strict Ollama function calls and validated JSON fallback with duplicate-key rejection
- [x] Calculator, unit conversion, local time, system/battery status, clipboard, approved-folder search and text excerpts
- [x] App open/close, file/folder open, single-file delete, notes, tasks, reminders, agenda, media keys, brightness, screen lock
- [x] Web search is omitted unless explicitly enabled; each request is shown and confirmed
- [ ] Full desktop-app coverage and other OS adapters
- [ ] Calendar/weather integrations

## Phase 4 — HUD and settings: implemented as a local web interface

- [x] Responsive original dark HUD, animated state orb, transcript, text composer, PTT, speaker, and keyboard shortcut
- [x] Model, persona, voice, mode, optional web search, embeddings, approved folder, encryption, and diagnostics controls
- [x] Agenda, memory edit/delete, export, and forget-everything views
- [ ] Native desktop wrapper and signed application package
- [ ] Accessibility audit with screen readers and a broader device-size review

## Phase 5 — setup and distribution: source installer implemented; release packaging remains

- [x] Windows PowerShell setup/start/stop scripts
- [x] Local hardware diagnostics and model-tier recommendation
- [x] User-triggered model download progress; Whisper archive size and SHA-256 validation
- [x] Troubleshooting quickstart
- [ ] Signed one-click installer and native app shell
- [ ] Checksum-pinned Qwen3/Ollama model manifests and provenance workflow
- [ ] Packaging and install verification on clean Windows 10/11 x64 and ARM64 machines
- [ ] macOS/Linux install and adapter support

## Phase 6 — security review, tests, and docs: implemented with limitations listed here

- [x] Local network and permission audit in [SECURITY.md](SECURITY.md)
- [x] Windows DPAPI database encryption toggle; exported JSON and previous backup copies are not encrypted by it
- [x] Permissive dependency/model inventory in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)
- [x] Automated tests for tool permissions, prompt-injection handling, memory, encryption round-trip, settings, and streaming
- [x] Documentation, real UI screenshot, and manual voice checklist
- [ ] External security review, signed releases, and repeatable cross-platform CI

## Longer-term ideas

Multi-language recognition, a commercially permissive wake-word model, native desktop packaging, mobile companion, selected openly licensed TTS voices, smart-home adapters, and local calendar integration. These remain proposals and are not built into this source release.
