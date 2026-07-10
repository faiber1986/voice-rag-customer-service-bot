// Push-to-talk demo client for the streaming voice endpoint.
//
// Captures the microphone, resamples to 16kHz mono PCM16, chunks it into
// 20ms frames (matching app/voice/vad.py's webrtcvad frame size), and
// streams them over a WebSocket to /ws/voice?lang=<en|es>. Renders partial
// transcripts (English mode only), streamed answer tokens, and plays back
// streamed TTS audio chunks as they arrive.
//
// Known simplification (documented in README Future Work): uses
// ScriptProcessorNode, which is deprecated in favor of AudioWorklet, but
// needs no separate module file and is universally supported — a reasonable
// trade-off for a demo page with no build step.

const SAMPLE_RATE = 16000;
const FRAME_MS = 20;
const FRAME_SAMPLES = (SAMPLE_RATE * FRAME_MS) / 1000; // 320 samples = 640 bytes
const RELEASE_TIMEOUT_MS = 5000; // safety net if the server never sends "done"

const connectionStatusEl = document.getElementById("connection-status");
const turnStatusEl = document.getElementById("turn-status");
const recordButton = document.getElementById("record-button");
const transcriptEl = document.getElementById("transcript");
const transcriptPanelEl = document.getElementById("transcript-panel");
const answerEl = document.getElementById("answer");
const languageSelect = document.getElementById("language-select");
const themeToggle = document.getElementById("theme-toggle");

// --- UI strings (specs/006 FR-001: bilingual conversation surface) ---

const UI_STRINGS = {
  en: {
    subtitle: "Financial domain demo — streaming voice pipeline (STT → RAG → LLM → TTS)",
    holdToTalk: "Hold to talk",
    transcriptHeading: "Transcript",
    answerHeading: "Answer",
    examplesHeading: "Try asking",
    transcriptPlaceholder:
      'Nothing yet — hold the button and ask a question, e.g. "What\'s my checking account balance?"',
    connected: "Connected",
    disconnected: "Disconnected",
    statusIdle: "Idle",
    statusListening: "Listening",
    statusThinking: "Thinking",
    statusSpeaking: "Speaking",
    examples: [
      '"What\'s my checking account balance?"',
      '"What are my most recent transactions?"',
      '"What interest rate do savings accounts earn?"',
      '"What\'s the weather like tomorrow?" (out of domain — should refuse)',
      '"Can I talk to a human agent?" (explicit escalation)',
    ],
  },
  es: {
    subtitle: "Demo de dominio financiero — pipeline de voz en streaming (STT → RAG → LLM → TTS)",
    holdToTalk: "Mantén presionado para hablar",
    transcriptHeading: "Transcripción",
    answerHeading: "Respuesta",
    examplesHeading: "Prueba preguntar",
    transcriptPlaceholder: "",
    connected: "Conectado",
    disconnected: "Desconectado",
    statusIdle: "En espera",
    statusListening: "Escuchando",
    statusThinking: "Pensando",
    statusSpeaking: "Hablando",
    examples: [
      '"¿Cuál es el saldo de mi cuenta de cheques?"',
      '"¿Cuáles son mis transacciones más recientes?"',
      '"¿Qué tasa de interés ganan las cuentas de ahorro?"',
      '"¿Cómo estará el clima mañana?" (fuera de dominio — debe rechazar)',
      '"¿Puedo hablar con un agente humano?" (escalación explícita)',
    ],
  },
};

let currentLanguage = localStorage.getItem("language") || "en";

