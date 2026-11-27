import type { NotificationOut } from "./api";

// One readable line per family notification, used by NotificationSettings.
// Unknown types get a plain sentence, not the raw type.

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
    case "medicine.reminder": {
      const message = str(p, "message");
      const from = str(p, "from");
      const lead = from ? `${from} sent you a medicine reminder` : "Medicine reminder";
      return { text: message ? `${lead}: "${message}"` : `${lead}.`, urgent: false };
    }
    case "medicine_reminders_created": {
      const names = Array.isArray(p?.medicines)
        ? p.medicines.filter((m): m is string => typeof m === "string" && m.trim() !== "")
        : [];
      return {
        text: names.length ? `Medicine reminders were set up for ${names.join(", ")}.` : "Medicine reminders were set up.",
        urgent: false,
      };
    }
    case "task.assigned": {
      const title = str(p, "title");
      return { text: title ? `You were given a task: ${title}` : "You were given a task.", urgent: false };
    }
    case "task.notified": {
      const title = str(p, "title");
      return { text: title ? `Task reminder: ${title}` : "You have a task reminder.", urgent: false };
    }
    case "appointment.completed": {
      const reason = str(p, "reason") ?? "appointment";
      const provider = str(p, "provider");
      const by = str(p, "completed_by");
      const day = str(p, "scheduled_date");
      const when = day
        ? ` on ${new Date(`${day}T00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })}`
        : "";
      return {
        text: `${parent}'s ${reason}${provider ? ` with ${provider}` : ""}${when} is completed${by ? `, marked by ${by}` : ""}.`,
        urgent: false,
      };
    }
    default:
      return { text: "You have a new care update.", urgent: false };
  }
}
