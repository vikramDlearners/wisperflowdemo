import { useEffect, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useParams } from "react-router-dom";
import { API_BASE_URL, ApiError, taskLinks } from "../api";
import type { TaskLinkView } from "../api";
import "../task-link.css";

// Opened from a shared task link. No sign-in: the token in the URL opens this one task.

const MAX_BYTES = 10 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png", "image/webp"];

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.detail;
  return "Something went wrong. Check your connection and try again.";
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function TaskLink() {
  const { token = "" } = useParams();
  const [task, setTask] = useState<TaskLinkView | null>(null);
  const [loadError, setLoadError] = useState<{ status: number; text: string } | null>(null);
  const [busy, setBusy] = useState<"" | "complete" | "note" | "image">("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [name, setName] = useState("");

  const reload = () =>
    taskLinks.view(token).then(setTask, (err: unknown) =>
      setLoadError({ status: err instanceof ApiError ? err.status : 0, text: messageOf(err) }),
    );

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const act = async (kind: "complete" | "note" | "image", action: () => Promise<unknown>) => {
    setBusy(kind);
    setError("");
    try {
      await action();
      await reload();
      return true;
    } catch (err) {
      setError(messageOf(err));
      return false;
    } finally {
      setBusy("");
    }
  };

  const submitNote = async (e: FormEvent) => {
    e.preventDefault();
    if (!note.trim()) return;
    if (await act("note", () => taskLinks.addNote(token, note.trim(), name.trim() || null))) setNote("");
  };

  const upload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!TYPES.includes(file.type)) return setError("Choose a JPEG, PNG or WebP photo.");
    if (file.size > MAX_BYTES) return setError("The photo must be 10 MB or smaller.");
    await act("image", () => taskLinks.addImage(token, file));
  };

  if (loadError) {
    const gone = loadError.status === 410;
    return (
      <main className="tl-page">
        <section className="tl-card tl-card--empty" role="alert">
          <h1>{gone ? "This link no longer works" : "Task not found"}</h1>
          <p>
            {gone
              ? `${loadError.text}. Ask the person who shared it for a new link.`
              : loadError.status === 404
                ? "Check that you copied the whole link."
                : loadError.text}
          </p>
        </section>
      </main>
    );
  }

  if (!task) {
    return (
      <main className="tl-page">
        <p className="tl-muted" aria-live="polite">Loading task…</p>
      </main>
    );
  }

  const done = task.status === "DONE";

  return (
    <main className="tl-page">
      <p className="tl-eyebrow">CareCircle · shared task</p>
      <section className="tl-card">
        <div className="tl-head">
          <h1>{task.title}</h1>
          <span className={`tl-status${done ? " is-done" : ""}`}>
            {done ? "Done" : task.status === "IN_PROGRESS" ? "In progress" : "To do"}
          </span>
        </div>
        {task.description && <p className="tl-desc">{task.description}</p>}
        <dl className="tl-meta">
          {task.due_at && (
            <>
              <dt>Due</dt>
              <dd>{formatDate(task.due_at)}</dd>
            </>
          )}
          <dt>Assigned to</dt>
          <dd>{task.assignee_name ?? "No one yet"}</dd>
          {task.priority !== "normal" && (
            <>
              <dt>Priority</dt>
              <dd>{task.priority === "high" ? "High" : "Low"}</dd>
            </>
          )}
        </dl>
        <button
          type="button"
          className="tl-btn tl-btn--primary"
          disabled={done || busy !== ""}
          onClick={() => void act("complete", () => taskLinks.complete(token))}
        >
          {done ? "✓ Completed" : busy === "complete" ? "Marking…" : "Mark completed"}
        </button>
        {error && (
          <p className="tl-error" role="alert">
            {error}
          </p>
        )}
      </section>

      <section className="tl-card" aria-labelledby="tl-photos">
        <h2 id="tl-photos">Photos</h2>
        {task.images.length > 0 ? (
          <ul className="tl-photos">
            {task.images.map((img) => (
              <li key={img.id}>
                <a href={`${API_BASE_URL}${img.url}`} target="_blank" rel="noreferrer">
                  <img src={`${API_BASE_URL}${img.url}`} alt={`Photo added ${formatDate(img.created_at)}`} />
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="tl-muted">No photos yet.</p>
        )}
        <label className={`tl-btn tl-btn--soft${busy ? " is-disabled" : ""}`}>
          {busy === "image" ? "Uploading…" : "＋ Add a photo"}
          <input
            type="file"
            accept={TYPES.join(",")}
            className="tl-file"
            disabled={busy !== ""}
            onChange={(e) => void upload(e)}
          />
        </label>
        <p className="tl-hint">JPEG, PNG or WebP, up to 10 MB.</p>
      </section>

      <section className="tl-card" aria-labelledby="tl-notes">
        <h2 id="tl-notes">Notes</h2>
        {task.notes.length > 0 ? (
          <ul className="tl-notes">
            {task.notes.map((n) => (
              <li key={n.id}>
                <p>{n.body}</p>
                <span className="tl-muted">
                  {n.author_name ?? "Someone with the link"} · {formatDate(n.created_at)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="tl-muted">No notes yet.</p>
        )}
        <form className="tl-form" onSubmit={(e) => void submitNote(e)}>
          <label htmlFor="tl-note">Add a note</label>
          <textarea
            id="tl-note"
            rows={3}
            maxLength={2000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What happened, what's left to do…"
          />
          <label htmlFor="tl-name">Your name (optional)</label>
          <input id="tl-name" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
          <button type="submit" className="tl-btn tl-btn--primary" disabled={!note.trim() || busy !== ""}>
            {busy === "note" ? "Saving…" : "Save note"}
          </button>
        </form>
      </section>

      <p className="tl-hint">This link works until {formatDate(task.link_expires_at)}.</p>
    </main>
  );
}
