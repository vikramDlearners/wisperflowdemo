import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { ApiError, auth, members, type MemberOut } from "../api";

// Lists the family's members and lets a manager remove them (soft delete via
// DELETE /api/families/{familyId}/members/{membershipId}). The backend rejects
// removing the family creator; the current user's own row is hidden here.

function messageFrom(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  return "Something went wrong. Please check your connection and try again.";
}

export default function ManageProfile() {
  const { familyId = "" } = useParams();

  const [rows, setRows] = useState<MemberOut[]>([]);
  const [myUserId, setMyUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await members.list(familyId));
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setLoading(false);
    }
  }, [familyId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let active = true;
    auth
      .me()
      .then((me) => {
        if (active) setMyUserId(me.id);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  async function handleRemove(m: MemberOut) {
    if (!window.confirm("Remove this user from the profile?")) return;
    setBusyId(m.membership_id);
    setError(null);
    try {
      await members.remove(familyId, m.membership_id);
      await load();
    } catch (err) {
      setError(messageFrom(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <WorkspaceLayout familyId={familyId} current="manage-profile" title="Manage Profile">
      <div className="pp-content">
        <div className="pp-page-head">
          <div>
            <p className="pp-eyebrow">Care circle · Family workspace</p>
            <h1>Manage Profile</h1>
            <p className="pp-muted">See who is on this family profile and remove users who no longer need access.</p>
          </div>
        </div>

        {error && (
          <div role="alert" className="pp-alert">
            {error}
          </div>
        )}

        <section className="pp-card" aria-label="Users on this profile">
          {loading ? (
            <p role="status" className="pp-muted">
              Loading users…
            </p>
          ) : rows.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Relationship</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((m) => (
                  <tr key={m.membership_id}>
                    <td>{m.display_name}</td>
                    <td>{m.email ?? "—"}</td>
                    <td>{m.role_name}</td>
                    <td>{m.relationship ?? "—"}</td>
                    <td>
                      {m.user_id !== myUserId && (
                        <button
                          type="button"
                          className="pp-btn pp-btn-ghost"
                          onClick={() => void handleRemove(m)}
                          disabled={busyId !== null}
                        >
                          {busyId === m.membership_id ? "Removing…" : "Remove"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            !error && <p className="pp-muted">No users on this profile.</p>
          )}
        </section>
      </div>
    </WorkspaceLayout>
  );
}
