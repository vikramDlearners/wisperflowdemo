import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import "../health-notes.css";
import "../care-circle.css";
import { API_BASE_URL, ApiError, medicalFile, type SharedFileOut } from "../api";

// What a doctor sees from a shared link: the medical card and every document, with no sign-in.

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });

export default function SharedMedicalFile() {
  const { token = "" } = useParams();
  const [file, setFile] = useState<SharedFileOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    medicalFile.shared(token).then(setFile, (err: unknown) => {
      const status = err instanceof ApiError ? err.status : 0;
      setError(
        status === 410 || status === 404
          ? "This link has expired or was turned off. Ask the family for a new one."
          : "Could not load the file. Check your connection and try again.",
      );
    });
  }, [token]);

  if (error)
    return (
      <main className="pp-content">
        <p className="pp-alert" role="alert">{error}</p>
      </main>
    );
  if (!file) return <main className="pp-content"><p className="pp-muted">Loading…</p></main>;
  const c = file.card;
  const facts: [string, string | null][] = [
    ["Blood group", c.blood_group],
    ["Allergies", c.allergies],
    ["Medicines", c.medicines.join(", ") || null],
    ["Doctor", [c.doctor, c.doctor_phone].filter(Boolean).join(" · ") || null],
    ["Hospital", c.hospital],
    ["Emergency contact", c.emergency_contact ? `${c.emergency_contact.name} · ${c.emergency_contact.phone}` : null],
    ["Notes", c.notes],
  ];

  return (
    <main className="pp-content">
      <div className="pp-page-head">
        <div>
          <p className="pp-eyebrow">Shared medical file · link works until {day(file.expires_at)}</p>
          <h1>{c.name}</h1>
        </div>
      </div>
      <section className="pp-card">
        <dl>
          {facts
            .filter(([, v]) => v)
            .map(([k, v]) => (
              <div key={k}>
                <dt className="pp-muted">{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
        </dl>
      </section>
      <h2>Documents</h2>
      {file.documents.length === 0 && <p className="pp-muted">No documents yet.</p>}
      <ul className="cc-list">
        {file.documents.map((d) => (
          <li key={d.id} className="pp-card cc-row">
            <div>
              <strong>{d.title}</strong>
              <p className="pp-muted">{d.doc_date ? day(d.doc_date) : "No date"}</p>
              {d.text && <p style={{ whiteSpace: "pre-line" }}>{d.text}</p>}
            </div>
            {d.file_url && (
              <a className="pp-btn pp-btn-ghost" href={`${API_BASE_URL}${d.file_url}`} target="_blank" rel="noreferrer">
                Open {d.file_name ?? "file"}
              </a>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
