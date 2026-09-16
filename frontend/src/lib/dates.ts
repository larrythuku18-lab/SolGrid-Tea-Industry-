export function toIsoDate(d: Date): string {
  // Local Y-M-D, not toISOString() — that converts to UTC first, which
  // rolls back to the previous day for any positive UTC offset (including
  // Kenya's, the one place this app actually runs).
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function currentMonthRange(): { start: string; end: string } {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  return { start: toIsoDate(start), end: toIsoDate(now) };
}
