import { useEffect, useState } from "react";
import "../health-notes.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import {
  careProfiles,
  visitPrep,
  weeklySummary,
  type CareProfileOut,
  type VisitPrepOut,
  type WeeklySummaryOut,
} from "../api";

// The parent's last seven days on one page, and the patterns worth a call. The family also gets this
// by email and in the app every Sunday evening, and each warning as soon as it shows up.

function shiftDay(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function prepLine(p: VisitPrepOut["points"][number]): string {
  switch (p.kind) {
    case "bp_high":
      return `BP was high on ${p.count} day(s), last ${p.value}.`;
    case "sugar_high":
      return `Sugar was high on ${p.count} day(s), last ${p.value}.`;
    case "missed":
      return `Missed ${p.value} ${p.count} time(s).`;
    case "said":
      return `Said: "${p.value}"`;
    case "allergy":
      return `Allergies: ${p.value}.`;
  }
}

function nice(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export default function WeeklySummary({ familyId }: { familyId: string }) {
  const [profiles, setProfiles] = useState<CareProfileOut[]>([]);
  const [profileId, setProfileId] = useState("");
  const [end, setEnd] = useState<string | undefined>(undefined);
  const [week, setWeek] = useState<WeeklySummaryOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prep, setPrep] = useState<VisitPrepOut | null>(null);

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
    setError(null);
    weeklySummary
      .get(familyId, profileId, end)
      .then((data) => active && setWeek(data))
      .catch((err) => active && setError(err instanceof Error ? err.message : "Could not load the week"));
    return () => {
      active = false;
    };
  }, [familyId, profileId, end]);

  useEffect(() => {
    if (!profileId) return;
    visitPrep.get(familyId, profileId).then(setPrep).catch(() => setPrep(null));
  }, [familyId, profileId]);

  const doses = week ? week.taken + week.skipped + week.missed : 0;

  return (
    <WorkspaceLayout familyId={familyId} current="week" title="This week">
      <div className="pp-content">
        <div className="pp-page-head hn-head">
          <div>
            <p className="pp-eyebrow">Care circle · Family workspace</p>
            <h1>{week ? `${week.parent_name}'s week` : "This week"}</h1>
            <p className="pp-muted">
              {week ? `${nice(week.start)} to ${nice(week.end)}. ` : ""}
              Sent to the family every Sunday evening. Warnings are sent as soon as they show up.
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

        {week && (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              <button type="button" className="pp-btn" onClick={() => setEnd(shiftDay(week.end, -7))}>
                ← Week before
              </button>
              {end && (
                <button type="button" className="pp-btn" onClick={() => setEnd(undefined)}>
                  This week
                </button>
              )}
            </div>

            {week.warnings.length > 0 && (
              <section className="pp-card" style={{ borderLeft: "4px solid #b42318", marginBottom: 16 }}>
                <h2>Worth a call</h2>
                <ul>
                  {week.warnings.map((w) => (
                    <li key={w.kind}>{w.text}</li>
                  ))}
                </ul>
              </section>
            )}

            <div className="hn-grid">
              <section className="pp-card">
                <h2>Medicines</h2>
                {doses ? (
                  <p>
                    <strong>{week.taken}</strong> of {doses} doses taken
                    {week.missed > 0 && <>, {week.missed} missed</>}
                    {week.skipped > 0 && <>, {week.skipped} skipped</>}.
                  </p>
                ) : (
                  <p className="pp-muted">No doses were logged this week.</p>
                )}
              </section>
              <section className="pp-card">
                <h2>Check-ins and mood</h2>
                <p>
                  Spoke on <strong>{week.checkin_days}</strong> of 7 days. Tapped "I'm fine" on{" "}
                  <strong>{week.fine_days}</strong>.
                </p>
                {week.unwell_days > 0 && <p>Felt unwell on {week.unwell_days} day(s).</p>}
                {week.health_words.length > 0 && (
                  <p className="pp-muted">In their words: {week.health_words.map((w) => `"${w}"`).join(", ")}</p>
                )}
                <p className="pp-muted">Sleep is not tracked yet.</p>
              </section>
              <section className="pp-card">
                <h2>BP and sugar</h2>
                {week.bp.length === 0 && week.sugar.length === 0 && <p className="pp-muted">No readings this week.</p>}
                {week.bp.length > 0 && <p>BP: {week.bp.map((r) => `${r.value} (${nice(r.day)})`).join(", ")}</p>}
                {week.sugar.length > 0 && (
                  <p>Sugar: {week.sugar.map((r) => `${r.value} (${nice(r.day)})`).join(", ")}</p>
                )}
              </section>
              <section className="pp-card">
                <h2>Doctor visits and tasks</h2>
                {week.visits_done.map((v) => (
                  <p key={v}>Seen: {v}</p>
                ))}
                {week.visits_next.map((v) => (
                  <p key={v}>Coming up: {v}</p>
                ))}
                {week.visits_done.length + week.visits_next.length === 0 && (
                  <p className="pp-muted">No visits this week or in the next two weeks.</p>
                )}
                <p>
                  Tasks: {week.tasks_done} done, {week.tasks_open} still open.
                </p>
              </section>
              {prep && (prep.points.length > 0 || prep.refills.length > 0) && (
                <section className="pp-card">
                  <h2>Before the next visit</h2>
                  {prep.points.length > 0 && (
                    <ul>
                      {prep.points.map((p, i) => (
                        <li key={`${p.kind}-${i}`}>{prepLine(p)}</li>
                      ))}
                    </ul>
                  )}
                  {prep.refills.map((r) => (
                    <p key={r.medicine_id}>
                      Running low: {r.name}
                      {r.left !== null ? ` (about ${r.left} left)` : ""}
                      {r.asked ? ", refill asked for." : "."}
                    </p>
                  ))}
                </section>
              )}
            </div>
          </>
        )}
      </div>
    </WorkspaceLayout>
  );
}
