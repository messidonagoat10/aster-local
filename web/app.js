"use strict";

const state = { token: "", socket: null, conversationId: localStorage.getItem("aster.conversation") || crypto.randomUUID(), busy: false, currentReply: null, speakerEnabled: localStorage.getItem("aster.speaker") === "true", recording: false, recordingPurpose: "chat", testAudioDetected: false, speechModelInstalled: false, audioContext: null, mediaStream: null, pcmChunks: [], finishingRecording: false, speechTimer: null, modelReady: false, encryptionEnabled: false };
const transcript = document.querySelector("#transcript");
const intro = document.querySelector("#intro");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const connectionDot = document.querySelector("#connection-dot");
const connectionLabel = document.querySelector("#connection-label");
const modelStatus = document.querySelector("#model-status");
const memoryPanel = document.querySelector("#memory-panel");
const micButton = document.querySelector("#mic-button");
const speakerToggle = document.querySelector("#speaker-toggle");
const microphoneStatus = document.querySelector("#microphone-status");
const voiceModelButton = document.querySelector("#install-voice-model");
let toastTimer;

function toast(message) {
  const element = document.querySelector("#toast");
  element.textContent = message;
  element.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("show"), 2600);
}

function setConnection(kind, label) {
  connectionDot.className = `dot ${kind}`;
  connectionLabel.textContent = label;
}

function addMessage(role, text = "") {
  intro.hidden = true;
  const row = document.createElement("article");
  row.className = `message ${role}`;
  const icon = document.createElement("span");
  icon.className = "message-icon";
  icon.textContent = role === "user" ? "Y" : "A";
  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;
  row.append(icon, body);
  transcript.append(row);
  transcript.scrollTop = transcript.scrollHeight;
  return body;
}

function setBusy(busy) {
  state.busy = busy;
  sendButton.disabled = busy;
  input.disabled = busy;
  document.querySelector("#new-chat").disabled = busy;
  document.querySelector("#forget-all").disabled = busy;
}

function setRecording(recording) {
  state.recording = recording;
  micButton.classList.toggle("active", recording);
  micButton.setAttribute("aria-label", recording ? "Stop push-to-talk" : "Start push-to-talk");
  micButton.title = recording ? "Listening · audio is not saved" : "Push to talk";
  microphoneStatus.textContent = recording ? "Listening · audio stays in memory and is not saved" : "Enter to send · Shift + Enter for a new line";
  document.body.classList.toggle("listening", recording);
}

