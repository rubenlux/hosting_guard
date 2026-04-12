import { useState, useEffect, useCallback, useRef } from 'react';
import { getHostingHealth, getHostingHealthHistory } from '../api/hosting';

/**
 * Fetches health status and health history for a single hosting.
 *
 * Race-condition safe: if hostingId changes or the component unmounts
 * while a fetch is in-flight, the stale response is silently discarded.
 *
 * Returns:
 *   health        — current health snapshot { score, status, color, ... }
 *   history       — array of past health checks (up to `historyLimit` entries)
 *   loading       — true while a fetch is in progress
 *   error         — Error | null
 *   refresh()     — manually re-fetch both health and history
 */
export function useHostingStatus(hostingId, historyLimit = 24) {
  const [health,  setHealth]  = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  // Tracks the latest fetch token so stale responses can be ignored.
  const activeTokenRef = useRef(0);

  const fetch = useCallback(async () => {
    if (!hostingId) {
      setLoading(false);
      return;
    }

    // Bump the token; this fetch "owns" this token value.
    const token = ++activeTokenRef.current;

    setLoading(true);
    setError(null);

    try {
      const [healthRes, historyRes] = await Promise.all([
        getHostingHealth(hostingId),
        getHostingHealthHistory(hostingId, historyLimit),
      ]);

      // Discard if a newer fetch started while this one was in-flight.
      if (token !== activeTokenRef.current) return;

      setHealth(healthRes);
      setHistory(historyRes);
    } catch (err) {
      if (token !== activeTokenRef.current) return;
      setError(err);
    } finally {
      if (token === activeTokenRef.current) setLoading(false);
    }
  }, [hostingId, historyLimit]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  return { health, history, loading, error, refresh: fetch };
}
