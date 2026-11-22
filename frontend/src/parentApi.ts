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
// `audio` is base64 (audio_type, usually audio/mpeg) or null when speech is unavailable.

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
  call_number: string | null;
  language: string;
  reminders_due: ReminderDue[];
}

export interface TurnOut {
  messages: { sender: "bot" | "parent"; text: string }[];
  step: string;
  urgent: boolean;
  call_number: string | null;
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

export function getCheckin(): Promise<CheckinOut> {
  return send<CheckinOut>("/api/parent/checkin", { method: "GET" });
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
