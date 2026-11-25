import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import "../ask-help.css";

export interface SetupStep {
  title: string;
  detail: string;
  action: string;
  /** null while an earlier step has to be done first */
  to: string | null;
  done: boolean;
}

/** "How to get started" for new users: shown until every step is done. */
export default function GetStarted({ steps }: { steps: SetupStep[] }) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);

  function close() {
    setOpen(false);
    buttonRef.current?.focus();
  }

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const doneCount = steps.filter((s) => s.done).length;
  if (doneCount === steps.length) return null;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="start-open"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        How to get started
        <span>
          {doneCount} of {steps.length} done
        </span>
      </button>
      {open && (
        <div className="ask-overlay" onMouseDown={(e) => e.target === e.currentTarget && close()}>
          <div className="ask-dialog" role="dialog" aria-modal="true" aria-labelledby="start-title">
            <div className="ask-head">
              <h2 id="start-title">How to get started</h2>
              <button ref={closeRef} type="button" className="ask-close" aria-label="Close" onClick={close}>
                ×
              </button>
            </div>
            <p className="start-progress">
              {doneCount} of {steps.length} steps done
            </p>
            <ol className="start-steps">
              {steps.map((s, i) => (
                <li key={s.title} className={s.done ? "is-done" : undefined}>
                  <span className="start-mark" aria-hidden="true">
                    {s.done ? "✓" : i + 1}
                  </span>
                  <div className="start-text">
                    <strong>{s.title}</strong>
                    <span>{s.detail}</span>
                  </div>
                  {s.done ? (
                    <span className="start-done">Done</span>
                  ) : s.to === null ? (
                    <span className="start-later">After step {i}</span>
                  ) : (
                    <Link to={s.to} className="ask-chip start-link">
                      {s.action}
                    </Link>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </>
  );
}
