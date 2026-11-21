import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  careProfiles,
  confirmPrescriptionScan,
  uploadPrescriptionScan,
  type CareProfileOut,
  type PrescriptionMedicineIn,
  type PrescriptionScanOut,
} from "../api";

interface PrescriptionScanProps {
  familyId: string;
}

interface MedicineRow {
  name: string;
  dose: string;
  instructions: string;
  times: string; // comma-separated "HH:MM"
}

const HH_MM = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : fallback;
}

export default function PrescriptionScan({ familyId }: PrescriptionScanProps) {
  const [profiles, setProfiles] = useState<CareProfileOut[]>([]);
  const [careProfileId, setCareProfileId] = useState("");
  const [loading, setLoading] = useState(true);

  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [scan, setScan] = useState<PrescriptionScanOut | null>(null);
  const [rows, setRows] = useState<MedicineRow[]>([]);

  const [confirming, setConfirming] = useState(false);
  const [notifiedCount, setNotifiedCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    careProfiles
      .list(familyId)
      .then((list) => {
        if (cancelled) return;
        setProfiles(list);
        setCareProfileId(list[0]?.id ?? "");
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(messageOf(err, "Could not load care profiles."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [familyId]);

  function updateRow(index: number, field: keyof MedicineRow, value: string) {
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  }

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    if (!file || !careProfileId) return;
    setUploading(true);
    setError(null);
    setScan(null);
    setRows([]);
    setNotifiedCount(null);
    try {
      const result = await uploadPrescriptionScan(familyId, careProfileId, file);
      setScan(result);
      setRows(
        (result.proposed?.medicines ?? []).map((m) => ({
          name: m.name,
          dose: m.dose ?? "",
          instructions: m.instructions ?? "",
          times: m.times.join(", "),
        })),
      );
    } catch (err) {
      setError(messageOf(err, "Could not upload the photo."));
    } finally {
      setUploading(false);
    }
  }

  async function handleConfirm(e: FormEvent) {
    e.preventDefault();
    if (!scan) return;
    const medicines: PrescriptionMedicineIn[] = [];
    for (const row of rows) {
      const name = row.name.trim();
      if (!name) {
        setError("Every medicine needs a name.");
        return;
      }
      const times = row.times
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t !== "");
      if (times.length === 0 || !times.every((t) => HH_MM.test(t))) {
        setError(`Times for ${name} must be 24-hour HH:MM, separated by commas.`);
        return;
      }
      medicines.push({
        name,
        dose: row.dose.trim() || null,
        instructions: row.instructions.trim() || null,
        times,
      });
    }

    setConfirming(true);
    setError(null);
    try {
      const out = await confirmPrescriptionScan(familyId, careProfileId, scan.id, { medicines });
      setNotifiedCount(out.notified_user_ids.length);
      setScan({ ...scan, status: "confirmed" });
    } catch (err) {
      setError(messageOf(err, "Could not create reminders."));
    } finally {
      setConfirming(false);
    }
  }

  if (loading) return <p role="status">Loading care profiles…</p>;

  return (
    <main>
      <h1>Scan a prescription</h1>

      {profiles.length === 0 ? (
        <p>No care profiles yet. Add one before scanning a prescription.</p>
      ) : (
        <form onSubmit={handleUpload}>
          {profiles.length > 1 && (
            <label>
              Care profile
              <select
                value={careProfileId}
                disabled={scan !== null}
                onChange={(e) => setCareProfileId(e.target.value)}
              >
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Prescription photo
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <button type="submit" disabled={!file || !careProfileId || uploading}>
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </form>
      )}

      {uploading && <p role="status">Reading the photo…</p>}
      {error && <p role="alert">{error}</p>}

      {scan && scan.status !== "confirmed" && (
        <p>Detected document: {scan.document_type}</p>
      )}

      {scan?.status === "rejected" && (
        <p>This file is not a prescription. Please upload a photo of a medicine prescription.</p>
      )}

      {scan?.status === "pending_review" && (
        <form onSubmit={handleConfirm}>
          <p>Check each medicine and its times, then confirm to create reminders.</p>
          {rows.length === 0 && <p>No medicines were found on this prescription.</p>}
          {rows.map((row, index) => (
            <fieldset key={index}>
              <legend>Medicine {index + 1}</legend>
              <label>
                Name
                <input
                  required
                  maxLength={255}
                  value={row.name}
                  onChange={(e) => updateRow(index, "name", e.target.value)}
                />
              </label>
              <label>
                Dose
                <input
                  maxLength={120}
                  value={row.dose}
                  onChange={(e) => updateRow(index, "dose", e.target.value)}
                />
              </label>
              <label>
                Instructions
                <textarea
                  maxLength={2000}
                  value={row.instructions}
                  onChange={(e) => updateRow(index, "instructions", e.target.value)}
                />
              </label>
              <label>
                Times (HH:MM, comma-separated)
                <input
                  required
                  placeholder="08:00, 20:00"
                  value={row.times}
                  onChange={(e) => updateRow(index, "times", e.target.value)}
                />
              </label>
            </fieldset>
          ))}
          <button type="submit" disabled={confirming || rows.length === 0}>
            {confirming ? "Confirming…" : "Confirm and create reminders"}
          </button>
        </form>
      )}

      {scan?.status === "confirmed" && notifiedCount !== null && (
        <p role="status">
          Medicines saved and reminders set. {notifiedCount} recipient
          {notifiedCount === 1 ? "" : "s"} notified.
        </p>
      )}
    </main>
  );
}
