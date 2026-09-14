import type { Facility } from "../types/api";

interface FacilitySelectProps {
  facilities: Facility[];
  value: string;
  onChange: (facilityId: string) => void;
  id?: string;
}

export function FacilitySelect({ facilities, value, onChange, id }: FacilitySelectProps) {
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      {facilities.length === 0 && <option value="">No facilities yet</option>}
      {facilities.map((f) => (
        <option key={f.id} value={f.id}>
          {f.name}
        </option>
      ))}
    </select>
  );
}
