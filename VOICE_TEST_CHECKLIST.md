# Manual voice test checklist

Automated tests cover PCM bounds, silence/no-speech handling, the local transcriber adapter, route authorization, and speaker control stubs. Complete these checks on a Windows PC with a microphone and an installed Windows speech voice. Do not use sensitive content in test prompts.

## Before testing

- [ ] Settings → Diagnostics shows the speech dependency and downloaded Whisper model as ready.
- [ ] Windows has a microphone selected as its input device and a local SAPI voice installed.
- [ ] Aster is open at its exact `127.0.0.1` origin. No other application is recording.
- [ ] Browser microphone permission has not been disabled for the local origin.

## Recognition and VAD

- [ ] Run **Settings → Test your microphone**. Confirm it only reports local input, never submits the transcript to chat, and does not create a recording file.
- [ ] If the speech model is not installed, confirm the mic test still detects input and directs the user to download the model for transcription checks.
- [ ] Start push-to-talk; confirm the microphone button, orb, and status visibly show listening.
- [ ] Speak a short clear sentence, then pause; confirm silence detection ends capture and produces a transcript.
- [ ] Stop a turn manually with the mic button and with Ctrl+Space.
- [ ] Record only room silence; confirm a clear no-speech message and no model request.
- [ ] Speak in a noisy room; confirm Aster handles an empty/poor transcription gracefully rather than sending it as a chat.
- [ ] Hold the mic for the 30-second limit; confirm the capture stops and no longer audio is accepted.
- [ ] Deny browser microphone permission; confirm text entry still works and the UI explains the issue.
- [ ] Inspect `%LOCALAPPDATA%\Aster`; confirm no raw audio recording or temporary WAV file is created by Aster.

## Spoken output and interrupt

- [ ] Run **Settings → Test speaker** and confirm the fixed test phrase plays using the currently selected local voice, speed, and pitch.
- [ ] Enable the speaker; request a short answer and confirm audio comes from the selected installed local voice.
- [ ] Change voice, speed, and pitch; save and check the new setting is used.
- [ ] Begin a longer spoken answer, press PTT while it is speaking, and confirm current speech is stopped before capture.
- [ ] Turn the speaker off; verify the same request produces text only.
- [ ] Remove or disable local SAPI voices; confirm diagnostics reports speech output unavailable and text remains usable.

## Offline behavior

- [ ] After downloading models, disable external internet access while leaving Ollama on loopback; verify text chat and Whisper recognition still work.
- [ ] With internet disabled, verify the model status remains local and web search cannot run unless explicitly opted in and confirmed.

## Results

Record OS build, Python version, CPU/ GPU, model tags, microphone, local voice, observed transcription time, and any failures. Avoid including transcript text or private data in the report.
