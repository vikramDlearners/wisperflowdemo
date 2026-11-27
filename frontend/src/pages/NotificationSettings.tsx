import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { FormEvent } from "react";
import { ApiError, families, intentMode, notifications } from "../api";
import type { NotificationOut } from "../api";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { notificationLine } from "../notificationText";
import "../activity.css";
import "../notifications.css";

interface NotificationSettingsProps {
  familyId: string;
}

type Filter = "all" | "unread" | "urgent";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "urgent", label: "Urgent" },
];

const EMPTY_TEXT: Record<Filter, string> = {
  all: "No notifications yet. Family updates will show up here.",
  unread: "You're all caught up.",
  urgent: "No urgent notifications.",
};

// Values the backend accepts for the intent mode.
const MODES = [
  {
    value: "offline_rules",
    label: "Basic",
    help: 'Matches simple answers such as "yes", "I took it" or "later". Works without an AI service.',
  },
  {
    value: "online_llm",
    label: "AI",
    help: "Understands answers in a parent's own words. Uses Basic if AI is not available.",
  },
];

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

function look(type: string): { icon: string; tone: string } {
  if (type === "checkin.urgent") return { icon: "⚠️", tone: "urgent" };
  if (type.startsWith("medicine")) return { icon: "💊", tone: "medicines" };
  if (type.startsWith("task")) return { icon: "✅", tone: "tasks" };
  if (type.startsWith("checkin")) return { icon: "💬", tone: "chat" };
  if (type.startsWith("appointment")) return { icon: "📅", tone: "appointments" };
  return { icon: "🔔", tone: "settings" };
}

function dayLabel(d: Date): string {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function AnswerSettings({ familyId }: NotificationSettingsProps) {
  const [current, setCurrent] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [canEdit, setCanEdit] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setCurrent(null);
    setCanEdit(null);
    setError(null);
    setSaved(false);
    intentMode
      .get(familyId)
      .then((mode) => {
        if (cancelled) return;
        setCurrent(mode.intent_mode);
        setDraft(mode.intent_mode);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(messageOf(err));
      });
    families
      .me(familyId)
      .then((me) => {
        if (!cancelled) setCanEdit(me.permissions.includes("roles.manage"));
      })
      .catch(() => {
        if (!cancelled) setCanEdit(false);
      });
    return () => {
      cancelled = true;
    };
  }, [familyId]);

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const result = await intentMode.put(familyId, { intent_mode: draft });
      setCurrent(result.intent_mode);
      setDraft(result.intent_mode);
      setSaved(true);
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="pp-card" onSubmit={save} aria-labelledby="answer-settings-heading">
      <h3 id="answer-settings-heading" className="nt-section-title">
        How CareVoice understands medicine answers
      </h3>
      <p className="nt-hint">Used when a parent replies about their medicines. Applies to every family in the app.</p>
      {current === null && !error && (
        <p role="status" className="nt-note">
          Loading setting…
        </p>
      )}
      {error && (
        <p role="alert" className="act-error nt-gap">
          {current === null ? `Could not load this setting: ${error}` : `Could not save: ${error}`}
        </p>
      )}
      {current !== null && (
        <>
          <fieldset className="nt-options" disabled={!canEdit || saving} aria-labelledby="answer-settings-heading">
            {MODES.map((m) => (
              <label key={m.value} className="nt-option">
                <input
                  type="radio"
                  name="intent-mode"
                  value={m.value}
                  checked={draft === m.value}
                  onChange={() => {
                    setDraft(m.value);
                    setSaved(false);
                  }}
                />
                <span>
                  <strong>{m.label}</strong>
                  <small>{m.help}</small>
                </span>
              </label>
            ))}
          </fieldset>
          {canEdit && (
            <div className="nt-save-row">
              <button type="submit" className="pp-btn" disabled={saving || draft === current}>
                {saving ? "Saving…" : "Save changes"}
              </button>
              {saved && (
                <span role="status" className="nt-saved">
                  Saved
                </span>
              )}
            </div>
          )}
          {canEdit === false && <p className="nt-note">Only people who can manage roles can change this.</p>}
        </>
      )}
    </form>
  );
}

