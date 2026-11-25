import { useEffect, useState, type ReactNode } from "react";
import { fetchProfilePhoto } from "../profilePhoto";
import { Link, useParams } from "react-router-dom";
import "../dashboard.css";
import AskHelp from "../components/AskHelp";
import DoseButtons from "../components/DoseButtons";
import WorkspaceLayout from "../components/WorkspaceLayout";
import {
  ApiError,
  auth,
  careProfiles,
  completeEmergency,
  families,
  getFamilyDashboard,
  medicines,
  members,
  type DashboardParentOut,
  type DashboardResponse,
  type DashboardStockItemOut,
  type DoseToday,
  type MemberOut,
  tasks,
  type TaskOut,
} from "../api";
import { canRecord, doseLabel, slotName, sortDoses } from "../doses";
import { isChild } from "../lib/constants";

// Family dashboard: GET /api/families/{familyId}/dashboard, optionally scoped
// to one parent with care_profile_id.

const TIME_RE = /^(\d{1,2}):(\d{2})/;

function formatTime(hhmm: string): string {
  const m = TIME_RE.exec(hhmm);
  if (!m) return hhmm;
  const h = Number(m[1]);
  return `${((h + 11) % 12) + 1}:${m[2]} ${h < 12 ? "AM" : "PM"}`;
}

// Dates arrive as "YYYY-MM-DD"; build a local day to avoid UTC shifts.
function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function formatStamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Could not load the dashboard.";
}

function greetingFor(hour: number): string {
  if (hour < 12) return "Good morning";
  return hour < 17 ? "Good afternoon" : "Good evening";
}

function startOfDay(offset = 0): Date {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + offset);
}

