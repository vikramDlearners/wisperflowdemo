import { useEffect, useMemo, useState } from "react";
import "../activity.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { activity, ApiError, auth, members } from "../api";
import type { ActivityOut } from "../api";

interface CareVoiceActivityProps {
  familyId: string;
}

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

type Category = "chat" | "urgent" | "medicines" | "tasks" | "appointments" | "family" | "settings";

const CATEGORY_LOOK: Record<Category, { icon: string; label: string }> = {
  chat: { icon: "💬", label: "Parent chat" },
  urgent: { icon: "🆘", label: "Urgent" },
  medicines: { icon: "💊", label: "Medicines" },
  tasks: { icon: "✅", label: "Tasks" },
  appointments: { icon: "📅", label: "Appointments" },
  family: { icon: "👪", label: "Family" },
  settings: { icon: "⚙️", label: "Settings" },
};

const FILTERS: { key: "all" | Category; label: string }[] = [
  { key: "all", label: "All" },
  { key: "chat", label: "Parent chat" },
  { key: "medicines", label: "Medicines" },
  { key: "tasks", label: "Tasks" },
  { key: "appointments", label: "Appointments" },
  { key: "family", label: "Family" },
];

const CHECKIN_STEPS: Record<string, string> = {
  greet: "Started today's check-in",
  health: "Shared how they're feeling",
  medicines: "Answering about medicines",
  meals: "Telling what they ate",
  appointments: "Heard about appointments",
  done: "Finished the check-in",
};

const TASK_STATUS: Record<string, string> = { OPEN: "open", DONE: "done" };

