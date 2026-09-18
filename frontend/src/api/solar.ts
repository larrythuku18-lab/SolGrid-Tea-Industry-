import { apiRequest, openEventStream } from "./client";
import type {
  GenerationVsConsumptionSeries,
  SolarHealthPoint,
  SolarHealthSummary,
  SolarLiveHealthUpdate,
  SolarLiveSeriesUpdate,
  SolarLiveSnapshot,
  SolarLiveTick,
} from "../types/api";

export function getGenerationVsConsumption(params: {
  facility_id: string;
  period_start: string;
  period_end: string;
}): Promise<GenerationVsConsumptionSeries> {
  return apiRequest<GenerationVsConsumptionSeries>("/api/v1/solar/generation", { query: params });
}

export function getSolarHealth(params: { facility_id: string; as_of?: string }): Promise<SolarHealthSummary> {
  return apiRequest<SolarHealthSummary>("/api/v1/solar/health", { query: params });
}

export function getSolarHealthHistory(params: {
  facility_id: string;
  period_start: string;
  period_end: string;
}): Promise<SolarHealthPoint[]> {
  return apiRequest<SolarHealthPoint[]>("/api/v1/solar/health/history", { query: params });
}

export interface SolarLiveHandlers {
  onSnapshot: (payload: SolarLiveSnapshot) => void;
  onHealth: (payload: SolarLiveHealthUpdate) => void;
  onSeries: (payload: SolarLiveSeriesUpdate) => void;
  onTick: (payload: SolarLiveTick) => void;
  onOpen?: () => void;
}

/** Opens the server-sent-events feed for a facility. Resolves when the
 * server ends the stream, rejects if it can't be established — see
 * `openEventStream`, and `useSolarLive` for the reconnect policy. */
export function openSolarLiveStream(
  params: {
    facility_id: string;
    period_start?: string;
    period_end?: string;
    interval_s?: number;
  },
  handlers: SolarLiveHandlers,
  signal: AbortSignal,
): Promise<void> {
  return openEventStream(
    "/api/v1/solar/live",
    {
      query: {
        facility_id: params.facility_id,
        period_start: params.period_start,
        period_end: params.period_end,
        interval_s: params.interval_s !== undefined ? String(params.interval_s) : undefined,
      },
      signal,
      onOpen: handlers.onOpen,
      onEvent: (event, data) => {
        switch (event) {
          case "snapshot":
            handlers.onSnapshot(data as SolarLiveSnapshot);
            break;
          case "health":
            handlers.onHealth(data as SolarLiveHealthUpdate);
            break;
          case "series":
            handlers.onSeries(data as SolarLiveSeriesUpdate);
            break;
          case "tick":
            handlers.onTick(data as SolarLiveTick);
            break;
          // An event name this build doesn't know: ignore it rather than
          // guess. The backend can grow new events without breaking a page
          // that's already open (or a stale bundle).
          default:
            break;
        }
      },
    },
    true,
  );
}
