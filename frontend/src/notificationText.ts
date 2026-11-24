import type { NotificationOut } from "./api";

// One readable line per family notification, shared by Dashboard and NotificationSettings.
// Payload shapes: backend/app/services/family_alerts.py. Other types keep showing the raw type.

export interface NotificationLine {
  text: string;
  /** True for checkin.urgent: show a "Needs attention now" badge. */
  urgent: boolean;
}

function str(payload: Record<string, unknown> | null, key: string): string | null {
  const v = payload?.[key];
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

const PART_NAMES: Record<string, string> = { morning: "morning", noon: "afternoon", night: "night" };

function slotText(slot: string | null): string {
  if (!slot || slot === "any") return "";
  return PART_NAMES[slot] ? ` (${PART_NAMES[slot]})` : ` (due ${slot})`;
}

export function notificationLine(n: Pick<NotificationOut, "type" | "payload">): NotificationLine {
  const p = n.payload;
  const parent = str(p, "parent_name") ?? "Your parent";
  const said = str(p, "text");
  const medicine = str(p, "medicine_name") ?? "a medicine";
  switch (n.type) {
    case "checkin.update":
      return { text: said ? `${parent} checked in: "${said}"` : `${parent} checked in today.`, urgent: false };
    case "checkin.urgent":
      return {
        text: said ? `${parent} reported: "${said}"` : `${parent} reported something that needs attention.`,
        urgent: true,
      };
    case "medicine.missed":
      return {
        text: p?.child
          ? `${medicine} for ${parent} hasn't been marked as taken${slotText(str(p, "slot"))}.`
          : `${parent} hasn't taken ${medicine}${slotText(str(p, "slot"))}.`,
        urgent: false,
      };
    case "medicine.finished":
      return { text: `${parent} says ${medicine} has run out. Please arrange a refill.`, urgent: false };
    default:
      return { text: n.type, urgent: false };
  }
}
