import { useEffect, useState } from "react";

/** A clock the UI can subscribe to, so a "last reading 4m ago" label keeps
 * counting between server heartbeats. Only the ticking is local — the age
 * itself is derived from the server's own timestamp, so it stays correct on
 * a machine whose clock is off. */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return now;
}
