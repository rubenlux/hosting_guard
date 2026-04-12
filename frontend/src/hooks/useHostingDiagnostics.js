import { useState, useCallback, useEffect, useRef } from 'react';
import { diagnoseHosting } from '../services/api';

/**
 * Manages the AI diagnosis lifecycle for a hosting container.
 *
 * @param {Array} hostings — hosting list from useDashboardData; used to resolve names internally.
 *
 * Returns:
 *   diagnose(hostingId) — triggers diagnosis; resolves hostingName from hostings list
 *   data    — { hostingName, ...apiResult } or null
 *   loading — true while request is in-flight
 *   error   — Error | null
 *   reset() — clears all state (use when closing the modal)
 */
export function useHostingDiagnostics(hostings = []) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  const hostingsRef = useRef(hostings);
  useEffect(() => { hostingsRef.current = hostings; });

  const diagnose = useCallback(async (hostingId) => {
    const hostingName = hostingsRef.current.find(h => h.hosting_id === hostingId)?.name;
    setLoading(true);
    setData(null);
    setError(null);
    try {
      const result = await diagnoseHosting(hostingId);
      setData({ hostingName, ...result });
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { diagnose, data, loading, error, reset };
}
