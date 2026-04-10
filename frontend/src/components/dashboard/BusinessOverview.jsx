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
 * Visual hierarchy:
 *   1. Hero     — system status at a glance
 *   2. IA       — insight advisory
 *   3. KPIs     — supporting metrics
 *   4. Sparkline + top pages
 *   5. Realtime status bar
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

      <HeroSection realtime={realtime} kpis={kpis} />

      <InsightCard
        insight={{
          message: 'Detectamos aumento del 40% en CPU. Posible plugin mal configurado.',
        }}
      />

      <KPISection kpis={kpis} />

      <div className="mb-3">
        <SparklineChart data={sparkline} />
      </div>

      <TopPagesMini pages={topPages} />

      <RealtimeMini {...realtime} />

    </OverviewCard>
  );
}
