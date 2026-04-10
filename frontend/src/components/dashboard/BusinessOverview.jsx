import { useDashboardData }  from '../../hooks/useDashboardData';
import OverviewCard          from './OverviewCard';
import KPISection            from './KPISection';
import SparklineChart        from './SparklineChart';
import TopPagesMini          from './TopPagesMini';
import RealtimeMini          from './RealtimeMini';
import DashboardSkeleton     from './DashboardSkeleton';
import EmptyState            from './EmptyState';
import ErrorState            from './ErrorState';
import SiteSelector          from './SiteSelector';

/**
 * Dashboard analytics overview — pure composition, zero business logic.
 *
 * All data fetching and transformation lives in useDashboardData.
 * All rendering lives in the atomic sub-components.
 */
export default function BusinessOverview() {
  const {
    sites, site, selectSite, retry,
    kpis, sparkline, topPages, chips, realtime,
    loading, error,
  } = useDashboardData();

  if (loading) return <DashboardSkeleton />;
  if (error)   return <ErrorState message={error?.message} onRetry={retry} />;
  if (!site)   return <EmptyState hasSite={false} />;

  // safety net — prevents rendering with invalid data
  if (!kpis)   return <DashboardSkeleton />;

  const isEmpty = kpis.visits === 0 && kpis.sessions === 0;
  if (isEmpty)  return <EmptyState hasSite={true} />;

  return (
    <OverviewCard
      siteName={site.name}
      headerExtra={
        <SiteSelector
          sites={sites}
          selectedId={site.site_id}
          onChange={selectSite}
        />
      }
    >

      <KPISection kpis={kpis} />

      {chips.length > 0 && (
        <div className="flex gap-1.5 flex-wrap mb-3">
          {chips.map((chip, i) => (
            <span
              key={i}
              className="bg-white/5 border border-white/8 px-2 py-0.5 rounded text-[10px] font-mono text-gray-300"
            >
              {chip}
            </span>
          ))}
        </div>
      )}

      <div className="mb-3">
        <SparklineChart data={sparkline} />
      </div>

      <TopPagesMini pages={topPages} />

      <RealtimeMini {...realtime} />

    </OverviewCard>
  );
}
