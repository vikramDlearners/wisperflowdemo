import { useCallback, useEffect, useRef, useState } from "react";
import "../parent-notes.css";
import { ApiError } from "../api";
import {
  createParentNote,
  deleteParentNote,
  getNotePeople,
  getParentNotes,
  type NotePerson,
  type ParentNote,
} from "../parentApi";
import { notesStrings, type NotesStrings } from "../parentNotesStrings";

// "My notes" for the parent chat: write a note, then answer one question at a time —
// when to be reminded, and who should get it (me by default). A note for someone else
// becomes their task; the parent is then asked whether to send that person a reminder too.

type Step = "list" | "text" | "when" | "who" | "remindOther";
type When = "none" | "1h" | "today6" | "tomorrow6" | "tomorrow9" | "custom";

interface Draft {
  text: string;
  when: When;
  custom: string; // datetime-local value
  who: string | null; // null = me
}

const EMPTY: Draft = { text: "", when: "none", custom: "", who: null };

function at(daysAhead: number, hour: number): Date {
  const d = new Date();
  d.setDate(d.getDate() + daysAhead);
  d.setHours(hour, 0, 0, 0);
  return d;
}

function remindDate(draft: Draft): Date | null {
  switch (draft.when) {
    case "1h":
      return new Date(Date.now() + 60 * 60 * 1000);
    case "today6":
      return at(0, 18);
    case "tomorrow6":
      return at(1, 18);
    case "tomorrow9":
      return at(1, 9);
    case "custom":
      return draft.custom ? new Date(draft.custom) : null;
    default:
      return null;
  }
}

function formatWhen(iso: string, t: NotesStrings): string {
  const d = new Date(iso);
  const time = d.toLocaleTimeString(t.locale, { hour: "numeric", minute: "2-digit" });
  const today = new Date();
  const tomorrow = new Date();
  tomorrow.setDate(today.getDate() + 1);
  if (d.toDateString() === today.toDateString()) return `${t.today} ${time}`;
  if (d.toDateString() === tomorrow.toDateString()) return `${t.tomorrow} ${time}`;
  return `${d.toLocaleDateString(t.locale, { weekday: "short", day: "numeric", month: "short" })} ${time}`;
}

