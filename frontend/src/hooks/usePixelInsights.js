import { useState, useEffect } from 'react';
import { getPixelDashboardSummary } from '../api/analytics';

/**
 * Fetches the pixel dashboard summary for a given site.
 *
 * Designed to be a focused, single-responsibility hook:
 * - No caching (consumers add their own if needed)
 * - Cancellation via mounted flag to prevent setState after unmount
 * - Re-fetches when siteId or days changes
 *
 * Returns { data, loading, error }
 */
export function usePixelInsights(siteId, days = 7) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  useEffect(() => {
    if (!siteId) {
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);

    async function fetchData() {
      try {
        const res = await getPixelDashboardSummary(siteId, days);
        if (active) setData(res);
      } catch (err) {
        if (active) setError(err);
      } finally {
        if (active) setLoading(false);
      }
    }

    fetchData();
    return () => { active = false; };
  }, [siteId, days]);

  return { data, loading, error };
}
