import { useEffect, useState } from "react";
import { notificationLine } from "../notificationText";
import {
  ApiError,
  families,
  medicines,
  notifications,
  tasks,
  type FamilyOut,
  type MedicineOut,
  type MyAccess,
  type NotificationOut,
  type TaskOut,
} from "../api";

interface DashboardData {
  family: FamilyOut;
  access: MyAccess;
  medicines: MedicineOut[];
  tasks: TaskOut[];
  notifications: NotificationOut[];
}

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Could not load the dashboard.";
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const list = await families.list();
        const family = list[0];
        if (!family) {
          throw new ApiError(404, "No family found. Create one to get started.");
        }
        const [access, meds, taskList, notes] = await Promise.all([
          families.me(family.id),
          medicines.list(family.id),
          tasks.list(family.id),
          notifications.list(),
        ]);
        if (!cancelled) {
          setData({ family, access, medicines: meds, tasks: taskList, notifications: notes });
        }
      } catch (err) {
        if (!cancelled) setError(errorText(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <p role="status">Loading dashboard…</p>;
  if (error) return <p role="alert">{error}</p>;
  if (!data) return null;

  const openTasks = data.tasks.filter((t) => t.status !== "completed");
  const unreadNotes = data.notifications.filter((n) => n.status !== "read");

  return (
    <main>
      <h1>{data.family.name}</h1>
      <p>Your role: {data.access.role}</p>

      <section>
        <h2>Medicines ({data.medicines.length})</h2>
        <ul>
          {data.medicines.map((m) => (
            <li key={m.id}>
              {m.display_name}
              {m.quantity_remaining !== null && ` — ${m.quantity_remaining} left`}
              {m.refill_date && ` — refill ${m.refill_date}`}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Open tasks ({openTasks.length})</h2>
        <ul>
          {openTasks.map((t) => (
            <li key={t.id}>
              {t.title} — {t.status}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2>Notifications ({unreadNotes.length} unread)</h2>
        <ul>
          {data.notifications.map((n) => (
            <li key={n.id}>
              {notificationLine(n).urgent && <strong className="notification-urgent">Needs attention now: </strong>}
              {notificationLine(n).text} — {n.status}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
