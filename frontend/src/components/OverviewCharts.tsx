import { useEffect, useState } from "react";
import "../overview-charts.css";
import { getDoseHistory, type DashboardResponse, type DashboardStockItemOut, type DoseHistoryItemOut } from "../api";
import { downloadCsv, toCsv } from "../lib/csv";

type Kind = "taken" | "missed" | "skipped" | "none";
type Counts = Record<Kind, number>;

const LABELS: Record<Kind, string> = { taken: "Taken", missed: "Missed", skipped: "Skipped", none: "No answer yet" };
const KINDS: Kind[] = ["taken", "missed", "skipped", "none"];

function countDoses(schedule: { status: string | null }[]): Counts {
  const counts: Counts = { taken: 0, missed: 0, skipped: 0, none: 0 };
  for (const { status } of schedule) {
    if (status === "taken" || status === "skipped") counts[status] += 1;
    else if (status === "missed" || status === "not_taken") counts.missed += 1;
    else counts.none += 1;
  }
  return counts;
}

function dayBefore(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function dayText(iso: string, options: Intl.DateTimeFormatOptions): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { ...options, timeZone: "UTC" });
}

function Legend({ kinds }: { kinds: Kind[] }) {
  return (
    <ul className="oc-legend">
      {kinds.map((k) => (
        <li key={k}>
          <span className={`oc-swatch is-${k}`} aria-hidden="true" />
          {LABELS[k]}
        </li>
      ))}
    </ul>
  );
}

