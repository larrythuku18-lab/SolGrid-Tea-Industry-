import { apiRequest } from "./client";
import type { GenerationVsConsumptionSeries, SolarHealthSummary } from "../types/api";

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