function applyLanguage(lang) {
  currentLanguage = lang;
  localStorage.setItem("language", lang);
  languageSelect.value = lang;
  document.documentElement.lang = lang;

  const s = UI_STRINGS[lang];
  document.getElementById("ui-subtitle").textContent = s.subtitle;
  document.getElementById("ui-transcript-heading").textContent = s.transcriptHeading;
  document.getElementById("ui-answer-heading").textContent = s.answerHeading;
  document.getElementById("ui-examples-heading").textContent = s.examplesHeading;
  recordButton.textContent = s.holdToTalk;

  const examplesList = document.getElementById("examples-list");
  examplesList.innerHTML = "";
  for (const example of s.examples) {
    const li = document.createElement("li");
    li.textContent = example;
    examplesList.appendChild(li);
  }

  // Spanish mode hides the transcript panel (specs/006 FR-005): the server
  // translates Spanish speech to English internally, and showing that
  // English translation as "what you said" would be confusing.
  transcriptPanelEl.style.display = lang === "es" ? "none" : "";
}

// --- Theme (specs/006 FR-007: Light/Dark switch, OS-seeded, persisted) ---

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("theme", theme);
  themeToggle.textContent = theme === "dark" ? "☀️" : "🌙";
}

const storedTheme = localStorage.getItem("theme");
const osPrefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
applyTheme(storedTheme || (osPrefersDark ? "dark" : "light"));

themeToggle.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(next);
});

// --- WebSocket + audio pipeline ---

let ws = null;
let audioContext = null;
let mediaStream = null;
let sourceNode = null;
let processorNode = null;
let silentGainNode = null;
let recording = false;
let releasing = false;
let releaseTimer = null;
let pcmBuffer = new Int16Array(0);

let audioQueue = [];
let playingAudio = false;

function setConnectionStatus(connected) {
  const s = UI_STRINGS[currentLanguage];
  connectionStatusEl.textContent = connected ? s.connected : s.disconnected;
  connectionStatusEl.className = `badge ${connected ? "badge-connected" : "badge-disconnected"}`;
  recordButton.disabled = !connected;
}

