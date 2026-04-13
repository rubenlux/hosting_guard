import { motion } from 'framer-motion';
import { useBusinessOverview } from '../../hooks/useBusinessOverview';
import OverviewCard      from './OverviewCard';
import DashboardSkeleton from './DashboardSkeleton';
import EmptyState        from './EmptyState';
import ErrorState        from './ErrorState';
import SiteSelector      from './SiteSelector';
import TopPagesMini      from './TopPagesMini';
import RealtimeMini      from './RealtimeMini';

// New Chart Components
import TrafficAreaChart  from './charts/TrafficAreaChart';
import BounceRadialChart from './charts/BounceRadialChart';
import ActiveUsersPulse  from './charts/ActiveUsersPulse';
import SessionsBarChart  from './charts/SessionsBarChart';

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
  } = useBusinessOverview();

  if (loading) return <DashboardSkeleton />;
  if (error)   return <ErrorState message={error?.message} onRetry={retry} />;
  if (!site)   return <EmptyState hasSite={false} />;
  if (!kpis)   return <DashboardSkeleton />;

  const isEmpty = kpis.visits === 0 && kpis.sessions === 0;
  if (isEmpty)  return <EmptyState hasSite={true} />;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
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
        {/* Visual Analytics Grid */}
        <div className="mt-8 space-y-6">
          
          {/* TOP ROW: Main Traffic + Quick Metrics */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-7 xl:col-span-8">
              <TrafficAreaChart data={sparkline} />
            </div>
            
            <div className="lg:col-span-5 xl:col-span-4 flex flex-col gap-6">
              <div className="grid grid-cols-2 gap-6 flex-1">
                <BounceRadialChart bounceRate={kpis.bounceRate} />
                <ActiveUsersPulse active={realtime?.active} />
              </div>
              <SessionsBarChart data={sparkline} />
            </div>
          </div>

          {/* BOTTOM ROW: Details */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-7 xl:col-span-8">
              <div className="bg-[#121214] border border-white/10 rounded-xl p-5 shadow-sm">
                <h3 className="text-[12px] font-mono text-gray-400 uppercase tracking-widest font-bold mb-4">Páginas Más Visitadas</h3>
                <TopPagesMini pages={topPages} />
              </div>
            </div>
            <div className="lg:col-span-5 xl:col-span-4">
              <RealtimeMini {...realtime} />
            </div>
          </div>
          
        </div>
      </OverviewCard>
    </motion.div>
  );
}
