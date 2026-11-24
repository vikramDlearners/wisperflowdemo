import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, members, roles } from "../api";
import type { MemberOut, RoleOut } from "../api";
import { RELATIONSHIP_OPTIONS } from "../lib/constants";
import { useNavigate } from "react-router-dom";
import "../members-permissions.css";

interface MembersPermissionsProps {
  familyId: string;
}

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

// Permissions grouped by area, with plain-language labels (the code stays the stored value).
const PERMISSION_GROUPS: { title: string; items: { code: string; label: string }[] }[] = [
  {
    title: "Overview & care profile",
    items: [
      { code: "dashboard.view", label: "See the family dashboard" },
      { code: "parent_profile.view", label: "View care profile" },
      { code: "parent_profile.edit", label: "Edit care profile" },
    ],
  },
  {
    title: "Medicines",
    items: [
      { code: "medicines.view", label: "View medicines" },
      { code: "medicines.edit", label: "Add and edit medicines" },
      { code: "medicine_quantity.update", label: "Update tablets left" },
    ],
  },
  {
    title: "Records",
    items: [
      { code: "reports.view", label: "View records" },
      { code: "reports.upload", label: "Upload records" },
    ],
  },
  {
    title: "Tasks",
    items: [
      { code: "tasks.view", label: "View tasks" },
      { code: "tasks.create", label: "Create tasks" },
      { code: "tasks.assign", label: "Assign tasks" },
      { code: "tasks.update_own", label: "Update own tasks" },
    ],
  },
  {
    title: "Appointments",
    items: [
      { code: "appointments.view", label: "View appointments" },
      { code: "appointments.create", label: "Add appointments" },
      { code: "appointments.update", label: "Change appointments" },
      { code: "appointments.delete", label: "Delete appointments" },
    ],
  },
  {
    title: "Family & settings",
    items: [
      { code: "activity.view", label: "See activity" },
      { code: "members.manage", label: "Manage members" },
      { code: "roles.manage", label: "Manage roles" },
      { code: "notifications.configure", label: "Notification settings" },
    ],
  },
  {
    title: "Parent chat",
    items: [{ code: "voice.use_parent_mode", label: "Use the parent chat" }],
  },
];

const PERMISSION_OPTIONS: string[] = PERMISSION_GROUPS.flatMap((g) => g.items.map((i) => i.code));

const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every((p) => b.includes(p));

interface PermissionPickerProps {
  idPrefix: string;
  selected: string[];
  onChange: (next: string[]) => void;
}

// The grouped checkbox grid, used by every role card and by "Create role".
function PermissionPicker({ idPrefix, selected, onChange }: PermissionPickerProps) {
  const toggle = (code: string, on: boolean) =>
    onChange(on ? [...selected, code] : selected.filter((v) => v !== code));
  return (
    <div className="mp-groups">
      {PERMISSION_GROUPS.map((group) => {
        const codes = group.items.map((i) => i.code);
        const allOn = codes.every((c) => selected.includes(c));
        return (
          <fieldset key={group.title} className="mp-group">
            <legend className="mp-group-title">
              {group.title}
              <button
                type="button"
                className="mp-link"
                onClick={() =>
                  onChange(
                    allOn
                      ? selected.filter((v) => !codes.includes(v))
                      : [...selected, ...codes.filter((c) => !selected.includes(c))],
                  )
                }
              >
                {allOn ? "Clear" : "All"}
              </button>
            </legend>
            {group.items.map((item) => (
              <label key={item.code} className="mp-perm" htmlFor={`${idPrefix}-${item.code}`}>
                <input
                  type="checkbox"
                  id={`${idPrefix}-${item.code}`}
                  checked={selected.includes(item.code)}
                  onChange={(e) => toggle(item.code, e.target.checked)}
                />
                <span>{item.label}</span>
              </label>
            ))}
          </fieldset>
        );
      })}
    </div>
  );
}

