import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import "../parent-chat.css";
import { ApiError } from "../api";
import LogoutButton from "../components/LogoutButton";
import { getCheckin, sendText, sendVoice, type ChatMessage, type ReminderDue, type TurnOut } from "../parentApi";

// The parent's check-in chat: tap the big mic, speak, and see/hear the reply.
// Bot bubbles sit on the left, the parent's on the right. Text input is always one tap away.

const MAX_RECORD_MS = 15_000;
const VOICE_UNAVAILABLE = "Voice isn't available right now. Please type instead.";
const GENERIC_ERROR = "Something went wrong. Please try again.";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "unlinked"; detail: string }
  | { kind: "forbidden" }
  | { kind: "error" };

type Phase = "idle" | "recording" | "sending";

interface Bubble {
  sender: "bot" | "parent";
  text: string;
}

function voiceSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.MediaRecorder !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === "function"
  );
}

function pickMimeType(): string | undefined {
  const preferred = "audio/webm;codecs=opus";
  try {
    if (typeof MediaRecorder.isTypeSupported === "function" && MediaRecorder.isTypeSupported(preferred)) {
      return preferred;
    }
  } catch {
    // Fall back to the browser default.
  }
  return undefined;
}

function telHref(number: string): string {
  return `tel:${number.replace(/[^\d+]/g, "")}`;
}

function reminderKey(r: ReminderDue): string {
  return `${r.medicine_id}|${r.slot}|${r.remind_at}`;
}

