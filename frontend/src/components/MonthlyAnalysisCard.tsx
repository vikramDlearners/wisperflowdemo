import type { MonthlyAnalysis } from "../api";
import "../monthly-analysis.css";

// The month's analysis, shown under the Chat answer to "Give me last month's analysis".

function rupees(n: number): string {
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
}

function day(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function plural(n: number, word: string, many = `${word}s`): string {
  return `${n} ${n === 1 ? word : many}`;
}

const INCIDENT_LABEL: Record<MonthlyAnalysis["incidents"][number]["kind"], string> = {
  emergency: "Emergency",
  urgent: "Felt unwell",
  important: "Important",
};

const SPEND_KIND: Record<string, string> = { medicine: "💊", appointment: "🩺", insurance: "⛨" };

export default function MonthlyAnalysisCard({ data }: { data: MonthlyAnalysis }) {
  const { medicines: med, spending: spend, conversations: talk, incidents, diet, notes } = data;
  const mealTotal = diet.meals.breakfast + diet.meals.lunch + diet.meals.dinner;

  return (
    <section className="ma-card" aria-label={`${data.period.label} analysis for ${data.parent.name}`}>
      <header className="ma-head">
        <span aria-hidden="true">📊</span>
        <div>
          <strong>{data.period.label} analysis</strong>
          <small>{data.parent.name}</small>
        </div>
      </header>

      <div className="ma-tiles">
        {med && (
          <div className="ma-tile">
            <span className="ma-tile-icon" aria-hidden="true">💊</span>
            <strong>
              {med.taken}
              {med.recorded > 0 && <small> / {med.recorded}</small>}
            </strong>
            <span>Medicines taken</span>
            <em>{med.taken_percent === null ? "No doses recorded" : `${med.taken_percent}% of recorded doses`}</em>
          </div>
        )}
        {spend && (
          <div className="ma-tile">
            <span className="ma-tile-icon" aria-hidden="true">₹</span>
            <strong>{rupees(spend.total)}</strong>
            <span>Total spent</span>
            <em>{spend.item_count ? plural(spend.item_count, "payment") : "Nothing recorded"}</em>
          </div>
        )}
        <div className="ma-tile">
          <span className="ma-tile-icon" aria-hidden="true">💬</span>
          <strong>{talk.conversations}</strong>
          <span>Conversations</span>
          <em>
            Talked on {talk.days_talked} of {talk.days_in_month} days
          </em>
        </div>
        <div className={`ma-tile${incidents.length ? " is-alert" : ""}`}>
          <span className="ma-tile-icon" aria-hidden="true">⚠️</span>
          <strong>{incidents.length}</strong>
          <span>Major incidents</span>
          <em>{incidents.length ? "See below" : "A calm month"}</em>
        </div>
      </div>

      {med && med.by_medicine.length > 0 && (
        <div className="ma-section">
          <h3>Medicines</h3>
          <ul className="ma-bars">
            {med.by_medicine.map((m) => {
              const all = m.taken + m.missed + m.skipped || 1;
              return (
                <li key={m.name}>
                  <div className="ma-bar-label">
                    <span>{m.name}</span>
                    <small>
                      {m.taken} taken{m.missed ? ` · ${m.missed} missed` : ""}
                      {m.skipped ? ` · ${m.skipped} skipped` : ""}
                    </small>
                  </div>
                  <div className="ma-bar" aria-hidden="true">
                    <span className="is-taken" style={{ width: `${(100 * m.taken) / all}%` }} />
                    <span className="is-missed" style={{ width: `${(100 * m.missed) / all}%` }} />
                    <span className="is-skipped" style={{ width: `${(100 * m.skipped) / all}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {spend && spend.total > 0 && (
        <div className="ma-section">
          <h3>Money spent</h3>
          <div className="ma-split">
            {!!spend.medicines && (
              <span>
                Medicines <b>{rupees(spend.medicines)}</b>
              </span>
            )}
            {!!spend.appointments && (
              <span>
                Doctor visits <b>{rupees(spend.appointments)}</b>
              </span>
            )}
            {!!spend.insurance && (
              <span>
                Insurance <b>{rupees(spend.insurance)}</b>
              </span>
            )}
          </div>
          <ul className="ma-list">
            {spend.items.map((i, n) => (
              <li key={n}>
                <span aria-hidden="true">{SPEND_KIND[i.kind]}</span>
                <span className="ma-grow">{i.label}</span>
                <small>{day(i.date)}</small>
                <b>{rupees(i.amount)}</b>
              </li>
            ))}
          </ul>
          {spend.item_count > spend.items.length && (
            <p className="ma-more">And {spend.item_count - spend.items.length} smaller payments.</p>
          )}
        </div>
      )}

      {incidents.length > 0 && (
        <div className="ma-section">
          <h3>Major incidents</h3>
          <ul className="ma-list">
            {incidents.map((i, n) => (
              <li key={n}>
                <span className={`ma-badge is-${i.kind}`}>{INCIDENT_LABEL[i.kind]}</span>
                <span className="ma-grow">{i.text}</span>
                <small>{day(i.date)}</small>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="ma-section">
        <h3>Diet</h3>
        {diet.days_reported === 0 ? (
          <p className="ma-muted">No meals were reported this month.</p>
        ) : (
          <>
            {diet.summary && <p>{diet.summary}</p>}
            <div className="ma-meals">
              <span>
                🌅 <b>{diet.meals.breakfast}</b> breakfasts
              </span>
              <span>
                ☀️ <b>{diet.meals.lunch}</b> lunches
              </span>
              <span>
                🌙 <b>{diet.meals.dinner}</b> dinners
              </span>
              {diet.skipped > 0 && (
                <span className="is-alert">
                  <b>{diet.skipped}</b> skipped
                </span>
              )}
            </div>
            {mealTotal + diet.skipped > 0 && diet.recent.length > 0 && (
              <ul className="ma-list ma-recent">
                {diet.recent.map((r, n) => (
                  <li key={n}>
                    <small>{day(r.date)}</small>
                    <span className="ma-grow">
                      {r.meals.length > 0 && <em>{r.meals.join(", ")}: </em>}
                      {r.text}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      {notes.length > 0 && (
        <div className="ma-section">
          <h3>Other notes</h3>
          <ul className="ma-list ma-notes">
            {notes.map((n, i) => (
              <li key={i}>
                <div>
                  <small>
                    {n.source} · {day(n.date)}
                  </small>
                  <span>{n.text}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <footer className="ma-foot">
        {data.source === "ai" ? "Summary written by AI from the app's records." : "From the app's records."} Not
        medical advice.
      </footer>
    </section>
  );
}