/** Today's doses as one bar, split by status. */
export function TodayChart({ schedule }: { schedule: DashboardResponse["today_schedule"] }) {
  const counts = countDoses(schedule);
  const total = schedule.length;
  if (total === 0) return <p className="ov-empty">No doses scheduled today.</p>;
  const shown = KINDS.filter((k) => counts[k] > 0);
  return (
    <div className="oc-today">
      <p className="oc-figure">
        <strong>{Math.round((counts.taken / total) * 100)}%</strong> taken
        <span className="pp-muted"> · {counts.taken} of {total}</span>
      </p>
      <div className="oc-split" aria-hidden="true">
        {shown.map((k) => (
          <div key={k} className={`oc-part is-${k}`} style={{ flexGrow: counts[k] }} title={`${LABELS[k]}: ${counts[k]}`} />
        ))}
      </div>
      <ul className="oc-keys">
        {shown.map((k) => (
          <li key={k}>
            <span className={`oc-swatch is-${k}`} aria-hidden="true" />
            {LABELS[k]}
            <strong>{counts[k]}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

const ANSWER_KINDS: Kind[] = ["taken", "missed", "skipped"];
const MAX_DAYS = 90; // the backend's limit
const RANGES = [7, 14, 30] as const;

function daysBetween(start: string, end: string): number {
  return Math.round((Date.parse(end) - Date.parse(start)) / 86_400_000) + 1;
}

function rangeError(start: string, end: string, today: string): string | null {
  if (!start || !end) return "Choose both dates.";
  if (start > end) return "The From date must not be after the To date.";
  if (end > today) return "The To date cannot be after today.";
  if (daysBetween(start, end) > MAX_DAYS) return `Choose ${MAX_DAYS} days or fewer.`;
  return null;
}

function slotText(slot: string): string {
  if (slot.includes(":")) {
    return new Date(`2000-01-01T${slot}:00`).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  return slot === "any" ? "Any time" : slot[0].toUpperCase() + slot.slice(1);
}

const STATUS_TEXT: Record<string, string> = {
  taken: "Taken",
  skipped: "Skipped",
  missed: "Missed",
  not_taken: "Not taken",
};
const SOURCE_TEXT: Record<string, string> = { chatbot: "Check-in chat", manual: "Family", system: "Automatic" };

function downloadReport(name: string, start: string, end: string, rows: DoseHistoryItemOut[]) {
  const counts = countDoses(rows);
  const report = [
    ["Parent", name],
    ["From", start],
    ["To", end],
    ["Taken", String(counts.taken)],
    ["Missed or not taken", String(counts.missed)],
    ["Skipped", String(counts.skipped)],
    [],
    ["Date", "Time", "Medicine", "Answer", "Recorded by", "Recorded at"],
    ...rows.map((r) => [
      r.dose_date,
      slotText(r.slot),
      r.medicine_name,
      STATUS_TEXT[r.status] ?? r.status,
      SOURCE_TEXT[r.source] ?? r.source,
      new Date(r.recorded_at).toLocaleString(),
    ]),
  ];
  downloadCsv(`medicine-report-${start}-to-${end}.csv`, toCsv(["Medicine report"], report));
}

/**
 * Recorded answers per day for the chosen dates, with a report to download. Only answers are counted: the medicines
 * scheduled on a past day are not stored, so "out of scheduled" could be wrong.
 */
export function AnswersChart({ familyId, data }: { familyId: string; data: DashboardResponse }) {
  const profileId = data.selected_care_profile_id;
  const today = data.on_date;
  const [range, setRange] = useState<number | "custom">(7);
  const [custom, setCustom] = useState({ start: "", end: "" });
  const [history, setHistory] = useState<{ key: string; rows: DoseHistoryItemOut[] } | null>(null);
  const [failedKey, setFailedKey] = useState<string | null>(null);
  const [view, setView] = useState<"chart" | "table">("chart");

  const { start, end } = range === "custom" ? custom : { start: dayBefore(today, range - 1), end: today };
  const invalid = rangeError(start, end, today);
  const key = `${familyId}/${profileId}/${start}/${end}`;

  // `data` is a new object after each dashboard reload, so an answer recorded on this page shows up here too.
  useEffect(() => {
    if (!profileId || invalid) return;
    let active = true;
    setFailedKey(null);
    getDoseHistory(familyId, { care_profile_id: profileId, start, end })
      .then((rows) => active && setHistory({ key, rows }))
      .catch(() => active && setFailedKey(key));
    return () => {
      active = false;
    };
  }, [familyId, profileId, start, end, invalid, key, data]);

  if (!profileId) return <p className="ov-empty">No profiles added yet.</p>;

  const rows = !invalid && history?.key === key ? history.rows : null;
  const parentName = data.parents.find((p) => p.care_profile_id === profileId)?.display_name ?? "";

  return (
    <div>
      <div className="oc-bar">
        <select
          className="oc-field"
          aria-label="Dates"
          value={range}
          onChange={(e) => {
            if (e.target.value === "custom") {
              setCustom({ start, end });
              setRange("custom");
            } else setRange(Number(e.target.value));
          }}
        >
          {RANGES.map((n) => <option key={n} value={n}>Last {n} days</option>)}
          <option value="custom">Choose dates</option>
        </select>
        {range === "custom" && (
          <>
            <label className="oc-date">
              From
              <input
                className="oc-field"
                type="date"
                max={today}
                value={start}
                onChange={(e) => setCustom({ start: e.target.value, end })}
              />
            </label>
            <label className="oc-date">
              To
              <input
                className="oc-field"
                type="date"
                max={today}
                value={end}
                onChange={(e) => setCustom({ start, end: e.target.value })}
              />
            </label>
          </>
        )}
        <button
          type="button"
          className="oc-download"
          disabled={!rows?.length}
          onClick={() => rows && downloadReport(parentName, start, end, rows)}
        >
          <span aria-hidden="true">↓</span> Download report
        </button>
      </div>
      {invalid ? (
        <p className="ov-empty" role="alert">{invalid}</p>
      ) : rows ? (
        <AnswersView rows={rows} start={start} end={end} today={today} view={view} onView={setView} />
      ) : failedKey === key ? (
        <p className="ov-empty" role="alert">Could not load these dates.</p>
      ) : (
        <p className="ov-empty" role="status">Loading…</p>
      )}
    </div>
  );
}

interface AnswersViewProps {
  rows: DoseHistoryItemOut[];
  start: string;
  end: string;
  today: string;
  view: "chart" | "table";
  onView: (view: "chart" | "table") => void;
}

function AnswersView({ rows, start, end, today, view, onView }: AnswersViewProps) {
  if (rows.length === 0) return <p className="ov-empty">No medicine answers on these dates.</p>;
  const n = daysBetween(start, end);
  const days = Array.from({ length: n }, (_, i) => {
    const date = dayBefore(end, n - 1 - i);
    const counts = countDoses(rows.filter((r) => r.dose_date === date));
    return { date, counts, total: counts.taken + counts.missed + counts.skipped };
  });
  const labelEvery = n <= 7 ? 1 : Math.ceil(n / 5);
  // An even top, so the halfway gridline is a whole number.
  const top = Math.max(2, 2 * Math.ceil(Math.max(...days.map((d) => d.total)) / 2));
  const full = (iso: string) => dayText(iso, { weekday: "long", month: "short", day: "numeric" });
  const summary = (c: Counts, total: number) =>
    total === 0
      ? "No answers recorded"
      : ANSWER_KINDS.filter((k) => c[k] > 0).map((k) => `${LABELS[k]}: ${c[k]}`).join(", ");

  return (
    <div>
      <div className="oc-bar">
        {view === "chart" ? <Legend kinds={ANSWER_KINDS} /> : <span className="oc-legend">Answers recorded each day</span>}
        <div className="oc-toggle" role="group" aria-label="Show as">
          {(["chart", "table"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => onView(v)}>
              {v === "chart" ? "Chart" : "Table"}
            </button>
          ))}
        </div>
      </div>
      {view === "chart" ? (
        <>
          <div className="oc-plot" role="group" aria-label="Medicine answers recorded each day">
            {[top, top / 2, 0].map((v) => (
              <div key={v} className="oc-grid" style={{ bottom: `${(v / top) * 100}%` }} aria-hidden="true">
                <span>{v}</span>
              </div>
            ))}
            <div className="oc-cols">
              {days.map(({ date, counts, total }, i) => (
                <div key={date} className="oc-col" tabIndex={0} role="img" aria-label={`${full(date)}. ${summary(counts, total)}`}>
                  <div className="oc-stack" style={{ height: `${(total / top) * 100}%` }}>
                    {[...ANSWER_KINDS].reverse().filter((k) => counts[k] > 0).map((k) => (
                      <div key={k} className={`oc-part is-${k}`} style={{ flexGrow: counts[k] }} />
                    ))}
                  </div>
                  <div className={`oc-tip${i < n / 3 ? " is-left" : i >= (n * 2) / 3 ? " is-right" : ""}`} aria-hidden="true">
                    <span>{full(date)}</span>
                    {total === 0
                      ? "No answers recorded"
                      : ANSWER_KINDS.filter((k) => counts[k] > 0).map((k) => (
                          <span key={k} className="oc-tip-row">
                            <span className={`oc-swatch is-${k}`} />
                            <strong>{counts[k]}</strong> {LABELS[k]}
                          </span>
                        ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className={`oc-days${n > 14 ? " is-dense" : ""}`} aria-hidden="true">
            {days.map((d, i) => (
              <span key={d.date}>
                {(n - 1 - i) % labelEvery > 0
                  ? null
                  : d.date === today
                    ? "Today"
                    : dayText(d.date, n <= 7 ? { weekday: "short" } : { month: "short", day: "numeric" })}
              </span>
            ))}
          </div>
        </>
      ) : (
        <div className="oc-scroll" tabIndex={0} role="region" aria-label="Answers recorded each day">
          <table className="oc-table">
            <thead>
              <tr>
                <th scope="col">Day</th>
                {ANSWER_KINDS.map((k) => <th key={k} scope="col">{LABELS[k]}</th>)}
              </tr>
            </thead>
            <tbody>
              {days.map((d) => (
                <tr key={d.date}>
                  <td>{dayText(d.date, { weekday: "short", month: "short", day: "numeric" })}</td>
                  {ANSWER_KINDS.map((k) => <td key={k}>{d.counts[k]}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** Days left as a bar, on one scale shared by the whole list. */
export function StockBar({ item, all }: { item: DashboardStockItemOut; all: DashboardStockItemOut[] }) {
  if (item.days_left === null) return null;
  const max = Math.max(1, ...all.map((m) => m.days_left ?? 0));
  return (
    <div className="oc-stock" aria-hidden="true" title={`${item.display_name}: ${item.days_left} days left`}>
      <div className={item.low ? "is-low" : ""} style={{ width: `${(Math.max(0, item.days_left) / max) * 100}%` }} />
    </div>
  );
}
