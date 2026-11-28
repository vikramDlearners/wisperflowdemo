import { useEffect, useRef, useState, type FormEvent } from "react";
import "../health-notes.css";
import "../care-circle.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import FamilyCallButton from "../components/FamilyCallButton";
import {
  careProfiles,
  circle,
  fetchAuthedBlob,
  type CardOut,
  type CareProfileOut,
  type ContactIn,
  type ContactOut,
  type HelpOut,
  type PostOut,
} from "../api";

// The parent's circle, family side: errands the parent asked for, things to send them, the people they call,
// and the medical card with a full-screen emergency view for the ambulance or ER.

type Tab = "help" | "send" | "people" | "card";
const TABS: [Tab, string][] = [
  ["help", "Help asked"],
  ["send", "Send to parent"],
  ["people", "People to call"],
  ["card", "Medical card"],
];
const HELP_LABEL: Record<HelpOut["kind"], string> = {
  groceries: "Groceries",
  bill: "Pay a bill",
  cab: "Cab to the clinic",
  nurse: "A nurse",
  physio: "A physiotherapist",
  other: "Something else",
};
const ROLES = ["doctor", "pharmacy", "hospital", "neighbour", "driver", "watchman", "nurse", "physio", "friend", "other"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const tel = (n: string) => `tel:${n.replace(/[^\d+]/g, "")}`;
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

function HelpTab({ familyId, rows, onChange }: { familyId: string; rows: HelpOut[]; onChange: () => void }) {
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  async function decide(h: HelpOut, status: HelpOut["status"]) {
    setError(null);
    const raw = amounts[h.id];
    try {
      await circle.decide(familyId, h.id, status, raw ? Number(raw) : h.amount);
      onChange();
    } catch {
      setError("Could not save. Try again.");
    }
  }
  if (rows.length === 0) return <p className="pp-muted">Nothing asked yet. The parent asks from their chat screen.</p>;
  return (
    <ul className="cc-list">
      {rows.map((h) => (
        <li key={h.id} className="pp-card cc-row">
          <div>
            <strong>{HELP_LABEL[h.kind]}</strong> <span className={`cc-status cc-${h.status}`}>{h.status}</span>
            {h.note && <p>{h.note}</p>}
            <p className="pp-muted">
              Asked {when(h.created_at)}
              {h.amount !== null && ` · ₹${h.amount.toLocaleString("en-IN")}`}
            </p>
          </div>
          <div className="cc-actions">
            {h.status === "asked" && (
              <>
                <label className="hn-field cc-amount">
                  <span>Amount (₹)</span>
                  <input
                    type="number"
                    min="0"
                    inputMode="decimal"
                    value={amounts[h.id] ?? ""}
                    onChange={(e) => setAmounts({ ...amounts, [h.id]: e.target.value })}
                  />
                </label>
                <button type="button" className="pp-btn" onClick={() => void decide(h, "approved")}>
                  Approve
                </button>
                <button type="button" className="pp-btn pp-btn-ghost" onClick={() => void decide(h, "declined")}>
                  Decline
                </button>
              </>
            )}
            {h.status === "approved" && (
              <button type="button" className="pp-btn" onClick={() => void decide(h, "done")}>
                Mark done
              </button>
            )}
          </div>
        </li>
      ))}
      {error && <p role="alert" className="pp-alert">{error}</p>}
    </ul>
  );
}

function Media({ post }: { post: PostOut }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!post.media_url) return;
    let url: string | null = null;
    void fetchAuthedBlob(post.media_url).then((u) => {
      url = u;
      setSrc(u);
    });
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [post.media_url]);
  if (!src) return null;
  return post.kind === "photo" ? <img src={src} alt="" className="cc-photo" /> : <audio controls src={src} />;
}