function setSpeaker(enabled) {
  state.speakerEnabled = enabled;
  localStorage.setItem("aster.speaker", String(enabled));
  speakerToggle.classList.toggle("active", enabled);
  speakerToggle.setAttribute("aria-pressed", String(enabled));
  speakerToggle.setAttribute("aria-label", enabled ? "Turn spoken answers off" : "Turn spoken answers on");
  speakerToggle.title = enabled ? "Spoken answers on" : "Spoken answers off";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Authorization": `Bearer ${state.token}`, "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Local request failed (${response.status}).`);
  }
  return response.status === 204 ? null : response.json();
}

async function loadHistory() {
  const messages = await api(`/api/conversations/${encodeURIComponent(state.conversationId)}/messages`);
  for (const message of messages) addMessage(message.role, message.content);
}

function connect() {
  return new Promise((resolve, reject) => {
    let authenticated = false;
    const url = new URL("/ws", location.href);
    url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(url);
    state.socket = socket;
    socket.addEventListener("open", () => socket.send(JSON.stringify({ type: "auth", token: state.token })), { once: true });
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "ready") {
        authenticated = true;
        setConnection("ready", "Local connection ready");
        resolve();
      } else if (message.type === "delta" && state.currentReply) {
        state.currentReply.textContent += message.text;
        transcript.scrollTop = transcript.scrollHeight;
      } else if (message.type === "delta") {
        state.currentReply = addMessage("assistant", message.text);
      } else if (message.type === "done") {
        state.currentReply = null;
        setBusy(false);
        input.focus();
        if (message.spoken) {
          document.body.classList.add("speaking");
          const words = transcript.lastElementChild?.querySelector(".message-body")?.textContent?.trim().split(/\s+/).length || 1;
          state.speechTimer = setTimeout(stopSpeechTimer, Math.max(2500, Math.min(60000, words * 420)));
        }
      } else if (message.type === "speech") {
        document.body.classList.add("speaking");
      } else if (message.type === "audio_error") {
        toast(message.message || "Local spoken output is unavailable.");
      } else if (message.type === "confirmation_required") {
        const tier = message.permission === "dangerous" ? "Dangerous action" : "Confirm this change";
        const confirmed = window.confirm(`${tier}\n\n${message.action}\n\nAster will do this only if you approve.`);
        socket.send(JSON.stringify({ type: "confirmation_response", id: message.id, confirmed }));
      } else if (message.type === "tool_result") {
        if (!message.ok) toast("A requested action could not be completed; I did not claim it succeeded.");
        else if (["note_create", "task_create", "timer_start", "task_complete"].includes(message.name)) refreshAgenda().catch(() => {});
      } else if (message.type === "error") {
        state.currentReply = null;
        setBusy(false);
        addMessage("error", message.message || "Something went wrong.");
      }
    });
    socket.addEventListener("close", () => {
      if (!authenticated) reject(new Error("The local session could not be authenticated. Reload the page."));
      if (state.busy) {
        state.currentReply = null;
        setBusy(false);
        addMessage("error", "The local connection closed. Reload the page to reconnect.");
      }
      setConnection("bad", "Disconnected");
    });
    socket.addEventListener("error", () => {
      setConnection("bad", "Connection error");
      reject(new Error("Could not connect to the local assistant."));
    }, { once: true });
  });
}

async function sendMessage(text, speak = state.speakerEnabled) {
  if (state.busy || !state.socket || state.socket.readyState !== WebSocket.OPEN) {
    toast("The local assistant is not connected yet.");
    return;
  }
  addMessage("user", text);
  setBusy(true);
  state.socket.send(JSON.stringify({ type: "chat", conversation_id: state.conversationId, text, speak }));
}

function stopSpeechTimer() {
  clearTimeout(state.speechTimer);
  state.speechTimer = null;
  document.body.classList.remove("speaking");
}

async function finishRecording() {
  if (!state.recording || state.finishingRecording) return;
  clearTimeout(state.recordingTimer);
  state.finishingRecording = true;
  const purpose = state.recordingPurpose;
  const chunks = state.pcmChunks;
  state.pcmChunks = [];
  setRecording(false);
  microphoneStatus.textContent = "Transcribing locally…";
  try {
    if (!chunks.length) throw new Error("No microphone audio was captured. Check microphone permissions and try again.");
    if (purpose === "test" && !state.speechModelInstalled) {
      const result = state.testAudioDetected
        ? "Microphone captured audio locally. Download the speech model to check transcription."
        : "No sound was detected. Check the selected microphone and try again.";
      document.querySelector("#microphone-test-result").textContent = result;
      microphoneStatus.textContent = "Microphone test complete · audio was not saved or sent";
      return;
    }
    const byteLength = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
    const pcm = new Uint8Array(byteLength);
    let offset = 0;
    for (const chunk of chunks) { pcm.set(new Uint8Array(chunk), offset); offset += chunk.byteLength; }
    const response = await fetch("/api/transcribe", {
      method: "POST",
      headers: { "Authorization": `Bearer ${state.token}`, "Content-Type": "application/octet-stream" },
      body: pcm,
      cache: "no-store",
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || "Local speech recognition failed.");
    if (purpose === "test") {
      const testResult = document.querySelector("#microphone-test-result");
      testResult.textContent = result.text.trim()
        ? `Heard locally: “${result.text.trim()}”`
        : "No speech detected. Check the selected microphone and try again.";
      microphoneStatus.textContent = "Microphone test complete · audio was not saved or sent";
    } else if (result.text.trim()) {
      await sendMessage(result.text);
    } else {
      microphoneStatus.textContent = "No speech detected · try again or type a message";
      toast("No speech was recognized. Check your microphone and try again.");
    }
  } catch (error) {
    microphoneStatus.textContent = "Enter to send · Shift + Enter for a new line";
    if (purpose === "test") document.querySelector("#microphone-test-result").textContent = error.message;
    toast(error.message);
  } finally {
    if (purpose === "test") document.querySelector("#test-microphone").textContent = "Test microphone";
    if (state.audioContext) await state.audioContext.close().catch(() => {});
    state.audioContext = null;
    if (state.mediaStream) state.mediaStream.getTracks().forEach((track) => track.stop());
    state.mediaStream = null;
    state.finishingRecording = false;
    state.recordingPurpose = "chat";
  }
}

async function startRecording(purpose = "chat") {
  try {
    state.recordingPurpose = purpose;
    await api("/api/speech/stop", { method: "POST", body: "{}" });
    stopSpeechTimer();
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) {
      throw new Error("This browser does not support local push-to-talk. Open Aster in an up-to-date browser.");
    }
    state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    state.audioContext = new AudioContext({ sampleRate: 16000 });
    await state.audioContext.audioWorklet.addModule("/assets/audio-capture.js");
    const source = state.audioContext.createMediaStreamSource(state.mediaStream);
    const processor = new AudioWorkletNode(state.audioContext, "aster-pcm-capture", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1], channelCount: 1 });
    state.pcmChunks = [];
    state.testAudioDetected = false;
    processor.port.onmessage = (event) => {
      if (event.data.type === "pcm" && state.recording) {
        state.pcmChunks.push(event.data.buffer);
        if (state.recordingPurpose === "test") {
          const samples = new Int16Array(event.data.buffer);
          for (const sample of samples) {
            if (Math.abs(sample) >= 180) {
              state.testAudioDetected = true;
              document.querySelector("#microphone-test-result").textContent = "Microphone is picking up sound… pause to finish the check.";
              break;
            }
          }
        }
      }
      if (event.data.type === "silence-end") finishRecording();
    };
    source.connect(processor);
    processor.connect(state.audioContext.destination);
    setRecording(true);
    state.recordingTimer = setTimeout(finishRecording, 30000);
  } catch (error) {
    if (state.mediaStream) state.mediaStream.getTracks().forEach((track) => track.stop());
    if (state.audioContext) await state.audioContext.close().catch(() => {});
    state.mediaStream = null;
    state.audioContext = null;
    state.recordingPurpose = "chat";
    if (purpose === "test") document.querySelector("#test-microphone").textContent = "Test microphone";
    microphoneStatus.textContent = "Enter to send · Shift + Enter for a new line";
    if (purpose === "test") document.querySelector("#microphone-test-result").textContent = error.message || "Microphone permission was denied.";
    toast(error.message || "Microphone permission was denied or no microphone is available.");
  }
}

async function refreshVoiceStatus() {
  try {
    const status = await api("/api/voice/status");
    state.speechModelInstalled = Boolean(status.speech_model_installed);
    speakerToggle.disabled = !status.speaker.available;
    if (!status.speech_model_installed && status.speech_recognition_available) voiceModelButton.hidden = false;
    if (!status.speech_recognition_available) micButton.disabled = true;
    if (!status.speaker.available) speakerToggle.title = status.speaker.reason || "Local spoken output is unavailable";
    const voiceChoice = document.querySelector("#voice-choice");
    voiceChoice.replaceChildren(new Option("System default voice", ""));
    for (const voice of status.speaker.voices || []) voiceChoice.add(new Option(voice, voice));
    document.querySelector("#speaker-diagnostic").textContent = status.speaker.available
      ? `Local Windows speech is ready · ${status.speaker.voices.length} installed voice(s)`
      : (status.speaker.reason || "No local speaker voice was detected.");
  } catch { /* Text mode remains available when voice diagnostics fail. */ }
}

function showSettings(open = true) {
  const panel = document.querySelector("#settings-panel");
  panel.classList.toggle("open", open);
  panel.setAttribute("aria-hidden", String(!open));
}

async function renderApprovedFolders(folders) {
  const target = document.querySelector("#approved-folders");
  target.replaceChildren();
  if (!folders.length) {
    const empty = document.createElement("small");
    empty.textContent = "No folders approved.";
    target.append(empty);
    return;
  }
  for (const folder of folders) {
    const row = document.createElement("div");
    row.className = "approved-folder";
    const path = document.createElement("span");
    path.textContent = folder;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.addEventListener("click", async () => {
      try {
        const result = await api("/api/folders/approved", { method: "DELETE", body: JSON.stringify({ path: folder }) });
        await renderApprovedFolders(result.approved_folders);
      } catch (error) { toast(error.message); }
    });
    row.append(path, remove);
    target.append(row);
  }
}

async function loadSettings() {
  const settings = await api("/api/settings");
  document.querySelector("#model-choice").value = settings.model;
  document.querySelector("#persona-input").value = settings.system_prompt;
  document.querySelector("#web-search-enabled").checked = settings.web_search_enabled;
  document.querySelector("#semantic-memory-enabled").checked = settings.semantic_memory_enabled;
  document.querySelector("#mode-choice").value = settings.mode;
  document.querySelector("#voice-rate").value = settings.voice_rate;
  document.querySelector("#voice-pitch").value = settings.voice_pitch;
  document.querySelector("#voice-rate-label").textContent = settings.voice_rate;
  document.querySelector("#voice-pitch-label").textContent = settings.voice_pitch;
  const encryptionToggle = document.querySelector("#encryption-enabled");
  encryptionToggle.disabled = !settings.encryption.supported;
  encryptionToggle.checked = settings.encryption.enabled;
  state.encryptionEnabled = settings.encryption.enabled;
  document.querySelector("#encryption-status").textContent = settings.encryption.supported
    ? (settings.encryption.enabled
      ? "Encrypted for this Windows account. The database is decrypted only in memory while Aster runs."
      : "Off. Turn this on to protect the database with Windows DPAPI. Previously created backups are not changed.")
    : "Database encryption is currently supported on Windows only. Use operating-system disk encryption on this platform.";
  setSpeaker(settings.voice_output_enabled || settings.mode === "voice");
  await renderApprovedFolders(settings.approved_folders);
  await refreshVoiceStatus();
  await refreshDiagnostics();
}

async function streamEmbeddingInstall() {
  const button = document.querySelector("#install-embedding-model");
  const log = document.querySelector("#embedding-progress");
  button.disabled = true;
  log.textContent = "Starting local embedding model download…";
  try {
    const response = await fetch("/api/setup/embedding-model", {
      method: "POST",
      headers: { "Authorization": `Bearer ${state.token}`, "Content-Type": "application/json" },
      body: "{}",
      cache: "no-store",
    });
    if (!response.ok) {
      const problem = await response.json().catch(() => ({}));
      throw new Error(problem.detail || `Embedding model setup failed (${response.status}).`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const events = pending.split("\n\n");
      pending = events.pop() || "";
      for (const item of events) {
        const line = item.split("\n").find((entry) => entry.startsWith("data: "));
        if (!line) continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === "progress") log.textContent = `${log.textContent}\n${event.line}`.slice(-6000);
        if (event.type === "error") throw new Error(event.message || "Ollama could not download the embedding model.");
        if (event.type === "done") log.textContent = `${log.textContent}\nEmbedding model ready.`.slice(-6000);
      }
    }
    toast("The local embedding model is ready. Enable semantic memory and save settings to use it.");
  } catch (error) {
    log.textContent = `${log.textContent}\n${error.message}`.slice(-6000);
    toast(error.message);
  } finally { button.disabled = false; }
}

async function refreshDiagnostics() {
  const output = document.querySelector("#diagnostics-output");
  output.textContent = "Checking local components…";
  try {
    const details = await api("/api/diagnostics");
    document.querySelector("#model-recommendation").textContent = `Detected ${details.memory_bytes ? `${(details.memory_bytes / (1024 ** 3)).toFixed(0)} GB RAM` : "unknown memory"}; recommended ${details.recommended_model}.`;
    output.textContent = JSON.stringify(details, null, 2);
  } catch (error) { output.textContent = error.message; }
}

async function streamModelInstall() {
  const button = document.querySelector("#install-model");
  const log = document.querySelector("#model-progress");
  button.disabled = true;
  log.textContent = "Starting local model download…";
  try {
    const response = await fetch("/api/setup/model", {
      method: "POST",
      headers: { "Authorization": `Bearer ${state.token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: document.querySelector("#model-choice").value }),
      cache: "no-store",
    });
    if (!response.ok) {
      const problem = await response.json().catch(() => ({}));
      throw new Error(problem.detail || `Model setup failed (${response.status}).`);
    }
    if (!response.body) throw new Error("The model download stream is unavailable.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    let failed = false;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      const events = pending.split("\n\n");
      pending = events.pop() || "";
      for (const item of events) {
        const line = item.split("\n").find((entry) => entry.startsWith("data: "));
        if (!line) continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === "progress") log.textContent = `${log.textContent}\n${event.line}`.slice(-6000);
        if (event.type === "error") { failed = true; throw new Error(event.message || "Ollama could not download the model."); }
        if (event.type === "done") log.textContent = `${log.textContent}\nModel ready.`.slice(-6000);
      }
    }
    await refreshHealth();
    await refreshDiagnostics();
    if (!failed) toast("The local model is ready.");
  } catch (error) {
    log.textContent = `${log.textContent}\n${error.message}`.slice(-6000);
    toast(error.message);
  } finally { button.disabled = false; }
}

