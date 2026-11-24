import { useEffect, useRef, useState, type FormEvent } from "react";
import { estimateRefill, REFILL_BUFFER_DAYS, toDateInput } from "../refill";
import TimeSelect from "../components/TimeSelect";
import { Link, useNavigate } from "react-router-dom";
import "../medicines.css";
import "../prescription-scan.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { createCareProfileFromOnboarding } from "../careProfileSetup";
import {
  checkImageFile,
  ImageUploadUnavailable,
  uploadMedicineImage,
  uploadPrescriptionImage,
  useMedicineImage,
  formatPrice,
} from "../medicineImage";
import {
  ApiError,
  careProfiles,
  families,
  medicines,
  members,
  type CareProfileOut,
  type MedicineCreate,
  type MedicineOut,
  type MedicineUpdate,
  type MemberOut,
} from "../api";

interface MedicineFormProps {
  familyId: string;
  /** Preselects the care profile when creating. Otherwise the user must choose, unless there is only one. */
  careProfileId?: string;
  /** Set to edit an existing medicine; omit to create. */
  medicineId?: string;
  /** Called after a successful save. Defaults to returning to the medicines list. */
  onSaved?: (medicine: MedicineOut) => void;
}

const errorText = (err: unknown, fallback: string) =>
  err instanceof ApiError ? err.detail : fallback;

// "1 Dec" (adds the year only when it is not this year).
function shortDate(d: Date): string {
  const opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" };
  if (d.getFullYear() !== new Date().getFullYear()) opts.year = "numeric";
  return d.toLocaleDateString(undefined, opts);
}

// Name suggestions: the family's own medicines first, then common ones.
const COMMON_MEDICINES = [
  "Amlodipine 5 mg",
  "Atorvastatin 10 mg",
  "Calcium + Vitamin D3",
  "Dolo 650",
  "Ecosprin 75 mg",
  "Glimepiride 1 mg",
  "Losartan 50 mg",
  "Metformin 500 mg",
  "Pantoprazole 40 mg",
  "Paracetamol 500 mg",
  "Rosuvastatin 10 mg",
  "Telmisartan 40 mg",
  "Thyronorm 50 mcg",
  "Vitamin D3 60000 IU",
];

const VOICE_EXAMPLE =
  "One tablet at 9 am and one tablet at 8 pm after food, and the total remaining quantity is 10. " +
  "Pricing is 10 tablets for ₹55.";

type FormMode = "form" | "voice";

// One-tap reminder times.
const QUICK_TIMES: { label: string; time: string }[] = [
  { label: "Morning 8 AM", time: "08:00" },
  { label: "Afternoon 2 PM", time: "14:00" },
  { label: "Night 8 PM", time: "20:00" },
];
const FOOD_OPTIONS = ["before food", "after food", "with food"] as const;
const FOOD_RE = /,?\s*\b(before|after|with)\s+(food|meals?)\b/i;

/** Put "after food" (etc.) at the end of the schedule text, replacing any food note already there. */
function withFood(text: string, food: string | null): string {
  const base = text.replace(FOOD_RE, "").trim().replace(/,$/, "");
  if (!food) return base;
  return base ? `${base}, ${food}` : food.charAt(0).toUpperCase() + food.slice(1);
}

type FieldKey = "profile" | "name" | "price" | "count" | "times";

interface PhotoCardProps {
  title: string;
  addLabel: string;
  hint: string;
  icon: string;
  alt: string;
  /** The saved photo (blob: URL) when editing. */
  current: string | null;
  file: File | null;
  preview: string | null;
  error: string | null;
  canEdit: boolean;
  onPick: (file: File | null | undefined) => void;
  onClear: () => void;
}

