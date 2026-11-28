import type { CardOut, HelpOut, PostOut } from "./parentApi";
// Typed fetch client for the CareCircle API.
// Interfaces mirror backend/app/schemas.py. Routes are verified against the
// router files in backend/app/api/.

// Empty by default: requests stay same-origin and the Vite dev proxy forwards /api.
export const API_BASE_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

const TOKEN_KEY = "carecircle.session_token";

export function getSessionToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setSessionToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// ---- Types (from schemas.py) ----

export interface UserOut {
  id: string;
  email: string | null;
  display_name: string;
  role?: string | null;
  other_role?: string | null;
}

export interface SignInRequest {
  email: string;
  display_name?: string | null;
}

export interface VerifyRequest {
  token: string;
}

export interface ParentInviteAccept {
  token: string;
}

export interface InviteOut {
  detail: string;
  invite_link?: string;
}

export interface SessionOut {
  session_token: string;
  user: UserOut;
}

export interface FamilyCreate {
  name: string;
}

export interface FamilyOut {
  id: string;
  name: string;
}

export interface MemberOut {
  membership_id: string;
  user_id: string;
  display_name: string;
  email: string | null;
  role_id: string;
  role_name: string;
  relationship: string | null;
}

export interface MemberCreate {
  /** An email, a mobile number, or both. */
  email?: string | null;
  phone?: string | null;
  display_name?: string | null;
  role_id: string;
  relationship?: string | null;
  /** Link the new member to this existing care profile instead of creating a new one. */
  care_profile_id?: string | null;
}

export interface MemberRoleChange {
  role_id: string;
}

export interface RoleOut {
  id: string;
  name: string;
  is_system: boolean;
  permissions: string[];
}

export interface RoleCreate {
  name: string;
  permissions: string[];
}

export interface RolePermissionsUpdate {
  permissions: string[];
}

export interface MyAccess {
  role: string;
  permissions: string[];
}

export interface CareProfileCreate {
  display_name: string;
  greeting_name: string;
  preferred_language?: string;
  timezone?: string;
}

export interface CareProfileUpdate {
  display_name?: string | null;
  greeting_name?: string | null;
  preferred_language?: string | null;
  timezone?: string | null;
}

export interface CareProfileOut {
  id: string;
  display_name: string;
  greeting_name: string;
  preferred_language: string;
  timezone: string;
}

export interface MedicineCreate {
  care_profile_id: string;
  display_name: string;
  instructions_text?: string | null;
  quantity_remaining?: number | null;
  refill_date?: string | null; // ISO date (YYYY-MM-DD)
  /** Last day of the course (YYYY-MM-DD); null means ongoing. */
  take_until?: string | null;
  responsible_user_id?: string | null;
  /** The appointment at which the doctor gave this medicine. */
  appointment_id?: string | null;
}

export interface MedicineUpdate {
  display_name?: string | null;
  instructions_text?: string | null;
  refill_date?: string | null;
  take_until?: string | null;
  responsible_user_id?: string | null;
  active?: boolean | null;
  // Pricing (edit only; the server computes total_price = unit_price x total_medicine_count).
  unit_price?: number | string | null;
  total_medicine_count?: number | null;
  /** The appointment at which the doctor gave this medicine. */
  appointment_id?: string | null;
}

export interface QuantityUpdate {
  quantity: number;
}

export interface MedicineOut {
  id: string;
  care_profile_id: string;
  display_name: string;
  instructions_text: string | null;
  quantity_remaining: number | null;
  refill_date: string | null;
  take_until?: string | null;
  responsible_user_id: string | null;
  active: boolean;
  /** Set when the medicine was confirmed from a prescription scan. */
  prescription_scan_id?: string | null;
  /** True when the medicine (or its linked prescription scan) has a photo. */
  has_image?: boolean;
  image_url?: string | null;
  // Decimals arrive as JSON strings (e.g. "12.50").
  unit_price?: string | number | null;
  total_medicine_count?: number | null;
  total_price?: string | number | null;
  /** True when a photo of the prescription is saved (GET .../prescription-image). */
  has_prescription_image?: boolean;
  /** The appointment at which the doctor gave this medicine. */
  appointment_id?: string | null;
}

/** Voice mode: what POST .../medicines/parse-text read from the spoken sentence. Unknown fields are null. */
export interface MedicineTextOut {
  instructions_text: string | null;
  reminder_times: string[]; // "HH:MM", 24-hour
  quantity_remaining: number | null;
  unit_price: string | number | null;
  total_medicine_count: number | null;
  source: "gemini" | "rules";
}

export interface TaskCreate {
  title: string;
  description?: string | null;
  due_at?: string | null; // ISO datetime
  priority?: string;
  assigned_to_user_id?: string | null;
  care_profile_id?: string | null;
}

export interface TaskAssign {
  assignee_user_id: string;
}

export interface TaskStatusUpdate {
  status: string;
}

export interface TaskUpdate {
  title?: string | null;
  description?: string | null;
  due_at?: string | null;
  priority?: string | null;
}

/** Voice mode: what POST .../tasks/parse-text read from the spoken task. Unknown fields are null. */
export interface TaskTextOut {
  title: string | null;
  description: string | null;
  due_date: string | null; // YYYY-MM-DD
  priority: "low" | "normal" | "high";
  assignee_user_id: string | null;
  assignee_name: string | null;
  source: "gemini" | "rules";
}

export interface TaskOut {
  id: string;
  title: string;
  description: string | null;
  due_at: string | null;
  status: string;
  priority: string;
  assigned_to_user_id: string | null;
  created_by_user_id: string;
}

export interface NotificationOut {
  id: string;
  family_id: string | null;
  type: string;
  payload: Record<string, unknown> | null;
  status: string;
  created_at: string;
}

export interface NotificationSummaryOut {
  summary: string | null;
  count: number;
  days: number;
  error: string | null;
}