async function refreshHealth() {
  try {
    const health = await fetch("/api/health").then((response) => response.json());
    state.modelReady = health.ollama === "ready" && health.model_available;
    if (health.ollama !== "ready") {
      modelStatus.textContent = "Ollama is not running. Start Ollama, then reload this page.";
    } else if (!health.model_available) {
      modelStatus.textContent = `Model ${health.model} is missing. Run: ollama pull ${health.model}`;
    } else {
      modelStatus.textContent = `Ready · ${health.model} · inference stays on this computer`;
    }
  } catch {
    state.modelReady = false;
    modelStatus.textContent = "Could not check Ollama. Confirm it is running on this computer.";
  }
}

async function refreshMemories() {
  const list = document.querySelector("#memory-list");
  list.replaceChildren();
  const memories = await api("/api/memories");
  if (!memories.length) {
    const empty = document.createElement("p");
    empty.className = "empty-memory";
    empty.textContent = "No saved notes yet.";
    list.append(empty);
    return;
  }
  for (const memory of memories) {
    const item = document.createElement("article");
    item.className = "memory-item";
    const content = document.createElement("div");
    content.className = "memory-text";
    content.textContent = memory.content;
    const actions = document.createElement("div");
    actions.className = "memory-actions";
    const edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "Edit";
    edit.addEventListener("click", async () => {
      const updated = window.prompt("Edit this saved note:", memory.content);
      if (updated === null) return;
      try {
        await api(`/api/memories/${encodeURIComponent(memory.id)}`, { method: "PUT", body: JSON.stringify({ content: updated }) });
        await refreshMemories();
        toast("Memory updated.");
      } catch (error) { toast(error.message); }
    });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      try {
        await api(`/api/memories/${encodeURIComponent(memory.id)}`, { method: "DELETE" });
        await refreshMemories();
        toast("Memory deleted.");
      } catch (error) { toast(error.message); }
    });
    actions.append(edit, remove);
    item.append(content, actions);
    list.append(item);
  }
}

