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

export function monthsBeforeIso(isoDate: string, months: number): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const d = new Date(year, month - 1, day);
  d.setMonth(d.getMonth() - months);
  return toIsoDate(d);
}

/** Parses either a bare `YYYY-MM-DD` (local midnight — `new Date("2026-09-16")`
 * is UTC midnight, which rolls back a day in EAT) or a full ISO timestamp as
 * the health endpoints send. Both shapes come back from this API. */
export function parseIsoInstant(iso: string): Date {
  if (iso.includes("T")) return new Date(iso);
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function formatMonthLabel(isoDate: string): string {
  return parseIsoInstant(isoDate).toLocaleDateString("en-US", { month: "short" });
}

/** Day + time, for a reading timestamp on a live view — the month-alone
 * label the charts use says nothing about whether a reading is current. */
export function formatDateTime(iso: string): string {
  return parseIsoInstant(iso).toLocaleString("en-US", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "just now" / "45s" / "12m" / "3h 05m" / "2d". A bare age in seconds is
 * unreadable at a glance, and "0.02758" seconds — a real value this API
 * returns for a reading that just landed — is worse. */
export function formatAge(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "unknown";
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    const rem = minutes % 60;
    return rem === 0 ? `${hours}h` : `${hours}h ${String(rem).padStart(2, "0")}m`;
  }
  return `${Math.floor(hours / 24)}d`;
}
