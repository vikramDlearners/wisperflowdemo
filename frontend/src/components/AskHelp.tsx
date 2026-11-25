import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import "../ask-help.css";
import { askHelp, ApiError } from "../api";
import { DESTINATIONS, isAskKey, matchAsk, type AskKey, type AskState } from "../lib/askHelp";

const EXAMPLES = ["I want to add an appointment", "View appointments", "Add a task", "Show medicines"];
const SUGGESTED: AskKey[] = ["appointments.view", "tasks.view", "medicines.view", "records.view", "members.view"];

function useOpenAsk() {
  const navigate = useNavigate();
  return (familyId: string, text: string, key: AskKey, tried: AskKey[]) => {
    const ask: AskState = { id: Date.now(), text, familyId, key, tried: [...tried, key] };
    navigate(DESTINATIONS[key].path(familyId), { state: { ask } });
  };
}

/** The page the backend (LLM) picks for this question, or a message to show when it cannot. */
async function askBackend(
  familyId: string,
  text: string,
  tried: AskKey[],
): Promise<{ key: AskKey } | { note: string }> {
  try {
    const r = await askHelp.ask(familyId, text, tried);
    if (isAskKey(r.destination) && !tried.includes(r.destination)) return { key: r.destination };
    return {
      note: r.available
        ? "I could not find a page for that. Try other words, or pick one:"
        : "I did not understand that, and smart help is not available right now. Try other words, or pick one:",
    };
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return { note: err.detail };
    return { note: "I could not check that right now. Try other words, or pick one:" };
  }
}

function Suggestions({ skip, onPick }: { skip: AskKey[]; onPick: (k: AskKey) => void }) {
  return (
    <div className="ask-chips">
      {SUGGESTED.filter((k) => !skip.includes(k)).map((k) => (
        <button key={k} type="button" className="ask-chip" onClick={() => onPick(k)}>
          {DESTINATIONS[k].label}
        </button>
      ))}
    </div>
  );
}

/** The "Ask for help" button and its dialog. */
export default function AskHelp({ familyId }: { familyId: string }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const run = useRef(0); // a reply that arrives after the dialog is closed must not open a page
  const openAsk = useOpenAsk();

  function close() {
    run.current += 1;
    setOpen(false);
    setBusy(false);
    setNote(null);
    buttonRef.current?.focus();
  }

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(
    () => () => {
      run.current += 1;
    },
    [],
  );

  async function submit(value: string) {
    const asked = value.trim();
    if (!asked || busy) return;
    const key = matchAsk(asked);
    if (key) {
      openAsk(familyId, asked, key, []);
      return;
    }
    const mine = ++run.current;
    setBusy(true);
    setNote(null);
    const result = await askBackend(familyId, asked, []);
    if (mine !== run.current) return;
    setBusy(false);
    if ("key" in result) openAsk(familyId, asked, result.key, []);
    else setNote(result.note);
  }

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="pp-btn pp-btn-ghost"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        <span aria-hidden="true">?</span> Ask for help
      </button>
      {open && (
        <div className="ask-overlay" onMouseDown={(e) => e.target === e.currentTarget && close()}>
          <div className="ask-dialog" role="dialog" aria-modal="true" aria-labelledby="ask-title">
            <div className="ask-head">
              <h2 id="ask-title">Ask for help</h2>
              <button type="button" className="ask-close" aria-label="Close" onClick={close}>
                ×
              </button>
            </div>
            <form
              className="ask-form"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                void submit(text);
              }}
            >
              <label htmlFor="ask-text">What would you like to do?</label>
              <div className="ask-row">
                <input
                  id="ask-text"
                  ref={inputRef}
                  value={text}
                  maxLength={500}
                  autoComplete="off"
                  placeholder="e.g. I want to add an appointment"
                  readOnly={busy}
                  onChange={(e) => {
                    setText(e.target.value);
                    setNote(null);
                  }}
                />
                <button type="submit" className="pp-btn" disabled={busy || !text.trim()}>
                  {busy ? "Thinking…" : "Go"}
                </button>
              </div>
            </form>
            <div role="status">{note && <p className="ask-note">{note}</p>}</div>
            {note ? (
              <Suggestions skip={[]} onPick={(k) => openAsk(familyId, text.trim(), k, [])} />
            ) : (
              <div className="ask-chips">
                {EXAMPLES.map((x) => (
                  <button key={x} type="button" className="ask-chip" disabled={busy} onClick={() => void submit(x)}>
                    {x}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

/** Shown on the page Ask for help opened, so a wrong guess can be corrected. */
export function AskHelpResult() {
  const location = useLocation();
  const ask = (location.state as { ask?: AskState } | null)?.ask ?? null;
  const [closedId, setClosedId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const current = useRef<number | null>(null);
  const openAsk = useOpenAsk();
  const id = ask?.id ?? null;
  current.current = id;

  useEffect(() => {
    setBusy(false);
    setNote(null);
  }, [id]);

  // It can cover a form's buttons, so it goes away unless the user is correcting the answer.
  useEffect(() => {
    if (id === null || busy || note) return;
    const timer = window.setTimeout(() => setClosedId(id), 15000);
    return () => window.clearTimeout(timer);
  }, [id, busy, note]);

  if (!ask || closedId === ask.id || !isAskKey(ask.key)) return null;

  async function wrong(a: AskState) {
    setBusy(true);
    const result = await askBackend(a.familyId, a.text, a.tried);
    if (current.current !== a.id) return;
    setBusy(false);
    if ("key" in result) openAsk(a.familyId, a.text, result.key, a.tried);
    else setNote(result.note);
  }

  return (
    <div className="ask-result" role="status">
      <div className="ask-result-row">
        <span>
          Opened <strong>{DESTINATIONS[ask.key].label}</strong> for “{ask.text}”
        </span>
        {!note && (
          <button type="button" className="ask-chip" disabled={busy} onClick={() => void wrong(ask)}>
            {busy ? "Thinking…" : "Not what I wanted"}
          </button>
        )}
        <button
          type="button"
          className="ask-close"
          aria-label="Close"
          onClick={() => {
            current.current = null;
            setClosedId(ask.id);
          }}
        >
          ×
        </button>
      </div>
      {note && (
        <>
          <p className="ask-note">{note}</p>
          <Suggestions skip={ask.tried} onPick={(k) => openAsk(ask.familyId, ask.text, k, ask.tried)} />
        </>
      )}
    </div>
  );
}
