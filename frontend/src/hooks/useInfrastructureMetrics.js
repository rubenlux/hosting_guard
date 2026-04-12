import { useMemo } from 'react';

/**
 * Derives infrastructure KPIs from raw hosting + health data.
 * Pure computation — no side effects, no fetching.
 *
 * Returns:
 *   avgHealthScore — integer 0-100, or null when no hostings
 *   avgCpu         — string "N.N" (percentage of first hosting's cpu_limit)
 *   totalRam       — formatted string "N.N MB" or "N.N GB"
 *   healthTrend    — { arrow, label, color } based on latest two health checks
 *   unresolved     — count of unresolved alerts
 */
export function useInfrastructureMetrics(hostings, healthData, healthHistory, alerts) {
  const avgHealthScore = useMemo(() => {
    if (!hostings.length) return null;
    const sum = hostings.reduce((acc, h) => acc + (healthData[h.hosting_id]?.score ?? 0), 0);
    return Math.round(sum / hostings.length);
  }, [hostings, healthData]);

  const avgCpu = useMemo(() => {
    if (!hostings.length) return '0';
    const sum = hostings.reduce((acc, h) => acc + parseFloat(h.metrics?.cpu || 0), 0);
    return (sum / hostings.length).toFixed(1);
  }, [hostings]);

  const totalRam = useMemo(() => {
    const totalMiB = hostings.reduce((acc, h) => {
      const memStr = h.metrics?.memory || '0MiB';
      const val = parseFloat(memStr);
      return acc + (isNaN(val) ? 0 : (memStr.includes('GiB') ? val * 1024 : val));
    }, 0);
    return totalMiB > 1024
      ? `${(totalMiB / 1024).toFixed(1)} GB`
      : `${totalMiB.toFixed(1)} MB`;
  }, [hostings]);

  const healthTrend = useMemo(() => {
    const history = (hostings[0] && healthHistory[hostings[0].hosting_id]) || [];
    if (history.length < 2) return { arrow: '↔', label: 'Estable',    color: '#fff'     };
    const last = history[history.length - 1].score;
    const prev = history[history.length - 2].score;
    if (last > prev) return  { arrow: '↑', label: 'Mejorando',  color: '#4ade80' };
    if (last < prev) return  { arrow: '↓', label: 'Degradando', color: '#f87171' };
    return                   { arrow: '↔', label: 'Estable',    color: '#fff'     };
  }, [hostings, healthHistory]);

  const unresolved = useMemo(
    () => (alerts ?? []).filter(a => !a.resolved).length,
    [alerts],
  );

  return { avgHealthScore, avgCpu, totalRam, healthTrend, unresolved };
}
