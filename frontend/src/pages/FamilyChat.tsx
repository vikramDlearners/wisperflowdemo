import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import "../ask-help.css";
import "../family-chat.css";
import { ApiError, auth, familyChat, type FamilyChatTurn } from "../api";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { DESTINATIONS, isAskKey, matchAsk, type AskKey } from "../lib/askHelp";

// Chat: the first page a family member sees after signing in. Conversations are kept in this browser only.

interface Message extends FamilyChatTurn {
  destination?: AskKey | null;
}

interface Conversation {
  id: string;
  title: string;
  messages: Message[];
}

const MAX_TEXT = 1000;
const MAX_HISTORY = 12;
const MAX_CONVERSATIONS = 30;
const SUGGESTIONS = [
  "How are things today?",
  "Were today's medicines taken?",
  "Which medicines need a refill?",
  "What are the upcoming appointments?",
  "Show my open tasks",
];

const storageKey = (userId: string, familyId: string) => `carecircle_chat:${userId}:${familyId}`;

function load(key: string): Conversation[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter(
      (c): c is Conversation =>
        typeof c?.id === "string" &&
        typeof c.title === "string" &&
        Array.isArray(c.messages) &&
        c.messages.every((m: Message) => typeof m?.text === "string" && (m.role === "user" || m.role === "assistant")),
    );
  } catch {
    return [];
  }
}

function save(key: string, conversations: Conversation[]) {
  try {
    localStorage.setItem(key, JSON.stringify(conversations));
  } catch {
    // Storage is full or blocked: the chat still works until the page is closed.
  }
}

/** "Add a task" needs a page, not an answer: the chat itself changes nothing. */
function pageToOpen(text: string): AskKey | null {
  const key = matchAsk(text);
  return key && (key.endsWith(".add") || key === "prescription.scan") ? key : null;
}

