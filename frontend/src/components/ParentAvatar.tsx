import { useEffect, useState } from "react";
import { fetchParentProfilePhoto, type ParentProfile } from "../parentApi";

/** A profile's picture, or the first letter of the name when there is none. */
export default function ParentAvatar({ profile, large = false }: { profile: ParentProfile; large?: boolean }) {
  const [uploaded, setUploaded] = useState<string | null>(null);
  const [broken, setBroken] = useState(false);

  useEffect(() => {
    setUploaded(null);
    setBroken(false);
    if (!profile.has_photo) return;
    let url: string | null = null;
    let cancelled = false;
    fetchParentProfilePhoto(profile.id)
      .then((u) => {
        if (cancelled && u) URL.revokeObjectURL(u);
        else {
          url = u;
          setUploaded(u);
        }
      })
      .catch(() => undefined); // the letter is shown instead
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [profile.id, profile.has_photo]);

  const src = uploaded ?? (profile.has_photo ? null : profile.photo_url);
  return (
    <span className={`pc-avatar${large ? " is-large" : ""}`} aria-hidden="true">
      {src && !broken ? (
        <img src={src} alt="" onError={() => setBroken(true)} />
      ) : (
        [...profile.name.trim()][0]?.toUpperCase() ?? "?"
      )}
    </span>
  );
}