async function refreshAgenda() {
  const list = document.querySelector("#agenda-list");
  const items = await api("/api/agenda");
  list.replaceChildren();
  const notified = new Set(JSON.parse(localStorage.getItem("aster.notified-reminders") || "[]"));
  const now = Date.now();
  for (const item of items) {
    const done = Boolean(item.completed);
    const due = item.due_at ? new Date(item.due_at) : null;
    if (!done && item.kind === "reminder" && due && due.getTime() <= now && !notified.has(item.id)) {
      toast(`Reminder: ${item.title}`);
      notified.add(item.id);
    }
    const row = document.createElement("article");
    row.className = `agenda-item${done ? " done" : ""}`;
    const title = document.createElement("div");
    title.className = "agenda-title";
    title.textContent = `${item.kind.toUpperCase()} · ${item.title}`;
    const meta = document.createElement("div");
    meta.className = "agenda-meta";
    meta.textContent = due ? `Due ${due.toLocaleString()}` : (done ? "Completed" : "No due date");
    row.append(title, meta);
    if (item.content) {
      const content = document.createElement("div");
      content.className = "agenda-content";
      content.textContent = item.content;
      row.append(content);
    }
    const actions = document.createElement("div");
    actions.className = "agenda-actions";
    if (!done && ["todo", "reminder"].includes(item.kind)) {
      const complete = document.createElement("button");
      complete.type = "button";
      complete.textContent = "Complete";
      complete.addEventListener("click", async () => {
        try { await api(`/api/agenda/${item.id}/complete`, { method: "POST", body: "{}" }); await refreshAgenda(); }
        catch (error) { toast(error.message); }
      });
      actions.append(complete);
    }
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Delete";
    remove.addEventListener("click", async () => {
      if (!window.confirm(`Delete “${item.title}” from this computer?`)) return;
      try { await api(`/api/agenda/${item.id}`, { method: "DELETE" }); await refreshAgenda(); }
      catch (error) { toast(error.message); }
    });
    actions.append(remove);
    row.append(actions);
    list.append(row);
  }
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "empty-memory";
    empty.textContent = "No reminders, tasks, or notes yet.";
    list.append(empty);
  }
  localStorage.setItem("aster.notified-reminders", JSON.stringify([...notified]));
}