function localInputMin(): string {
  const d = new Date(Date.now() + 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const errorText = (err: unknown) => (err instanceof ApiError ? err.detail : null);

interface ParentNotesProps {
  language: string;
  onClose: () => void;
}

export default function ParentNotes({ language, onClose }: ParentNotesProps) {
  const t = notesStrings(language);
  const [notes, setNotes] = useState<ParentNote[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [people, setPeople] = useState<NotePerson[] | null>(null);
  const [step, setStep] = useState<Step>("list");
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const load = useCallback(async () => {
    setLoadError(false);
    try {
      setNotes(await getParentNotes());
    } catch {
      setLoadError(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Move focus to each new question, so screen readers and keyboards follow along.
  useEffect(() => {
    headingRef.current?.focus();
  }, [step]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && step === "list") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [step, onClose]);

  function start() {
    setDraft(EMPTY);
    setError(null);
    setSaved(null);
    setStep("text");
  }

  async function toWho() {
    setError(null);
    if (draft.when === "custom") {
      const d = remindDate(draft);
      if (!d || d.getTime() <= Date.now()) {
        setError(t.timeInPast);
        return;
      }
    }
    let list = people;
    if (list === null) {
      try {
        list = await getNotePeople();
      } catch {
        list = [];
      }
      setPeople(list);
    }
    // With nobody else in the family, the note can only be for the parent: save it straight away.
    if (list.length === 0) {
      await save({ ...draft, who: null }, false);
      return;
    }
    setStep("who");
  }

  async function save(d: Draft, sendReminder: boolean) {
    setSaving(true);
    setError(null);
    const when = remindDate(d);
    try {
      const note = await createParentNote({
        text: d.text.trim(),
        remind_at: when ? when.toISOString() : null,
        remind_user_id: d.who,
        send_reminder: d.who ? sendReminder : false,
      });
      const name = note.remind_user_name ?? "";
      const whenText = note.remind_at ? formatWhen(note.remind_at, t) : "";
      setSaved(
        !note.remind_user_id
          ? note.remind_at
            ? t.savedForMe(whenText)
            : t.savedPlain
          : !note.send_reminder
            ? t.savedTask(name)
            : note.remind_at
              ? t.savedTaskReminder(name, whenText)
              : t.savedTaskReminderNow(name),
      );
      setNotes((prev) => [note, ...(prev ?? [])]);
      setStep("list");
    } catch (err) {
      setError(errorText(err) ?? t.loadFailed);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    setConfirmId(null);
    setSaved(null);
    try {
      await deleteParentNote(id);
      setNotes((prev) => (prev ?? []).filter((n) => n.id !== id));
    } catch {
      setError(t.loadFailed);
    }
  }

  const person = draft.who ? people?.find((p) => p.user_id === draft.who) : undefined;
  const lateToday = new Date().getHours() >= 17;

  const whenOptions: { value: When; label: string }[] = [
    { value: "none", label: t.noReminder },
    { value: "1h", label: t.inOneHour },
    lateToday ? { value: "tomorrow6", label: t.tomorrowAt6 } : { value: "today6", label: t.todayAt6 },
    { value: "tomorrow9", label: t.tomorrowAt9 },
    { value: "custom", label: t.pickTime },
  ];

  return (
    <div className="pn" role="dialog" aria-modal="true" aria-labelledby="pn-title">
      <div className="pn-inner">
        <header className="pn-head">
          <button type="button" className="pn-back" onClick={step === "list" ? onClose : () => setStep("list")}>
            ← {step === "list" ? t.close : t.cancel}
          </button>
        </header>

        {step === "list" && (
          <section>
            <h2 id="pn-title" ref={headingRef} tabIndex={-1} className="pn-title">
              {t.myNotes}
            </h2>
            {saved && (
              <p role="status" className="pn-saved">
                ✓ {saved}
              </p>
            )}
            {error && <p role="alert" className="pn-error">{error}</p>}
            <button type="button" className="pn-primary pn-write" onClick={start}>
              {t.writeNote}
            </button>

            {loadError ? (
              <div className="pn-empty">
                <p>{t.loadFailed}</p>
                <button type="button" className="pn-secondary" onClick={() => void load()}>
                  {t.tryAgain}
                </button>
              </div>
            ) : notes === null ? (
              <p className="pn-muted">…</p>
            ) : notes.length === 0 ? (
              <p className="pn-empty">{t.empty}</p>
            ) : (
              <ul className="pn-list">
                {notes.map((n) => (
                  <li key={n.id} className="pn-note">
                    <p className="pn-note-text">{n.text}</p>
                    <div className="pn-meta">
                      <span className="pn-tag">
                        {n.remind_user_id ? t.taskForShort(n.remind_user_name ?? "") : t.forYou}
                      </span>
                      <span className="pn-when">
                        {n.remind_at
                          ? n.reminded && (!n.remind_user_id || n.send_reminder)
                            ? `✓ ${t.reminderSent}`
                            : `⏰ ${t.reminderAt(formatWhen(n.remind_at, t))}`
                          : n.remind_user_id && n.send_reminder
                            ? `✓ ${t.reminderSent}`
                            : t.noReminderLabel}
                      </span>
                    </div>
                    {confirmId === n.id ? (
                      <div className="pn-confirm" role="alertdialog" aria-label={t.confirmRemove}>
                        <span>{t.confirmRemove}</span>
                        <div className="pn-row">
                          <button type="button" className="pn-secondary" onClick={() => setConfirmId(null)}>
                            {t.keep}
                          </button>
                          <button type="button" className="pn-danger" onClick={() => void remove(n.id)}>
                            {t.yesRemove}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button type="button" className="pn-remove" onClick={() => setConfirmId(n.id)}>
                        {t.remove}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {step === "text" && (
          <section>
            <h2 id="pn-title" ref={headingRef} tabIndex={-1} className="pn-q">
              {t.whatToNote}
            </h2>
            <textarea
              className="pn-textarea"
              rows={4}
              maxLength={1000}
              placeholder={t.placeholder}
              aria-label={t.whatToNote}
              value={draft.text}
              onChange={(e) => setDraft({ ...draft, text: e.target.value })}
            />
            <p className="pn-label">{t.examplesLabel}</p>
            <div className="pn-examples">
              {t.examples.map((ex) => (
                <button key={ex} type="button" className="pn-example" onClick={() => setDraft({ ...draft, text: ex })}>
                  {ex}
                </button>
              ))}
            </div>
            <div className="pn-nav">
              <button type="button" className="pn-primary" disabled={!draft.text.trim()} onClick={() => setStep("when")}>
                {t.next}
              </button>
            </div>
          </section>
        )}

        {step === "when" && (
          <section>
            <h2 id="pn-title" ref={headingRef} tabIndex={-1} className="pn-q">
              {t.whenRemind}
            </h2>
            <blockquote className="pn-quote">{draft.text}</blockquote>
            <div className="pn-choices" role="radiogroup" aria-label={t.whenRemind}>
              {whenOptions.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  role="radio"
                  aria-checked={draft.when === o.value}
                  className={`pn-choice${draft.when === o.value ? " is-on" : ""}`}
                  onClick={() => {
                    setError(null);
                    setDraft({ ...draft, when: o.value });
                  }}
                >
                  {o.label}
                </button>
              ))}
            </div>
            {draft.when === "custom" && (
              <input
                type="datetime-local"
                className="pn-datetime"
                aria-label={t.pickTime}
                min={localInputMin()}
                value={draft.custom}
                onChange={(e) => setDraft({ ...draft, custom: e.target.value })}
              />
            )}
            {error && <p role="alert" className="pn-error">{error}</p>}
            <div className="pn-nav">
              <button type="button" className="pn-secondary" onClick={() => setStep("text")}>
                {t.back}
              </button>
              <button
                type="button"
                className="pn-primary"
                disabled={saving || (draft.when === "custom" && !draft.custom)}
                onClick={() => void toWho()}
              >
                {saving ? t.saving : t.next}
              </button>
            </div>
          </section>
        )}

        {step === "who" && (
          <section>
            <h2 id="pn-title" ref={headingRef} tabIndex={-1} className="pn-q">
              {draft.when === "none" ? t.whoFor : t.whoRemind}
            </h2>
            <div className="pn-choices" role="radiogroup" aria-label={draft.when === "none" ? t.whoFor : t.whoRemind}>
              <button
                type="button"
                role="radio"
                aria-checked={draft.who === null}
                className={`pn-choice pn-person${draft.who === null ? " is-on" : ""}`}
                onClick={() => setDraft({ ...draft, who: null })}
              >
                <strong>{t.me}</strong>
                <span>{t.meHint}</span>
              </button>
              {(people ?? []).map((p) => (
                <button
                  key={p.user_id}
                  type="button"
                  role="radio"
                  aria-checked={draft.who === p.user_id}
                  className={`pn-choice pn-person${draft.who === p.user_id ? " is-on" : ""}`}
                  onClick={() => setDraft({ ...draft, who: p.user_id })}
                >
                  <strong>{p.display_name}</strong>
                  {p.relationship && <span>{p.relationship}</span>}
                </button>
              ))}
            </div>
            {error && <p role="alert" className="pn-error">{error}</p>}
            <div className="pn-nav">
              <button type="button" className="pn-secondary" onClick={() => setStep("when")}>
                {t.back}
              </button>
              {draft.who === null ? (
                <button type="button" className="pn-primary" disabled={saving} onClick={() => void save(draft, false)}>
                  {saving ? t.saving : t.save}
                </button>
              ) : (
                <button type="button" className="pn-primary" onClick={() => setStep("remindOther")}>
                  {t.next}
                </button>
              )}
            </div>
          </section>
        )}

        {step === "remindOther" && person && (
          <section>
            <h2 id="pn-title" ref={headingRef} tabIndex={-1} className="pn-q">
              {t.alsoRemind(person.display_name)}
            </h2>
            <p className="pn-info">{t.taskFor(person.display_name)}</p>
            {error && <p role="alert" className="pn-error">{error}</p>}
            <div className="pn-stack">
              <button type="button" className="pn-primary" disabled={saving} onClick={() => void save(draft, true)}>
                {saving ? t.saving : t.yesRemind}
              </button>
              <button type="button" className="pn-secondary" disabled={saving} onClick={() => void save(draft, false)}>
                {t.noJustTask}
              </button>
              <button type="button" className="pn-link" disabled={saving} onClick={() => setStep("who")}>
                {t.back}
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
