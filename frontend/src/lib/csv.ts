// Quote every cell, escape internal quotes, join with CRLF rows.
export function toCsv(headers: string[], rows: string[][]): string {
  const quote = (cell: string) => `"${cell.replace(/^[=+\-@\t\r]/, "'$&").replace(/"/g, '""')}"`;
  const lines = [headers, ...rows].map((row) => row.map(quote).join(","));
  return lines.join("\r\n");
}

export function downloadCsv(filename: string, csv: string): void {
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
