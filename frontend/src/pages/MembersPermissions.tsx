import { useEffect, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { ApiError, members, roles } from "../api";
import type { MemberOut, RoleOut } from "../api";
import { RELATIONSHIP_OPTIONS } from "../lib/constants";

interface MembersPermissionsProps {
  familyId: string;
}

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

const PERMISSION_OPTIONS: string[] = [
  "dashboard.view", "parent_profile.view", "parent_profile.edit", "medicines.view", "medicines.edit",
  "medicine_quantity.update", "reports.view", "reports.upload", "tasks.view", "tasks.create",
  "tasks.assign", "tasks.update_own", "appointments.view", "appointments.create", "appointments.update",
  "appointments.delete", "activity.view", "members.manage", "roles.manage", "notifications.configure",
  "voice.use_parent_mode",
];

export default function MembersPermissions({ familyId }: MembersPermissionsProps) {
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

  const selectedValues = (e: ChangeEvent<HTMLSelectElement>) => Array.from(e.target.selectedOptions, (o) => o.value);

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
    try {
      const updated = await roles.updatePermissions(familyId, role.id, {
        permissions: permDrafts[role.id] ?? [],
      });
      setRoleList((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      setPermDrafts((prev) => ({ ...prev, [updated.id]: updated.permissions }));
    } catch (err: unknown) {
      setActionError(messageOf(err));
    }
  };

  if (loading) return <p role="status">Loading members and roles…</p>;
  if (error) return <p role="alert">{error}</p>;

  return (
    <main className="parent-layout wizard-page" aria-labelledby="members-permissions-heading">
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

      <h3>Roles</h3>
      {roleList.length === 0 ? (
        <p>No roles yet.</p>
      ) : (
        <ul>
          {roleList.map((r) => (
            <li key={r.id}>
              <strong>{r.name}</strong>
              {r.is_system ? " (system)" : ""}
              <fieldset className="wizard-field">
                <legend>Permissions</legend>
                {PERMISSION_OPTIONS.map((p) => {
                  const selected = permDrafts[r.id] ?? [];
                  return (
                    <label key={p}>
                      <input
                        type="checkbox"
                        id={`perm-${r.id}-${p}`}
                        checked={selected.includes(p)}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...selected, p]
                            : selected.filter((v) => v !== p);
                          setPermDrafts((prev) => ({ ...prev, [r.id]: next }));
                        }}
                      />
                      {p}
                    </label>
                  );
                })}
              </fieldset>

              <button type="button" className="btn btn-secondary" onClick={() => void handleSavePermissions(r)}>
                Save permissions
              </button>
            </li>
          ))}
        </ul>
      )}

      <form className="wizard-form" onSubmit={handleCreateRole} aria-label="Create role">
        <label className="wizard-field">
          Role name
          <input value={roleName} onChange={(e) => setRoleName(e.target.value)} required maxLength={64} />
        </label>
        <label className="wizard-field">
          Permissions
          <select multiple value={rolePermissions} onChange={(e) => setRolePermissions(selectedValues(e))}>
            {PERMISSION_OPTIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn" disabled={creatingRole || roleName.trim() === ""}>
          {creatingRole ? "Creating…" : "Create role"}
        </button>
      </form>
    </main>
  );
}
