import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import TimeSelect from "../components/TimeSelect";
import { Link, useSearchParams } from "react-router-dom";
import "../medicines.css";
import "../prescription-scan.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { createCareProfileFromOnboarding } from "../careProfileSetup";
import {
  ApiError,
  careProfiles,
  confirmPrescriptionScan,
  getPrescriptionScan,
  members,
  uploadPrescriptionScan,
  type CareProfileOut,
  type MemberOut,
  type PrescriptionMedicineIn,
  type PrescriptionScanOut,
} from "../api";

// Prescription scan flow: Upload -> Review -> Done.
//   POST   .../prescription-scans               upload (201 pending_review | 201 rejected | 400 | 401)
//   GET    .../prescription-scans/{scanId}      resume via ?scan=&profile= (200 | 404)
//   POST   .../prescription-scans/{scanId}/confirm  (200 | 400 not pending | 422 bad time)

interface PrescriptionScanProps {
  familyId: string;
}

interface MedicineRow {
  key: number;
  name: string;
  dose: string;
  instructions: string;
  times: string[]; // 24-hour "HH:MM"
  responsible: string; // user id or ""
}

// Errors are tied to a place on the page so they show next to what caused them.
type ScanError =
  | { kind: "auth" }
  | { kind: "upload"; message: string }
  | { kind: "notFound" }
  | { kind: "notPending"; message: string }
  | { kind: "review"; message: string; row?: number; time?: number }
  | { kind: "general"; message: string };

const ACCEPT = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 10 * 1024 * 1024;
const HH_MM = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;

let nextKey = 1;
const newRow = (m?: PrescriptionMedicineIn): MedicineRow => ({
  key: nextKey++,
  name: m?.name ?? "",
  dose: m?.dose ?? "",
  instructions: m?.instructions ?? "",
  times: m?.times?.length ? [...m.times] : ["08:00"],
  responsible: m?.responsible_user_id ?? "",
});

function formatSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// FastAPI 422 bodies arrive as a JSON string in ApiError.detail; pull out the first problem.
function parseValidation(detail: string): { message: string; row?: number; time?: number } {
  try {
    const items = JSON.parse(detail) as { loc?: (string | number)[]; msg?: string }[];
    const first = Array.isArray(items) ? items[0] : undefined;
    if (!first) return { message: detail };
    const loc = first.loc ?? [];
    const mi = loc.indexOf("medicines");
    const row = mi >= 0 && typeof loc[mi + 1] === "number" ? (loc[mi + 1] as number) : undefined;
    const ti = loc.indexOf("times");
    const time = ti >= 0 && typeof loc[ti + 1] === "number" ? (loc[ti + 1] as number) : undefined;
    const msg = (first.msg ?? "Please check the details").replace(/^Value error,\s*/i, "");
    return { message: msg.charAt(0).toUpperCase() + msg.slice(1), row, time };
  } catch {
    return { message: detail };
  }
}

function docLabel(type: string): string {
  if (type === "invoice") return "an invoice";
  if (type === "prescription") return "a prescription";
  return "not a prescription";
}