/** One photo picker card (medicine photo, prescription photo). The file is uploaded when the form is saved. */
function PhotoCard({ title, addLabel, hint, icon, alt, current, file, preview, error, canEdit, onPick, onClear }: PhotoCardProps) {
  const shown = preview ?? current;
  const input = (capture: boolean) => (
    <input
      type="file"
      accept="image/jpeg,image/png,image/webp"
      {...(capture ? { capture: "environment" as const } : {})}
      className="mf-photo-input"
      onChange={(e) => {
        onPick(e.target.files?.[0]);
        e.target.value = "";
      }}
    />
  );
  return (
    <section className="pp-card">
      <div className="pp-card-head">
        <h2>{title}</h2>
        <span className="md-sub">Optional</span>
      </div>
      {shown ? (
        <div className="mf-photo">
          <img src={shown} alt={alt} />
        </div>
      ) : (
        !canEdit && <p className="pp-muted mf-side-text">No photo yet.</p>
      )}
      {canEdit ? (
        <>
          {!shown && (
            <label className="mf-photo-drop">
              {input(true)}
              <span className="mf-photo-icon" aria-hidden="true">
                {icon}
              </span>
              <strong>{addLabel}</strong>
              <span className="md-sub">{hint}</span>
            </label>
          )}
          {shown && (
            <div className="mf-photo-actions">
              <label className="pp-btn pp-btn-ghost md-btn-link mf-photo-change">
                Change photo
                {input(false)}
              </label>
              {file && (
                <button type="button" className="mf-photo-remove" onClick={onClear}>
                  {current ? "Keep current" : "Remove"}
                </button>
              )}
            </div>
          )}
          {error && (
            <p role="alert" className="mf-photo-error">
              {error}
            </p>
          )}
          {file && <p className="md-sub mf-photo-note">The photo is uploaded when you save.</p>}
        </>
      ) : (
        <p className="md-sub mf-photo-note">Only members who can edit medicines can add a photo.</p>
      )}
    </section>
  );
}

/** A picked photo plus its preview URL and any problem with it. */
function usePickedPhoto() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!file) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return {
    file,
    preview,
    error,
    pick(f: File | null | undefined) {
      setError(null);
      if (!f) return;
      const problem = checkImageFile(f);
      if (problem) setError(problem);
      else setFile(f);
    },
    clear() {
      setFile(null);
      setError(null);
    },
  };
}

