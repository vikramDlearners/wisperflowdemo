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

// ---------- The daily "I'm fine" button (backend/app/api/parent.py) ----------
//   GET  /api/parent/fine  -> FineOut (today's state)
//   POST /api/parent/fine  -> FineOut (tells the family all is well, once a day)

export interface FineOut {
  day: string;
  fine_at: string | null;
  /** The app asked the parent at 11:00 because the button was not pressed yet. */
  asked: boolean;
  family_told: boolean;
}

export function getFine(): Promise<FineOut> {
  return send<FineOut>("/api/parent/fine", { method: "GET" });
}

export function sendFine(): Promise<FineOut> {
  return send<FineOut>("/api/parent/fine", { method: "POST" });
}

// ---------- Parent notes (backend/app/api/parent_notes.py) ----------
//   GET    /api/parent/notes          -> ParentNote[] (newest first)
//   POST   /api/parent/notes          {text, remind_at?, remind_user_id?, send_reminder?} -> ParentNote
//   DELETE /api/parent/notes/{id}     -> 204
//   GET    /api/parent/notes/people   -> NotePerson[] (family members a note can go to)
// A note for someone else becomes their task; send_reminder also messages them at remind_at (or now).

export interface ParentNote {
  id: string;
  text: string;
  remind_at: string | null;
  /** null = the parent themselves */
  remind_user_id: string | null;
  remind_user_name: string | null;
  send_reminder: boolean;
  task_id: string | null;
  /** The reminder has gone out (or there was none to send). */
  reminded: boolean;
  created_at: string;
}

export interface NotePerson {
  user_id: string;
  display_name: string;
  relationship: string | null;
}

export interface ParentNoteIn {
  text: string;
  remind_at?: string | null;
  remind_user_id?: string | null;
  send_reminder?: boolean;
}

export function getParentNotes(): Promise<ParentNote[]> {
  return send<ParentNote[]>("/api/parent/notes", { method: "GET" });
}

export function getNotePeople(): Promise<NotePerson[]> {
  return send<NotePerson[]>("/api/parent/notes/people", { method: "GET" });
}

export function createParentNote(body: ParentNoteIn): Promise<ParentNote> {
  return send<ParentNote>("/api/parent/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function deleteParentNote(id: string): Promise<void> {
  // 204 has no body, so this does not go through send() (which parses JSON).
  const res = await fetch(`${API_BASE_URL}/api/parent/notes/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: { Accept: "application/json", ...authHeaders() },
  });
  if (!res.ok && res.status !== 404) throw new ApiError(res.status, res.statusText || "Request failed");
}

// ---------- Today's plan and refills (backend/app/api/parent.py, app/services/today_plan.py) ----------
//   GET  /api/parent/today               -> TodayPlanOut
//   POST /api/parent/refills/{medicine}  -> RefillOut (makes one task for the family; repeat-safe)

export interface RefillOut {
  medicine_id: string;
  name: string;
  left: number | null;
  refill_date: string | null;
  ask_name: string | null;
  asked: boolean;
}

export interface VisitPoint {
  kind: "bp_high" | "sugar_high" | "missed" | "said" | "allergy";
  count: number;
  value: string | null;
}

export interface TodayPlanOut {
  day: string;
  doses: { medicine_id: string; name: string; time: string; status: string }[];
  visits: { id: string; day: string; time: string; provider: string; reason: string; location: string | null }[];
  tasks: string[];
  refills: RefillOut[];
  visit_points: VisitPoint[];
  birthdays: { name: string; phone: string | null; today: boolean }[];
}

export function getToday(): Promise<TodayPlanOut> {
  return send<TodayPlanOut>("/api/parent/today", { method: "GET" });
}

export function askRefill(medicineId: string): Promise<RefillOut> {
  return send<RefillOut>(`/api/parent/refills/${medicineId}`, { method: "POST" });
}

// ---------- The parent's circle (backend/app/api/care_circle.py) ----------

export type HelpKind = "bill" | "groceries" | "cab" | "nurse" | "physio" | "other";

export interface HelpOut {
  id: string;
  care_profile_id: string;
  kind: HelpKind;
  note: string | null;
  status: "asked" | "approved" | "declined" | "done";
  task_id: string | null;
  amount: number | null;
  created_at: string;
  decided_at: string | null;
}

export interface PostOut {
  id: string;
  kind: "text" | "photo" | "voice";
  text: string | null;
  author: string | null;
  created_at: string;
  seen_at: string | null;
  media_url: string | null;
}

export interface CirclePerson {
  name: string;
  role: string;
  phone: string;
}

export interface CardOut {
  name: string;
  blood_group: string | null;
  allergies: string | null;
  medicines: string[];
  doctor: string | null;
  doctor_phone: string | null;
  hospital: string | null;
  emergency_name: string | null;
  emergency_phone: string | null;
  notes: string | null;
  emergency_contact: { name: string; phone: string } | null;
  insurance: { insurer: string; policy_number: string | null; helpline: string | null } | null;
}

export interface PrivacyOut {
  share_words: boolean;
  share_chats: boolean;
  video_auto_answer: boolean;
}

export interface NudgeOut {
  kind: "birthday" | "call" | "walk";
  name: string | null;
  phone: string | null;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const askHelp = (kind: HelpKind, note: string | null) => send<HelpOut>("/api/parent/help", json({ kind, note }));
export const getMyHelp = () => send<HelpOut[]>("/api/parent/help", { method: "GET" });
export const getPosts = () => send<PostOut[]>("/api/parent/posts", { method: "GET" });
export const getCircle = () => send<CirclePerson[]>("/api/parent/circle", { method: "GET" });
export const getCard = () => send<CardOut>("/api/parent/card", { method: "GET" });
export const getPrivacy = () => send<PrivacyOut>("/api/parent/privacy", { method: "GET" });
export const setPrivacy = (values: Partial<PrivacyOut>) =>
  send<PrivacyOut>("/api/parent/privacy", { ...json(values), method: "PUT" });
export const getNudge = () => send<NudgeOut>("/api/parent/nudge", { method: "GET" });

// Photos and voice notes need the auth header, so they load as blob URLs.
export async function fetchPostMedia(url: string): Promise<string | null> {
  const res = await fetch(`${API_BASE_URL}${url}`, { headers: authHeaders() });
  return res.ok ? URL.createObjectURL(await res.blob()) : null;
}

// Video check-ins: a family member rings, the parent's app asks every few seconds whether a call is ringing.
export interface IncomingCall {
  id: string;
  caller: string;
  offer: string;
  auto_answer: boolean;
}
export interface ParentCallOut {
  id: string;
  status: "ringing" | "live" | "ended";
  answer: string | null;
}
export const getIncomingCall = () => send<IncomingCall | null>("/api/parent/calls/incoming", { method: "GET" });
export const getParentCall = (id: string) => send<ParentCallOut>(`/api/parent/calls/${id}`, { method: "GET" });
export const answerCall = (id: string, sdp: string) =>
  send<ParentCallOut>(`/api/parent/calls/${id}/answer`, json({ sdp }));
export const endParentCall = (id: string) => send<ParentCallOut>(`/api/parent/calls/${id}/end`, json({}));
