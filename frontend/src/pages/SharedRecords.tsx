import { useEffect, useState } from "react";
import "../medicines.css";
import WorkspaceLayout from "../components/WorkspaceLayout";
import {
  families,
  getProfile,
  medicines,
  type ConversationSummaryOut,
} from "../api";

// Family records: conversation summaries (GET /api/families/{id}/conversation-summaries)
// and the family's medicines with their reminder times.

interface MedicineRow {
  id: string;
  name: string;
  times: string[];
  notes: string | null; // MedicineOut has no separate notes field; instructions_text is used.
  lastTaken: string | null;
}

// Quote every cell, escape internal quotes, join with CRLF rows.
function toCsv(headers: string[], rows: string[][]): string {
  const quote = (cell: string) => `"${cell.replace(/"/g, '""')}"`;
  const lines = [headers, ...rows].map((row) => row.map(quote).join(","));
  return lines.join("\r\n");
}

function downloadCsv(filename: string, csv: string): void {
  // BOM so Excel detects UTF-8.
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function SharedRecords({ familyId }: { familyId: string }) {
  const [summaries, setSummaries] = useState<ConversationSummaryOut[]>([]);
  const [medicineRows, setMedicineRows] = useState<MedicineRow[]>([]);
  const [parentName, setParentName] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(null);
    (async () => {
      try {
        const [summaryList, medicineList, lastTakenList, profile] = await Promise.all([
          families.conversationSummaries(familyId),
          medicines.list(familyId),
          medicines.lastTaken(familyId),
          getProfile().catch(() => null),
        ]);
        const name = profile?.parent_full_name ?? "";
        const lastTakenById = new Map(
          lastTakenList.map((l) => [l.medicine_id, l.last_taken_at]),
        );
        const rows = await Promise.all(
          medicineList.map(async (m) => {
            const reminders = await medicines.getReminders(familyId, m.id);
            return {
              id: m.id,
              name: m.display_name,
              times: reminders.times,
              notes: m.instructions_text,
              lastTaken: lastTakenById.get(m.id) ?? null,
            };
          }),
        );
        if (!active) return;
        // Newest first.
        const sorted = [...summaryList].sort(
          (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
        );
        setSummaries(sorted);
        setMedicineRows(rows);
        setParentName(name);
      } catch (err) {
        if (active) {
          setLoadError(
            err instanceof Error
              ? `Could not load records: ${err.message}`
              : "Could not load records. Please try again.",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [familyId]);

  function handleDownloadSummaries() {
    const csv = toCsv(
      ["Parent name", "Date", "Summary"],
      summaries.map((s) => [parentName, new Date(s.created_at).toLocaleString(), s.summary]),
    );
    downloadCsv(`conversation-summaries-${familyId}.csv`, csv);
  }

  function handleDownloadMedicines() {
    const csv = toCsv(
      ["Parent name", "Medicine", "Time", "Last taken", "Notes"],
      medicineRows.map((m) => [
        parentName,
        m.name,
        m.times.length > 0 ? m.times.join(", ") : "—",
        m.lastTaken ? new Date(m.lastTaken).toLocaleString() : "—",
        m.notes || "—",
      ]),
    );
    downloadCsv(`medicines-${familyId}.csv`, csv);
  }

  return (
    <WorkspaceLayout familyId={familyId} current="records" title="Records">
      <div className="pp-content">
        <div
          className="pp-page-head"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}
        >
          <div>
            <p className="pp-eyebrow">Care circle · Family workspace</p>
            <h1>Records</h1>
            <p className="pp-muted">Conversation summaries and scheduled medicines for this family.</p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              className="pp-btn pp-btn-ghost"
              onClick={handleDownloadSummaries}
              disabled={summaries.length === 0}
            >
              Download summaries CSV
            </button>
            <button
              type="button"
              className="pp-btn pp-btn-ghost"
              onClick={handleDownloadMedicines}
              disabled={medicineRows.length === 0}
            >
              Download medicines CSV
            </button>
          </div>
        </div>

        {loading && <p role="status" className="pp-muted">Loading records…</p>}
        {loadError && (
          <div role="alert" className="pp-alert">
            {loadError}
          </div>
        )}

        {!loading && !loadError && (
          <>
            <section className="pp-card md-table-card">
              <h2>Conversation summary</h2>
              {summaries.length === 0 ? (
                <p className="pp-muted">No conversation summaries yet.</p>
              ) : (
                <div className="md-table-wrap">
                  <table className="md-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Summary</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summaries.map((s) => (
                        <tr key={s.id}>
                          <td>{new Date(s.created_at).toLocaleString()}</td>
                          <td>{s.summary}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="pp-card md-table-card">
              <h2>Medicines</h2>
              {medicineRows.length === 0 ? (
                <p className="pp-muted">No medicines scheduled.</p>
              ) : (
                <div className="md-table-wrap">
                  <table className="md-table">
                    <thead>
                      <tr>
                        <th>Medicine</th>
                        <th>Time</th>
                        <th>Last taken</th>
                        <th>Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {medicineRows.map((m) => (
                        <tr key={m.id}>
                          <td>{m.name}</td>
                          <td>{m.times.length > 0 ? m.times.join(", ") : "—"}</td>
                          <td>{m.lastTaken ? new Date(m.lastTaken).toLocaleString() : "—"}</td>
                          <td>{m.notes || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </WorkspaceLayout>
  );
}
