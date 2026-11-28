import { useEffect, useState, type FormEvent } from "react";
import "../health-notes.css";
import "../care-circle.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import ProfilePicker, { useCareProfiles } from "../components/ProfilePicker";
import { ApiError, carer, type CarerDayOut } from "../api";

// The paid carer's day: tick meals and medicines, and write a note or flag a concern for the family.
// A concern notifies every other family member.

const MEAL_LABEL = { breakfast: "Breakfast", lunch: "Lunch", dinner: "Dinner" } as const;
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
const messageOf = (e: unknown) => (e instanceof ApiError ? e.detail : "Could not save. Try again.");

export default function Carer({ familyId }: { familyId: string }) {
  const { profiles, profileId, setProfileId } = useCareProfiles(familyId);
  const [day, setDay] = useState<CarerDayOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<"note" | "concern">("note");
  const [text, setText] = useState("");

  const load = () => {
    if (!profileId) return;
    carer.day(familyId, profileId).then(setDay).catch((err) => setError(messageOf(err)));
  };
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [familyId, profileId]);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      load();
      return true;
    } catch (err) {
      setError(messageOf(err));
      return false;
    }
  }
  async function report(e: FormEvent) {
    e.preventDefault();
    if (await run(() => carer.report(familyId, profileId, kind, text.trim()))) setText("");
  }

  return (
    <WorkspaceLayout familyId={familyId} current="carer" title="Carer's day">
      <div className="pp-content">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">Carer · Family workspace</p>
            <h1>{day ? `${day.name}'s day` : "Carer's day"}</h1>
            <p className="pp-muted">For the carer at home. The family sees every tick and note.</p>
          </div>
          <ProfilePicker profiles={profiles} profileId={profileId} onChange={setProfileId} />
        </div>
        {error && <p className="pp-alert" role="alert">{error}</p>}
        {day && (
          <>
            <section className="pp-card">
              <h2>Meals</h2>
              <div className="cr-ticks">
                {day.meals.map((m) => (
                  <button
                    key={m.meal}
                    type="button"
                    className={m.done ? "pp-btn cr-done" : "pp-btn pp-btn-ghost"}
                    disabled={m.done}
                    aria-pressed={m.done}
                    onClick={() => void run(() => carer.meal(familyId, profileId, m.meal))}
                  >
                    {m.done ? "✓ " : ""}
                    {MEAL_LABEL[m.meal]}
                  </button>
                ))}
              </div>
            </section>
            <section className="pp-card">
              <h2>Medicines today</h2>
              {day.doses.length === 0 ? (
                <p className="pp-muted">No medicines due today.</p>
              ) : (
                <ul className="cc-list">
                  {day.doses.map((d) => (
                    <li key={`${d.medicine_id}-${d.slot}`} className="cc-row">
                      <span>
                        <strong>{d.slot}</strong> · {d.name}{" "}
                        {d.status !== "not_taken" && <span className={`cc-status cc-${d.status}`}>{d.status}</span>}
                      </span>
                      {d.status === "not_taken" && (
                        <span className="cc-actions">
                          <button
                            type="button"
                            className="pp-btn"
                            onClick={() => void run(() => carer.dose(familyId, profileId, d.medicine_id, d.slot, "taken"))}
                          >
                            Taken
                          </button>
                          <button
                            type="button"
                            className="pp-btn pp-btn-ghost"
                            onClick={() => void run(() => carer.dose(familyId, profileId, d.medicine_id, d.slot, "skipped"))}
                          >
                            Skipped
                          </button>
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <form className="pp-card hn-form" onSubmit={(e) => void report(e)}>
              <h2>Tell the family</h2>
              <div className="cc-tabs" role="radiogroup" aria-label="Kind">
                {(["note", "concern"] as const).map((k) => (
                  <button
                    key={k}
                    type="button"
                    role="radio"
                    aria-checked={kind === k}
                    className={kind === k ? "cc-tab cc-tab-on" : "cc-tab"}
                    onClick={() => setKind(k)}
                  >
                    {k === "note" ? "A note" : "A concern (alerts the family)"}
                  </button>
                ))}
              </div>
              <label className="hn-field">
                <span>What happened</span>
                <textarea required rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ate well, walked for 10 minutes." />
              </label>
              <button type="submit" className="pp-btn">
                Send
              </button>
            </form>
            {day.reports.length > 0 && (
              <ul className="cc-list">
                {day.reports.map((r) => (
                  <li key={r.id} className="pp-card">
                    {r.kind === "concern" && <span className="cc-status cc-declined">concern</span>} {r.text}
                    <p className="pp-muted">
                      {r.by} · {when(r.created_at)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </WorkspaceLayout>
  );
}
