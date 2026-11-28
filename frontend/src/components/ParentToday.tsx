import { useCallback, useEffect, useState } from "react";
import { askRefill, getToday, type TodayPlanOut, type VisitPoint } from "../parentApi";
import { fill, todayStrings, type TodayStrings } from "../parentTodayStrings";
import { circleStrings } from "../parentCircleStrings";

// Today only, under the "I'm fine" button: today's tablets, a doctor visit in the next two days with what to
// tell the doctor, tasks due today, and medicines running low with a one-tap "Yes, ask Ravi". Folded by
// default so the chat stays first; opens itself when a refill or a visit needs the parent.

function point(t: TodayStrings, p: VisitPoint): string {
  const v = { n: p.count, v: p.value ?? "", name: p.value ?? "" };
  switch (p.kind) {
    case "bp_high":
      return fill(t.pBp, v);
    case "sugar_high":
      return fill(t.pSugar, v);
    case "missed":
      return fill(t.pMissed, v);
    case "said":
      return fill(t.pSaid, v);
    case "allergy":
      return fill(t.pAllergy, v);
  }
}

export default function ParentToday({ language, profileId }: { language: string; profileId: string }) {
  const t = todayStrings(language);
  const [plan, setPlan] = useState<TodayPlanOut | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const refresh = useCallback(() => {
    getToday().then(setPlan).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 5 * 60 * 1000);
    return () => window.clearInterval(id);
  }, [refresh, profileId]);

  if (!plan) return null;
  const dayName = (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(language, { weekday: "long", day: "numeric", month: "short" });
  const needsYou = plan.refills.some((r) => !r.asked) || plan.visits.length > 0;

  async function yes(medicineId: string) {
    setBusy(medicineId);
    setFailed(false);
    try {
      const done = await askRefill(medicineId);
      setPlan((p) => p && { ...p, refills: p.refills.map((r) => (r.medicine_id === medicineId ? done : r)) });
    } catch {
      setFailed(true);
    } finally {
      setBusy(null);
    }
  }

  return (
    <details className="pc-today" open={needsYou}>
      <summary>
        <span aria-hidden="true">📅</span> {t.planTitle}
      </summary>
      <div className="pc-today-body">
        {plan.refills.map((r) => {
          const who = r.ask_name ?? "";
          const vals = { n: r.left ?? 0, name: r.name, who };
          return (
            <div key={r.medicine_id} className="pc-today-refill">
              {r.asked ? (
                <p role="status">✓ {fill(t.refillAsked, vals)}</p>
              ) : (
                <>
                  <p>{fill(r.left !== null ? t.refillAsk : t.refillAskDate, vals)}</p>
                  <button
                    type="button"
                    className="pc-fine-btn"
                    disabled={busy === r.medicine_id}
                    onClick={() => void yes(r.medicine_id)}
                  >
                    {busy === r.medicine_id ? t.sending : fill(t.refillYes, vals)}
                  </button>
                </>
              )}
            </div>
          );
        })}
        {failed && <p role="alert">{t.failed}</p>}

        {plan.doses.length > 0 && (
          <section>
            <h3>{t.tablets}</h3>
            <ul>
              {plan.doses.map((d) => (
                <li key={`${d.medicine_id}-${d.time}`}>
                  <strong>{d.time}</strong> {d.name} · {d.status === "taken" ? `✓ ${t.taken}` : t.notYet}
                </li>
              ))}
            </ul>
          </section>
        )}

        {plan.visits.length > 0 && (
          <section>
            <h3>{t.visits}</h3>
            <ul>
              {plan.visits.map((v) => (
                <li key={v.id}>
                  <strong>
                    {dayName(v.day)} {v.time}
                  </strong>{" "}
                  {v.provider}
                  {v.location ? `, ${v.location}` : ""}
                </li>
              ))}
            </ul>
            {plan.visit_points.length > 0 && (
              <>
                <h3>{t.tellDoctor}</h3>
                <ul>
                  {plan.visit_points.map((p, i) => (
                    <li key={`${p.kind}-${i}`}>{point(t, p)}</li>
                  ))}
                </ul>
              </>
            )}
            <p className="pc-fine-hint">{t.pAfter}</p>
          </section>
        )}

        {plan.tasks.length > 0 && (
          <section>
            <h3>{t.todo}</h3>
            <ul>
              {plan.tasks.map((task) => (
                <li key={task}>{task}</li>
              ))}
            </ul>
          </section>
        )}

        {plan.birthdays
          .filter((b) => !b.today)
          .map((b) => (
            <p key={b.name}>🎂 {fill(circleStrings(language).birthdayTomorrow, { name: b.name })}</p>
          ))}

        {plan.doses.length + plan.visits.length + plan.tasks.length + plan.refills.length === 0 && (
          <p>{t.nothing}</p>
        )}
      </div>
    </details>
  );
}
