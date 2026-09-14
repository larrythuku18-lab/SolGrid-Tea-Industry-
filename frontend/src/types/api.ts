export type ReadingType = "grid_electricity" | "diesel" | "fuelwood" | "solar_generation";
export type SourceChannel = "esp32" | "modbus" | "oem_api" | "manual" | "sms";
export type Role = "admin" | "operator" | "viewer";
export type FinancingMode = "ppa" | "capex";

export interface Facility {
  id: string;
  name: string;
  county: string | null;
  install_capacity_kw: number | null;
  is_active: boolean;
}

export interface FacilityInput {
  name: string;
  county?: string;
  install_capacity_kw?: number;
}

export interface EnergyReading {
  id: string;
  facility_id: string;
  reading_type: ReadingType;
  period_start: string;
  period_end: string;
  quantity: number;
  unit: string;
  cost_kes: number | null;
  moisture_pct: number | null;
  source_plantation: string | null;
  source_channel: SourceChannel;
}

export interface EnergyReadingInput {
  facility_id: string;
  reading_type: ReadingType;
  period_start: string;
  period_end: string;
  quantity: number;
  unit: string;
  cost_kes?: number | null;
  moisture_pct?: number | null;
  source_plantation?: string | null;
  source_channel?: SourceChannel;
}

export interface ProductionRecord {
  id: string;
  facility_id: string;
  period_start: string;
  period_end: string;
  made_tea_kg: number;
  source: string;
}

export interface ProductionRecordInput {
  facility_id: string;
  period_start: string;
  period_end: string;
  made_tea_kg: number;
}

export interface BenchmarkResult {
  facility_id: string;
  period_start: string;
  period_end: string;
  total_made_tea_kg: number;
  total_cost_kes: number;
  total_energy_kwh: number;
  cost_per_kg_tea_kes: number | null;
  kwh_per_kg_tea: number | null;
  energy_mix_pct: Record<string, number>;
  missing_energy_content_factors: string[];
}

export interface ScenarioInput {
  facility_id: string;
  financing_mode: FinancingMode;
  target_solar_kw: number;
  grid_tariff_kes_per_kwh: number;
  ppa_rate_kes_per_kwh?: number | null;
  capex_kes?: number | null;
  daytime_coincidence_factor: number;
  solar_capacity_factor: number;
  baseline_annual_grid_kwh: number;
  baseline_annual_electrical_kwh: number;
  baseline_annual_total_energy_kwh: number;
}

export interface ScenarioResult {
  id: string;
  solar_annual_generation_kwh: number;
  addressable_kwh: number;
  addressable_electrical_share_pct: number;
  addressable_of_total_energy_pct: number;
  annual_savings_kes: number;
  payback_years: number | null;
  emissions_avoided_grid_tco2: number;
  emissions_avoided_fuelwood_tco2: number;
  fuelwood_reduction_m3: number;
  grid_emission_factor_id: string;
  grid_emission_factor_methodology_note: string;
}

export interface Me {
  user_id: string;
  org_id: string;
  role: Role;
  email: string | null;
  organization_name: string | null;
}
