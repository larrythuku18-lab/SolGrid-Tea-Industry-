import type { ReadingType } from "../types/api";

export const READING_TYPE_LABEL: Record<ReadingType, string> = {
  grid_electricity: "Grid electricity",
  diesel: "Diesel",
  fuelwood: "Fuelwood",
  solar_generation: "Solar generation",
};

export const READING_TYPE_UNIT: Record<ReadingType, string> = {
  grid_electricity: "kWh",
  diesel: "litre",
  fuelwood: "m3",
  solar_generation: "kWh",
};

export const READING_TYPE_COLOR: Record<string, string> = {
  grid_electricity: "var(--volt)",
  diesel: "var(--alert)",
  fuelwood: "var(--ink-dim)",
  solar_generation: "var(--solar)",
};
