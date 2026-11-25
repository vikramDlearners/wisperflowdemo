import { useEffect, useRef, useState, type ReactNode } from "react";

/** The "⋯" button that holds the less used page actions. */
export default function MoreActions({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="ov-more" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="pp-btn pp-btn-ghost ov-more-btn"
        aria-label="More actions"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span aria-hidden="true">⋯</span>
      </button>
      {open && (
        <div className="ov-more-list" onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  );
}
