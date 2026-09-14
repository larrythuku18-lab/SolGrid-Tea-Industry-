import { apiRequest } from "./client";
import type { EnergyReading, EnergyReadingInput, ProductionRecord, ProductionRecordInput } from "../types/api";

export function listEnergyReadings(params: {
  facility_id?: string;
  period_start?: string;
  period_end?: string;
}): Promise<EnergyReading[]> {
  return apiRequest<EnergyReading[]>("/api/v1/ledger/energy-readings", { query: params });
}

export function createEnergyReading(input: EnergyReadingInput): Promise<{ id: string }> {
  return apiRequest("/api/v1/ledger/energy-readings", { method: "POST", body: input });
}

export function listProductionRecords(params: { facility_id?: string }): Promise<ProductionRecord[]> {
  return apiRequest<ProductionRecord[]>("/api/v1/ledger/production-records", { query: params });
}

export function createProductionRecord(input: ProductionRecordInput): Promise<{ id: string }> {
  return apiRequest("/api/v1/ledger/production-records", { method: "POST", body: input });
}