function SendTab({ familyId, profileId }: { familyId: string; profileId: string }) {
  const [posts, setPosts] = useState<PostOut[]>([]);
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [voice, setVoice] = useState<Blob | null>(null);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);

  useEffect(() => {
    circle.posts(familyId, profileId).then(setPosts).catch(() => setError("Could not load what was sent."));
  }, [familyId, profileId]);

  async function record() {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const parts: Blob[] = [];
      rec.ondataavailable = (e) => parts.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        setVoice(new Blob(parts, { type: rec.mimeType || "audio/webm" }));
        setRecording(false);
      };
      recorder.current = rec;
      rec.start();
      setRecording(true);
    } catch {
      setError("The microphone is not available.");
    }
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const kind: PostOut["kind"] = photo ? "photo" : voice ? "voice" : "text";
    if (kind === "text" && !text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const made = await circle.addPost(familyId, profileId, kind, text.trim(), photo ?? voice);
      setPosts((rows) => [made, ...rows]);
      setText("");
      setPhoto(null);
      setVoice(null);
    } catch {
      setError("Could not send. Photos and voice notes must be under 5 MB.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form className="pp-card hn-form" onSubmit={(e) => void send(e)}>
        <label className="hn-field">
          <span>A line for them</span>
          <textarea rows={2} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <div className="cc-actions">
          <label className="pp-btn pp-btn-ghost">
            📷 {photo ? photo.name : "Add a photo"}
            <input
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                setPhoto(e.target.files?.[0] ?? null);
                setVoice(null);
              }}
            />
          </label>
          <button type="button" className="pp-btn pp-btn-ghost" onClick={() => void record()} disabled={!!photo}>
            🎙 {recording ? "Stop recording" : voice ? "Record again" : "Record a voice note"}
          </button>
          <button type="submit" className="pp-btn" disabled={busy || recording}>
            Send
          </button>
        </div>
        {voice && <audio controls src={URL.createObjectURL(voice)} />}
        {error && <p role="alert" className="pp-alert">{error}</p>}
      </form>
      <ul className="cc-list">
        {posts.map((p) => (
          <li key={p.id} className="pp-card">
            <p>
              <strong>{p.author ?? "Family"}</strong> {p.text}
            </p>
            <Media post={p} />
            <p className="pp-muted">
              {when(p.created_at)} · {p.seen_at ? `seen ${when(p.seen_at)}` : "not seen yet"}
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}

const EMPTY_CONTACT: ContactIn = { name: "", role: "doctor", phone: "", address: "", birthday_month: null, birthday_day: null };

function PeopleTab({ familyId, profileId }: { familyId: string; profileId: string }) {
  const [rows, setRows] = useState<ContactOut[]>([]);
  const [draft, setDraft] = useState<(ContactIn & { id?: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    circle.contacts(familyId, profileId).then(setRows).catch(() => setError("Could not load the call list."));
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [familyId, profileId]);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    const { id, ...body } = draft;
    const clean: ContactIn = {
      ...body,
      phone: body.phone || null,
      address: body.address || null,
      birthday_month: body.birthday_month || null,
      birthday_day: body.birthday_day || null,
    };
    setError(null);
    try {
      if (id) await circle.updateContact(familyId, id, clean);
      else await circle.addContact(familyId, profileId, clean);
      setDraft(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    }
  }

  async function remove(c: ContactOut) {
    if (!window.confirm(`Remove ${c.name} from the call list?`)) return;
    try {
      await circle.removeContact(familyId, c.id);
      await load();
    } catch {
      setError("Could not remove.");
    }
  }

  return (
    <>
      <p className="pp-muted">
        Everyone here shows as a big call button on the parent's screen, after the family. Add a birthday and the
        parent is reminded the day before and on the day.
      </p>
      <button type="button" className="pp-btn" onClick={() => setDraft({ ...EMPTY_CONTACT })}>
        + Add someone
      </button>
      {draft && (
        <form className="pp-card hn-form hn-grid" onSubmit={(e) => void save(e)}>
          <label className="hn-field">
            <span>Name</span>
            <input required maxLength={120} value={draft.name ?? ""} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </label>
          <label className="hn-field">
            <span>Who they are</span>
            <select value={draft.role ?? "other"} onChange={(e) => setDraft({ ...draft, role: e.target.value })}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <label className="hn-field">
            <span>Phone</span>
            <input type="tel" maxLength={30} value={draft.phone ?? ""} onChange={(e) => setDraft({ ...draft, phone: e.target.value })} />
          </label>
          <label className="hn-field">
            <span>Address</span>
            <input maxLength={240} value={draft.address ?? ""} onChange={(e) => setDraft({ ...draft, address: e.target.value })} />
          </label>
          <label className="hn-field">
            <span>Birthday month</span>
            <select
              value={draft.birthday_month ?? ""}
              onChange={(e) => setDraft({ ...draft, birthday_month: e.target.value ? Number(e.target.value) : null })}
            >
              <option value="">None</option>
              {MONTHS.map((m, i) => (
                <option key={m} value={i + 1}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <label className="hn-field">
            <span>Birthday day</span>
            <input
              type="number"
              min="1"
              max="31"
              value={draft.birthday_day ?? ""}
              onChange={(e) => setDraft({ ...draft, birthday_day: e.target.value ? Number(e.target.value) : null })}
            />
          </label>
          <div className="cc-actions">
            <button type="submit" className="pp-btn">
              Save
            </button>
            <button type="button" className="pp-btn pp-btn-ghost" onClick={() => setDraft(null)}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="pp-alert">{error}</p>}
      <ul className="cc-list">
        {rows.map((c) => (
          <li key={c.id} className="pp-card cc-row">
            <div>
              <strong>{c.name}</strong> <span className="pp-muted">{c.role}</span>
              {c.phone && (
                <p>
                  <a href={tel(c.phone)}>📞 {c.phone}</a>
                </p>
              )}
              {c.birthday_month && c.birthday_day && (
                <p className="pp-muted">
                  🎂 {c.birthday_day} {MONTHS[c.birthday_month - 1]}
                </p>
              )}
            </div>
            <div className="cc-actions">
              <button type="button" className="pp-btn pp-btn-ghost" onClick={() => setDraft({ ...c })}>
                Edit
              </button>
              <button type="button" className="pp-btn pp-btn-ghost" onClick={() => void remove(c)}>
                Remove
              </button>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

// Big type, one screen, nothing to tap through: what an ambulance crew or ER desk asks for.
function EmergencyScreen({ card, onClose }: { card: CardOut; onClose: () => void }) {
  const hospitalSearch = `https://www.google.com/maps/search/${encodeURIComponent(card.hospital ?? "hospital")}+near+me`;
  const line = (label: string, value: string | null | undefined, phone?: string | null) => (
    <div className="cc-em-row">
      <dt>{label}</dt>
      <dd>
        {value || "Not recorded"}
        {phone && (
          <>
            {" "}
            <a href={tel(phone)}>📞 {phone}</a>
          </>
        )}
      </dd>
    </div>
  );
  return (
    <div className="cc-emergency" role="dialog" aria-modal="true" aria-labelledby="cc-em-title">
      <h1 id="cc-em-title">🚑 {card.name}</h1>
      <dl>
        {line("Blood group", card.blood_group)}
        {line("Allergies", card.allergies)}
        {line("Medicines", card.medicines.join(", "))}
        {line("Doctor", card.doctor ?? card.doctor_phone, card.doctor_phone)}
        {line("Emergency contact", card.emergency_contact?.name, card.emergency_contact?.phone)}
        {line(
          "Insurance",
          card.insurance && [card.insurance.insurer, card.insurance.policy_number].filter(Boolean).join(" · "),
          card.insurance?.helpline,
        )}
        <div className="cc-em-row">
          <dt>Hospital</dt>
          <dd>
            {card.hospital || "No preferred hospital"}{" "}
            <a href={hospitalSearch} target="_blank" rel="noreferrer">
              Nearest on the map
            </a>
          </dd>
        </div>
        {card.notes && line("Notes", card.notes)}
      </dl>
      <div className="cc-actions cc-no-print">
        <a className="pp-btn" href="tel:108">
          📞 Call 108
        </a>
        <button type="button" className="pp-btn pp-btn-ghost" onClick={() => window.print()}>
          Print
        </button>
        <button type="button" className="pp-btn pp-btn-ghost" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}

function CardTab({ familyId, profileId }: { familyId: string; profileId: string }) {
  const [card, setCard] = useState<CardOut | null>(null);
  const [form, setForm] = useState({ blood_group: "", emergency_name: "", emergency_phone: "", notes: "" });
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    circle
      .card(familyId, profileId)
      .then((c) => {
        setCard(c);
        setForm({
          blood_group: c.blood_group ?? "",
          emergency_name: c.emergency_name ?? "",
          emergency_phone: c.emergency_phone ?? "",
          notes: c.notes ?? "",
        });
      })
      .catch(() => setNote("Could not load the card."));
  }, [familyId, profileId]);

  async function save(e: FormEvent) {
    e.preventDefault();
    setNote(null);
    try {
      const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null]));
      setCard(await circle.saveCard(familyId, profileId, body));
      setNote("Saved.");
    } catch {
      setNote("Could not save.");
    }
  }

  if (!card) return note ? <p role="alert">{note}</p> : null;
  return (
    <>
      <p className="pp-muted">
        Allergies, the doctor and the hospital come from the parent's profile, and medicines from the medicine list.
        The parent sees this card on their chat screen.
      </p>
      <button type="button" className="pp-btn cc-em-btn" onClick={() => setOpen(true)}>
        🚑 Open emergency screen
      </button>
      <form className="pp-card hn-form hn-grid" onSubmit={(e) => void save(e)}>
        <label className="hn-field">
          <span>Blood group</span>
          <input maxLength={8} value={form.blood_group} onChange={(e) => setForm({ ...form, blood_group: e.target.value })} />
        </label>
        <label className="hn-field">
          <span>Emergency contact name</span>
          <input maxLength={120} value={form.emergency_name} onChange={(e) => setForm({ ...form, emergency_name: e.target.value })} />
        </label>
        <label className="hn-field">
          <span>Emergency contact phone</span>
          <input type="tel" maxLength={30} value={form.emergency_phone} onChange={(e) => setForm({ ...form, emergency_phone: e.target.value })} />
        </label>
        <label className="hn-field">
          <span>Notes for the ER</span>
          <textarea rows={2} maxLength={2000} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </label>
        <div className="cc-actions">
          <button type="submit" className="pp-btn">
            Save card
          </button>
          {note && <span role="status">{note}</span>}
        </div>
      </form>
      {open && <EmergencyScreen card={card} onClose={() => setOpen(false)} />}
    </>
  );
}

export default function CareCircle({ familyId }: { familyId: string }) {
  const [profiles, setProfiles] = useState<CareProfileOut[]>([]);
  const [profileId, setProfileId] = useState("");
  const [tab, setTab] = useState<Tab>("help");
  const [help, setHelp] = useState<HelpOut[]>([]);

  const loadHelp = () => circle.help(familyId).then(setHelp).catch(() => undefined);
  useEffect(() => {
    careProfiles
      .list(familyId)
      .then((rows) => {
        setProfiles(rows);
        setProfileId((id) => id || rows[0]?.id || "");
      })
      .catch(() => undefined);
    void loadHelp();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [familyId]);

  const waiting = help.filter((h) => h.status === "asked").length;
  const shownHelp = help.filter((h) => !profileId || h.care_profile_id === profileId);

  return (
    <WorkspaceLayout familyId={familyId} current="circle" title="Care circle">
      <div className="pp-content">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">Care circle · Family workspace</p>
            <h1>The parent's circle</h1>
            <p className="pp-muted">Errands they asked for, things to send them, the people they call, and their medical card.</p>
          </div>
          {profileId && (
            <FamilyCallButton
              familyId={familyId}
              profileId={profileId}
              name={profiles.find((p) => p.id === profileId)?.display_name ?? "the parent"}
            />
          )}
          {profiles.length > 1 && (
            <label className="hn-field">
              <span>Parent</span>
              <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <div className="cc-tabs" role="tablist">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              className={tab === key ? "cc-tab cc-tab-on" : "cc-tab"}
              onClick={() => setTab(key)}
            >
              {label}
              {key === "help" && waiting > 0 && <span className="cc-badge">{waiting}</span>}
            </button>
          ))}
        </div>
        {profileId && tab === "help" && <HelpTab familyId={familyId} rows={shownHelp} onChange={() => void loadHelp()} />}
        {profileId && tab === "send" && <SendTab familyId={familyId} profileId={profileId} />}
        {profileId && tab === "people" && <PeopleTab familyId={familyId} profileId={profileId} />}
        {profileId && tab === "card" && <CardTab familyId={familyId} profileId={profileId} />}
      </div>
    </WorkspaceLayout>
  );
}