function setTurnStatus(key, cssClass) {
  turnStatusEl.textContent = UI_STRINGS[currentLanguage][key];
  turnStatusEl.className = `badge badge-${cssClass}`;
}

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${location.host}/ws/voice?lang=${currentLanguage}`);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => setConnectionStatus(true);
  ws.onclose = () => {
    setConnectionStatus(false);
    setTimeout(connectWebSocket, 2000);
  };
  ws.onerror = () => ws.close();
  ws.onmessage = (event) => handleServerEvent(JSON.parse(event.data));
}

languageSelect.addEventListener("change", () => {
  applyLanguage(languageSelect.value);
  // Language is a per-connection parameter: reconnect so the next turn uses it.
  if (ws) {
    ws.onclose = null; // suppress the auto-reconnect from the old handler
    ws.close();
  }
  connectWebSocket();
});

function floatTo16BitPCM(float32Input) {
  const output = new Int16Array(float32Input.length);
  for (let i = 0; i < float32Input.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Input[i]));
    output[i] = s < 0 ? s * 32768 : s * 32767;
  }
  return output;
}

function resampleTo16k(float32Input, inputSampleRate) {
  if (inputSampleRate === SAMPLE_RATE) {
    return floatTo16BitPCM(float32Input);
  }
  const ratio = inputSampleRate / SAMPLE_RATE;
  const outputLength = Math.floor(float32Input.length / ratio);
  const output = new Int16Array(outputLength);
  for (let i = 0; i < outputLength; i++) {
    const srcIndex = i * ratio;
    const srcIndexFloor = Math.floor(srcIndex);
    const frac = srcIndex - srcIndexFloor;
    const s0 = float32Input[srcIndexFloor] || 0;
    const s1 = float32Input[srcIndexFloor + 1] || s0;
    const sample = s0 + (s1 - s0) * frac;
    output[i] = Math.max(-32768, Math.min(32767, Math.round(sample * 32768)));
  }
  return output;
}

async function startRecording() {
  if (recording) return;
  recording = true;
  releasing = false;
  pcmBuffer = new Int16Array(0);
  transcriptEl.textContent = "";
  answerEl.textContent = "";
  setTurnStatus("statusListening", "listening");
  recordButton.classList.add("recording");

  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  audioContext = new (window.AudioContext || window.webkitAudioContext)();
  sourceNode = audioContext.createMediaStreamSource(mediaStream);
  processorNode = audioContext.createScriptProcessor(4096, 1, 1);

  // ScriptProcessorNode needs its output to reach the destination to keep
  // firing onaudioprocess; near-silent gain instead of exactly 0 — some
  // Chrome versions optimize a provably-silent chain into skipping real
  // processing, delivering all-zero buffers.
  silentGainNode = audioContext.createGain();
  silentGainNode.gain.value = 0.0001;

  processorNode.onaudioprocess = (event) => {
    if (!recording && !releasing) return;
    const input = event.inputBuffer.getChannelData(0);
    const resampled = resampleTo16k(input, audioContext.sampleRate);

    const merged = new Int16Array(pcmBuffer.length + resampled.length);
    merged.set(pcmBuffer);
    merged.set(resampled, pcmBuffer.length);
    pcmBuffer = merged;

    while (pcmBuffer.length >= FRAME_SAMPLES) {
      const frame = pcmBuffer.slice(0, FRAME_SAMPLES);
      pcmBuffer = pcmBuffer.slice(FRAME_SAMPLES);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(frame.buffer);
      }
    }
  };

  sourceNode.connect(processorNode);
  processorNode.connect(silentGainNode);
  silentGainNode.connect(audioContext.destination);
}

function releaseRecording() {
  if (!recording) return;
  recording = false;
  releasing = true;
  recordButton.classList.remove("recording");
  setTurnStatus("statusThinking", "thinking");

  // Keep streaming real (now-quiet) mic audio after release so the server's
  // VAD sees genuine trailing silence and declares end-of-turn naturally.
  releaseTimer = setTimeout(stopMicHard, RELEASE_TIMEOUT_MS);
}

function stopMicHard() {
  releasing = false;
  clearTimeout(releaseTimer);
  if (processorNode) {
    processorNode.disconnect();
    processorNode = null;
  }
  if (silentGainNode) {
    silentGainNode.disconnect();
    silentGainNode = null;
  }
  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
}

function enqueueAudioChunk(base64Wav) {
  const binary = atob(base64Wav);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], { type: "audio/wav" });
  audioQueue.push(URL.createObjectURL(blob));
  playNextAudioChunk();
}

function playNextAudioChunk() {
  if (playingAudio || audioQueue.length === 0) return;
  playingAudio = true;
  const url = audioQueue.shift();
  const audio = new Audio(url);
  audio.onended = () => {
    playingAudio = false;
    URL.revokeObjectURL(url);
    playNextAudioChunk();
  };
  audio.play().catch(() => {
    playingAudio = false;
    playNextAudioChunk();
  });
}

function handleServerEvent(event) {
  switch (event.type) {
    case "partial_transcript":
    case "final_transcript":
      transcriptEl.textContent = event.text;
      break;
    case "retrieval_done":
      setTurnStatus("statusThinking", "thinking");
      break;
    case "answer_token":
      answerEl.textContent += event.text;
      break;
    case "audio_chunk":
      setTurnStatus("statusSpeaking", "speaking");
      enqueueAudioChunk(event.audio_base64);
      break;
    case "done":
      stopMicHard();
      setTurnStatus("statusIdle", "idle");
      break;
    default:
      break;
  }
}

recordButton.addEventListener("mousedown", startRecording);
recordButton.addEventListener("mouseup", releaseRecording);
recordButton.addEventListener("mouseleave", () => {
  if (recording) releaseRecording();
});
recordButton.addEventListener("touchstart", (event) => {
  event.preventDefault();
  startRecording();
});
recordButton.addEventListener("touchend", (event) => {
  event.preventDefault();
  releaseRecording();
});

applyLanguage(currentLanguage);
connectWebSocket();
