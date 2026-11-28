import { useCallback, useEffect, useRef, useState } from "react";
import {
  askHelp,
  fetchPostMedia,
  getCard,
  getCircle,
  getMyHelp,
  getNudge,
  getPosts,
  getPrivacy,
  setPrivacy,
  type CardOut,
  type CirclePerson,
  type HelpKind,
  type HelpOut,
  type NudgeOut,
  type PostOut,
  type PrivacyOut,
} from "../parentApi";
import { circleStrings, type CircleStrings } from "../parentCircleStrings";
import { fill } from "../parentTodayStrings";

// The parent's people, under today's plan: what the family sent, one-tap calls, errands the family approves,
// the medical card for an ambulance or ER, what the family may see, and an opt-in fall watch.

const KINDS: HelpKind[] = ["groceries", "bill", "cab", "nurse", "physio", "other"];
const FALL_KEY = "carecircle.fallWatch";
const FALL_SECONDS = 30;

const tel = (n: string) => `tel:${n.replace(/[^\d+]/g, "")}`;

function PostMedia({ post }: { post: PostOut }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!post.media_url) return;
    let url: string | null = null;
    fetchPostMedia(post.media_url).then((u) => {
      url = u;
      setSrc(u);
    });
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [post.media_url]);
  if (!src) return null;
  return post.kind === "photo" ? <img src={src} alt="" className="pc-post-photo" /> : <audio controls src={src} />;
}

function CardView({ card, t, onClose }: { card: CardOut; t: CircleStrings; onClose: () => void }) {
  const row = (label: string, value: string | null | undefined, phone?: string | null) =>
    value ? (
      <div className="pc-card-row">
        <dt>{label}</dt>
        <dd>
          {value}
          {phone && (
            <>
              {" "}
              <a href={tel(phone)}>📞 {phone}</a>
            </>
          )}
        </dd>
      </div>
    ) : null;
  return (
    <div className="pc-emergency-backdrop" role="dialog" aria-modal="true" aria-labelledby="pc-card-title">
      <div className="pc-card">
        <h2 id="pc-card-title">
          {t.cardTitle}: {card.name}
        </h2>
        <dl>
          {row(t.blood, card.blood_group)}
          {row(t.allergies, card.allergies)}
          {row(t.medicines, card.medicines.join(", "))}
          {row(t.doctor, card.doctor ?? card.doctor_phone, card.doctor_phone)}
          {row(t.hospital, card.hospital)}
          {row(t.contact, card.emergency_contact?.name, card.emergency_contact?.phone)}
          {card.insurance &&
            row(
              t.insurance,
              [card.insurance.insurer, card.insurance.policy_number].filter(Boolean).join(" · "),
              card.insurance.helpline,
            )}
          {row("", card.notes)}
        </dl>
        <button type="button" className="pc-emergency-no" onClick={onClose}>
          {t.close}
        </button>
      </div>
    </div>
  );
}

// A free fall (almost no gravity felt) followed within a second by a hard knock. Phones vary, so this can
// miss falls and can fire on a dropped phone; the countdown lets the parent say they are fine.
function useFallWatch(on: boolean, onFall: () => void) {
  useEffect(() => {
    if (!on) return;
    let weightless = 0;
    const handler = (e: DeviceMotionEvent) => {
      const a = e.accelerationIncludingGravity;
      if (!a) return;
      const g = Math.hypot(a.x ?? 0, a.y ?? 0, a.z ?? 0);
      const now = Date.now();
      if (g < 3) weightless = now;
      else if (g > 25 && now - weightless < 1000) {
        weightless = 0;
        onFall();
      }
    };
    window.addEventListener("devicemotion", handler);
    return () => window.removeEventListener("devicemotion", handler);
  }, [on, onFall]);
}

