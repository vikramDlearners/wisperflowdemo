import { useEffect, useState } from "react";
import type { ParentMedicine } from "../parentApi";

// Photos of the medicines a bot message names, so a parent who isn't sure which tablet is which
// can see it. Names come from the parent's own medicine list (GET /api/parent/medicines); a
// longer name wins over a shorter one inside it ("Metformin 500 mg" over "Metformin").

export function medicinesNamedIn(text: string, medicines: ParentMedicine[]): ParentMedicine[] {
  const lower = text.toLowerCase();
  const byLength = [...medicines].filter((m) => m.name.trim()).sort((a, b) => b.name.length - a.name.length);
  const found: ParentMedicine[] = [];
  for (const med of byLength) {
    const name = med.name.toLowerCase();
    if (!lower.includes(name)) continue;
    if (found.some((f) => f.name.toLowerCase().includes(name))) continue;
    found.push(med);
  }
  // Show them in the order the message names them.
  return found.sort((a, b) => lower.indexOf(a.name.toLowerCase()) - lower.indexOf(b.name.toLowerCase()));
}

interface Props {
  text: string;
  medicines: ParentMedicine[];
  photoUrls: Record<string, string>;
  photoLabel: string;
  closeLabel: string;
}

export default function ParentMedicinePhotos({ text, medicines, photoUrls, photoLabel, closeLabel }: Props) {
  const [open, setOpen] = useState<ParentMedicine | null>(null);
  const shown = medicinesNamedIn(text, medicines).filter((m) => m.has_image && photoUrls[m.id]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (shown.length === 0) return null;
  return (
    <>
      <div className="pc-med-photos">
        {shown.map((m) => (
          <button key={m.id} type="button" className="pc-med-photo" onClick={() => setOpen(m)}>
            <img src={photoUrls[m.id]} alt={`${photoLabel}: ${m.name}`} />
            <span className="pc-med-photo-name">{m.name}</span>
          </button>
        ))}
      </div>
      {open && (
        <div
          className="pc-photo-viewer"
          role="dialog"
          aria-modal="true"
          aria-label={`${photoLabel}: ${open.name}`}
          onClick={() => setOpen(null)}
        >
          <figure className="pc-photo-figure" onClick={(e) => e.stopPropagation()}>
            <img src={photoUrls[open.id]} alt={`${photoLabel}: ${open.name}`} />
            <figcaption>{open.name}</figcaption>
            <button type="button" className="pc-primary-btn" onClick={() => setOpen(null)} autoFocus>
              {closeLabel}
            </button>
          </figure>
        </div>
      )}
    </>
  );
}
