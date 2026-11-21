import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import "../medicines.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { ApiError, medicines, members, type MedicineOut, type MemberOut } from "../api";

interface MedicineListProps {
  familyId: string;
  onSelect?: (medicine: MedicineOut) => void;
  onAdd?: () => void;
}

// A refill is "approaching" when it is due within this many days (or overdue).
const REFILL_SOON_DAYS = 7;

const ICON_TONES = ["md-tone-green", "md-tone-warm", "md-tone-blue"];
const AVATAR_TONES = ["md-av-blue", "md-av-warm", "md-av-green"];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

// Whole days from today until an ISO date (negative when in the past).
function daysUntil(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  const target = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

function refillText(iso: string): string {
  const days = daysUntil(iso);
  if (days < 0) return `Overdue by ${-days} day${days === -1 ? "" : "s"}`;
  if (days === 0) return "Today";
  return `${days} day${days === 1 ? "" : "s"}`;
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function csvCell(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

export default function MedicineList({ familyId, onSelect, onAdd }: MedicineListProps) {
  const [items, setItems] = useState<MedicineOut[] | null>(null);
  const [people, setPeople] = useState<MemberOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");
  const [caregiverFilter, setCaregiverFilter] = useState<string>("all");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([medicines.list(familyId), members.list(familyId).catch(() => [] as MemberOut[])])
      .then(([list, memberList]) => {
        if (cancelled) return;
        setItems(list);
        setPeople(memberList);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.detail : "Could not load medicines.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [familyId]);

  const byUser = useMemo(() => new Map(people.map((p) => [p.user_id, p])), [people]);
  const all = items ?? [];

  const activeCount = all.filter((m) => m.active).length;
  const refillSoon = all.filter(
    (m) => m.active && m.refill_date && daysUntil(m.refill_date) <= REFILL_SOON_DAYS,
  ).length;

  // Caregivers responsible for at least one medicine, for the filter.
  const caregivers = people.filter((p) => all.some((m) => m.responsible_user_id === p.user_id));

  const rows = all.filter(
    (m) =>
      (statusFilter === "all" || (statusFilter === "active" ? m.active : !m.active)) &&
      (caregiverFilter === "all" ||
        (caregiverFilter === "none" ? !m.responsible_user_id : m.responsible_user_id === caregiverFilter)),
  );

  function handleExport() {
    const header = ["Medicine", "Instructions", "Quantity left", "Responsible caregiver", "Refill date", "Status"];
    const lines = rows.map((m) =>
      [
        m.display_name,
        m.instructions_text ?? "",
        m.quantity_remaining?.toString() ?? "",
        (m.responsible_user_id && byUser.get(m.responsible_user_id)?.display_name) || "",
        m.refill_date ?? "",
        m.active ? "Active" : "Inactive",
      ]
        .map(csvCell)
        .join(","),
    );
    const blob = new Blob([[header.join(","), ...lines].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "medicines.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  const addTo = `/family/${familyId}/medicines/new`;

  return (
    <WorkspaceLayout familyId={familyId} current="medicines" title="Medicines">
      <div className="pp-content">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">Care circle · Family workspace</p>
            <h1>Medicines</h1>
            <p className="pp-muted">
              Manage schedules, check-in status and the caregiver responsible for each medicine.
            </p>
          </div>
          <div className="pp-head-actions">
            <Link to={`/family/${familyId}/prescription-scan`} className="pp-btn pp-btn-ghost md-btn-link">
              Scan prescription
            </Link>
            <button type="button" className="pp-btn pp-btn-ghost" onClick={handleExport} disabled={rows.length === 0}>
              ↧ Export
            </button>
            {onAdd ? (
              <button type="button" className="pp-btn" onClick={onAdd}>
                + Add medicine
              </button>
            ) : (
              <Link to={addTo} className="pp-btn md-btn-link">
                + Add medicine
              </Link>
            )}
          </div>
        </div>

        {loading && <p role="status" className="pp-muted">Loading medicines…</p>}
        {error && <p role="alert" className="pp-alert">{error}</p>}

        {!loading && !error && (
          <>
            <div className="md-stats">
              <div className="pp-card md-stat">
                <strong>{activeCount}</strong>
                <span>Active medicine records</span>
              </div>
              <div className="pp-card md-stat">
                <strong>—</strong>
                <span>Daily scheduled check-ins · not configured yet</span>
              </div>
              <div className="pp-card md-stat">
                <strong>{refillSoon}</strong>
                <span>Refill approaching</span>
              </div>
            </div>

            <section className="pp-card md-table-card">
              <div className="pp-card-head">
                <h2>Current medicine schedule</h2>
                <div className="md-filters">
                  <select
                    aria-label="Filter by status"
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
                  >
                    <option value="all">All medicines</option>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </select>
                  <select
                    aria-label="Filter by caregiver"
                    value={caregiverFilter}
                    onChange={(e) => setCaregiverFilter(e.target.value)}
                  >
                    <option value="all">All caregivers</option>
                    {caregivers.map((c) => (
                      <option key={c.user_id} value={c.user_id}>
                        {c.display_name}
                      </option>
                    ))}
                    <option value="none">Unassigned</option>
                  </select>
                </div>
              </div>

              {all.length === 0 ? (
                <div className="md-empty">
                  <p>No medicines yet.</p>
                  <Link to={addTo} className="pp-btn md-btn-link">
                    + Add the first medicine
                  </Link>
                </div>
              ) : rows.length === 0 ? (
                <p className="md-empty pp-muted">No medicines match these filters.</p>
              ) : (
                <div className="md-table-wrap">
                  <table className="md-table">
                    <thead>
                      <tr>
                        <th>Medicine</th>
                        <th>Schedule</th>
                        <th>Next check-in</th>
                        <th>Responsible caregiver</th>
                        <th>Refill</th>
                        <th>Status</th>
                        <th>
                          <span className="md-sr">Actions</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((m, i) => {
                        const owner = m.responsible_user_id ? byUser.get(m.responsible_user_id) : undefined;
                        return (
                          <tr key={m.id} onClick={() => onSelect?.(m)}>
                            <td className="md-cell-med">
                              <div className="md-med">
                                <span className={`md-med-icon ${ICON_TONES[i % ICON_TONES.length]}`} aria-hidden="true">
                                  ✚
                                </span>
                                <div>
                                  <div className="md-strong">{m.display_name}</div>
                                  <div className="md-sub">
                                    {m.quantity_remaining != null
                                      ? `${m.quantity_remaining} left`
                                      : "Quantity not tracked"}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td data-label="Schedule">
                              <div>{m.instructions_text || "—"}</div>
                              <div className="md-sub">{m.instructions_text ? "Instructions" : "Not set"}</div>
                            </td>
                            <td data-label="Next check-in">
                              <div>—</div>
                              <div className="md-sub">Not scheduled</div>
                            </td>
                            <td data-label="Caregiver">
                              {owner ? (
                                <div className="md-owner">
                                  <span className={`md-av ${AVATAR_TONES[i % AVATAR_TONES.length]}`}>
                                    {initials(owner.display_name)}
                                  </span>
                                  <div>
                                    <div className="md-strong">{owner.display_name}</div>
                                    <div className="md-sub">{owner.role_name}</div>
                                  </div>
                                </div>
                              ) : (
                                <span className="md-sub">Unassigned</span>
                              )}
                            </td>
                            <td data-label="Refill">
                              <div>{m.refill_date ? refillText(m.refill_date) : "—"}</div>
                              <div className="md-sub">
                                {m.refill_date ? `Refill on ${formatDate(m.refill_date)}` : "Not configured"}
                              </div>
                            </td>
                            <td className="md-cell-status">
                              <span className={`md-status${m.active ? "" : " is-off"}`}>
                                {m.active ? "Active" : "Inactive"}
                              </span>
                            </td>
                            <td className="md-cell-more">
                              <Link
                                to={`/family/${familyId}/medicines/${m.id}`}
                                className="md-more"
                                aria-label={`Open ${m.display_name}`}
                                onClick={(e) => e.stopPropagation()}
                              >
                                •••
                              </Link>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <aside className="md-note">
              <span className="md-note-icon" aria-hidden="true">ⓘ</span>
              <div>
                <strong>Schedule source and confirmation</strong>
                <p>
                  Medicine names, timings and instructions are entered by an authorised family member from
                  doctor-provided information. CareCircle does not recommend or change treatment.
                </p>
              </div>
            </aside>
          </>
        )}
      </div>
    </WorkspaceLayout>
  );
}
