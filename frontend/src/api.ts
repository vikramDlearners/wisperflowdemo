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
  responsible_user_id?: string | null;
}

export interface MedicineUpdate {
  display_name?: string | null;
  instructions_text?: string | null;
  refill_date?: string | null;
  responsible_user_id?: string | null;
  active?: boolean | null;
  // Pricing (edit only; the server computes total_price = unit_price x total_medicine_count).
  unit_price?: number | string | null;
  total_medicine_count?: number | null;
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
  proposed: { medicines: PrescriptionMedicineIn[] } | null;
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

export function getFamilyDashboard(familyId: string, params: DashboardParams = {}): Promise<DashboardResponse> {
  const query = new URLSearchParams();
  if (params.care_profile_id) query.set("care_profile_id", params.care_profile_id);
  if (params.date) query.set("date", params.date);
  const qs = query.toString();
  return get<DashboardResponse>(`/api/families/${familyId}/dashboard${qs ? `?${qs}` : ""}`);
}

