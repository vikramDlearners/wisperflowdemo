import { useCallback, useEffect, useState } from "react";
import { getFine, sendFine, type FineOut } from "../parentApi";
import { todayStrings } from "../parentTodayStrings";

// The big "I'm fine" button at the top of the parent chat. One tap a day tells the family all is well.
// After 11:00 the server asks the parent (asked=true) before it tells the family, so the button then
// says "Are you OK?". Checked again every 5 minutes while the chat is open.

export default function ParentFine({ language, profileId }: { language: string; profileId: string }) {
  const t = todayStrings(language);
  const [fine, setFine] = useState<FineOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const refresh = useCallback(() => {
    getFine().then(setFine).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, 5 * 60 * 1000);
    return () => window.clearInterval(id);
  }, [refresh, profileId]);

  if (!fine) return null;

  if (fine.fine_at) {
    return (
      <div className="pc-fine pc-fine--done" role="status">
        <span aria-hidden="true">✓</span> {t.fineDone}
      </div>
    );
  }

  async function press() {
    setBusy(true);
    setFailed(false);
    try {
      setFine(await sendFine());
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`pc-fine${fine.asked ? " pc-fine--asked" : ""}`}>
      <button type="button" className="pc-fine-btn" onClick={() => void press()} disabled={busy}>
        <span aria-hidden="true">👍</span> {busy ? t.sending : t.imFine}
      </button>
      <p className="pc-fine-hint" role={fine.asked ? "alert" : undefined}>
        {failed ? t.failed : fine.asked ? t.askedHint : t.fineHint}
      </p>
    </div>
  );
}