export default function PrescriptionScan({ familyId }: PrescriptionScanProps) {
  const [params, setParams] = useSearchParams();
  const scanParam = params.get("scan");
  const profileParam = params.get("profile");

  const [profiles, setProfiles] = useState<CareProfileOut[]>([]);
  const [people, setPeople] = useState<MemberOut[]>([]);
  const [careProfileId, setCareProfileId] = useState("");
  const [loading, setLoading] = useState(true);

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);

  const [scan, setScan] = useState<PrescriptionScanOut | null>(null);
  const [rows, setRows] = useState<MedicineRow[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<{ medicines: number; notified: number } | null>(null);
  const [error, setError] = useState<ScanError | null>(null);

  const fileInput = useRef<HTMLInputElement>(null);

  // Load care profiles + members, and resume a scan from the URL if present.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([careProfiles.list(familyId), members.list(familyId).catch(() => [] as MemberOut[])])
      .then(async ([list, memberList]) => {
        if (cancelled) return;
        setProfiles(list);
        setPeople(memberList);
        const profile = profileParam && list.some((p) => p.id === profileParam) ? profileParam : list.length === 1 || scanParam ? list[0]?.id ?? "" : "";
        setCareProfileId(profile);
        if (scanParam && profile) {
          try {
            const s = await getPrescriptionScan(familyId, profile, scanParam);
            if (!cancelled) showScan(s);
          } catch (err) {
            if (!cancelled) handleError(err, "load");
          }
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) handleError(err, "load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // Resume only on first load / family change, not on our own URL updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [familyId]);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function showScan(s: PrescriptionScanOut) {
    setScan(s);
    setRows((s.proposed?.medicines ?? []).map((m) => newRow(m)));
    setError(null);
  }

  function handleError(err: unknown, stage: "load" | "upload" | "confirm") {
    if (err instanceof ApiError) {
      if (err.status === 401) return setError({ kind: "auth" });
      if (stage === "load" && err.status === 404) return setError({ kind: "notFound" });
      if (stage === "upload" && (err.status === 400 || err.status === 413 || err.status === 422))
        return setError({ kind: "upload", message: err.detail });
      if (stage === "confirm" && err.status === 400) return setError({ kind: "notPending", message: err.detail });
      if (stage === "confirm" && err.status === 422) return setError({ kind: "review", ...parseValidation(err.detail) });
      return setError({ kind: "general", message: err.detail });
    }
    setError({ kind: "general", message: "Something went wrong. Please check your connection and try again." });
  }

  function pickFile(f: File | null | undefined) {
    setError(null);
    if (!f) return;
    if (!ACCEPT.includes(f.type)) {
      setFile(null);
      setError({ kind: "upload", message: "Unsupported file type. Upload a JPG, PNG or WebP photo." });
      return;
    }
    if (f.size > MAX_BYTES) {
      setFile(null);
      setError({ kind: "upload", message: "This photo is larger than 10 MB. Please use a smaller one." });
      return;
    }
    setFile(f);
  }

  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setDragOver(false);
    pickFile(e.dataTransfer.files?.[0]);
  }

  // Scans are filed under a care profile; create one first if the family has none.
  async function ensureCareProfile(): Promise<string> {
    if (careProfileId) return careProfileId;
    const created = await createCareProfileFromOnboarding(familyId);
    setProfiles([created]);
    setCareProfileId(created.id);
    return created.id;
  }

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const profileId = await ensureCareProfile();
      const s = await uploadPrescriptionScan(familyId, profileId, file);
      showScan(s);
      setParams({ scan: s.id, profile: profileId }, { replace: true });
    } catch (err) {
      handleError(err, "upload");
    } finally {
      setUploading(false);
    }
  }

  async function reloadScan() {
    if (!scan) return;
    try {
      showScan(await getPrescriptionScan(familyId, careProfileId, scan.id));
    } catch (err) {
      handleError(err, "load");
    }
  }

  function startOver() {
    setScan(null);
    setRows([]);
    setFile(null);
    setResult(null);
    setError(null);
    setParams({}, { replace: true });
  }

  const updateRow = (key: number, patch: Partial<MedicineRow>) =>
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  async function handleConfirm(e: FormEvent) {
    e.preventDefault();
    if (!scan) return;
    const medicines: PrescriptionMedicineIn[] = [];
    for (const [i, row] of rows.entries()) {
      const name = row.name.trim();
      if (!name) return setError({ kind: "review", message: "Every medicine needs a name.", row: i });
      const times = row.times.map((t) => t.trim()).filter(Boolean);
      if (times.length === 0)
        return setError({ kind: "review", message: `Add at least one time for ${name}.`, row: i });
      const bad = times.findIndex((t) => !HH_MM.test(t));
      if (bad >= 0)
        return setError({ kind: "review", message: `Time must be 24-hour HH:MM: ${times[bad]}`, row: i, time: bad });
      medicines.push({
        name,
        dose: row.dose.trim() || null,
        instructions: row.instructions.trim() || null,
        times,
        responsible_user_id: row.responsible || null,
      });
    }
    if (medicines.length === 0) return setError({ kind: "review", message: "Add at least one medicine to confirm." });

    setConfirming(true);
    setError(null);
    try {
      const out = await confirmPrescriptionScan(familyId, careProfileId, scan.id, { medicines });
      setResult({ medicines: out.medicine_ids.length, notified: out.notified_user_ids.length });
      setScan({ ...scan, status: "confirmed" });
    } catch (err) {
      handleError(err, "confirm");
    } finally {
      setConfirming(false);
    }
  }

  const step = scan?.status === "confirmed" ? 3 : scan?.status === "pending_review" ? 2 : 1;
  const medsPath = `/family/${familyId}/medicines`;
  const reviewErr = error?.kind === "review" ? error : null;

  return (
    <WorkspaceLayout familyId={familyId} current="medicines" title="Scan prescription">
      <div className="pp-content">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">
              <Link to={medsPath} className="mf-back">
                ← Medicines
              </Link>
            </p>
            <h1>Scan prescription</h1>
            <p className="pp-muted">
              Upload a photo of the doctor's prescription. Check what CareCircle reads, then confirm to add the
              medicines and reminders.
            </p>
          </div>
        </div>

        <ol className="ps-steps" aria-label="Progress">
          {["Upload photo", "Review medicines", "Done"].map((label, i) => (
            <li
              key={label}
              className={`ps-step${step === i + 1 ? " is-current" : ""}${step > i + 1 ? " is-done" : ""}`}
              aria-current={step === i + 1 ? "step" : undefined}
            >
              <span className="ps-step-n">{step > i + 1 ? "✓" : i + 1}</span>
              <span className="ps-step-label">{label}</span>
            </li>
          ))}
        </ol>

        {loading && <p role="status" className="pp-muted">Loading…</p>}

        {error?.kind === "auth" && (
          <div className="ps-banner ps-banner-error" role="alert">
            <strong>Your session has expired.</strong>
            <span>Sign in again to upload or review prescriptions.</span>
            <Link to="/start" className="pp-btn md-btn-link">Sign in</Link>
          </div>
        )}
        {error?.kind === "general" && (
          <div className="ps-banner ps-banner-error" role="alert">
            <strong>Something went wrong.</strong>
            <span>{error.message}</span>
          </div>
        )}
        {error?.kind === "notFound" && (
          <div className="ps-banner ps-banner-warn" role="alert">
            <strong>We couldn't find that scan.</strong>
            <span>It may belong to another care profile or have been removed. Upload the photo again.</span>
            <button type="button" className="pp-btn" onClick={startOver}>Upload a new photo</button>
          </div>
        )}

        {/* Step 1: upload (also shown again after a rejected document) */}
        {!loading && step === 1 && error?.kind !== "auth" && error?.kind !== "notFound" && (
          <div className="ps-grid">
            <form className="pp-card" onSubmit={handleUpload}>
              <div className="pp-card-head">
                <h2>Prescription photo</h2>
              </div>

              {scan?.status === "rejected" && (
                <div className="ps-banner ps-banner-warn ps-inline" role="alert">
                  <strong>This looks like {docLabel(scan.document_type)}.</strong>
                  <span>No medicines were added. Please upload a photo of the doctor's prescription instead.</span>
                </div>
              )}

              {profiles.length > 0 && (
                <label className="pp-field ps-profile">
                  Who are these medicines for?
                  <select required value={careProfileId} onChange={(e) => setCareProfileId(e.target.value)}>
                    <option value="" disabled>
                      Select a profile
                    </option>
                    {profiles.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.display_name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <label
                className={`ps-drop${dragOver ? " is-over" : ""}${error?.kind === "upload" ? " is-error" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
              >
                <input
                  ref={fileInput}
                  type="file"
                  accept={ACCEPT.join(",")}
                  className="ps-file"
                  onChange={(e) => {
                    pickFile(e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
                {file && preview ? (
                  <span className="ps-chosen">
                    <img src={preview} alt="" className="ps-thumb" />
                    <span className="ps-chosen-text">
                      <strong>{file.name}</strong>
                      <span className="md-sub">{formatSize(file.size)} · Click to choose a different photo</span>
                    </span>
                  </span>
                ) : (
                  <span className="ps-drop-empty">
                    <span className="ps-drop-icon" aria-hidden="true">⤒</span>
                    <strong>Drop a photo here or click to browse</strong>
                    <span className="md-sub">JPG, PNG or WebP · up to 10 MB</span>
                  </span>
                )}
              </label>
              {error?.kind === "upload" && (
                <p role="alert" className="ps-field-error">{error.message}</p>
              )}

              <div className="ps-actions">
                <Link to={medsPath} className="pp-btn pp-btn-ghost md-btn-link">Cancel</Link>
                <button type="submit" className="pp-btn" disabled={!file || uploading || (profiles.length > 0 && !careProfileId)}>
                  {uploading ? "Reading prescription…" : "Upload and read"}
                </button>
              </div>
            </form>

            <aside className="pp-card ps-tips">
              <h2>For the best result</h2>
              <ul>
                <li>Lay the prescription flat in good light.</li>
                <li>Fit the whole page in the photo, with no fingers covering text.</li>
                <li>One prescription per photo. Bills and invoices are not read.</li>
              </ul>
            </aside>
          </div>
        )}

        {/* Step 2: review proposed medicines */}
        {step === 2 && scan && (
          <form onSubmit={handleConfirm} noValidate>
            {error?.kind === "notPending" && (
              <div className="ps-banner ps-banner-warn" role="alert">
                <strong>This scan can't be confirmed any more.</strong>
                <span>{error.message}. It may already have been confirmed by someone else.</span>
                <button type="button" className="pp-btn pp-btn-ghost" onClick={reloadScan}>Refresh scan</button>
              </div>
            )}
            {reviewErr && reviewErr.row === undefined && (
              <div className="ps-banner ps-banner-error" role="alert">
                <span>{reviewErr.message}</span>
              </div>
            )}

            <section className="pp-card">
              <div className="pp-card-head">
                <h2>
                  Review medicines <span className="ps-count">{rows.length}</span>
                </h2>
                <span className="pp-badge">Pending review</span>
              </div>
              <p className="pp-muted ps-lead">
                Check each name, dose and time against the prescription. Times use the 24-hour clock.
              </p>

              {rows.length === 0 && (
                <p className="ps-empty">No medicines were found on this prescription. Add them below.</p>
              )}

              <div className="ps-meds">
                {rows.map((row, i) => {
                  const rowErr = reviewErr && reviewErr.row === i ? reviewErr : null;
                  return (
                    <fieldset key={row.key} className={`ps-med${rowErr ? " is-error" : ""}`}>
                      <legend className="ps-med-head">
                        <span className="md-med-icon md-tone-green" aria-hidden="true">✚</span>
                        Medicine {i + 1}
                      </legend>
                      <button
                        type="button"
                        className="ps-remove"
                        aria-label={`Remove medicine ${i + 1}`}
                        onClick={() => setRows((prev) => prev.filter((r) => r.key !== row.key))}
                      >
                        Remove
                      </button>

                      <div className="ps-med-fields">
                        <label className="pp-field">
                          Name
                          <input
                            required
                            maxLength={255}
                            value={row.name}
                            onChange={(e) => updateRow(row.key, { name: e.target.value })}
                          />
                        </label>
                        <label className="pp-field">
                          Dose
                          <input
                            maxLength={120}
                            placeholder="e.g. 5 mg"
                            value={row.dose}
                            onChange={(e) => updateRow(row.key, { dose: e.target.value })}
                          />
                        </label>
                        <label className="pp-field ps-wide">
                          Instructions
                          <input
                            maxLength={2000}
                            placeholder="e.g. after food"
                            value={row.instructions}
                            onChange={(e) => updateRow(row.key, { instructions: e.target.value })}
                          />
                        </label>

                        <div className="pp-field ps-wide">
                          <span id={`times-${row.key}`}>Reminder times</span>
                          <div className="ps-times" role="group" aria-labelledby={`times-${row.key}`}>
                            {row.times.map((t, ti) => (
                              <span
                                key={ti}
                                className={`ps-time${rowErr && rowErr.time === ti ? " is-error" : ""}`}
                              >
                                <TimeSelect
                                  value={t}
                                  ariaLabel={`Time ${ti + 1}`}
                                  onChange={(v) => {
                                    const times = [...row.times];
                                    times[ti] = v;
                                    updateRow(row.key, { times });
                                  }}
                                />
                                {row.times.length > 1 && (
                                  <button
                                    type="button"
                                    aria-label={`Remove time ${ti + 1}`}
                                    onClick={() =>
                                      updateRow(row.key, { times: row.times.filter((_, x) => x !== ti) })
                                    }
                                  >
                                    ×
                                  </button>
                                )}
                              </span>
                            ))}
                            <button
                              type="button"
                              className="ps-add-time"
                              onClick={() => updateRow(row.key, { times: [...row.times, "12:00"] })}
                            >
                              + Add time
                            </button>
                          </div>
                        </div>

                        <label className="pp-field ps-wide">
                          Responsible caregiver
                          <select
                            value={row.responsible}
                            onChange={(e) => updateRow(row.key, { responsible: e.target.value })}
                          >
                            <option value="">Unassigned</option>
                            {people.map((p) => (
                              <option key={p.user_id} value={p.user_id}>
                                {p.display_name} · {p.role_name}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>

                      {rowErr && (
                        <p role="alert" className="ps-field-error">
                          {rowErr.message}
                        </p>
                      )}
                    </fieldset>
                  );
                })}
              </div>

              <button
                type="button"
                className="ps-add-med"
                onClick={() => setRows((prev) => [...prev, newRow()])}
                disabled={rows.length >= 50}
              >
                + Add another medicine
              </button>
            </section>

            <div className="md-note ps-note">
              <span className="md-note-icon" aria-hidden="true">ⓘ</span>
              <div>
                <strong>You are confirming, not CareCircle</strong>
                <p>
                  CareCircle only reads the photo. Medicines are added exactly as you confirm them here, and CareCircle
                  does not recommend or change treatment.
                </p>
              </div>
            </div>

            <div className="ps-actions ps-actions-bar">
              <button type="button" className="pp-btn pp-btn-ghost" onClick={startOver} disabled={confirming}>
                Start over
              </button>
              <button type="submit" className="pp-btn" disabled={confirming || rows.length === 0}>
                {confirming
                  ? "Confirming…"
                  : `Confirm ${rows.length} medicine${rows.length === 1 ? "" : "s"}`}
              </button>
            </div>
          </form>
        )}

        {/* Step 3: done */}
        {step === 3 && (
          <section className="pp-card ps-done" role="status">
            <span className="ps-done-icon" aria-hidden="true">✓</span>
            <h2>Medicines added</h2>
            <p className="pp-muted">
              {result
                ? `${result.medicines} medicine${result.medicines === 1 ? "" : "s"} saved with reminders. ${
                    result.notified
                  } family member${result.notified === 1 ? "" : "s"} notified.`
                : "This prescription has already been confirmed."}
            </p>
            <div className="ps-actions ps-center">
              <button type="button" className="pp-btn pp-btn-ghost" onClick={startOver}>
                Scan another
              </button>
              <Link to={medsPath} className="pp-btn md-btn-link">
                View medicines
              </Link>
            </div>
          </section>
        )}
      </div>
    </WorkspaceLayout>
  );
}