function dayLabel(d: Date): string {
  if (d >= startOfDay() && d < startOfDay(1)) return "Today";
  if (d >= startOfDay(1) && d < startOfDay(2)) return "Tomorrow";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

// "09:40 AM" today, else "3 Jun".
function shortStamp(iso: string): string {
  const d = new Date(iso);
  return d >= startOfDay()
    ? d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** "A", "A and B", "A, B and C". */
function listNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

function count(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

const isDone = (t: TaskOut) => ["done", "completed"].includes(t.status.toLowerCase());

const DOSE_TONES = { taken: "green", missed: "red", skipped: "amber", due: "blue" } as const;

interface Attention {
  key: string;
  icon: string;
  title: string;
  detail: string;
  tag: string;
  tone: "red" | "amber" | "blue";
  action: string;
  to: string;
}

function Pill({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`ov-pill is-${tone}`}>{children}</span>;
}

interface StatProps {
  label: string;
  value: ReactNode;
  sub: string;
  icon: string;
  to: string;
}

function Stat({ label, value, sub, icon, to }: StatProps) {
  return (
    <Link to={to} className="ov-card ov-stat">
      <span>
        <span className="ov-stat-label">{label}</span>
        <strong className="ov-stat-value">{value}</strong>
        <span className="ov-stat-sub">{sub}</span>
      </span>
      <span className="ov-tile" aria-hidden="true">{icon}</span>
    </Link>
  );
}

interface PanelProps {
  title: string;
  link?: { text: string; to: string };
  children: ReactNode;
}

function Panel({ title, link, children }: PanelProps) {
  return (
    <section className="ov-card ov-panel">
      <div className="ov-panel-head">
        <h2>{title}</h2>
        {link && <Link to={link.to}>{link.text} <span aria-hidden="true">→</span></Link>}
      </div>
      {children}
    </section>
  );
}

type Tone = "red" | "amber" | "green";

function stockTone(item: DashboardStockItemOut): Tone {
  if (item.low || (item.days_left !== null && item.days_left <= 4)) return "red";
  if (item.days_left !== null && item.days_left <= 7) return "amber";
  return "green";
}

function daysLabel(item: DashboardStockItemOut): string {
  if (item.days_left === null) return item.low ? "Low" : "—";
  const n = Math.round(item.days_left);
  return `${n} day${n === 1 ? "" : "s"} left`;
}

interface AvatarProps {
  name: string;
  photoUrl: string | null;
  gender: string | null;
  child: boolean;
  familyId: string;
  careProfileId: string;
  hasPhoto?: boolean;
}

// The parent's uploaded photo first (fetched with sign-in), else the image link, else an emoji or initials.
function Avatar({ name, photoUrl, gender, child, familyId, careProfileId, hasPhoto }: AvatarProps) {
  const [uploaded, setUploaded] = useState<string | null>(null);
  useEffect(() => {
    if (!hasPhoto) {
      setUploaded(null);
      return;
    }
    let active = true;
    let created: string | null = null;
    fetchProfilePhoto({ familyId, careProfileId })
      .then((url) => {
        created = url;
        if (active) setUploaded(url);
        else if (url) URL.revokeObjectURL(url);
      })
      .catch(() => undefined);
    return () => {
      active = false;
      if (created) URL.revokeObjectURL(created);
    };
  }, [hasPhoto, familyId, careProfileId]);

  const src = uploaded ?? photoUrl;
  if (src) return <img className="db-avatar" src={src} alt={name} />;
  if (gender === "male" || gender === "female") {
    return (
      <span className="db-avatar is-emoji" aria-hidden="true">
        {child ? (gender === "male" ? "👦" : "👧") : gender === "male" ? "👨" : "👩"}
      </span>
    );
  }
  return (
    <span className="db-avatar is-initials" aria-hidden="true">
      {initials(name)}
    </span>
  );
}

// The overview reads as one page: pieces the user may not see are simply left out.
export default function Dashboard() {
  const { familyId = "" } = useParams();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | null>(null);
  const [familyTasks, setFamilyTasks] = useState<TaskOut[] | null>(null);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [team, setTeam] = useState<MemberOut[]>([]);
  const [doses, setDoses] = useState<DoseToday[]>([]);
  const [zones, setZones] = useState<Record<string, string>>({});
  const [perms, setPerms] = useState<string[]>([]);
  const [recorded, setRecorded] = useState(0); // bumped after a dose is recorded, to load the page again
  const [completing, setCompleting] = useState<string | null>(null);
  const [shareNote, setShareNote] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    auth
      .me()
      .then((me) => active && setUserName(me.display_name))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getFamilyDashboard(familyId, selectedId ? { care_profile_id: selectedId } : {})
      .then((res) => active && setData(res))
      .catch((err) => active && setError(errorText(err)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [familyId, selectedId, recorded]);

  useEffect(() => {
    let active = true;
    setTasksError(null);
    tasks
      .list(familyId)
      .then((res) => active && setFamilyTasks(res))
      .catch((err) => active && setTasksError(errorText(err)));
    members
      .list(familyId)
      .then((res) => active && setTeam(res))
      .catch(() => undefined);
    families
      .me(familyId)
      .then((res) => active && setPerms(res.permissions))
      .catch(() => undefined);
    careProfiles
      .list(familyId)
      .then((res) => active && setZones(Object.fromEntries(res.map((p) => [p.id, p.timezone]))))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [familyId]);

  // When each dose was answered; the dashboard itself only says how.
  const profileId = data?.selected_care_profile_id ?? null;
  useEffect(() => {
    if (!profileId) return;
    let active = true;
    medicines
      .dosesToday(familyId, profileId)
      .then((res) => active && setDoses(res))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [familyId, profileId, recorded]);

  const path = (p: string) => `/family/${familyId}${p}`;
  const addProfile = `/onboarding/parent?add=1&family=${familyId}`;
  const firstName = userName?.trim().split(/\s+/)[0];
  const parent: DashboardParentOut | undefined = data?.parents.find(
    (p) => p.care_profile_id === data.selected_care_profile_id,
  );

  const schedule = data
    ? sortDoses(
        data.today_schedule.map((item) => ({
          medicine_id: item.medicine_id,
          slot: item.slot,
          status: item.status as DoseToday["status"],
          recorded_at:
            doses.find((d) => d.medicine_id === item.medicine_id && d.slot === item.slot)?.recorded_at ?? null,
        })),
      )
    : [];
  const medicineNames = new Map(data?.today_schedule.map((i) => [i.medicine_id, i.medicine_name]));
  async function markCompleted(id: string) {
    setCompleting(id);
    try {
      await completeEmergency(familyId, id);
      setRecorded((n) => n + 1);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setCompleting(null);
    }
  }

  const mayRecord = perms.includes("medicine_quantity.update");
  const zone = profileId ? zones[profileId] : undefined;
  const openTasks = (familyTasks ?? []).filter((t) => !isDone(t));
  const overdue = openTasks.filter((t) => t.due_at && new Date(t.due_at) < new Date());
  const dueToday = openTasks.filter((t) => t.due_at && dayLabel(new Date(t.due_at)) === "Today");
  const missed = schedule.filter((d) => d.status === "missed" || d.status === "not_taken");
  const lowStock = data?.medicine_stock.filter((m) => m.low) ?? [];

  const attention: Attention[] = [
    ...missed.map((d): Attention => ({
      key: `dose-${d.medicine_id}-${d.slot}`,
      icon: "!",
      title: `${medicineNames.get(d.medicine_id)} was ${d.status === "missed" ? "missed" : "not taken"}`,
      detail: `Today · ${slotName(d.slot)}`,
      tag: "Missed",
      tone: "red",
      action: "Review medicine",
      to: path(`/medicines/${d.medicine_id}`),
    })),
    ...(data?.emergency.active && missed.length === 0
      ? [{
          key: "emergency",
          icon: "!",
          title: "Emergency alert active",
          detail: data.emergency.last_check_at ? `Last check ${formatStamp(data.emergency.last_check_at)}` : "A dose was missed today",
          tag: "Open",
          tone: "red" as const,
          action: "Review activity",
          to: path("/activity"),
        }]
      : []),
    ...lowStock.map((m): Attention => ({
      key: `stock-${m.medicine_id}`,
      icon: "▤",
      title: `${m.display_name} is running low`,
      detail: daysLabel(m),
      tag: "Low stock",
      tone: "amber",
      action: "Review stock",
      to: path(`/medicines/${m.medicine_id}`),
    })),
    ...openTasks
      .filter((t) => overdue.includes(t) || !t.assigned_to_user_id)
      .map((t): Attention => {
        const late = overdue.includes(t);
        return {
          key: `task-${t.id}`,
          icon: "☷",
          title: t.title,
          detail: t.due_at ? `Due ${formatStamp(t.due_at)}` : "No due date",
          tag: late ? "Overdue" : "Unassigned",
          tone: late ? "amber" : "blue",
          action: late ? "Review task" : "Assign caregiver",
          to: path("/tasks"),
        };
      }),
  ];
  const onTrack = attention.length === 0 && !data?.emergencies.length;
  const appt = data?.next_appointment ?? null;

  // Doses whose time has come and that nobody has marked taken or skipped: what "Remind parent" is for.
  const notTakenYet = schedule.filter((d) => {
    if (d.status === "taken" || d.status === "skipped") return false;
    if (d.status === "missed" || d.status === "not_taken") return true;
    const text = doseLabel(d, zone).text;
    return text === "Due now" || text === "Not answered yet";
  });
  const takenCount = data?.medicines_today.taken ?? 0;
  const totalCount = data?.medicines_today.total ?? 0;
  const notTakenNames = [...new Set(notTakenYet.map((d) => medicineNames.get(d.medicine_id) ?? "a medicine"))];

  // The care summary in plain words, one line per topic.
  const summaryLines: { icon: string; text: string; tone: "ok" | "warn" | "info" }[] = data
    ? [
        totalCount === 0
          ? { icon: "💊", text: "No medicines to take today.", tone: "info" }
          : takenCount >= totalCount
            ? { icon: "💊", text: `All ${count(totalCount, "medicine")} taken today. Well done!`, tone: "ok" }
            : notTakenYet.length > 0
              ? {
                  icon: "💊",
                  text: `${takenCount === 0 ? "No medicines" : `Only ${takenCount} of ${totalCount}`} taken so far today. ${listNames(notTakenNames)} ${notTakenNames.length === 1 ? "is" : "are"} waiting to be taken.`,
                  tone: "warn",
                }
              : {
                  icon: "💊",
                  text: `${takenCount} of ${count(totalCount, "medicine")} taken so far. The rest are due later today.`,
                  tone: "info",
                },
        attention.length === 0
          ? { icon: "✅", text: "Nothing else to worry about.", tone: "ok" }
          : {
              icon: "⚠️",
              text:
                attention.length === 1
                  ? `1 thing to check: ${attention[0].title}.`
                  : `${attention.length} things to check, starting with: ${attention[0].title}.`,
              tone: "warn",
            },
        appt
          ? {
              icon: "📅",
              text: `Next appointment: ${dayLabel(parseDay(appt.scheduled_date))} at ${formatTime(appt.start_time)}.`,
              tone: "info",
            }
          : { icon: "📅", text: "No doctor appointments booked.", tone: "info" },
      ]
    : [];
  const summary = summaryLines.map((l) => l.text).join(" ");

  // "Remind parent": WhatsApp + text message (and the app) about the medicines waiting to be taken.
  const [reminding, setReminding] = useState(false);
  const [reminderNote, setReminderNote] = useState<{ text: string; bad?: boolean } | null>(null);
  useEffect(() => setReminderNote(null), [profileId]);

  async function remindParent() {
    if (!profileId || !parent) return;
    setReminding(true);
    setReminderNote(null);
    try {
      const r = await medicines.remindParent(familyId, profileId);
      const phone = r.sent_to ? ` (${r.sent_to})` : "";
      setReminderNote({ text: `Reminder sent to ${parent.display_name} on WhatsApp and text message${phone}.` });
    } catch (err) {
      setReminderNote({ text: errorText(err), bad: true });
    } finally {
      setReminding(false);
    }
  }

  async function shareUpdate() {
    if (!parent) return;
    const text = `Care update for ${parent.display_name}: ${summary}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: "CareCircle update", text });
        return;
      }
      await navigator.clipboard.writeText(text);
      setShareNote("Update copied. Paste it into any chat or email.");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setShareNote("Could not share the update from this browser.");
    }
  }

  let content: ReactNode;
  if (!data) {
    content = error ? (
      <div role="alert" className="db-banner is-error">
        {error}
      </div>
    ) : (
      <p role="status" className="pp-muted">
        Loading overview…
      </p>
    );
  } else {
    const { taken, total } = data.medicines_today;
    const shownAttention = attention.slice(0, 4);

    content = (
      <>
        {error && (
          <div role="alert" className="db-banner is-error">
            {error}
          </div>
        )}
        {loading && <p role="status" className="pp-muted">Updating…</p>}

        {data.emergencies.map((e) => (
          <section key={e.id} role="alert" className="db-emergency" aria-label={`Emergency: ${e.parent_name}`}>
            <div className="db-emergency-body">
              <h2>🚨 Emergency: {e.parent_name}</h2>
              <p>{e.source === "button" ? "Pressed the emergency button" : e.text}</p>
              <p>{formatStamp(e.created_at)}</p>
            </div>
            {perms.includes("tasks.update_own") && (
              <button
                type="button"
                className="db-emergency-done"
                disabled={completing !== null}
                onClick={() => void markCompleted(e.id)}
              >
                {completing === e.id ? "Saving…" : "Mark as completed"}
              </button>
            )}
          </section>
        ))}

        {data.parents.length > 1 && (
          <div className="db-switcher" role="group" aria-label="Choose profile">
            {data.parents.map((p) => {
              const active = p.care_profile_id === parent?.care_profile_id;
              return (
                <button
                  key={p.care_profile_id}
                  type="button"
                  className={`db-switch${active ? " is-active" : ""}`}
                  aria-pressed={active}
                  onClick={() => setSelectedId(p.care_profile_id)}
                >
                  {p.display_name}
                </button>
              );
            })}
          </div>
        )}

        {parent ? (
          <section className={`ov-pulse${onTrack ? "" : " is-attention"}`} aria-label="Care pulse">
            <Avatar
              name={parent.display_name}
              photoUrl={parent.photo_url}
              gender={parent.gender}
              child={isChild(parent.relationship)}
              familyId={familyId}
              careProfileId={parent.care_profile_id}
              hasPhoto={parent.has_photo}
            />
            <div className="ov-pulse-text">
              <h2>
                <Link to={path(`/parents/${parent.care_profile_id}`)}>{parent.display_name}</Link>
                {onTrack ? " is doing well today." : " needs a little help today."}
              </h2>
              <ul className="ov-pulse-lines">
                {summaryLines.map((l) => (
                  <li key={l.icon} className={`is-${l.tone}`}>
                    <span aria-hidden="true">{l.icon}</span>
                    {l.text}
                  </li>
                ))}
              </ul>
              {notTakenYet.length > 0 && (
                <div className="ov-remind">
                  <button type="button" className="pp-btn ov-remind-btn" disabled={reminding} onClick={() => void remindParent()}>
                    {reminding ? "Sending…" : `🔔 Remind ${parent.display_name}`}
                  </button>
                  <span className="ov-remind-hint">Sends a WhatsApp and text message about the medicines not taken yet.</span>
                </div>
              )}
              {reminderNote && (
                <p className={`ov-remind-note${reminderNote.bad ? " is-bad" : ""}`} role={reminderNote.bad ? "alert" : "status"}>
                  {reminderNote.bad ? "" : "✓ "}
                  {reminderNote.text}
                </p>
              )}
              <p className="ov-pulse-facts">
                <span>{parent.age !== null ? `${parent.age} years` : "Age not set"}{parent.relationship && ` · ${parent.relationship}`}</span>
                <span>Health: {parent.known_health_conditions || "None recorded"}</span>
                <span>Caregiver: {parent.primary_caregiver_name || "Not set"}</span>
              </p>
            </div>
            <Pill tone={onTrack ? "green" : "amber"}>{onTrack ? "On track" : "Needs attention"}</Pill>
          </section>
        ) : (
          <section className="ov-pulse">
            <div className="ov-pulse-text">
              <h2>No profiles added yet.</h2>
              <p>Add a parent or child to start following their care here.</p>
            </div>
            <Link to={addProfile} className="pp-btn ov-btn">Add profile</Link>
          </section>
        )}

        <div className="ov-stats">
          <Stat
            label="Medicine check-ins"
            value={`${taken} / ${total}`}
            sub={total === 0 ? "None scheduled today" : `Today · ${taken} confirmed`}
            icon="◷"
            to={path("/medicines")}
          />
          <Stat
            label="Needs attention"
            value={attention.length}
            sub={
              [
                missed.length > 0 && `${missed.length} missed`,
                lowStock.length > 0 && `${lowStock.length} low stock`,
                overdue.length > 0 && count(overdue.length, "overdue task"),
              ].filter(Boolean).join(" · ") || (onTrack ? "All clear" : "Tasks to assign")
            }
            icon="!"
            to={path(missed.length || lowStock.length ? "/medicines" : "/tasks")}
          />
          {familyTasks && (
            <Stat label="Open tasks" value={openTasks.length} sub={`${dueToday.length} due today`} icon="☷" to={path("/tasks")} />
          )}
          <Stat
            label="Upcoming appointment"
            value={appt ? dayLabel(parseDay(appt.scheduled_date)) : "None"}
            sub={appt ? `${formatTime(appt.start_time)} · ${appt.doctor || appt.title}` : "Nothing booked"}
            icon="▦"
            to={path("/appointments")}
          />
        </div>

        <div className="ov-row ov-row-wide">
          <Panel title="Today's medicine check-ins" link={{ text: "View all", to: path("/medicines") }}>
            {schedule.length === 0 ? (
              <p className="ov-empty">No doses scheduled today.</p>
            ) : (
              <table className="ov-table">
                <thead>
                  <tr>
                    <th scope="col">Schedule</th>
                    <th scope="col">Reported status</th>
                    <th scope="col">Updated</th>
                    {mayRecord && <th scope="col">Record</th>}
                  </tr>
                </thead>
                <tbody>
                  {schedule.map((d) => {
                    const label = doseLabel({ ...d, recorded_at: null }, zone);
                    return (
                      <tr key={`${d.medicine_id}-${d.slot}`}>
                        <td>
                          <strong>{slotName(d.slot)}</strong>
                          <span className="pp-muted">{medicineNames.get(d.medicine_id)}</span>
                        </td>
                        <td><Pill tone={DOSE_TONES[label.tone]}>{label.text.replace("✓ ", "")}</Pill></td>
                        <td className="pp-muted">{d.recorded_at ? shortStamp(d.recorded_at) : "—"}</td>
                        {mayRecord && profileId && (
                          <td className="ov-record">
                            {d.status !== "taken" && d.status !== "skipped" && canRecord(d, zone) && (
                              <DoseButtons
                                familyId={familyId}
                                careProfileId={profileId}
                                dose={d}
                                medicineName={medicineNames.get(d.medicine_id) ?? "this medicine"}
                                onRecorded={() => setRecorded((n) => n + 1)}
                              />
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </Panel>

          <Panel title="Needs attention">
            {onTrack ? (
              <p className="ov-empty">Nothing needs attention right now.</p>
            ) : (
              <ul className="ov-list">
                {shownAttention.map((a) => (
                  <li key={a.key}>
                    <span className={`ov-tile is-${a.tone}`} aria-hidden="true">{a.icon}</span>
                    <div className="ov-list-main">
                      <div className="ov-list-title">
                        <strong>{a.title}</strong>
                        <Pill tone={a.tone}>{a.tag}</Pill>
                      </div>
                      <span className="pp-muted">{a.detail}</span>
                      <Link to={a.to}>{a.action} <span aria-hidden="true">→</span></Link>
                    </div>
                  </li>
                ))}
                {attention.length > shownAttention.length && (
                  <li className="pp-muted">and {attention.length - shownAttention.length} more</li>
                )}
              </ul>
            )}
          </Panel>
        </div>

        <div className="ov-row">
          <Panel title="Recent family activity" link={{ text: "View all", to: path("/timeline") }}>
            {data.recent_activity.length === 0 ? (
              <p className="ov-empty">No activity yet.</p>
            ) : (
              <ul className="ov-list">
                {data.recent_activity.slice(0, 5).map((a) => (
                  <li key={a.id}>
                    <span className="ov-tile" aria-hidden="true">{a.text.startsWith("Appointment") ? "▦" : a.text.startsWith("Medicine") ? "▤" : a.text.startsWith("Task") ? "☷" : "♡"}</span>
                    <strong className="ov-list-main">{a.text}</strong>
                    <span className="pp-muted ov-stamp">{shortStamp(a.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {team.length > 0 && (
            <Panel title="Care team" link={{ text: "View all", to: path("/members") }}>
              <ul className="ov-list">
                {team.slice(0, 5).map((m, i) => (
                  <li key={m.membership_id}>
                    <span className={`pp-avatar ${i % 2 ? "pp-avatar-warm" : "pp-avatar-green"}`} aria-hidden="true">{initials(m.display_name)}</span>
                    <div className="ov-list-main">
                      <strong>{m.display_name}</strong>
                      {m.relationship && <span className="pp-muted">{m.relationship}</span>}
                    </div>
                    <Pill tone="green">{m.role_name}</Pill>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>

        <div className="ov-row">
          <Panel title="Medicine stock" link={{ text: "View all", to: path("/medicines") }}>
            {data.medicine_stock.length === 0 ? (
              <p className="ov-empty">No medicines in stock.</p>
            ) : (
              <ul className="ov-list">
                {data.medicine_stock.map((m) => (
                  <li key={m.medicine_id}>
                    <div className="ov-list-main">
                      <strong>{m.display_name}</strong>
                      <span className="pp-muted">{[m.instructions_text, m.purpose].filter(Boolean).join(" · ") || "—"}</span>
                    </div>
                    <Pill tone={stockTone(m)}>{daysLabel(m)}</Pill>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Open tasks" link={{ text: "View all", to: path("/tasks") }}>
            {tasksError ? (
              <p className="ov-empty">{tasksError}</p>
            ) : openTasks.length === 0 ? (
              <p className="ov-empty">{familyTasks ? "No open tasks." : "Loading tasks…"}</p>
            ) : (
              <ul className="ov-list">
                {openTasks.slice(0, 5).map((t) => (
                  <li key={t.id}>
                    <strong className="ov-list-main">{t.title}</strong>
                    <span className="pp-muted ov-stamp">{t.due_at ? formatStamp(t.due_at) : "No due date"}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </>
    );
  }

  return (
    <WorkspaceLayout familyId={familyId} current="overview" title="Overview">
      <div className="pp-content db ov">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">Care circle · Family workspace</p>
            <h1>{greetingFor(new Date().getHours())}{firstName && `, ${firstName}`}</h1>
            <p className="pp-muted">
              {parent ? `Here is the latest care update for ${parent.display_name}.` : "Here is your family care summary for today."}
            </p>
          </div>
          <div className="pp-head-actions">
            {parent && (
              <button type="button" className="pp-btn pp-btn-ghost" onClick={() => void shareUpdate()}>
                <span aria-hidden="true">↗</span> Share update
              </button>
            )}
            {perms.includes("parent_profile.edit") && (
              <Link to={addProfile} className="pp-btn pp-btn-ghost ov-btn">
                <span aria-hidden="true">＋</span> Add profile
              </Link>
            )}
            <Link to={path("/tasks?new=1")} className="pp-btn ov-btn">
              <span aria-hidden="true">＋</span> Add task
            </Link>
            {familyId && <AskHelp familyId={familyId} />}
          </div>
        </div>
        <p role="status" className="ov-share-note">{shareNote}</p>
        {content}
      </div>
    </WorkspaceLayout>
  );
}
