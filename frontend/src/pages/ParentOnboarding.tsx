import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  families,
  getProfile,
  saveProfileSection,
  type ParentProfileFields,
  type ParentProfileOut,
  type ProfileSection,
} from "../api";
import { RELATIONSHIP_OPTIONS } from "../lib/constants";

const TOTAL_STEPS = 5;

// Step number (1-based) -> backend section it saves to.
const STEP_SECTIONS: ProfileSection[] = ["parent", "communication", "care", "medical", "additional"];

const STEP_TITLES = [
  "Parent profile",
  "Communication profile",
  "Care responsibility",
  "Medical information",
  "Additional details",
];


const LANGUAGE_OPTIONS = ["English", "Tamil", "Hindi", "Telugu", "Malayalam", "Kannada"];

const SECTION_LABELS: Record<ProfileSection, string> = {
  parent: "Parent",
  communication: "Communication",
  care: "Care",
  medical: "Medical",
  additional: "Additional",
};

// Every input is held as a string; empty strings become null when saved.
interface FormState {
  parent_full_name: string;
  preferred_name: string;
  relationship: string;
  date_of_birth: string;
  approximate_age: string;
  profile_picture_url: string;
  preferred_language: string;
  parent_mobile: string;
  caregiver_name: string;
  caregiver_relationship: string;
  caregiver_phone: string;
  caregiver_email: string;
  known_health_conditions: string;
  allergies: string;
  primary_doctor_name: string;
  doctor_contact_number: string;
  preferred_hospital: string;
  care_instructions: string;
}

const EMPTY_FORM: FormState = {
  parent_full_name: "",
  preferred_name: "",
  relationship: "",
  date_of_birth: "",
  approximate_age: "",
  profile_picture_url: "",
  preferred_language: "",
  parent_mobile: "",
  caregiver_name: "",
  caregiver_relationship: "",
  caregiver_phone: "",
  caregiver_email: "",
  known_health_conditions: "",
  allergies: "",
  primary_doctor_name: "",
  doctor_contact_number: "",
  preferred_hospital: "",
  care_instructions: "",
};

type FieldChange = ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>;

const errorText = (err: unknown) =>
  err instanceof ApiError ? err.detail : "Something went wrong. Please try again.";

function fromProfile(p: ParentProfileOut): FormState {
  return {
    parent_full_name: p.parent_full_name ?? "",
    preferred_name: p.preferred_name ?? "",
    relationship: p.relationship ?? "",
    date_of_birth: p.date_of_birth ?? "",
    approximate_age: p.approximate_age == null ? "" : String(p.approximate_age),
    profile_picture_url: p.profile_picture_url ?? "",
    preferred_language: p.preferred_language ?? "",
    parent_mobile: p.parent_mobile ?? "",
    caregiver_name: p.caregiver_name ?? "",
    caregiver_relationship: p.caregiver_relationship ?? "",
    caregiver_phone: p.caregiver_phone ?? "",
    caregiver_email: p.caregiver_email ?? "",
    known_health_conditions: p.known_health_conditions ?? "",
    allergies: p.allergies ?? "",
    primary_doctor_name: p.primary_doctor_name ?? "",
    doctor_contact_number: p.doctor_contact_number ?? "",
    preferred_hospital: p.preferred_hospital ?? "",
    care_instructions: p.care_instructions ?? "",
  };
}

const textOrNull = (value: string): string | null => {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
};

function numberOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

// Age in whole years from a YYYY-MM-DD date of birth, or null if not parseable.
function ageFromDob(dob: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dob);
  if (!match) return null;
  const today = new Date();
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  let age = today.getFullYear() - year;
  const birthdayNotYet =
    today.getMonth() + 1 < month || (today.getMonth() + 1 === month && today.getDate() < day);
  if (birthdayNotYet) age -= 1;
  return age >= 0 ? age : null;
}

// Builds the request fields for one wizard step.
function fieldsForStep(step: number, f: FormState): ParentProfileFields {
  switch (step) {
    case 1:
      return {
        parent_full_name: textOrNull(f.parent_full_name),
        preferred_name: textOrNull(f.preferred_name),
        relationship: textOrNull(f.relationship),
        date_of_birth: textOrNull(f.date_of_birth),
        approximate_age: f.date_of_birth ? null : numberOrNull(f.approximate_age),
        preferred_language: textOrNull(f.preferred_language),
      };
    case 2:
      return { parent_mobile: textOrNull(f.parent_mobile) };
    case 3:
      return {
        caregiver_name: textOrNull(f.caregiver_name),
        caregiver_relationship: textOrNull(f.caregiver_relationship),
        caregiver_phone: textOrNull(f.caregiver_phone),
        caregiver_email: textOrNull(f.caregiver_email),
      };
    case 4:
      return {
        known_health_conditions: textOrNull(f.known_health_conditions),
        allergies: textOrNull(f.allergies),
        primary_doctor_name: textOrNull(f.primary_doctor_name),
        doctor_contact_number: textOrNull(f.doctor_contact_number),
        preferred_hospital: textOrNull(f.preferred_hospital),
        care_instructions: textOrNull(f.care_instructions),
      };
    default:
      // Step 5: the additional section holds the profile picture URL.
      return { profile_picture_url: textOrNull(f.profile_picture_url) };
  }
}

