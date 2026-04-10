import { useDashboardData }  from '../../hooks/useDashboardData';
import OverviewCard          from './OverviewCard';
import DashboardSkeleton     from './DashboardSkeleton';
import EmptyState            from './EmptyState';
import ErrorState            from './ErrorState';
import SiteSelector          from './SiteSelector';
import HeroSection           from './HeroSection';
import IAInsightCard         from './IAInsightCard';
import MonitoringSection     from './MonitoringSection';
import TrafficSection        from './TrafficSection';

/**
 * Dashboard analytics overview — pure composition, zero business logic.
 *
 * Visual hierarchy:
 *   1. Hero     — system status at a glance
 *   2. IA       — insight chips as protagonist
 *   3. Monitoring — KPIs + realtime
 *   4. Traffic  — sparkline + top pages
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

      <HeroSection realtime={realtime} />

      <IAInsightCard chips={chips} />

      <MonitoringSection kpis={kpis} realtime={realtime} />

      <TrafficSection sparkline={sparkline} topPages={topPages} />

    </OverviewCard>
  );
}
