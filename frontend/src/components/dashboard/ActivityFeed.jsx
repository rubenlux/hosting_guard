import React from 'react';
import { RefreshCw } from 'lucide-react';

/**
 * Renders the recent activity feed.
 * Pure presentation — data and refresh handler come via props.
 */
export default function ActivityFeed({ events, onRefresh }) {
  return (
    <div className="card-dash">
      <div className="card-header-dash">
        <div className="text-sm font-bold">Actividad Reciente</div>
        <button onClick={onRefresh} className="text-muted hover:text-white transition-colors" title="Refrescar">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="p-4 space-y-4 max-h-[400px] overflow-y-auto">
        {events.length === 0 ? (
          <div className="text-[11px] text-muted italic p-2">Sin actividad reciente.</div>
        ) : events.map(event => {
          const isCritical = event.event_type === 'CRITICAL' || event.event_type === 'panic';
          const isWarning  = event.event_type === 'WARNING'  || event.event_type === 'throttle';
          const isRestart  = event.event_type === 'restart';
          const isHealth   = event.source === 'health';

          const dotColor = isCritical || isRestart
            ? 'bg-danger shadow-[0_0_8px_red] animate-led'
            : isWarning
            ? 'bg-warn shadow-[0_0_8px_orange] animate-led'
            : 'bg-accent shadow-[0_0_8px_rgba(0,255,136,0.5)]';

          const siteLabel = isHealth
            ? event.container_name
            : (event.container_name || '').split('_').slice(-1)[0];

          return (
            <div key={event.id || event.event_id} className="flex gap-4 items-start border-l-2 border-white/5 pl-4 ml-1">
              <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${dotColor}`} />
              <div className="space-y-1">
                <div className="text-xs font-bold text-white flex items-center gap-2">
                  {event.event_type.toUpperCase()}
                  <span className="text-[9px] text-muted font-normal bg-white/5 px-1.5 py-0.5 rounded capitalize">{siteLabel}</span>
                  {isHealth && (
                    <span className="text-[9px] font-mono bg-ia/10 text-ia px-1.5 py-0.5 rounded">salud</span>
                  )}
                  {event.resolved && (
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
                <div className="text-[9px] text-muted font-mono uppercase tracking-tighter">
                  {new Date(event.created_at).toLocaleString()}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
