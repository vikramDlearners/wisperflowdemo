import { useState } from "react";
import { ApiError, medicines, type DoseToday } from "../api";
import { slotName } from "../doses";

interface DoseButtonsProps {
  familyId: string;
  careProfileId: string;
  dose: DoseToday;
  medicineName: string;
  onRecorded: () => void;
}

// A caregiver records one of today's doses. The answer already given is not offered again.
export default function DoseButtons({ familyId, careProfileId, dose, medicineName, onRecorded }: DoseButtonsProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const answered = dose.status === "taken" || dose.status === "skipped";

  async function record(status: "taken" | "skipped") {
    setBusy(true);
    setError(null);
    try {
      await medicines.recordDose(familyId, {
        care_profile_id: careProfileId,
        medicine_id: dose.medicine_id,
        slot: dose.slot,
        status,
      });
      onRecorded();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not save this dose.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="dose-buttons">
      {(["taken", "skipped"] as const)
        .filter((status) => status !== dose.status)
        .map((status) => (
          <button
            key={status}
            type="button"
            className={`pp-btn dose-button${status === "taken" ? "" : " pp-btn-ghost"}`}
            aria-label={`Mark ${medicineName}, ${slotName(dose.slot)}, as ${status}`}
            disabled={busy}
            onClick={() => void record(status)}
          >
            {answered ? `Change to ${status}` : status === "taken" ? "Mark as taken" : "Skipped"}
          </button>
        ))}
      {error && <span role="alert" className="dose-error">{error}</span>}
    </span>
  );
}