export default function ParentChat() {
  const navigate = useNavigate();
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [messages, setMessages] = useState<Bubble[]>([]);
  const [language, setLanguage] = useState("en");
  const [callNumber, setCallNumber] = useState<string | null>(null);
  const [reminders, setReminders] = useState<ReminderDue[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [canUseVoice] = useState(voiceSupported);
  const [showText, setShowText] = useState(() => !voiceSupported());
  const [text, setText] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  // Bumped after every server response so the reminder timer is recomputed.
  const [responseTick, setResponseTick] = useState(0);

  const endRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const stopTimerRef = useRef<number | null>(null);
  const audioRef = useRef<{ audio: HTMLAudioElement; url: string } | null>(null);
  const firedRef = useRef<Set<string>>(new Set());
  const busyRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    busyRef.current = phase !== "idle";
  }, [phase]);

  // ---------- errors shared by every call ----------

  /** Handles 401/403/409. Returns true when the error was handled that way. */
  const handleAuthError = useCallback(
    (err: unknown): boolean => {
      if (!(err instanceof ApiError)) return false;
      if (err.status === 401) {
        navigate("/start", { replace: true });
        return true;
      }
      if (err.status === 403) {
        setLoad({ kind: "forbidden" });
        return true;
      }
      if (err.status === 409) {
        setLoad({ kind: "unlinked", detail: err.detail || "Ask your family to link your profile" });
        return true;
      }
      return false;
    },
    [navigate],
  );

  // ---------- audio playback ----------

  const stopAudio = useCallback(() => {
    const current = audioRef.current;
    if (!current) return;
    current.audio.pause();
    URL.revokeObjectURL(current.url);
    audioRef.current = null;
  }, []);

  const playAudio = useCallback(
    (base64: string | null, type: string | null) => {
      if (!base64) return;
      stopAudio();
      let url: string;
      try {
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        url = URL.createObjectURL(new Blob([bytes], { type: type || "audio/mpeg" }));
      } catch {
        return; // Bad audio: the text is already on screen.
      }
      const audio = new Audio(url);
      const entry = { audio, url };
      audioRef.current = entry;
      const release = () => {
        URL.revokeObjectURL(url);
        if (audioRef.current === entry) audioRef.current = null;
      };
      audio.addEventListener("ended", release);
      audio.addEventListener("error", release);
      audio.play().catch(() => {
        // Autoplay blocked or unsupported: the text is already shown.
        release();
      });
    },
    [stopAudio],
  );

  // ---------- loading the conversation ----------

  const refresh = useCallback(async () => {
    try {
      const data = await getCheckin();
      if (!mountedRef.current) return;
      setMessages(data.messages.map((m: ChatMessage) => ({ sender: m.sender, text: m.text })));
      setLanguage(data.language || "en");
      setCallNumber(data.call_number);
      setReminders(data.reminders_due);
      setLoad({ kind: "ready" });
    } catch (err) {
      if (!mountedRef.current) return;
      if (handleAuthError(err)) return;
      setLoad((prev) => (prev.kind === "ready" ? prev : { kind: "error" }));
    } finally {
      if (mountedRef.current) setResponseTick((t) => t + 1);
    }
  }, [handleAuthError]);

  useEffect(() => {
    mountedRef.current = true;
    void refresh();
    return () => {
      mountedRef.current = false;
    };
  }, [refresh]);

  // Clean up the mic, timers and audio when leaving the page.
  useEffect(() => {
    return () => {
      if (stopTimerRef.current !== null) window.clearTimeout(stopTimerRef.current);
      const rec = recorderRef.current;
      if (rec && rec.state !== "inactive") {
        rec.ondataavailable = null;
        rec.onstop = null;
        rec.stop();
      }
      streamRef.current?.getTracks().forEach((t) => t.stop());
      stopAudio();
    };
  }, [stopAudio]);

  // When a medicine reminder time passes while the page is open, fetch the conversation again
  // (the server then adds the medicine question).
  useEffect(() => {
    if (load.kind !== "ready") return;
    const pending = reminders
      .filter((r) => !firedRef.current.has(reminderKey(r)))
      .map((r) => ({ r, at: Date.parse(r.remind_at) }))
      .filter((x) => Number.isFinite(x.at))
      .sort((a, b) => a.at - b.at);
    if (pending.length === 0) return;
    const next = pending[0];
    // A small buffer so the server's clock has also passed remind_at.
    const delay = Math.min(Math.max(next.at - Date.now(), 0) + 2000, 2_147_000_000);
    let timer = window.setTimeout(function fire() {
      if (busyRef.current) {
        timer = window.setTimeout(fire, 5000);
        return;
      }
      firedRef.current.add(reminderKey(next.r));
      void refresh();
    }, delay);
    return () => window.clearTimeout(timer);
  }, [reminders, responseTick, load.kind, refresh]);

  // Keep the newest message in view.
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "end" });
  }, [messages, phase]);

  // ---------- a turn (text or voice) ----------

  function applyTurn(turn: TurnOut) {
    setMessages((prev) => [...prev, ...turn.messages.map((m) => ({ sender: m.sender, text: m.text }))]);
    if (turn.call_number) setCallNumber(turn.call_number);
    playAudio(turn.audio, turn.audio_type);
    setResponseTick((t) => t + 1);
  }

  function openTextInput() {
    setShowText(true);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }

  async function handleSendText(e: FormEvent) {
    e.preventDefault();
    const value = text.trim();
    if (!value || phase !== "idle") return;
    stopAudio();
    setNotice(null);
    setPhase("sending");
    setText("");
    setMessages((prev) => [...prev, { sender: "parent", text: value }]);
    try {
      const turn = await sendText(value);
      if (!mountedRef.current) return;
      applyTurn(turn);
    } catch (err) {
      if (!mountedRef.current) return;
      // The message wasn't taken: remove the bubble and give the text back.
      setMessages((prev) => prev.slice(0, -1));
      setText(value);
      if (!handleAuthError(err)) {
        setNotice(err instanceof ApiError && err.status === 400 && err.detail ? err.detail : GENERIC_ERROR);
      }
    } finally {
      if (mountedRef.current) setPhase("idle");
    }
  }

  async function submitVoice(blob: Blob) {
    if (blob.size === 0) {
      setNotice("I didn't hear anything. Please tap the microphone and try again.");
      setPhase("idle");
      return;
    }
    try {
      const turn = await sendVoice(blob);
      if (!mountedRef.current) return;
      const heard = turn.transcript?.trim();
      if (heard) setMessages((prev) => [...prev, { sender: "parent", text: heard }]);
      applyTurn(turn);
    } catch (err) {
      if (!mountedRef.current) return;
      if (handleAuthError(err)) return;
      if (err instanceof ApiError && err.status === 503) {
        setNotice(err.detail || VOICE_UNAVAILABLE);
        openTextInput();
      } else if (err instanceof ApiError && (err.status === 413 || err.status === 400)) {
        setNotice(err.detail || GENERIC_ERROR);
      } else {
        setNotice(GENERIC_ERROR);
      }
    } finally {
      if (mountedRef.current) setPhase("idle");
    }
  }

  // ---------- recording ----------

  function stopRecording() {
    if (stopTimerRef.current !== null) {
      window.clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }
    const rec = recorderRef.current;
    if (rec && rec.state !== "inactive") rec.stop();
  }

  async function startRecording() {
    stopAudio();
    setNotice(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setNotice("I can't use the microphone. Please allow it, or type your answer below.");
      openTextInput();
      return;
    }
    if (!mountedRef.current) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    let rec: MediaRecorder;
    try {
      const mimeType = pickMimeType();
      rec = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      setNotice("Voice isn't available on this phone. Please type your answer below.");
      openTextInput();
      return;
    }
    streamRef.current = stream;
    recorderRef.current = rec;
    chunksRef.current = [];
    rec.ondataavailable = (ev: BlobEvent) => {
      if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
    };
    rec.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      recorderRef.current = null;
      const type = rec.mimeType || chunksRef.current[0]?.type || "audio/webm";
      const blob = new Blob(chunksRef.current, { type });
      chunksRef.current = [];
      if (!mountedRef.current) return;
      setPhase("sending");
      void submitVoice(blob);
    };
    try {
      rec.start();
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      recorderRef.current = null;
      setNotice("Voice isn't available on this phone. Please type your answer below.");
      openTextInput();
      return;
    }
    setPhase("recording");
    stopTimerRef.current = window.setTimeout(stopRecording, MAX_RECORD_MS);
  }

  function handleMic() {
    if (phase === "recording") stopRecording();
    else if (phase === "idle") void startRecording();
  }

  // ---------- render ----------

  const header = (
    <header className="pc-header">
      <h1 className="pc-brand">CareCircle</h1>
      <div className="pc-header-actions">
        {load.kind === "ready" && (
          <button
            type="button"
            className="pc-help-btn"
            aria-expanded={helpOpen}
            aria-controls="pc-help-panel"
            onClick={() => setHelpOpen((o) => !o)}
          >
            Help
          </button>
        )}
        <LogoutButton className="pc-logout" />
      </div>
    </header>
  );

  if (load.kind !== "ready") {
    return (
      <div className="pc-page">
        {header}
        <main className="pc-main pc-main--center">
          {load.kind === "loading" && (
            <p className="pc-status" role="status">
              Getting ready…
            </p>
          )}
          {load.kind === "unlinked" && (
            <div className="pc-card" role="alert">
              <h2>Almost there</h2>
              <p>{load.detail}</p>
            </div>
          )}
          {load.kind === "forbidden" && (
            <div className="pc-card" role="alert">
              <h2>This page is for parents</h2>
              <p>
                <Link to="/start" className="pc-link">
                  Go to the start page
                </Link>
              </p>
            </div>
          )}
          {load.kind === "error" && (
            <div className="pc-card" role="alert">
              <h2>We couldn't load your chat</h2>
              <p>{GENERIC_ERROR}</p>
              <button
                type="button"
                className="pc-primary-btn"
                onClick={() => {
                  setLoad({ kind: "loading" });
                  void refresh();
                }}
              >
                Try again
              </button>
            </div>
          )}
        </main>
      </div>
    );
  }

  const statusText = phase === "recording" ? "Listening…" : phase === "sending" ? "Thinking…" : "";

  return (
    <div className="pc-page">
      {header}

      {helpOpen && (
        <section id="pc-help-panel" className="pc-help" aria-label="Help">
          {callNumber ? (
            <a className="pc-call-btn" href={telHref(callNumber)}>
              <span aria-hidden="true">📞</span> Call family
              <span className="pc-call-number">{callNumber}</span>
            </a>
          ) : (
            <p className="pc-help-text">Ask your family to add a phone number</p>
          )}
        </section>
      )}

      {callNumber && !helpOpen && (
        <div className="pc-call-wrap">
          <a className="pc-call-btn" href={telHref(callNumber)}>
            <span aria-hidden="true">📞</span> Call family
            <span className="pc-call-number">{callNumber}</span>
          </a>
        </div>
      )}

      <main className="pc-main">
        <ol className="pc-messages" lang={language} aria-live="polite" aria-label="Conversation">
          {messages.map((m, i) => (
            <li key={i} className={`pc-bubble pc-bubble--${m.sender}`}>
              <span className="pc-sr">{m.sender === "bot" ? "CareCircle says:" : "You said:"}</span>
              {m.text}
            </li>
          ))}
        </ol>
        {statusText && (
          <p className="pc-status" role="status">
            {statusText}
          </p>
        )}
        <div ref={endRef} />
      </main>

      <footer className="pc-controls">
        {notice && (
          <p className="pc-notice" role="alert">
            {notice}
          </p>
        )}

        {canUseVoice && (
          <button
            type="button"
            className={`pc-mic${phase === "recording" ? " is-recording" : ""}`}
            onClick={handleMic}
            disabled={phase === "sending"}
            aria-pressed={phase === "recording"}
            aria-label={phase === "recording" ? "Stop and send" : "Tap to speak"}
          >
            <svg viewBox="0 0 24 24" width="56" height="56" aria-hidden="true">
              {phase === "recording" ? (
                <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
              ) : (
                <path
                  d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}
            </svg>
          </button>
        )}
        {canUseVoice && (
          <p className="pc-mic-hint" aria-hidden="true">
            {phase === "recording" ? "Tap again to send" : phase === "sending" ? "Please wait" : "Tap to speak"}
          </p>
        )}

        {showText ? (
          <form className="pc-text-form" onSubmit={handleSendText}>
            <label htmlFor="pc-text" className="pc-sr">
              Type your answer
            </label>
            <input
              id="pc-text"
              ref={inputRef}
              className="pc-text-input"
              type="text"
              lang={language}
              value={text}
              maxLength={2000}
              autoComplete="off"
              placeholder="Type your answer"
              onChange={(e) => setText(e.target.value)}
            />
            <button type="submit" className="pc-primary-btn" disabled={phase !== "idle" || !text.trim()}>
              Send
            </button>
          </form>
        ) : (
          <button type="button" className="pc-type-btn" onClick={openTextInput}>
            Type instead
          </button>
        )}
      </footer>
    </div>
  );
}
