import KPISection  from './KPISection';
import RealtimeMini from './RealtimeMini';

/**
 * Groups KPIs and realtime status into a single monitoring block.
 *
 * Props:
 *   kpis     — { visits, sessions, bounceRate, active }
 *   realtime — { active, lastPath, lastTime, isLive }
 */
export default function MonitoringSection({ kpis, realtime }) {
  return (
    <div className="space-y-3 mb-4">
      <KPISection kpis={kpis} />
      <RealtimeMini {...realtime} />
    </div>
  );
}
