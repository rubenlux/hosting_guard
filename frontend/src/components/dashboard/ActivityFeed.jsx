import { RefreshCw, History } from 'lucide-react';

/**
 * Renders the recent activity feed.
 * Pure presentation — data and refresh handler come via props.
 *
 * Events are historical records, NOT current state.
 * Current state lives in healthData / Advisory.
 */

function relativeTime(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1)   return 'Ahora mismo';
  if (mins < 60)  return `Hace ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `Hace ${hours}h`;
  const days = Math.floor(hours / 24);
  return `Hace ${days}d`;
}

export default function ActivityFeed({ events, onRefresh }) {
  return (
    <div className="card-dash">
      <div className="card-header-dash">
        <div className="flex items-center gap-2">
          <div className="text-sm font-bold">Actividad Reciente</div>
          <div className="flex items-center gap-1 text-[9px] font-mono text-muted bg-white/5 px-1.5 py-0.5 rounded">
            <History className="w-2.5 h-2.5" />
            historial
          </div>
        </div>
        <button onClick={onRefresh} className="text-gray-400 hover:text-indigo-600 transition-colors" title="Refrescar">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="p-4 space-y-4 max-h-[600px] overflow-y-auto">
        {events.length === 0 ? (
          <div className="text-[11px] text-muted italic p-2">Sin actividad reciente.</div>
        ) : events.map(event => {
          const type = event.event_type?.toUpperCase() ?? '';

          const isCritical = type === 'CRITICAL' || type === 'PANIC';
          const isWarning  = type === 'WARNING'  || type === 'THROTTLE';
          const isRecovery = type === 'RECOVERY';
          const isRestart  = type === 'RESTART';
          const isHealth   = event.source === 'health';

          const dotColor = isRecovery
            ? 'bg-green-500 shadow-[0_0_8px_rgba(0,255,136,0.6)] animate-led'
            : isCritical || isRestart
            ? 'bg-danger shadow-[0_0_8px_red] animate-led'
            : isWarning
            ? 'bg-warn shadow-[0_0_8px_orange] animate-led'
            : 'bg-accent shadow-[0_0_8px_rgba(0,255,136,0.5)]';

          const typeColor = isRecovery
            ? 'text-green-400'
            : isCritical
            ? 'text-danger'
            : isWarning
            ? 'text-warn'
            : 'text-white';

          const siteLabel = isHealth
            ? event.container_name
            : (event.container_name || '').split('_').slice(-1)[0];

          return (
            <div
              key={event.id || event.event_id}
              className={`flex gap-4 items-start border-l-2 pl-4 ml-1 ${
                isRecovery ? 'border-green-500/30' : isCritical ? 'border-danger/30' : 'border-orange-500/40'
              }`}
            >
              <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${dotColor}`} />
              <div className="space-y-1">
                <div className={`text-xs font-bold flex items-center gap-2 flex-wrap ${typeColor}`}>
                  {type}
                  <span className="text-[9px] text-muted font-normal bg-white/5 px-1.5 py-0.5 rounded capitalize">
                    {siteLabel}
                  </span>
                  {isHealth && (
                    <span className="text-[9px] font-mono bg-ia/10 text-ia px-1.5 py-0.5 rounded">salud</span>
                  )}
                  {isRecovery && (
                    <span className="text-[9px] font-mono bg-green-500/10 text-green-400 px-1.5 py-0.5 rounded">✓ recuperado</span>
                  )}
                  {event.resolved && !isRecovery && (
                    <span className="text-[9px] font-mono bg-accent/10 text-accent px-1.5 py-0.5 rounded">✓ resuelto</span>
                  )}
                </div>

                <div className="text-[11px] text-gray-400 leading-tight">{event.message}</div>

                {(event.cpu_pct != null || event.mem_pct != null) && (
                  <div className="flex gap-2 text-[9px] font-mono text-muted">
                    {event.cpu_pct != null && <span>CPU {event.cpu_pct.toFixed(1)}%</span>}
                    {event.mem_pct != null && <span>RAM {event.mem_pct.toFixed(1)}%</span>}
                  </div>
                )}

                <div className="text-[9px] text-muted font-mono" title={new Date(event.created_at).toLocaleString()}>
                  {relativeTime(event.created_at)}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
