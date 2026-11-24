import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ApiError,
  careProfiles,
  families,
  getProfile,
  saveFamilyParentProfileSection,
  saveProfileSection,
  type ParentProfileFields,
  type ParentProfileOut,
  type ProfileSection,
} from "../api";
import { languageCodeFor } from "../careProfileSetup";
import { CHILD_RELATIONSHIPS, RELATIONSHIP_OPTIONS } from "../lib/constants";

const TOTAL_STEPS = 4;

// Step number (1-based) -> backend section it saves to.
const STEP_SECTIONS: ProfileSection[] = ["parent", "communication", "care", "medical"];

const STEPS = [
  { short: "Parent", title: "About your parent", hint: "Just the basics. You can add more later." },
  { short: "Contact", title: "How can we reach them?", hint: "Optional. Skip this if you don't have it handy." },
  { short: "Caregiver", title: "Who looks after them?", hint: "The main caregiver. Everything here is optional." },
  { short: "Health", title: "Health details", hint: "Optional. Add what you know and update it any time." },
];

const CHILD_STEPS: Record<string, { short: string; title: string; hint: string }> = {
  Parent: { short: "Child", title: "About your child", hint: "Just the basics. You can add more later." },
};

const LANGUAGE_OPTIONS = ["English", "Tamil", "Hindi", "Telugu", "Malayalam", "Kannada"];

// Every input is held as a string; empty strings become null when saved.
interface FormState {
  parent_full_name: string;
  preferred_name: string;
  relationship: string;
  date_of_birth: string;
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
    default:
      return {
        known_health_conditions: textOrNull(f.known_health_conditions),
        allergies: textOrNull(f.allergies),
        primary_doctor_name: textOrNull(f.primary_doctor_name),
        doctor_contact_number: textOrNull(f.doctor_contact_number),
        preferred_hospital: textOrNull(f.preferred_hospital),
        care_instructions: textOrNull(f.care_instructions),
      };
  }
}

