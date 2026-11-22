import type { DoseToday } from "./api";

export type DoseTone = "taken" | "missed" | "skipped" | "due";

export interface DoseLabel {
  text: string;
  tone: DoseTone;
}

export const DEFAULT_TZ = "Asia/Kolkata";

// An invalid timezone string makes Intl throw a RangeError: fall back to the browser zone.
const tz = (timeZone?: string | null): string | undefined => {
  const zone = timeZone || DEFAULT_TZ;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: zone });
    return zone;
  } catch {
    return undefined;
  }
};

// recorded_at may come without a timezone suffix (SQLite): treat that as UTC.
function parseRecorded(iso: string): Date {
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

function parseSlot(slot: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(slot);
  return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

// Minutes since midnight of `now` in the given zone.
function minutesNow(now: Date, timeZone: string | undefined): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone,
  }).formatToParts(now);
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? 0);
  return (get("hour") % 24) * 60 + get("minute");
}

// "8:00 PM" from minutes-of-day (no zone conversion).
function clock(mins: number): string {
  return new Date(2000, 0, 1, Math.floor(mins / 60), mins % 60).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

// Slots in day order, "any" last.
export function sortDoses(doses: DoseToday[]): DoseToday[] {
  const key = (d: DoseToday) => (d.slot === "any" ? "99:99" : d.slot.padStart(5, "0"));
  return [...doses].sort((a, b) => key(a).localeCompare(key(b)));
}

export function doseLabel(
  d: DoseToday,
  timeZone?: string | null,
  now: Date = new Date(),
): DoseLabel {
  const zone = tz(timeZone);
  const slot = parseSlot(d.slot);
  if (d.status === "taken") {
    const at = d.recorded_at ? parseRecorded(d.recorded_at) : null;
    const t =
      at && !Number.isNaN(at.getTime())
        ? ` ${at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", timeZone: zone })}`
        : "";
    return { text: `✓ Taken${t}`, tone: "taken" };
  }
  if (d.status === "not_taken") return { text: "Not taken", tone: "missed" };
  // Written by the system when the slot passed with no answer (not something the parent said).
  if (d.status === "missed") return { text: "Missed", tone: "missed" };
  if (d.status === "skipped") return { text: "Skipped", tone: "skipped" };
  if (slot === null) return { text: "Not answered yet", tone: "due" };
  if (slot > minutesNow(now, zone)) return { text: `Due ${clock(slot)}`, tone: "due" };
  return { text: "Due now", tone: "due" };
}

// Human slot name: "8:00 AM" or "Once today".
export function slotName(slot: string): string {
  const m = parseSlot(slot);
  return m === null ? "Once today" : clock(m);
}
