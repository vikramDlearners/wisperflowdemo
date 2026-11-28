// Insurance policies: labels and "is the renewal due?" (shared by the Insurance page and the Overview).

import type { InsuranceOut } from "./api";

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
