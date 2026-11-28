import { useCallback, useEffect, useState, type FormEvent } from "react";
import "../medicines.css";
import "../health-notes.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import {
  careProfiles,
  health,
  type CareProfileOut,
  type HealthListOut,
  type HealthNoteOut,
  type ReadingKind,
} from "../api";

// One health list per parent: allergies, conditions and readings, from chat, uploads and the family.
// Food advice in the parent's chat uses this same list.

const KINDS: { kind: ReadingKind; label: string; unit: string; example: string }[] = [
  { kind: "bp", label: "BP", unit: "mmHg", example: "130/85" },
  { kind: "sugar", label: "Sugar", unit: "mg/dL", example: "140" },
  { kind: "weight", label: "Weight", unit: "kg", example: "62" },
  { kind: "pulse", label: "Pulse", unit: "bpm", example: "76" },
];

export default function HealthNotes({ familyId }: { familyId: string }) {
  const [profiles, setProfiles] = useState<CareProfileOut[]>([]);
  const [profileId, setProfileId] = useState("");
  const [list, setList] = useState<HealthListOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [tracking, setTracking] = useState<string[] | null>(null);
  const [kind, setKind] = useState<ReadingKind>("bp");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    careProfiles
      .list(familyId)
      .then((rows) => {
        setProfiles(rows);
        setProfileId((current) => current || rows[0]?.id || "");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load profiles"));
  }, [familyId]);

  useEffect(() => {
    if (!profileId) return;
    let active = true;
    health
      .list(familyId, profileId)
      .then((data) => active && setList(data))
      .catch((err) => active && setError(err instanceof Error ? err.message : "Could not load the health list"));
    return () => {
      active = false;
    };
  }, [familyId, profileId, refresh]);

  const reload = useCallback(() => setRefresh((n) => n + 1), []);

  async function save(body: { text: string } | { kind: ReadingKind; value: string }) {
    setBusy(true);
    setError(null);
    try {
      const saved = await health.add(familyId, profileId, body);
      setTracking(saved.tracking);
      reload();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function handleNote(e: FormEvent) {
    e.preventDefault();
    if (text.trim() && (await save({ text: text.trim() }))) setText("");
  }

  async function handleReading(e: FormEvent) {
    e.preventDefault();
    if (value.trim() && (await save({ kind, value: value.trim() }))) setValue("");
  }

  async function handleRemove(note: HealthNoteOut) {
    if (!window.confirm(`Take "${note.text}" off the list?`)) return;
    try {
      await health.remove(familyId, profileId, note.id);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove");
    }
  }

  const name = profiles.find((p) => p.id === profileId)?.greeting_name ?? "your parent";

  return (
    <WorkspaceLayout familyId={familyId} current="health" title="Health notes">
      <div className="pp-content">
        <div className="pp-page-head hn-head">
          <div>
            <p className="pp-eyebrow">Care circle · Family workspace</p>
            <h1>Health notes</h1>
            <p className="pp-muted">
              Allergies, conditions and readings for {name}. The chat adds to this list, and food advice uses it.
            </p>
          </div>
          {profiles.length > 1 && (
            <label className="hn-field">
              <span>Parent</span>
              <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        {error && (
          <div role="alert" className="pp-alert">
            {error}
          </div>
        )}

        <div className="hn-grid">
          <section className="pp-card">
            <h2>Add a note</h2>
            <form onSubmit={handleNote} className="hn-form">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={3}
                placeholder="For example: BP was 150/95 this morning. Allergic to penicillin."
                aria-label="Health note"
              />
              <button type="submit" className="pp-btn" disabled={busy || !text.trim() || !profileId}>
                Save note
              </button>
            </form>
            <form onSubmit={handleReading} className="hn-form hn-reading">
              <select value={kind} onChange={(e) => setKind(e.target.value as ReadingKind)} aria-label="Reading">
                {KINDS.map((k) => (
                  <option key={k.kind} value={k.kind}>
                    {k.label}
                  </option>
                ))}
              </select>
              <input
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={KINDS.find((k) => k.kind === kind)?.example}
                aria-label="Reading value"
              />
              <button type="submit" className="pp-btn pp-btn-ghost" disabled={busy || !value.trim() || !profileId}>
                Add reading
              </button>
            </form>
            {tracking && (
              <div className="hn-tracking" role="status">
                {tracking.length === 0 ? (
                  <span>I didn't find a reading, condition or allergy in that.</span>
                ) : (
                  <>
                    <strong>I'll keep track of:</strong>
                    <ul>
                      {tracking.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            )}
          </section>

          <section className="pp-card">
            <h2>Allergies</h2>
            <NoteChips notes={list?.allergies ?? []} known={list?.known_allergies ?? []} onRemove={handleRemove} />
            <h2>Conditions</h2>
            <NoteChips notes={list?.conditions ?? []} known={list?.known_conditions ?? []} onRemove={handleRemove} />
          </section>
        </div>

        {profileId && <Trends familyId={familyId} profileId={profileId} refresh={refresh} />}

        <section className="pp-card md-table-card">
          <h2>Recent readings</h2>
          {!list || list.readings.length === 0 ? (
            <p className="pp-muted">No readings yet.</p>
          ) : (
            <div className="md-table-wrap">
              <table className="md-table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Reading</th>
                    <th>From</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {list.readings.map((r) => (
                    <tr key={r.id}>
                      <td>{new Date(r.recorded_at).toLocaleString()}</td>
                      <td>{r.text}</td>
                      <td title={r.source_text ?? undefined}>{SOURCE_LABELS[r.source] ?? r.source}</td>
                      <td>
                        <button type="button" className="pp-btn pp-btn-ghost hn-small" onClick={() => handleRemove(r)}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </WorkspaceLayout>
  );
}

const SOURCE_LABELS: Record<string, string> = { chat: "Chat", upload: "Upload", family: "Family" };

function NoteChips({
  notes,
  known,
  onRemove,
}: {
  notes: HealthNoteOut[];
  known: string[];
  onRemove: (note: HealthNoteOut) => void;
}) {
  // "known" also holds answers from the onboarding profile, which are not notes and cannot be removed here.
  const noted = new Set(notes.map((n) => n.label.toLowerCase()));
  const fromProfile = known.filter((k) => !noted.has(k.toLowerCase()));
  if (notes.length === 0 && fromProfile.length === 0) return <p className="pp-muted">None noted.</p>;
  return (
    <ul className="hn-chips">
      {notes.map((n) => (
        <li key={n.id} title={n.source_text ?? undefined}>
          {n.label}
          {n.value && n.value !== "yes" ? ` (${n.value})` : ""}
          <button type="button" aria-label={`Remove ${n.label}`} onClick={() => onRemove(n)}>
            ×
          </button>
        </li>
      ))}
      {fromProfile.map((k) => (
        <li key={k} title="From the care profile">
          {k}
        </li>
      ))}
    </ul>
  );
}

function Trends({ familyId, profileId, refresh }: { familyId: string; profileId: string; refresh: number }) {
  const [kind, setKind] = useState<ReadingKind>("bp");
  const [days, setDays] = useState(90);
  const [rows, setRows] = useState<HealthNoteOut[]>([]);

  useEffect(() => {
    let active = true;
    health
      .readings(familyId, profileId, kind, days)
      .then((data) => active && setRows(data.filter((r) => r.value_num != null)))
      .catch(() => active && setRows([]));
    return () => {
      active = false;
    };
  }, [familyId, profileId, kind, days, refresh]);

  const meta = KINDS.find((k) => k.kind === kind)!;
  return (
    <section className="pp-card">
      <div className="hn-trend-head">
        <h2>Readings over time</h2>
        <div className="hn-filters">
          <div className="hn-tabs" role="tablist">
            {KINDS.map((k) => (
              <button
                key={k.kind}
                type="button"
                role="tab"
                aria-selected={k.kind === kind}
                className={k.kind === kind ? "is-on" : ""}
                onClick={() => setKind(k.kind)}
              >
                {k.label}
              </button>
            ))}
          </div>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Time range">
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={365}>1 year</option>
          </select>
        </div>
      </div>
      {rows.length === 0 ? (
        <p className="pp-muted">No {meta.label} readings with numbers in this time.</p>
      ) : (
        <LineChart rows={rows} unit={meta.unit} twoLines={kind === "bp"} />
      )}
    </section>
  );
}

const W = 640;
const H = 220;
const PAD = { left: 44, right: 16, top: 12, bottom: 28 };

function LineChart({ rows, unit, twoLines }: { rows: HealthNoteOut[]; unit: string; twoLines: boolean }) {
  const [hover, setHover] = useState<number | null>(null);
  const times = rows.map((r) => Date.parse(r.recorded_at));
  const values = rows.flatMap((r) => [r.value_num!, ...(twoLines && r.value_num2 != null ? [r.value_num2] : [])]);
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  const lo = Math.floor(Math.min(...values) * 0.95);
  const hi = Math.ceil(Math.max(...values) * 1.05) || 1;
  const x = (t: number) => PAD.left + (t1 === t0 ? (W - PAD.left - PAD.right) / 2 : ((t - t0) / (t1 - t0)) * (W - PAD.left - PAD.right));
  const y = (v: number) => PAD.top + (1 - (v - lo) / (hi - lo || 1)) * (H - PAD.top - PAD.bottom);
  const path = (pick: (r: HealthNoteOut) => number | null) =>
    rows
      .map((r, i) => [x(times[i]), pick(r)] as const)
      .filter(([, v]) => v != null)
      .map(([px, v], i) => `${i ? "L" : "M"}${px.toFixed(1)},${y(v!).toFixed(1)}`)
      .join("");
  const ticks = [lo, Math.round((lo + hi) / 2), hi];
  const fmtDay = (t: number) => new Date(t).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  const hovered = hover == null ? null : rows[hover];

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    let best = 0;
    times.forEach((t, i) => {
      if (Math.abs(x(t) - px) < Math.abs(x(times[best]) - px)) best = i;
    });
    setHover(best);
  }

  return (
    <div className="hn-chart">
      {twoLines && (
        <div className="hn-legend">
          <span className="hn-key hn-key-1" /> Top (systolic) <span className="hn-key hn-key-2" /> Bottom (diastolic)
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Readings in ${unit}`} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} className="hn-grid-line" />
            <text x={PAD.left - 6} y={y(v) + 4} textAnchor="end" className="hn-axis">
              {v}
            </text>
          </g>
        ))}
        <text x={PAD.left} y={H - 8} className="hn-axis">
          {fmtDay(t0)}
        </text>
        {t1 !== t0 && (
          <text x={W - PAD.right} y={H - 8} textAnchor="end" className="hn-axis">
            {fmtDay(t1)}
          </text>
        )}
        {hovered && <line x1={x(times[hover!])} x2={x(times[hover!])} y1={PAD.top} y2={H - PAD.bottom} className="hn-cross" />}
        <path d={path((r) => r.value_num)} className="hn-line hn-line-1" />
        {twoLines && <path d={path((r) => r.value_num2)} className="hn-line hn-line-2" />}
        {rows.map((r, i) => (
          <g key={r.id}>
            <circle cx={x(times[i])} cy={y(r.value_num!)} r={hover === i ? 5 : 4} className="hn-dot hn-line-1" />
            {twoLines && r.value_num2 != null && (
              <circle cx={x(times[i])} cy={y(r.value_num2)} r={hover === i ? 5 : 4} className="hn-dot hn-line-2" />
            )}
          </g>
        ))}
      </svg>
      {hovered && (
        <div className="hn-tip" style={{ left: `${(x(times[hover!]) / W) * 100}%` }}>
          <strong>{hovered.text}</strong>
          <span>{new Date(hovered.recorded_at).toLocaleString()}</span>
        </div>
      )}
    </div>
  );
}
