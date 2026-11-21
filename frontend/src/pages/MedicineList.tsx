import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, medicines, type MedicineOut } from "../api";

interface MedicineListProps {
  familyId: string;
  onSelect?: (medicine: MedicineOut) => void;
  onAdd?: () => void;
}

export default function MedicineList({ familyId, onSelect, onAdd }: MedicineListProps) {
  const [items, setItems] = useState<MedicineOut[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    medicines
      .list(familyId)
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.detail : "Could not load medicines.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [familyId]);

  if (loading) return <p role="status">Loading medicines…</p>;
  if (error) return <p role="alert">{error}</p>;

  return (
    <main>
      <header>
        <h1>Medicine list</h1>
        {onAdd && <button type="button" onClick={onAdd}>Add medicine</button>}
        <Link to={`/family/${familyId}/prescription-scan`}>Scan prescription</Link>
      </header>

      {!items || items.length === 0 ? (
        <p>No medicines yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Instructions</th>
              <th>Quantity left</th>
              <th>Refill date</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => (
              <tr key={m.id} onClick={() => onSelect?.(m)}>
                <td>{m.display_name}</td>
                <td>{m.instructions_text ?? "—"}</td>
                <td>{m.quantity_remaining ?? "—"}</td>
                <td>{m.refill_date ?? "—"}</td>
                <td>{m.active ? "Active" : "Inactive"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
