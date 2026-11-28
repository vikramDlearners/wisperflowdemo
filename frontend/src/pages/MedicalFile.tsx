import { useEffect, useState, type FormEvent } from "react";
import "../health-notes.css";
import "../care-circle.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import ProfilePicker, { useCareProfiles } from "../components/ProfilePicker";
import { ApiError, fetchAuthedBlob, medicalFile, type DocKind, type MedicalDocOut, type MedicalLinkOut } from "../api";

// Every prescription, lab report, scan and discharge summary in one place, searchable, with a time-limited
// link a new doctor can open without an account.

const KINDS: [DocKind, string][] = [
  ["prescription", "Prescription"],
  ["lab", "Lab report"],
  ["scan", "Scan"],
  ["discharge", "Discharge summary"],
  ["insurance", "Insurance"],
  ["other", "Other"],
];
const KIND_LABEL = Object.fromEntries(KINDS) as Record<DocKind, string>;
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
const messageOf = (e: unknown) => (e instanceof ApiError ? e.detail : "Could not save. Try again.");

function AddForm({ familyId, profileId, onAdded }: { familyId: string; profileId: string; onAdded: () => void }) {
  const [kind, setKind] = useState<DocKind | "">("");
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file && !text.trim()) {
      setError("Choose a file or type what the document says.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await medicalFile.add(familyId, profileId, { kind, title, doc_date: date, text, file });
      setKind("");
      setTitle("");
      setDate("");
      setText("");
      setFile(null);
      (e.target as HTMLFormElement).reset();
      onAdded();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="pp-card hn-form" onSubmit={(e) => void submit(e)}>
      <h2>Add a document</h2>
      <p className="pp-muted">Upload a photo or PDF. When AI reading is set up, the type, title, date and text are filled in for you.</p>
      <div className="hn-grid">
        <label className="hn-field">
          <span>File (photo or PDF)</span>
          <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <label className="hn-field">
          <span>Type</span>
          <select value={kind} onChange={(e) => setKind(e.target.value as DocKind | "")}>
            <option value="">Work it out</option>
            {KINDS.map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="hn-field">
          <span>Title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Diabetes panel, City Lab" />
        </label>
        <label className="hn-field">
          <span>Date on the document</span>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
      </div>
      <label className="hn-field">
        <span>What it says (optional with a file)</span>
        <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="HbA1c 7.1 %" />
      </label>
      {error && <p className="pp-alert" role="alert">{error}</p>}
      <button type="submit" className="pp-btn" disabled={busy}>
        {busy ? "Saving…" : "Add to the file"}
      </button>
    </form>
  );
}

function Links({ familyId, profileId }: { familyId: string; profileId: string }) {
  const [links, setLinks] = useState<MedicalLinkOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = () => medicalFile.links(familyId, profileId).then(setLinks).catch(() => setError("Could not load the links."));
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [familyId, profileId]);

  async function share(days: 1 | 7 | 30) {
    setError(null);
    try {
      await medicalFile.share(familyId, profileId, days);
      await load();
    } catch (err) {
      setError(messageOf(err));
    }
  }
  async function revoke(id: string) {
    try {
      await medicalFile.revoke(familyId, id);
      await load();
    } catch (err) {
      setError(messageOf(err));
    }
  }

  return (
    <section className="pp-card">
      <h2>Share with a doctor</h2>
      <p className="pp-muted">The doctor opens the link without an account. It stops working when it expires or you turn it off.</p>
      <div className="cc-actions">
        {([1, 7, 30] as const).map((d) => (
          <button key={d} type="button" className="pp-btn pp-btn-ghost" onClick={() => void share(d)}>
            Link for {d === 1 ? "1 day" : `${d} days`}
          </button>
        ))}
      </div>
      {error && <p className="pp-alert" role="alert">{error}</p>}
      {links.length > 0 && (
        <ul className="cc-list">
          {links.map((l) => {
            const url = `${location.origin}/medical-file/${l.token}`;
            return (
              <li key={l.id} className="cc-row">
                <div>
                  <a className="mf-link" href={url} target="_blank" rel="noreferrer">
                    {url}
                  </a>
                  <p className="pp-muted">Works until {day(l.expires_at)}</p>
                </div>
                <div className="cc-actions">
                  <button type="button" className="pp-btn pp-btn-ghost" onClick={() => void navigator.clipboard?.writeText(url)}>
                    Copy
                  </button>
                  <button type="button" className="pp-btn pp-btn-ghost" onClick={() => void revoke(l.id)}>
                    Turn off
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default function MedicalFile({ familyId }: { familyId: string }) {
  const { profiles, profileId, setProfileId } = useCareProfiles(familyId);
  const [docs, setDocs] = useState<MedicalDocOut[]>([]);
  const [q, setQ] = useState("");
  const [asked, setAsked] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = (query = asked) => {
    if (!profileId) return;
    medicalFile
      .list(familyId, profileId, query || undefined)
      .then(setDocs)
      .catch(() => setError("Could not load the file."));
  };
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [familyId, profileId]);

  async function open(d: MedicalDocOut) {
    if (!d.file_url) return;
    const url = await fetchAuthedBlob(d.file_url);
    if (url) window.open(url, "_blank", "noopener");
    else setError("Could not open the file.");
  }
  async function remove(d: MedicalDocOut) {
    if (!window.confirm(`Remove "${d.title}" from the file?`)) return;
    try {
      await medicalFile.remove(familyId, d.id);
      load();
    } catch (err) {
      setError(messageOf(err));
    }
  }

  return (
    <WorkspaceLayout familyId={familyId} current="file" title="Medical file">
      <div className="pp-content">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">Medical file · Family workspace</p>
            <h1>One medical file</h1>
            <p className="pp-muted">Prescriptions, lab reports, scans and discharge summaries. Ask it things like "When was the last HbA1c?"</p>
          </div>
          <ProfilePicker profiles={profiles} profileId={profileId} onChange={setProfileId} />
        </div>
        {profileId && (
          <>
            <form
              className="mf-search"
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                setAsked(q.trim());
                load(q.trim());
              }}
            >
              <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="When was the last HbA1c?" aria-label="Search the file" />
              <button type="submit" className="pp-btn">
                Search
              </button>
              {asked && (
                <button
                  type="button"
                  className="pp-btn pp-btn-ghost"
                  onClick={() => {
                    setQ("");
                    setAsked("");
                    load("");
                  }}
                >
                  Show all
                </button>
              )}
            </form>
            {error && <p className="pp-alert" role="alert">{error}</p>}
            {docs.length === 0 ? (
              <p className="pp-muted">{asked ? "Nothing in the file matches that." : "The file is empty. Add the first document below."}</p>
            ) : (
              <ul className="cc-list">
                {docs.map((d) => (
                  <li key={d.id} className="pp-card cc-row">
                    <div>
                      <strong>{d.title}</strong> <span className="cc-status">{KIND_LABEL[d.kind]}</span>
                      <p className="pp-muted">{d.doc_date ? day(d.doc_date) : "No date"}</p>
                      {d.match && <p><span className="mf-match">{d.match}</span></p>}
                    </div>
                    <div className="cc-actions">
                      {d.has_file && (
                        <button type="button" className="pp-btn pp-btn-ghost" onClick={() => void open(d)}>
                          Open
                        </button>
                      )}
                      <button type="button" className="pp-btn pp-btn-ghost" onClick={() => void remove(d)}>
                        Remove
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <AddForm familyId={familyId} profileId={profileId} onAdded={() => load()} />
            <Links familyId={familyId} profileId={profileId} />
          </>
        )}
      </div>
    </WorkspaceLayout>
  );
}