export default function MembersPermissions({ familyId }: MembersPermissionsProps) {
  const navigate = useNavigate();
  const [memberList, setMemberList] = useState<MemberOut[]>([]);
  const [roleList, setRoleList] = useState<RoleOut[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [memberRoleId, setMemberRoleId] = useState("");
  const [relationship, setRelationship] = useState("");
  const [addingMember, setAddingMember] = useState(false);
  const [invitingId, setInvitingId] = useState<string | null>(null);
  const [inviteNotice, setInviteNotice] = useState<string | null>(null);

  const [roleName, setRoleName] = useState("");
  const [rolePermissions, setRolePermissions] = useState<string[]>([]);
  const [creatingRole, setCreatingRole] = useState(false);

  const [permDrafts, setPermDrafts] = useState<Record<string, string[]>>({});
  const [savingRoleId, setSavingRoleId] = useState<string | null>(null);
  const [savedRoleId, setSavedRoleId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([members.list(familyId), roles.list(familyId)])
      .then(([memberData, roleData]) => {
        if (cancelled) return;
        setMemberList(memberData);
        setRoleList(roleData);
        setPermDrafts(Object.fromEntries(roleData.map((r) => [r.id, r.permissions])));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError && err.status === 403
              ? "You don't have access to manage members in this family. Ask the family manager to change your role."
              : `Could not load members and roles: ${messageOf(err)}`,
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [familyId]);

  const handleAddMember = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setActionError(null);
    setAddingMember(true);
    try {
      const created = await members.create(familyId, {
        email: email.trim(),
        display_name: displayName.trim() || null,
        role_id: memberRoleId,
        relationship: relationship ? relationship.toLowerCase() : null,
      });
      setMemberList((prev) => [...prev, created]);
      setEmail("");
      setDisplayName("");
      setMemberRoleId("");
      setRelationship("");
    } catch (err: unknown) {
      setActionError(messageOf(err));
    } finally {
      setAddingMember(false);
    }
  };

  const handleMemberRoleChange = async (membershipId: string, roleId: string) => {
    setActionError(null);
    try {
      const updated = await members.update(familyId, membershipId, { role_id: roleId });
      setMemberList((prev) => prev.map((m) => (m.membership_id === updated.membership_id ? updated : m)));
    } catch (err: unknown) {
      setActionError(messageOf(err));
    }
  };

  const handleSendInvite = async (membershipId: string) => {
    setActionError(null);
    setInviteNotice(null);
    setInvitingId(membershipId);
    try {
      const res = await members.invite(familyId, membershipId);
      setInviteNotice(res.detail);
    } catch (err: unknown) {
      setActionError(messageOf(err));
    } finally {
      setInvitingId(null);
    }
  };

  const handleCreateRole = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setActionError(null);
    setCreatingRole(true);
    try {
      const created = await roles.create(familyId, {
        name: roleName.trim(),
        permissions: rolePermissions,
      });
      setRoleList((prev) => [...prev, created]);
      setPermDrafts((prev) => ({ ...prev, [created.id]: created.permissions }));
      setRoleName("");
      setRolePermissions([]);
    } catch (err: unknown) {
      setActionError(messageOf(err));
    } finally {
      setCreatingRole(false);
    }
  };

  const handleSavePermissions = async (role: RoleOut) => {
    setActionError(null);
    setSavingRoleId(role.id);
    try {
      const updated = await roles.updatePermissions(familyId, role.id, {
        permissions: permDrafts[role.id] ?? [],
      });
      setRoleList((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      setPermDrafts((prev) => ({ ...prev, [updated.id]: updated.permissions }));
      setSavedRoleId(updated.id);
    } catch (err: unknown) {
      setActionError(messageOf(err));
    } finally {
      setSavingRoleId(null);
    }
  };

  if (loading) return <p role="status">Loading members and roles…</p>;
  if (error) return <p role="alert">{error}</p>;

  return (
    <main className="parent-layout wizard-page mp-page" aria-labelledby="members-permissions-heading">
      <h1 id="members-permissions-heading">Family members &amp; permissions</h1>

      {actionError && <p role="alert" className="wizard-error">{actionError}</p>}
      {inviteNotice && <p role="status">{inviteNotice}</p>}



      <form className="wizard-form" onSubmit={handleAddMember} aria-label="Add member">
        <label className="wizard-field">
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="wizard-field">
          Display name
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={255} />
        </label>
        <label className="wizard-field">
          Role
          <select value={memberRoleId} onChange={(e) => setMemberRoleId(e.target.value)} required>
            <option value="">Select a role</option>
            {roleList.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label className="wizard-field">
          Relationship (optional)
          <select value={relationship} onChange={(e) => setRelationship(e.target.value)}>
            <option value="">Not specified</option>
            {RELATIONSHIP_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn" disabled={addingMember || email.trim() === "" || memberRoleId === ""}>
          {addingMember ? "Adding…" : "Add member"}
        </button>
      </form>
      <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
        Back
      </button>

      <section className="mp-roles" aria-labelledby="mp-roles-title">
        <div className="mp-roles-head">
          <h2 id="mp-roles-title">Roles &amp; permissions</h2>
          <p className="muted">What each role can do in this family. Open a role to change it.</p>
        </div>

        {roleList.length === 0 ? (
          <p className="muted">No roles yet.</p>
        ) : (
          <div className="mp-role-list">
            {roleList.map((r) => {
              const draft = permDrafts[r.id] ?? [];
              const known = draft.filter((p) => PERMISSION_OPTIONS.includes(p));
              const changed = !sameSet(draft, r.permissions);
              const memberCount = memberList.filter((m) => m.role_name === r.name).length;
              return (
                <details key={r.id} className="mp-role">
                  <summary className="mp-role-summary">
                    <span className="mp-role-name">
                      {r.name}
                      {r.is_system && <span className="mp-tag">System</span>}
                      {changed && <span className="mp-tag mp-tag-warn">Unsaved</span>}
                    </span>
                    <span className="mp-role-meta">
                      {memberCount} {memberCount === 1 ? "member" : "members"} ·{" "}
                      {known.length === PERMISSION_OPTIONS.length
                        ? "Full access"
                        : `${known.length} of ${PERMISSION_OPTIONS.length} allowed`}
                    </span>
                  </summary>
                  <div className="mp-role-body">
                    <PermissionPicker
                      idPrefix={`perm-${r.id}`}
                      selected={draft}
                      onChange={(next) => {
                        setSavedRoleId(null);
                        setPermDrafts((prev) => ({ ...prev, [r.id]: next }));
                      }}
                    />
                    <div className="mp-role-actions">
                      {savedRoleId === r.id && !changed && (
                        <span role="status" className="mp-saved">
                          ✓ Saved
                        </span>
                      )}
                      {changed && (
                        <button
                          type="button"
                          className="mp-btn mp-btn-ghost"
                          onClick={() => setPermDrafts((prev) => ({ ...prev, [r.id]: r.permissions }))}
                        >
                          Undo changes
                        </button>
                      )}
                      <button
                        type="button"
                        className="mp-btn"
                        disabled={!changed || savingRoleId === r.id}
                        onClick={() => void handleSavePermissions(r)}
                      >
                        {savingRoleId === r.id ? "Saving…" : "Save permissions"}
                      </button>
                    </div>
                  </div>
                </details>
              );
            })}
          </div>
        )}

        <details className="mp-role mp-new-role">
          <summary className="mp-role-summary">
            <span className="mp-role-name">+ Create a new role</span>
            <span className="mp-role-meta">For example “Nurse” or “Neighbour”</span>
          </summary>
          <form className="mp-role-body" onSubmit={handleCreateRole} aria-label="Create role">
            <label className="mp-field">
              Role name
              <input value={roleName} onChange={(e) => setRoleName(e.target.value)} required maxLength={64} />
            </label>
            <PermissionPicker idPrefix="new-role" selected={rolePermissions} onChange={setRolePermissions} />
            <div className="mp-role-actions">
              <button type="submit" className="mp-btn" disabled={creatingRole || roleName.trim() === ""}>
                {creatingRole ? "Creating…" : "Create role"}
              </button>
            </div>
          </form>
        </details>
      </section>
    </main>
  );
}
