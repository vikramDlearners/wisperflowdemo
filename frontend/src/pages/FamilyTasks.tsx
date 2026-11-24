import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, auth, families, members, tasks } from "../api";
import type { MemberOut, TaskOut } from "../api";
import WorkspaceLayout from "../components/WorkspaceLayout";
import "../tasks.css";

interface FamilyTasksProps {
  familyId: string;
}

// The server's statuses. Older data may use other spellings, so reading is forgiving.
type Status = "OPEN" | "IN_PROGRESS" | "DONE";
type Filter = "all" | "mine" | "unassigned" | "today" | "overdue";
type Priority = "low" | "normal" | "high";

const COLUMNS: { key: Status; title: string; empty: string }[] = [
  { key: "OPEN", title: "To do", empty: "Nothing waiting. Nice!" },
  { key: "IN_PROGRESS", title: "In progress", empty: "Press “Start” on a task when someone begins it." },
  { key: "DONE", title: "Completed", empty: "Finished tasks show up here." },
];

const PRIORITIES: { key: Priority; label: string }[] = [
  { key: "low", label: "Low" },
  { key: "normal", label: "Normal" },
  { key: "high", label: "High" },
];

// Ideas shown when the family has no tasks yet; one click fills the new-task form.
const IDEAS = [
  "Refill blood pressure tablets",
  "Book the next doctor's appointment",
  "Pick up lab test reports",
  "Pay the electricity bill",
  "Call Amma in the evening",
];

const DONE_LIMIT = 5;

function statusOf(task: TaskOut): Status {
  const s = task.status.trim().toUpperCase().replace(/[\s-]+/g, "_");
  if (s === "DONE" || s === "COMPLETED") return "DONE";
  if (s === "IN_PROGRESS") return "IN_PROGRESS";
  return "OPEN";
}

function priorityOf(task: TaskOut): Priority {
  const p = task.priority.trim().toLowerCase();
  return p === "high" || p === "low" ? p : "normal";
}

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}

function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

/** YYYY-MM-DD in local time, for <input type="date">. */
function toDateInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** A due date picked as a day is stored at 6 PM local time that day. */
function dueIso(date: string): string | null {
  if (!date) return null;
  const [y, m, d] = date.split("-").map(Number);
  return new Date(y, m - 1, d, 18, 0, 0).toISOString();
}

type DueState = "overdue" | "today" | "tomorrow" | "later";

function dueInfo(iso: string, now: Date): { text: string; state: DueState } {
  const due = new Date(iso);
  const today = startOfDay(now);
  const day = startOfDay(due);
  const diff = Math.round((day.getTime() - today.getTime()) / 86400000);
  const date = due.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  if (diff < 0) return { text: diff === -1 ? "Overdue · yesterday" : `Overdue · ${date}`, state: "overdue" };
  if (diff === 0) return { text: "Due today", state: "today" };
  if (diff === 1) return { text: "Due tomorrow", state: "tomorrow" };
  if (diff < 7) return { text: `Due ${due.toLocaleDateString(undefined, { weekday: "long" })}`, state: "later" };
  return { text: `Due ${date}`, state: "later" };
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts
    .slice(0, 2)
    .map((p) => p.charAt(0).toUpperCase())
    .join("");
}

const PRIORITY_RANK: Record<Priority, number> = { high: 0, normal: 1, low: 2 };

/** Overdue first, then the soonest due date, then the highest priority. Tasks without a date go last. */
function compareTasks(a: TaskOut, b: TaskOut): number {
  const da = a.due_at ? new Date(a.due_at).getTime() : Infinity;
  const db = b.due_at ? new Date(b.due_at).getTime() : Infinity;
  if (da !== db) return da - db;
  return PRIORITY_RANK[priorityOf(a)] - PRIORITY_RANK[priorityOf(b)];
}

interface Draft {
  title: string;
  description: string;
  due: string; // YYYY-MM-DD
  priority: Priority;
  assignee: string;
}