export default function ParentOnboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [profile, setProfile] = useState<ParentProfileOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Shown after Finish: choose to add more users or open the parent profile.
  const [finished, setFinished] = useState(false);
  const [nextError, setNextError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getProfile()
      .then((p) => {
        if (!active) return;
        setProfile(p);
        setForm(fromProfile(p));
      })
      .catch((err: unknown) => {
        if (active) setError(errorText(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const update = (key: keyof FormState) => (e: FieldChange) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const parentMissing =
    !form.parent_full_name.trim() || !form.preferred_name.trim() || !form.relationship;

  const percent = profile?.completion.overall ?? 0;
  const isFinal = step === TOTAL_STEPS;

  // Saves the current step's section. Returns the response, or null on failure.
  async function saveCurrentStep(): Promise<ParentProfileOut | null> {
    setSaving(true);
    setError(null);
    try {
      const saved = await saveProfileSection(
        STEP_SECTIONS[step - 1],
        fieldsForStep(step, form),
      );
      setProfile(saved);
      return saved;
    } catch (err) {
      setError(errorText(err));
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (step === 1 && parentMissing) {
      setError("Please fill in parent's full name, preferred name and relationship.");
      return;
    }
    const saved = await saveCurrentStep();
    if (!saved) return;
    if (isFinal) {
      setFinished(true);
    } else {
      setStep((s) => s + 1);
    }
  }

  // "Add more users" goes to the members page of the user's first family.
  async function goAddUsers() {
    setNextError(null);
    try {
      const list = await families.list();
      if (list.length === 0) {
        setNextError("Create a family first, then you can add more users.");
        return;
      }
      navigate(`/family/${list[0].id}/members`);
    } catch (err) {
      setNextError(errorText(err));
    }
  }

  function skip() {
    setError(null);
    setStep((s) => s + 1);
  }

  function back() {
    setError(null);
    setStep((s) => s - 1);
  }

  const showBack = step > 1;
  const showSkip = step > 1 && !isFinal;

  return (
    <main className="parent-layout wizard-page">
      <h1>Set up parent profile</h1>

      <div className="wizard-progress-header">
        <span className="muted">
          Step {step} of {TOTAL_STEPS}: {STEP_TITLES[step - 1]}
        </span>
        <span className="muted">{percent}% complete</span>
      </div>
      <div
        className="wizard-progress"
        role="progressbar"
        aria-label="Profile completion"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div className="wizard-progress-fill" style={{ width: `${percent}%` }} />
      </div>

      {loading && <p className="muted">Loading your profile…</p>}
      {error && <p role="alert" className="wizard-error">{error}</p>}

      <form className="wizard-form" onSubmit={handleSubmit}>
        {step === 1 && (
          <>
            <label className="wizard-field">
              Parent's full name <span className="wizard-required">(required)</span>
              <input
                required
                maxLength={255}
                value={form.parent_full_name}
                onChange={update("parent_full_name")}
              />
            </label>
            <label className="wizard-field">
              Preferred name <span className="wizard-required">(required)</span>
              <input
                required
                maxLength={255}
                value={form.preferred_name}
                onChange={update("preferred_name")}
              />
            </label>
            <label className="wizard-field">
              Relationship <span className="wizard-required">(required)</span>
              <select required value={form.relationship} onChange={update("relationship")}>
                <option value="">Choose…</option>
                {RELATIONSHIP_OPTIONS.map((opt) => (
                  <option key={opt} value={opt.toLowerCase()}>
                    {opt}
                  </option>
                ))}
              </select>
            </label>
            <label className="wizard-field">
              Date of birth
              <input type="date" value={form.date_of_birth} onChange={update("date_of_birth")} />
            </label>
            {form.date_of_birth ? (
              <p className="muted">
                Age: {ageFromDob(form.date_of_birth) ?? "—"} (calculated from date of birth)
              </p>
            ) : (
              <label className="wizard-field">
                Approximate age
                <input
                  type="number"
                  min={0}
                  max={130}
                  inputMode="numeric"
                  value={form.approximate_age}
                  onChange={update("approximate_age")}
                />
              </label>
            )}
            <label className="wizard-field">
              Profile picture (image link)
              <input
                type="url"
                placeholder="https://…"
                value={form.profile_picture_url}
                onChange={update("profile_picture_url")}
              />
            </label>
            <p className="wizard-hint">File upload is coming later. For now, paste a link to a picture.</p>
            <label className="wizard-field">
              Preferred language
              <select value={form.preferred_language} onChange={update("preferred_language")}>
                <option value="">Choose…</option>
                {LANGUAGE_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            </label>
            {parentMissing && (
              <p className="wizard-hint">
                Fill in parent's full name, preferred name and relationship to save this step.
              </p>
            )}
          </>
        )}

        {step === 2 && (
          <label className="wizard-field">
            Parent mobile number
            <input
              type="tel"
              inputMode="tel"
              value={form.parent_mobile}
              onChange={update("parent_mobile")}
            />
          </label>
        )}

        {step === 3 && (
          <>
            <p className="wizard-hint">Primary caregiver for the parent. All optional.</p>
            <label className="wizard-field">
              Caregiver name
              <input maxLength={255} value={form.caregiver_name} onChange={update("caregiver_name")} />
            </label>
            <label className="wizard-field">
              Relationship to parent
              <input
                maxLength={255}
                value={form.caregiver_relationship}
                onChange={update("caregiver_relationship")}
              />
            </label>
            <label className="wizard-field">
              Caregiver phone
              <input
                type="tel"
                inputMode="tel"
                value={form.caregiver_phone}
                onChange={update("caregiver_phone")}
              />
            </label>
            <label className="wizard-field">
              Caregiver email
              <input type="email" value={form.caregiver_email} onChange={update("caregiver_email")} />
            </label>
          </>
        )}

        {step === 4 && (
          <>
            <label className="wizard-field">
              Known health conditions
              <textarea rows={3} value={form.known_health_conditions} onChange={update("known_health_conditions")} />
            </label>
            <label className="wizard-field">
              Allergies
              <textarea rows={2} value={form.allergies} onChange={update("allergies")} />
            </label>
            <label className="wizard-field">
              Primary doctor name
              <input value={form.primary_doctor_name} onChange={update("primary_doctor_name")} />
            </label>
            <label className="wizard-field">
              Doctor's contact number
              <input
                type="tel"
                inputMode="tel"
                value={form.doctor_contact_number}
                onChange={update("doctor_contact_number")}
              />
            </label>
            <label className="wizard-field">
              Preferred hospital
              <input value={form.preferred_hospital} onChange={update("preferred_hospital")} />
            </label>
            <label className="wizard-field">
              Important care instructions
              <textarea rows={4} value={form.care_instructions} onChange={update("care_instructions")} />
            </label>
          </>
        )}

        {isFinal && (
          <section className="wizard-summary">
            <h2>Profile complete: {percent}%</h2>
            <p className="muted">
              Review is done. Press Finish to save and choose what to do next. You can update any section later.
            </p>
            <div className="wizard-completion">
              <h3>Completion by section</h3>
              <ul className="wizard-completion-list">
                {(Object.keys(SECTION_LABELS) as ProfileSection[]).map((key) => (
                  <li key={key}>
                    <span>{SECTION_LABELS[key]}</span>
                    <span>{profile?.completion.sections[key] ?? 0}%</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        )}

        <div className="wizard-actions">
          {showBack && (
            <button type="button" className="btn btn-secondary" onClick={back} disabled={saving}>
              Back
            </button>
          )}
          {showSkip && (
            <button type="button" className="btn btn-secondary" onClick={skip} disabled={saving}>
              Skip
            </button>
          )}
          <button
            type="submit"
            className="btn"
            disabled={saving || loading || (step === 1 && parentMissing)}
          >
            {saving ? "Saving…" : isFinal ? "Finish" : "Save and continue"}
          </button>
        </div>
      </form>

      {finished && (
        <div className="finish-overlay">
          <div
            className="finish-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="finish-title"
          >
            <div className="finish-icon" aria-hidden="true">✓</div>
            <h2 id="finish-title">Profile complete</h2>
            <p className="muted">
              {form.preferred_name.trim() || "Your parent"}'s profile is saved. What would you like
              to do next?
            </p>
            {nextError && <p role="alert" className="wizard-error">{nextError}</p>}
            <div className="finish-actions">
              <button type="button" className="btn btn-secondary" onClick={goAddUsers}>
                Add more users
              </button>
              <button type="button" className="btn" autoFocus onClick={() => navigate("/parent-profile")}>
                Go to parent profile
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
