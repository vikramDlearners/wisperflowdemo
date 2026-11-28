import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";
import "../ask-help.css";
import "../family-chat.css";
import {
  ApiError,
  auth,
  familyChat,
  type FamilyChatConversationOut,
  type FamilyChatTurn,
  type MonthlyAnalysis,
} from "../api";
import MonthlyAnalysisCard from "../components/MonthlyAnalysisCard";
import WorkspaceLayout from "../components/WorkspaceLayout";
import { DESTINATIONS, isAskKey, matchAsk, type AskKey } from "../lib/askHelp";

// Chat: the first page a family member sees after signing in. Each member's conversations are saved in the
// database (only they can see them), so they follow them to any device.

interface Message extends FamilyChatTurn {
  destination?: AskKey | null;
  card?: MonthlyAnalysis | null;
}

/** A question waiting for its answer, or whose answer failed (shown with "Try again"). Not saved yet. */
interface Pending {
  conversationId: string | null; // null: it starts a new chat
  text: string;
}

const MAX_TEXT = 1000;
const SUGGESTIONS = [
  "How are things today?",
  "Give me last month's analysis",
  "Were today's medicines taken?",
  "Which medicines need a refill?",
  "What are the upcoming appointments?",
  "Show my open tasks",
];

// Where chats were kept in this browser before they were saved in the database.
const oldStorageKey = (userId: string, familyId: string) => `carecircle_chat:${userId}:${familyId}`;

interface OldConversation {
  title: string;
  messages: Message[];
}

function loadOld(key: string): OldConversation[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter(
      (c): c is OldConversation =>
        typeof c?.title === "string" &&
        Array.isArray(c.messages) &&
        c.messages.every((m: Message) => typeof m?.text === "string" && (m.role === "user" || m.role === "assistant")),
    );
  } catch {
    return [];
  }
}

/** "Give me last month's analysis" (also "monthly report", "recap"): answered with the analysis card. */
const ANALYSIS = /\b(?:analys[ie]s|analy[sz]e|analytics|recap|monthly\s+(?:report|summary|review))\b/i;

/** "Add a task" needs a page, not an answer: the chat itself changes nothing. */
function pageToOpen(text: string): AskKey | null {
  if (ANALYSIS.test(text)) return null;
  const key = matchAsk(text);
  return key && (key.endsWith(".add") || key === "prescription.scan") ? key : null;
}

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError && err.status < 500 && err.status !== 422 ? err.detail : fallback;
}

