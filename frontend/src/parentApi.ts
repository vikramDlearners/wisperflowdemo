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
  /** Show the photos of the medicines this message names. */
  photos?: boolean;
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
  /** The parent's family: "Move to Portal" opens its Overview page. */
  family_id: string;
  /** False when the parent's role can't view the Overview page: the link is then hidden. */
  can_open_portal?: boolean;
  step: string;
  messages: ChatMessage[];
  /** Set only once something urgent was reported today (drives the red Call button). */
  call_number: string | null;
  /** The family's phone for the Help button, urgent or not. */
  help_number: string | null;
  language: string;
  /** The language on the parent's profile, kept when the parent switches the chat to another one. */
  recommended_language: string;
  reminders_due: ReminderDue[];
  /** Speech for the bot messages this request added (greeting / re-asked question), else null. */
  audio: string | null;
  audio_type: string | null;
}

export interface TurnOut {
  messages: { sender: "bot" | "parent"; text: string; photos?: boolean }[];
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

// The profile being used in the chat; sent with every call, so everything is saved to it. null = the account's own.
let careProfileId: string | null = null;

export function setParentProfile(id: string | null): void {
  careProfileId = id;
}

function authHeaders(): Record<string, string> {
  const token = getSessionToken();
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(careProfileId ? { "X-Care-Profile-Id": careProfileId } : {}),
  };
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

// The profiles this account can use the chat as (father, mother...).
//   GET /profiles             -> [{id, name, relationship, has_photo, photo_url, own}]
//   GET /profiles/{id}/photo  -> the uploaded picture's bytes
export interface ParentProfile {
  id: string;
  name: string;
  relationship: string | null;
  has_photo: boolean;
  photo_url: string | null;
  own: boolean;
}

export function getParentProfiles(): Promise<ParentProfile[]> {
  return send<ParentProfile[]>("/api/parent/profiles", { method: "GET" });
}

/** The profile picture as a blob: URL (the request needs the Bearer token), or null if there is none. */
export async function fetchParentProfilePhoto(id: string): Promise<string | null> {
  const res = await fetch(`${API_BASE_URL}/api/parent/profiles/${encodeURIComponent(id)}/photo`, {
    headers: authHeaders(),
  });
  if (!res.ok) return null;
  return URL.createObjectURL(await res.blob());
}

/** newSession: the chat page just opened, so start a new conversation on screen (fresh greeting). */
export function getCheckin(newSession: boolean, speak: boolean): Promise<CheckinOut> {
  return send<CheckinOut>(`/api/parent/checkin?new_session=${newSession}&speak=${speak}`, { method: "GET" });
}

/** Switch the chat's language: greets again and repeats the open question in it. */
export function setParentLanguage(language: string, speak: boolean): Promise<CheckinOut> {
  return send<CheckinOut>(`/api/parent/language?speak=${speak}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language }),
  });
}

/** Speech for a bot message on screen; audio is null when the server has no voice. */
export function speakMessage(text: string): Promise<{ audio: string | null; audio_type: string | null }> {
  return send("/api/parent/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

/** speak: false when voice is off in the chat, so the server makes no speech. */
export function sendText(text: string, speak: boolean): Promise<TurnOut> {
  return send<TurnOut>(`/api/parent/checkin/text?speak=${speak}`, {
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

// A photo of a medicine strip or box the parent is unsure about.
export function sendMedicinePhoto(file: File, speak: boolean): Promise<TurnOut> {
  const form = new FormData();
  form.append("file", file, file.name || "medicine.jpg");
  return send<TurnOut>(`/api/parent/checkin/medicine-photo?speak=${speak}`, { method: "POST", body: form });
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
