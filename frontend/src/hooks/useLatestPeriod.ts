import { useEffect, useState } from "react";
import { listProductionRecords } from "../api/ledger";
import { currentMonthRange } from "../lib/dates";

interface Period {
  start: string;
  end: string;
}

/** The facility's most recent production period on file, falling back to
 * the current calendar month for a facility with no history yet. Landing
 * pages default to this instead of "this calendar month" — a real
 * factory's bills for the current month usually aren't in yet, so that
 * default showed an empty/zeroed dashboard for most of every month. */
export function useLatestPeriod(facilityId: string): { period: Period | null; isLoading: boolean } {
  const [period, setPeriod] = useState<Period | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!facilityId) {
      setPeriod(null);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    listProductionRecords({ facility_id: facilityId })
      .then((records) => {
        if (cancelled) return;
        setPeriod(
          records[0] ? { start: records[0].period_start, end: records[0].period_end } : currentMonthRange()
        );
      })
      .catch(() => {
        if (!cancelled) setPeriod(currentMonthRange());
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [facilityId]);

  return { period, isLoading };
}
