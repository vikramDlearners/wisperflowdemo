import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import "../medicines.css";
import DoseButtons from "../components/DoseButtons";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { canRecord, doseLabel, slotName, sortDoses } from "../doses";
import { formatPrice, useMedicineImage } from "../medicineImage";
import {
  ApiError,
  careProfiles,
  families,
  medicines,
  members,
  type CareProfileOut,
  type DoseToday,
  type MedicineOut,
  type MemberOut,
} from "../api";

// One medicine: photo, schedule, stock, refill and the responsible caregiver.

interface MedicineDetailProps {
  familyId: string;
  medicineId: string;
  onEdit?: (medicine: MedicineOut) => void;
}

const LOW_STOCK = 5; // tablets
const REFILL_SOON_DAYS = 7;

function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}
function daysUntil(iso: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((parseDay(iso).getTime() - today.getTime()) / 86_400_000);
}
const longDate = (iso: string) =>
  parseDay(iso).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "long", year: "numeric" });

function refillSummary(iso: string): string {
  const days = daysUntil(iso);
  if (days < 0) return `Overdue by ${-days} day${days === -1 ? "" : "s"}`;
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  return `In ${days} days`;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

const errorText = (err: unknown, fallback: string) => (err instanceof ApiError ? err.detail : fallback);

export default function MedicineDetail({ familyId, medicineId, onEdit }: MedicineDetailProps) {
  const [medicine, setMedicine] = useState<MedicineOut | null>(null);
  const imageUrl = useMedicineImage(familyId, medicineId);
  const [people, setPeople] = useState<MemberOut[]>([]);
  const [profiles, setProfiles] = useState<CareProfileOut[]>([]);
  const [perms, setPerms] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [doses, setDoses] = useState<DoseToday[] | null>(null);
  const [dosesFailed, setDosesFailed] = useState(false);

  const [quantity, setQuantity] = useState("");
  const [savingQty, setSavingQty] = useState(false);
  const [qtyError, setQtyError] = useState<string | null>(null);
  const [qtySaved, setQtySaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      medicines.get(familyId, medicineId),
      members.list(familyId).catch(() => [] as MemberOut[]),
      careProfiles.list(familyId).catch(() => [] as CareProfileOut[]),
      families.me(familyId).catch(() => null),
    ])
      .then(([m, memberList, profileList, access]) => {
        if (cancelled) return;
        setMedicine(m);
        setQuantity(m.quantity_remaining?.toString() ?? "");
        setPeople(memberList);
        setProfiles(profileList);
        setPerms(access?.permissions ?? null);
        setDoses(null);
        setDosesFailed(false);
        medicines
          .dosesToday(familyId, m.care_profile_id)
          .then((all) => {
            if (!cancelled) setDoses(all.filter((d) => d.medicine_id === m.id));
          })
          .catch(() => {
            if (!cancelled) setDosesFailed(true);
          });
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorText(err, "Could not load this medicine."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [familyId, medicineId]);

  async function loadDoses(m: MedicineOut) {
    try {
      const all = await medicines.dosesToday(familyId, m.care_profile_id);
      setDoses(all.filter((d) => d.medicine_id === m.id));
    } catch {
      setDosesFailed(true);
    }
  }

  // Unknown permissions: show the controls and let the server decide.
  const can = (code: string) => perms === null || perms.includes(code);

  function step(delta: number) {
    setQtySaved(false);
    setQtyError(null);
    const current = Number(quantity || 0);
    setQuantity(String(Math.max(0, (Number.isFinite(current) ? current : 0) + delta)));
  }

  async function handleQuantity(e: FormEvent) {
    e.preventDefault();
    const qty = Number(quantity);
    if (quantity === "" || !Number.isInteger(qty) || qty < 0) {
      setQtyError("Enter a whole number, 0 or more.");
      return;
    }
    setSavingQty(true);
    setQtyError(null);
    setQtySaved(false);
    try {
      const updated = await medicines.updateQuantity(familyId, medicineId, { quantity: qty });
      setMedicine(updated);
      setQuantity(updated.quantity_remaining?.toString() ?? "");
      setQtySaved(true);
    } catch (err) {
      setQtyError(errorText(err, "Could not update the stock."));
    } finally {
      setSavingQty(false);
    }
  }

  const listPath = `/family/${familyId}/medicines`;
  const editPath = `/family/${familyId}/medicines/${medicineId}/edit`;

  const owner = medicine?.responsible_user_id
    ? people.find((p) => p.user_id === medicine.responsible_user_id)
    : undefined;
  const recipient = medicine ? profiles.find((p) => p.id === medicine.care_profile_id) : undefined;
  const qty = medicine?.quantity_remaining ?? null;
  const lowStock = qty !== null && qty <= LOW_STOCK;
  const refillDays = medicine?.refill_date ? daysUntil(medicine.refill_date) : null;
  const refillSoon = refillDays !== null && refillDays <= REFILL_SOON_DAYS;
  const dirty = medicine !== null && quantity !== (medicine.quantity_remaining?.toString() ?? "");

  return (
    <WorkspaceLayout familyId={familyId} current="medicines" title={medicine?.display_name ?? "Medicine"}>
      <div className="pp-content md-d">
        <p className="pp-eyebrow">
          <Link to={listPath} className="mf-back">
            ← Medicines
          </Link>
        </p>

        {loading && <p role="status" className="pp-muted">Loading medicine…</p>}
        {error && <p role="alert" className="pp-alert">{error}</p>}

        {medicine && (
          <>
            {/* Header */}
            <section className="md-d-hero">
              <div className="md-d-photo">
                {imageUrl ? (
                  <img src={imageUrl} alt={`Photo of ${medicine.display_name}`} />
                ) : (
                  <span className="md-d-photo-empty" aria-hidden="true">
                    ✚
                  </span>
                )}
              </div>

              <div className="md-d-hero-body">
                <div className="md-d-tags">
                  <span className={`md-status${medicine.active ? "" : " is-off"}`}>
                    {medicine.active ? "Active" : "Inactive"}
                  </span>
                  {recipient && <span className="md-d-tag">For {recipient.display_name}</span>}
                  {medicine.prescription_scan_id && <span className="md-d-tag md-d-tag-rx">🧾 From prescription</span>}
                </div>
                <h1>{medicine.display_name}</h1>
                <p className="md-d-instructions">
                  {medicine.instructions_text || "No schedule or instructions added yet."}
                </p>
                {(lowStock || refillSoon) && (
                  <div className="md-d-alerts">
                    {lowStock && (
                      <span className="md-d-alert">
                        {qty === 0 ? "Out of stock" : `Only ${qty} left`}
                      </span>
                    )}
                    {refillSoon && medicine.refill_date && (
                      <span className="md-d-alert">Refill {refillSummary(medicine.refill_date).toLowerCase()}</span>
                    )}
                  </div>
                )}
              </div>

              {can("medicines.edit") && (
                <div className="md-d-hero-actions">
                  {onEdit ? (
                    <button type="button" className="pp-btn" onClick={() => onEdit(medicine)}>
                      ✎ Edit medicine
                    </button>
                  ) : (
                    <Link to={editPath} className="pp-btn md-btn-link">
                      ✎ Edit medicine
                    </Link>
                  )}
                </div>
              )}
            </section>

            {/* Key facts */}
            <div className="md-d-facts">
              <div className={`pp-card md-d-fact${lowStock ? " is-warn" : ""}`}>
                <span className="md-d-fact-label">Tablets left</span>
                <strong>{qty ?? "—"}</strong>
                <span className="md-sub">{qty === null ? "Stock not tracked" : lowStock ? "Running low" : "In stock"}</span>
              </div>
              <div className={`pp-card md-d-fact${refillSoon ? " is-warn" : ""}`}>
                <span className="md-d-fact-label">Next refill</span>
                <strong>{medicine.refill_date ? refillSummary(medicine.refill_date) : "—"}</strong>
                <span className="md-sub">{medicine.refill_date ? longDate(medicine.refill_date) : "Not set"}</span>
              </div>
              <div className="pp-card md-d-fact">
                <span className="md-d-fact-label">Responsible caregiver</span>
                {owner ? (
                  <div className="md-d-owner">
                    <span className="md-av md-av-blue">{initials(owner.display_name)}</span>
                    <span>
                      <strong>{owner.display_name}</strong>
                      <span className="md-sub">{owner.role_name}</span>
                    </span>
                  </div>
                ) : (
                  <>
                    <strong>Unassigned</strong>
                    <span className="md-sub">No one is responsible yet</span>
                  </>
                )}
              </div>
              <div className="pp-card md-d-fact">
                <span className="md-d-fact-label">Cost</span>
                <strong>{formatPrice(medicine.total_price) ?? "—"}</strong>
                <span className="md-sub">
                  {formatPrice(medicine.unit_price) && medicine.total_medicine_count != null
                    ? `${formatPrice(medicine.unit_price)} × ${medicine.total_medicine_count} tablets`
                    : formatPrice(medicine.unit_price)
                      ? `${formatPrice(medicine.unit_price)} per tablet`
                      : "Price not added"}
                </span>
              </div>
            </div>

            {/* Today's doses */}
            {(dosesFailed || (doses !== null && doses.length > 0)) && (
              <section className="pp-card md-today">
                <h2>Today</h2>
                {dosesFailed || doses === null ? (
                  <p className="pp-muted">Couldn't load today's doses.</p>
                ) : (
                  <ul className="md-today-list">
                    {sortDoses(doses).map((d) => {
                      const label = doseLabel(d, recipient?.timezone);
                      return (
                        <li key={d.slot}>
                          <span className="md-today-slot">{slotName(d.slot)}</span>
                          <span className={`md-dose is-${label.tone}`}>{label.text}</span>
                          {can("medicine_quantity.update") && canRecord(d, recipient?.timezone) && (
                            <DoseButtons
                              familyId={familyId}
                              careProfileId={medicine.care_profile_id}
                              dose={d}
                              medicineName={medicine.display_name}
                              onRecorded={() => void loadDoses(medicine)}
                            />
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            )}

            <div className="md-d-grid">
              {/* Details */}
              <section className="pp-card">
                <h2>Details</h2>
                <dl className="md-d-dl">
                  <div>
                    <dt>Schedule &amp; instructions</dt>
                    <dd>{medicine.instructions_text || <span className="pp-muted">Not added</span>}</dd>
                  </div>
                  <div>
                    <dt>Refill date</dt>
                    <dd>{medicine.refill_date ? longDate(medicine.refill_date) : <span className="pp-muted">Not set</span>}</dd>
                  </div>
                  <div>
                    <dt>Care recipient</dt>
                    <dd>{recipient?.display_name ?? <span className="pp-muted">—</span>}</dd>
                  </div>
                  <div>
                    <dt>Price per tablet</dt>
                    <dd>{formatPrice(medicine.unit_price) ?? <span className="pp-muted">Not added</span>}</dd>
                  </div>
                  <div>
                    <dt>Tablets bought</dt>
                    <dd>{medicine.total_medicine_count ?? <span className="pp-muted">Not added</span>}</dd>
                  </div>
                  <div>
                    <dt>Total cost</dt>
                    <dd>{formatPrice(medicine.total_price) ?? <span className="pp-muted">—</span>}</dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd>
                      {medicine.prescription_scan_id ? (
                        <Link
                          to={`/family/${familyId}/prescription-scan?scan=${medicine.prescription_scan_id}&profile=${medicine.care_profile_id}`}
                        >
                          From a prescription scan · view prescription
                        </Link>
                      ) : (
                        "Entered by a family member"
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{medicine.active ? "Active · included in reminders" : "Inactive · kept in the record only"}</dd>
                  </div>
                </dl>
              </section>

              {/* Stock */}
              <section className="pp-card">
                <h2>Update stock</h2>
                {can("medicine_quantity.update") ? (
                  <form onSubmit={handleQuantity} className="md-d-stock">
                    <p className="pp-muted md-d-stock-help">Count the tablets left and save, for example after a refill.</p>
                    <div className="md-d-stepper">
                      <button type="button" onClick={() => step(-1)} aria-label="One less" disabled={savingQty}>
                        −
                      </button>
                      <input
                        type="number"
                        min={0}
                        step={1}
                        inputMode="numeric"
                        aria-label="Tablets left"
                        value={quantity}
                        onChange={(e) => {
                          setQtySaved(false);
                          setQuantity(e.target.value);
                        }}
                      />
                      <button type="button" onClick={() => step(1)} aria-label="One more" disabled={savingQty}>
                        +
                      </button>
                    </div>
                    <div className="md-d-quick">
                      {[10, 30].map((n) => (
                        <button key={n} type="button" onClick={() => step(n)} disabled={savingQty}>
                          +{n} refill
                        </button>
                      ))}
                    </div>
                    <button type="submit" className="pp-btn md-d-save" disabled={savingQty || !dirty}>
                      {savingQty ? "Saving…" : "Save stock"}
                    </button>
                    {qtyError && <p role="alert" className="mf-photo-error">{qtyError}</p>}
                    {qtySaved && !dirty && <p role="status" className="md-d-saved">✓ Stock updated.</p>}
                  </form>
                ) : (
                  <p className="pp-muted">Only members who can update medicine stock can change this.</p>
                )}
              </section>
            </div>

            <div className="md-note">
              <span className="md-note-icon" aria-hidden="true">ⓘ</span>
              <div>
                <strong>Schedule source and confirmation</strong>
                <p>
                  Medicine names, timings and instructions are entered by an authorised family member from
                  doctor-provided information. CareCircle does not recommend or change treatment.
                </p>
              </div>
            </div>
          </>
        )}
      </div>
    </WorkspaceLayout>
  );
}
