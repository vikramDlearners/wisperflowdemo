import { useEffect, useState, type FormEvent } from "react";
import "../health-notes.css";
import "../care-circle.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import ProfilePicker, { useCareProfiles } from "../components/ProfilePicker";
import { ApiError, paperwork, type PaperKind, type PaperOut } from "../api";

// The yearly chores that come with an older parent: the pension life certificate, income tax, bank KYC,
// property tax, plus insurance renewals from the insurance page.

const KINDS: [PaperKind, string][] = [
  ["life_certificate", "Pension life certificate"],
  ["income_tax", "Income tax return"],
  ["bank_kyc", "Bank KYC"],
  ["property_tax", "Property tax"],
  ["other", "Something else"],
];
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
const messageOf = (e: unknown) => (e instanceof ApiError ? e.detail : "Could not save. Try again.");

function dueText(p: PaperOut) {
  if (p.days_left === null) return "";
  if (p.days_left < 0) return `${-p.days_left} days late`;
  if (p.days_left === 0) return "due today";
  return `in ${p.days_left} days`;
}

export default function Paperwork({ familyId }: { familyId: string }) {
  const { profiles, profileId, setProfileId } = useCareProfiles(familyId);
  const [rows, setRows] = useState<PaperOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [kind, setKind] = useState<PaperKind>("other");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");

  const load = () => {
    if (!profileId) return;
    paperwork.list(familyId, profileId).then(setRows).catch(() => setError("Could not load paperwork."));
  };
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [familyId, profileId]);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    setInfo(null);
    try {
      await action();
      load();
      return true;
    } catch (err) {
      setError(messageOf(err));
      return false;
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    const ok = await run(() =>
      paperwork.add(familyId, profileId, { kind, title: title.trim() || null, due_date: due, note: note.trim() || null }),
    );
    if (ok) {
      setTitle("");
      setDue("");
      setNote("");
    }
  }

  return (
    <WorkspaceLayout familyId={familyId} current="paperwork" title="Paperwork">
      <div className="pp-content">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">Paperwork · Family workspace</p>
            <h1>Paperwork</h1>
            <p className="pp-muted">
              Usual dates are a starting point. Property tax dates differ by city, so change them to match yours.
            </p>
          </div>
          <ProfilePicker profiles={profiles} profileId={profileId} onChange={setProfileId} />
        </div>
        {profileId && (
          <>
            <div className="cc-actions">
              <button
                type="button"
                className="pp-btn pp-btn-ghost"
                onClick={() =>
                  void run(async () => {
                    const r = await paperwork.addUsual(familyId, profileId);
                    setInfo(r.added ? `Added ${r.added} usual items.` : "The usual items are already on the list.");
                  })
                }
              >
                Add the usual
              </button>
            </div>
            {error && <p className="pp-alert" role="alert">{error}</p>}
            {info && <p role="status">{info}</p>}
            {rows.length === 0 ? (
              <p className="pp-muted">Nothing due. Add the usual yearly items or your own below.</p>
            ) : (
              <ul className="cc-list">
                {rows.map((p) => (
                  <li key={`${p.source}-${p.id}`} className="pp-card cc-row">
                    <div>
                      <strong>{p.title}</strong>
                      <p>
                        {day(p.due_date)}{" "}
                        <span className={p.days_left !== null && p.days_left <= 14 ? "pw-soon" : "pp-muted"}>{dueText(p)}</span>
                      </p>
                      {p.note && <p className="pp-muted">{p.note}</p>}
                    </div>
                    {p.source === "paperwork" && (
                      <div className="cc-actions">
                        <button
                          type="button"
                          className="pp-btn"
                          onClick={() =>
                            void run(async () => {
                              const r = await paperwork.done(familyId, p.id);
                              setInfo(r.next_due ? `Done. Next one is due ${day(r.next_due)}.` : "Done.");
                            })
                          }
                        >
                          Done
                        </button>
                        <button
                          type="button"
                          className="pp-btn pp-btn-ghost"
                          onClick={() => window.confirm(`Delete "${p.title}"?`) && void run(() => paperwork.remove(familyId, p.id))}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                    {p.source === "insurance" && <span className="pp-muted">From the insurance page</span>}
                  </li>
                ))}
              </ul>
            )}
            <form className="pp-card hn-form" onSubmit={(e) => void add(e)}>
              <h2>Add a reminder</h2>
              <div className="hn-grid">
                <label className="hn-field">
                  <span>What</span>
                  <select value={kind} onChange={(e) => setKind(e.target.value as PaperKind)}>
                    {KINDS.map(([k, label]) => (
                      <option key={k} value={k}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="hn-field">
                  <span>Title</span>
                  <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Leave blank to use the type" />
                </label>
                <label className="hn-field">
                  <span>Due</span>
                  <input type="date" required value={due} onChange={(e) => setDue(e.target.value)} />
                </label>
                <label className="hn-field">
                  <span>Note</span>
                  <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="SBI branch, Anna Nagar" />
                </label>
              </div>
              <button type="submit" className="pp-btn">
                Add
              </button>
            </form>
          </>
        )}
      </div>
    </WorkspaceLayout>
  );
}