export interface ActivityOut {
  id: string;
  actor_id: string | null;
  action: string;
  object_type: string;
  object_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

// Mirrors backend ConversationSummaryOut (GET /api/families/{family_id}/conversation-summaries).
export interface ConversationSummaryOut {
  id: string;
  checkin_id: string | null;
  care_profile_id: string | null;
  from_seq: number | null;
  to_seq: number | null;
  summary: string;
  important: unknown[] | null;
  source: string;
  created_at: string;
}

export interface IntentModeOut {
  intent_mode: string;
}

export interface IntentModeUpdate {
  intent_mode: string;
}

export interface SignUpRequest {
  email: string;
  display_name: string;
}

export interface LoginRequest {
  email: string;
}

export interface VerifyOtpRequest {
  email: string;
  code: string;
}

export type RoleChoice = "parent" | "caretaker" | "hospital" | "manager" | "others";

export interface SetRoleRequest {
  role: RoleChoice;
  other_role: string | null;
}

// ---- Core request helper ----

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getSessionToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  // FormData: let the browser set the multipart Content-Type with its boundary.
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
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

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T>(path: string) => request<T>("GET", path);
const post = <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {});
const put = <T>(path: string, body: unknown) => request<T>("PUT", path, body);
const patch = <T>(path: string, body: unknown) => request<T>("PATCH", path, body);
const del = <T = void>(path: string) => request<T>("DELETE", path);

// ---- auth (paths confirmed in api/auth.py) ----

export const auth = {
  requestLink: (body: SignInRequest) =>
    post<{ detail: string }>("/api/auth/request-link", body),
  verify: async (body: VerifyRequest): Promise<SessionOut> => {
    const session = await post<SessionOut>("/api/auth/verify", body);
    setSessionToken(session.session_token);
    return session;
  },
  me: () => get<UserOut>("/api/auth/me"),
  logout: async (): Promise<void> => {
    try {
      await post<void>("/api/auth/logout");
    } finally {
      setSessionToken(null);
    }
  },
};

// ---- email OTP auth (paths from backend api/auth.py) ----

export function signUp(email: string, displayName: string): Promise<unknown> {
  const body: SignUpRequest = { email, display_name: displayName.trim() };
  return post<unknown>("/api/auth/signup", body);
}

export function login(email: string): Promise<unknown> {
  const body: LoginRequest = { email };
  return post<unknown>("/api/auth/login", body);
}

export async function verifyOtp(email: string, code: string): Promise<SessionOut> {
  const body: VerifyOtpRequest = { email, code };
  const session = await post<SessionOut>("/api/auth/verify-otp", body);
  setSessionToken(session.session_token);
  return session;
}

export async function acceptParentInvite(token: string): Promise<SessionOut> {
  const body: ParentInviteAccept = { token };
  const session = await post<SessionOut>("/api/auth/accept-invite", body);
  setSessionToken(session.session_token);
  return session;
}

export function setRole(role: RoleChoice, otherRole: string | null): Promise<unknown> {
  const body: SetRoleRequest = { role, other_role: otherRole };
  return patch<unknown>("/api/auth/me/role", body);
}

// ---- families (verified against api/families.py) ----

export const families = {
  list: () => get<FamilyOut[]>("/api/families"),
  create: (body: FamilyCreate) => post<FamilyOut>("/api/families", body),
  get: (familyId: string) => get<FamilyOut>(`/api/families/${familyId}`),
  me: (familyId: string) => get<MyAccess>(`/api/families/${familyId}/me`),
  conversationSummaries: (familyId: string) =>
    get<ConversationSummaryOut[]>(`/api/families/${familyId}/conversation-summaries`),
};

// ---- members (verified against api/families.py) ----

export const members = {
  list: (familyId: string) => get<MemberOut[]>(`/api/families/${familyId}/members`),
  create: (familyId: string, body: MemberCreate) =>
    post<MemberOut>(`/api/families/${familyId}/members`, body),
  update: (familyId: string, membershipId: string, body: MemberRoleChange) =>
    patch<MemberOut>(`/api/families/${familyId}/members/${membershipId}`, body),
  invite: (familyId: string, membershipId: string) =>
    post<InviteOut>(`/api/families/${familyId}/members/${membershipId}/invite`),
  remove: (familyId: string, membershipId: string) =>
    del(`/api/families/${familyId}/members/${membershipId}`),
};

// ---- care profiles (verified against api/care_profiles.py) ----

export const careProfiles = {
  list: (familyId: string) => get<CareProfileOut[]>(`/api/families/${familyId}/care-profiles`),
  create: (familyId: string, body: CareProfileCreate) =>
    post<CareProfileOut>(`/api/families/${familyId}/care-profiles`, body),
  get: (familyId: string, profileId: string) =>
    get<CareProfileOut>(`/api/families/${familyId}/care-profiles/${profileId}`),
  update: (familyId: string, profileId: string, body: CareProfileUpdate) =>
    patch<CareProfileOut>(`/api/families/${familyId}/care-profiles/${profileId}`, body),
  delete: (familyId: string, profileId: string) =>
    del(`/api/families/${familyId}/care-profiles/${profileId}`),
};

// ---- medicines (verified against api/medicines.py) ----

export interface DoseToday {
  medicine_id: string;
  slot: string; // "HH:MM" or "any"
  status: "taken" | "not_taken" | "skipped" | "missed" | null;
  recorded_at: string | null;
}

export interface DoseRecord {
  care_profile_id: string;
  medicine_id: string;
  slot: string;
  status: "taken" | "skipped";
}

export interface MedicineLastTakenOut {
  medicine_id: string;
  last_taken_at: string | null;
}

