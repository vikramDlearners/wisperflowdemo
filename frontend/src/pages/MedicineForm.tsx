import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import "../medicines.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { createCareProfileFromOnboarding } from "../careProfileSetup";
import {
  checkImageFile,
  ImageUploadUnavailable,
  uploadMedicineImage,
  useMedicineImage,
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
  /** Preselects the care profile when creating. Otherwise the first profile is used. */
  careProfileId?: string;
  /** Set to edit an existing medicine; omit to create. */
  medicineId?: string;
  /** Called after a successful save. Defaults to returning to the medicines list. */
  onSaved?: (medicine: MedicineOut) => void;
}

const errorText = (err: unknown, fallback: string) =>
  err instanceof ApiError ? err.detail : fallback;

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
  const [people, setPeople] = useState<MemberOut[]>([]);

  const [profileId, setProfileId] = useState(careProfileId ?? "");
  const [displayName, setDisplayName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [quantity, setQuantity] = useState("");
  const [refillDate, setRefillDate] = useState("");
  const [responsible, setResponsible] = useState("");
  const [active, setActive] = useState(true);

  // Medicine photo. Only members with medicines.edit can add or remove it.
  const [canEditPhoto, setCanEditPhoto] = useState(true);
  // The saved photo (GET .../image), shown when editing an existing medicine.
  const currentImage = useMedicineImage(familyId, isEdit ? medicineId : null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

  useEffect(() => {
    if (!photo) {
      setPhotoPreview(null);
      return;
    }
    const url = URL.createObjectURL(photo);
    setPhotoPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  function pickPhoto(file: File | null | undefined) {
    setPhotoError(null);
    if (!file) return;
    const problem = checkImageFile(file);
    if (problem) {
      setPhotoError(problem);
      return;
    }
    setPhoto(file);
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      careProfiles.list(familyId).catch(() => [] as CareProfileOut[]),
      members.list(familyId).catch(() => [] as MemberOut[]),
      isEdit ? medicines.get(familyId, medicineId) : Promise.resolve(null),
      families.me(familyId).catch(() => null),
    ])
      .then(([profileList, memberList, med, access]) => {
        if (cancelled) return;
        setProfiles(profileList);
        setPeople(memberList);
        // If permissions can't be read, show the controls; the server still enforces them.
        setCanEditPhoto(access ? access.permissions.includes("medicines.edit") : true);
        if (med) {
          setProfileId(med.care_profile_id);
          setDisplayName(med.display_name);
          setInstructions(med.instructions_text ?? "");
          setQuantity(med.quantity_remaining?.toString() ?? "");
          setRefillDate(med.refill_date ?? "");
          setResponsible(med.responsible_user_id ?? "");
          setActive(med.active);
        } else {
          setProfileId((current) => current || profileList[0]?.id || "");
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

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!displayName.trim()) {
      setError("Please enter the medicine name.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const refill = refillDate === "" ? null : refillDate;
      const owner = responsible === "" ? null : responsible;
      let result: MedicineOut;

      if (isEdit) {
        const body: MedicineUpdate = {
          display_name: displayName.trim(),
          instructions_text: instructions.trim() || null,
          refill_date: refill,
          responsible_user_id: owner,
          active,
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
      }
      // Photo is a separate upload after the medicine itself is saved.
      let photoProblem: string | null = null;
      try {
        if (photo) await uploadMedicineImage(familyId, result.id, photo);
      } catch (err) {
        photoProblem =
          err instanceof ImageUploadUnavailable
            ? "the server doesn't support medicine photos yet"
            : errorText(err, "the photo upload failed");
      }
      const saved = isEdit ? "Medicine updated" : "Medicine added";
      const notice = photoProblem
        ? `${saved}, but the photo wasn't uploaded: ${photoProblem}.`
        : `${saved}.`;
      if (onSaved) onSaved(result);
      else navigate(listPath, { state: { notice, warn: Boolean(photoProblem) } });
    } catch (err) {
      setError(errorText(err, "Could not save medicine."));
    } finally {
      setSaving(false);
    }
  }

  const title = isEdit ? "Edit medicine" : "Add medicine";

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

        {loading && <p role="status" className="pp-muted">Loading…</p>}
        {error && <p role="alert" className="pp-alert">{error}</p>}

        {!loading && (
          <div className="mf-grid">
            <section className="pp-card">
              <div className="pp-card-head">
                <h2>Medicine details</h2>
                {isEdit && (
                  <span className={`md-status${active ? "" : " is-off"}`}>{active ? "Active" : "Inactive"}</span>
                )}
              </div>

              <div className="mf-fields">
                <label className="pp-field mf-span">
                  <span>
                    Medicine name <span className="mf-req">Required</span>
                  </span>
                  <input
                    required
                    maxLength={255}
                    placeholder="e.g. Amlodipine 5 mg"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                  />
                </label>

                {profiles.length > 1 && !isEdit && (
                  <label className="pp-field mf-span">
                    For
                    <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                      {profiles.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.display_name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                <label className="pp-field mf-span">
                  Schedule & instructions
                  <textarea
                    rows={3}
                    placeholder="e.g. 1 tablet at 9:00 AM and 8:00 PM, after food"
                    value={instructions}
                    onChange={(e) => setInstructions(e.target.value)}
                  />
                </label>

                {!isEdit && (
                  <label className="pp-field">
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
                )}

                <label className="pp-field">
                  Refill date
                  <input type="date" value={refillDate} onChange={(e) => setRefillDate(e.target.value)} />
                </label>

                <label className={`pp-field${isEdit ? "" : " mf-span"}`}>
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
              <section className="pp-card">
                <div className="pp-card-head">
                  <h2>Medicine photo</h2>
                  <span className="md-sub">Optional</span>
                </div>
                {(() => {
                  const shown = photoPreview ?? currentImage;
                  return (
                    <>
                      {shown ? (
                        <div className="mf-photo">
                          <img src={shown} alt={`Photo of ${displayName || "the medicine"}`} />
                        </div>
                      ) : (
                        !canEditPhoto && <p className="pp-muted mf-side-text">No photo yet.</p>
                      )}

                      {canEditPhoto ? (
                        <>
                          {!shown && (
                            <label className="mf-photo-drop">
                              <input
                                type="file"
                                accept="image/jpeg,image/png,image/webp"
                                capture="environment"
                                className="mf-photo-input"
                                onChange={(e) => {
                                  pickPhoto(e.target.files?.[0]);
                                  e.target.value = "";
                                }}
                              />
                              <span className="mf-photo-icon" aria-hidden="true">📷</span>
                              <strong>Add a photo of the medicine</strong>
                              <span className="md-sub">Strip or box · JPG, PNG or WebP · up to 10 MB</span>
                            </label>
                          )}
                          {shown && (
                            <div className="mf-photo-actions">
                              <label className="pp-btn pp-btn-ghost md-btn-link mf-photo-change">
                                Change photo
                                <input
                                  type="file"
                                  accept="image/jpeg,image/png,image/webp"
                                  className="mf-photo-input"
                                  onChange={(e) => {
                                    pickPhoto(e.target.files?.[0]);
                                    e.target.value = "";
                                  }}
                                />
                              </label>
                              {photo && (
                                <button
                                  type="button"
                                  className="mf-photo-remove"
                                  onClick={() => {
                                    setPhoto(null);
                                    setPhotoError(null);
                                  }}
                                >
                                  {currentImage ? "Keep current" : "Remove"}
                                </button>
                              )}
                            </div>
                          )}
                          {photoError && <p role="alert" className="mf-photo-error">{photoError}</p>}
                          {photo && <p className="md-sub mf-photo-note">The photo is uploaded when you save.</p>}
                        </>
                      ) : (
                        <p className="md-sub mf-photo-note">Only members who can edit medicines can add a photo.</p>
                      )}
                    </>
                  );
                })()}
              </section>

              <section className="pp-card">
                <h2>Prefer to scan?</h2>
                <p className="pp-muted mf-side-text">
                  Upload a photo of the prescription and confirm the medicines it finds.
                </p>
                <Link to={`/family/${familyId}/prescription-scan`} className="pp-btn pp-btn-ghost md-btn-link mf-full">
                  Scan prescription
                </Link>
              </section>

              <div className="md-note mf-note">
                <span className="md-note-icon" aria-hidden="true">ⓘ</span>
                <div>
                  <strong>Schedule source and confirmation</strong>
                  <p>
                    Medicine names, timings and instructions are entered by an authorised family member from
                    doctor-provided information. CareCircle does not recommend or change treatment.
                  </p>
                </div>
              </div>
            </aside>
          </div>
        )}

        {!loading && (
          <div className="mf-bottom-actions">
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
