import { useEffect, useState, type FormEvent } from "react";
import "../health-notes.css";
import "../care-circle.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import ProfilePicker, { useCareProfiles } from "../components/ProfilePicker";
import { ApiError, siblings, type SharingOut } from "../api";

// Brothers and sisters sharing care: who paid for what and who owes whom, who visited this month,
// and who went to the last appointment.

const rupees = (n: number) => `₹${Math.abs(n).toLocaleString("en-IN")}`;
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
const today = () => new Date().toLocaleDateString("en-CA");
const messageOf = (e: unknown) => (e instanceof ApiError ? e.detail : "Could not save. Try again.");

export default function Sharing({ familyId }: { familyId: string }) {
  const { profiles, profileId, setProfileId } = useCareProfiles(familyId);
  const [data, setData] = useState<SharingOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [what, setWhat] = useState("");
  const [spentOn, setSpentOn] = useState(today());
  const [paidBy, setPaidBy] = useState("");
  const [visitDate, setVisitDate] = useState(today());
  const [visitNote, setVisitNote] = useState("");

  const load = () => {
    if (!profileId) return;
    siblings.get(familyId, profileId).then(setData).catch(() => setError("Could not load sharing."));
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

  async function addExpense(e: FormEvent) {
    e.preventDefault();
    const ok = await run(() =>
      siblings.addExpense(familyId, profileId, {
        amount: Number(amount),
        what: what.trim(),
        spent_on: spentOn,
        paid_by_user_id: paidBy || null,
      }),
    );
    if (ok) {
      setAmount("");
      setWhat("");
    }
  }
  async function addVisit(e: FormEvent) {
    e.preventDefault();
    const ok = await run(() =>
      siblings.addVisit(familyId, profileId, { visit_date: visitDate, appointment_id: null, note: visitNote.trim() || null }),
    );
    if (ok) setVisitNote("");
  }

  const last = data?.last_appointment;
  return (
    <WorkspaceLayout familyId={familyId} current="sharing" title="Sharing care">
      <div className="pp-content">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">Sharing care · Family workspace</p>
            <h1>Sharing the care</h1>
            <p className="pp-muted">Costs are split equally between the family members who are not the parent or a carer.</p>
          </div>
          <ProfilePicker profiles={profiles} profileId={profileId} onChange={setProfileId} />
        </div>
        {error && <p className="pp-alert" role="alert">{error}</p>}
        {data && (
          <>
            <section className="pp-card">
              <h2>Money</h2>
              <p>
                {rupees(data.total)} spent in all · {rupees(data.share)} each
              </p>
              <ul className="cc-list">
                {data.balances.map((b) => (
                  <li key={b.user_id} className="cc-row">
                    <span>
                      <strong>{b.name}</strong> paid {rupees(b.paid)}
                    </span>
                    <span className={b.balance > 0 ? "sh-plus" : b.balance < 0 ? "sh-minus" : "pp-muted"}>
                      {b.balance > 0 ? `is owed ${rupees(b.balance)}` : b.balance < 0 ? `owes ${rupees(b.balance)}` : "settled"}
                    </span>
                  </li>
                ))}
              </ul>
              <form className="hn-form" onSubmit={(e) => void addExpense(e)}>
                <div className="hn-grid">
                  <label className="hn-field">
                    <span>Amount (₹)</span>
                    <input type="number" min="1" required inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
                  </label>
                  <label className="hn-field">
                    <span>What for</span>
                    <input required value={what} onChange={(e) => setWhat(e.target.value)} placeholder="Physio, groceries…" />
                  </label>
                  <label className="hn-field">
                    <span>Date</span>
                    <input type="date" required value={spentOn} onChange={(e) => setSpentOn(e.target.value)} />
                  </label>
                  <label className="hn-field">
                    <span>Paid by</span>
                    <select value={paidBy} onChange={(e) => setPaidBy(e.target.value)}>
                      <option value="">Me</option>
                      {data.members.map((m) => (
                        <option key={m.user_id} value={m.user_id}>
                          {m.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <button type="submit" className="pp-btn">
                  Add expense
                </button>
              </form>
              {data.expenses.length > 0 && (
                <ul className="cc-list">
                  {data.expenses.map((x) => (
                    <li key={x.id} className="cc-row">
                      <span>
                        {day(x.spent_on)} · {x.what} · <strong>{rupees(x.amount)}</strong> by {x.paid_by}
                      </span>
                      <button
                        type="button"
                        className="pp-btn pp-btn-ghost"
                        onClick={() => void run(() => siblings.removeExpense(familyId, x.id))}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="pp-card">
              <h2>Visits this month</h2>
              {data.visits_this_month.length === 0 ? (
                <p className="pp-muted">No visits logged this month.</p>
              ) : (
                <ul className="cc-list">
                  {data.visits_this_month.map((v) => (
                    <li key={v.user_id} className="cc-row">
                      <strong>{v.name}</strong>
                      <span>{v.count === 1 ? "1 visit" : `${v.count} visits`}</span>
                    </li>
                  ))}
                </ul>
              )}
              <form className="hn-form" onSubmit={(e) => void addVisit(e)}>
                <div className="hn-grid">
                  <label className="hn-field">
                    <span>I visited on</span>
                    <input type="date" required value={visitDate} onChange={(e) => setVisitDate(e.target.value)} />
                  </label>
                  <label className="hn-field">
                    <span>Note</span>
                    <input value={visitNote} onChange={(e) => setVisitNote(e.target.value)} placeholder="Sunday lunch" />
                  </label>
                </div>
                <button type="submit" className="pp-btn">
                  Log my visit
                </button>
              </form>
            </section>

            <section className="pp-card">
              <h2>Last appointment</h2>
              {!last ? (
                <p className="pp-muted">No past appointments.</p>
              ) : (
                <div className="cc-row">
                  <span>
                    {day(last.date)} · {[last.provider, last.reason].filter(Boolean).join(" · ") || "Appointment"}
                    <br />
                    {last.went ? <strong>{last.went} went.</strong> : <span className="pp-muted">Nobody has said they went.</span>}
                  </span>
                  {!last.went && (
                    <button
                      type="button"
                      className="pp-btn"
                      onClick={() =>
                        void run(() =>
                          siblings.addVisit(familyId, profileId, { visit_date: last.date, appointment_id: last.id, note: null }),
                        )
                      }
                    >
                      I went
                    </button>
                  )}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </WorkspaceLayout>
  );
}