export const medicines = {
  dosesToday: (familyId: string, careProfileId: string) =>
    get<DoseToday[]>(
      `/api/families/${familyId}/medicines/doses/today?care_profile_id=${encodeURIComponent(careProfileId)}`,
    ),
  recordDose: (familyId: string, body: DoseRecord) =>
    post<DoseToday>(`/api/families/${familyId}/medicines/doses`, body),
  list: (familyId: string) => get<MedicineOut[]>(`/api/families/${familyId}/medicines`),
  lastTaken: (familyId: string) =>
    get<MedicineLastTakenOut[]>(`/api/families/${familyId}/medicines/last-taken`),
  create: (familyId: string, body: MedicineCreate) =>
    post<MedicineOut>(`/api/families/${familyId}/medicines`, body),
  get: (familyId: string, medicineId: string) =>
    get<MedicineOut>(`/api/families/${familyId}/medicines/${medicineId}`),
  update: (familyId: string, medicineId: string, body: MedicineUpdate) =>
    patch<MedicineOut>(`/api/families/${familyId}/medicines/${medicineId}`, body),
  delete: (familyId: string, medicineId: string) =>
    del(`/api/families/${familyId}/medicines/${medicineId}`),
  updateQuantity: (familyId: string, medicineId: string, body: QuantityUpdate) =>
    patch<MedicineOut>(`/api/families/${familyId}/medicines/${medicineId}/quantity`, body),
  getReminders: (familyId: string, medicineId: string) =>
    get<{ times: string[] }>(`/api/families/${familyId}/medicines/${medicineId}/reminders`),
  setReminders: (familyId: string, medicineId: string, times: string[]) =>
    put<{ times: string[] }>(`/api/families/${familyId}/medicines/${medicineId}/reminders`, { times }),
  parseText: (familyId: string, text: string) =>
    post<MedicineTextOut>(`/api/families/${familyId}/medicines/parse-text`, { text }),
  remindParent: (familyId: string, careProfileId: string) =>
    post<RemindParentOut>(`/api/families/${familyId}/medicines/remind-parent`, { care_profile_id: careProfileId }),
};

/** What "Remind parent" sent: channels are "whatsapp", "sms" and "app"; sent_to is a masked phone number. */
export interface RemindParentOut {
  sent_at: string;
  channels: ("whatsapp" | "sms" | "app")[];
  sent_to: string | null;
  medicines: string[];
  message: string;
}

// ---- tasks (verified against api/tasks.py) ----

export const tasks = {
  list: (familyId: string) => get<TaskOut[]>(`/api/families/${familyId}/tasks`),
  create: (familyId: string, body: TaskCreate) =>
    post<TaskOut>(`/api/families/${familyId}/tasks`, body),
  get: (familyId: string, taskId: string) =>
    get<TaskOut>(`/api/families/${familyId}/tasks/${taskId}`),
  update: (familyId: string, taskId: string, body: TaskUpdate) =>
    patch<TaskOut>(`/api/families/${familyId}/tasks/${taskId}`, body),
  delete: (familyId: string, taskId: string) =>
    del(`/api/families/${familyId}/tasks/${taskId}`),
  assign: (familyId: string, taskId: string, body: TaskAssign) =>
    post<TaskOut>(`/api/families/${familyId}/tasks/${taskId}/assign`, body),
  parseText: (familyId: string, text: string, today: string) =>
    post<TaskTextOut>(`/api/families/${familyId}/tasks/parse-text`, { text, today }),
  complete: (familyId: string, taskId: string) =>
    post<TaskOut>(`/api/families/${familyId}/tasks/${taskId}/complete`),
  notify: (familyId: string, taskId: string) =>
    post<TaskOut>(`/api/families/${familyId}/tasks/${taskId}/notify`),
  updateStatus: (familyId: string, taskId: string, body: TaskStatusUpdate) =>
    patch<TaskOut>(`/api/families/${familyId}/tasks/${taskId}/status`, body),
};

// ---- shareable task links (verified against api/task_links.py) ----

export interface TaskShareLinkOut {
  token: string;
  path: string; // frontend route, e.g. /task-link/<token>
  expires_at: string;
}

export interface TaskLinkNoteOut {
  id: string;
  body: string;
  author_name: string | null;
  created_at: string;
}

