import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, intentMode, notifications } from "../api";
import type { NotificationOut } from "../api";
import { notificationLine } from "../notificationText";

interface NotificationSettingsProps {
  familyId: string;
}

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

export default function NotificationSettings({ familyId }: NotificationSettingsProps) {
  const [currentMode, setCurrentMode] = useState<string>("");
  const [modeDraft, setModeDraft] = useState<string>("");
  const [items, setItems] = useState<NotificationOut[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([intentMode.get(familyId), notifications.list()])
      .then(([modeData, notificationData]) => {
        if (cancelled) return;
        setCurrentMode(modeData.intent_mode);
        setModeDraft(modeData.intent_mode);
        setItems(notificationData);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(messageOf(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [familyId]);

  const handleSaveMode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setActionError(null);
    setSaving(true);
    try {
      const saved = await intentMode.put(familyId, { intent_mode: modeDraft.trim() });
      setCurrentMode(saved.intent_mode);
      setModeDraft(saved.intent_mode);
    } catch (err: unknown) {
      setActionError(messageOf(err));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p role="status">Loading notification settings…</p>;
  if (error) return <p role="alert">Could not load notification settings: {error}</p>;

  return (
    <section aria-labelledby="notification-settings-heading">
      <h2 id="notification-settings-heading">Notification settings</h2>

      {actionError && <p role="alert">{actionError}</p>}

      <form onSubmit={handleSaveMode} aria-label="Intent mode">
        <label>
          Intent mode
          <input value={modeDraft} onChange={(e) => setModeDraft(e.target.value)} required />
        </label>
        <p>Current: {currentMode || "not set"}</p>
        <button type="submit" disabled={saving || modeDraft.trim() === "" || modeDraft.trim() === currentMode}>
          {saving ? "Saving…" : "Save intent mode"}
        </button>
      </form>

      <h3>Notifications</h3>
      {items.length === 0 ? (
        <p>No notifications.</p>
      ) : (
        <ul>
          {items.map((n) => (
            <li key={n.id}>
              {notificationLine(n).urgent && <strong className="notification-urgent">Needs attention now: </strong>}
              <strong>{notificationLine(n).text}</strong> — {n.status}
              <time dateTime={n.created_at}> · {new Date(n.created_at).toLocaleString()}</time>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
