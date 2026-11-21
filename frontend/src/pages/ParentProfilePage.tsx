import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import "../parent-profile.css";
import LogoutButton from "../components/LogoutButton";
import {
  ApiError,
  auth,
  families,
  getProfile,
  saveProfileSection,
  type ParentProfileOut,
  type UserOut,
} from "../api";

// Parent profile page in the family workspace layout (sidebar + header).
// Reads and saves the signed-in user's parent onboarding profile.

const RELATIONSHIP_OPTIONS = ["Mother", "Father", "Grandmother", "Grandfather", "Other"];
const LANGUAGE_OPTIONS: { value: string; label: string }[] = [
  { value: "English", label: "English" },
  { value: "Tamil", label: "Tamil · தமிழ்" },
  { value: "Hindi", label: "Hindi · हिन्दी" },
  { value: "Telugu", label: "Telugu · తెలుగు" },
  { value: "Malayalam", label: "Malayalam · മലയാളം" },
  { value: "Kannada", label: "Kannada · ಕನ್ನಡ" },
];
const VOICE_SPEEDS = ["Slow and clear", "Normal", "Fast"];
const ACCESSIBILITY = ["Large text", "Spoken prompts", "High contrast"];

const ROLE_LABELS: Record<string, string> = {
  parent: "Parent",
  caretaker: "Caretaker",
  hospital: "Hospital staff",
  child_of_parent: "Child of a parent",
  others: "Member",
};

interface FormState {
  parent_full_name: string;
  preferred_name: string;
  relationship: string;
  parent_mobile: string;
  preferred_language: string;
  caregiver_name: string;
}

function toForm(p: ParentProfileOut): FormState {
  return {
    parent_full_name: p.parent_full_name ?? "",
    preferred_name: p.preferred_name ?? "",
    relationship: p.relationship ?? "",
    parent_mobile: p.parent_mobile ?? "",
    preferred_language: p.preferred_language ?? "",
    caregiver_name: p.caregiver_name ?? "",
  };
}

const orNull = (v: string) => (v.trim() ? v.trim() : null);

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Something went wrong. Please try again.";
}