export default function ParentOnboarding() {
  const navigate = useNavigate();
  // "?add=1&family=<id>" opens the questions for another profile straight away.
  const [params] = useSearchParams();
  const addFamilyId = params.get("add") ? params.get("family") : null;
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loading, setLoading] = useState(!addFamilyId);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Shown after Finish: choose to add another profile or open the profile.
  const [finished, setFinished] = useState(false);
  const [nextError, setNextError] = useState<string | null>(null);
  // "Add another profile": the same questions again, saved to a new care profile in the family.
  // careProfileId is created when step 1 is first saved.
  const [newParent, setNewParent] = useState<{ familyId: string; careProfileId: string | null } | null>(
    addFamilyId ? { familyId: addFamilyId, careProfileId: null } : null,
  );
  const [child, setChild] = useState(false);

  useEffect(() => {
    if (addFamilyId) return;
    let active = true;
    getProfile()
      .then((p) => {
        if (!active) return;
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
  }, [addFamilyId]);

  function chooseKind(isChildProfile: boolean) {
    setChild(isChildProfile);
    setForm((prev) => ({ ...prev, relationship: "" }));
  }

  const update = (key: keyof FormState) => (e: FieldChange) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const age = ageFromDob(form.date_of_birth);
  const parentMissing =
    !form.parent_full_name.trim() || !form.preferred_name.trim() || !form.relationship;

  // Children have no phone of their own, so the contact step is left out.
  const steps = STEPS.map((s, i) => ({ ...s, ...(child ? CHILD_STEPS[s.short] : undefined), number: i + 1 })).filter(
    (s) => !(child && s.number === 2),
  );
  const current = steps.find((s) => s.number === step) ?? steps[0];
  const person = child ? "child" : "parent";
  const move = (by: 1 | -1) => setStep((s) => (child && s + by === 2 ? s + 2 * by : s + by));

  const isFinal = step === TOTAL_STEPS;

  // Saves the current step's section. Returns the response, or null on failure.
  async function saveCurrentStep(): Promise<ParentProfileOut | null> {
    setSaving(true);
    setError(null);
    try {
      const section = STEP_SECTIONS[step - 1];
      const fields = fieldsForStep(step, form);
      let saved: ParentProfileOut;
      if (newParent) {
        const careProfileId = await ensureNewParentProfile(newParent.familyId, newParent.careProfileId);
        saved = await saveFamilyParentProfileSection(newParent.familyId, careProfileId, section, fields);
      } else {
        saved = await saveProfileSection(section, fields);
      }
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
      setError(`Please fill in your ${person}'s full name, preferred name and relationship.`);
      return;
    }
    const saved = await saveCurrentStep();
    if (!saved) return;
    if (isFinal) {
      setFinished(true);
    } else {
      move(1);
    }
  }

  // The new parent's care profile: created on the first save of step 1, and kept in step with the
  // name, greeting and language if step 1 is saved again.
  async function ensureNewParentProfile(familyId: string, careProfileId: string | null): Promise<string> {
    const names = {
      display_name: form.parent_full_name.trim(),
      greeting_name: form.preferred_name.trim() || form.parent_full_name.trim().split(/\s+/)[0],
      preferred_language: languageCodeFor(form.preferred_language),
    };
    if (careProfileId) {
      if (step === 1) await careProfiles.update(familyId, careProfileId, names);
      return careProfileId;
    }
    const created = await careProfiles.create(familyId, names);
    setNewParent({ familyId, careProfileId: created.id });
    return created.id;
  }

  // "Add another profile" starts the same questions again, for another person in the family.
  async function goAddUsers() {
    setNextError(null);
    try {
      const list = await families.list();
      if (list.length === 0) {
        setNextError("Create a family first, then you can add another profile.");
        return;
      }
      setNewParent({ familyId: list[0].id, careProfileId: null });
      setForm(EMPTY_FORM);
      setChild(false);
      setError(null);
      setStep(1);
      setFinished(false);
      window.scrollTo({ top: 0 });
    } catch (err) {
      setNextError(errorText(err));
    }
  }

  function goToProfile() {
    if (newParent?.careProfileId) {
      navigate(`/family/${newParent.familyId}/parents/${newParent.careProfileId}`);
    } else {
      navigate("/parent-profile");
    }
  }

  function skip() {
    setError(null);
    if (isFinal) setFinished(true);
    else move(1);
  }

  function back() {
    setError(null);
    move(-1);
  }

  const showBack = step > 1;
  const showSkip = step > 1;

  return (
    <main className="parent-layout wizard-page onboarding-page">
      <header className="wizard-brand">
        <img src="/carecircle-logo-full.webp" alt="CareCircle" />
        <span className="muted">{newParent ? "Add a care profile" : "Set up care profile"}</span>
      </header>

      <div className="wizard-card">
        <ol className="wizard-steps" aria-label={`Step ${steps.indexOf(current) + 1} of ${steps.length}`}>
          {steps.map((s) => (
            <li
              key={s.number}
              className={s.number < step ? "is-done" : s.number === step ? "is-current" : undefined}
              aria-current={s.number === step ? "step" : undefined}
            >
              {s.short}
            </li>
          ))}
        </ol>

        <div>
          <h1>{current.title}</h1>
          <p className="wizard-hint">{current.hint}</p>
        </div>

        {loading && <p className="muted">Loading your profile…</p>}
        {error && <p role="alert" className="wizard-error">{error}</p>}

        <form className="wizard-form" onSubmit={handleSubmit}>
          {step === 1 && (
            <>
              {newParent && (
                <fieldset className="role-fieldset wizard-wide">
                  <legend>Who is this profile for?</legend>
                  <div className="wizard-kinds">
                    {[false, true].map((isChildProfile) => (
                      <label key={String(isChildProfile)} className="role-option">
                        <input
                          type="radio"
                          name="kind"
                          checked={child === isChildProfile}
                          onChange={() => chooseKind(isChildProfile)}
                        />
                        {isChildProfile ? "Child" : "Parent"}
                      </label>
                    ))}
                  </div>
                </fieldset>
              )}
              <label className="wizard-field wizard-wide">
                {child ? "Child's" : "Parent's"} full name <span className="wizard-required" aria-hidden="true">*</span>
                <input
                  required
                  maxLength={255}
                  value={form.parent_full_name}
                  onChange={update("parent_full_name")}
                />
              </label>
              <label className="wizard-field">
                Preferred name <span className="wizard-required" aria-hidden="true">*</span>
                <input
                  required
                  maxLength={255}
                  value={form.preferred_name}
                  onChange={update("preferred_name")}
                />
              </label>
              <label className="wizard-field">
                Relationship <span className="wizard-required" aria-hidden="true">*</span>
                <select required value={form.relationship} onChange={update("relationship")}>
                  <option value="">Choose…</option>
                  {(child ? CHILD_RELATIONSHIPS : RELATIONSHIP_OPTIONS).map((opt) => (
                    <option key={opt} value={opt.toLowerCase()}>
                      {opt}
                    </option>
                  ))}
                </select>
              </label>
              <label className="wizard-field">
                Date of birth{age !== null && <span className="wizard-optional"> (age {age})</span>}
                <input type="date" value={form.date_of_birth} onChange={update("date_of_birth")} />
              </label>
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
            </>
          )}

          {step === 2 && (
            <label className="wizard-field wizard-wide">
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
              <label className="wizard-field">
                Caregiver name
                <input maxLength={255} value={form.caregiver_name} onChange={update("caregiver_name")} />
              </label>
              <label className="wizard-field">
                Relationship to {person}
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
              <label className="wizard-field wizard-wide">
                Known health conditions
                <textarea rows={2} value={form.known_health_conditions} onChange={update("known_health_conditions")} />
              </label>
              <label className="wizard-field wizard-wide">
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
              <label className="wizard-field wizard-wide">
                Preferred hospital
                <input value={form.preferred_hospital} onChange={update("preferred_hospital")} />
              </label>
              <label className="wizard-field wizard-wide">
                Important care instructions
                <textarea rows={2} value={form.care_instructions} onChange={update("care_instructions")} />
              </label>
            </>
          )}

          <div className="wizard-actions">
            {addFamilyId && step === 1 && (
              <button type="button" className="btn btn-secondary wizard-back" onClick={() => navigate(-1)} disabled={saving}>
                Cancel
              </button>
            )}
            {showBack && (
              <button type="button" className="btn btn-secondary wizard-back" onClick={back} disabled={saving}>
                Back
              </button>
            )}
            {showSkip && (
              <button type="button" className="wizard-skip" onClick={skip} disabled={saving}>
                Skip
              </button>
            )}
            <button
              type="submit"
              className="btn"
              disabled={saving || loading || (step === 1 && parentMissing)}
            >
              {saving ? "Saving…" : isFinal ? "Finish" : "Continue"}
            </button>
          </div>
        </form>
      </div>

      {finished && (
        <div className="finish-overlay">
          <div
            className="finish-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="finish-title"
          >
            <div className="finish-icon" aria-hidden="true">✓</div>
            <h2 id="finish-title">You're all set</h2>
            <p className="muted">
              {form.preferred_name.trim() || `Your ${person}`}'s profile is saved. What would you like
              to do next?
            </p>
            {nextError && <p role="alert" className="wizard-error">{nextError}</p>}
            <div className="finish-actions">
              <button type="button" className="btn btn-secondary" onClick={goAddUsers}>
                Add another profile
              </button>
              <button type="button" className="btn" autoFocus onClick={goToProfile}>
                Go to profile
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
