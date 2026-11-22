import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import "../parent-profile.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import {
  ApiError,
  deleteFamilyParentProfile,
  families,
  members,
  getFamilyDashboard,
  getFamilyParentProfile,
  getProfile,
  saveFamilyParentProfileSection,
  saveProfileSection,
  type DashboardParentOut,
  type MemberOut,
  type ParentProfileOut,
} from "../api";
import { RELATIONSHIP_OPTIONS } from "../lib/constants";


// Parent profile page in the shared family workspace layout (sidebar + header).
// Reads and saves the signed-in user's parent onboarding profile.


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

interface FormState {
  parent_full_name: string;
  preferred_name: string;
  relationship: string;
  parent_mobile: string;
  preferred_language: string;
  caregiver_name: string;
  deficiencies: string;
  notes: string;
}

function toForm(p: ParentProfileOut): FormState {
  return {
    parent_full_name: p.parent_full_name ?? "",
    preferred_name: p.preferred_name ?? "",
    relationship: p.relationship ?? "",
    parent_mobile: p.parent_mobile ?? "",
    preferred_language: p.preferred_language ?? "",
    caregiver_name: p.caregiver_name ?? "",
    deficiencies: p.deficiencies ?? "",
    notes: p.notes ?? "",
  };
}

const orNull = (v: string) => (v.trim() ? v.trim() : null);

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Something went wrong. Please try again.";
}