function text(meta: Record<string, unknown> | null, key: string): string | null {
  const v = meta?.[key];
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

interface Described {
  category: Category;
  what: string; // follows the actor's name: "added a medicine"
  detail: string | null;
}

// A plain sentence for each kind of activity the app records.
function describe(item: ActivityOut): Described {
  const m = item.metadata;
  const name = text(m, "title") ?? text(m, "name") ?? text(m, "display_name");
  const role = text(m, "role");
  switch (item.action) {
    case "family.created":
      return { category: "family", what: "created the family", detail: null };
    case "care_profile.created":
      return { category: "family", what: "added a care profile", detail: name };
    case "care_profile.updated":
      return { category: "family", what: "updated a care profile", detail: name };
    case "care_profile.deleted":
      return { category: "family", what: "removed a care profile", detail: name };
    case "member.added":
      return { category: "family", what: "added a family member", detail: role ? `As ${role}` : null };
    case "member.removed":
      return { category: "family", what: "removed a family member", detail: null };
    case "member.role_changed":
      return { category: "family", what: "changed a member's role", detail: role ? `Now ${role}` : null };
    case "role.created":
      return { category: "family", what: "created a new role", detail: name };
    case "role.permissions_updated": {
      const perms = m?.permissions;
      const n = Array.isArray(perms) ? perms.length : null;
      return {
        category: "family",
        what: "changed a role's permissions",
        detail: n == null ? null : `${n} permissions allowed`,
      };
    }
    case "parent_invite.created":
      return { category: "family", what: "sent the parent a sign-in link", detail: null };
    case "medicine.created":
      return { category: "medicines", what: "added a medicine", detail: name };
    case "medicine.updated":
      return { category: "medicines", what: "updated a medicine", detail: name };
    case "medicine.deleted":
      return { category: "medicines", what: "removed a medicine", detail: name };
    case "medicine.image_uploaded":
      return { category: "medicines", what: "added a medicine photo", detail: name };
    case "medicine.quantity_updated":
      return { category: "medicines", what: "updated tablets left", detail: name };
    case "medicine.reminders_set":
      return { category: "medicines", what: "set medicine reminder times", detail: name };
    case "prescription_scan.created":
      return { category: "medicines", what: "scanned a prescription", detail: null };
    case "prescription_scan.confirmed":
      return { category: "medicines", what: "added medicines from a prescription", detail: null };
    case "appointment.created":
      return { category: "appointments", what: "added an appointment", detail: name };
    case "appointment.updated":
      return { category: "appointments", what: "changed an appointment", detail: name };
    case "appointment.deleted":
      return { category: "appointments", what: "cancelled an appointment", detail: name };
    case "task.created":
      return { category: "tasks", what: "created a task", detail: name };
    case "task.assigned":
      return { category: "tasks", what: "assigned a task", detail: name };
    case "task.updated":
      return { category: "tasks", what: "updated a task", detail: name };
    case "task.deleted":
      return { category: "tasks", what: "deleted a task", detail: name };
    case "task.notified":
      return { category: "tasks", what: "sent a task reminder", detail: name };
    case "task.status_changed": {
      const status = text(m, "status");
      return {
        category: "tasks",
        what: `marked a task ${status ? TASK_STATUS[status] ?? status.toLowerCase() : "updated"}`,
        detail: name,
      };
    }
    case "checkin.updated": {
      const step = text(m, "step");
      return { category: "chat", what: "talked with CareCircle", detail: step ? CHECKIN_STEPS[step] ?? null : null };
    }
    case "checkin.emergency":
      return { category: "urgent", what: "pressed the emergency button", detail: "The family was alerted" };
    case "settings.intent_mode_changed": {
      const mode = text(m, "mode");
      return {
        category: "settings",
        what: "changed how answers are understood",
        detail: mode === "online_llm" ? "AI mode (Gemini)" : mode === "offline_rules" ? "Offline rules" : null,
      };
    }
    default: {
      // Anything new still reads sensibly: "medicine.something_new" -> "something new (medicine)".
      const [object, verb] = item.action.split(".");
      return {
        category: "settings",
        what: `${(verb ?? item.action).replace(/_/g, " ")} (${(object ?? "").replace(/_/g, " ")})`,
        detail: null,
      };
    }
  }
}

function dayLabel(d: Date): string {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

export default function CareVoiceActivity({ familyId }: CareVoiceActivityProps) {
  const [items, setItems] = useState<ActivityOut[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [meId, setMeId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | Category>("all");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      activity.list(familyId),
      members.list(familyId).catch(() => []),
      auth.me().catch(() => null),
    ])
      .then(([data, people, me]) => {
        if (cancelled) return;
        setItems(data);
        setNames(Object.fromEntries(people.map((p) => [p.user_id, p.display_name || p.email || "A member"])));
        setMeId(me?.id ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(messageOf(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [familyId]);

  const rows = useMemo(
    () =>
      items
        .map((item) => ({ item, d: describe(item), at: new Date(item.created_at) }))
        .sort((a, b) => b.at.getTime() - a.at.getTime()),
    [items],
  );
  const shown = rows.filter(
    (r) => filter === "all" || r.d.category === filter || (filter === "chat" && r.d.category === "urgent"),
  );
  const days: { label: string; rows: typeof shown }[] = [];
  for (const r of shown) {
    const label = dayLabel(r.at);
    const last = days[days.length - 1];
    if (last && last.label === label) last.rows.push(r);
    else days.push({ label, rows: [r] });
  }

  const who = (actorId: string | null) => {
    if (!actorId) return "CareCircle";
    if (actorId === meId) return "You";
    return names[actorId] ?? "A family member";
  };

  return (
    <WorkspaceLayout familyId={familyId} current="activity" title="CareVoice activity">
      <section className="act-page" aria-labelledby="carevoice-activity-heading">
        <header className="act-header">
          <p className="act-eyebrow">Care circle · Family workspace</p>
          <h2 id="carevoice-activity-heading" className="act-title">
            CareVoice activity
          </h2>
          <p className="act-subtitle">
            Everything that happens in your family's care, newest first: check-ins, medicines, tasks and changes.
          </p>
        </header>

        {loading && (
          <p role="status" className="act-muted">
            Loading activity…
          </p>
        )}
        {error && (
          <p role="alert" className="act-error">
            Could not load activity: {error}
          </p>
        )}

        {!loading && !error && (
          <>
            <div className="act-filters" role="group" aria-label="Show">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  className={`act-chip${filter === f.key ? " is-active" : ""}`}
                  aria-pressed={filter === f.key}
                  onClick={() => setFilter(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {days.length === 0 ? (
              <div className="act-empty">
                <span aria-hidden="true">🕊️</span>
                <p>{items.length === 0 ? "Nothing has happened yet." : "Nothing here for this filter."}</p>
              </div>
            ) : (
              days.map((day) => (
                <section key={day.label} className="act-day" aria-label={day.label}>
                  <h3 className="act-day-label">{day.label}</h3>
                  <ol className="act-list">
                    {day.rows.map(({ item, d, at }) => {
                      const look = CATEGORY_LOOK[d.category];
                      return (
                        <li key={item.id} className={`act-item act-${d.category}`}>
                          <span className="act-icon" aria-hidden="true">
                            {look.icon}
                          </span>
                          <div className="act-body">
                            <p className="act-line">
                              <strong>{who(item.actor_id)}</strong> {d.what}
                            </p>
                            {d.detail && <p className="act-detail">{d.detail}</p>}
                          </div>
                          <div className="act-side">
                            <time dateTime={item.created_at} className="act-time">
                              {at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
                            </time>
                            <span className="act-tag">{look.label}</span>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                </section>
              ))
            )}
          </>
        )}
      </section>
    </WorkspaceLayout>
  );
}