export default function FamilyChat({ familyId }: { familyId: string }) {
  const [user, setUser] = useState<{ id: string; name: string } | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<{ id: string; text: string } | null>(null);
  const [userFailed, setUserFailed] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const all = useRef<Conversation[]>([]);
  const mounted = useRef(true);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const key = user && storageKey(user.id, familyId);
  const open = conversations.find((c) => c.id === openId) ?? null;
  const messages = open?.messages ?? [];

  useEffect(() => {
    mounted.current = true;
    auth
      .me()
      .then((me) => {
        if (!mounted.current) return;
        all.current = load(storageKey(me.id, familyId));
        setConversations(all.current);
        setUser({ id: me.id, name: me.display_name });
      })
      .catch(() => mounted.current && setUserFailed(true));
    return () => {
      mounted.current = false;
    };
  }, [familyId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [openId, messages.length, busyId, error]);

  useEffect(() => {
    const box = inputRef.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 180)}px`;
  }, [text]);

  function update(next: Conversation[]) {
    all.current = next.slice(0, MAX_CONVERSATIONS);
    setConversations(all.current);
    if (key) save(key, all.current);
  }

  /** Adds to a conversation and moves it to the top. Does nothing when it was deleted meanwhile. */
  function append(id: string, message: Message) {
    const found = all.current.find((c) => c.id === id);
    if (!found) return;
    const changed = { ...found, messages: [...found.messages, message] };
    update([changed, ...all.current.filter((c) => c.id !== id)]);
  }

  async function reply(id: string) {
    const turns = all.current.find((c) => c.id === id)?.messages ?? [];
    const question = turns[turns.length - 1];
    if (!question) return;
    setError(null);

    const page = pageToOpen(question.text);
    if (page) {
      append(id, { role: "assistant", text: "You can do that here:", destination: page });
      return;
    }

    setBusyId(id);
    try {
      const history = turns
        .slice(0, -1)
        .slice(-MAX_HISTORY)
        .map(({ role, text: said }) => ({ role, text: said.slice(0, 4000) }));
      const out = await familyChat.send(familyId, question.text, history);
      if (!mounted.current) return;
      let destination = isAskKey(out.destination) ? out.destination : null;
      if (!destination && out.source === "rules") destination = matchAsk(question.text);
      append(id, { role: "assistant", text: out.reply, destination });
    } catch (err) {
      if (!mounted.current) return;
      const known = err instanceof ApiError && err.status < 500 && err.status !== 422;
      setError({ id, text: known ? err.detail : "I could not answer just now. Please try again." });
    } finally {
      if (mounted.current) setBusyId(null);
    }
  }

  function send(value: string) {
    const said = value.trim();
    if (!said || busyId || !user) return;
    let id = openId;
    if (!id || !all.current.some((c) => c.id === id)) {
      id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      update([{ id, title: said.slice(0, 60), messages: [] }, ...all.current]);
      setOpenId(id);
    }
    append(id, { role: "user", text: said });
    setText("");
    void reply(id);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;
    e.preventDefault();
    send(text);
  }

  function show(id: string | null) {
    setOpenId(id);
    setShowHistory(false);
    inputRef.current?.focus();
  }

  function remove(c: Conversation) {
    if (!window.confirm(`Delete the chat "${c.title}"?`)) return;
    update(all.current.filter((x) => x.id !== c.id));
    if (c.id === openId) setOpenId(null);
  }

  const last = messages[messages.length - 1];
  const busy = openId !== null && busyId === openId;
  // The last question has no answer: it failed, or the page was closed before the answer came.
  const unanswered = last?.role === "user" && !busy;

  return (
    <WorkspaceLayout familyId={familyId} current="chat" title="Chat">
      <div className={`fc${showHistory ? " fc-history-open" : ""}`}>
        <aside className="fc-history" id="fc-history" aria-label="Chat history">
          <button type="button" className="fc-new" onClick={() => show(null)}>
            <span aria-hidden="true">＋</span> New chat
          </button>
          <ul>
            {conversations.map((c) => (
              <li key={c.id} className={c.id === openId ? "is-open" : undefined}>
                <button
                  type="button"
                  className="fc-title"
                  title={c.title}
                  aria-current={c.id === openId ? "true" : undefined}
                  onClick={() => show(c.id)}
                >
                  {c.title}
                </button>
                <button type="button" className="fc-delete" aria-label={`Delete chat: ${c.title}`} onClick={() => remove(c)}>
                  ×
                </button>
              </li>
            ))}
          </ul>
          <p className="fc-note">{conversations.length ? "Saved on this device only." : "Your chats will show here."}</p>
        </aside>

        <section className="fc-main" aria-label="Chat">
          <div className="fc-bar">
            <button
              type="button"
              className="ask-chip"
              aria-expanded={showHistory}
              aria-controls="fc-history"
              onClick={() => setShowHistory((s) => !s)}
            >
              {showHistory ? "Back to chat" : "History"}
            </button>
            <button type="button" className="ask-chip" onClick={() => show(null)}>
              New chat
            </button>
          </div>

          <div className="fc-scroll">
            {messages.length === 0 ? (
              <div className="fc-welcome">
                <h1>Hello{user ? `, ${user.name.trim().split(/\s+/)[0]}` : ""}. How can I help?</h1>
                <p>Ask about medicines, appointments, tasks or how your parent is doing.</p>
                <div className="fc-suggestions">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} type="button" className="ask-chip" disabled={!user || !!busyId} onClick={() => send(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="fc-thread" role="log" aria-live="polite">
                {messages.map((m, i) => (
                  <div key={i} className={`fc-msg is-${m.role}`}>
                    <span className="fc-sr">{m.role === "user" ? "You:" : "CareCircle:"}</span>
                    <p>{m.text}</p>
                    {isAskKey(m.destination) && (
                      <Link className="ask-chip fc-link" to={DESTINATIONS[m.destination].path(familyId)}>
                        Open {DESTINATIONS[m.destination].label}
                      </Link>
                    )}
                  </div>
                ))}
                {busy && (
                  <div className="fc-msg is-assistant">
                    <p className="fc-thinking">Thinking…</p>
                  </div>
                )}
                {unanswered && openId && (
                  <div className="fc-msg is-assistant" role="alert">
                    <p>{error?.id === openId ? error.text : "This question was not answered."}</p>
                    <button type="button" className="ask-chip fc-link" disabled={!!busyId} onClick={() => void reply(openId)}>
                      Try again
                    </button>
                  </div>
                )}
                <div ref={endRef} />
              </div>
            )}
          </div>

          <form
            className="fc-composer"
            onSubmit={(e) => {
              e.preventDefault();
              send(text);
            }}
          >
            {userFailed && <p role="alert">Could not load your account. Reload the page to try again.</p>}
            <div className="fc-box">
              <textarea
                ref={inputRef}
                rows={1}
                value={text}
                maxLength={MAX_TEXT}
                placeholder="Ask anything about your parent's care"
                aria-label="Your message"
                onChange={(e) => setText(e.target.value)}
                onKeyDown={onKeyDown}
              />
              <button type="submit" aria-label="Send" disabled={!text.trim() || !!busyId || !user}>
                ↑
              </button>
            </div>
            <p>Not for emergencies or medical advice. This chat alerts no one.</p>
          </form>
        </section>
      </div>
    </WorkspaceLayout>
  );
}