export default function ParentProfilePage() {
  const [profile, setProfile] = useState<ParentProfileOut | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [familyId, setFamilyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  // The page opens read-only; "Edit profile" switches the fields to inputs.
  const [editing, setEditing] = useState(false);
  const firstInput = useRef<HTMLInputElement>(null);

  // "Give link to parent": POST /api/families/{familyId}/members/{membershipId}/invite
  const [parentMember, setParentMember] = useState<MemberOut | null>(null);
  const [membersLoaded, setMembersLoaded] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [inviteMsg, setInviteMsg] = useState<string | null>(null);
  const [inviteErr, setInviteErr] = useState<string | null>(null);
  const [showLinkDialog, setShowLinkDialog] = useState(false);
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [copyErr, setCopyErr] = useState<string | null>(null);

  // Preview-only settings: there are no backend fields for these yet.
  const [voiceSpeed, setVoiceSpeed] = useState(VOICE_SPEEDS[0]);
  const [access, setAccess] = useState<string[]>(ACCESSIBILITY);

  // Profile tabs: null = the signed-in user's own profile; otherwise a parent's care profile id.
  const [selectedCareProfileId, setSelectedCareProfileId] = useState<string | null>(null);
  const [parentTabs, setParentTabs] = useState<
    Pick<DashboardParentOut, "care_profile_id" | "display_name" | "relationship">[]
  >([]);
  const [ownLabel, setOwnLabel] = useState("My profile");
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([getProfile(), families.list().catch(() => [])])
      .then(([p, fams]) => {
        if (!active) return;
        setProfile(p);
        setForm(toForm(p));
        setFamilyId(fams[0]?.id ?? null);
        setOwnLabel(p.parent_full_name?.trim() || "My profile");
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

  // Parents in this family, one tab each.
  useEffect(() => {
    if (!familyId) return;
    let active = true;
    getFamilyDashboard(familyId)
      .then((d) => {
        if (active)
          setParentTabs(
            d.parents.map((p) => ({
              care_profile_id: p.care_profile_id,
              display_name: p.display_name,
              relationship: p.relationship,
            })),
          );
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [familyId]);

  async function handleSelectTab(careProfileId: string | null) {
    if (careProfileId === selectedCareProfileId) return;
    setSelectedCareProfileId(careProfileId);
    setEditing(false);
    setError(null);
    setSaved(false);
    setNotice(null);
    setLoading(true);
    try {
      const p =
        careProfileId && familyId
          ? await getFamilyParentProfile(familyId, careProfileId)
          : await getProfile();
      setProfile(p);
      setForm(toForm(p));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }

  // Deletes the selected parent's profile after confirmation, then returns to the own profile.
  async function handleDeleteProfile() {
    if (!familyId || !selectedCareProfileId) return;
    if (!window.confirm("Delete this parent's profile? This cannot be undone.")) return;
    const deletedId = selectedCareProfileId;
    setDeleting(true);
    setError(null);
    setSaved(false);
    setNotice(null);
    try {
      await deleteFamilyParentProfile(familyId, deletedId);
      setParentTabs((prev) => prev.filter((t) => t.care_profile_id !== deletedId));
      await handleSelectTab(null);
      setNotice("Profile deleted.");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setDeleting(false);
    }
  }

  // Find the family member who has the Parent role; the invite is sent to them.
  useEffect(() => {
    if (!familyId) return;
    let active = true;
    members
      .list(familyId)
      .then((list) => {
        if (active) setParentMember(list.find((m) => m.role_name.toLowerCase() === "parent") ?? null);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setMembersLoaded(true);
      });
    return () => {
      active = false;
    };
  }, [familyId]);

  async function handleGiveLink() {
    if (!familyId || !parentMember) return;
    setInviting(true);
    setInviteMsg(null);
    setInviteErr(null);
    setInviteLink(null);
    try {
      // The backend replies { email, invite_link } with the address the sign-in link went to and the link itself.
      const res = (await members.invite(familyId, parentMember.membership_id)) as unknown as {
        email?: string;
        invite_link?: string;
      };
      const mobile = profile?.parent_mobile?.trim();
      const who = profile?.parent_full_name?.trim().split(/\s+/)[0] || "your parent";
      setInviteMsg(
        mobile
          ? `Invite sent to ${who} via mobile (${mobile}).`
          : `Invite sent to ${who} via email (${res.email ?? parentMember.email ?? "their email"}).`,
      );
      setInviteLink(res.invite_link ?? null);
      setShowLinkDialog(true);
    } catch (err) {
      setInviteErr(errorText(err));
    } finally {
      setInviting(false);
    }
  }

  async function handleCopyLink() {
    if (!inviteLink) return;
    try {
      await navigator.clipboard.writeText(inviteLink);
      setCopied(true);
      setCopyErr(null);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopyErr("Could not copy the link. Please copy it manually.");
    }
  }

  const set = (key: keyof FormState) => (value: string) => {
    setSaved(false);
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  const toggleAccess = (item: string) =>
    setAccess((prev) => (prev.includes(item) ? prev.filter((x) => x !== item) : [...prev, item]));

  function handleEdit() {
    setError(null);
    setSaved(false);
    setEditing(true);
  }

  function handleCancel() {
    if (profile) setForm(toForm(profile));
    setError(null);
    setSaved(false);
    setEditing(false);
  }

  useEffect(() => {
    if (editing) firstInput.current?.focus();
  }, [editing]);

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
    // A selected parent's profile is saved through the family route; the own profile keeps the existing calls.
    const save: typeof saveProfileSection =
      selectedCareProfileId && familyId
        ? (section, fields) => saveFamilyParentProfileSection(familyId, selectedCareProfileId, section, fields)
        : saveProfileSection;
    try {
      await save("parent", {
        parent_full_name: orNull(form.parent_full_name),
        preferred_name: orNull(form.preferred_name),
        relationship: orNull(form.relationship),
        preferred_language: orNull(form.preferred_language),
      });
      await save("communication", {
        parent_mobile: orNull(form.parent_mobile),
      });
      await save("medical", {
        deficiencies: orNull(form.deficiencies),
        notes: orNull(form.notes),
      });
      const updated = await save("care", {
        caregiver_name: orNull(form.caregiver_name),
      });
      setProfile(updated);
      setForm(toForm(updated));
      setSaved(true);
      setEditing(false);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  const parentName = profile?.parent_full_name?.trim() || "Your parent";
  const firstName = parentName.split(/\s+/)[0];
  const greeting = form?.preferred_name.trim() || "there";

  // One form row: an input in edit mode, plain text in view mode.
  const row = (label: string, editor: ReactNode, value: string | null | undefined, muted = false) =>
    editing ? (
      <label className="pp-field">
        {label}
        {editor}
      </label>
    ) : (
      <div className="pp-field">
        <span>{label}</span>
        <span className={`pp-value${!value || muted ? " is-empty" : ""}`}>{value || "Not added"}</span>
      </div>
    );
  const relationshipLabel =
    RELATIONSHIP_OPTIONS.find((o) => o.toLowerCase() === form?.relationship) ?? form?.relationship;
  const languageLabel =
    LANGUAGE_OPTIONS.find((o) => o.value === form?.preferred_language)?.label ?? form?.preferred_language;

  return (
    <WorkspaceLayout familyId={familyId} current="parent-profile" title="Parent profile">
        <form
          className={`pp-content${editing ? " is-editing" : ""}`}
          onSubmit={editing ? handleSave : (e) => e.preventDefault()}
        >
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
              {editing ? (
                <>
                  <button
                    type="button"
                    className="pp-btn pp-btn-ghost pp-save-btn"
                    onClick={handleCancel}
                    disabled={saving}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="pp-btn pp-save-btn" disabled={saving}>
                    {saving ? "Saving…" : "Save changes"}
                  </button>
                </>
              ) : (
                <button type="button" className="pp-btn pp-edit-btn" onClick={handleEdit} disabled={!form}>
                  ✎ Edit profile
                </button>
              )}
              {selectedCareProfileId !== null && (
                <button
                  type="button"
                  className="pp-btn pp-delete-btn"
                  onClick={handleDeleteProfile}
                  disabled={deleting || saving}
                >
                  {deleting ? "Deleting…" : "Delete profile"}
                </button>
              )}
            </div>
          </div>

          {loading && <p role="status" className="pp-muted">Loading profile…</p>}
          {error && <p role="alert" className="pp-alert">{error}</p>}
          {saved && <p role="status" className="pp-saved">Changes saved.</p>}
          {notice && <p role="status" className="pp-saved">{notice}</p>}

          {form && (
            <div className="pp-tabs" role="tablist" aria-label="Profiles">
              <button
                type="button"
                role="tab"
                aria-selected={selectedCareProfileId === null}
                className={`pp-tab${selectedCareProfileId === null ? " is-active" : ""}`}
                onClick={() => handleSelectTab(null)}
                disabled={saving}
              >
                {ownLabel}
              </button>
              {parentTabs.map((t) => (
                <button
                  key={t.care_profile_id}
                  type="button"
                  role="tab"
                  aria-selected={selectedCareProfileId === t.care_profile_id}
                  className={`pp-tab${selectedCareProfileId === t.care_profile_id ? " is-active" : ""}`}
                  onClick={() => handleSelectTab(t.care_profile_id)}
                  disabled={saving}
                >
                  {t.display_name}
                  {t.relationship ? ` · ${t.relationship}` : ""}
                </button>
              ))}
            </div>
          )}

          {form && (
            <div className="pp-grid">
              <section className="pp-card">
                <div className="pp-card-head">
                  <h2>Personal information</h2>
                  <span className="pp-badge">Care recipient</span>
                </div>

                <div className="pp-fields">
                  {row(
                    "Full name",
                    <input
                      ref={firstInput}
                      required
                      maxLength={120}
                      value={form.parent_full_name}
                      onChange={(e) => set("parent_full_name")(e.target.value)}
                    />,
                    form.parent_full_name,
                  )}
                  {row(
                    "Relationship",
                    <select required value={form.relationship} onChange={(e) => set("relationship")(e.target.value)}>
                      <option value="">Choose…</option>
                      {RELATIONSHIP_OPTIONS.map((opt) => (
                        <option key={opt} value={opt.toLowerCase()}>
                          {opt}
                        </option>
                      ))}
                    </select>,
                    relationshipLabel,
                  )}
                  {row(
                    "Preferred greeting",
                    <input
                      required
                      maxLength={60}
                      value={form.preferred_name}
                      onChange={(e) => set("preferred_name")(e.target.value)}
                    />,
                    form.preferred_name,
                  )}
                  {row("Time zone", <input value="Asia / Kolkata (IST)" disabled />, "Asia / Kolkata (IST)")}
                  {row(
                    "Mobile number",
                    <input
                      type="tel"
                      inputMode="tel"
                      maxLength={20}
                      value={form.parent_mobile}
                      onChange={(e) => set("parent_mobile")(e.target.value)}
                    />,
                    form.parent_mobile,
                  )}
                  {row("Parent app account", <input value="Not linked yet" disabled />, "Not linked yet", true)}
                  {row(
                    "Preferred language",
                    <select value={form.preferred_language} onChange={(e) => set("preferred_language")(e.target.value)}>
                      <option value="">Choose…</option>
                      {LANGUAGE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>,
                    languageLabel,
                  )}
                  {row(
                    "Voice speed",
                    <select value={voiceSpeed} onChange={(e) => setVoiceSpeed(e.target.value)}>
                      {VOICE_SPEEDS.map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>,
                    voiceSpeed,
                  )}
                </div>

                <fieldset className="pp-access">
                  <legend>Accessibility preferences</legend>
                  {editing ? (
                    ACCESSIBILITY.map((item) => (
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
                    ))
                  ) : access.length === 0 ? (
                    <span className="pp-value is-empty">None selected</span>
                  ) : (
                    access.map((item) => (
                      <span key={item} className="pp-chip is-on is-static">
                        ✓ {item}
                      </span>
                    ))
                  )}
                </fieldset>
                {editing && (
                  <p className="pp-hint">Voice speed and accessibility preferences are a preview and are not saved yet.</p>
                )}

                <hr className="pp-divider" />

                <h2 className="pp-subhead">Assigned family contacts</h2>
                <div className="pp-fields">
                  {row(
                    "Primary contact",
                    <input
                      maxLength={120}
                      placeholder="Caregiver name"
                      value={form.caregiver_name}
                      onChange={(e) => set("caregiver_name")(e.target.value)}
                    />,
                    form.caregiver_name,
                  )}
                  {row("Secondary contact", <input value="Not assigned" disabled />, "Not assigned", true)}
                </div>

                <hr className="pp-divider" />

                <h2 className="pp-subhead">Health deficiencies</h2>
                <div className="pp-fields">
                  {row(
                    "Deficiencies",
                    <textarea
                      maxLength={500}
                      placeholder="e.g. calcium, sugar problems, other deficiencies"
                      value={form.deficiencies}
                      onChange={(e) => set("deficiencies")(e.target.value)}
                    />,
                    form.deficiencies,
                  )}
                  {row(
                    "Notes",
                    <textarea
                      maxLength={500}
                      placeholder="Any other notes about health"
                      value={form.notes}
                      onChange={(e) => set("notes")(e.target.value)}
                    />,
                    form.notes,
                  )}
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
                      <div className="pp-person-sub">
                        Send {firstName} a sign-in link to open CareCircle on their phone
                      </div>
                    </div>
                  </div>
                  <div className="pp-access-row">
                    <span className="pp-muted">Parent participant access</span>
                    <span className={`pp-badge${inviteMsg ? "" : " pp-badge-muted"}`}>
                      {inviteMsg ? "Invite sent" : "Not active"}
                    </span>
                  </div>

                  <div className="pp-invite">
                    <button
                      type="button"
                      className="pp-btn pp-invite-btn"
                      onClick={handleGiveLink}
                      disabled={!parentMember || inviting}
                    >
                      {inviting ? "Sending link…" : inviteMsg ? "Send link again" : "Give link to parent"}
                    </button>
                    {inviteMsg && (
                      <p role="status" className="pp-invite-ok">
                        ✓ {inviteMsg}
                      </p>
                    )}
                    {inviteErr && (
                      <p role="alert" className="pp-invite-err">
                        {inviteErr}
                      </p>
                    )}
                    {showLinkDialog && (
                      <div
                        className="pp-dialog-overlay"
                        onClick={() => {
                          setShowLinkDialog(false);
                          setCopied(false);
                        }}
                      >
                        <div
                          className="pp-dialog"
                          role="dialog"
                          aria-modal="true"
                          aria-labelledby="pp-dialog-title"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <h3 id="pp-dialog-title">Link sent</h3>
                          <p>Link sent to SMS, WhatsApp and Email</p>
                          <button
                            type="button"
                            className="pp-btn"
                            onClick={() => {
                              setShowLinkDialog(false);
                              setCopied(false);
                            }}
                          >
                            OK
                          </button>
                          <button
                            type="button"
                            className="pp-btn"
                            onClick={handleCopyLink}
                            disabled={!inviteLink}
                          >
                            {copied ? "Copied" : "Copy Link"}
                          </button>
                          {copyErr && (
                            <p role="alert" className="pp-invite-err">
                              {copyErr}
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                    {!familyId && !loading && (
                      <p className="pp-invite-hint">Create a family first to send {firstName} a link.</p>
                    )}
                    {familyId && membersLoaded && !parentMember && (
                      <p className="pp-invite-hint">
                        Add {firstName} as a family member with the Parent role first.{" "}
                        <Link to={`/family/${familyId}/members`}>Go to Family members</Link>
                      </p>
                    )}
                  </div>
                </section>
              </div>
            </div>
          )}

          {/* Phones: Cancel / Save sit in a bar pinned to the bottom of the screen. */}
          {form && editing && (
            <div className="pp-bottom-actions">
              {(saved || error) && (
                <p className={`pp-bottom-status${error ? " is-error" : ""}`} aria-hidden="true">
                  {error ?? "✓ Changes saved."}
                </p>
              )}
              <button type="button" className="pp-btn pp-btn-ghost" onClick={handleCancel} disabled={saving}>
                Cancel
              </button>
              <button type="submit" className="pp-btn" disabled={saving}>
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          )}
        </form>
    </WorkspaceLayout>
  );
}
