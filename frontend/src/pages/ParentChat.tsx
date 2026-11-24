import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import "../parent-chat.css";
import { ApiError } from "../api";
import LogoutButton from "../components/LogoutButton";
import ParentAvatar from "../components/ParentAvatar";
import ParentMedicinePhotos from "../components/ParentMedicinePhotos";
import { PARENT_LANGUAGES, parentLangCode, parentStrings, type ParentLang } from "../parentChatStrings";
import {
  fetchParentMedicinePhoto,
  getCheckin,
  getParentMedicines,
  getParentProfiles,
  sendEmergency,
  sendText,
  sendVoice,
  setParentLanguage,
  setParentProfile,
  speakMessage,
  type ChatMessage,
  type CheckinOut,
  type EmergencyOut,
  type ParentMedicine,
  type ParentProfile,
  type ReminderDue,
  type TurnOut,
} from "../parentApi";

// The parent's check-in chat. Bot bubbles sit on the left (tap one to hear it), the parent's on the right.
// Typing is the default; the Voice switch at the top right adds the big mic. The Audio switch beside Send
// (on by default) reads each new bot message aloud.

const MAX_RECORD_MS = 15_000;
const VOICE_KEY = "carecircle.parentVoice";
const AUDIO_KEY = "carecircle.parentAudio";

function savedAudioOn(): boolean {
  try {
    return localStorage.getItem(AUDIO_KEY) !== "off";
  } catch {
    return true;
  }
}

/** The text for a voice to read: bullet points become a plain sentence. */
function spokenText(message: string): string {
  return message.replace(/([:?])\n• /g, "$1 ").replace(/\n• /g, ", ").replace(/\n/g, ". ");
}

/** The device's voice for a language. Browsers load the list late, so wait a moment for it. */
async function deviceVoice(code: string): Promise<SpeechSynthesisVoice | undefined> {
  const synth = window.speechSynthesis;
  if (!synth) return undefined;
  if (synth.getVoices().length === 0) {
    await new Promise<void>((resolve) => {
      synth.addEventListener("voiceschanged", () => resolve(), { once: true });
      window.setTimeout(resolve, 1500);
    });
  }
  const voices = synth.getVoices().filter((v) => v.lang.toLowerCase().split(/[-_]/)[0] === code);
  return voices.find((v) => /[-_]in$/i.test(v.lang)) ?? voices[0];
}

function savedVoiceOn(): boolean {
  try {
    return localStorage.getItem(VOICE_KEY) === "on";
  } catch {
    return false;
  }
}

type LoadState =
  | { kind: "loading" }
  | { kind: "choose" } // several profiles in this account: ask who is here
  | { kind: "ready" }
  | { kind: "unlinked" }
  | { kind: "forbidden" }
  | { kind: "error" };

type Phase = "idle" | "recording" | "sending";