document.querySelector("#composer").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  input.style.height = "auto";
  await sendMessage(text);
});
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    document.querySelector("#composer").requestSubmit();
  }
});
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
});
document.querySelector("#new-chat").addEventListener("click", () => {
  state.conversationId = crypto.randomUUID();
  localStorage.setItem("aster.conversation", state.conversationId);
  transcript.replaceChildren();
  intro.hidden = false;
  toast("New conversation started.");
});
document.querySelector("#memory-toggle").addEventListener("click", async () => {
  memoryPanel.classList.add("open");
  memoryPanel.setAttribute("aria-hidden", "false");
  try { await refreshMemories(); } catch (error) { toast(error.message); }
});
document.querySelector("#memory-close").addEventListener("click", () => {
  memoryPanel.classList.remove("open");
  memoryPanel.setAttribute("aria-hidden", "true");
});
document.querySelector("#agenda-toggle").addEventListener("click", async () => {
  const panel = document.querySelector("#agenda-panel");
  panel.classList.add("open");
  panel.setAttribute("aria-hidden", "false");
  try { await refreshAgenda(); } catch (error) { toast(error.message); }
});
document.querySelector("#agenda-close").addEventListener("click", () => {
  const panel = document.querySelector("#agenda-panel");
  panel.classList.remove("open");
  panel.setAttribute("aria-hidden", "true");
});
document.querySelector("#memory-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const field = document.querySelector("#memory-input");
  const content = field.value.trim();
  if (!content) return;
  try {
    await api("/api/memories", { method: "POST", body: JSON.stringify({ content }) });
    field.value = "";
    await refreshMemories();
    toast("Memory saved on this computer.");
  } catch (error) { toast(error.message); }
});
document.querySelector("#export-data").addEventListener("click", async () => {
  try {
    const response = await fetch("/api/export", { headers: { "Authorization": `Bearer ${state.token}` }, cache: "no-store" });
    if (!response.ok) throw new Error("Could not export local data.");
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "aster-local-export.json";
    link.click();
    URL.revokeObjectURL(url);
    toast("Export saved to your downloads.");
  } catch (error) { toast(error.message); }
});
document.querySelector("#forget-all").addEventListener("click", async () => {
  if (!window.confirm("Delete all conversations, memories, notes, reminders, to-dos, settings, and approved folders from this device? This cannot be undone.")) return;
  try {
    await api("/api/forget-everything", { method: "DELETE" });
    transcript.replaceChildren();
    intro.hidden = false;
    localStorage.removeItem("aster.notified-reminders");
    await refreshMemories();
    await refreshAgenda();
    await loadSettings();
    toast("Local conversations and user data deleted.");
  } catch (error) { toast(error.message); }
});

