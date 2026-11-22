import { API_BASE_URL, ApiError, getSessionToken } from "./api";

// Parent voice check-in, under /api/parent (backend/app/api/parent.py):
//
//   GET  /checkin        -> CheckinOut: today's full stored conversation. Greets once per day;
//                           a reload adds messages only when a medicine question became due.
//   POST /checkin/text   {"text": "..."} -> TurnOut: only this turn's bot replies.
//   POST /checkin/voice  multipart field "file" (<= 2 MB) -> VoiceTurnOut (TurnOut + transcript).
//                        413 too large, 400 empty, 503 when speech-to-text fails.
//
// Errors: 401 signed out, 403 not a parent, 409 parent not linked to a profile.
// `audio` is base64 (audio_type, usually audio/mpeg) or null when speech is unavailable / nothing new.
// `call_number` is urgent-only; `help_number` is always the family's phone (or null if none).

export interface ChatMessage {
  sender: "bot" | "parent";
  text: string;
  created_at?: string;
}

export interface ReminderDue {
  medicine_id: string;
  name: string;
  slot: string;
  remind_at: string;
}

export interface CheckinOut {
  checkin_id: string;
  step: string;
  messages: ChatMessage[];
  /** Set only once something urgent was reported today (drives the red Call button). */
  call_number: string | null;
  /** The family's phone for the Help button, urgent or not. */
  help_number: string | null;
  language: string;
  reminders_due: ReminderDue[];
  /** Speech for the bot messages this request added (greeting / re-asked question), else null. */
  audio: string | null;
  audio_type: string | null;
}

export interface TurnOut {
  messages: { sender: "bot" | "parent"; text: string }[];
  step: string;
  /** The parent's current language: it can change mid-conversation from the Edit parent page. */
  language?: string;
  urgent: boolean;
  call_number: string | null;
  help_number: string | null;
  audio: string | null;
  audio_type: string | null;
  transcript?: string;
}

export const MAX_VOICE_BYTES = 2 * 1024 * 1024;

function authHeaders(): Record<string, string> {
  const token = getSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Mirrors api.ts: FastAPI errors carry {"detail": ...}.
async function send<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...authHeaders(), ...(init.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText || "Request failed";
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (data && data.detail !== undefined) {
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // Body was not JSON; keep statusText.
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** newSession: the chat page just opened, so start a new conversation on screen (fresh greeting). */
export function getCheckin(newSession = false): Promise<CheckinOut> {
  return send<CheckinOut>(`/api/parent/checkin${newSession ? "?new_session=true" : ""}`, { method: "GET" });
}

export function sendText(text: string): Promise<TurnOut> {
  return send<TurnOut>("/api/parent/checkin/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

function extensionFor(type: string): string {
  if (type.includes("webm")) return "webm";
  if (type.includes("ogg")) return "ogg";
  if (type.includes("mp4") || type.includes("m4a") || type.includes("aac")) return "m4a";
  if (type.includes("mpeg")) return "mp3";
  if (type.includes("wav")) return "wav";
  return "webm";
}

export function sendVoice(blob: Blob): Promise<TurnOut> {
  const form = new FormData();
  form.append("file", blob, `voice.${extensionFor(blob.type)}`);
  // No Content-Type header: the browser sets the multipart boundary.
  return send<TurnOut>("/api/parent/checkin/voice", { method: "POST", body: form });
}


// The parent's own medicines, for showing a photo next to a medicine the bot names.
//   GET /medicines                 -> [{id, name, has_image}] (active medicines only)
//   GET /medicines/{id}/image      -> the photo bytes, 404 when there is none

export interface ParentMedicine {
  id: string;
  name: string;
  has_image: boolean;
}

export function getParentMedicines(): Promise<ParentMedicine[]> {
  return send<ParentMedicine[]>("/api/parent/medicines", { method: "GET" });
}

/** The medicine photo as a blob: URL (the request needs the Bearer token), or null if there is none. */
export async function fetchParentMedicinePhoto(medicineId: string): Promise<string | null> {
  const res = await fetch(`${API_BASE_URL}/api/parent/medicines/${encodeURIComponent(medicineId)}/image`, {
    headers: authHeaders(),
  });
  if (!res.ok) return null;
  return URL.createObjectURL(await res.blob());
}


// Help -> "Yes, it's an emergency": alerts the whole family now.
//   POST /emergency -> {notified: [names], channels: [...], emergency_number}
export interface EmergencyOut {
  notified: string[];
  channels: string[];
  emergency_number: string;
}

export function sendEmergency(): Promise<EmergencyOut> {
  return send<EmergencyOut>("/api/parent/emergency", { method: "POST" });
}