export default function ParentProfilePage() {
  const [profile, setProfile] = useState<ParentProfileOut | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [user, setUser] = useState<UserOut | null>(null);
  const [familyId, setFamilyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Preview-only settings: there are no backend fields for these yet.
  const [voiceSpeed, setVoiceSpeed] = useState(VOICE_SPEEDS[0]);
  const [access, setAccess] = useState<string[]>(ACCESSIBILITY);

  useEffect(() => {
    let active = true;
    Promise.all([getProfile(), auth.me().catch(() => null), families.list().catch(() => [])])
      .then(([p, me, fams]) => {
        if (!active) return;
        setProfile(p);
        setForm(toForm(p));
        setUser(me);
        setFamilyId(fams[0]?.id ?? null);
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

  const set = (key: keyof FormState) => (value: string) => {
    setSaved(false);
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const toggleAccess = (item: string) =>
    setAccess((prev) => (prev.includes(item) ? prev.filter((x) => x !== item) : [...prev, item]));

  function handleCancel() {
    if (profile) setForm(toForm(profile));
    setError(null);
    setSaved(false);
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!form) return;
    if (!form.parent_full_name.trim() || !form.preferred_name.trim() || !form.relationship) {
      setError("Full name, preferred greeting and relationship are required.");
      return;
    }
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await saveProfileSection("parent", {
        parent_full_name: orNull(form.parent_full_name),
        preferred_name: orNull(form.preferred_name),
        relationship: orNull(form.relationship),
        preferred_language: orNull(form.preferred_language),
      });
      await saveProfileSection("communication", {
        parent_mobile: orNull(form.parent_mobile),
      });
      const updated = await saveProfileSection("care", {
        caregiver_name: orNull(form.caregiver_name),
      });
      setProfile(updated);
      setForm(toForm(updated));
      setSaved(true);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  const parentName = profile?.parent_full_name?.trim() || "Your parent";
  const firstName = parentName.split(/\s+/)[0];
  const greeting = form?.preferred_name.trim() || "there";
  const userName = user?.display_name ?? "You";
  const userRole = (user?.role && ROLE_LABELS[user.role]) || "Family member";

  const nav = (path: string) => (familyId ? `/family/${familyId}${path}` : null);
  const workspace: { icon: string; label: string; to: string | null; current?: boolean }[] = [
    { icon: "⌂", label: "Overview", to: nav("") },
    { icon: "♡", label: "Parent profile", to: "/parent-profile", current: true },
    { icon: "▤", label: "Medicines", to: nav("/medicines") },
    { icon: "◉", label: "CareVoice activity", to: nav("/activity") },
    { icon: "☷", label: "Tasks", to: nav("/tasks") },
    { icon: "▦", label: "Appointments", to: nav("/appointments") },
    { icon: "▧", label: "Records", to: nav("/records") },
    { icon: "↗", label: "Family timeline", to: nav("/timeline") },
  ];
  const settings = [
    { icon: "♙", label: "Family members", to: nav("/members") },
    { icon: "⚙", label: "Notification settings", to: nav("/notifications") },
  ];

  const renderNav = (items: { icon: string; label: string; to: string | null; current?: boolean }[]) =>
    items.map((item) =>
      item.to ? (
        <Link
          key={item.label}
          to={item.to}
          className={`pp-nav-item${item.current ? " is-current" : ""}`}
          aria-current={item.current ? "page" : undefined}
        >
          <span className="pp-nav-icon" aria-hidden="true">{item.icon}</span>
          {item.label}
        </Link>
      ) : (
        <span key={item.label} className="pp-nav-item is-disabled" title="Create a family first">
          <span className="pp-nav-icon" aria-hidden="true">{item.icon}</span>
          {item.label}
        </span>
      ),
    );

  return (
    <div className="pp">
      <aside className="pp-sidebar">
        <div className="pp-brand">
          <span className="pp-brand-mark" aria-hidden="true">✳</span>
          <div>
            <div className="pp-brand-name">CareCircle</div>
            <div className="pp-brand-tag">Family care, together</div>
          </div>
        </div>

        <nav aria-label="Workspace">
          <p className="pp-nav-heading">Workspace</p>
          {renderNav(workspace)}
          <p className="pp-nav-heading">Settings</p>
          {renderNav(settings)}
        </nav>

        <div className="pp-family">
          <p className="pp-nav-heading">Your family</p>
          <div className="pp-person">
            <span className="pp-avatar pp-avatar-green">{initials(parentName)}</span>
            <div>
              <div className="pp-person-name">{parentName}</div>
              <div className="pp-person-sub">Care profile</div>
            </div>
          </div>
          <div className="pp-person">
            <span className="pp-avatar pp-avatar-warm">{initials(userName)}</span>
            <div>
              <div className="pp-person-name">{userName}</div>
              <div className="pp-person-sub">{userRole}</div>
            </div>
          </div>
          <LogoutButton />
        </div>
      </aside>

      <div className="pp-main">
        <header className="pp-topbar">
          <nav className="pp-breadcrumb" aria-label="Breadcrumb">
            <span>CareCircle</span>
            <span aria-hidden="true">/</span>
            <strong>Parent profile</strong>
          </nav>
          <label className="pp-search">
            <span aria-hidden="true">⌕</span>
            <input type="search" placeholder="Search records, tasks..." aria-label="Search records and tasks" />
          </label>
          <button type="button" className="pp-bell" aria-label="Notifications">
            🔔
          </button>
          <div className="pp-user">
            <span className="pp-avatar pp-avatar-warm">{initials(userName)}</span>
            <div>
              <div className="pp-person-name">{userName}</div>
              <div className="pp-person-sub">{userRole}</div>
            </div>
          </div>
        </header>

        <form className="pp-content" onSubmit={handleSave}>
          <div className="pp-page-head">
            <div>
              <p className="pp-eyebrow">Care circle · Family workspace</p>
              <h1>Parent profile</h1>
              <p className="pp-muted">
                Manage {firstName}'s care profile, preferred voice experience and assigned family contacts.
              </p>
            </div>
            <div className="pp-head-actions">
              {familyId ? (
                <Link to={`/family/${familyId}/members`} className="pp-btn pp-btn-ghost pp-btn-link">
                  + Add users
                </Link>
              ) : (
                <span
                  className="pp-btn pp-btn-ghost pp-btn-link is-disabled"
                  aria-disabled="true"
                  title="Create a family first to add users"
                >
                  + Add users
                </span>
              )}
              <button type="button" className="pp-btn pp-btn-ghost" onClick={handleCancel} disabled={saving || !form}>
                Cancel
              </button>
              <button type="submit" className="pp-btn" disabled={saving || !form}>
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>

          {loading && <p role="status" className="pp-muted">Loading profile…</p>}
          {error && <p role="alert" className="pp-alert">{error}</p>}
          {saved && <p role="status" className="pp-saved">Changes saved.</p>}

          {form && (
            <div className="pp-grid">
              <section className="pp-card">
                <div className="pp-card-head">
                  <h2>Personal information</h2>
                  <span className="pp-badge">Care recipient</span>
                </div>

                <div className="pp-fields">
                  <label className="pp-field">
                    Full name
                    <input required maxLength={120} value={form.parent_full_name} onChange={(e) => set("parent_full_name")(e.target.value)} />
                  </label>
                  <label className="pp-field">
                    Relationship
                    <select required value={form.relationship} onChange={(e) => set("relationship")(e.target.value)}>
                      <option value="">Choose…</option>
                      {RELATIONSHIP_OPTIONS.map((opt) => (
                        <option key={opt} value={opt.toLowerCase()}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="pp-field">
                    Preferred greeting
                    <input required maxLength={60} value={form.preferred_name} onChange={(e) => set("preferred_name")(e.target.value)} />
                  </label>
                  <label className="pp-field">
                    Time zone
                    <input value="Asia / Kolkata (IST)" disabled />
                  </label>
                  <label className="pp-field">
                    Mobile number
                    <input type="tel" inputMode="tel" maxLength={20} value={form.parent_mobile} onChange={(e) => set("parent_mobile")(e.target.value)} />
                  </label>
                  <label className="pp-field">
                    Parent app account
                    <input value="Not linked yet" disabled />
                  </label>
                  <label className="pp-field">
                    Preferred language
                    <select value={form.preferred_language} onChange={(e) => set("preferred_language")(e.target.value)}>
                      <option value="">Choose…</option>
                      {LANGUAGE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="pp-field">
                    Voice speed
                    <select value={voiceSpeed} onChange={(e) => setVoiceSpeed(e.target.value)}>
                      {VOICE_SPEEDS.map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                  </label>
                </div>

                <fieldset className="pp-access">
                  <legend>Accessibility preferences</legend>
                  {ACCESSIBILITY.map((item) => (
                    <button
                      key={item}
                      type="button"
                      className={`pp-chip${access.includes(item) ? " is-on" : ""}`}
                      aria-pressed={access.includes(item)}
                      onClick={() => toggleAccess(item)}
                    >
                      {access.includes(item) ? "✓ " : ""}
                      {item}
                    </button>
                  ))}
                </fieldset>
                <p className="pp-hint">Voice speed and accessibility preferences are a preview and are not saved yet.</p>

                <hr className="pp-divider" />

                <h2 className="pp-subhead">Assigned family contacts</h2>
                <div className="pp-fields">
                  <label className="pp-field">
                    Primary contact
                    <input maxLength={120} placeholder="Caregiver name" value={form.caregiver_name} onChange={(e) => set("caregiver_name")(e.target.value)} />
                  </label>
                  <label className="pp-field">
                    Secondary contact
                    <input value="Not assigned" disabled />
                  </label>
                </div>
              </section>

              <div className="pp-side">
                <section className="pp-card">
                  <div className="pp-card-head">
                    <h2>Parent experience preview</h2>
                    <span className="pp-badge">Enabled</span>
                  </div>
                  <div className="pp-preview">
                    <span className="pp-preview-icon" aria-hidden="true">◉</span>
                    <p className="pp-preview-hello">Hello {greeting}</p>
                    <p className="pp-muted">Your care reminders are ready.</p>
                    <span className="pp-preview-btn" aria-hidden="true">🎙 Talk to CareCircle</span>
                  </div>
                </section>

                <section className="pp-card">
                  <h2>Linked device</h2>
                  <div className="pp-device">
                    <span className="pp-device-icon" aria-hidden="true">▣</span>
                    <div>
                      <div className="pp-person-name">No device linked yet</div>
                      <div className="pp-person-sub">Invite {firstName} from Family members to link a phone</div>
                    </div>
                  </div>
                  <div className="pp-access-row">
                    <span className="pp-muted">Parent participant access</span>
                    <span className="pp-badge pp-badge-muted">Not active</span>
                  </div>
                </section>
              </div>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