micButton.addEventListener("click", () => {
  if (state.recording) {
    clearTimeout(state.recordingTimer);
    finishRecording();
  } else if (!state.finishingRecording) {
    startRecording();
  }
});
speakerToggle.addEventListener("click", async () => {
  setSpeaker(!state.speakerEnabled);
  try { await api("/api/settings", { method: "PUT", body: JSON.stringify({ voice_output_enabled: state.speakerEnabled }) }); }
  catch (error) { setSpeaker(!state.speakerEnabled); toast(error.message); }
});
voiceModelButton.addEventListener("click", async () => {
  voiceModelButton.disabled = true;
  microphoneStatus.textContent = "Downloading and verifying the 118 MB speech model…";
  try {
    await api("/api/setup/voice-model", { method: "POST", body: "{}" });
    voiceModelButton.hidden = true;
    microphoneStatus.textContent = "Speech model ready · audio is processed locally";
    toast("Speech recognition is ready.");
  } catch (error) {
    toast(error.message);
  } finally {
    voiceModelButton.disabled = false;
    if (!state.recording) microphoneStatus.textContent = "Enter to send · Shift + Enter for a new line";
  }
});
document.querySelector("#settings-toggle").addEventListener("click", async () => {
  showSettings(true);
  try { await loadSettings(); } catch (error) { toast(error.message); }
});
document.querySelector("#settings-close").addEventListener("click", () => showSettings(false));
document.querySelector("#install-model").addEventListener("click", streamModelInstall);
document.querySelector("#install-embedding-model").addEventListener("click", streamEmbeddingInstall);
document.querySelector("#refresh-diagnostics").addEventListener("click", refreshDiagnostics);
document.querySelector("#approve-folder").addEventListener("click", async () => {
  const button = document.querySelector("#approve-folder");
  button.disabled = true;
  try {
    const result = await api("/api/folders/select", { method: "POST", body: "{}" });
    if (!result.cancelled) await renderApprovedFolders(result.approved_folders);
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
});
document.querySelector("#mode-choice").addEventListener("change", (event) => {
  if (event.target.value === "voice") setSpeaker(true);
});
document.querySelector("#voice-rate").addEventListener("input", (event) => { document.querySelector("#voice-rate-label").textContent = event.target.value; });
document.querySelector("#voice-pitch").addEventListener("input", (event) => { document.querySelector("#voice-pitch-label").textContent = event.target.value; });
document.querySelector("#test-microphone").addEventListener("click", () => {
  const button = document.querySelector("#test-microphone");
  if (state.recording && state.recordingPurpose === "test") {
    clearTimeout(state.recordingTimer);
    finishRecording();
    return;
  }
  if (state.recording || state.finishingRecording) {
    toast("Finish the current push-to-talk recording before testing the microphone.");
    return;
  }
  document.querySelector("#microphone-test-result").textContent = "Listening for up to 30 seconds. Speak, then pause to finish.";
  button.textContent = "Stop microphone test";
  startRecording("test");
});
document.querySelector("#test-speaker").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await api("/api/speech/test", {
      method: "POST",
      body: JSON.stringify({
        voice: document.querySelector("#voice-choice").value,
        rate: Number(document.querySelector("#voice-rate").value),
        pitch: Number(document.querySelector("#voice-pitch").value),
      }),
    });
    toast("Playing a short local speaker test.");
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; }
});
document.querySelector("#save-settings").addEventListener("click", async () => {
  const mode = document.querySelector("#mode-choice").value;
  if (mode === "voice") setSpeaker(true);
  const values = {
    model: document.querySelector("#model-choice").value,
    system_prompt: document.querySelector("#persona-input").value,
    web_search_enabled: document.querySelector("#web-search-enabled").checked,
    semantic_memory_enabled: document.querySelector("#semantic-memory-enabled").checked,
    voice_output_enabled: state.speakerEnabled,
    voice: document.querySelector("#voice-choice").value,
    voice_rate: Number(document.querySelector("#voice-rate").value),
    voice_pitch: Number(document.querySelector("#voice-pitch").value),
    mode,
  };
  try {
    const saved = await api("/api/settings", { method: "PUT", body: JSON.stringify(values) });
    const encryptionWanted = document.querySelector("#encryption-enabled").checked;
    if (encryptionWanted !== state.encryptionEnabled) {
      const prompt = encryptionWanted
        ? "Encrypt Aster's local database for this Windows account? Existing backups and deleted disk blocks are not re-encrypted."
        : "Turn off database encryption? Aster will write its database in plaintext for this Windows account.";
      if (!window.confirm(prompt)) {
        document.querySelector("#encryption-enabled").checked = state.encryptionEnabled;
      } else {
        const encryption = await api("/api/encryption", { method: "PUT", body: JSON.stringify({ enabled: encryptionWanted }) });
        state.encryptionEnabled = encryption.enabled;
      }
    }
    await refreshHealth();
    await refreshDiagnostics();
    await loadSettings();
    toast("Settings saved on this computer.");
  } catch (error) { toast(error.message); }
});
document.addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.code === "Space") {
    event.preventDefault();
    if (state.recording) finishRecording(); else startRecording();
  }
  if (event.key === "Escape") showSettings(false);
});

async function start() {
  try {
    const response = await fetch("/api/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}", cache: "no-store" });
    if (!response.ok) throw new Error("Could not start a secure local session.");
    state.token = (await response.json()).token;
    await Promise.all([loadHistory(), connect()]);
    await refreshHealth();
    await loadSettings();
    await refreshAgenda();
    document.querySelector("#launch-warning").hidden = true;
    setInterval(() => refreshAgenda().catch(() => {}), 15000);
    if (!state.modelReady && !localStorage.getItem("aster.setup-seen")) {
      showSettings(true);
      localStorage.setItem("aster.setup-seen", "true");
    }
  } catch (error) {
    setConnection("bad", "Could not connect");
    modelStatus.textContent = error.message;
  }
}

start();
