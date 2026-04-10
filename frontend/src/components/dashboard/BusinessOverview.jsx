import { useDashboardData }  from '../../hooks/useDashboardData';
import OverviewCard          from './OverviewCard';
import DashboardSkeleton     from './DashboardSkeleton';
import EmptyState            from './EmptyState';
import ErrorState            from './ErrorState';
import SiteSelector          from './SiteSelector';
import HeroSection           from './HeroSection';
import InsightCard           from './InsightCard';
import KPISection            from './KPISection';
import SparklineChart        from './SparklineChart';
import TopPagesMini          from './TopPagesMini';
import RealtimeMini          from './RealtimeMini';

/**
 * Dashboard analytics overview — pure composition, zero business logic.
 *
 * Layout:
 *   [ Hero — full width ]
 *   [ KPI strip — 4 columns ]
 *   [ Left 8/12: Sparkline + TopPages ]   [ Right 4/12: Realtime + InsightCard ]
 */
export default function BusinessOverview() {
  const {
    sites, site, selectSite, retry,
    kpis, sparkline, topPages, realtime,
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

      <HeroSection realtime={realtime} />

      <KPISection kpis={kpis} />

      <div className="grid grid-cols-12 gap-6">

        {/* Left column — traffic */}
        <div className="col-span-8 space-y-6">
          <SparklineChart data={sparkline} />
          <TopPagesMini pages={topPages} />
        </div>

        {/* Right column — realtime + insight */}
        <div className="col-span-4 space-y-6">
          <RealtimeMini {...realtime} />
          <InsightCard
            insight={{
              message: 'Detectamos aumento del 40% en CPU. Posible plugin mal configurado.',
            }}
          />
        </div>

      </div>

    </OverviewCard>
  );
}