interface Bubble {
  sender: "bot" | "parent";
  text: string;
  photos?: boolean;
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

// Shown if the emergency request fails before the server sends its number (dummy until a real one is set).
const DUMMY_EMERGENCY_NUMBER = "+91 00000 00000";

function telHref(number: string): string {
  return `tel:${number.replace(/[^\d+]/g, "")}`;
}

function reminderKey(r: ReminderDue): string {
  return `${r.medicine_id}|${r.slot}|${r.remind_at}`;
}

/** The Wispr Flow mark: five bars. */
function WisprFlowIcon() {
  return (
    <svg className="pc-wispr" viewBox="0 0 344 337" width="26" height="26" aria-hidden="true">
      <path
        d="M24.5 24.5v288M98.5 176v102M172.5 81v175M246 179v99M319.5 24.5v288"
        fill="none"
        stroke="currentColor"
        strokeWidth="49"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function ParentChat() {
  const navigate = useNavigate();
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [profiles, setProfiles] = useState<ParentProfile[]>([]);
  const [profile, setProfile] = useState<ParentProfile | null>(null);
  const [messages, setMessages] = useState<Bubble[]>([]);
  // "" until the first load: strings then follow the browser locale.
  const [language, setLanguage] = useState("");
  const [recommended, setRecommended] = useState("");
  const t = parentStrings(language);
  const [callNumber, setCallNumber] = useState<string | null>(null);
  const [helpNumber, setHelpNumber] = useState<string | null>(null);
  const [familyId, setFamilyId] = useState<string | null>(null);
  const [reminders, setReminders] = useState<ReminderDue[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [canUseVoice] = useState(voiceSupported);
  const [voiceOn, setVoiceOn] = useState(savedVoiceOn);
  // The Audio switch: read each new bot message aloud.
  const [audioOn, setAudioOn] = useState(savedAudioOn);
  const audioOnRef = useRef(audioOn);
  // Speech the browser refused to play before the first tap; that tap plays it.
  const blockedSpeechRef = useRef<(() => void) | null>(null);
  // How many messages are already on screen, so a refresh reads only the new ones.
  const shownCountRef = useRef(0);
  const useMic = canUseVoice && voiceOn;
  const [textOpen, setTextOpen] = useState(false);
  const showText = textOpen || !useMic;
  // The bubble being read aloud.
  const [playing, setPlaying] = useState<number | null>(null);
  // Bumped whenever playback stops, so speech that arrives late is not played.
  const playSeqRef = useRef(0);
  const [text, setText] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  // Help -> "Is this an emergency?" -> alert the family and show the number to call.
  const [emergency, setEmergency] = useState<"closed" | "ask" | "sending" | "done" | "failed">("closed");
  const [emergencyInfo, setEmergencyInfo] = useState<EmergencyOut | null>(null);
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
    playSeqRef.current++;
    blockedSpeechRef.current = null;
    setPlaying(null);
    window.speechSynthesis?.cancel();
    window.speechSynthesis?.getVoices(); // browsers load the voice list on the first ask
    const current = audioRef.current;
    if (!current) return;
    current.audio.pause();
    URL.revokeObjectURL(current.url);
    audioRef.current = null;
  }, []);

  const playAudio = useCallback(
    (base64: string | null, type: string | null, onEnd?: (failed: boolean, blocked?: boolean) => void) => {
      if (!base64) return;
      stopAudio();
      let url: string;
      try {
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        url = URL.createObjectURL(new Blob([bytes], { type: type || "audio/mpeg" }));
      } catch {
        onEnd?.(true);
        return; // Bad audio: the text is already on screen.
      }
      const audio = new Audio(url);
      const entry = { audio, url };
      audioRef.current = entry;
      const release = (failed: boolean, blocked = false) => {
        URL.revokeObjectURL(url);
        if (audioRef.current !== entry) return; // stopped, or replaced by newer audio
        audioRef.current = null;
        onEnd?.(failed, blocked);
      };
      audio.addEventListener("ended", () => release(false));
      audio.addEventListener("error", () => release(true));
      // Autoplay blocked or unsupported: the text is already shown.
      audio.play().catch((err) => release(true, err instanceof DOMException && err.name === "NotAllowedError"));
    },
    [stopAudio],
  );

  /** Reads a message in the device's own voice for the language, if it has one. */
  const speakOnDevice = useCallback(
    async (message: string, lang: string, onEnd: (failed: boolean, blocked?: boolean) => void) => {
      const seq = playSeqRef.current;
      const voice = await deviceVoice(parentLangCode(lang));
      if (seq !== playSeqRef.current) return;
      if (!voice) {
        onEnd(true);
        return;
      }
      const utterance = new SpeechSynthesisUtterance(spokenText(message));
      utterance.voice = voice;
      utterance.lang = voice.lang;
      utterance.rate = 0.9;
      utterance.onend = () => {
        if (seq === playSeqRef.current) onEnd(false);
      };
      utterance.onerror = (ev) => {
        if (seq === playSeqRef.current) onEnd(true, ev.error === "not-allowed");
      };
      window.speechSynthesis.speak(utterance);
    },
    [],
  );

  /** Reads new bot messages aloud when the Audio switch is on. The text is on screen, so failures stay quiet. */
  const speakNew = useCallback(
    (audio: string | null, type: string | null, texts: string[], lang: string) => {
      if (!audioOnRef.current || texts.length === 0) return;
      stopAudio();
      const start = () => {
        const onEnd = (_failed: boolean, blocked?: boolean) => {
          if (blocked && audioOnRef.current) blockedSpeechRef.current = start;
        };
        if (audio) playAudio(audio, type, onEnd);
        else void speakOnDevice(texts.join("\n"), lang, onEnd);
      };
      start();
    },
    [playAudio, speakOnDevice, stopAudio],
  );

  useEffect(() => {
    function onFirstTap(e: MouseEvent) {
      const start = blockedSpeechRef.current;
      if (!start) return;
      blockedSpeechRef.current = null;
      // A tap on a control does that control's job instead.
      if (e.target instanceof Element && e.target.closest("button, a, select")) return;
      start();
    }
    document.addEventListener("click", onFirstTap);
    return () => document.removeEventListener("click", onFirstTap);
  }, []);

  /** Tap a bot message to hear it; tap it again to stop. */
  async function handleListen(index: number, message: string) {
    if (phase !== "idle" || startingRef.current) return;
    const wasPlaying = playing === index;
    stopAudio();
    if (wasPlaying) return;
    setNotice(null);
    setPlaying(index);
    const seq = playSeqRef.current;
    let speech: { audio: string | null; audio_type: string | null } = { audio: null, audio_type: null };
    try {
      speech = await speakMessage(message);
    } catch (err) {
      if (!mountedRef.current || handleAuthError(err)) return;
    }
    if (!mountedRef.current || seq !== playSeqRef.current) return;
    const finish = (failed: boolean) => {
      if (!mountedRef.current) return;
      setPlaying(null);
      if (failed) setNotice(t.cannotPlay);
    };
    if (speech.audio) {
      let ended = false;
      playAudio(speech.audio, speech.audio_type, (failed) => {
        ended = true;
        finish(failed);
      });
      if (!ended) setPlaying(index); // starting playback cleared the mark
      return;
    }
    // No server voice: use the device's own voice.
    void speakOnDevice(message, language, finish);
  }

  function toggleVoice() {
    if (phase !== "idle" || startingRef.current) return;
    stopAudio();
    setNotice(null);
    const on = !voiceOn;
    setVoiceOn(on);
    setTextOpen(false);
    try {
      localStorage.setItem(VOICE_KEY, on ? "on" : "off");
    } catch {
      // Not remembered; still applies until the page closes.
    }
  }

  function toggleAudio() {
    stopAudio();
    const on = !audioOn;
    audioOnRef.current = on;
    setAudioOn(on);
    try {
      localStorage.setItem(AUDIO_KEY, on ? "on" : "off");
    } catch {
      // Not remembered; still applies until the page closes.
    }
  }

  // ---------- medicine photos ----------
  // A bot message that names a medicine shows its photo underneath. Checked again after every bot
  // reply, so a photo the family has just added appears; each photo is downloaded once.

  const [medicines, setMedicines] = useState<ParentMedicine[]>([]);
  const [photoUrls, setPhotoUrls] = useState<Record<string, string>>({});
  const loadedPhotosRef = useRef(new Map<string, string>());
  const botCount = messages.filter((m) => m.sender === "bot").length;
  const profileId = profile?.id ?? null;

  useEffect(() => {
    if (!profileId) return;
    let cancelled = false;
    (async () => {
      try {
        const meds = await getParentMedicines();
        if (cancelled) return;
        setMedicines(meds);
        for (const med of meds) {
          if (!med.has_image || loadedPhotosRef.current.has(med.id)) continue;
          const url = await fetchParentMedicinePhoto(med.id);
          if (!url) continue;
          if (cancelled) {
            URL.revokeObjectURL(url);
            return;
          }
          loadedPhotosRef.current.set(med.id, url);
          setPhotoUrls((prev) => ({ ...prev, [med.id]: url }));
        }
      } catch {
        // Photos are a help, not essential: the chat works without them.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [botCount, profileId]);

  useEffect(() => {
    const loaded = loadedPhotosRef.current;
    return () => {
      loaded.forEach((u) => URL.revokeObjectURL(u));
      loaded.clear();
    };
  }, []);

  // ---------- emergency ----------

  async function handleEmergencyYes() {
    setEmergency("sending");
    try {
      const info = await sendEmergency();
      if (!mountedRef.current) return;
      setEmergencyInfo(info);
      setEmergency("done");
      void refresh(); // shows the alert note in the chat and the red Call button
    } catch (err) {
      if (!mountedRef.current) return;
      if (handleAuthError(err)) return;
      setEmergency("failed");
    }
  }

  function handleEmergencyNo() {
    setEmergency("closed");
    setHelpOpen(true);
  }

  // ---------- loading the conversation ----------

  const showCheckin = useCallback(
    (data: CheckinOut, fresh: boolean) => {
      setMessages(data.messages.map((m: ChatMessage) => ({ sender: m.sender, text: m.text, photos: m.photos })));
      setLanguage(data.language || "");
      setRecommended(data.recommended_language || "");
      setCallNumber(data.call_number);
      setHelpNumber(data.help_number);
      setFamilyId(data.can_open_portal && data.family_id ? data.family_id : null);
      setReminders(data.reminders_due);
      setLoad({ kind: "ready" });
      // Reads the greeting or a newly asked question, never what is already on screen.
      const added = fresh ? data.messages : data.messages.slice(shownCountRef.current);
      const texts = added.filter((m) => m.sender === "bot").map((m) => m.text);
      speakNew(data.audio, data.audio_type, texts, data.language || "");
    },
    [speakNew],
  );

  const refresh = useCallback(async (newSession = false) => {
    const seq = ++seqRef.current;
    try {
      const data = await getCheckin(newSession, audioOnRef.current);
      // Ignore a snapshot that a newer turn or refresh has overtaken.
      if (!mountedRef.current || seq !== seqRef.current) return;
      showCheckin(data, newSession);
    } catch (err) {
      if (!mountedRef.current || seq !== seqRef.current) return;
      if (handleAuthError(err)) return;
      setLoad((prev) => (prev.kind === "ready" ? prev : { kind: "error" }));
    } finally {
      if (mountedRef.current) setResponseTick((t) => t + 1);
    }
  }, [handleAuthError, showCheckin]);

  /** Starts a new conversation on screen for this profile; everything said is saved to it. */
  const startWith = useCallback(
    (p: ParentProfile | null) => {
      setParentProfile(p?.id ?? null);
      setProfile(p);
      setMessages([]);
      setMedicines([]);
      setReminders([]);
      firedRef.current.clear();
      shownCountRef.current = 0;
      setCallNumber(null);
      setHelpNumber(null);
      setHelpOpen(false);
      setEmergency("closed");
      setEmergencyInfo(null);
      setNotice(null);
      setText("");
      setLoad({ kind: "loading" });
      void refresh(true);
    },
    [refresh],
  );

  const open = useCallback(async () => {
    const seq = ++seqRef.current;
    setParentProfile(null);
    setLoad({ kind: "loading" });
    try {
      const list = await getParentProfiles();
      if (!mountedRef.current || seq !== seqRef.current) return;
      setProfiles(list);
      if (list.length > 1) setLoad({ kind: "choose" });
      else startWith(list[0] ?? null);
    } catch (err) {
      if (!mountedRef.current || seq !== seqRef.current) return;
      if (!handleAuthError(err)) setLoad({ kind: "error" });
    }
  }, [handleAuthError, startWith]);

  /** Back to "Who is using CareCircle right now?". */
  function switchProfile() {
    if (phase !== "idle" || startingRef.current) return;
    stopAudio();
    seqRef.current++; // a refresh still on its way is ignored
    setProfile(null);
    setParentProfile(null);
    setLoad({ kind: "choose" });
  }

  useEffect(() => {
    mountedRef.current = true;
    // Every opening (or reload) of the chat starts a new conversation on screen.
    void open();
    return () => {
      mountedRef.current = false;
    };
  }, [open]);

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
    shownCountRef.current = messages.length;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "end" });
  }, [messages, phase]);

  // ---------- a turn (text or voice) ----------

  function applyTurn(turn: TurnOut) {
    seqRef.current++;
    setMessages((prev) => [...prev, ...turn.messages.map((m) => ({ sender: m.sender, text: m.text, photos: m.photos }))]);
    if (turn.language) setLanguage(turn.language);
    if (turn.call_number) setCallNumber(turn.call_number);
    setHelpNumber(turn.help_number);
    const texts = turn.messages.filter((m) => m.sender === "bot").map((m) => m.text);
    speakNew(turn.audio, turn.audio_type, texts, turn.language || language);
    setResponseTick((t) => t + 1);
  }

  async function handleLanguage(code: string) {
    if (phase !== "idle" || startingRef.current || code === parentLangCode(language)) return;
    stopAudio();
    setNotice(null);
    seqRef.current++;
    setPhase("sending");
    try {
      const data = await setParentLanguage(code, audioOn);
      if (!mountedRef.current) return;
      seqRef.current++;
      showCheckin(data, true);
      setResponseTick((n) => n + 1);
    } catch (err) {
      if (!mountedRef.current) return;
      if (!handleAuthError(err)) setNotice(t.genericError);
    } finally {
      if (mountedRef.current) setPhase("idle");
    }
  }

  function openTextInput() {
    setTextOpen(true);
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
      const turn = await sendText(value, audioOn);
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

  // English and the recommended language. When that is English too, every language is offered.
  const recommendedCode = parentLangCode(recommended || language);
  const languageCodes = [
    ...new Set([
      recommendedCode,
      "en",
      ...(recommendedCode === "en" ? Object.keys(PARENT_LANGUAGES) : [parentLangCode(language)]),
    ]),
  ] as ParentLang[];

  const hour = new Date().getHours();
  const greeting = hour < 12 ? t.goodMorning : hour < 17 ? t.goodAfternoon : t.goodEvening;

  const header = (
    <header className="pc-header">
      <h1 className="pc-brand">
        <img src="/carecircle-mark.png" alt="" className="pc-brand-img" width="34" height="34" />
        CareCircle
      </h1>
      {load.kind === "ready" && (
        <label className="pc-lang">
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
            <path
              d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.5 3.8 5.6 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.6-3.8-9S9.5 5.5 12 3z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
            />
          </svg>
          <span className="pc-sr">{t.language}</span>
          <select
            value={parentLangCode(language)}
            disabled={phase !== "idle"}
            onChange={(e) => void handleLanguage(e.target.value)}
          >
            {languageCodes.map((code) => (
              <option key={code} value={code} lang={code}>
                {PARENT_LANGUAGES[code]}
                {code === recommended ? ` (${t.recommended})` : ""}
              </option>
            ))}
          </select>
        </label>
      )}
      {load.kind === "ready" && (
        <button
          type="button"
          role="switch"
          aria-checked={voiceOn}
          className="pc-voice"
          onClick={toggleVoice}
          disabled={phase !== "idle"}
          title={t.voice}
        >
          <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
            <path
              d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="pc-voice-track" aria-hidden="true" />
          <span className="pc-sr">{t.voice}</span>
        </button>
      )}
      <div className="pc-header-actions">
        {load.kind === "ready" && familyId && (
          <Link to={`/family/${familyId}`} className="pc-portal-btn">
            {t.moveToPortal}
          </Link>
        )}
        {load.kind === "ready" && (
          <button
            type="button"
            className="pc-help-btn"
            aria-expanded={helpOpen}
            aria-controls="pc-help-panel"
            onClick={() => (helpOpen ? setHelpOpen(false) : setEmergency("ask"))}
          >
            {t.help}
          </button>
        )}
        <LogoutButton className="pc-logout" label={t.logOut} busyLabel={t.signingOut} />
      </div>
      {load.kind === "ready" && profile && (
        <div className="pc-profile">
          <ParentAvatar profile={profile} />
          <span className="pc-profile-name">{profile.name}</span>
          {profiles.length > 1 && (
            <button type="button" className="pc-switch" onClick={switchProfile} disabled={phase !== "idle"}>
              {t.switchProfile}
            </button>
          )}
        </div>
      )}
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
          {load.kind === "choose" && (
            <div className="pc-card pc-who">
              <p className="pc-who-greeting">{greeting}</p>
              <h2>{t.whoIsUsing}</h2>
              <ul className="pc-who-list">
                {profiles.map((p) => (
                  <li key={p.id}>
                    <button type="button" className="pc-who-btn" onClick={() => startWith(p)}>
                      <ParentAvatar profile={p} large />
                      <span className="pc-who-name">{p.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
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
                onClick={() => void open()}
              >
                {t.tryAgain}
              </button>
            </div>
          )}
        </main>
      </div>
    );
  }

  const audioSwitch = (
    <button
      type="button"
      role="switch"
      aria-checked={audioOn}
      className="pc-voice pc-audio"
      onClick={toggleAudio}
      title={t.audio}
    >
      <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
        <path
          d={`M4 9.5v5h3.5l4.5 4v-13l-4.5 4z${audioOn ? "M15.5 9a4 4 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11" : "M16 9.5l5 5M21 9.5l-5 5"}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="pc-voice-track" aria-hidden="true" />
      <span className="pc-sr">{t.audio}</span>
    </button>
  );

  const statusText = phase === "recording" ? t.listening : phase === "sending" ? t.thinking : "";

  return (
    <div className="pc-page" lang={parentLangCode(language)}>
      {header}

      {emergency !== "closed" && (
        <div className="pc-emergency-backdrop">
          <div
            className="pc-emergency"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="pc-emergency-title"
            lang={parentLangCode(language)}
          >
            {emergency === "ask" && (
              <>
                <h2 id="pc-emergency-title" className="pc-emergency-title">{t.emergencyQuestion}</h2>
                <button type="button" className="pc-emergency-yes" onClick={handleEmergencyYes} autoFocus>
                  {t.emergencyYes}
                </button>
                <button type="button" className="pc-emergency-no" onClick={handleEmergencyNo}>
                  {t.emergencyNo}
                </button>
              </>
            )}
            {emergency === "sending" && (
              <h2 id="pc-emergency-title" className="pc-emergency-title" role="status">{t.emergencySending}</h2>
            )}
            {(emergency === "done" || emergency === "failed") && (
              <>
                <h2 id="pc-emergency-title" className="pc-emergency-title">
                  {emergency === "done" ? t.emergencyNotified : t.emergencyFailed}
                </h2>
                <a
                  className="pc-call-btn pc-emergency-call"
                  href={telHref(emergencyInfo?.emergency_number ?? DUMMY_EMERGENCY_NUMBER)}
                >
                  <span aria-hidden="true">📞</span> {t.emergencyCall}
                  <span className="pc-call-number">
                    {emergencyInfo?.emergency_number ?? DUMMY_EMERGENCY_NUMBER}
                  </span>
                </a>
                <button type="button" className="pc-emergency-no" onClick={() => setEmergency("closed")}>
                  {t.closePhoto}
                </button>
              </>
            )}
          </div>
        </div>
      )}

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
              {m.sender === "bot" ? (
                <button
                  type="button"
                  className={`pc-listen${playing === i ? " is-playing" : ""}`}
                  aria-pressed={playing === i}
                  title={t.tapToListen}
                  onClick={() => void handleListen(i, m.text)}
                >
                  <span className="pc-listen-text">{m.text}</span>
                  <span className="pc-play" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
                      <path d={playing === i ? "M7 6h10a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z" : "M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z"} />
                    </svg>
                  </span>
                </button>
              ) : (
                m.text
              )}
              {m.sender === "bot" && m.photos && (
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

        {useMic && (
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
        {useMic && (
          <p className="pc-mic-hint" aria-hidden="true">
            {phase === "recording" ? t.tapAgainToSend : phase === "sending" ? t.pleaseWait : t.tapToSpeak}
          </p>
        )}

        {showText ? (
          <form className="pc-text-form" onSubmit={handleSendText}>
            <label htmlFor="pc-text" className="pc-sr">
              {t.typeYourAnswer}
            </label>
            <div className="pc-text-wrap">
              <WisprFlowIcon />
              <input
                id="pc-text"
                ref={inputRef}
                className="pc-text-input"
                type="text"
                lang={parentLangCode(language)}
                value={text}
                maxLength={2000}
                autoComplete="off"
                onChange={(e) => setText(e.target.value)}
              />
              {/* Not a placeholder: this line is long and has to wrap on a phone. */}
              {!text && (
                <span className="pc-text-hint" aria-hidden="true">
                  {t.typeYourAnswer}
                </span>
              )}
            </div>
            {audioSwitch}
            <button type="submit" className="pc-primary-btn" disabled={phase !== "idle" || !text.trim()}>
              {t.send}
            </button>
          </form>
        ) : (
          <div className="pc-type-row">
            <button type="button" className="pc-type-btn" onClick={openTextInput}>
              {t.typeInstead}
            </button>
            {audioSwitch}
          </div>
        )}
      </footer>
    </div>
  );
}
