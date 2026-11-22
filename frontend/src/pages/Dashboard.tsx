import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import "../dashboard.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import {
  ApiError,
  auth,
  getFamilyDashboard,
  type DashboardParentOut,
  type DashboardResponse,
  type DashboardStockItemOut,
} from "../api";

// Family dashboard: GET /api/families/{familyId}/dashboard, optionally scoped
// to one parent with care_profile_id.

const TIME_RE = /^(\d{1,2}):(\d{2})/;

// Medicines without reminder times are recorded per part of the day.
const SLOT_PART_NAMES: Record<string, string> = { morning: "Morning", noon: "Afternoon", night: "Night" };

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

function Avatar({ name, photoUrl, gender }: { name: string; photoUrl: string | null; gender: string | null }) {
  if (photoUrl) return <img className="db-avatar" src={photoUrl} alt={name} />;
  if (gender === "male" || gender === "female") {
    return (
      <span className="db-avatar is-emoji" aria-hidden="true">
        {gender === "male" ? "👨" : "👩"}
      </span>
    );
  }
  return (
    <span className="db-avatar is-initials" aria-hidden="true">
      {initials(name)}
    </span>
  );
}

export default function Dashboard() {
  const { familyId = "" } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    auth
      .me()
      .then((me) => {
        if (active) setUserName(me.display_name);
      })
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
      .then((res) => {
        if (active) setData(res);
      })
      .catch((err) => {
        if (active) setError(errorText(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [familyId, selectedId]);

  const greeting = `Good Evening, ${userName ?? "there"}`;

  let content: ReactNode;
  if (!data) {
    content = error ? (
      <div role="alert" className="db-banner is-error">
        {error}
      </div>
    ) : (
      <p role="status" className="pp-muted">
        Loading dashboard…
      </p>
    );
  } else {
    const parent: DashboardParentOut | undefined =
      data.parents.find((p) => p.care_profile_id === data.selected_care_profile_id) ?? data.parents[0];
    const taken = data.medicines_today.taken;
    const total = data.medicines_today.total;
    const lowCount = data.medicine_stock.filter((s) => s.low).length;
    const appt = data.next_appointment;

    content = (
      <>
        {error && (
          <div role="alert" className="db-banner is-error">
            {error}
          </div>
        )}
        {loading && <p role="status" className="pp-muted">Updating…</p>}

        {/* Parent overview */}
        <section className="db-card db-tint-teal db-overview" aria-label="Parent overview">
          <div className="db-overview-main">
            <h2 className="db-card-title">Parent Overview</h2>
            {data.parents.length > 0 ? (
              <div className="db-switcher" role="group" aria-label="Choose parent">
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
                      <Avatar name={p.display_name} photoUrl={p.photo_url} gender={p.gender} />
                      {p.display_name}
                    </button>
                  );
                })}
              </div>
            ) : (
              <p className="pp-muted">No parents added yet.</p>
            )}
            {parent && (
              <div className="db-parent">
                <Avatar name={parent.display_name} photoUrl={parent.photo_url} gender={parent.gender} />
                <div className="db-parent-text">
                  <button
                    type="button"
                    className="db-parent-name db-parent-link"
                    onClick={() => navigate(`/family/${familyId}/parents/${parent.care_profile_id}`)}
                  >
                    {parent.display_name}
                  </button>
                  <div className="pp-muted">
                    {parent.age !== null ? `${parent.age} years` : "Age not set"}
                    {parent.relationship && ` • ${parent.relationship}`}
                  </div>
                </div>
                {parent.all_good && <span className="db-badge is-good">✓ All Good</span>}
              </div>
            )}
          </div>
          <dl className="db-facts">
            <div>
              <dt>Health</dt>
              <dd>{parent?.known_health_conditions || "None recorded"}</dd>
            </div>
            <div>
              <dt><span aria-hidden="true">💊</span> Medicines</dt>
              <dd>{data.daily_medicine_count} Medicine(s) daily</dd>
            </div>
            <div>
              <dt>Primary Caregiver</dt>
              <dd>{parent?.primary_caregiver_name || "Not set"}</dd>
            </div>
          </dl>
        </section>

        {/* Summary cards */}
        <div className="db-summary">
          <section className="db-card db-tint-mint">
            <h3 className="db-card-title"><span aria-hidden="true">💊</span> Today's Medicines</h3>
            <p className="db-big">
              {taken} / {total}
            </p>
            {total > 0 && taken === total && <span className="db-badge is-good">✓ Completed</span>}
          </section>

          <section className="db-card db-tint-blue">
            <h3 className="db-card-title"><span aria-hidden="true">📅</span> Next Appointment</h3>
            {appt ? (
              <>
                <p className="db-big db-big-sm">{parseDay(appt.scheduled_date).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</p>
                <p className="db-sub">{appt.title}</p>
                <p className="pp-muted">
                  {appt.doctor}
                  {appt.location && ` • ${appt.location}`}
                </p>
                <p className="pp-muted">{formatTime(appt.start_time)}</p>
              </>
            ) : (
              <p className="pp-muted">No upcoming appointments.</p>
            )}
          </section>

          <section className="db-card db-tint-lavender">
            <h3 className="db-card-title"><span aria-hidden="true">💊</span> Medicine Stock</h3>
            <p className="db-big">
              {lowCount > 0 ? <span className="db-badge is-red">{lowCount} Low</span> : <span className="db-badge is-good">All OK</span>}
            </p>
            <p className="pp-muted">Out of {data.medicine_stock.length} medicines</p>
          </section>

          <section className="db-card db-tint-rose">
            <h3 className="db-card-title">Emergency</h3>
            {data.emergency.active ? (
              <span className="db-badge is-red">Emergency alert active</span>
            ) : (
              <span className="db-badge is-good">✓ No Active Alerts</span>
            )}
            <p className="pp-muted">
              {data.emergency.last_check_at
                ? `Last check: ${formatStamp(data.emergency.last_check_at)}`
                : "No check recorded yet"}
            </p>
          </section>
        </div>

        {/* Lists */}
        <div className="db-lists">
          <section className="db-card db-tint-mint" aria-label="Medicine stock list">
            <h2 className="db-card-title"><span aria-hidden="true">💊</span> Medicine Stock</h2>
            {data.medicine_stock.length === 0 ? (
              <p className="pp-muted">No medicines in stock.</p>
            ) : (
              <ul className="db-list">
                {data.medicine_stock.map((s) => (
                  <li key={s.medicine_id} className="db-row">
                    <div className="db-row-main">
                      <strong>{s.display_name}</strong>
                      <span className="pp-muted">
                        {[s.instructions_text, s.purpose].filter(Boolean).join(" • ") || "—"}
                      </span>
                    </div>
                    <span className={`db-days is-${stockTone(s)}`}>{daysLabel(s)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="db-card db-tint-blue" aria-label="Today's schedule">
            <h2 className="db-card-title">Today's Schedule</h2>
            <table className="db-schedule-table">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col"><span aria-hidden="true">💊</span> Medicine</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.today_schedule.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="pp-muted">No doses scheduled today.</td>
                  </tr>
                ) : (
                  data.today_schedule.map((item, i) => {
                    const done = item.status === "taken";
                    return (
                      <tr key={`${item.medicine_id}-${item.slot}-${i}`}>
                        <td className="db-schedule-time">
                          {item.slot === "any" || item.slot in SLOT_PART_NAMES
                            ? (SLOT_PART_NAMES[item.slot] ?? "Any time")
                            : formatTime(item.slot)}
                        </td>
                        <td className="db-schedule-name">{item.medicine_name}</td>
                        <td>
                          <span className={`db-schedule-status${done ? " is-done" : " is-pending"}`}>
                            {done ? "Completed" : "Pending"}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </section>

          <section className="db-card db-tint-lavender" aria-label="Recent activity">
            <h2 className="db-card-title">Recent Activity</h2>
            {data.recent_activity.length === 0 ? (
              <p className="pp-muted">No recent activity.</p>
            ) : (
              <ul className="db-list">
                {data.recent_activity.map((a) => (
                  <li key={a.id} className="db-row">
                    <span className="db-row-main">{a.text}</span>
                    <span className="pp-muted db-stamp">{formatStamp(a.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </>
    );
  }

  return (
    <WorkspaceLayout familyId={familyId} current="overview" title="Dashboard">
      <div className="pp-content db">
        <div className="pp-page-head">
          <div>
            <h1>{greeting}</h1>
            <p className="pp-muted">Here's your family care summary for today.</p>
          </div>
        </div>
        {content}
      </div>
    </WorkspaceLayout>
  );
}
