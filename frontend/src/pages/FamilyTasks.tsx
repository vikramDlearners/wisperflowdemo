import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, members, tasks } from "../api";
import type { MemberOut, TaskOut } from "../api";
import WorkspaceLayout from "../components/WorkspaceLayout";
import "../tasks.css";


interface FamilyTasksProps {
  familyId: string;
}

type ColumnKey = "todo" | "in_progress" | "done";

const DONE_STATUSES = ["done", "completed"];

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

function isDone(task: TaskOut): boolean {
  return DONE_STATUSES.includes(task.status);
}

function columnOf(task: TaskOut): ColumnKey {
  if (isDone(task)) return "done";
  if (task.status === "in_progress") return "in_progress";
  return "todo";
}

function startOfToday(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function formatDue(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function priorityPillClass(priority: string): string {
  const p = priority.trim().toLowerCase();
  if (p === "high") return "tasks-pill tasks-pill--high";
  if (p === "low") return "tasks-pill tasks-pill--low";
  return "tasks-pill tasks-pill--normal";
}

function priorityLabel(priority: string): string {
  const p = priority.trim();
  if (!p) return "Normal";
  return p.charAt(0).toUpperCase() + p.slice(1).toLowerCase();
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join("");
}

export default function FamilyTasks({ familyId }: FamilyTasksProps) {
  const [items, setItems] = useState<TaskOut[]>([]);
  const [memberList, setMemberList] = useState<MemberOut[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState<boolean>(() => new URLSearchParams(window.location.search).has("new"));
  const [notifyState, setNotifyState] = useState<Record<string, "pending" | "sent">>({});

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [priority, setPriority] = useState("");
  const [assignee, setAssignee] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([tasks.list(familyId), members.list(familyId)])
      .then(([taskData, memberData]) => {
        if (cancelled) return;
        setItems(taskData);
        setMemberList(memberData);
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

  const replaceTask = (updated: TaskOut) =>
    setItems((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));

  const runAction = async (action: () => Promise<TaskOut>) => {
    setActionError(null);
    try {
      replaceTask(await action());
    } catch (err: unknown) {
      setActionError(messageOf(err));
    }
  };

  const notifyThem = (taskId: string) =>
    runAction(async () => {
      setNotifyState((prev) => ({ ...prev, [taskId]: "pending" }));
      try {
        const updated = await tasks.notify(familyId, taskId);
        setNotifyState((prev) => ({ ...prev, [taskId]: "sent" }));
        return updated;
      } catch (err: unknown) {
        setNotifyState((prev) => {
          const next = { ...prev };
          delete next[taskId];
          return next;
        });
        throw err;
      }
    });

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setActionError(null);
    setCreating(true);
    try {
      const created = await tasks.create(familyId, {
        title: title.trim(),
        description: description.trim() || null,
        due_at: dueAt ? new Date(dueAt).toISOString() : null,
        priority: priority.trim() || undefined,
        assigned_to_user_id: assignee || null,
      });
      setItems((prev) => [...prev, created]);
      setTitle("");
      setDescription("");
      setDueAt("");
      setPriority("");
      setAssignee("");
    } catch (err: unknown) {
      setActionError(messageOf(err));
    } finally {
      setCreating(false);
    }
  };

  const memberName = (userId: string | null): string => {
    if (!userId) return "Unassigned";
    return memberList.find((m) => m.user_id === userId)?.display_name ?? userId;
  };

  const statusOptions = Array.from(new Set(items.map((t) => t.status)));

  // Stats, computed from loaded tasks only.
  // "Completed this week" is omitted: TaskOut has no completion timestamp.
  const today = startOfToday();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);
  const openTasks = items.filter((t) => !isDone(t));
  const dueTodayCount = openTasks.filter((t) => {
    if (!t.due_at) return false;
    const due = new Date(t.due_at);
    return due >= today && due < tomorrow;
  }).length;
  const overdueCount = openTasks.filter((t) => t.due_at && new Date(t.due_at) < today).length;

  const columns: { key: ColumnKey; title: string }[] = [
    { key: "todo", title: "To do" },
    { key: "in_progress", title: "In progress" },
    { key: "done", title: "Completed" },
  ];

  const renderCard = (task: TaskOut, column: ColumnKey) => {
    const done = column === "done";
    const assigned = task.assigned_to_user_id;
    const name = memberName(assigned);
    // Category and progress are not fields on TaskOut, so they are not shown.
    const dueText = task.due_at ? `Due ${formatDue(task.due_at)}` : null;
    const ownerLabel = done
      ? assigned
        ? "Completed by"
        : "Completed"
      : assigned
        ? "Assigned"
        : "Needs owner";

    return (
      <li key={task.id} className="tasks-card">
        <div className="tasks-card__top">
          <strong className="tasks-card__title">{task.title}</strong>
          {done ? (
            <span className="tasks-pill tasks-pill--done">Done</span>
          ) : (
            <span className={priorityPillClass(task.priority)}>{priorityLabel(task.priority)}</span>
          )}
        </div>
        {task.description && <p className="tasks-card__desc">{task.description}</p>}
        {dueText && <div className="tasks-card__meta">{dueText}</div>}

        <div className="tasks-card__owner">
          <span className={assigned ? "tasks-avatar" : "tasks-avatar tasks-avatar--empty"}>
            {assigned ? initialsOf(name) : "—"}
          </span>
          <div className="tasks-card__owner-text">
            <div className="tasks-card__owner-name">{name}</div>
            <div className="tasks-card__owner-label">{ownerLabel}</div>
          </div>
        </div>

        <div className="tasks-card__actions">
          <label>
            Assign
            <select
              value={task.assigned_to_user_id ?? ""}
              onChange={(e) => {
                const userId = e.target.value;
                if (userId) {
                  void runAction(() => tasks.assign(familyId, task.id, { assignee_user_id: userId }));
                }
              }}
            >
              <option value="">Choose a member</option>
              {memberList.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Status
            <input
              list={`task-status-options-${task.id}`}
              defaultValue={task.status}
              onBlur={(e) => {
                const next = e.target.value.trim();
                if (next && next !== task.status) {
                  void runAction(() => tasks.updateStatus(familyId, task.id, { status: next }));
                }
              }}
            />
            <datalist id={`task-status-options-${task.id}`}>
              {statusOptions.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </label>

          <button
            type="button"
            className="tasks-btn tasks-btn--small"
            disabled={done}
            onClick={() => void runAction(() => tasks.complete(familyId, task.id))}
          >
            Complete
          </button>

          <button
            type="button"
            className="tasks-btn tasks-btn--small"
            disabled={notifyState[task.id] === "pending"}
            onClick={() => void notifyThem(task.id)}
          >
            Notify them
          </button>
        </div>
        {notifyState[task.id] === "sent" && (
          <p role="status">
            Notification sent in email, whatsapp and text message. It also appears in the Overview tab.
          </p>
        )}
      </li>
    );
  };

  if (loading) return <p role="status">Loading tasks…</p>;
  if (error) return <p role="alert">Could not load tasks: {error}</p>;

  return (
    <WorkspaceLayout familyId={familyId} current="tasks" title="Family tasks">
    <section className="tasks-page" aria-labelledby="family-tasks-heading">

      <header className="tasks-header">
        <div>
          <p className="tasks-eyebrow">CARE CIRCLE · FAMILY WORKSPACE</p>
          <h2 id="family-tasks-heading" className="tasks-title">
            Family tasks
          </h2>
          <p className="tasks-subtitle">
            Coordinate the practical work of care. Every task has an owner, due date and clear status.
          </p>
        </div>
        <div className="tasks-header__actions">
          <button type="button" className="tasks-btn tasks-btn--outline" disabled title="No filters available on this page">
            Filters
          </button>
          <button
            type="button"
            className="tasks-btn tasks-btn--primary"
            aria-expanded={showForm}
            onClick={() => setShowForm((v) => !v)}
          >
            + New task
          </button>
        </div>
      </header>

      {actionError && <p role="alert">{actionError}</p>}

      {showForm && (
        <form onSubmit={handleCreate} aria-label="Create task" className="tasks-form">
          <label>
            Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={255} />
          </label>
          <label>
            Description
            <input value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
          <label>
            Due
            <input type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} />
          </label>
          <label>
            Priority
            <input value={priority} onChange={(e) => setPriority(e.target.value)} placeholder="normal" />
          </label>
          <label>
            Assign to
            <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">Unassigned</option>
              {memberList.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.display_name}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="tasks-btn tasks-btn--primary" disabled={creating || title.trim() === ""}>
            {creating ? "Creating…" : "Create task"}
          </button>
        </form>
      )}

      <div className="tasks-stats">
        <div className="tasks-stat">
          <div className="tasks-stat__value">{openTasks.length}</div>
          <div className="tasks-stat__label">Open tasks</div>
        </div>
        <div className="tasks-stat">
          <div className="tasks-stat__value">{dueTodayCount}</div>
          <div className="tasks-stat__label">Due today</div>
        </div>
        <div className="tasks-stat">
          <div className="tasks-stat__value">{overdueCount}</div>
          <div className="tasks-stat__label">Overdue</div>
        </div>
      </div>

      {items.length === 0 ? (
        <p className="tasks-empty-all">No tasks yet.</p>
      ) : (
        <div className="tasks-board">
          {columns.map((col) => {
            const list = items.filter((t) => columnOf(t) === col.key);
            return (
              <div key={col.key} className="tasks-column">
                <div className="tasks-column__header">
                  <h3 className="tasks-column__title">{col.title}</h3>
                  <span className="tasks-count">{list.length}</span>
                </div>
                {list.length === 0 ? (
                  <p className="tasks-empty">No tasks</p>
                ) : (
                  <ul className="tasks-list">{list.map((task) => renderCard(task, col.key))}</ul>
                )}
                {col.key === "done" && list.length > 0 && (
                  <p className="tasks-note">Completed tasks remain in the family activity history.</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
    </WorkspaceLayout>
  );
}
