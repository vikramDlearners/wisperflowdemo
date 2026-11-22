import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import "../parent-chat.css";
import { ApiError } from "../api";
import LogoutButton from "../components/LogoutButton";
import ParentMedicinePhotos from "../components/ParentMedicinePhotos";
import { parentLangCode, parentStrings } from "../parentChatStrings";
import {
  fetchParentMedicinePhoto,
  getCheckin,
  getParentMedicines,
  sendText,
  sendVoice,
  type ChatMessage,
  type ParentMedicine,
  type ReminderDue,
  type TurnOut,
} from "../parentApi";

// The parent's check-in chat: tap the big mic, speak, and see/hear the reply.
// Bot bubbles sit on the left, the parent's on the right. Text input is always one tap away.

const MAX_RECORD_MS = 15_000;

type LoadState =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "unlinked" }
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
  // "" until the first load: strings then follow the browser locale.
  const [language, setLanguage] = useState("");
  const t = parentStrings(language);
  const [callNumber, setCallNumber] = useState<string | null>(null);
  const [helpNumber, setHelpNumber] = useState<string | null>(null);
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
  // Set synchronously on the first tap so a double tap can't start two recordings.
  const startingRef = useRef(false);
  // Bumped by every refresh and every turn; a refresh whose number is stale is ignored.
  const seqRef = useRef(0);
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
        setLoad({ kind: "unlinked" });
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

  // ---------- medicine photos ----------
  // Loaded once; a bot message that names a medicine shows its photo underneath.

  const [medicines, setMedicines] = useState<ParentMedicine[]>([]);
  const [photoUrls, setPhotoUrls] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    const created: string[] = [];
    (async () => {
      try {
        const meds = await getParentMedicines();
        if (cancelled) return;
        setMedicines(meds);
        for (const med of meds.filter((m) => m.has_image)) {
          const url = await fetchParentMedicinePhoto(med.id);
          if (!url) continue;
          if (cancelled) {
            URL.revokeObjectURL(url);
            return;
          }
          created.push(url);
          setPhotoUrls((prev) => ({ ...prev, [med.id]: url }));
        }
      } catch {
        // Photos are a help, not essential: the chat works without them.
      }
    })();
    return () => {
      cancelled = true;
      created.forEach((u) => URL.revokeObjectURL(u));
    };
  }, []);

  // ---------- loading the conversation ----------

  const refresh = useCallback(async () => {
    const seq = ++seqRef.current;
    try {
      const data = await getCheckin();
      // Ignore a snapshot that a newer turn or refresh has overtaken.
      if (!mountedRef.current || seq !== seqRef.current) return;
      setMessages(data.messages.map((m: ChatMessage) => ({ sender: m.sender, text: m.text })));
      setLanguage(data.language || "");
      setCallNumber(data.call_number);
      setHelpNumber(data.help_number);
      setReminders(data.reminders_due);
      setLoad({ kind: "ready" });
      // Speaks the greeting / newly asked question (null on a plain reload).
      playAudio(data.audio, data.audio_type);
    } catch (err) {
      if (!mountedRef.current || seq !== seqRef.current) return;
      if (handleAuthError(err)) return;
      setLoad((prev) => (prev.kind === "ready" ? prev : { kind: "error" }));
    } finally {
      if (mountedRef.current) setResponseTick((t) => t + 1);
    }
  }, [handleAuthError, playAudio]);

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
    seqRef.current++;
    setMessages((prev) => [...prev, ...turn.messages.map((m) => ({ sender: m.sender, text: m.text }))]);
    if (turn.language) setLanguage(turn.language);
    if (turn.call_number) setCallNumber(turn.call_number);
    setHelpNumber(turn.help_number);
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
    seqRef.current++;
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
        if (err instanceof ApiError) console.warn("Check-in text failed:", err.status, err.detail);
        setNotice(t.genericError);
      }
    } finally {
      if (mountedRef.current) setPhase("idle");
    }
  }

  async function submitVoice(blob: Blob) {
    if (blob.size === 0) {
      setNotice(t.heardNothing);
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
        console.warn("Voice unavailable:", err.detail);
        setNotice(t.voiceUnavailable);
        openTextInput();
      } else if (err instanceof ApiError && (err.status === 413 || err.status === 400)) {
        console.warn("Voice turn rejected:", err.status, err.detail);
        setNotice(t.genericError);
      } else {
        setNotice(t.genericError);
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
      setNotice(t.micBlocked);
      openTextInput();
      return;
    }
    // Left the page, or a recorder already exists: never keep a second mic stream open.
    if (!mountedRef.current || recorderRef.current) {
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    let rec: MediaRecorder;
    try {
      const mimeType = pickMimeType();
      rec = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      setNotice(t.voiceNotOnPhone);
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
      seqRef.current++;
      setPhase("sending");
      void submitVoice(blob);
    };
    try {
      rec.start();
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      recorderRef.current = null;
      setNotice(t.voiceNotOnPhone);
      openTextInput();
      return;
    }
    setPhase("recording");
    stopTimerRef.current = window.setTimeout(stopRecording, MAX_RECORD_MS);
  }

  function handleMic() {
    if (phase === "recording") {
      stopRecording();
      return;
    }
    if (phase !== "idle" || startingRef.current) return;
    startingRef.current = true;
    busyRef.current = true;
    void startRecording().finally(() => {
      startingRef.current = false;
      busyRef.current = recorderRef.current !== null;
    });
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
            {t.help}
          </button>
        )}
        <LogoutButton className="pc-logout" label={t.logOut} busyLabel={t.signingOut} />
      </div>
    </header>
  );

  if (load.kind !== "ready") {
    return (
      <div className="pc-page" lang={parentLangCode(language)}>
        {header}
        <main className="pc-main pc-main--center">
          {load.kind === "loading" && (
            <p className="pc-status" role="status">
              {t.gettingReady}
            </p>
          )}
          {load.kind === "unlinked" && (
            <div className="pc-card" role="alert">
              <h2>{t.almostThere}</h2>
              <p>{t.notLinked}</p>
              <p>{t.notLinkedHelp}</p>
              <LogoutButton label={t.logOut} busyLabel={t.signingOut} />
            </div>
          )}
          {load.kind === "forbidden" && (
            <div className="pc-card" role="alert">
              <h2>{t.parentsOnly}</h2>
              <p>
                <Link to="/start" className="pc-link">
                  {t.goToStart}
                </Link>
              </p>
            </div>
          )}
          {load.kind === "error" && (
            <div className="pc-card" role="alert">
              <h2>{t.loadFailedTitle}</h2>
              <p>{t.genericError}</p>
              <button
                type="button"
                className="pc-primary-btn"
                onClick={() => {
                  setLoad({ kind: "loading" });
                  void refresh();
                }}
              >
                {t.tryAgain}
              </button>
            </div>
          )}
        </main>
      </div>
    );
  }

  const statusText = phase === "recording" ? t.listening : phase === "sending" ? t.thinking : "";

  return (
    <div className="pc-page" lang={parentLangCode(language)}>
      {header}

      {helpOpen && (
        <section id="pc-help-panel" className="pc-help" aria-label={t.help}>
          {helpNumber ? (
            <a className="pc-call-btn" href={telHref(helpNumber)}>
              <span aria-hidden="true">📞</span> {t.callFamily}
              <span className="pc-call-number">{helpNumber}</span>
            </a>
          ) : (
            <p className="pc-help-text">{t.askFamilyAddPhone}</p>
          )}
        </section>
      )}

      {callNumber && !helpOpen && (
        <div className="pc-call-wrap">
          <a className="pc-call-btn" href={telHref(callNumber)}>
            <span aria-hidden="true">📞</span> {t.callFamily}
            <span className="pc-call-number">{callNumber}</span>
          </a>
        </div>
      )}

      <main className="pc-main">
        <ol className="pc-messages" lang={parentLangCode(language)} aria-live="polite" aria-label={t.conversation}>
          {messages.map((m, i) => (
            <li key={i} className={`pc-bubble pc-bubble--${m.sender}`}>
              <span className="pc-sr">{m.sender === "bot" ? t.botSays : t.youSaid}</span>
              {m.text}
              {m.sender === "bot" && (
                <ParentMedicinePhotos
                  text={m.text}
                  medicines={medicines}
                  photoUrls={photoUrls}
                  photoLabel={t.photoOf}
                  closeLabel={t.closePhoto}
                />
              )}
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
            aria-label={phase === "recording" ? t.stopAndSend : t.tapToSpeak}
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
            {phase === "recording" ? t.tapAgainToSend : phase === "sending" ? t.pleaseWait : t.tapToSpeak}
          </p>
        )}

        {showText ? (
          <form className="pc-text-form" onSubmit={handleSendText}>
            <label htmlFor="pc-text" className="pc-sr">
              {t.typeYourAnswer}
            </label>
            <input
              id="pc-text"
              ref={inputRef}
              className="pc-text-input"
              type="text"
              lang={parentLangCode(language)}
              value={text}
              maxLength={2000}
              autoComplete="off"
              placeholder={t.typeYourAnswer}
              onChange={(e) => setText(e.target.value)}
            />
            <button type="submit" className="pc-primary-btn" disabled={phase !== "idle" || !text.trim()}>
              {t.send}
            </button>
          </form>
        ) : (
          <button type="button" className="pc-type-btn" onClick={openTextInput}>
            {t.typeInstead}
          </button>
        )}
      </footer>
    </div>
  );
}
