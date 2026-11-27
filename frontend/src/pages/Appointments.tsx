import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import TimeSelect from "../components/TimeSelect";
import { Link, useParams } from "react-router-dom";
import "../medicines.css";
import "../appointments.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { createCareProfileFromOnboarding } from "../careProfileSetup";
import {
  ApiError,
  appointments as api,
  careProfiles,
  medicines as medicinesApi,
  type AppointmentListOut,
  type AppointmentOut,
  type AppointmentStatus,
  type CareProfileOut,
  type MedicineOut,
} from "../api";

// Appointments for the family's care recipient (a care profile), using
// GET/POST /api/appointments and GET/PATCH/DELETE /api/appointments/{id}.

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const STATUS_LABEL: Record<AppointmentStatus, string> = {
  scheduled: "Scheduled",
  rescheduled: "Rescheduled",
  completed: "Completed",
  cancelled: "Cancelled",
};

type LoadError = { kind: "auth" | "forbidden" | "general"; message: string };

interface FormState {
  id: string | null; // null = new appointment
  profileId: string; // which parent it is for
  scheduled_date: string;
  start_time: string;
  provider: string;
  reason: string;
  location: string;
  notes: string;
  fee: string; // rupees, "" when not known
  doctor_notes: string;
}

/** "₹500" / "₹650.50" for a fee, or null when none was added. */
function formatFee(fee: string | number | null | undefined): string | null {
  if (fee === null || fee === undefined || fee === "") return null;
  const n = Number(fee);
  if (!Number.isFinite(n)) return null;
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
}

const VOICE_EXAMPLE =
  "Amma's eye check-up with Dr. Rao at Apollo Hospital next Tuesday at 10:30 am. Bring the old reports.";

// ---------- date helpers (dates are local calendar days, "YYYY-MM-DD") ----------
const pad = (n: number) => String(n).padStart(2, "0");
const isoDay = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}
function startOfToday(): Date {
  const t = new Date();
  t.setHours(0, 0, 0, 0);
  return t;
}
const daysBetween = (a: Date, b: Date) => Math.round((b.getTime() - a.getTime()) / 86_400_000);

function formatTime(hhmm: string): string {
  const m = /^(\d{1,2}):(\d{2})/.exec(hhmm);
  if (!m) return hhmm;
  const h = Number(m[1]);
  return `${((h + 11) % 12) + 1}:${m[2]} ${h < 12 ? "AM" : "PM"}`;
}

// Compact form for calendar chips: "10 AM", "2:30 PM".
const shortTime = (hhmm: string) => formatTime(hhmm).replace(":00 ", " ");

function relativeDay(iso: string): string {
  const diff = daysBetween(startOfToday(), parseDay(iso));
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  return parseDay(iso).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

const longDate = (iso: string) =>
  parseDay(iso).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });

const isOpen = (a: AppointmentOut) => a.status === "scheduled" || a.status === "rescheduled";

function errorFrom(err: unknown): LoadError {
  if (err instanceof ApiError) {
    if (err.status === 401) return { kind: "auth", message: "Your session has expired. Please sign in again." };
    if (err.status === 403)
      return {
        kind: "forbidden",
        message:
          "You don't have permission to see appointments in this family. Ask the family manager to give your role the appointment permissions.",
      };
    return { kind: "general", message: err.detail };
  }
  return { kind: "general", message: "Something went wrong. Please check your connection and try again." };
}

