import { useEffect, useState } from "react";
import { careProfiles, type CareProfileOut } from "../api";

// The family's parents, with the first one chosen. Pages that work on one parent at a time share this.
export function useCareProfiles(familyId: string) {
  const [profiles, setProfiles] = useState<CareProfileOut[]>([]);
  const [profileId, setProfileId] = useState("");
  useEffect(() => {
    careProfiles
      .list(familyId)
      .then((rows) => {
        setProfiles(rows);
        setProfileId((id) => id || rows[0]?.id || "");
      })
      .catch(() => undefined);
  }, [familyId]);
  return { profiles, profileId, setProfileId };
}

export default function ProfilePicker({
  profiles,
  profileId,
  onChange,
}: {
  profiles: CareProfileOut[];
  profileId: string;
  onChange: (id: string) => void;
}) {
  if (profiles.length < 2) return null;
  return (
    <label className="hn-field">
      <span>Parent</span>
      <select value={profileId} onChange={(e) => onChange(e.target.value)}>
        {profiles.map((p) => (
          <option key={p.id} value={p.id}>
            {p.display_name}
          </option>
        ))}
      </select>
    </label>
  );
}