export default function MedicineForm({
  familyId,
  careProfileId,
  medicineId,
  onSaved,
}: MedicineFormProps) {
  const isEdit = medicineId !== undefined;
  const navigate = useNavigate();
  const listPath = `/family/${familyId}/medicines`;

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [profiles, setProfiles] = useState<CareProfileOut[]>([]);
  // A failed load must not look like "no profiles yet", which would create one on save.
  const [profilesFailed, setProfilesFailed] = useState(false);
  const [people, setPeople] = useState<MemberOut[]>([]);

  const [profileId, setProfileId] = useState(careProfileId ?? "");
  const [displayName, setDisplayName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [quantity, setQuantity] = useState("");
  const [refillDate, setRefillDate] = useState("");
  // The refill date follows the tablets left and the schedule until someone picks a date by hand.
  const [refillTouched, setRefillTouched] = useState(false);
  const [responsible, setResponsible] = useState("");
  const [active, setActive] = useState(true);
  // Pricing: price per tablet and how many tablets were bought; the server computes the total.
  const [unitPrice, setUnitPrice] = useState("");
  const [totalCount, setTotalCount] = useState("");
  // Reminder times (HH:MM); saved with a PUT after the medicine itself is saved.
  const [times, setTimes] = useState<string[]>([]);
  // What the server had when loaded; null means the load failed, so we must not overwrite it.
  const [loadedTimes, setLoadedTimes] = useState<string[] | null>([]);
  const [linkedScanId, setLinkedScanId] = useState<string | null>(null);

  // Medicine photo. Only members with medicines.edit can add or remove it.
  const [canEditPhoto, setCanEditPhoto] = useState(true);
  // The saved photo (GET .../image), shown when editing an existing medicine.
  const currentImage = useMedicineImage(familyId, isEdit ? medicineId : null);
  const currentPrescription = useMedicineImage(familyId, isEdit ? medicineId : null, 0, "prescription-image");
  const medPhoto = usePickedPhoto();
  const rxPhoto = usePickedPhoto();

  // Voice mode (adding only): pick the parent and the name, then say the rest in one sentence (Wispr Flow
  // types it into the big box) and "Fill the form" reads it into the fields.
  const [mode, setMode] = useState<FormMode>("voice");
  const [spoken, setSpoken] = useState("");
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);
  const [readResult, setReadResult] = useState<{ source: string; filled: string[] } | null>(null);
  const [nameSuggestions, setNameSuggestions] = useState<string[]>(COMMON_MEDICINES);
  const voice = mode === "voice" && !isEdit;
  // Fields "Fill the form" just set, highlighted for a few seconds so you can see what changed.
  const [justFilled, setJustFilled] = useState<string[]>([]);
  const checkRef = useRef<HTMLElement | null>(null);
  // A problem shown under the field it is about.
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldKey, string>>>({});
  // While someone types into "Total paid", keep their text; otherwise it shows price × tablets.
  const [totalTyped, setTotalTyped] = useState<string | null>(null);

  useEffect(() => {
    if (justFilled.length === 0) return;
    const t = window.setTimeout(() => setJustFilled([]), 6000);
    return () => window.clearTimeout(t);
  }, [justFilled]);

  // The summary message came from field problems: drop it once they are all fixed.
  const errorFromFields = useRef(false);
  useEffect(() => {
    if (errorFromFields.current && Object.keys(fieldErrors).length === 0) {
      errorFromFields.current = false;
      setError(null);
    }
  }, [fieldErrors]);

  const clearFieldError = (key: FieldKey) =>
    setFieldErrors((cur) => {
      if (!cur[key]) return cur;
      const next = { ...cur };
      delete next[key];
      return next;
    });
  const filledClass = (key: string) => (justFilled.includes(key) ? " mf-filled" : "");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      careProfiles.list(familyId).catch(() => null),
      members.list(familyId).catch(() => [] as MemberOut[]),
      isEdit ? medicines.get(familyId, medicineId) : Promise.resolve(null),
      families.me(familyId).catch(() => null),
      isEdit ? Promise.resolve([] as MedicineOut[]) : medicines.list(familyId).catch(() => [] as MedicineOut[]),
      isEdit
        ? medicines
            .getReminders(familyId, medicineId)
            .then((r) => r.times)
            .catch(() => null as string[] | null)
        : Promise.resolve([] as string[] | null),
    ])
      .then(([profileList, memberList, med, access, familyMedicines, reminderTimes]) => {
        if (cancelled) return;
        const own = familyMedicines.map((m) => m.display_name.trim()).filter(Boolean);
        setNameSuggestions([...new Set([...own, ...COMMON_MEDICINES])]);
        setProfiles(profileList ?? []);
        setProfilesFailed(profileList === null);
        setPeople(memberList);
        setTimes(reminderTimes ?? []);
        setLoadedTimes(reminderTimes);
        // If permissions can't be read, show the controls; the server still enforces them.
        setCanEditPhoto(access ? access.permissions.includes("medicines.edit") : true);
        if (med) {
          setProfileId(med.care_profile_id);
          setDisplayName(med.display_name);
          setInstructions(med.instructions_text ?? "");
          setQuantity(med.quantity_remaining?.toString() ?? "");
          setRefillDate(med.refill_date ?? "");
          setRefillTouched(Boolean(med.refill_date));
          setResponsible(med.responsible_user_id ?? "");
          setActive(med.active);
          setUnitPrice(med.unit_price != null ? String(Number(med.unit_price)) : "");
          setTotalCount(med.total_medicine_count != null ? String(med.total_medicine_count) : "");
          setLinkedScanId(med.prescription_scan_id ?? null);
        } else {
          setProfileId((current) => current || (profileList?.length === 1 ? profileList[0].id : ""));
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorText(err, "Could not load medicine."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [familyId, medicineId, isEdit]);

  // Suggested refill date from today, the tablets left and the schedule (reminder times or the text).
  const refillEstimate = estimateRefill(quantity, instructions, times);
  const suggestedRefill = refillEstimate ? toDateInput(refillEstimate.refillBy) : null;
  useEffect(() => {
    if (!refillTouched && suggestedRefill) setRefillDate(suggestedRefill);
  }, [refillTouched, suggestedRefill]);

  async function fillFromSpeech() {
    if (!spoken.trim()) {
      setReadError("Say or type the schedule, tablets left and price first.");
      return;
    }
    setReading(true);
    setReadError(null);
    try {
      const r = await medicines.parseText(familyId, spoken.trim());
      const filled: string[] = [];
      if (r.instructions_text) {
        setInstructions(r.instructions_text);
        filled.push("schedule");
      }
      if (r.reminder_times.length > 0) {
        setTimes(r.reminder_times);
        filled.push("reminder times");
      }
      if (r.quantity_remaining != null) {
        setQuantity(String(r.quantity_remaining));
        filled.push("tablets left");
      }
      if (r.unit_price != null) {
        setUnitPrice(String(Number(r.unit_price)));
        filled.push("price per tablet");
      }
      if (r.total_medicine_count != null) {
        setTotalCount(String(r.total_medicine_count));
        filled.push("tablets bought");
      }
      // The refill date follows the new tablets left and schedule.
      if (filled.length > 0) {
        setRefillTouched(false);
        setTotalTyped(null);
        setJustFilled(filled);
        window.setTimeout(() => checkRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
      }
      setReadResult({ source: r.source, filled });
    } catch (err) {
      setReadError(errorText(err, "Could not read that. Please try again or fill the fields by hand."));
    } finally {
      setReading(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!isEdit && !profileId && profilesFailed) {
      setError("Could not load the family's profiles. Please reload the page and try again.");
      return;
    }
    const problems: Partial<Record<FieldKey, string>> = {};
    if (!isEdit && !profileId && profiles.length > 0) problems.profile = "Choose who this medicine is for.";
    if (!displayName.trim()) problems.name = "Enter the medicine name.";
    if (unitPrice.trim() !== "" && !(Number(unitPrice) >= 0)) problems.price = "Price per tablet must be 0 or more.";
    if (totalCount.trim() !== "" && !(Number.isInteger(Number(totalCount)) && Number(totalCount) >= 0))
      problems.count = "Tablets bought must be a whole number.";
    if (times.some((t) => !/^([01]\d|2[0-3]):[0-5]\d$/.test(t)))
      problems.times = "Fill in every reminder time, or remove the empty ones.";
    const keys = Object.keys(problems) as FieldKey[];
    if (keys.length > 0) {
      setFieldErrors(problems);
      errorFromFields.current = true;
      setError(keys.length === 1 ? problems[keys[0]]! : `Please fix the ${keys.length} highlighted fields.`);
      const first = document.getElementById(`mf-${keys[0]}`);
      first?.scrollIntoView({ behavior: "smooth", block: "center" });
      if (first instanceof HTMLInputElement || first instanceof HTMLSelectElement) first.focus({ preventScroll: true });
      return;
    }
    setFieldErrors({});
    setSaving(true);
    setError(null);
    try {
      const refill = refillDate === "" ? null : refillDate;
      const owner = responsible === "" ? null : responsible;
      const pricing = {
        unit_price: unitPrice.trim() === "" ? null : Number(unitPrice),
        total_medicine_count: totalCount.trim() === "" ? null : Number(totalCount),
      };
      let result: MedicineOut;

      if (isEdit) {
        const body: MedicineUpdate = {
          display_name: displayName.trim(),
          instructions_text: instructions.trim() || null,
          refill_date: refill,
          responsible_user_id: owner,
          active,
          ...pricing,
        };
        result = await medicines.update(familyId, medicineId, body);
      } else {
        // No care profile yet: create one from the onboarding details first.
        let careProfile = profileId;
        if (!careProfile) {
          const created = await createCareProfileFromOnboarding(familyId);
          setProfiles([created]);
          setProfileId(created.id);
          careProfile = created.id;
        }
        const body: MedicineCreate = {
          care_profile_id: careProfile,
          display_name: displayName.trim(),
          instructions_text: instructions.trim() || null,
          quantity_remaining: quantity === "" ? null : Number(quantity),
          refill_date: refill,
          responsible_user_id: owner,
        };
        result = await medicines.create(familyId, body);
        // Create doesn't accept pricing; set it with a follow-up update.
        if (pricing.unit_price !== null || pricing.total_medicine_count !== null) {
          result = await medicines.update(familyId, result.id, pricing);
        }
      }
      // Reminder times are saved separately too (PUT replaces them all).
      // Skipped when unchanged, and when the load failed (it would wipe the existing times).
      const changed =
        loadedTimes !== null && JSON.stringify([...new Set(times)].sort()) !== JSON.stringify([...loadedTimes].sort());
      if (changed) await medicines.setReminders(familyId, result.id, times);
      // Photo is a separate upload after the medicine itself is saved.
      let photoProblem: string | null = null;
      try {
        if (medPhoto.file) await uploadMedicineImage(familyId, result.id, medPhoto.file);
      } catch (err) {
        photoProblem =
          err instanceof ImageUploadUnavailable
            ? "the server doesn't support medicine photos yet"
            : errorText(err, "the upload failed");
      }
      let rxProblem: string | null = null;
      try {
        if (rxPhoto.file) result = await uploadPrescriptionImage(familyId, result.id, rxPhoto.file);
      } catch (err) {
        rxProblem = errorText(err, "the upload failed");
      }
      const saved = isEdit ? "Medicine updated" : "Medicine added";
      const problems = [
        photoProblem && `the medicine photo wasn't uploaded: ${photoProblem}`,
        rxProblem && `the prescription photo wasn't uploaded: ${rxProblem}`,
      ].filter(Boolean);
      const notice = problems.length ? `${saved}, but ${problems.join("; ")}.` : `${saved}.`;
      if (onSaved) onSaved(result);
      else navigate(listPath, { state: { notice, warn: problems.length > 0 } });
    } catch (err) {
      setError(errorText(err, "Could not save medicine."));
    } finally {
      setSaving(false);
    }
  }

  const title = isEdit ? "Edit medicine" : "Add medicine";

  // ---- fields shared by both layouts ----

  const profileField = profiles.length > 0 && (
    <label className="pp-field mf-span">
      <span>
        Who is this medicine for? {!isEdit && <span className="mf-req">Required</span>}
      </span>
      <select
        id="mf-profile"
        required
        disabled={isEdit}
        value={profileId}
        aria-invalid={Boolean(fieldErrors.profile)}
        onChange={(e) => {
          setProfileId(e.target.value);
          clearFieldError("profile");
        }}
      >
        <option value="" disabled>
          Select a profile
        </option>
        {profiles.map((p) => (
          <option key={p.id} value={p.id}>
            {p.display_name}
          </option>
        ))}
      </select>
      {fieldErrors.profile && <span className="mf-field-error">{fieldErrors.profile}</span>}
    </label>
  );

  const nameField = (
    <label className="pp-field mf-span">
      <span>
        Medicine name <span className="mf-req">Required</span>
      </span>
      <input
        id="mf-name"
        required
        maxLength={255}
        placeholder="Start typing, e.g. Amlodipine 5 mg"
        list="mf-name-suggestions"
        autoComplete="off"
        value={displayName}
        aria-invalid={Boolean(fieldErrors.name)}
        onChange={(e) => {
          setDisplayName(e.target.value);
          clearFieldError("name");
        }}
      />
      {fieldErrors.name && <span className="mf-field-error">{fieldErrors.name}</span>}
      <datalist id="mf-name-suggestions">
        {nameSuggestions.map((n) => (
          <option key={n} value={n} />
        ))}
      </datalist>
    </label>
  );

  const currentFood = (FOOD_RE.exec(instructions)?.[1] ?? "").toLowerCase();
  const instructionsField = (
    <div className={`pp-field mf-span${filledClass("schedule")}`}>
      <label htmlFor="mf-instructions">Schedule & instructions</label>
      <textarea
        id="mf-instructions"
        rows={3}
        placeholder="e.g. 1 tablet at 9:00 AM and 8:00 PM, after food"
        value={instructions}
        onChange={(e) => setInstructions(e.target.value)}
      />
      <div className="mf-chips" role="group" aria-label="When to take it">
        {FOOD_OPTIONS.map((f) => {
          const on = currentFood === f.split(" ")[0];
          return (
            <button
              key={f}
              type="button"
              className={`mf-chip${on ? " is-on" : ""}`}
              aria-pressed={on}
              onClick={() => setInstructions(withFood(instructions, on ? null : f))}
            >
              {on ? "✓ " : ""}
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          );
        })}
      </div>
    </div>
  );

  const quantityField = !isEdit && (
    <label className={`pp-field${filledClass("tablets left")}`}>
      Quantity remaining
      <input
        type="number"
        min={0}
        step={1}
        inputMode="numeric"
        placeholder="Tablets left"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
      />
    </label>
  );

  const refillField = (
    <label className={`pp-field${justFilled.length ? " mf-filled" : ""}`}>
      Refill date
      <input
        type="date"
        value={refillDate}
        onChange={(e) => {
          setRefillTouched(true);
          setRefillDate(e.target.value);
        }}
      />
      {refillEstimate && (
        <span className="mf-refill-hint">
          {refillEstimate.days} {refillEstimate.days === 1 ? "day" : "days"} of tablets at {refillEstimate.perDay} a day
          (runs out {shortDate(refillEstimate.runsOut)}). Refill by {shortDate(refillEstimate.refillBy)},{" "}
          {REFILL_BUFFER_DAYS} days early.
          {refillDate !== toDateInput(refillEstimate.refillBy) && (
            <button
              type="button"
              className="mf-refill-use"
              onClick={() => {
                setRefillTouched(false);
                setRefillDate(toDateInput(refillEstimate.refillBy));
              }}
            >
              Use this date
            </button>
          )}
        </span>
      )}
    </label>
  );

  const caretakerField = (span: boolean) => (
    <label className={`pp-field${span ? " mf-span" : ""}`}>
      Responsible caregiver
      <select value={responsible} onChange={(e) => setResponsible(e.target.value)}>
        <option value="">Unassigned</option>
        {people.map((p) => (
          <option key={p.user_id} value={p.user_id}>
            {p.display_name} · {p.role_name}
          </option>
        ))}
      </select>
    </label>
  );

  const computedTotal =
    unitPrice !== "" && totalCount !== "" && Number(unitPrice) >= 0 && Number(totalCount) >= 0
      ? String(Math.round(Number(unitPrice) * Number(totalCount) * 100) / 100)
      : "";
  const pricingField = (
    <div className={`mf-span mf-price${filledClass("price per tablet") || filledClass("tablets bought")}`}>
      <div className="mf-price-head">
        <strong>Pricing</strong>
        <span className="md-sub">Optional · for tracking medicine costs</span>
      </div>
      <div className="mf-price-row">
        <label className="pp-field">
          Price per tablet (₹)
          <input
            id="mf-price"
            aria-invalid={Boolean(fieldErrors.price)}
            className={filledClass("price per tablet").trim()}
            type="number"
            min={0}
            step="0.01"
            inputMode="decimal"
            placeholder="e.g. 4.50"
            value={unitPrice}
            onChange={(e) => {
              setUnitPrice(e.target.value);
              clearFieldError("price");
            }}
          />
          {fieldErrors.price && <span className="mf-field-error">{fieldErrors.price}</span>}
        </label>
        <span className="mf-price-x" aria-hidden="true">
          ×
        </span>
        <label className="pp-field">
          Tablets bought
          <input
            id="mf-count"
            aria-invalid={Boolean(fieldErrors.count)}
            className={filledClass("tablets bought").trim()}
            type="number"
            min={0}
            step={1}
            inputMode="numeric"
            placeholder="e.g. 30"
            value={totalCount}
            onChange={(e) => {
              setTotalCount(e.target.value);
              clearFieldError("count");
            }}
          />
          {fieldErrors.count && <span className="mf-field-error">{fieldErrors.count}</span>}
        </label>
        <span className="mf-price-x" aria-hidden="true">
          =
        </span>
        <label className="pp-field mf-price-total">
          Total paid (₹)
          <input
            type="number"
            min={0}
            step="0.01"
            inputMode="decimal"
            placeholder="Pack price"
            value={totalTyped ?? computedTotal}
            onChange={(e) => {
              const v = e.target.value;
              setTotalTyped(v);
              const count = Number(totalCount);
              if (v.trim() !== "" && Number(v) >= 0 && count > 0) setUnitPrice((Number(v) / count).toFixed(2));
            }}
            onBlur={() => setTotalTyped(null)}
          />
        </label>
      </div>
      <span className="md-sub mf-price-tip">
        Know the strip price? Enter the tablets bought, then type the price in Total paid and we'll work out the price
        per tablet.
      </span>
    </div>
  );

  const timesField = (
    <div id="mf-times" className={`pp-field mf-span${filledClass("reminder times")}`}>
      <span id="mf-times-label">Reminder times</span>
      <div className="ps-times" role="group" aria-labelledby="mf-times-label">
        {times.map((t, ti) => (
          <span key={ti} className="ps-time">
            <TimeSelect
              value={t}
              ariaLabel={`Time ${ti + 1}`}
              onChange={(v) => setTimes(times.map((x, i) => (i === ti ? v : x)))}
            />
            <button
              type="button"
              aria-label={`Remove time ${ti + 1}`}
              onClick={() => setTimes(times.filter((_, i) => i !== ti))}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="mf-chips" role="group" aria-label="Add a reminder time">
        {QUICK_TIMES.filter((q) => !times.includes(q.time)).map((q) => (
          <button
            key={q.time}
            type="button"
            className="mf-chip"
            onClick={() => {
              setTimes([...times, q.time].sort());
              clearFieldError("times");
            }}
          >
            + {q.label}
          </button>
        ))}
        <button type="button" className="mf-chip" onClick={() => setTimes([...times, "12:00"])}>
          + Other time
        </button>
      </div>
      {fieldErrors.times && <span className="mf-field-error">{fieldErrors.times}</span>}
      {loadedTimes === null && (
        <span role="alert" className="pp-alert">
          Could not load the current reminder times, so they will be left unchanged on save.
        </span>
      )}
      <span className="md-sub">Optional · we remind the family at these times.</span>
    </div>
  );

  const medicinePhotoCard = (
    <PhotoCard
      title="Medicine photo"
      addLabel="Add a photo of the medicine"
      hint="Strip or box · JPG, PNG or WebP · up to 10 MB. Your parent can ask for this photo in the chat."
      icon="📷"
      alt={`Photo of ${displayName || "the medicine"}`}
      current={currentImage}
      file={medPhoto.file}
      preview={medPhoto.preview}
      error={medPhoto.error}
      canEdit={canEditPhoto}
      onPick={medPhoto.pick}
      onClear={medPhoto.clear}
    />
  );

  const prescriptionPhotoCard = (
    <PhotoCard
      title="Prescription photo"
      addLabel="Add a photo of the prescription"
      hint="The doctor's note for this medicine · up to 10 MB"
      icon="🧾"
      alt={`Prescription for ${displayName || "the medicine"}`}
      current={currentPrescription}
      file={rxPhoto.file}
      preview={rxPhoto.preview}
      error={rxPhoto.error}
      canEdit={canEditPhoto}
      onPick={rxPhoto.pick}
      onClear={rxPhoto.clear}
    />
  );

  const stepDone = [
    Boolean((profileId || profiles.length === 0) && displayName.trim()),
    Boolean(readResult && readResult.filled.length > 0),
    Boolean(instructions.trim() || times.length > 0),
    Boolean(medPhoto.file || rxPhoto.file || responsible),
  ];
  const stepBadge = (n: number) => (
    <span className={`mv-step${stepDone[n - 1] ? " is-done" : ""}`} aria-label={stepDone[n - 1] ? `Step ${n}, done` : `Step ${n}`}>
      {stepDone[n - 1] ? "✓" : n}
    </span>
  );

  const sourceNote = (
    <div className="md-note mf-note">
      <span className="md-note-icon" aria-hidden="true">
        ⓘ
      </span>
      <div>
        <strong>Schedule source and confirmation</strong>
        <p>
          Medicine names, timings and instructions are entered by an authorised family member from doctor-provided
          information. CareCircle does not recommend or change treatment.
        </p>
      </div>
    </div>
  );

  return (
    <WorkspaceLayout familyId={familyId} current="medicines" title={title}>
      <form className="pp-content" onSubmit={handleSubmit} noValidate>
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">
              <Link to={listPath} className="mf-back">
                ← Medicines
              </Link>
            </p>
            <h1>{title}</h1>
            <p className="pp-muted">
              Enter the medicine exactly as written on the doctor's prescription.
            </p>
          </div>
          <div className="pp-head-actions mf-head-actions">
            <Link to={listPath} className="pp-btn pp-btn-ghost md-btn-link">
              Cancel
            </Link>
            <button type="submit" className="pp-btn" disabled={saving || loading}>
              {saving ? "Saving…" : isEdit ? "Save changes" : "Add medicine"}
            </button>
          </div>
        </div>

        {loading && (
          <p role="status" className="pp-muted">
            Loading…
          </p>
        )}
        {error && (
          <p role="alert" className="pp-alert">
            {error}
          </p>
        )}

        {!loading && !isEdit && (
          <div className="mv-mode" role="radiogroup" aria-label="How do you want to add it?">
            <button
              type="button"
              role="radio"
              aria-checked={voice}
              className={`mv-mode-btn${voice ? " is-on" : ""}`}
              onClick={() => setMode("voice")}
            >
              <span aria-hidden="true">🎙️</span> Voice mode
              <small>Say the schedule, stock and price</small>
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={!voice}
              className={`mv-mode-btn${!voice ? " is-on" : ""}`}
              onClick={() => setMode("form")}
            >
              <span aria-hidden="true">⌨️</span> Type it in
              <small>Fill every field yourself</small>
            </button>
          </div>
        )}

        {!loading && voice && (
          <div className="mv-flow">
            <section className="pp-card">
              <div className="pp-card-head">
                <h2>
                  {stepBadge(1)} Which medicine?
                </h2>
              </div>
              <div className="mf-fields">
                {profileField}
                {nameField}
              </div>
            </section>

            <section className="pp-card mv-speak">
              <div className="pp-card-head">
                <h2>
                  {stepBadge(2)} Say the details
                </h2>
                <span className="md-sub">Schedule · tablets left · price</span>
              </div>
              <p className="pp-muted mv-help">
                Click in the box and speak with Wispr Flow (or type). For example:{" "}
                <button type="button" className="mv-example" onClick={() => setSpoken(VOICE_EXAMPLE)}>
                  “{VOICE_EXAMPLE}”
                </button>
              </p>
              <textarea
                className="mv-box"
                rows={6}
                aria-label="Medicine details, spoken or typed"
                placeholder="One tablet at 9 am and one at 8 pm after food. 10 tablets left. 10 tablets for ₹55."
                value={spoken}
                maxLength={2000}
                onChange={(e) => {
                  setSpoken(e.target.value);
                  setReadError(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    void fillFromSpeech();
                  }
                }}
              />
              <div className="mv-actions">
                <button type="button" className="pp-btn" onClick={() => void fillFromSpeech()} disabled={reading}>
                  {reading ? "Reading…" : "✨ Fill the form"}
                </button>
                <span className="md-sub">Ctrl + Enter also works</span>
              </div>
              {readError && (
                <p role="alert" className="pp-alert">
                  {readError}
                </p>
              )}
              {readResult && !readError && (
                <p role="status" className={`mv-result${readResult.filled.length ? "" : " is-empty"}`}>
                  {readResult.filled.length
                    ? `Filled ${readResult.filled.join(", ")}${readResult.source === "gemini" ? " (read by Gemini)" : ""}. Please check them below.`
                    : "Couldn't find a schedule, stock or price in that. Try saying it again, or fill the fields below."}
                </p>
              )}
            </section>

            <section className="pp-card" ref={checkRef}>
              <div className="pp-card-head">
                <h2>
                  {stepBadge(3)} Check the details
                </h2>
                <span className="md-sub">Change anything that's wrong</span>
              </div>
              <div className="mf-fields">
                {instructionsField}
                {timesField}
                {quantityField}
                {refillField}
                {pricingField}
              </div>
            </section>

            <section className="pp-card">
              <div className="pp-card-head">
                <h2>
                  {stepBadge(4)} Photos and caregiver
                </h2>
              </div>
              <div className="mv-photos">
                {medicinePhotoCard}
                {prescriptionPhotoCard}
              </div>
              <div className="mf-fields mv-caretaker">{caretakerField(true)}</div>
            </section>

            {sourceNote}
          </div>
        )}

        {!loading && !voice && (
          <div className="mf-grid">
            <section className="pp-card">
              <div className="pp-card-head">
                <h2>Medicine details</h2>
                {isEdit && (
                  <span className={`md-status${active ? "" : " is-off"}`}>{active ? "Active" : "Inactive"}</span>
                )}
              </div>

              <div className="mf-fields">
                {profileField}
                {nameField}
                {instructionsField}
                {quantityField}
                {refillField}
                {caretakerField(!isEdit)}
                {pricingField}
                {timesField}

                {linkedScanId && (
                  <p className="mf-span mf-linked">
                    🧾 Added from a prescription scan.{" "}
                    <Link to={`/family/${familyId}/prescription-scan?scan=${linkedScanId}&profile=${profileId}`}>
                      View prescription
                    </Link>
                  </p>
                )}

                {isEdit && (
                  <label className="mf-toggle mf-span">
                    <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
                    <span>
                      <strong>Active</strong>
                      <span className="md-sub">Inactive medicines stay in the record but are not scheduled.</span>
                    </span>
                  </label>
                )}
              </div>
            </section>

            <aside className="mf-side">
              {medicinePhotoCard}
              {prescriptionPhotoCard}

              <section className="pp-card">
                <h2>Prefer to scan?</h2>
                <p className="pp-muted mf-side-text">
                  Upload a photo of the prescription and confirm the medicines it finds.
                </p>
                <Link to={`/family/${familyId}/prescription-scan`} className="pp-btn pp-btn-ghost md-btn-link mf-full">
                  Scan prescription
                </Link>
              </section>

              {sourceNote}
            </aside>
          </div>
        )}

        {!loading && (
          <div className="mf-bottom-actions">
            {error && <span className="mf-bar-error">{error}</span>}
            <Link to={listPath} className="pp-btn pp-btn-ghost md-btn-link">
              Cancel
            </Link>
            <button type="submit" className="pp-btn" disabled={saving}>
              {saving ? "Saving…" : isEdit ? "Save changes" : "Add medicine"}
            </button>
          </div>
        )}
      </form>
    </WorkspaceLayout>
  );
}
