export function toIsoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function currentMonthRange(): { start: string; end: string } {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  return { start: toIsoDate(start), end: toIsoDate(now) };
}
