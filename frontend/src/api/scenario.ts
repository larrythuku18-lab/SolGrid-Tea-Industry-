import { apiRequest } from "./client";
import type { ScenarioInput, ScenarioResult } from "../types/api";

export function runScenario(input: ScenarioInput): Promise<ScenarioResult> {
  return apiRequest<ScenarioResult>("/api/v1/scenarios", { method: "POST", body: input });
}
