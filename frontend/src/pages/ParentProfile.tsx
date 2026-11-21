import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, auth, careProfiles, type CareProfileOut } from "../api";

interface ParentProfileProps {
  familyId: string;
}

export default function ParentProfile({ familyId }: ParentProfileProps) {
  const [profiles, setProfiles] = useState<CareProfileOut[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [displayName, setDisplayName] = useState("");
  const [greetingName, setGreetingName] = useState("");
  const [language, setLanguage] = useState("");
  const [timezone, setTimezone] = useState("");

  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    careProfiles
      .list(familyId)
      .then((list) => {
        if (cancelled) return;
        setProfiles(list);
        setSelectedId(list[0]?.id ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.detail : "Could not load care profiles.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [familyId]);

  const selected = profiles?.find((p) => p.id === selectedId) ?? null;

  useEffect(() => {
    if (!selected) return;
    setDisplayName(selected.display_name);
    setGreetingName(selected.greeting_name);
    setLanguage(selected.preferred_language);
    setTimezone(selected.timezone);
    setSaved(false);
  }, [selected?.id]);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const updated = await careProfiles.update(familyId, selected.id, {
        display_name: displayName,
        greeting_name: greetingName,
        preferred_language: language,
        timezone,
      });
      setProfiles((prev) => prev?.map((p) => (p.id === updated.id ? updated : p)) ?? prev);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not save the profile.");
    } finally {
      setSaving(false);
    }
  }

  async function handleSignOut() {
    try {
      await auth.logout();
    } catch {
      // Token is cleared even if the request fails; ignore the error.
    }
    navigate("/");
  }

  if (loading) return <p role="status">Loading care profiles…</p>;
  if (error && !profiles) return <p role="alert">{error}</p>;
  if (!profiles || profiles.length === 0) return <p>No care profiles yet.</p>;

  return (
    <main>
      <h1>Parent profile</h1>

      <label>
        Care profile
        <select value={selectedId ?? ""} onChange={(e) => setSelectedId(e.target.value)}>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.display_name}
            </option>
          ))}
        </select>
      </label>

      {selected && (
        <form onSubmit={handleSave}>
          <label>
            Display name
            <input required maxLength={255} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <label>
            Greeting name
            <input required maxLength={255} value={greetingName} onChange={(e) => setGreetingName(e.target.value)} />
          </label>
          <label>
            Preferred language
            <input value={language} onChange={(e) => setLanguage(e.target.value)} />
          </label>
          <label>
            Timezone
            <input value={timezone} onChange={(e) => setTimezone(e.target.value)} />
          </label>
          <button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save profile"}
          </button>
          {saved && <p role="status">Profile saved.</p>}
          {error && <p role="alert">{error}</p>}
        </form>
      )}

      <button type="button" onClick={handleSignOut}>
        Sign out
      </button>
    </main>
  );
}
