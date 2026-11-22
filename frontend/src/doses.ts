import type { DoseToday } from "./api";

export type DoseTone = "taken" | "missed" | "skipped" | "due";

export interface DoseLabel {
  text: string;
  tone: DoseTone;
}

const timeFmt = (d: Date) => d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

// recorded_at may come without a timezone suffix (SQLite): treat that as UTC.
function parseRecorded(iso: string): Date {
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

function slotDate(slot: string, now: Date): Date | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(slot);
  if (!m) return null;
  const d = new Date(now);
  d.setHours(Number(m[1]), Number(m[2]), 0, 0);
  return d;
}

// Slots in day order, "any" last.
export function sortDoses(doses: DoseToday[]): DoseToday[] {
  const key = (d: DoseToday) => (d.slot === "any" ? "99:99" : d.slot.padStart(5, "0"));
  return [...doses].sort((a, b) => key(a).localeCompare(key(b)));
}

export function doseLabel(d: DoseToday, now: Date = new Date()): DoseLabel {
  const when = slotDate(d.slot, now);
  if (d.status === "taken") {
    const at = d.recorded_at ? parseRecorded(d.recorded_at) : null;
    const t = at && !Number.isNaN(at.getTime()) ? ` ${timeFmt(at)}` : "";
    return { text: `✓ Taken${t}`, tone: "taken" };
  }
  if (d.status === "not_taken") return { text: "Not taken", tone: "missed" };
  if (d.status === "skipped") return { text: "Skipped", tone: "skipped" };
  if (!when) return { text: "Not answered yet", tone: "due" };
  if (when.getTime() > now.getTime()) return { text: `Due ${timeFmt(when)}`, tone: "due" };
  return { text: "Due now", tone: "due" };
}

// Human slot name: "8:00 AM" or "Once today".
export function slotName(slot: string, now: Date = new Date()): string {
  const when = slotDate(slot, now);
  return when ? timeFmt(when) : "Once today";
}
