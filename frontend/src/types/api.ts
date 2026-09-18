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

export type PanelStatus = "normal" | "underperforming" | "fault";
export type BatteryStatus = "normal" | "degraded" | "fault";
export type InsightSeverity = "info" | "warn" | "critical";

export interface GenerationVsConsumptionPoint {
  period_start: string;
  period_end: string;
  generation_kwh: number;
  consumption_kwh: number;
  self_consumption_pct: number | null;
}

export interface GenerationVsConsumptionSeries {
  facility_id: string;
  install_capacity_kw: number | null;
  points: GenerationVsConsumptionPoint[];
}

export interface SolarHealthLatest {
  /** ISO timestamp, not a date — see SolarHealthPoint below. */
  ts: string;
  battery_soc_pct: number | null;
  battery_soh_pct: number | null;
  panel_status: PanelStatus;
  battery_status: BatteryStatus;
  panel_temp_c: number | null;
  note: string | null;
}

export interface SolarInsight {
  severity: InsightSeverity;
  message: string;
}

export interface SolarHealthSummary {
  facility_id: string;
  latest: SolarHealthLatest | null;
  battery_soh_trend_pct: number | null;
  insights: SolarInsight[];
}

export interface SolarHealthPoint {
  /** ISO timestamp. Deliberately not truncated to a date: the health chart
   * is appended to by a live feed, and two readings in one day have to land
   * at different x positions. */
  ts: string;
  battery_soc_pct: number | null;
  battery_soh_pct: number | null;
}

// ---------- realtime feed (GET /api/v1/solar/live) ----------

export interface SolarLiveFreshness {
  server_ts: string;
  latest_health_ts: string | null;
  /** Seconds since that reading on the server's clock; null when the
   * facility has never reported. */
  latest_health_age_s: number | null;
  is_stale: boolean;
}

/** Sent once per connection, so a viewer isn't staring at an empty panel
 * while waiting for the next reading. Carries summaries, not raw history —
 * that came from the REST endpoints. */
export interface SolarLiveSnapshot {
  facility_id: string;
  health: SolarHealthSummary;
  series: GenerationVsConsumptionSeries;
  freshness: SolarLiveFreshness;
}

export interface SolarLiveHealthUpdate {
  /** New readings since the previous event, oldest first. */
  points: SolarHealthPoint[];
  health: SolarHealthSummary;
  freshness: SolarLiveFreshness;
}

export interface SolarLiveSeriesUpdate {
  series: GenerationVsConsumptionSeries;
  freshness: SolarLiveFreshness;
}

/** Heartbeat: no new data, just proof the stream is alive and how long since
 * the site last reported. */
export interface SolarLiveTick {
  freshness: SolarLiveFreshness;
}

export interface Me {
  user_id: string;
  org_id: string;
  role: Role;
  email: string | null;
  organization_name: string | null;
}
