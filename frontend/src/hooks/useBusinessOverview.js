/**
 * Data hook for BusinessOverview — pixel analytics dashboard.
 *
 * Provides the exact API surface that BusinessOverview.jsx expects:
 *   sites, site, selectSite, retry
 *   kpis, sparkline, topPages, realtime
 *   loading, error
 *
 * Uses React Query for caching + background refresh.
 * Sites list is fetched once; per-site summary re-fetches on site/days change.
 */
import { useState, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { getPixelDashboardSummary } from '../services/api';

// ── Query keys ────────────────────────────────────────────────────────────────
const SITES_KEY    = ['pixel', 'sites'];
const SUMMARY_KEY  = (siteId, days) => ['pixel', 'summary', siteId, days];

const DAYS_DEFAULT = 7;

// ── Shape mappers (pure, testable) ────────────────────────────────────────────
function mapKpis(stats) {
  if (!stats) return null;
  return {
    visits:     stats.today_events      ?? 0,
    sessions:   stats.unique_sessions   ?? 0,
    bounceRate: stats.bounce_rate       ?? 0,
    active:     stats.active_users_5min ?? 0,
  };
}

function mapRealtime(stats) {
  if (!stats) return null;
  return {
    active_users_5min: stats.active_users_5min ?? 0,
    bounce_rate:       stats.bounce_rate       ?? 0,
    unique_sessions:   stats.unique_sessions   ?? 0,
  };
}

export function useBusinessOverview() {
  const queryClient = useQueryClient();
  const [selectedSite, setSelectedSite] = useState(null);
  const [days] = useState(DAYS_DEFAULT);

  // ── Sites list ────────────────────────────────────────────────────────────
  const sitesQuery = useQuery({
    queryKey: SITES_KEY,
    queryFn:  async () => {
      const { data } = await api.get('/pixel/sites');
      return data;
    },
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });

  const sites = sitesQuery.data ?? [];

  // Auto-select first site when list loads and nothing is selected yet
  const site = selectedSite ?? sites[0] ?? null;

  // ── Per-site dashboard summary ────────────────────────────────────────────
  const summaryQuery = useQuery({
    queryKey: SUMMARY_KEY(site?.site_id, days),
    queryFn:  () => getPixelDashboardSummary(site.site_id, days),
    enabled:  Boolean(site?.site_id),
    staleTime: 30_000,
    refetchInterval: () =>
      document.visibilityState === 'visible' ? 30_000 : false,
  });

  const summary = summaryQuery.data;

  // ── Derived data ──────────────────────────────────────────────────────────
  const kpis     = mapKpis(summary?.stats);
  const sparkline = summary?.sparkline     ?? null;
  const topPages  = summary?.pages_raw     ?? null;
  const realtime  = mapRealtime(summary?.stats);

  // ── Actions ───────────────────────────────────────────────────────────────
  const selectSite = useCallback((site) => setSelectedSite(site), []);

  const retry = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: SITES_KEY });
    if (site?.site_id) {
      queryClient.invalidateQueries({ queryKey: SUMMARY_KEY(site.site_id, days), exact: true });
    }
  }, [queryClient, site, days]);

  return {
    // Site management
    sites,
    site,
    selectSite,
    retry,
    // Analytics data
    kpis,
    sparkline,
    topPages,
    realtime,
    // Status
    loading: sitesQuery.isLoading || (Boolean(site) && summaryQuery.isLoading),
    error:   sitesQuery.error     ?? summaryQuery.error ?? null,
  };
}