export default function ParentCircle({
  language,
  profileId,
  onEmergency,
}: {
  language: string;
  profileId: string;
  onEmergency: () => void;
}) {
  const t = circleStrings(language);
  const [posts, setPosts] = useState<PostOut[]>([]);
  const [people, setPeople] = useState<CirclePerson[]>([]);
  const [help, setHelp] = useState<HelpOut[]>([]);
  const [nudge, setNudge] = useState<NudgeOut | null>(null);
  const [privacy, setPriv] = useState<PrivacyOut | null>(null);
  const [card, setCard] = useState<CardOut | null>(null);
  const [busy, setBusy] = useState<HelpKind | null>(null);
  const [failed, setFailed] = useState(false);
  const [fallOn, setFallOn] = useState(() => localStorage.getItem(FALL_KEY) === "1");
  const [noSensor, setNoSensor] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const emergencyRef = useRef(onEmergency);
  emergencyRef.current = onEmergency;

  useEffect(() => {
    const quiet = <T,>(p: Promise<T>, set: (v: T) => void) => p.then(set).catch(() => undefined);
    quiet(getPosts(), setPosts);
    quiet(getCircle(), setPeople);
    quiet(getMyHelp(), setHelp);
    quiet(getNudge(), setNudge);
    quiet(getPrivacy(), setPriv);
  }, [profileId]);

  useFallWatch(fallOn && countdown === null, useCallback(() => setCountdown(FALL_SECONDS), []));

  useEffect(() => {
    if (countdown === null) return;
    if (countdown <= 0) {
      setCountdown(null);
      emergencyRef.current();
      return;
    }
    const id = window.setTimeout(() => setCountdown((n) => (n === null ? null : n - 1)), 1000);
    return () => window.clearTimeout(id);
  }, [countdown]);

  async function ask(kind: HelpKind) {
    setBusy(kind);
    setFailed(false);
    try {
      const made = await askHelp(kind, null);
      setHelp((rows) => [made, ...rows.filter((r) => r.id !== made.id)]);
    } catch {
      setFailed(true);
    } finally {
      setBusy(null);
    }
  }

  async function toggle(key: keyof PrivacyOut, value: boolean) {
    try {
      setPriv(await setPrivacy({ [key]: value }));
    } catch {
      setFailed(true);
    }
  }

  async function toggleFall(value: boolean) {
    const DM = typeof DeviceMotionEvent === "undefined" ? null : DeviceMotionEvent;
    if (value && !DM) {
      setNoSensor(true);
      return;
    }
    // iPhones ask once before the page may read the motion sensor.
    const request = (DM as unknown as { requestPermission?: () => Promise<string> } | null)?.requestPermission;
    if (value && request && (await request()) !== "granted") {
      setNoSensor(true);
      return;
    }
    localStorage.setItem(FALL_KEY, value ? "1" : "0");
    setFallOn(value);
  }

  const nudgeText =
    nudge?.kind === "birthday"
      ? fill(t.birthdayToday, { name: nudge.name ?? "" })
      : nudge?.kind === "call"
        ? fill(t.nudgeCall, { name: nudge.name ?? "" })
        : nudge
          ? t.nudgeWalk
          : null;
  const unseen = posts.some((p) => !p.seen_at);
  const open = help.filter((h) => h.status === "asked" || h.status === "approved");

  return (
    <>
      {countdown !== null && (
        <div className="pc-emergency-backdrop" role="alertdialog" aria-modal="true" aria-labelledby="pc-fall-title">
          <div className="pc-emergency">
            <h2 id="pc-fall-title" className="pc-emergency-title">
              {fill(t.fallAsk, { n: countdown })}
            </h2>
            <button type="button" className="pc-emergency-no" onClick={() => setCountdown(null)} autoFocus>
              {t.fallOk}
            </button>
          </div>
        </div>
      )}
      {card && <CardView card={card} t={t} onClose={() => setCard(null)} />}

      <details className="pc-today pc-circle" open={unseen || nudge?.kind === "birthday"}>
        <summary>
          <span aria-hidden="true">👪</span> {t.title}
        </summary>
        <div className="pc-today-body">
          {nudgeText && (
            <p className="pc-circle-nudge">
              {nudgeText}{" "}
              {nudge?.phone && (
                <a className="pc-fine-btn" href={tel(nudge.phone)}>
                  📞 {nudge.name}
                </a>
              )}
            </p>
          )}

          {posts.length > 0 && (
            <section>
              <h3>{t.fromFamily}</h3>
              <ul className="pc-posts">
                {posts.map((p) => (
                  <li key={p.id}>
                    <strong>{p.author}</strong> {p.text}
                    <PostMedia post={p} />
                  </li>
                ))}
              </ul>
            </section>
          )}

          {people.length > 0 && (
            <section>
              <h3>{t.callTitle}</h3>
              <div className="pc-circle-calls">
                {people.map((p) => (
                  <a key={`${p.name}-${p.phone}`} className="pc-call-btn" href={tel(p.phone)}>
                    <span aria-hidden="true">📞</span> {p.name}
                    <span className="pc-call-number">{p.phone}</span>
                  </a>
                ))}
              </div>
            </section>
          )}

          <section>
            <h3>{t.helpTitle}</h3>
            <div className="pc-circle-help">
              {KINDS.map((k) => (
                <button key={k} type="button" className="pc-fine-btn" disabled={busy !== null} onClick={() => void ask(k)}>
                  {t.kinds[k]}
                </button>
              ))}
            </div>
            {open.length > 0 && (
              <ul>
                {open.map((h) => (
                  <li key={h.id} role="status">
                    {t.kinds[h.kind]}: {t.status[h.status]}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <button
            type="button"
            className="pc-fine-btn"
            onClick={() => getCard().then(setCard).catch(() => setFailed(true))}
          >
            🩺 {t.cardBtn}
          </button>

          {privacy && (
            <section>
              <h3>{t.privacyTitle}</h3>
              {(
                [
                  ["share_words", t.shareWords],
                  ["share_chats", t.shareChats],
                  ["video_auto_answer", t.autoAnswer],
                ] as [keyof PrivacyOut, string][]
              ).map(([key, label]) => (
                <label key={key} className="pc-circle-toggle">
                  <input type="checkbox" checked={privacy[key]} onChange={(e) => void toggle(key, e.target.checked)} />
                  {label}
                </label>
              ))}
              <label className="pc-circle-toggle">
                <input type="checkbox" checked={fallOn} onChange={(e) => void toggleFall(e.target.checked)} />
                {t.fallOn}
              </label>
              {noSensor && <p role="alert">{t.fallNoSensor}</p>}
            </section>
          )}
          {failed && <p role="alert">{t.failed}</p>}
        </div>
      </details>
    </>
  );
}