export default function Appointments() {
  const { familyId = "" } = useParams();

  const [profiles, setProfiles] = useState<CareProfileOut[]>([]);
  const [careProfileId, setCareProfileId] = useState("");
  const [data, setData] = useState<AppointmentListOut>({ upcoming: [], past: [] });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<LoadError | null>(null);

  const [view, setView] = useState<"calendar" | "list">("calendar");
  const [month, setMonth] = useState(() => {
    const t = startOfToday();
    return new Date(t.getFullYear(), t.getMonth(), 1);
  });
  const [selectedDay, setSelectedDay] = useState(() => isoDay(startOfToday()));

  const [detail, setDetail] = useState<AppointmentOut | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Voice mode for a new appointment: say it in one go (Wispr Flow types it), "Fill the form" fills the fields.
  const [spoken, setSpoken] = useState("");
  const [reading, setReading] = useState(false);
  const [readNote, setReadNote] = useState<{ text: string; bad?: boolean } | null>(null);
  const [filled, setFilled] = useState<string[]>([]);
  const voiceRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (filled.length === 0) return;
    const t = window.setTimeout(() => setFilled([]), 6000);
    return () => window.clearTimeout(t);
  }, [filled]);

  const loadAppointments = useCallback(async (profileId: string) => {
    if (!profileId) {
      setData({ upcoming: [], past: [] });
      return;
    }
    setData(await api.list(profileId));
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    (async () => {
      try {
        const list = await careProfiles.list(familyId);
        if (!active) return;
        setProfiles(list);
        const first = list[0]?.id ?? "";
        setCareProfileId(first);
        if (first) {
          const res = await api.list(first);
          if (active) setData(res);
        }
      } catch (err) {
        if (active) setLoadError(errorFrom(err));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [familyId]);

  async function switchProfile(id: string) {
    setCareProfileId(id);
    setLoadError(null);
    try {
      await loadAppointments(id);
    } catch (err) {
      setLoadError(errorFrom(err));
    }
  }

  const all = useMemo(() => [...data.upcoming, ...data.past], [data]);
  const byDay = useMemo(() => {
    const map = new Map<string, AppointmentOut[]>();
    for (const a of all) {
      const list = map.get(a.scheduled_date) ?? [];
      list.push(a);
      map.set(a.scheduled_date, list);
    }
    for (const list of map.values()) list.sort((x, y) => x.start_time.localeCompare(y.start_time));
    return map;
  }, [all]);

  // ---------- stats ----------
  const today = startOfToday();
  const upcomingOpen = data.upcoming.filter(isOpen);
  const next7 = upcomingOpen.filter((a) => daysBetween(today, parseDay(a.scheduled_date)) <= 7).length;
  const completedThisMonth = all.filter((a) => {
    const d = parseDay(a.scheduled_date);
    return a.status === "completed" && d.getMonth() === today.getMonth() && d.getFullYear() === today.getFullYear();
  }).length;
  const nextAppt = [...upcomingOpen].sort(
    (a, b) => a.scheduled_date.localeCompare(b.scheduled_date) || a.start_time.localeCompare(b.start_time),
  )[0];

  // ---------- calendar grid ----------
  const cells = useMemo(() => {
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const start = new Date(first);
    start.setDate(1 - first.getDay());
    const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
    const weeks = Math.ceil((first.getDay() + daysInMonth) / 7);
    return Array.from({ length: weeks * 7 }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return d;
    });
  }, [month]);

  const shiftMonth = (delta: number) => setMonth((m) => new Date(m.getFullYear(), m.getMonth() + delta, 1));
  function goToday() {
    const t = startOfToday();
    setMonth(new Date(t.getFullYear(), t.getMonth(), 1));
    setSelectedDay(isoDay(t));
  }

  // ---------- actions ----------
  function openAdd(day?: string) {
    setActionError(null);
    setNotice(null);
    setSpoken("");
    setReadNote(null);
    setFilled([]);
    setForm({
      id: null,
      profileId: careProfileId,
      scheduled_date: day ?? isoDay(today),
      start_time: "10:00",
      provider: "",
      reason: "",
      location: "",
      notes: "",
      fee: "",
      doctor_notes: "",
    });
    window.setTimeout(() => voiceRef.current?.focus(), 50);
  }

  // /appointments?new=1 opens the Add form once the page has loaded.
  const openNewRef = useRef(new URLSearchParams(window.location.search).has("new"));
  useEffect(() => {
    if (loading || !openNewRef.current) return;
    openNewRef.current = false;
    if (!loadError) openAdd();
  }, [loading, loadError]);

  async function fillFromSpeech() {
    if (!form) return;
    if (!spoken.trim()) {
      setReadNote({ text: "Say or type the appointment first.", bad: true });
      voiceRef.current?.focus();
      return;
    }
    setReading(true);
    setReadNote(null);
    try {
      const r = await api.parseText(familyId, spoken.trim(), isoDay(new Date()));
      const next: FormState = { ...form };
      const got: string[] = [];
      if (r.care_recipient_id && profiles.some((p) => p.id === r.care_recipient_id) && profiles.length > 1) {
        next.profileId = r.care_recipient_id;
        got.push("parent");
      }
      if (r.reason) {
        next.reason = r.reason;
        got.push("reason");
      }
      if (r.provider) {
        next.provider = r.provider;
        got.push("doctor");
      }
      if (r.location) {
        next.location = r.location;
        got.push("place");
      }
      if (r.scheduled_date) {
        next.scheduled_date = r.scheduled_date;
        got.push("date");
      }
      if (r.start_time) {
        next.start_time = r.start_time;
        got.push("time");
      }
      if (r.notes) {
        next.notes = r.notes;
        got.push("notes");
      }
      setForm(next);
      setFilled(got);
      setActionError(null);
      setReadNote(
        got.length
          ? {
              text: `Filled ${got.join(", ")}${r.source === "gemini" ? " (read by Gemini)" : ""}. Check it and press Add appointment.`,
            }
          : { text: "Couldn't make out an appointment from that. Try again, or fill the fields below.", bad: true },
      );
    } catch (err) {
      setReadNote({ text: errorFrom(err).message, bad: true });
    } finally {
      setReading(false);
    }
  }

  const filledClass = (key: string) => (filled.includes(key) ? " ap-filled" : "");

  function openEdit(a: AppointmentOut) {
    setActionError(null);
    setDetail(null);
    setForm({
      id: a.id,
      profileId: a.care_recipient_id,
      scheduled_date: a.scheduled_date,
      start_time: a.start_time,
      provider: a.provider,
      reason: a.reason,
      location: a.location ?? "",
      notes: a.notes,
      fee: a.fee != null && a.fee !== "" ? String(Number(a.fee)) : "",
      doctor_notes: a.doctor_notes ?? "",
    });
  }

  function openDetail(a: AppointmentOut) {
    setActionError(null);
    setConfirmDelete(false);
    setDetail(a);
  }

  async function refresh(profileId = careProfileId) {
    try {
      await loadAppointments(profileId);
    } catch (err) {
      setLoadError(errorFrom(err));
    }
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    if (!form.scheduled_date || !/^\d{2}:\d{2}$/.test(form.start_time) || !form.provider.trim() || !form.reason.trim()) {
      setActionError("Please fill in the date, time, doctor or clinic, and reason.");
      return;
    }
    if (form.fee.trim() !== "" && !(Number(form.fee) >= 0)) {
      setActionError("The fee must be a number, 0 or more.");
      return;
    }
    const visit = {
      fee: form.fee.trim() === "" ? null : Math.round(Number(form.fee) * 100) / 100,
      doctor_notes: form.doctor_notes.trim() || null,
    };
    setBusy(true);
    setActionError(null);
    try {
      if (form.id) {
        const original = all.find((a) => a.id === form.id);
        const moved =
          original && (original.scheduled_date !== form.scheduled_date || original.start_time !== form.start_time);
        await api.update(form.id, {
          scheduled_date: form.scheduled_date,
          start_time: form.start_time,
          provider: form.provider.trim(),
          reason: form.reason.trim(),
          location: form.location.trim() || null,
          notes: form.notes.trim(),
          ...visit,
          // Moving a scheduled visit marks it as rescheduled.
          ...(moved && original?.status === "scheduled" ? { status: "rescheduled" as const } : {}),
        });
        setNotice("Appointment updated.");
        await refresh();
      } else {
        // Appointments belong to a care profile; create one first if the family has none.
        let profileId = form.profileId || careProfileId;
        if (!profileId) {
          const created = await createCareProfileFromOnboarding(familyId);
          setProfiles([created]);
          setCareProfileId(created.id);
          profileId = created.id;
        }
        await api.create({
          family_id: familyId,
          care_recipient_id: profileId,
          scheduled_date: form.scheduled_date,
          start_time: form.start_time,
          provider: form.provider.trim(),
          reason: form.reason.trim(),
          location: form.location.trim() || null,
          notes: form.notes.trim(),
          ...visit,
        });
        const forName = profiles.length > 1 ? profiles.find((p) => p.id === profileId)?.display_name : null;
        setNotice(forName ? `Appointment added for ${forName}.` : "Appointment added.");
        // Show the parent it was added for.
        if (profileId !== careProfileId) setCareProfileId(profileId);
        await refresh(profileId);
      }
      const d = parseDay(form.scheduled_date);
      setMonth(new Date(d.getFullYear(), d.getMonth(), 1));
      setSelectedDay(form.scheduled_date);
      setForm(null);
    } catch (err) {
      setActionError(errorFrom(err).message);
    } finally {
      setBusy(false);
    }
  }

  // ---------- after the visit: fee, doctor's notes, medicines given ----------
  const [visit, setVisit] = useState<{ fee: string; doctor_notes: string } | null>(null);
  const [picking, setPicking] = useState<string[] | null>(null); // medicine ids ticked in the picker
  const [parentMedicines, setParentMedicines] = useState<MedicineOut[] | null>(null);

  useEffect(() => {
    // A different appointment (or none): close the inline editors.
    setVisit(null);
    setPicking(null);
  }, [detail?.id]);

  function openVisit(a: AppointmentOut) {
    setVisit({
      fee: a.fee != null && a.fee !== "" ? String(Number(a.fee)) : "",
      doctor_notes: a.doctor_notes ?? "",
    });
  }

  async function saveVisit(a: AppointmentOut) {
    if (!visit) return;
    if (visit.fee.trim() !== "" && !(Number(visit.fee) >= 0)) {
      setActionError("The fee must be a number, 0 or more.");
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api.update(a.id, {
        fee: visit.fee.trim() === "" ? null : Math.round(Number(visit.fee) * 100) / 100,
        doctor_notes: visit.doctor_notes.trim() || null,
      });
      setDetail(updated);
      setVisit(null);
      setNotice("Visit details saved.");
      await refresh();
    } catch (err) {
      setActionError(errorFrom(err).message);
    } finally {
      setBusy(false);
    }
  }

  async function openPicker(a: AppointmentOut) {
    setActionError(null);
    setPicking((a.medicines ?? []).map((m) => m.id));
    try {
      const list = await medicinesApi.list(familyId);
      setParentMedicines(list.filter((m) => m.care_profile_id === a.care_recipient_id));
    } catch (err) {
      setParentMedicines([]);
      setActionError(errorFrom(err).message);
    }
  }

  async function saveMedicines(a: AppointmentOut) {
    if (!picking) return;
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api.setMedicines(a.id, picking);
      setDetail(updated);
      setPicking(null);
      const n = updated.medicines?.length ?? 0;
      setNotice(n ? `${n} ${n === 1 ? "medicine" : "medicines"} linked to this appointment.` : "Medicines unlinked.");
      await refresh();
    } catch (err) {
      setActionError(errorFrom(err).message);
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(a: AppointmentOut, status: AppointmentStatus) {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await api.update(a.id, { status });
      setDetail(updated);
      setNotice(`Appointment marked as ${STATUS_LABEL[status].toLowerCase()}.`);
      // After the visit: ask for the fee and what the doctor said.
      if (status === "completed") openVisit(updated);
      await refresh();
    } catch (err) {
      setActionError(errorFrom(err).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(a: AppointmentOut) {
    setBusy(true);
    setActionError(null);
    try {
      await api.remove(a.id);
      setDetail(null);
      setConfirmDelete(false);
      setNotice("Appointment deleted.");
      await refresh();
    } catch (err) {
      setActionError(errorFrom(err).message);
    } finally {
      setBusy(false);
    }
  }

  const selectedList = byDay.get(selectedDay) ?? [];
  const recentPast = data.past.slice(0, 4);
  const canEdit = loadError?.kind !== "forbidden" && loadError?.kind !== "auth";

  return (
    <WorkspaceLayout familyId={familyId} current="appointments" title="Appointments">
      <div className="pp-content">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">Care circle · Family workspace</p>
            <h1>Appointments</h1>
            <p className="pp-muted">
              Keep upcoming visits, notes and follow-ups in one shared calendar.
            </p>
          </div>
          <div className="pp-head-actions">
            <button
              type="button"
              className="pp-btn pp-btn-ghost"
              onClick={() => setView(view === "calendar" ? "list" : "calendar")}
            >
              {view === "calendar" ? "List view" : "Calendar view"}
            </button>
            <button type="button" className="pp-btn" onClick={() => openAdd()} disabled={loading || !canEdit}>
              + Add appointment
            </button>
          </div>
        </div>

        {loading && <p role="status" className="pp-muted">Loading appointments…</p>}
        {loadError && (
          <div role="alert" className={`ap-banner${loadError.kind === "general" ? " is-error" : " is-warn"}`}>
            {loadError.message}
          </div>
        )}
        {notice && !form && !detail && (
          <p role="status" className="pp-saved">
            ✓ {notice}
          </p>
        )}

        {!loading && profiles.length > 1 && (
          <label className="pp-field ap-profile">
            Showing appointments for
            <select value={careProfileId} onChange={(e) => void switchProfile(e.target.value)}>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </label>
        )}

        {/* Without access (401/403) there is nothing meaningful to show beyond the banner. */}
        {!loading && canEdit && (
          <>
            <div className="md-stats">
              <div className="pp-card md-stat">
                <strong>{upcomingOpen.length}</strong>
                <span>Upcoming appointment{upcomingOpen.length === 1 ? "" : "s"}</span>
              </div>
              <div className="pp-card md-stat">
                <strong>{next7}</strong>
                <span>In the next 7 days</span>
              </div>
              <div className="pp-card md-stat">
                <strong>{completedThisMonth}</strong>
                <span>Completed this month</span>
              </div>
            </div>

            <div className="ap-grid">
              {view === "calendar" ? (
                <section className="pp-card ap-cal" aria-label="Calendar">
                  <div className="ap-cal-head">
                    <h2>{month.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</h2>
                    <div className="ap-cal-nav">
                      <button type="button" onClick={() => shiftMonth(-1)} aria-label="Previous month">
                        ‹
                      </button>
                      <button type="button" className="ap-today" onClick={goToday}>
                        Today
                      </button>
                      <button type="button" onClick={() => shiftMonth(1)} aria-label="Next month">
                        ›
                      </button>
                    </div>
                  </div>

                  <div className="ap-weekdays" aria-hidden="true">
                    {WEEKDAYS.map((d) => (
                      <span key={d}>{d}</span>
                    ))}
                  </div>
                  <div className="ap-days">
                    {cells.map((d) => {
                      const iso = isoDay(d);
                      const items = byDay.get(iso) ?? [];
                      const outside = d.getMonth() !== month.getMonth();
                      const isToday = iso === isoDay(today);
                      return (
                        <div
                          key={iso}
                          className={`ap-day${outside ? " is-outside" : ""}${isToday ? " is-today" : ""}${
                            iso === selectedDay ? " is-selected" : ""
                          }`}
                        >
                          <button
                            type="button"
                            className="ap-day-btn"
                            onClick={() => setSelectedDay(iso)}
                            aria-label={`${longDate(iso)}${items.length ? `, ${items.length} appointment${items.length === 1 ? "" : "s"}` : ""}`}
                            aria-pressed={iso === selectedDay}
                          >
                            {d.getDate()}
                          </button>
                          <div className="ap-chips">
                            {items.slice(0, 2).map((a) => (
                              <button
                                key={a.id}
                                type="button"
                                className={`ap-chip is-${a.status}`}
                                onClick={() => openDetail(a)}
                                title={`${formatTime(a.start_time)} · ${a.reason}`}
                              >
                                {shortTime(a.start_time)} · {a.reason}
                              </button>
                            ))}
                            {items.length > 2 && (
                              <button type="button" className="ap-more" onClick={() => setSelectedDay(iso)}>
                                +{items.length - 2} more
                              </button>
                            )}
                          </div>
                          {items.length > 0 && <span className={`ap-dot is-${items[0].status}`} aria-hidden="true" />}
                        </div>
                      );
                    })}
                  </div>

                  <div className="ap-dayview">
                    <div className="ap-dayview-head">
                      <strong>{longDate(selectedDay)}</strong>
                      {canEdit && (
                        <button type="button" className="ap-link" onClick={() => openAdd(selectedDay)}>
                          + Add on this day
                        </button>
                      )}
                    </div>
                    {selectedList.length === 0 ? (
                      <p className="pp-muted ap-empty">No appointments on this day.</p>
                    ) : (
                      <ul className="ap-list">
                        {selectedList.map((a) => (
                          <ApptRow key={a.id} a={a} onOpen={openDetail} />
                        ))}
                      </ul>
                    )}
                  </div>
                </section>
              ) : (
                <section className="pp-card ap-listview" aria-label="All appointments">
                  <h2>Upcoming</h2>
                  {data.upcoming.length === 0 ? (
                    <p className="pp-muted ap-empty">No upcoming appointments.</p>
                  ) : (
                    <ul className="ap-list">
                      {data.upcoming.map((a) => (
                        <ApptRow key={a.id} a={a} onOpen={openDetail} showDate />
                      ))}
                    </ul>
                  )}
                  <h2 className="ap-list-gap">Past</h2>
                  {data.past.length === 0 ? (
                    <p className="pp-muted ap-empty">No past appointments.</p>
                  ) : (
                    <ul className="ap-list">
                      {data.past.map((a) => (
                        <ApptRow key={a.id} a={a} onOpen={openDetail} showDate />
                      ))}
                    </ul>
                  )}
                </section>
              )}

              <div className="ap-side">
                <section className="pp-card">
                  <h2>Next appointment</h2>
                  {nextAppt ? (
                    <div className="ap-next">
                      <span className="ap-when">
                        {relativeDay(nextAppt.scheduled_date)} · {formatTime(nextAppt.start_time)}
                      </span>
                      <p className="ap-next-title">{nextAppt.reason}</p>
                      <p className="pp-muted">{nextAppt.provider}</p>
                      {nextAppt.notes && (
                        <div className="ap-next-notes">
                          <span>Notes</span>
                          <p>{nextAppt.notes}</p>
                        </div>
                      )}
                      <div className="ap-next-status">
                        <span className="pp-muted">Status</span>
                        <span className={`ap-status is-${nextAppt.status}`}>{STATUS_LABEL[nextAppt.status]}</span>
                      </div>
                      <button type="button" className="pp-btn ap-full" onClick={() => openDetail(nextAppt)}>
                        View appointment
                      </button>
                    </div>
                  ) : (
                    <div className="ap-next-empty">
                      <p className="pp-muted">No upcoming appointments.</p>
                      {canEdit && (
                        <button type="button" className="pp-btn pp-btn-ghost ap-full" onClick={() => openAdd()}>
                          + Add appointment
                        </button>
                      )}
                    </div>
                  )}
                </section>

                <section className="pp-card">
                  <h2>Recent visits</h2>
                  {recentPast.length === 0 ? (
                    <p className="pp-muted ap-empty">Past appointments will show here.</p>
                  ) : (
                    <ul className="ap-list ap-list-compact">
                      {recentPast.map((a) => (
                        <ApptRow key={a.id} a={a} onOpen={openDetail} showDate />
                      ))}
                    </ul>
                  )}
                </section>
              </div>
            </div>
          </>
        )}
      </div>

      {/* ---------- Appointment details ---------- */}
      {detail && (
        <Modal title="Appointment" onClose={() => setDetail(null)}>
          <span className={`ap-status is-${detail.status}`}>{STATUS_LABEL[detail.status]}</span>
          <p className="ap-next-title">{detail.reason}</p>
          <dl className="ap-dl">
            <div>
              <dt>When</dt>
              <dd>
                {longDate(detail.scheduled_date)} · {formatTime(detail.start_time)}
              </dd>
            </div>
            <div>
              <dt>Doctor / clinic</dt>
              <dd>{detail.provider}</dd>
            </div>
            {detail.location && (
              <div>
                <dt>Where</dt>
                <dd>{detail.location}</dd>
              </div>
            )}
            <div>
              <dt>Notes before the visit</dt>
              <dd className={detail.notes ? "" : "pp-muted"}>{detail.notes || "No notes"}</dd>
            </div>
          </dl>

          <section className="ap-visit" aria-labelledby="ap-visit-title">
            <div className="ap-visit-head">
              <h3 id="ap-visit-title">After the visit</h3>
              {!visit && (
                <button type="button" className="ap-link" onClick={() => openVisit(detail)} disabled={busy}>
                  {formatFee(detail.fee) || detail.doctor_notes ? "Edit" : "+ Add fee and doctor's notes"}
                </button>
              )}
            </div>

            {visit ? (
              <div className="ap-visit-form">
                <label className="pp-field">
                  Fee (₹)
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    inputMode="decimal"
                    placeholder="e.g. 500"
                    value={visit.fee}
                    autoFocus
                    onChange={(e) => setVisit({ ...visit, fee: e.target.value })}
                  />
                </label>
                <label className="pp-field">
                  What the doctor said
                  <textarea
                    rows={4}
                    placeholder="e.g. BP is better. Reduce salt. Continue Amlodipine. Review in 3 months."
                    value={visit.doctor_notes}
                    onChange={(e) => setVisit({ ...visit, doctor_notes: e.target.value })}
                  />
                </label>
                <div className="ap-modal-actions">
                  <button type="button" className="pp-btn pp-btn-ghost" onClick={() => setVisit(null)} disabled={busy}>
                    Cancel
                  </button>
                  <button type="button" className="pp-btn" onClick={() => void saveVisit(detail)} disabled={busy}>
                    {busy ? "Saving…" : "Save visit details"}
                  </button>
                </div>
              </div>
            ) : (
              <dl className="ap-dl ap-visit-dl">
                <div>
                  <dt>Fee</dt>
                  <dd className={formatFee(detail.fee) ? "ap-fee" : "pp-muted"}>{formatFee(detail.fee) ?? "Not added"}</dd>
                </div>
                <div>
                  <dt>Doctor's notes</dt>
                  <dd className={detail.doctor_notes ? "ap-doctor-notes" : "pp-muted"}>
                    {detail.doctor_notes || "Not added"}
                  </dd>
                </div>
              </dl>
            )}

            <div className="ap-visit-head">
              <h4>Medicines given</h4>
              {!picking && (
                <button type="button" className="ap-link" onClick={() => void openPicker(detail)} disabled={busy}>
                  {detail.medicines?.length ? "Change" : "+ Link medicines"}
                </button>
              )}
            </div>
            {picking ? (
              <div className="ap-pick">
                {parentMedicines === null ? (
                  <p className="pp-muted">Loading medicines…</p>
                ) : parentMedicines.length === 0 ? (
                  <p className="pp-muted">No medicines added for this parent yet.</p>
                ) : (
                  <ul className="ap-pick-list">
                    {parentMedicines.map((m) => {
                      const on = picking.includes(m.id);
                      const elsewhere = m.appointment_id && m.appointment_id !== detail.id;
                      return (
                        <li key={m.id}>
                          <label className={`ap-pick-item${on ? " is-on" : ""}`}>
                            <input
                              type="checkbox"
                              checked={on}
                              onChange={() =>
                                setPicking(on ? picking.filter((id) => id !== m.id) : [...picking, m.id])
                              }
                            />
                            <span>
                              <strong>{m.display_name}</strong>
                              {(elsewhere || !m.active) && (
                                <small>
                                  {!m.active ? "Stopped" : ""}
                                  {!m.active && elsewhere ? " · " : ""}
                                  {elsewhere ? "Linked to another appointment, ticking moves it here" : ""}
                                </small>
                              )}
                            </span>
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                )}
                <Link
                  className="ap-link ap-new-med"
                  to={`/family/${familyId}/medicines/new?profile=${detail.care_recipient_id}&appointment=${detail.id}&from=appointments`}
                >
                  + Add a new medicine from this visit
                </Link>
                <div className="ap-modal-actions">
                  <button type="button" className="pp-btn pp-btn-ghost" onClick={() => setPicking(null)} disabled={busy}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="pp-btn"
                    onClick={() => void saveMedicines(detail)}
                    disabled={busy || parentMedicines === null}
                  >
                    {busy ? "Saving…" : "Save medicines"}
                  </button>
                </div>
              </div>
            ) : detail.medicines?.length ? (
              <ul className="ap-med-chips">
                {detail.medicines.map((m) => (
                  <li key={m.id}>
                    <Link to={`/family/${familyId}/medicines/${m.id}`} className={m.active ? "" : "is-stopped"}>
                      💊 {m.display_name}
                      {!m.active && <small> · stopped</small>}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="pp-muted ap-none">No medicines linked yet.</p>
            )}
          </section>

          {actionError && <p role="alert" className="pp-alert">{actionError}</p>}

          {confirmDelete ? (
            <div className="ap-confirm" role="alertdialog" aria-label="Confirm delete">
              <p>Delete this appointment? This can't be undone.</p>
              <div className="ap-modal-actions">
                <button type="button" className="pp-btn pp-btn-ghost" onClick={() => setConfirmDelete(false)} disabled={busy}>
                  Keep it
                </button>
                <button type="button" className="pp-btn ap-danger" onClick={() => void handleDelete(detail)} disabled={busy}>
                  {busy ? "Deleting…" : "Delete"}
                </button>
              </div>
            </div>
          ) : (
            <div className="ap-modal-actions ap-wrap">
              <button type="button" className="ap-link ap-link-danger" onClick={() => setConfirmDelete(true)} disabled={busy}>
                Delete
              </button>
              <span className="ap-spacer" />
              {isOpen(detail) && (
                <button type="button" className="pp-btn pp-btn-ghost" onClick={() => void setStatus(detail, "cancelled")} disabled={busy}>
                  Cancel appointment
                </button>
              )}
              {detail.status === "cancelled" && (
                <button type="button" className="pp-btn pp-btn-ghost" onClick={() => void setStatus(detail, "scheduled")} disabled={busy}>
                  Restore
                </button>
              )}
              <button type="button" className="pp-btn pp-btn-ghost" onClick={() => openEdit(detail)} disabled={busy}>
                Edit
              </button>
              {isOpen(detail) && (
                <button type="button" className="pp-btn" onClick={() => void setStatus(detail, "completed")} disabled={busy}>
                  Mark completed
                </button>
              )}
            </div>
          )}
        </Modal>
      )}

      {/* ---------- Add / edit form ---------- */}
      {form && (
        <Modal title={form.id ? "Edit appointment" : "Add appointment"} onClose={() => setForm(null)}>
          <form onSubmit={handleSave} className="ap-form" noValidate>
            {!form.id && (
              <div className="ap-voice">
                <label htmlFor="ap-voice-box" className="ap-voice-label">
                  <span aria-hidden="true">🎙️</span> Say it in one go
                  <small>Who it's for, the reason, doctor, place, day and time. Speak with Wispr Flow or type.</small>
                </label>
                <textarea
                  id="ap-voice-box"
                  ref={voiceRef}
                  rows={3}
                  maxLength={2000}
                  value={spoken}
                  placeholder={`e.g. “${VOICE_EXAMPLE}”`}
                  onChange={(e) => {
                    setSpoken(e.target.value);
                    setReadNote(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                      e.preventDefault();
                      void fillFromSpeech();
                    }
                  }}
                />
                <div className="ap-voice-actions">
                  <button type="button" className="pp-btn" disabled={reading} onClick={() => void fillFromSpeech()}>
                    {reading ? "Reading…" : "✨ Fill the form"}
                  </button>
                  {!spoken && (
                    <button type="button" className="ap-voice-example" onClick={() => setSpoken(VOICE_EXAMPLE)}>
                      Try an example
                    </button>
                  )}
                  <span className="ap-voice-hint">Ctrl + Enter also works</span>
                </div>
                {readNote && (
                  <p className={`ap-voice-note${readNote.bad ? " is-bad" : ""}`} role={readNote.bad ? "alert" : "status"}>
                    {readNote.text}
                  </p>
                )}
                <div className="ap-voice-or" aria-hidden="true">
                  <span>or fill in the details</span>
                </div>
              </div>
            )}
            {!form.id && profiles.length > 1 && (
              <label className={`pp-field${filledClass("parent")}`}>
                For
                <select value={form.profileId} onChange={(e) => setForm({ ...form, profileId: e.target.value })}>
                  {profiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.display_name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="ap-form-row">
              <label className={`pp-field${filledClass("date")}`}>
                Date
                <input
                  type="date"
                  required
                  value={form.scheduled_date}
                  onChange={(e) => setForm({ ...form, scheduled_date: e.target.value })}
                />
              </label>
              <div className={`pp-field${filledClass("time")}`}>
                <span>Time</span>
                <TimeSelect
                  value={form.start_time}
                  ariaLabel="Appointment time"
                  onChange={(v) => setForm({ ...form, start_time: v })}
                />
              </div>
            </div>
            <label className={`pp-field${filledClass("doctor")}`}>
              Doctor or clinic
              <input
                required
                maxLength={255}
                placeholder="e.g. Dr. Rao · City Clinic"
                value={form.provider}
                onChange={(e) => setForm({ ...form, provider: e.target.value })}
              />
            </label>
            <label className={`pp-field${filledClass("place")}`}>
              <span>
                Where <span className="ap-optional">Optional</span>
              </span>
              <input
                maxLength={255}
                placeholder="e.g. Apollo Hospital, Jayanagar"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
              />
            </label>
            <label className={`pp-field${filledClass("reason")}`}>
              Reason
              <input
                required
                maxLength={255}
                placeholder="e.g. Doctor follow-up"
                value={form.reason}
                onChange={(e) => setForm({ ...form, reason: e.target.value })}
              />
            </label>
            <label className={`pp-field${filledClass("notes")}`}>
              Notes before the visit
              <textarea
                rows={3}
                placeholder="e.g. Bring recent lab results"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </label>
            <details className="ap-form-visit" open={Boolean(form.fee || form.doctor_notes)}>
              <summary>After the visit: fee and doctor's notes</summary>
              <div className="ap-form-visit-body">
                <label className="pp-field">
                  <span>
                    Fee (₹) <span className="ap-optional">Optional</span>
                  </span>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    inputMode="decimal"
                    placeholder="e.g. 500"
                    value={form.fee}
                    onChange={(e) => setForm({ ...form, fee: e.target.value })}
                  />
                </label>
                <label className="pp-field">
                  <span>
                    What the doctor said <span className="ap-optional">Optional</span>
                  </span>
                  <textarea
                    rows={3}
                    placeholder="e.g. BP is better. Reduce salt. Review in 3 months."
                    value={form.doctor_notes}
                    onChange={(e) => setForm({ ...form, doctor_notes: e.target.value })}
                  />
                </label>
              </div>
            </details>
            {form.id && all.find((a) => a.id === form.id)?.status === "scheduled" && (
              <p className="pp-hint">Changing the date or time marks the appointment as rescheduled.</p>
            )}

            {actionError && <p role="alert" className="pp-alert">{actionError}</p>}

            <div className="ap-modal-actions">
              <button type="button" className="pp-btn pp-btn-ghost" onClick={() => setForm(null)} disabled={busy}>
                Cancel
              </button>
              <button type="submit" className="pp-btn" disabled={busy}>
                {busy ? "Saving…" : form.id ? "Save changes" : "Add appointment"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </WorkspaceLayout>
  );
}

function ApptRow({ a, onOpen, showDate = false }: { a: AppointmentOut; onOpen: (a: AppointmentOut) => void; showDate?: boolean }) {
  return (
    <li>
      <button type="button" className={`ap-row is-${a.status}`} onClick={() => onOpen(a)}>
        <span className="ap-row-time">
          {showDate && <span className="ap-row-date">{relativeDay(a.scheduled_date)}</span>}
          {formatTime(a.start_time)}
        </span>
        <span className="ap-row-main">
          <strong>{a.reason}</strong>
          <span>
            {a.provider}
            {formatFee(a.fee) && ` · ${formatFee(a.fee)}`}
            {a.medicines?.length ? ` · ${a.medicines.length} ${a.medicines.length === 1 ? "medicine" : "medicines"}` : ""}
          </span>
        </span>
        <span className={`ap-status is-${a.status}`}>{STATUS_LABEL[a.status]}</span>
      </button>
    </li>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="ap-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ap-modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="ap-modal-head">
          <h2>{title}</h2>
          <button type="button" className="ap-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
