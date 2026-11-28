// Insurance policies: labels and "is the renewal due?" (shared by the Insurance page and the Overview).

import { API_BASE_URL, ApiError, getSessionToken, type InsuranceDocumentRead, type InsuranceOut } from "./api";

/** A renewal within this many days (or already past) counts as due. */
export const DUE_WITHIN_DAYS = 30;

export const POLICY_TYPES: { key: InsuranceOut["policy_type"]; label: string; icon: string }[] = [
  { key: "health", label: "Health", icon: "🩺" },
  { key: "life", label: "Life", icon: "🛡️" },
  { key: "accident", label: "Accident", icon: "🩹" },
  { key: "critical_illness", label: "Critical illness", icon: "❤️" },
  { key: "home", label: "Home", icon: "🏠" },
  { key: "vehicle", label: "Vehicle", icon: "🚗" },
  { key: "other", label: "Other", icon: "📄" },
];

export const FREQUENCIES: { key: InsuranceOut["premium_frequency"]; label: string; perYear: number }[] = [
  { key: "yearly", label: "Yearly", perYear: 1 },
  { key: "half_yearly", label: "Every 6 months", perYear: 2 },
  { key: "quarterly", label: "Every 3 months", perYear: 4 },
  { key: "monthly", label: "Monthly", perYear: 12 },
];

export function typeLabel(t: string): string {
  return POLICY_TYPES.find((p) => p.key === t)?.label ?? "Other";
}

export function typeIcon(t: string): string {
  return POLICY_TYPES.find((p) => p.key === t)?.icon ?? "📄";
}

export function frequencyLabel(f: string): string {
  return FREQUENCIES.find((x) => x.key === f)?.label ?? "Yearly";
}

/** "YYYY-MM-DD" as a local calendar day. */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

/** Whole days from today to the renewal date (negative when it has passed). */
export function daysUntil(iso: string, today: Date = new Date()): number {
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((parseDay(iso).getTime() - start.getTime()) / 86_400_000);
}

export type RenewalState = "overdue" | "due" | "ok";

export function renewalState(p: Pick<InsuranceOut, "renewal_date">, today: Date = new Date()): RenewalState {
  const days = daysUntil(p.renewal_date, today);
  if (days < 0) return "overdue";
  return days <= DUE_WITHIN_DAYS ? "due" : "ok";
}

/** "Overdue by 3 days", "Due today", "Due tomorrow", "Due in 12 days", "Renews 15 Dec 2027". */
export function renewalText(p: Pick<InsuranceOut, "renewal_date">, today: Date = new Date()): string {
  const days = daysUntil(p.renewal_date, today);
  if (days < 0) return `Overdue by ${-days} ${days === -1 ? "day" : "days"}`;
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  if (days <= DUE_WITHIN_DAYS) return `Due in ${days} days`;
  return `Renews ${formatDay(p.renewal_date)}`;
}

export function formatDay(iso: string): string {
  return parseDay(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function rupees(value: string | number | null | undefined): string | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
}

/** The premium paid in a year (premium × payments a year). */
export function yearlyPremium(p: Pick<InsuranceOut, "premium" | "premium_frequency">): number {
  const n = Number(p.premium ?? 0);
  const per = FREQUENCIES.find((f) => f.key === p.premium_frequency)?.perYear ?? 1;
  return Number.isFinite(n) ? n * per : 0;
}

// ---- policy documents (PDF or photo) ----

export const DOCUMENT_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/webp"];
export const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;

/** A problem with a picked file, or null when it can be uploaded. */
export function checkDocument(file: File): string | null {
  if (!DOCUMENT_TYPES.includes(file.type)) return "Upload a PDF, or a JPG, PNG or WebP photo.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_DOCUMENT_BYTES) return "This file is larger than 10 MB. Please choose a smaller one.";
  return null;
}

function authHeaders(): Record<string, string> {
  const token = getSessionToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fail(res: Response): Promise<never> {
  let detail = res.statusText || "Request failed";
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    // not JSON
  }
  throw new ApiError(res.status, detail);
}

const base = (familyId: string) => `${API_BASE_URL}/api/families/${familyId}/insurance`;

async function sendFile<T>(url: string, method: "POST" | "PUT", file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(url, { method, headers: { Accept: "application/json", ...authHeaders() }, body: form });
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}

/** Gemini reads the document to fill in the form; nothing is saved. */
export const readInsuranceDocument = (familyId: string, file: File) =>
  sendFile<InsuranceDocumentRead>(`${base(familyId)}/read-document`, "POST", file);

export const attachInsuranceDocument = (familyId: string, policyId: string, file: File) =>
  sendFile<InsuranceOut>(`${base(familyId)}/${policyId}/document`, "PUT", file);

export async function removeInsuranceDocument(familyId: string, policyId: string): Promise<InsuranceOut> {
  const res = await fetch(`${base(familyId)}/${policyId}/document`, {
    method: "DELETE",
    headers: { Accept: "application/json", ...authHeaders() },
  });
  if (!res.ok) return fail(res);
  return (await res.json()) as InsuranceOut;
}

/** Opens the attached document in a new tab (fetched with the sign-in token, shown as a blob: URL). */
export async function openInsuranceDocument(familyId: string, policyId: string): Promise<void> {
  const tab = window.open("", "_blank"); // opened now, while the click still counts, so it isn't blocked
  try {
    const res = await fetch(`${base(familyId)}/${policyId}/document`, { headers: authHeaders() });
    if (!res.ok) await fail(res);
    const url = URL.createObjectURL(await res.blob());
    if (tab) tab.location.href = url;
    else window.location.href = url;
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (err) {
    tab?.close();
    throw err;
  }
}