export default function NotificationSettings({ familyId }: NotificationSettingsProps) {
  const [items, setItems] = useState<NotificationOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [marking, setMarking] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    notifications
      .list()
      .then((list) => {
        // The API returns this user's notifications from every family.
        if (!cancelled) setItems(list.filter((n) => n.family_id === null || n.family_id === familyId));
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

  const markRead = async (ids: string[]) => {
    setActionError(null);
    setMarking(true);
    const results = await Promise.allSettled(ids.map((id) => notifications.markRead(id)));
    const updated = new Map<string, NotificationOut>();
    for (const r of results) if (r.status === "fulfilled") updated.set(r.value.id, r.value);
    setItems((prev) => prev.map((n) => updated.get(n.id) ?? n));
    const failed = results.find((r) => r.status === "rejected");
    if (failed) setActionError(messageOf(failed.reason));
    setMarking(false);
  };

  const rows = items
    .map((item) => ({
      item,
      line: notificationLine(item),
      at: new Date(item.created_at),
      unread: item.status === "unread",
    }))
    .sort((a, b) => b.at.getTime() - a.at.getTime());
  const unreadIds = rows.filter((r) => r.unread).map((r) => r.item.id);
  const counts: Record<Filter, number> = {
    all: rows.length,
    unread: unreadIds.length,
    urgent: rows.filter((r) => r.line.urgent).length,
  };
  const shown = rows.filter((r) => filter === "all" || (filter === "unread" ? r.unread : r.line.urgent));
  const days: { label: string; rows: typeof shown }[] = [];
  for (const r of shown) {
    const label = dayLabel(r.at);
    const last = days[days.length - 1];
    if (last && last.label === label) last.rows.push(r);
    else days.push({ label, rows: [r] });
  }

  return (
    <WorkspaceLayout familyId={familyId} current="notifications" title="Notification settings">
      <section className="act-page" aria-labelledby="notification-settings-heading">
        <header>
          <p className="act-eyebrow">Care circle · Family workspace</p>
          <h2 id="notification-settings-heading" className="act-title">
            Notification settings
          </h2>
          <p className="act-subtitle">Choose how CareVoice reads answers, and catch up on your family's updates.</p>
        </header>

        <AnswerSettings familyId={familyId} />

        <div className="nt-head">
          <h3 className="nt-section-title">Your notifications</h3>
          {unreadIds.length > 0 && (
            <button type="button" className="pp-btn pp-btn-ghost" disabled={marking} onClick={() => markRead(unreadIds)}>
              {marking ? "Marking…" : "Mark all as read"}
            </button>
          )}
        </div>

        {loading && (
          <p role="status" className="act-muted">
            Loading notifications…
          </p>
        )}
        {error && (
          <p role="alert" className="act-error">
            Could not load notifications: {error}
          </p>
        )}
        {actionError && (
          <p role="alert" className="act-error">
            Could not mark as read: {actionError}
          </p>
        )}

        {!loading && !error && (
          <>
            <div className="act-filters" role="group" aria-label="Filter notifications">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  className={`act-chip${filter === f.key ? " is-active" : ""}`}
                  aria-pressed={filter === f.key}
                  onClick={() => setFilter(f.key)}
                >
                  {f.label} ({counts[f.key]})
                </button>
              ))}
            </div>
            {days.length === 0 ? (
              <p className="act-empty">{EMPTY_TEXT[filter]}</p>
            ) : (
              days.map((day) => (
                <section key={day.label} className="act-day" aria-label={day.label}>
                  <h4 className="act-day-label">{day.label}</h4>
                  <ol className="act-list">
                    {day.rows.map(({ item, line, at, unread }) => {
                      const { icon, tone } = look(item.type);
                      return (
                        <li key={item.id} className={`act-item act-${tone} nt-item${unread ? " is-unread" : ""}`}>
                          <span className="act-icon" aria-hidden="true">
                            {icon}
                          </span>
                          <div className="act-body">
                            {line.urgent && <span className="nt-urgent-tag">Needs attention</span>}
                            <p className="act-line">
                              {unread && <span className="nt-dot" role="img" aria-label="Unread" />}
                              {line.text}
                            </p>
                            {item.type === "appointment.completed" &&
                              typeof item.payload?.appointment_id === "string" && (
                                <Link
                                  className="nt-link nt-view"
                                  to={`/family/${item.family_id ?? familyId}/appointments?appointment=${item.payload.appointment_id}`}
                                  onClick={() => {
                                    if (unread) void markRead([item.id]);
                                  }}
                                >
                                  View appointment details →
                                </Link>
                              )}
                            {unread && (
                              <button
                                type="button"
                                className="nt-link"
                                disabled={marking}
                                onClick={() => markRead([item.id])}
                              >
                                Mark as read
                              </button>
                            )}
                          </div>
                          <div className="act-side">
                            <time dateTime={item.created_at} className="act-time">
                              {at.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
                            </time>
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
