import { useEffect, useState } from "react";
import { listFacilities } from "../api/facilities";
import type { Facility } from "../types/api";

interface UseFacilitiesResult {
  facilities: Facility[];
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

export function useFacilities(): UseFacilitiesResult {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    listFacilities()
      .then((result) => {
        if (!cancelled) {
          setFacilities(result);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "failed to load facilities");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return { facilities, isLoading, error, reload: () => setReloadKey((k) => k + 1) };
}
