import { useEffect, useState } from "react";
import { openSolarLiveStream } from "../api/solar";
import type {
  GenerationVsConsumptionSeries,
  SolarHealthLatest,
  SolarHealthPoint,
  SolarHealthSummary,
  SolarLiveFreshness,
} from "../types/api";

/** `idle` until there's a facility (and a period) to stream for; `connecting`
 * on an attempt in flight; `live` once a frame has arrived; `offline` when
 * the stream has dropped and a retry is scheduled. */
export type SolarLiveStatus = "idle" | "connecting" | "live" | "offline";

export interface SolarLiveResult {
  status: SolarLiveStatus;
  error: string | null;
  latest: SolarHealthLatest | null;
  /** The streamed health summary — insights and the SoH trend, recomputed
   * server-side whenever a reading lands. Null until the first frame. */
  health: SolarHealthSummary | null;
  /** Readings that arrived *while this page was open*, oldest first. Merged
   * onto the REST-loaded history by the page; see its comment. */
  newPoints: SolarHealthPoint[];
  series: GenerationVsConsumptionSeries | null;
  freshness: SolarLiveFreshness | null;
  lastEventAt: number | null;
  /** Bumped when a connection is re-established after the first one, so the
   * page can re-load the REST history it may have missed while the stream
   * was down. Zero until that happens. */
  resyncNonce: number;
}

interface SolarLiveParams {
  facilityId: string;
  periodStart?: string;
  periodEnd?: string;
}

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;
// The server ticks every few seconds. Silence for much longer than that means
// the connection is dead even if the socket hasn't noticed — worth catching,
// because a live badge that stays green over a dead stream is the exact lie
// this view exists to avoid.
const SILENCE_TIMEOUT_MS = 20000;

/** Subscribes to `GET /api/v1/solar/live` and keeps the subscription alive. */
export function useSolarLive({ facilityId, periodStart, periodEnd }: SolarLiveParams): SolarLiveResult {
  const [status, setStatus] = useState<SolarLiveStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<SolarHealthLatest | null>(null);
  const [health, setHealth] = useState<SolarHealthSummary | null>(null);
  const [newPoints, setNewPoints] = useState<SolarHealthPoint[]>([]);
  const [series, setSeries] = useState<GenerationVsConsumptionSeries | null>(null);
  const [freshness, setFreshness] = useState<SolarLiveFreshness | null>(null);
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);
  const [resyncNonce, setResyncNonce] = useState(0);

  // Both are needed: the window the stream reports the generation series over
  // has to be the same one the page loaded over REST, or a `series` event
  // would swap the chart for a differently-windowed one.
  const ready = Boolean(facilityId && periodEnd);

  useEffect(() => {
    if (!ready) {
      setStatus("idle");
      setError(null);
      setLatest(null);
      setHealth(null);
      setSeries(null);
      setNewPoints([]);
      setFreshness(null);
      setLastEventAt(null);
      return;
    }

    let stopped = false;
    let attempt = 0;
    let connectedBefore = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let silenceTimer: ReturnType<typeof setTimeout> | undefined;
    let socket: AbortController | null = null;

    setStatus("connecting");
    setError(null);
    setLatest(null);
    setHealth(null);
    setSeries(null);
    setNewPoints([]);
    setFreshness(null);

    // Any frame — data or heartbeat — means the connection is working.
    const noteActivity = () => {
      setLastEventAt(Date.now());
      if (silenceTimer) clearTimeout(silenceTimer);
      silenceTimer = setTimeout(() => socket?.abort(), SILENCE_TIMEOUT_MS);
    };

    const scheduleReconnect = () => {
      if (stopped) return;
      setStatus((current) => (current === "live" || current === "connecting" ? "offline" : current));
      const delay = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * 2 ** attempt);
      attempt += 1;
      // Jittered: every open dashboard in the same outage should not come
      // back at the same instant.
      reconnectTimer = setTimeout(connect, delay * (0.85 + Math.random() * 0.3));
    };

    const connect = async () => {
      if (stopped) return;
      socket = new AbortController();
      if (attempt === 0) setStatus("connecting");

      try {
        await openSolarLiveStream(
          { facility_id: facilityId, period_start: periodStart, period_end: periodEnd },
          {
            onOpen: () => {
              // Deliberately not on the first connection: the page's own REST
              // load already covers that one, and refetching twice on mount
              // would be waste, not freshness.
              if (connectedBefore) setResyncNonce((n) => n + 1);
              connectedBefore = true;
            },
            onSnapshot: (payload) => {
              noteActivity();
              attempt = 0;
              setStatus("live");
              setError(null);
              setLatest(payload.health.latest);
              setHealth(payload.health);
              setSeries(payload.series);
              setFreshness(payload.freshness);
            },
            onHealth: (payload) => {
              noteActivity();
              setStatus("live");
              setLatest(payload.health.latest);
              setHealth(payload.health);
              setFreshness(payload.freshness);
              setNewPoints((prev) => [...prev, ...payload.points]);
            },
            onSeries: (payload) => {
              noteActivity();
              setStatus("live");
              setSeries(payload.series);
              setFreshness(payload.freshness);
            },
            onTick: (payload) => {
              noteActivity();
              setStatus("live");
              setFreshness(payload.freshness);
            },
          },
          socket.signal,
        );
      } catch (err) {
        // A watchdog abort isn't an error to report — it's the reconnect
        // path starting, and the status is about to say so.
        if (!stopped && !socket.signal.aborted) {
          setError(err instanceof Error ? err.message : "live feed unavailable");
        }
      }

      scheduleReconnect();
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (silenceTimer) clearTimeout(silenceTimer);
      socket?.abort();
    };
  }, [ready, facilityId, periodStart, periodEnd]);

  return { status, error, latest, health, newPoints, series, freshness, lastEventAt, resyncNonce };
}
