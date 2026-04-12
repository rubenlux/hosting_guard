/**
 * Canonical export. Renamed from useHostingDashboard → useDashboardData.
 * The old file re-exports this for backward compatibility.
 *
 * Backed by React Query: deduplication, background refresh, and smart
 * invalidation replace the manual polling + useState approach.
 *
 * Public API is unchanged — Dashboard.jsx requires zero edits.
 */
import { useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getDashboardSummary } from '../services/api';

export const DASHBOARD_KEY = ['dashboard'];

const POLL_INTERVAL = 15_000; // 15 s

// Module-level — stable reference, never re-created on render
const getRefetchInterval = () =>
  document.visibilityState === 'visible' ? POLL_INTERVAL : false;

// Pure mapper — extracted for reuse and unit-testability
const mapDashboardData = (raw) => ({
  hostings:      raw.hostings       ?? [],
  healthData:    raw.health         ?? {},
  healthHistory: raw.health_history ?? {},
  alerts:        raw.alerts         ?? [],
  events:        raw.events         ?? [],
});

export function useDashboardData() {
  const queryClient = useQueryClient();

  const { data, isLoading, isFetching } = useQuery({
    queryKey: DASHBOARD_KEY,
    queryFn:  getDashboardSummary,
    refetchInterval: getRefetchInterval,  // only polls while tab is visible
    // structuralSharing is true by default in React Query v5 — select output
    // is memoized automatically; no extra config needed.
    select: mapDashboardData,
  });

  // useCallback: stable reference — consumers won't re-render on every poll
  // exact: true — won't cascade into future sub-keys like ['dashboard', id]
  const refresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: DASHBOARD_KEY, exact: true });
  }, [queryClient]);

  return {
    hostings:      data?.hostings      ?? [],
    healthData:    data?.healthData    ?? {},
    healthHistory: data?.healthHistory ?? {},
    alerts:        data?.alerts        ?? [],
    events:        data?.events        ?? [],
    isInitialLoading: isLoading,          // true only on first fetch — drive skeleton
    isRefreshing:     isFetching,         // true on every background poll — drive shimmer
    loading: isLoading || isFetching,     // backward-compat for existing consumers
    refresh,
  };
}