export interface TaskLinkImageOut {
  id: string;
  url: string; // API path; prefix with API_BASE_URL
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface TaskLinkView {
  id: string;
  title: string;
  description: string | null;
  due_at: string | null;
  status: string;
  priority: string;
  assignee_name: string | null;
  link_expires_at: string;
  notes: TaskLinkNoteOut[];
  images: TaskLinkImageOut[];
}

export const taskLinks = {
  // Family side (signed in).
  share: (familyId: string, taskId: string) =>
    post<TaskShareLinkOut>(`/api/families/${familyId}/tasks/${taskId}/share-link`),
  revoke: (familyId: string, taskId: string) => del(`/api/families/${familyId}/tasks/${taskId}/share-link`),
  // Link side: the token is the only credential.
  view: (token: string) => get<TaskLinkView>(`/api/task-links/${encodeURIComponent(token)}`),
  complete: (token: string) => post<void>(`/api/task-links/${encodeURIComponent(token)}/complete`),
  addNote: (token: string, body: string, authorName: string | null) =>
    post<TaskLinkNoteOut>(`/api/task-links/${encodeURIComponent(token)}/notes`, {
      body,
      author_name: authorName,
    }),
  addImage: (token: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return post<TaskLinkImageOut>(`/api/task-links/${encodeURIComponent(token)}/images`, form);
  },
};

// ---- activity (verified against api/activity.py) ----

export const activity = {
  list: (familyId: string) => get<ActivityOut[]>(`/api/families/${familyId}/activity`),
};

// ---- roles (verified against api/roles.py) ----

export const roles = {
  list: (familyId: string) => get<RoleOut[]>(`/api/families/${familyId}/roles`),
  create: (familyId: string, body: RoleCreate) =>
    post<RoleOut>(`/api/families/${familyId}/roles`, body),
  updatePermissions: (familyId: string, roleId: string, body: RolePermissionsUpdate) =>
    put<RoleOut>(`/api/families/${familyId}/roles/${roleId}/permissions`, body),
};

// ---- settings: intent mode (verified against api/settings.py) ----

export const intentMode = {
  get: (familyId: string) => get<IntentModeOut>(`/api/families/${familyId}/settings/intent-mode`),
  put: (familyId: string, body: IntentModeUpdate) =>
    put<IntentModeOut>(`/api/families/${familyId}/settings/intent-mode`, body),
};

// ---- notifications (verified against api/notifications.py) ----

export const notifications = {
  list: () => get<NotificationOut[]>("/api/notifications"),
  summary: () => get<NotificationSummaryOut>("/api/notifications/summary"),
  markRead: (notificationId: string) =>
    post<NotificationOut>(`/api/notifications/${notificationId}/read`),
};

// ---- parent onboarding profile (backend GET/PATCH /api/auth/me/profile) ----

export type ProfileSection = "parent" | "communication" | "care" | "medical" | "additional";

export interface ProfileCompletion {
  overall: number;
  sections: Record<ProfileSection, number>;
}

export interface ParentProfileOut {
  /** A photo was uploaded from the device (see profilePhoto.ts). */
  has_photo?: boolean;
  parent_full_name: string | null;
  preferred_name: string | null;
  relationship: string | null;
  date_of_birth: string | null; // ISO date (YYYY-MM-DD)
  approximate_age: number | null;
  age: number | null;
  profile_picture_url: string | null;
  preferred_language: string | null;
  parent_mobile: string | null;
  known_health_conditions: string | null;
  allergies: string | null;
  primary_doctor_name: string | null;
  doctor_contact_number: string | null;
  preferred_hospital: string | null;
  care_instructions: string | null;
  deficiencies: string | null;
  notes: string | null;
  caregiver_name: string | null;
  caregiver_relationship: string | null;
  caregiver_phone: string | null;
  caregiver_email: string | null;
  completion: ProfileCompletion;
}

// Any subset of the editable profile fields. Empty values are sent as null.
export type ParentProfileFields = Partial<Omit<ParentProfileOut, "age" | "completion">>;

export function getProfile(): Promise<ParentProfileOut> {
  return get<ParentProfileOut>("/api/auth/me/profile");
}

export function saveProfileSection(
  section: ProfileSection,
  fields: ParentProfileFields,
): Promise<ParentProfileOut> {
  return patch<ParentProfileOut>("/api/auth/me/profile", { section, ...fields });
}

// A parent's profile as seen from the family workspace (any parent in the family, not just the signed-in user).
export function getFamilyParentProfile(familyId: string, careProfileId: string): Promise<ParentProfileOut> {
  return get<ParentProfileOut>(`/api/families/${familyId}/parents/${careProfileId}/profile`);
}

export function saveFamilyParentProfileSection(
  familyId: string,
  careProfileId: string,
  section: ProfileSection,
  fields: ParentProfileFields,
): Promise<ParentProfileOut> {
  return patch<ParentProfileOut>(`/api/families/${familyId}/parents/${careProfileId}/profile`, {
    section,
    ...fields,
  });
}

export function deleteFamilyParentProfile(familyId: string, careProfileId: string): Promise<void> {
  return del(`/api/families/${familyId}/parents/${careProfileId}/profile`);
}


// ---- prescription scans (verified against api/prescription_scans.py) ----

export interface PrescriptionMedicineIn {
  name: string;
  dose: string | null;
  instructions: string | null;
  times: string[]; // 24-hour "HH:MM"
  responsible_user_id?: string | null;
}

export interface PrescriptionScanOut {
  id: string;
  document_type: string; // 'prescription' | 'invoice' | 'other'
  status: string; // 'pending_review' | 'rejected' | 'confirmed'
  proposed: { medicines: PrescriptionMedicineIn[]; health_notes?: string[] } | null;
  /** What the app keeps track of from this upload: each medicine with its times, and health notes. */
  tracking?: string[];
}

export interface PrescriptionScanConfirm {
  medicines: PrescriptionMedicineIn[];
}

export interface PrescriptionScanConfirmOut {
  medicine_ids: string[];
  notified_user_ids: string[];
}

function prescriptionScanBase(familyId: string, careProfileId: string): string {
  return `/api/families/${familyId}/care-profiles/${careProfileId}/prescription-scans`;
}

export function uploadPrescriptionScan(
  familyId: string,
  careProfileId: string,
  file: File,
): Promise<PrescriptionScanOut> {
  const form = new FormData();
  form.append("file", file);
  return request<PrescriptionScanOut>("POST", prescriptionScanBase(familyId, careProfileId), form);
}

export function getPrescriptionScan(
  familyId: string,
  careProfileId: string,
  scanId: string,
): Promise<PrescriptionScanOut> {
  return get<PrescriptionScanOut>(`${prescriptionScanBase(familyId, careProfileId)}/${scanId}`);
}

export function confirmPrescriptionScan(
  familyId: string,
  careProfileId: string,
  scanId: string,
  body: PrescriptionScanConfirm,
): Promise<PrescriptionScanConfirmOut> {
  return post<PrescriptionScanConfirmOut>(
    `${prescriptionScanBase(familyId, careProfileId)}/${scanId}/confirm`,
    body,
  );
}


// ---- health notes (verified against api/health_notes.py) ----

export interface HealthNoteOut {
  id: string;
  kind: "allergy" | "condition" | "reading";
  /** Allergy: what to avoid. Condition: its name. Reading: bp, sugar, weight or pulse. */
  label: string;
  value: string | null;
  value_num: number | null;
  value_num2: number | null;
  /** One plain line, like "BP 140/90 mmHg" or "allergy to peanuts". */
  text: string;
  source: "chat" | "upload" | "family";
  source_text: string | null;
  recorded_at: string;
}

export interface HealthListOut {
  allergies: HealthNoteOut[];
  conditions: HealthNoteOut[];
  readings: HealthNoteOut[];
  known_allergies: string[];
  known_conditions: string[];
}

export interface HealthSavedOut {
  tracking: string[];
  notes: HealthNoteOut[];
}

export type ReadingKind = "bp" | "sugar" | "weight" | "pulse";

const healthBase = (familyId: string, careProfileId: string) =>
  `/api/families/${familyId}/care-profiles/${careProfileId}/health`;

export const health = {
  list: (familyId: string, careProfileId: string) => get<HealthListOut>(healthBase(familyId, careProfileId)),
  add: (familyId: string, careProfileId: string, body: { text: string } | { kind: ReadingKind; value: string }) =>
    post<HealthSavedOut>(healthBase(familyId, careProfileId), body),
  remove: (familyId: string, careProfileId: string, noteId: string) =>
    del(`${healthBase(familyId, careProfileId)}/${noteId}`),
  readings: (familyId: string, careProfileId: string, kind: ReadingKind, days = 90) =>
    get<HealthNoteOut[]>(`${healthBase(familyId, careProfileId)}/readings?kind=${kind}&days=${days}`),
};

// ---- appointments (verified against api/appointments.py) ----
// The family is not in the URL: list by care_recipient_id (a care profile id);
// get/update/delete look the family up from the appointment itself.

export type AppointmentStatus = "scheduled" | "completed" | "cancelled" | "rescheduled";

export interface AppointmentOut {
  id: string;
  care_recipient_id: string;
  scheduled_date: string; // YYYY-MM-DD
  start_time: string; // HH:MM
  provider: string;
  reason: string;
  location?: string | null;
  notes: string;
  status: AppointmentStatus;
  /** After the visit: the fee (a decimal string such as "500.00") and what the doctor said. */
  fee?: string | number | null;
  doctor_notes?: string | null;
  /** The family member responsible for the visit; told (with the managers) when it is completed. */
  responsible_user_id?: string | null;
  /** Medicines the doctor gave at this appointment. */
  medicines?: { id: string; display_name: string; active: boolean }[];
}

export interface AppointmentListOut {
  upcoming: AppointmentOut[]; // today or later, soonest first
  past: AppointmentOut[]; // before today, most recent first
}

export interface AppointmentCreate {
  family_id: string;
  care_recipient_id: string;
  scheduled_date: string;
  start_time: string;
  provider: string;
  reason: string;
  location?: string | null;
  notes?: string;
  fee?: number | null;
  doctor_notes?: string | null;
  responsible_user_id?: string | null;
}

/** Voice mode: what POST /api/appointments/parse-text read from the spoken appointment. Unknown fields are null. */
export interface AppointmentTextOut {
  care_recipient_id: string | null;
  care_recipient_name: string | null;
  reason: string | null;
  provider: string | null;
  location: string | null;
  scheduled_date: string | null; // YYYY-MM-DD
  start_time: string | null; // HH:MM
  notes: string | null;
  source: "gemini" | "rules";
}

export type AppointmentUpdate = Partial<Omit<AppointmentCreate, "family_id">> & {
  status?: AppointmentStatus;
};

export const appointments = {
  list: (careRecipientId: string) =>
    get<AppointmentListOut>(`/api/appointments?care_recipient_id=${encodeURIComponent(careRecipientId)}`),
  get: (appointmentId: string) => get<AppointmentOut>(`/api/appointments/${appointmentId}`),
  create: (body: AppointmentCreate) => post<AppointmentOut>("/api/appointments", body),
  update: (appointmentId: string, body: AppointmentUpdate) =>
    patch<AppointmentOut>(`/api/appointments/${appointmentId}`, body),
  remove: (appointmentId: string) => del(`/api/appointments/${appointmentId}`),
  parseText: (familyId: string, text: string, today: string) =>
    post<AppointmentTextOut>("/api/appointments/parse-text", { family_id: familyId, text, today }),
  /** Which medicines the doctor gave at this appointment (replaces the list). */
  setMedicines: (appointmentId: string, medicineIds: string[]) =>
    put<AppointmentOut>(`/api/appointments/${appointmentId}/medicines`, { medicine_ids: medicineIds }),
};

// ---- ask for help (only called when the text rules are not sure) ----

export interface AskOut {
  destination: string | null; // a key from lib/askHelp.ts, or null when nothing fits
  available: boolean; // false when no LLM could be reached
}

export const askHelp = {
  ask: (familyId: string, text: string, tried: string[]) =>
    post<AskOut>(`/api/families/${familyId}/ask`, { text, tried }),
};

// ---- family chat ----

export interface FamilyChatTurn {
  role: "user" | "assistant";
  text: string;
}

export interface FamilyChatOut {
  reply: string;
  destination: string | null; // a key from lib/askHelp.ts
  source: "ai" | "rules";
  /** The saved conversation the question and answer were added to. */
  conversation_id: string;
  /** Shown under the answer: the month's analysis ("Give me last month's analysis"). */
  card?: MonthlyAnalysis | null;
}

/** A month of the parent's care (services/monthly_analysis.py). A section the member may not view is null. */
export interface MonthlyAnalysis {
  kind: "monthly_analysis";
  parent: { id: string; name: string };
  period: { start: string; end: string; label: string };
  overview: string;
  source: "ai" | "rules";
  medicines: {
    taken: number;
    missed: number;
    skipped: number;
    recorded: number;
    taken_percent: number | null;
    by_medicine: { name: string; taken: number; missed: number; skipped: number }[];
  } | null;
  spending: {
    total: number;
    medicines: number | null;
    appointments: number | null;
    insurance: number | null;
    items: { kind: "medicine" | "appointment" | "insurance"; label: string; amount: number; date: string }[];
    item_count: number;
  } | null;
  conversations: {
    conversations: number;
    days_talked: number;
    days_in_period?: number;
    days_in_month?: number; // cards saved before ranges were added
    parent_messages: number;
  };
  /** All incidents in the period; `incidents` lists the newest of them. */
  incident_count?: number;
  incidents: { date: string; kind: "emergency" | "urgent" | "important"; text: string; status: string | null }[];
  diet: {
    days_reported: number;
    meals: { breakfast: number; lunch: number; dinner: number };
    skipped: number;
    recent: { date: string; meals: string[]; text: string }[];
    summary: string | null;
  };
  notes: { date: string; source: string; text: string }[];
  /** One row per month when the period is several months (empty for one month). */
  months?: {
    month: string;
    label: string;
    taken: number | null;
    recorded: number | null;
    taken_percent: number | null;
    spent: number | null;
    conversations: number;
    days_talked: number;
    incidents: number;
    meal_days: number;
  }[];
}

/** A saved chat, newest first in the list. Only the member who had it can see it. */
export interface FamilyChatConversationOut {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
}

export interface FamilyChatSavedMessage extends FamilyChatTurn {
  id: string;
  destination: string | null;
  card?: MonthlyAnalysis | null;
  created_at: string;
}

export interface FamilyChatImportItem {
  title: string;
  messages: { role: "user" | "assistant"; text: string; destination?: string | null }[];
}

// Chats are saved in the database: GET/DELETE .../chat/conversations[/{id}]; POST .../chat saves the question
// and its answer (in conversation_id, or a new chat); POST .../chat/log saves a question the page answered itself.
export const familyChat = {
  send: (familyId: string, text: string, conversationId: string | null) =>
    post<FamilyChatOut>(`/api/families/${familyId}/chat`, { text, conversation_id: conversationId }),
  log: (familyId: string, body: { text: string; reply: string; destination: string | null; conversation_id: string | null }) =>
    post<{ conversation_id: string }>(`/api/families/${familyId}/chat/log`, body),
  list: (familyId: string) => get<FamilyChatConversationOut[]>(`/api/families/${familyId}/chat/conversations`),
  get: (familyId: string, conversationId: string) =>
    get<{ id: string; title: string; updated_at: string; messages: FamilyChatSavedMessage[] }>(
      `/api/families/${familyId}/chat/conversations/${conversationId}`,
    ),
  remove: (familyId: string, conversationId: string) =>
    del(`/api/families/${familyId}/chat/conversations/${conversationId}`),
  importChats: (familyId: string, conversations: FamilyChatImportItem[]) =>
    post<{ imported: number }>(`/api/families/${familyId}/chat/conversations/import`, { conversations }),
};

// ---- insurance (api/insurance.py): policies and their renewals ----

export interface InsuranceOut {
  id: string;
  /** Whose cover; null for a family policy. */
  care_profile_id: string | null;
  policy_type: "health" | "life" | "accident" | "critical_illness" | "home" | "vehicle" | "other";
  insurer: string;
  plan_name: string | null;
  policy_number: string | null;
  sum_insured: string | number | null; // decimals arrive as strings
  premium: string | number | null;
  premium_frequency: "yearly" | "half_yearly" | "quarterly" | "monthly";
  start_date: string | null;
  renewal_date: string; // YYYY-MM-DD
  last_renewed_on: string | null;
  agent_name: string | null;
  agent_phone: string | null;
  helpline: string | null;
  notes: string | null;
  responsible_user_id: string | null;
  /** A policy document (PDF or photo) is attached: open it with openInsuranceDocument (insurance.ts). */
  has_document?: boolean;
  document_name?: string | null;
  document_type?: string | null;
}

/** What could be read from an uploaded policy document (POST .../insurance/read-document). */
export interface InsuranceDocumentRead {
  policy_type: InsuranceOut["policy_type"] | null;
  insurer: string | null;
  plan_name: string | null;
  policy_number: string | null;
  insured_name: string | null;
  sum_insured: string | number | null;
  premium: string | number | null;
  premium_frequency: InsuranceOut["premium_frequency"] | null;
  start_date: string | null;
  renewal_date: string | null;
  agent_name: string | null;
  agent_phone: string | null;
  helpline: string | null;
  source: "gemini" | "none";
}

export type InsuranceIn = Omit<
  InsuranceOut,
  "id" | "last_renewed_on" | "sum_insured" | "premium" | "has_document" | "document_name" | "document_type"
> & {
  sum_insured: number | null;
  premium: number | null;
};

export const insurance = {
  list: (familyId: string) => get<InsuranceOut[]>(`/api/families/${familyId}/insurance`),
  create: (familyId: string, body: InsuranceIn) => post<InsuranceOut>(`/api/families/${familyId}/insurance`, body),
  update: (familyId: string, id: string, body: Partial<InsuranceIn>) =>
    patch<InsuranceOut>(`/api/families/${familyId}/insurance/${id}`, body),
  renew: (familyId: string, id: string, body: { renewal_date?: string | null; premium?: number | null }) =>
    post<InsuranceOut>(`/api/families/${familyId}/insurance/${id}/renew`, body),
  remove: (familyId: string, id: string) => del(`/api/families/${familyId}/insurance/${id}`),
};

// ---- family dashboard (verified against api/dashboard.py and schemas.py) ----

export interface DashboardParentOut {
  care_profile_id: string;
  display_name: string;
  relationship: string | null;
  age: number | null;
  photo_url: string | null;
  /** An uploaded photo exists: fetch it with fetchProfilePhoto (profilePhoto.ts). */
  has_photo?: boolean;
  gender: string | null;
  known_health_conditions: string | null;
  primary_caregiver_name: string | null;
  all_good: boolean;
}

export interface DashboardMedicinesTodayOut {
  taken: number;
  total: number;
}

export interface DashboardScheduleItemOut {
  medicine_id: string;
  medicine_name: string;
  slot: string; // "HH:MM" or "any"
  status: string | null;
}

export interface DashboardStockItemOut {
  medicine_id: string;
  display_name: string;
  instructions_text: string | null;
  purpose: string | null;
  quantity_remaining: number | null;
  days_left: number | null;
  low: boolean;
}

export interface DashboardNextMonthItemOut {
  medicine_id: string;
  display_name: string;
  doses_per_day: number;
  /** Days of the next month the course still runs (up to take_until), else the whole month. */
  days_needed: number;
  take_until: string | null;
  tablets_needed: number;
  /** Tablets in stock, or null when never entered (counted as 0). */
  in_stock: number | null;
  /** Tablets needed minus stock, never below 0. */
  to_buy: number;
  unit_price: number | null;
  cost: number | null;
}

export interface DashboardNextMonthEstimateOut {
  /** Rupees to keep aside for the tablets the stock won't cover next month, or null when none are priced. */
  amount: number | null;
  days: number;
  priced_count: number;
  /** Medicines that need buying but have no price yet. */
  unpriced_count: number;
  items: DashboardNextMonthItemOut[];
}

export interface DashboardAppointmentOut {
  id: string;
  title: string;
  doctor: string;
  location: string | null;
  scheduled_date: string; // YYYY-MM-DD
  start_time: string; // HH:MM
}

export interface DashboardEmergencyOut {
  active: boolean;
  last_check_at: string | null;
}

export interface DashboardActivityOut {
  id: string;
  text: string;
  created_at: string;
}

export interface DashboardResponse {
  parents: DashboardParentOut[];
  selected_care_profile_id: string | null;
  on_date: string; // YYYY-MM-DD
  daily_medicine_count: number;
  medicines_today: DashboardMedicinesTodayOut;
  today_schedule: DashboardScheduleItemOut[];
  medicine_stock: DashboardStockItemOut[];
  next_month_estimate: DashboardNextMonthEstimateOut;
  next_appointment: DashboardAppointmentOut | null;
  emergency: DashboardEmergencyOut;
  recent_activity: DashboardActivityOut[];
  /** The whole family's emergencies that nobody has marked as completed yet. */
  emergencies: DashboardEmergencyItemOut[];
}

export interface DashboardEmergencyItemOut {
  id: string;
  care_profile_id: string;
  parent_name: string;
  text: string;
  source: "chat" | "button";
  created_at: string;
}

export function completeEmergency(familyId: string, id: string): Promise<void> {
  return post<void>(`/api/families/${familyId}/emergencies/${id}/complete`);
}

export interface DashboardParams {
  care_profile_id?: string;
  date?: string; // YYYY-MM-DD
}

export interface DoseHistoryItemOut {
  dose_date: string; // YYYY-MM-DD
  slot: string; // "HH:MM", "morning", "noon", "night" or "any"
  medicine_name: string;
  status: string; // taken, not_taken, skipped or missed
  source: string; // chatbot, manual or system
  recorded_at: string;
}

/** Recorded medicine answers from start to end, both included (YYYY-MM-DD, at most 90 days). */
export function getDoseHistory(
  familyId: string,
  params: { care_profile_id: string; start: string; end: string },
): Promise<DoseHistoryItemOut[]> {
  return get<DoseHistoryItemOut[]>(`/api/families/${familyId}/dose-history?${new URLSearchParams(params)}`);
}

export function getFamilyDashboard(familyId: string, params: DashboardParams = {}): Promise<DashboardResponse> {
  const query = new URLSearchParams();
  if (params.care_profile_id) query.set("care_profile_id", params.care_profile_id);
  if (params.date) query.set("date", params.date);
  const qs = query.toString();
  return get<DashboardResponse>(`/api/families/${familyId}/dashboard${qs ? `?${qs}` : ""}`);
}


// ---- weekly summary (verified against api/weekly_summary.py) ----

export interface WeekWarning {
  kind: string;
  text: string;
}

export interface WeeklySummaryOut {
  parent_name: string;
  start: string;
  end: string;
  taken: number;
  skipped: number;
  missed: number;
  checkin_days: number;
  fine_days: number;
  unwell_days: number;
  health_words: string[];
  bp: { day: string; value: string }[];
  sugar: { day: string; value: string }[];
  visits_done: string[];
  visits_next: string[];
  tasks_done: number;
  tasks_open: number;
  warnings: WeekWarning[];
  lines: string[];
}

export const weeklySummary = {
  get: (familyId: string, careProfileId: string, end?: string) =>
    get<WeeklySummaryOut>(
      `/api/families/${familyId}/care-profiles/${careProfileId}/weekly-summary${end ? `?end=${end}` : ""}`,
    ),
};

// ---- visit prep (verified against api/weekly_summary.py and services/today_plan.py) ----

export interface VisitPrepOut {
  points: { kind: "bp_high" | "sugar_high" | "missed" | "said" | "allergy"; count: number; value: string | null }[];
  refills: { medicine_id: string; name: string; left: number | null; refill_date: string | null;
    ask_name: string | null; asked: boolean }[];
}

export const visitPrep = {
  get: (familyId: string, careProfileId: string) =>
    get<VisitPrepOut>(`/api/families/${familyId}/care-profiles/${careProfileId}/weekly-summary/visit-prep`),
};

// ---- the parent's circle (verified against api/care_circle.py) ----

export type { CardOut, CirclePerson, HelpKind, HelpOut, PostOut } from "./parentApi";

export interface ContactOut {
  id: string;
  name: string;
  role: string;
  phone: string | null;
  address: string | null;
  birthday_month: number | null;
  birthday_day: number | null;
  sort_order: number;
}

export type ContactIn = Partial<Omit<ContactOut, "id">>;

const cpBase = (familyId: string, careProfileId: string) => `/api/families/${familyId}/care-profiles/${careProfileId}`;

export const circle = {
  help: (familyId: string) => get<HelpOut[]>(`/api/families/${familyId}/help`),
  decide: (familyId: string, helpId: string, status: HelpOut["status"], amount?: number | null) =>
    patch<HelpOut>(`/api/families/${familyId}/help/${helpId}`, { status, amount: amount ?? null }),
  posts: (familyId: string, careProfileId: string) => get<PostOut[]>(`${cpBase(familyId, careProfileId)}/posts`),
  addPost: (familyId: string, careProfileId: string, kind: PostOut["kind"], text: string, file?: Blob | null) => {
    const form = new FormData();
    form.append("kind", kind);
    if (text) form.append("text", text);
    if (file) form.append("file", file, file instanceof File ? file.name : "voice.webm");
    return post<PostOut>(`${cpBase(familyId, careProfileId)}/posts`, form);
  },
  contacts: (familyId: string, careProfileId: string) => get<ContactOut[]>(`${cpBase(familyId, careProfileId)}/contacts`),
  addContact: (familyId: string, careProfileId: string, body: ContactIn) =>
    post<ContactOut>(`${cpBase(familyId, careProfileId)}/contacts`, body),
  updateContact: (familyId: string, contactId: string, body: ContactIn) =>
    patch<ContactOut>(`/api/families/${familyId}/contacts/${contactId}`, body),
  removeContact: (familyId: string, contactId: string) => del(`/api/families/${familyId}/contacts/${contactId}`),
  card: (familyId: string, careProfileId: string) => get<CardOut>(`${cpBase(familyId, careProfileId)}/card`),
  saveCard: (
    familyId: string,
    careProfileId: string,
    body: Partial<Pick<CardOut, "blood_group" | "emergency_name" | "emergency_phone" | "notes">>,
  ) => put<CardOut>(`${cpBase(familyId, careProfileId)}/card`, body),
};

// Photos and voice notes need the auth header, so they load as blob URLs.
export async function fetchAuthedBlob(path: string): Promise<string | null> {
  const token = getSessionToken();
  const res = await fetch(`${API_BASE_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  return res.ok ? URL.createObjectURL(await res.blob()) : null;
}

// ---------- medical file, siblings, paperwork, carer, video ----------

export type DocKind = "prescription" | "lab" | "scan" | "discharge" | "insurance" | "other";

export interface MedicalDocOut {
  id: string;
  kind: DocKind;
  title: string;
  doc_date: string | null;
  text: string | null;
  has_file: boolean;
  file_name: string | null;
  created_at: string;
  file_url: string | null;
  match: string | null;
}

export interface MedicalLinkOut {
  id: string;
  token: string;
  expires_at: string;
  created_at: string;
}

export interface SharedFileOut {
  card: CardOut;
  expires_at: string;
  documents: MedicalDocOut[];
}

export interface SharingOut {
  total: number;
  share: number;
  balances: { user_id: string; name: string; paid: number; share: number; balance: number }[];
  expenses: { id: string; what: string; amount: number; spent_on: string; paid_by: string }[];
  visits_this_month: { user_id: string; name: string; count: number }[];
  visits: { id: string; name: string; visit_date: string; note: string | null; appointment_id: string | null }[];
  last_appointment: { id: string; date: string; provider: string | null; reason: string | null; went: string | null } | null;
  members: { user_id: string; name: string }[];
}

export type PaperKind = "life_certificate" | "income_tax" | "bank_kyc" | "property_tax" | "insurance" | "other";

export interface PaperOut {
  id: string;
  kind: PaperKind;
  title: string;
  due_date: string;
  note: string | null;
  done_on: string | null;
  source: "paperwork" | "insurance";
  days_left: number | null;
}

export interface CarerDayOut {
  name: string;
  meals: { meal: "breakfast" | "lunch" | "dinner"; done: boolean }[];
  doses: { medicine_id: string; name: string; slot: string; status: string; due_at: string }[];
  reports: { id: string; kind: "concern" | "note"; text: string; by: string; created_at: string }[];
}

export interface CallOut {
  id: string;
  status: "ringing" | "live" | "ended";
  answer: string | null;
}

export const medicalFile = {
  list: (familyId: string, careProfileId: string, q?: string) =>
    get<MedicalDocOut[]>(`${cpBase(familyId, careProfileId)}/medical-file${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  add: (
    familyId: string,
    careProfileId: string,
    fields: { kind?: DocKind | ""; title?: string; doc_date?: string; text?: string; file?: File | null },
  ) => {
    const form = new FormData();
    if (fields.kind) form.append("kind", fields.kind);
    if (fields.title) form.append("title", fields.title);
    if (fields.doc_date) form.append("doc_date", fields.doc_date);
    if (fields.text) form.append("text", fields.text);
    if (fields.file) form.append("file", fields.file, fields.file.name);
    return post<MedicalDocOut>(`${cpBase(familyId, careProfileId)}/medical-file`, form);
  },
  remove: (familyId: string, docId: string) => del(`/api/families/${familyId}/medical-file/${docId}`),
  links: (familyId: string, careProfileId: string) =>
    get<MedicalLinkOut[]>(`${cpBase(familyId, careProfileId)}/medical-file/links`),
  share: (familyId: string, careProfileId: string, days: 1 | 7 | 30) =>
    post<MedicalLinkOut>(`${cpBase(familyId, careProfileId)}/medical-file/links`, { days }),
  revoke: (familyId: string, linkId: string) => del(`/api/families/${familyId}/medical-links/${linkId}`),
  shared: (token: string) => get<SharedFileOut>(`/api/medical-file/${encodeURIComponent(token)}`),
};

export const siblings = {
  get: (familyId: string, careProfileId: string) => get<SharingOut>(`${cpBase(familyId, careProfileId)}/sharing`),
  addExpense: (
    familyId: string,
    careProfileId: string,
    body: { amount: number; what: string; spent_on: string; paid_by_user_id: string | null },
  ) => post<{ id: string }>(`${cpBase(familyId, careProfileId)}/expenses`, body),
  removeExpense: (familyId: string, id: string) => del(`/api/families/${familyId}/expenses/${id}`),
  addVisit: (
    familyId: string,
    careProfileId: string,
    body: { visit_date: string; appointment_id: string | null; note: string | null },
  ) => post<{ id: string }>(`${cpBase(familyId, careProfileId)}/visits`, body),
};

export const paperwork = {
  list: (familyId: string, careProfileId: string) => get<PaperOut[]>(`${cpBase(familyId, careProfileId)}/paperwork`),
  add: (
    familyId: string,
    careProfileId: string,
    body: { kind: PaperKind; title: string | null; due_date: string; note: string | null },
  ) => post<{ id: string }>(`${cpBase(familyId, careProfileId)}/paperwork`, body),
  addUsual: (familyId: string, careProfileId: string) =>
    post<{ added: number }>(`${cpBase(familyId, careProfileId)}/paperwork/usual`),
  done: (familyId: string, id: string) =>
    post<{ next_due: string | null }>(`/api/families/${familyId}/paperwork/${id}/done`),
  remove: (familyId: string, id: string) => del(`/api/families/${familyId}/paperwork/${id}`),
};

export const carer = {
  day: (familyId: string, careProfileId: string) => get<CarerDayOut>(`${cpBase(familyId, careProfileId)}/carer`),
  meal: (familyId: string, careProfileId: string, meal: string) =>
    post<void>(`${cpBase(familyId, careProfileId)}/carer/meals`, { meal, note: null }),
  dose: (familyId: string, careProfileId: string, medicine_id: string, slot: string, status: "taken" | "skipped") =>
    post<void>(`${cpBase(familyId, careProfileId)}/carer/doses`, { medicine_id, slot, status }),
  report: (familyId: string, careProfileId: string, kind: "concern" | "note", text: string) =>
    post<{ id: string }>(`${cpBase(familyId, careProfileId)}/carer/reports`, { kind, text }),
};

export const videoCalls = {
  start: (familyId: string, careProfileId: string, sdp: string) =>
    post<CallOut>(`${cpBase(familyId, careProfileId)}/calls`, { sdp }),
  get: (familyId: string, callId: string) => get<CallOut>(`/api/families/${familyId}/calls/${callId}`),
  end: (familyId: string, callId: string) => post<CallOut>(`/api/families/${familyId}/calls/${callId}/end`),
};
