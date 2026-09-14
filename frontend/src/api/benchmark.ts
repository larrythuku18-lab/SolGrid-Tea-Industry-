import { apiRequest } from "./client";
import type { BenchmarkResult } from "../types/api";

export function getBenchmark(params: {
  facility_id: string;
  period_start: string;
  period_end: string;
}): Promise<BenchmarkResult> {
  return apiRequest<BenchmarkResult>("/api/v1/benchmark", { query: params });
}
