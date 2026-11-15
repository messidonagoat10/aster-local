# Aster Local quickstart (Windows)

## Before you start

Install these once from the publishers' official sites:

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- [Ollama for Windows](https://ollama.com/download)

Keep this page, the downloaded model, and later chats on the same computer. The Qwen3 model pull needs internet and several gigabytes of disk space; normal chat works offline after the model is present.

## Start Aster

1. Extract the Aster folder somewhere under your Windows user profile.
2. Open that folder in File Explorer, choose **Open in Terminal**, and run:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\install.ps1
   ```

3. Wait for package and model downloads. The script opens <http://127.0.0.1:8765> in your browser.
4. In **Setup & settings**, review the recommended model, choose text/voice/both, and opt into any additional model downloads you want.

On later use, double-click **Aster.cmd** in the extracted project folder. You can also run `.\start-aster.ps1` in PowerShell. Close Aster with `.\stop-aster.ps1`.

Do not open `web/index.html` directly. It is a template that needs the local Aster server; opening it as a file disables its styling, branding, and app connection.

## First voice turn

1. Select **Voice (push-to-talk + spoken answers)** or **Both** in settings and save.
2. Use **Test your microphone** to confirm input. With the speech model installed, Aster shows a local transcript without sending it to chat. Without the model, this check still detects microphone input.
3. The first time, choose **Download speech model**. It is roughly 118 MB and is SHA-256 checked before extraction.
4. Choose an installed voice and click **Test speaker**. This plays a fixed phrase using the selected voice, speed, and pitch.
5. Click the microphone or press **Ctrl+Space**. Allow microphone access in your browser when asked, then speak. Silence ends the turn; click/press again to finish sooner.
6. Turn on the speaker button to hear answers. Speech uses an installed local Windows voice; no voice model or audio recording is uploaded.

If Windows has no installed SAPI voice, speech recognition and text chat can still work. Settings → Diagnostics explains what Aster could detect.

## Memory, documents, and tools

- **Memories**: add, edit, export, or delete saved notes. Optional semantic recall requires downloading `nomic-embed-text:v1.5`; keyword recall works without it.
- **Choose a folder…**: approve only the document folders Aster should search. Search currently reads `.txt`, `.md`, `.csv`, `.json`, and `.log` files. Results are untrusted reference text.
- **Agenda**: review notes, to-dos, and reminders. Timer alerts appear only while the Aster page is open.
- Aster automatically reads safe local information. It shows a specific confirmation before opening/modifying apps or deleting files. Optional web search is off by default; after opting in, every query still needs confirmation.
- You can enable Windows DPAPI database encryption in Settings. It protects the local database for the current Windows account, not exported JSON, old backups, or data while the account is signed in.

## Common fixes

| Symptom | Fix |
| --- | --- |
| `Ollama is not running` | Start the Ollama app from the Start menu, then refresh Aster. |
| Model is missing | Settings → **Download selected model**, or in PowerShell run `ollama pull qwen3:4b`. |
| Model is slow or memory is low | Choose Qwen3 1.7B or 4B. Larger models need more RAM/VRAM and are not always faster or more capable on a small machine. |
| Microphone unavailable | Use a browser with microphone support, check Windows input device and browser site permission, then refresh. The mic is active only during push-to-talk. |
| Speech model missing | Click **Download speech model**; the downloaded archive is size- and hash-verified. |
| No spoken response | Check the speaker toggle and Settings → Diagnostics for an installed Windows local voice. |
| Aster does not open | Keep the project folder extracted; rerun `.\start-aster.ps1`. If port 8765 is occupied, stop the other process or set `ASTER_PORT` to a free port before starting. |

## Stop and remove local data

Run `.\stop-aster.ps1`. Use **Forget everything** in settings to delete conversations, notes, agenda items, settings, and approved folders. For a complete removal, close Aster and delete `%LOCALAPPDATA%\Aster`. Enabling encryption before you save sensitive conversations is preferable to converting an existing database, because conversion cannot clean old filesystem snapshots or backups.

For the complete network audit and threat model, see [SECURITY.md](SECURITY.md).