export default function FamilyChat({ familyId }: { familyId: string }) {
  const [user, setUser] = useState<{ id: string; name: string } | null>(null);
  const [conversations, setConversations] = useState<FamilyChatConversationOut[]>([]);
  const [threads, setThreads] = useState<Record<string, Message[]>>({});
  const [openId, setOpenId] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);
  const [userFailed, setUserFailed] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const mounted = useRef(true);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const saved = openId ? threads[openId] ?? [] : [];
  const waiting = pending && pending.conversationId === openId ? pending : null;
  const messages: Message[] = waiting ? [...saved, { role: "user", text: waiting.text }] : saved;

  // Sign-in, then: copy any chats kept in this browser into the database (once), and list the saved chats.
  useEffect(() => {
    mounted.current = true;
    (async () => {
      let me;
      try {
        me = await auth.me();
      } catch {
        if (mounted.current) setUserFailed(true);
        return;
      }
      if (!mounted.current) return;
      setUser({ id: me.id, name: me.display_name });
      const key = oldStorageKey(me.id, familyId);
      const old = loadOld(key);
      if (old.length) {
        try {
          await familyChat.importChats(
            familyId,
            old.map((c) => ({
              title: c.title,
              messages: c.messages.map((m) => ({ role: m.role, text: m.text, destination: m.destination ?? null })),
            })),
          );
          localStorage.removeItem(key);
        } catch {
          // Kept in the browser; tried again next time the page opens.
        }
      }
      try {
        const list = await familyChat.list(familyId);
        if (mounted.current) setConversations(list);
      } catch (err) {
        if (mounted.current) setLoadError(errorText(err, "Could not load your saved chats."));
      }
    })();
    return () => {
      mounted.current = false;
    };
  }, [familyId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [openId, messages.length, busy, error]);

  useEffect(() => {
    const box = inputRef.current;
    if (!box) return;
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 180)}px`;
  }, [text]);

  /** Adds a saved exchange to its conversation and moves that conversation to the top of the list. */
  function addSaved(conversationId: string, title: string, added: Message[]) {
    setThreads((t) => ({ ...t, [conversationId]: [...(t[conversationId] ?? []), ...added] }));
    setConversations((list) => {
      const found = list.find((c) => c.id === conversationId);
      const row: FamilyChatConversationOut = found
        ? { ...found, updated_at: new Date().toISOString(), message_count: found.message_count + added.length }
        : { id: conversationId, title, updated_at: new Date().toISOString(), message_count: added.length };
      return [row, ...list.filter((c) => c.id !== conversationId)];
    });
  }

  /** Drops a chat that no longer exists on the server from the list and the page. */
  function forget(conversationId: string) {
    setConversations((list) => list.filter((c) => c.id !== conversationId));
    setThreads((t) => {
      const next = { ...t };
      delete next[conversationId];
      return next;
    });
  }

  async function ask(question: string, conversationId: string | null) {
    setPending({ conversationId, text: question });
    setError(null);
    setBusy(true);
    const answerIn = async (chatId: string | null): Promise<{ id: string; answer: Message }> => {
      const page = pageToOpen(question);
      if (page) {
        const reply = "You can do that here:";
        const saved = await familyChat.log(familyId, { text: question, reply, destination: page, conversation_id: chatId });
        return { id: saved.conversation_id, answer: { role: "assistant", text: reply, destination: page } };
      }
      const out = await familyChat.send(familyId, question, chatId);
      const card = out.card ?? null;
      let destination = isAskKey(out.destination) ? out.destination : null;
      if (!destination && !card && out.source === "rules") destination = matchAsk(question);
      return { id: out.conversation_id, answer: { role: "assistant", text: out.reply, destination, card } };
    };
    try {
      let result;
      try {
        result = await answerIn(conversationId);
      } catch (err) {
        // The open chat was deleted (e.g. from another tab or device): ask again in a new chat.
        if (!(conversationId && err instanceof ApiError && err.status === 404)) throw err;
        forget(conversationId);
        result = await answerIn(null);
      }
      const { id, answer } = result;
      if (!mounted.current) return;
      addSaved(id, question.slice(0, 60), [{ role: "user", text: question }, answer]);
      setPending(null);
      // A new chat gets its id once saved; stay on it unless another chat was opened meanwhile.
      setOpenId((current) => (current === conversationId ? id : current));
    } catch (err) {
      if (mounted.current) setError(errorText(err, "I could not answer just now. Please try again."));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  function send(value: string) {
    const said = value.trim();
    if (!said || busy || !user) return;
    setText("");
    void ask(said, openId);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;
    e.preventDefault();
    send(text);
  }

  async function show(id: string | null) {
    setOpenId(id);
    setShowHistory(false);
    setError(null);
    if (pending && !busy && pending.conversationId !== id) setPending(null); // a failed question elsewhere
    inputRef.current?.focus();
    if (id && !threads[id]) {
      setOpening(true);
      try {
        const convo = await familyChat.get(familyId, id);
        if (!mounted.current) return;
        setThreads((t) => ({
          ...t,
          [id]: convo.messages.map((m) => ({
            role: m.role,
            text: m.text,
            destination: isAskKey(m.destination) ? m.destination : null,
            card: m.card ?? null,
          })),
        }));
      } catch (err) {
        if (mounted.current) setError(errorText(err, "Could not open this chat."));
      } finally {
        if (mounted.current) setOpening(false);
      }
    }
  }

  async function remove(c: FamilyChatConversationOut) {
    if (!window.confirm(`Delete the chat "${c.title}"?`)) return;
    try {
      await familyChat.remove(familyId, c.id);
      setConversations((list) => list.filter((x) => x.id !== c.id));
      setThreads((t) => {
        const next = { ...t };
        delete next[c.id];
        return next;
      });
      if (c.id === openId) setOpenId(null);
    } catch (err) {
      setError(errorText(err, "Could not delete this chat."));
    }
  }

  const unanswered = waiting !== null && !busy;

  return (
    <WorkspaceLayout familyId={familyId} current="chat" title="Chat">
      <div className={`fc${showHistory ? " fc-history-open" : ""}`}>
        <aside className="fc-history" id="fc-history" aria-label="Chat history">
          <button type="button" className="fc-new" onClick={() => void show(null)}>
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
                  onClick={() => void show(c.id)}
                >
                  {c.title}
                </button>
                <button
                  type="button"
                  className="fc-delete"
                  aria-label={`Delete chat: ${c.title}`}
                  onClick={() => void remove(c)}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          {loadError && (
            <p className="fc-note" role="alert">
              {loadError}
            </p>
          )}
          <p className="fc-note">
            {conversations.length ? "Saved to your account. Only you can see your chats." : "Your chats will show here."}
          </p>
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
            <button type="button" className="ask-chip" onClick={() => void show(null)}>
              New chat
            </button>
          </div>

          <div className="fc-scroll">
            {opening && messages.length === 0 ? (
              <p className="fc-thinking" role="status">
                Opening chat…
              </p>
            ) : messages.length === 0 ? (
              <div className="fc-welcome">
                <h1>Hello{user ? `, ${user.name.trim().split(/\s+/)[0]}` : ""}. How can I help?</h1>
                <p>Ask about medicines, appointments, tasks or how your parent is doing.</p>
                <div className="fc-suggestions">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} type="button" className="ask-chip" disabled={!user || busy} onClick={() => send(s)}>
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
                    {m.card?.kind === "monthly_analysis" && <MonthlyAnalysisCard data={m.card} />}
                    {isAskKey(m.destination) && (
                      <Link className="ask-chip fc-link" to={DESTINATIONS[m.destination].path(familyId)}>
                        Open {DESTINATIONS[m.destination].label}
                      </Link>
                    )}
                  </div>
                ))}
                {busy && waiting && (
                  <div className="fc-msg is-assistant">
                    <p className="fc-thinking">Thinking…</p>
                  </div>
                )}
                {unanswered && waiting && (
                  <div className="fc-msg is-assistant" role="alert">
                    <p>{error ?? "This question was not answered."}</p>
                    <button
                      type="button"
                      className="ask-chip fc-link"
                      disabled={busy}
                      onClick={() => void ask(waiting.text, waiting.conversationId)}
                    >
                      Try again
                    </button>
                  </div>
                )}
                {!waiting && error && (
                  <div className="fc-msg is-assistant" role="alert">
                    <p>{error}</p>
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
              <button type="submit" aria-label="Send" disabled={!text.trim() || busy || !user}>
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
