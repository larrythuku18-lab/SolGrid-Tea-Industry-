import { apiRequest } from "./client";
import type { Facility, FacilityInput } from "../types/api";

export function listFacilities(): Promise<Facility[]> {
  return apiRequest<Facility[]>("/api/v1/facilities");
}

export function createFacility(input: FacilityInput): Promise<Facility> {
  return apiRequest<Facility>("/api/v1/facilities", { method: "POST", body: input });
}