const EMPTY_DRAFT: Draft = { title: "", description: "", due: "", priority: "normal", assignee: "" };

export default function FamilyTasks({ familyId }: FamilyTasksProps) {
  const [items, setItems] = useState<TaskOut[]>([]);
  const [memberList, setMemberList] = useState<MemberOut[]>([]);
  const [myId, setMyId] = useState<string | null>(null);
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ text: string; bad?: boolean } | null>(null);
  const [busy, setBusy] = useState<Record<string, boolean>>({});

  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [showAllDone, setShowAllDone] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  // The add / edit panel. editing = the task's id, or "new".
  const [editing, setEditing] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).has("new") ? "new" : null,
  );
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const titleRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([
      tasks.list(familyId),
      members.list(familyId),
      auth.me().catch(() => null),
      families.me(familyId).catch(() => null),
    ])
      .then(([taskData, memberData, me, access]) => {
        if (cancelled) return;
        setItems(taskData);
        setMemberList(memberData);
        setMyId(me?.id ?? null);
        setPermissions(access?.permissions ?? null);
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

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), toast.bad ? 7000 : 4000);
    return () => window.clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    if (editing) titleRef.current?.focus();
  }, [editing]);

  // If permissions can't be read, show every control; the server still checks.
  const can = (code: string) => permissions === null || permissions.includes(code);
  const canCreate = can("tasks.create");
  const canAssign = can("tasks.assign");

  const memberName = (userId: string | null): string => {
    if (!userId) return "No one yet";
    if (userId === myId) return "You";
    return memberList.find((m) => m.user_id === userId)?.display_name ?? "Former member";
  };

  const replaceTask = (updated: TaskOut) => setItems((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));

  const run = async (taskId: string, action: () => Promise<TaskOut | void>, done?: string) => {
    setBusy((b) => ({ ...b, [taskId]: true }));
    try {
      const result = await action();
      if (result) replaceTask(result);
      if (done) setToast({ text: done });
    } catch (err) {
      setToast({ text: messageOf(err), bad: true });
    } finally {
      setBusy((b) => {
        const next = { ...b };
        delete next[taskId];
        return next;
      });
    }
  };

  const setStatus = (task: TaskOut, status: Status, done: string) =>
    run(task.id, () => tasks.updateStatus(familyId, task.id, { status }), done);

  const remove = (task: TaskOut) =>
    run(
      task.id,
      async () => {
        await tasks.delete(familyId, task.id);
        setItems((prev) => prev.filter((t) => t.id !== task.id));
        setConfirmDelete(null);
      },
      `Deleted “${task.title}”.`,
    );

  function openNew(title = "") {
    setDraft({ ...EMPTY_DRAFT, title });
    setFormError(null);
    setEditing("new");
  }

  function openEdit(task: TaskOut) {
    setDraft({
      title: task.title,
      description: task.description ?? "",
      due: task.due_at ? toDateInput(new Date(task.due_at)) : "",
      priority: priorityOf(task),
      assignee: task.assigned_to_user_id ?? "",
    });
    setFormError(null);
    setEditing(task.id);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function closeForm() {
    setEditing(null);
    setFormError(null);
  }

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.title.trim()) {
      setFormError("Give the task a short title, e.g. “Refill BP tablets”.");
      titleRef.current?.focus();
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      if (editing === "new") {
        const created = await tasks.create(familyId, {
          title: draft.title.trim(),
          description: draft.description.trim() || null,
          due_at: dueIso(draft.due),
          priority: draft.priority,
          assigned_to_user_id: draft.assignee || null,
        });
        setItems((prev) => [...prev, created]);
        setToast({ text: `Added “${created.title}”.` });
      } else if (editing) {
        const before = items.find((t) => t.id === editing);
        let updated = await tasks.update(familyId, editing, {
          title: draft.title.trim(),
          description: draft.description.trim() || null,
          due_at: dueIso(draft.due),
          priority: draft.priority,
        });
        if (draft.assignee && draft.assignee !== before?.assigned_to_user_id) {
          updated = await tasks.assign(familyId, editing, { assignee_user_id: draft.assignee });
        }
        replaceTask(updated);
        setToast({ text: "Task updated." });
      }
      setEditing(null);
      setDraft(EMPTY_DRAFT);
    } catch (err) {
      setFormError(messageOf(err));
    } finally {
      setSaving(false);
    }
  }

  // ---- counts and filtering ----
  const now = new Date();
  const today = startOfDay(now);
  const tomorrow = addDays(today, 1);
  const open = items.filter((t) => statusOf(t) !== "DONE");
  const isOverdue = (t: TaskOut) => Boolean(t.due_at) && new Date(t.due_at!) < today && statusOf(t) !== "DONE";
  const isToday = (t: TaskOut) => {
    if (!t.due_at || statusOf(t) === "DONE") return false;
    const d = new Date(t.due_at);
    return d >= today && d < tomorrow;
  };
  const counts = {
    open: open.length,
    mine: open.filter((t) => myId && t.assigned_to_user_id === myId).length,
    unassigned: open.filter((t) => !t.assigned_to_user_id).length,
    today: items.filter(isToday).length,
    overdue: items.filter(isOverdue).length,
    done: items.length - open.length,
  };

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((t) => {
      if (q && !`${t.title} ${t.description ?? ""}`.toLowerCase().includes(q)) return false;
      if (filter === "mine") return Boolean(myId) && t.assigned_to_user_id === myId;
      if (filter === "unassigned") return !t.assigned_to_user_id;
      if (filter === "today") return isToday(t);
      if (filter === "overdue") return isOverdue(t);
      return true;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, filter, search, myId]);

  const FILTERS: { key: Filter; label: string; count: number }[] = [
    { key: "all", label: "All", count: items.length },
    { key: "mine", label: "Mine", count: counts.mine },
    { key: "unassigned", label: "Needs someone", count: counts.unassigned },
    { key: "today", label: "Due today", count: counts.today },
    { key: "overdue", label: "Overdue", count: counts.overdue },
  ];

  // ---- rendering ----

  const renderCard = (task: TaskOut) => {
    const status = statusOf(task);
    const done = status === "DONE";
    const priority = priorityOf(task);
    const due = task.due_at ? dueInfo(task.due_at, now) : null;
    const assigned = task.assigned_to_user_id;
    const working = Boolean(busy[task.id]);
    const mine = Boolean(myId) && assigned === myId;

    return (
      <li
        key={task.id}
        className={`tasks-card${done ? " is-done" : ""}${due && !done ? ` due-${due.state}` : ""}`}
        aria-busy={working}
      >
        <div className="tasks-card__top">
          <button
            type="button"
            className={`tasks-check${done ? " is-on" : ""}`}
            aria-label={done ? `Mark “${task.title}” as not done` : `Mark “${task.title}” as done`}
            disabled={working}
            onClick={() =>
              void (done
                ? setStatus(task, "OPEN", "Moved back to To do.")
                : setStatus(task, "DONE", `Done: “${task.title}”. 🎉`))
            }
          >
            {done ? "✓" : ""}
          </button>
          <div className="tasks-card__main">
            <strong className="tasks-card__title">{task.title}</strong>
            {task.description && <p className="tasks-card__desc">{task.description}</p>}
          </div>
          {!done && priority !== "normal" && (
            <span className={`tasks-pill tasks-pill--${priority}`}>{priority === "high" ? "High" : "Low"}</span>
          )}
        </div>

        <div className="tasks-card__meta">
          {due && !done && <span className={`tasks-due tasks-due--${due.state}`}>{due.text}</span>}
          {!(done && !assigned) && (
          <span className={`tasks-owner${assigned ? "" : " is-empty"}`}>
            <span className={assigned ? "tasks-avatar" : "tasks-avatar tasks-avatar--empty"} aria-hidden="true">
              {assigned ? initialsOf(memberName(assigned)) : "?"}
            </span>
            {canAssign && !done ? (
              <select
                aria-label={`Who does “${task.title}”`}
                value={assigned ?? ""}
                disabled={working}
                onChange={(e) => {
                  const userId = e.target.value;
                  if (userId)
                    void run(
                      task.id,
                      () => tasks.assign(familyId, task.id, { assignee_user_id: userId }),
                      `Given to ${memberName(userId)}.`,
                    );
                }}
              >
                <option value="" disabled>
                  Needs someone
                </option>
                {memberList.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.user_id === myId ? "You" : m.display_name}
                  </option>
                ))}
              </select>
            ) : (
              <span>{done && assigned ? `Done by ${memberName(assigned)}` : memberName(assigned)}</span>
            )}
          </span>
          )}
        </div>

        {confirmDelete === task.id ? (
          <div className="tasks-card__confirm" role="group" aria-label="Confirm delete">
            <span>Delete this task?</span>
            <button type="button" className="tasks-btn tasks-btn--danger tasks-btn--small" onClick={() => void remove(task)}>
              Delete
            </button>
            <button type="button" className="tasks-btn tasks-btn--ghost tasks-btn--small" onClick={() => setConfirmDelete(null)}>
              Keep
            </button>
          </div>
        ) : (
          <div className="tasks-card__actions">
            {status === "OPEN" && (
              <button
                type="button"
                className="tasks-btn tasks-btn--soft tasks-btn--small"
                disabled={working}
                onClick={() => void setStatus(task, "IN_PROGRESS", "Moved to In progress.")}
              >
                ▶ Start
              </button>
            )}
            {status === "IN_PROGRESS" && (
              <button
                type="button"
                className="tasks-btn tasks-btn--soft tasks-btn--small"
                disabled={working}
                onClick={() => void setStatus(task, "DONE", `Done: “${task.title}”. 🎉`)}
              >
                ✓ Mark done
              </button>
            )}
            {done && (
              <button
                type="button"
                className="tasks-btn tasks-btn--ghost tasks-btn--small"
                disabled={working}
                onClick={() => void setStatus(task, "OPEN", "Moved back to To do.")}
              >
                ↺ Reopen
              </button>
            )}
            {!done && (
              <button
                type="button"
                className="tasks-btn tasks-btn--ghost tasks-btn--small"
                disabled={working}
                title={assigned ? `Send ${memberName(assigned)} a reminder` : "Remind everyone in the family"}
                onClick={() =>
                  void run(
                    task.id,
                    () => tasks.notify(familyId, task.id),
                    assigned && !mine
                      ? `Reminder sent to ${memberName(assigned)}.`
                      : "Reminder sent to the family.",
                  )
                }
              >
                🔔 Remind
              </button>
            )}
            <span className="tasks-card__spacer" />
            {canCreate && (
              <button
                type="button"
                className="tasks-icon-btn"
                aria-label={`Edit “${task.title}”`}
                title="Edit"
                onClick={() => openEdit(task)}
              >
                ✎
              </button>
            )}
            {canAssign && (
              <button
                type="button"
                className="tasks-icon-btn"
                aria-label={`Delete “${task.title}”`}
                title="Delete"
                onClick={() => setConfirmDelete(task.id)}
              >
                🗑
              </button>
            )}
          </div>
        )}
      </li>
    );
  };

  const quickDue: { label: string; date: string }[] = [
    { label: "Today", date: toDateInput(today) },
    { label: "Tomorrow", date: toDateInput(tomorrow) },
    { label: "In 3 days", date: toDateInput(addDays(today, 3)) },
    { label: "Next week", date: toDateInput(addDays(today, 7)) },
  ];

  const form = editing && (
    <form onSubmit={handleSave} aria-label={editing === "new" ? "New task" : "Edit task"} className="tasks-form" noValidate>
      <div className="tasks-form__head">
        <h3>{editing === "new" ? "New task" : "Edit task"}</h3>
        <button type="button" className="tasks-icon-btn" aria-label="Close" onClick={closeForm}>
          ✕
        </button>
      </div>

      <label className="tasks-field tasks-field--wide">
        <span>What needs doing?</span>
        <input
          ref={titleRef}
          value={draft.title}
          maxLength={255}
          placeholder="e.g. Refill BP tablets"
          aria-invalid={Boolean(formError && !draft.title.trim())}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
        />
      </label>

      <label className="tasks-field tasks-field--wide">
        <span>
          Notes <small>Optional</small>
        </span>
        <textarea
          rows={2}
          value={draft.description}
          placeholder="Anything that helps, e.g. which pharmacy or the doctor's number"
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
        />
      </label>

      <div className="tasks-field">
        <span id="tasks-due-label">When is it due?</span>
        <div className="tasks-chips" role="group" aria-labelledby="tasks-due-label">
          {quickDue.map((q) => (
            <button
              key={q.label}
              type="button"
              className={`tasks-chip${draft.due === q.date ? " is-on" : ""}`}
              aria-pressed={draft.due === q.date}
              onClick={() => setDraft({ ...draft, due: draft.due === q.date ? "" : q.date })}
            >
              {q.label}
            </button>
          ))}
          <input
            type="date"
            aria-label="Pick a due date"
            value={draft.due}
            min={editing === "new" ? toDateInput(today) : undefined}
            onChange={(e) => setDraft({ ...draft, due: e.target.value })}
          />
        </div>
      </div>

      <div className="tasks-field">
        <span id="tasks-priority-label">How urgent?</span>
        <div className="tasks-segment" role="radiogroup" aria-labelledby="tasks-priority-label">
          {PRIORITIES.map((p) => (
            <button
              key={p.key}
              type="button"
              role="radio"
              aria-checked={draft.priority === p.key}
              className={`tasks-segment__btn tasks-segment__btn--${p.key}${draft.priority === p.key ? " is-on" : ""}`}
              onClick={() => setDraft({ ...draft, priority: p.key })}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {canAssign && (
        <label className="tasks-field">
          <span>Who will do it?</span>
          <select value={draft.assignee} onChange={(e) => setDraft({ ...draft, assignee: e.target.value })}>
            <option value="">Decide later</option>
            {memberList.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.user_id === myId ? "Me" : m.display_name}
                {m.role_name ? ` · ${m.role_name}` : ""}
              </option>
            ))}
          </select>
        </label>
      )}

      {formError && (
        <p role="alert" className="tasks-form__error">
          {formError}
        </p>
      )}

      <div className="tasks-form__actions">
        <button type="button" className="tasks-btn tasks-btn--ghost" onClick={closeForm}>
          Cancel
        </button>
        <button type="submit" className="tasks-btn tasks-btn--primary" disabled={saving}>
          {saving ? "Saving…" : editing === "new" ? "Add task" : "Save changes"}
        </button>
      </div>
    </form>
  );

  const body = loading ? (
    <p role="status" className="tasks-muted">
      Loading tasks…
    </p>
  ) : error ? (
    <p role="alert" className="tasks-alert">
      Could not load tasks: {error}
    </p>
  ) : (
    <>
      <div className="tasks-stats">
        {(
          [
            { key: "all", value: counts.open, label: "Open tasks", tone: "" },
            { key: "today", value: counts.today, label: "Due today", tone: counts.today ? "warn" : "" },
            { key: "overdue", value: counts.overdue, label: "Overdue", tone: counts.overdue ? "bad" : "" },
            { key: "mine", value: counts.mine, label: "Assigned to you", tone: "" },
          ] as { key: Filter; value: number; label: string; tone: string }[]
        ).map((s) => (
          <button
            key={s.key}
            type="button"
            className={`tasks-stat${s.tone ? ` tasks-stat--${s.tone}` : ""}${filter === s.key && s.key !== "all" ? " is-on" : ""}`}
            aria-pressed={filter === s.key && s.key !== "all"}
            onClick={() => setFilter(filter === s.key ? "all" : s.key)}
          >
            <span className="tasks-stat__value">{s.value}</span>
            <span className="tasks-stat__label">{s.label}</span>
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="tasks-welcome">
          <div className="tasks-welcome__icon" aria-hidden="true">
            🗂️
          </div>
          <h3>No tasks yet</h3>
          <p>
            Tasks help the family share the work of care: refills, appointments, bills and calls. Tasks from the
            parent's chats also appear here.
          </p>
          {canCreate && (
            <>
              <p className="tasks-muted">Start with one of these:</p>
              <div className="tasks-chips tasks-chips--center">
                {IDEAS.map((idea) => (
                  <button key={idea} type="button" className="tasks-chip" onClick={() => openNew(idea)}>
                    + {idea}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      ) : (
        <>
          <div className="tasks-toolbar">
            <div className="tasks-chips" role="group" aria-label="Show">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  className={`tasks-chip${filter === f.key ? " is-on" : ""}`}
                  aria-pressed={filter === f.key}
                  onClick={() => setFilter(f.key)}
                >
                  {f.label}
                  <span className="tasks-chip__count">{f.count}</span>
                </button>
              ))}
            </div>
            <input
              type="search"
              className="tasks-search"
              placeholder="Search tasks"
              aria-label="Search tasks"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {visible.length === 0 ? (
            <div className="tasks-nomatch">
              No tasks match.{" "}
              <button
                type="button"
                className="tasks-link"
                onClick={() => {
                  setFilter("all");
                  setSearch("");
                }}
              >
                Show all tasks
              </button>
            </div>
          ) : (
            <div className="tasks-board">
              {COLUMNS.map((col) => {
                const all = visible.filter((t) => statusOf(t) === col.key).sort(compareTasks);
                const list = col.key === "DONE" && !showAllDone ? all.slice(0, DONE_LIMIT) : all;
                return (
                  <section key={col.key} className={`tasks-column tasks-column--${col.key.toLowerCase()}`}>
                    <div className="tasks-column__header">
                      <h3 className="tasks-column__title">{col.title}</h3>
                      <span className="tasks-count">{all.length}</span>
                    </div>
                    {all.length === 0 ? (
                      <p className="tasks-empty">{col.empty}</p>
                    ) : (
                      <ul className="tasks-list">{list.map(renderCard)}</ul>
                    )}
                    {col.key === "DONE" && all.length > DONE_LIMIT && (
                      <button type="button" className="tasks-link tasks-more" onClick={() => setShowAllDone((v) => !v)}>
                        {showAllDone ? "Show fewer" : `Show all ${all.length} completed`}
                      </button>
                    )}
                  </section>
                );
              })}
            </div>
          )}
        </>
      )}
    </>
  );

  return (
    <WorkspaceLayout familyId={familyId} current="tasks" title="Family tasks">
      <section className="tasks-page" aria-labelledby="family-tasks-heading">
        <header className="tasks-header">
          <div>
            <p className="tasks-eyebrow">Care circle · Family workspace</p>
            <h2 id="family-tasks-heading" className="tasks-title">
              Family tasks
            </h2>
            <p className="tasks-subtitle">Share the work of care. Every task has someone to do it and a due date.</p>
          </div>
          {canCreate && !editing && (
            <button type="button" className="tasks-btn tasks-btn--primary" onClick={() => openNew()}>
              + New task
            </button>
          )}
        </header>

        {form}
        {body}

        {toast && (
          <div className={`tasks-toast${toast.bad ? " is-bad" : ""}`} role={toast.bad ? "alert" : "status"}>
            {toast.text}
            <button type="button" aria-label="Dismiss" onClick={() => setToast(null)}>
              ✕
            </button>
          </div>
        )}
      </section>
    </WorkspaceLayout>
  );
}
