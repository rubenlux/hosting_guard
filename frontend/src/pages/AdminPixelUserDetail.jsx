import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ShieldCheck, RefreshCw, ArrowRight, Activity, AlertTriangle,
  XCircle, ChevronDown, ChevronUp,
  CheckCircle2, AlertCircle, WifiOff,
} from 'lucide-react';
import {
  getAdminPixelHealth, getAdminUsers,
  getAdminPixelEvents, getPixelSiteStats,
} from '../services/api';

/* ═══════════════════════════════════════════════════════
   HELPERS
═══════════════════════════════════════════════════════ */
function timeAgo(str) {
  if (!str) return '—';
  const diff = (Date.now() - new Date(str + (str.endsWith('Z') ? '' : 'Z')).getTime()) / 1000;
  if (isNaN(diff) || diff < 0) return '—';
  if (diff < 60)    return `hace ${Math.round(diff)}s`;
  if (diff < 3600)  return `hace ${Math.round(diff / 60)}m`;
  if (diff < 86400) return `hace ${Math.round(diff / 3600)}h`;
  return `hace ${Math.round(diff / 86400)}d`;
}

function fmtTs(str) {
  if (!str) return '—';
  return new Date(str).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function fmtDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function fmtSecs(secs) {
  if (!secs) return '—';
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

function groupCount(arr, key) {
  return arr.reduce((acc, item) => {
    const k = item[key] || 'unknown';
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, {});
}

/* ═══════════════════════════════════════════════════════
   DIAGNOSTIC
═══════════════════════════════════════════════════════ */
function getDiagnostic(status, fetchErrorCount, recentCount) {
  if (status === 'dead') return {
    icon: <WifiOff className="w-3.5 h-3.5" />,
    text: 'Sin datos recientes',
    detail: 'El pixel no ha enviado eventos en más de 7 días. Verificar que el script esté instalado.',
    cls: 'border-red-500/20 bg-red-500/5 text-red-400',
  };
  if (status === 'warning') return {
    icon: <AlertTriangle className="w-3.5 h-3.5" />,
    text: 'Actividad irregular',
    detail: 'Sin eventos en las últimas 24h. Posible problema de instalación o tráfico muy bajo.',
    cls: 'border-amber-500/20 bg-amber-500/5 text-amber-400',
  };
  if (fetchErrorCount > 0) return {
    icon: <AlertCircle className="w-3.5 h-3.5" />,
    text: 'Problemas de envío',
    detail: `${fetchErrorCount} errores de envío detectados. La red o un bloqueador de anuncios puede estar impidiendo el tracking.`,
    cls: 'border-orange-500/20 bg-orange-500/5 text-orange-400',
  };
  return {
    icon: <CheckCircle2 className="w-3.5 h-3.5" />,
    text: 'Funcionando correctamente',
    detail: recentCount > 0
      ? `${recentCount} evento(s) en los últimos 10 minutos.`
      : 'El pixel está activo y enviando datos sin errores.',
    cls: 'border-emerald-500/20 bg-emerald-500/5 text-emerald-400',
  };
}

/* ═══════════════════════════════════════════════════════
   UI ATOMS
═══════════════════════════════════════════════════════ */
function StatusBadge({ status }) {
  const map = {
    active:  { label: 'Active',  cls: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20', icon: <Activity className="w-2.5 h-2.5" /> },
    warning: { label: 'Warning', cls: 'bg-amber-500/15  text-amber-400  border-amber-500/20',     icon: <AlertTriangle className="w-2.5 h-2.5" /> },
    dead:    { label: 'Dead',    cls: 'bg-red-500/15    text-red-400    border-red-500/20',       icon: <XCircle className="w-2.5 h-2.5" /> },
  };
  const s = map[status] || map.dead;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[9px] font-semibold uppercase ${s.cls}`}>
      {s.icon}{s.label}
    </span>
  );
}

const EVENT_STYLE = {
  pixel_init:   'bg-blue-500/15 text-blue-400   border border-blue-500/20',
  page_view:    'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20',
  click:        'bg-amber-500/15 text-amber-400  border border-amber-500/20',
  page_exit:    'bg-purple-500/15 text-purple-400 border border-purple-500/20',
  fetch_error:  'bg-red-500/20   text-red-400    border border-red-500/30',
  heartbeat:    'bg-cyan-500/15  text-cyan-400   border border-cyan-500/20',
  performance:  'bg-teal-500/15  text-teal-400   border border-teal-500/20',
  scroll_depth: 'bg-indigo-500/15 text-indigo-400 border border-indigo-500/20',
  js_error:     'bg-orange-500/15 text-orange-400 border border-orange-500/20',
  form_submit:  'bg-pink-500/15  text-pink-400   border border-pink-500/20',
};

function EventBadge({ type }) {
  const cls = EVENT_STYLE[type] || 'bg-white/5 text-gray-400 border border-white/10';
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[8px] font-mono font-semibold ${cls}`}>
      {type}
    </span>
  );
}

function MiniStat({ label, val, color, sub }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-[9px] text-gray-600 uppercase tracking-wider">{label}</div>
      <div className="text-sm font-bold font-mono" style={{ color: color || '#fff' }}>{val ?? '—'}</div>
      {sub && <div className="text-[8px] text-gray-600 font-mono">{sub}</div>}
    </div>
  );
}

function SectionTitle({ children }) {
  return (
    <div className="text-[9px] uppercase tracking-wider text-gray-600 font-semibold mb-2">{children}</div>
  );
}

function SimpleBar({ label, value, max, color }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 text-[9px] text-gray-500 truncate capitalize">{label}</div>
      <div className="flex-1 h-3 bg-white/5 rounded overflow-hidden">
        <div className="h-full rounded transition-all" style={{ width: `${pct}%`, background: color || '#00ff88' }} />
      </div>
      <div className="w-8 text-[9px] font-mono text-gray-400 text-right">{value}</div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   HEALTH BLOCK
═══════════════════════════════════════════════════════ */
function HealthBlock({ site, siteEvents }) {
  const now = Date.now();
  const tenMinAgo = now - 10 * 60 * 1000;

  const recentEvents = siteEvents.filter(e => new Date(e.created_at + 'Z') > tenMinAgo);
  const fetchErrors  = siteEvents.filter(e => e.event_type === 'fetch_error');
  const diagnostic   = getDiagnostic(site.status, fetchErrors.length, recentEvents.length);

  return (
    <div className="mb-4">
      {/* Health stats row */}
      <div className="grid grid-cols-4 gap-3 mb-3">
        <div className="bg-[#0d0d0d] rounded-lg border border-white/5 p-3">
          <SectionTitle>Status</SectionTitle>
          <StatusBadge status={site.status} />
        </div>
        <div className="bg-[#0d0d0d] rounded-lg border border-white/5 p-3">
          <SectionTitle>Último evento</SectionTitle>
          <div className="text-[11px] font-mono text-white">{timeAgo(site.last_seen_at)}</div>
          <div className="text-[8px] text-gray-600 mt-0.5">{fmtDate(site.last_seen_at)}</div>
        </div>
        <div className="bg-[#0d0d0d] rounded-lg border border-white/5 p-3">
          <SectionTitle>Eventos (10 min)</SectionTitle>
          <div className="text-[15px] font-bold font-mono text-[#00ff88]">{recentEvents.length}</div>
        </div>
        <div className="bg-[#0d0d0d] rounded-lg border border-white/5 p-3">
          <SectionTitle>Fetch errors</SectionTitle>
          <div className={`text-[15px] font-bold font-mono ${fetchErrors.length > 0 ? 'text-red-400' : 'text-gray-600'}`}>
            {fetchErrors.length}
          </div>
          {fetchErrors.length > 0 && (
            <div className="text-[8px] text-gray-600 mt-0.5">último: {timeAgo(fetchErrors[0]?.created_at)}</div>
          )}
        </div>
      </div>

      {/* Diagnostic banner */}
      <div className={`flex items-start gap-2.5 p-3 rounded-lg border text-[11px] ${diagnostic.cls}`}>
        <div className="shrink-0 mt-0.5">{diagnostic.icon}</div>
        <div>
          <div className="font-semibold">{diagnostic.text}</div>
          <div className="opacity-70 text-[10px] mt-0.5">{diagnostic.detail}</div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   EVENT STREAM
═══════════════════════════════════════════════════════ */
function EventStream({ siteEvents }) {
  const [filter, setFilter] = useState('all');
  const FILTERS = ['all', 'fetch_error', 'pixel_init', 'heartbeat', 'page_view', 'click'];

  const displayed = siteEvents
    .filter(e => filter === 'all' || e.event_type === filter)
    .slice(0, 50);

  const errorCount = siteEvents.filter(e => e.event_type === 'fetch_error').length;
  const lastError  = siteEvents.find(e => e.event_type === 'fetch_error');

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <SectionTitle>Event Stream — Technical Debug</SectionTitle>
        {errorCount > 0 && (
          <div className="flex items-center gap-1.5 text-[9px] text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded">
            <AlertCircle className="w-2.5 h-2.5" />
            {errorCount} fetch_error · último {timeAgo(lastError?.created_at)}
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex gap-1.5 mb-2 flex-wrap">
        {FILTERS.map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-2 py-0.5 rounded text-[8px] font-mono transition-all border ${
              filter === f
                ? (EVENT_STYLE[f] || 'bg-[#00ff88]/15 text-[#00ff88] border-[#00ff88]/20')
                : 'bg-white/5 text-gray-600 border-white/5 hover:text-white'
            }`}
          >
            {f}{f !== 'all' && siteEvents.filter(e => e.event_type === f).length > 0
              ? ` (${siteEvents.filter(e => e.event_type === f).length})`
              : ''}
          </button>
        ))}
      </div>

      {/* Event list */}
      {displayed.length === 0 ? (
        <div className="py-4 text-center text-[10px] text-gray-600 italic">
          Sin eventos de tipo "{filter}" en la muestra.
        </div>
      ) : (
        <div className="flex flex-col divide-y divide-white/5 rounded-lg border border-white/5 overflow-hidden max-h-72 overflow-y-auto">
          {displayed.map((e, i) => (
            <div
              key={e.event_id || i}
              className={`flex items-start gap-3 px-3 py-2 text-[10px] hover:bg-white/3 transition-colors ${
                e.event_type === 'fetch_error' ? 'bg-red-500/3' :
                e.event_type === 'pixel_init'  ? 'bg-blue-500/3' :
                e.event_type === 'heartbeat'   ? 'bg-cyan-500/3' : ''
              }`}
            >
              <EventBadge type={e.event_type} />
              <div className="flex-1 min-w-0">
                {e.url && (
                  <span className="text-gray-500 truncate block" title={e.url}>
                    {e.url.replace(/^https?:\/\/[^/]+/, '') || '/'}
                  </span>
                )}
              </div>
              <div className="text-[8px] text-gray-600 font-mono shrink-0">
                {fmtTs(e.created_at)}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="text-[8px] text-gray-700 mt-1.5 text-right font-mono">
        Mostrando {displayed.length} de {siteEvents.filter(e => filter === 'all' || e.event_type === filter).length} eventos en muestra
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   ANALYTICS (from stats endpoint)
═══════════════════════════════════════════════════════ */
function SiteAnalytics({ siteId, siteEvents }) {
  const [stats, setStats]     = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPixelSiteStats(siteId, 30)
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [siteId]);

  /* device / browser from events (fast, no extra call) */
  const deviceCounts  = groupCount(siteEvents.filter(e => e.device), 'device');
  const browserCounts = groupCount(siteEvents.filter(e => e.browser), 'browser');
  const maxDevice  = Math.max(...Object.values(deviceCounts), 1);
  const maxBrowser = Math.max(...Object.values(browserCounts), 1);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-3 text-[10px] text-gray-500">
        <RefreshCw className="w-3 h-3 animate-spin" /> Cargando analytics…
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Key metrics */}
      {stats && (
        <div>
          <SectionTitle>Métricas (últimos 30 días)</SectionTitle>
          <div className="grid grid-cols-5 gap-3">
            <MiniStat label="Sesiones"    val={stats.unique_sessions}  color="#00aaff" />
            <MiniStat label="Visitors"    val={stats.unique_visitors}  color="#00ff88" />
            <MiniStat label="Eventos"     val={stats.total_events}     color="#ffaa00" />
            <MiniStat label="Bounce"      val={stats.bounce_rate != null ? `${stats.bounce_rate}%` : null} color="#ff6b6b" />
            <MiniStat label="Avg tiempo"  val={fmtSecs(stats.avg_time_on_page)} color="#4ecdc4" />
          </div>
        </div>
      )}

      {/* Pages + referrers */}
      {stats && (stats.top_pages?.length > 0 || stats.top_referrers?.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          {stats.top_pages?.length > 0 && (
            <div>
              <SectionTitle>Top páginas</SectionTitle>
              <div className="flex flex-col gap-1">
                {stats.top_pages.slice(0, 6).map((p, i) => (
                  <div key={i} className="flex justify-between text-[10px]">
                    <span className="text-gray-400 truncate w-44 font-mono" title={p.url}>
                      {p.url?.replace(/^https?:\/\/[^/]+/, '') || '/'}
                    </span>
                    <span className="font-mono text-white ml-2">{p.views}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {stats.top_referrers?.length > 0 && (
            <div>
              <SectionTitle>Fuentes de tráfico</SectionTitle>
              <div className="flex flex-col gap-1">
                {stats.top_referrers.slice(0, 6).map((r, i) => (
                  <div key={i} className="flex justify-between text-[10px]">
                    <span className="text-gray-400 truncate w-44">{r.referrer || 'Directo'}</span>
                    <span className="font-mono text-white ml-2">{r.count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tech info: device + browser + OS */}
      <div className="grid grid-cols-3 gap-4">
        <div>
          <SectionTitle>Dispositivos (eventos)</SectionTitle>
          {Object.keys(deviceCounts).length === 0 ? (
            <div className="text-[9px] text-gray-600 italic">Sin datos</div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {Object.entries(deviceCounts).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <SimpleBar key={k} label={k} value={v} max={maxDevice} color="#00aaff" />
              ))}
            </div>
          )}
        </div>
        <div>
          <SectionTitle>Navegadores (eventos)</SectionTitle>
          {Object.keys(browserCounts).length === 0 ? (
            <div className="text-[9px] text-gray-600 italic">Sin datos</div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {Object.entries(browserCounts).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k, v]) => (
                <SimpleBar key={k} label={k} value={v} max={maxBrowser} color="#ffaa00" />
              ))}
            </div>
          )}
        </div>
        <div>
          <SectionTitle>SO (stats 30d)</SectionTitle>
          {!stats?.by_os?.length ? (
            <div className="text-[9px] text-gray-600 italic">Sin datos</div>
          ) : (
            <div className="flex flex-col gap-1.5">
              {stats.by_os.slice(0, 5).map((o, i) => (
                <SimpleBar key={i} label={o.os} value={o.count}
                  max={Math.max(...stats.by_os.map(x => x.count), 1)} color="#aa00ff" />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Event type breakdown from stats */}
      {stats?.by_event_type?.length > 0 && (
        <div>
          <SectionTitle>Tipos de evento (stats 30d)</SectionTitle>
          <div className="grid grid-cols-3 gap-2">
            {stats.by_event_type.map((et, i) => (
              <div key={i} className="flex items-center justify-between bg-[#0d0d0d] rounded px-2.5 py-1.5 border border-white/5">
                <EventBadge type={et.event_type} />
                <span className="font-mono text-[11px] text-white">{et.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* JS Errors */}
      {stats?.js_errors?.length > 0 && (
        <div>
          <SectionTitle>JS Errors detectados</SectionTitle>
          <div className="flex flex-col gap-1">
            {stats.js_errors.map((e, i) => (
              <div key={i} className="flex justify-between items-start text-[9px] bg-orange-500/5 border border-orange-500/10 rounded px-2 py-1.5">
                <span className="text-orange-400 font-mono truncate flex-1 mr-2" title={e.message}>{e.message || '(sin mensaje)'}</span>
                <span className="text-gray-500 font-mono shrink-0">{e.count}×</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Performance */}
      {stats?.performance && (stats.performance.avg_load_ms || stats.performance.avg_ttfb_ms) && (
        <div>
          <SectionTitle>Performance (stats 30d)</SectionTitle>
          <div className="flex gap-6">
            {stats.performance.avg_load_ms && (
              <MiniStat label="Avg Load Time" val={`${Math.round(stats.performance.avg_load_ms)}ms`} color="#4ecdc4" />
            )}
            {stats.performance.avg_ttfb_ms && (
              <MiniStat label="Avg TTFB" val={`${Math.round(stats.performance.avg_ttfb_ms)}ms`} color="#00aaff" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   SESSION GROUPING LOGIC
═══════════════════════════════════════════════════════ */
function buildSessions(events) {
  // Sort oldest→newest for chronological grouping
  const sorted = [...events].sort((a, b) =>
    new Date(a.created_at) - new Date(b.created_at)
  );

  const SESSION_GAP_MS = 30 * 60 * 1000; // 30 min fallback window
  const sessions = [];
  const sessionMap = {}; // session_id → session index

  for (const ev of sorted) {
    const sid = ev.session_id || null;
    const ts  = new Date(ev.created_at).getTime();

    if (sid && sessionMap[sid] !== undefined) {
      // known session_id → append
      sessions[sessionMap[sid]].events.push(ev);
      sessions[sessionMap[sid]].end = ts;
    } else if (sid) {
      // new session_id
      const idx = sessions.length;
      sessions.push({ id: sid, key: sid, events: [ev], start: ts, end: ts });
      sessionMap[sid] = idx;
    } else {
      // no session_id → try to attach to last open session by visitor_id or time gap
      const vid = ev.visitor_id;
      let attached = false;
      if (vid) {
        for (let i = sessions.length - 1; i >= 0; i--) {
          const s = sessions[i];
          const lastEvVid = s.events[s.events.length - 1]?.visitor_id;
          if (lastEvVid === vid && ts - s.end < SESSION_GAP_MS) {
            s.events.push(ev);
            s.end = ts;
            attached = true;
            break;
          }
        }
      }
      if (!attached) {
        // open new anonymous session
        const key = `anon_${ts}_${Math.random().toString(36).slice(2, 6)}`;
        sessions.push({ id: null, key, events: [ev], start: ts, end: ts });
      }
    }
  }

  // Sort newest first and limit to 50
  return sessions
    .sort((a, b) => b.start - a.start)
    .slice(0, 50)
    .map(s => {
      const durationSecs = Math.round((s.end - s.start) / 1000);
      const hasErrors    = s.events.some(e => e.event_type === 'fetch_error' || e.event_type === 'js_error');
      const isShort      = durationSecs < 10 && s.events.filter(e => e.event_type === 'page_view').length <= 1;
      const diagnosis = hasErrors ? 'errors' : isShort ? 'bounce' : 'normal';
      return { ...s, durationSecs, hasErrors, diagnosis };
    });
}

/* ─── session diagnosis label ─── */
function SessionDiagnosis({ diagnosis, hasErrors }) {
  if (hasErrors) return (
    <span className="inline-flex items-center gap-1 text-[8px] font-semibold px-1.5 py-0.5 rounded border bg-red-500/15 text-red-400 border-red-500/20">
      <XCircle className="w-2 h-2" /> Con errores
    </span>
  );
  if (diagnosis === 'bounce') return (
    <span className="inline-flex items-center gap-1 text-[8px] font-semibold px-1.5 py-0.5 rounded border bg-amber-500/15 text-amber-400 border-amber-500/20">
      <AlertTriangle className="w-2 h-2" /> Posible rebote
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-[8px] font-semibold px-1.5 py-0.5 rounded border bg-emerald-500/15 text-emerald-400 border-emerald-500/20">
      <CheckCircle2 className="w-2 h-2" /> Normal
    </span>
  );
}

/* ─── single event in timeline ─── */
function TimelineEvent({ ev }) {
  const [open, setOpen] = useState(false);
  const isError = ev.event_type === 'fetch_error' || ev.event_type === 'js_error';

  // parse properties — admin events have them serialized or as object
  let props = ev.properties;
  if (typeof props === 'string') {
    try { props = JSON.parse(props); } catch { props = null; }
  }
  const hasProps = props && typeof props === 'object' && Object.keys(props).length > 0;

  return (
    <div className={`group border-l-2 pl-3 pb-3 relative ${isError ? 'border-red-500/60' : 'border-white/10'}`}>
      {/* dot */}
      <div className={`absolute -left-[5px] top-0.5 w-2 h-2 rounded-full border ${
        isError ? 'bg-red-500 border-red-400' :
        ev.event_type === 'pixel_init' ? 'bg-blue-500 border-blue-400' :
        ev.event_type === 'heartbeat'  ? 'bg-cyan-500 border-cyan-400' :
        ev.event_type === 'page_view'  ? 'bg-emerald-500 border-emerald-400' :
        ev.event_type === 'click'      ? 'bg-amber-500 border-amber-400' :
        'bg-gray-700 border-gray-600'
      }`} />

      {/* main row */}
      <div
        className={`flex items-start gap-2 cursor-pointer ${hasProps ? 'hover:opacity-80' : ''}`}
        onClick={() => hasProps && setOpen(o => !o)}
      >
        <span className="text-[8px] text-gray-600 font-mono shrink-0 pt-0.5 w-16">
          {fmtTs(ev.created_at)}
        </span>
        <EventBadge type={ev.event_type} />
        <div className="flex-1 min-w-0">
          {ev.url && (
            <span className="text-[9px] text-gray-400 font-mono truncate block" title={ev.url}>
              {ev.url.replace(/^https?:\/\/[^/]+/, '') || '/'}
            </span>
          )}
          {/* fetch_error inline detail */}
          {ev.event_type === 'fetch_error' && props && (
            <div className="text-[9px] text-red-400 font-mono mt-0.5">
              {props.failed_event && <span className="mr-2">failed: {props.failed_event}</span>}
              {props.error && <span>{props.error}</span>}
            </div>
          )}
          {/* js_error inline detail */}
          {ev.event_type === 'js_error' && props?.message && (
            <div className="text-[9px] text-orange-400 font-mono truncate mt-0.5" title={props.message}>
              {props.message}
            </div>
          )}
          {/* UTM inline */}
          {props?.utm && (
            <div className="text-[8px] text-purple-400 font-mono mt-0.5">
              utm: {Object.entries(props.utm).map(([k, v]) => `${k.replace('utm_', '')}=${v}`).join(' · ')}
            </div>
          )}
        </div>
        {hasProps && (
          <span className="text-[7px] text-gray-700 shrink-0 pt-0.5">
            {open ? '▲' : '▼'}
          </span>
        )}
      </div>

      {/* expanded properties */}
      {open && hasProps && (
        <div className="mt-1.5 ml-16 bg-[#111] border border-white/5 rounded-lg p-2.5 text-[8px] font-mono">
          {/* device / browser / OS */}
          {(ev.device || ev.browser || ev.os) && (
            <div className="flex gap-3 mb-2 pb-2 border-b border-white/5 text-gray-500">
              {ev.device  && <span>device: <span className="text-gray-300">{ev.device}</span></span>}
              {ev.browser && <span>browser: <span className="text-gray-300">{ev.browser}</span></span>}
              {ev.os      && <span>os: <span className="text-gray-300">{ev.os}</span></span>}
            </div>
          )}
          {/* all properties */}
          <div className="flex flex-col gap-1">
            {Object.entries(props).map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <span className="text-gray-600 w-28 shrink-0">{k}:</span>
                <span className="text-gray-300 break-all">
                  {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── single session card ─── */
function SessionCard({ session }) {
  const [open, setOpen] = useState(false);
  const [evFilter, setEvFilter] = useState('all');

  const pageViews = session.events.filter(e => e.event_type === 'page_view').length;
  const errors    = session.events.filter(e => e.event_type === 'fetch_error' || e.event_type === 'js_error').length;

  // timeline: chronological order
  const timeline = [...session.events].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  const filtered = evFilter === 'all' ? timeline : timeline.filter(e => {
    if (evFilter === 'errors') return e.event_type === 'fetch_error' || e.event_type === 'js_error';
    return e.event_type === evFilter;
  });

  // Device/browser from first event that has them
  const refEv = timeline.find(e => e.device || e.browser);

  const shortId = session.id
    ? session.id.slice(0, 8) + '…'
    : '(anon)';

  return (
    <div className={`rounded-lg border overflow-hidden ${
      session.hasErrors ? 'border-red-500/20' : 'border-white/5'
    }`}>
      {/* session header */}
      <div
        className="px-3 py-2.5 flex items-center gap-3 cursor-pointer hover:bg-white/3 transition-colors bg-[#0f0f0f]"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[9px] font-mono text-gray-400">{shortId}</span>
            <SessionDiagnosis diagnosis={session.diagnosis} hasErrors={session.hasErrors} />
          </div>
          <div className="flex items-center gap-3 mt-0.5 text-[8px] text-gray-600">
            <span>{fmtDate(new Date(session.start).toISOString())}</span>
            {refEv && (
              <span className="capitalize">{[refEv.device, refEv.browser].filter(Boolean).join(' · ')}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 text-[9px] font-mono shrink-0">
          <span className="text-gray-500">{fmtSecs(session.durationSecs)}</span>
          <span className="text-gray-400">{session.events.length} ev.</span>
          <span className="text-gray-600">{pageViews} pv</span>
          {errors > 0 && <span className="text-red-400">{errors} err</span>}
        </div>
        <span className="text-gray-600 text-[9px]">{open ? '▲' : '▼'}</span>
      </div>

      {/* session timeline */}
      {open && (
        <div className="border-t border-white/5 bg-[#0a0a0a] px-3 pt-3 pb-2">
          {/* filter pills */}
          <div className="flex gap-1.5 mb-3 flex-wrap">
            {['all', 'errors', 'page_view', 'click'].map(f => (
              <button
                key={f}
                onClick={e => { e.stopPropagation(); setEvFilter(f); }}
                className={`px-2 py-0.5 rounded text-[7px] font-mono border transition-all ${
                  evFilter === f
                    ? 'bg-white/10 text-white border-white/20'
                    : 'bg-transparent text-gray-600 border-white/5 hover:text-gray-400'
                }`}
              >
                {f === 'errors' ? `solo errores (${errors})` : f}
              </button>
            ))}
          </div>

          {/* timeline list */}
          {filtered.length === 0 ? (
            <div className="text-[9px] text-gray-700 italic py-2">Sin eventos con este filtro.</div>
          ) : (
            <div className="pl-1">
              {filtered.map((ev, i) => <TimelineEvent key={ev.event_id || i} ev={ev} />)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── session replay panel ─── */
function SessionReplay({ siteEvents }) {
  const [sessionFilter, setSessionFilter] = useState('all');

  const sessions = useMemo(() => buildSessions(siteEvents), [siteEvents]);

  const displayed = useMemo(() => {
    if (sessionFilter === 'all')    return sessions;
    if (sessionFilter === 'errors') return sessions.filter(s => s.hasErrors);
    if (sessionFilter === 'active') return sessions.filter(s => {
      const age = (Date.now() - s.end) / 1000;
      return age < 3600; // active = last event < 1h ago
    });
    return sessions;
  }, [sessions, sessionFilter]);

  if (siteEvents.length === 0) {
    return (
      <div className="text-[10px] text-gray-600 italic py-3">
        Sin eventos en la muestra para reconstruir sesiones.
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <SectionTitle>User Sessions — Session Replay Light</SectionTitle>
        <span className="text-[8px] text-gray-700 font-mono">{sessions.length} sesiones · máx 50</span>
      </div>

      {/* global filters */}
      <div className="flex gap-1.5 mb-3">
        {[
          { id: 'all',    label: `Todas (${sessions.length})` },
          { id: 'errors', label: `Con errores (${sessions.filter(s => s.hasErrors).length})` },
          { id: 'active', label: 'Activas (<1h)' },
        ].map(f => (
          <button
            key={f.id}
            onClick={() => setSessionFilter(f.id)}
            className={`px-2.5 py-1 rounded text-[8px] font-mono border transition-all ${
              sessionFilter === f.id
                ? 'bg-[#00ff88]/10 text-[#00ff88] border-[#00ff88]/20'
                : 'bg-white/5 text-gray-600 border-white/5 hover:text-white'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* session list */}
      {displayed.length === 0 ? (
        <div className="text-[9px] text-gray-600 italic py-3">Sin sesiones con este filtro.</div>
      ) : (
        <div className="flex flex-col gap-2">
          {displayed.map(s => <SessionCard key={s.key} session={s} />)}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   SITE PANEL (expandable)
═══════════════════════════════════════════════════════ */
function SitePanel({ site, allEvents }) {
  const [open, setOpen] = useState(false);

  /* filter once and memoize */
  const siteEvents = useMemo(
    () => allEvents.filter(e => e.site_id === site.site_id),
    [allEvents, site.site_id]
  );

  return (
    <div className="border-b border-white/5 last:border-0">
      {/* Header row — always visible */}
      <div
        className="px-4 py-3 flex items-center gap-4 hover:bg-white/3 cursor-pointer transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[12px] font-medium text-white">{site.name}</span>
            {site.domain && (
              <span className="text-[9px] text-gray-500 font-mono bg-white/5 px-1.5 py-0.5 rounded">
                {site.domain}
              </span>
            )}
          </div>
          <div className="text-[8px] text-gray-700 font-mono">{site.site_id}</div>
        </div>
        <StatusBadge status={site.status} />
        <div className="text-right shrink-0">
          <div className="text-[10px] text-white font-mono">{timeAgo(site.last_seen_at)}</div>
          <div className="text-[8px] text-gray-600">{fmtDate(site.last_seen_at)}</div>
        </div>
        <div className="text-[10px] text-gray-600 font-mono w-14 text-right shrink-0">
          {site.total_events} ev.
        </div>
        <div className="shrink-0 text-gray-500">
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </div>

      {/* Expanded panel */}
      {open && (
        <div className="px-4 pb-5 pt-1 border-t border-white/5 bg-[#0c0c0c]">

          {/* 1. Health + diagnostic */}
          <div className="mt-4">
            <SectionTitle>Pixel Health</SectionTitle>
            <HealthBlock site={site} siteEvents={siteEvents} />
          </div>

          {/* 2. Analytics */}
          <div className="mt-4 pt-4 border-t border-white/5">
            <SectionTitle>Analytics</SectionTitle>
            <SiteAnalytics siteId={site.site_id} siteEvents={siteEvents} />
          </div>

          {/* 3. Event Stream */}
          <div className="mt-4 pt-4 border-t border-white/5">
            <EventStream siteEvents={siteEvents} />
          </div>

          {/* 4. Session Replay */}
          <div className="mt-4 pt-4 border-t border-white/5">
            <SessionReplay siteEvents={siteEvents} />
          </div>

        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   MAIN
═══════════════════════════════════════════════════════ */
export default function AdminPixelUserDetail() {
  const navigate  = useNavigate();
  const { user_id } = useParams();

  const [health,    setHealth]    = useState([]);
  const [users,     setUsers]     = useState([]);
  const [allEvents, setAllEvents] = useState([]);
  const [loading,   setLoading]   = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [h, u, ev] = await Promise.all([
        getAdminPixelHealth(),
        getAdminUsers(),
        getAdminPixelEvents(1000, 0),
      ]);
      setHealth(h);
      setUsers(u);
      setAllEvents(Array.isArray(ev) ? ev : []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const userInfo = useMemo(
    () => users.find(u => String(u.user_id) === String(user_id)),
    [users, user_id]
  );

  const sites = useMemo(
    () => health.filter(s => String(s.user_id) === String(user_id)),
    [health, user_id]
  );

  /* user-level summary from events */
  const userEventCount = useMemo(
    () => allEvents.filter(e => sites.some(s => s.site_id === e.site_id)).length,
    [allEvents, sites]
  );

  const userFetchErrors = useMemo(
    () => allEvents.filter(e => sites.some(s => s.site_id === e.site_id) && e.event_type === 'fetch_error').length,
    [allEvents, sites]
  );

  return (
    <div className="fixed inset-0 flex bg-[#0a0a0a] text-white overflow-hidden" style={{ fontFamily: 'Inter, sans-serif' }}>

      {/* ── SIDEBAR ── */}
      <aside className="w-56 shrink-0 flex flex-col border-r border-white/5 bg-[#0d0d0d]">
        <div className="px-5 py-5 border-b border-white/5">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#00ff88]/10 border border-[#00ff88]/20 flex items-center justify-center">
              <ShieldCheck className="w-4 h-4 text-[#00ff88]" />
            </div>
            <div>
              <div className="text-[11px] font-bold tracking-widest text-white uppercase">Admin Console</div>
              <div className="text-[9px] text-[#00ff88] font-mono tracking-widest">KINETIC COMMAND</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 flex flex-col gap-1">
          <button
            onClick={() => navigate('/admin')}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[11px] font-medium text-gray-500 hover:bg-white/5 hover:text-white border border-transparent transition-all text-left"
          >
            <ArrowRight className="w-3.5 h-3.5 shrink-0 rotate-180" />
            Admin
          </button>
          <button
            onClick={() => navigate('/admin/pixel-users')}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-[11px] font-medium text-gray-400 hover:bg-white/5 hover:text-white border border-transparent transition-all text-left"
          >
            <ArrowRight className="w-3.5 h-3.5 shrink-0 rotate-180" />
            Pixel Users
          </button>
          <div className="mt-1 px-3 py-2.5 rounded-lg bg-[#00ff88]/10 border border-[#00ff88]/20 text-[11px] font-medium text-[#00ff88] truncate leading-tight">
            {loading ? '…' : (userInfo?.email || `User #${user_id}`)}
          </div>

          {/* Quick info */}
          {!loading && (
            <div className="mt-4 px-3 flex flex-col gap-2">
              <div className="flex justify-between text-[10px]">
                <span className="text-gray-600">Sites</span>
                <span className="text-white font-mono">{sites.length}</span>
              </div>
              <div className="flex justify-between text-[10px]">
                <span className="text-gray-600">Activos</span>
                <span className="text-emerald-400 font-mono">{sites.filter(s => s.status === 'active').length}</span>
              </div>
              <div className="flex justify-between text-[10px]">
                <span className="text-gray-600">Eventos muestra</span>
                <span className="text-gray-400 font-mono">{userEventCount}</span>
              </div>
              {userFetchErrors > 0 && (
                <div className="flex justify-between text-[10px]">
                  <span className="text-red-500">Fetch errors</span>
                  <span className="text-red-400 font-mono">{userFetchErrors}</span>
                </div>
              )}
            </div>
          )}
        </nav>
      </aside>

      {/* ── MAIN ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Header */}
        <header className="h-14 shrink-0 flex items-center justify-between px-6 border-b border-white/5 bg-[#0d0d0d]">
          <div className="flex items-center gap-3">
            <h1 className="text-[13px] font-semibold text-white truncate max-w-xs">
              {loading ? 'Cargando…' : (userInfo?.email || `User #${user_id}`)}
            </h1>
            <span className="text-[10px] text-gray-500 font-mono">
              {sites.length} sites · {sites.filter(s => s.status === 'active').length} activos
            </span>
            {userFetchErrors > 0 && !loading && (
              <span className="flex items-center gap-1 text-[9px] text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-full">
                <AlertCircle className="w-2.5 h-2.5" />
                {userFetchErrors} fetch errors
              </span>
            )}
          </div>
          <button
            onClick={load}
            className="w-8 h-8 rounded-lg border border-white/10 flex items-center justify-center hover:bg-white/5 transition-all"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-5">

          {/* User summary cards */}
          {!loading && sites.length > 0 && (
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-2">Sites</div>
                <div className="text-2xl font-bold font-mono text-[#00aaff]">{sites.length}</div>
              </div>
              <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-2">Activos</div>
                <div className="text-2xl font-bold font-mono text-emerald-400">{sites.filter(s => s.status === 'active').length}</div>
              </div>
              <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-2">Total eventos (DB)</div>
                <div className="text-2xl font-bold font-mono text-[#ffaa00]">
                  {sites.reduce((sum, s) => sum + (s.total_events || 0), 0).toLocaleString()}
                </div>
              </div>
              <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-2">Fetch errors (muestra)</div>
                <div className={`text-2xl font-bold font-mono ${userFetchErrors > 0 ? 'text-red-400' : 'text-gray-600'}`}>
                  {userFetchErrors}
                </div>
              </div>
            </div>
          )}

          {/* Sites list */}
          <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
            <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
              <span className="text-[11px] font-semibold text-white">Sites de Pixel</span>
              <span className="text-[9px] text-gray-600">
                Expandir para ver health, analytics y event stream
              </span>
            </div>

            {loading ? (
              <div className="p-10 flex justify-center">
                <RefreshCw className="w-4 h-4 animate-spin text-gray-500" />
              </div>
            ) : sites.length === 0 ? (
              <div className="p-10 text-center text-gray-600 text-xs italic">
                Este usuario no tiene sites de pixel registrados.
              </div>
            ) : (
              <>
                <div className="px-4 py-2 bg-[#0d0d0d] border-b border-white/5 flex items-center gap-4 text-[8px] uppercase tracking-wider text-gray-700">
                  <div className="flex-1">Site / Domain / ID</div>
                  <div className="w-20 text-center">Status</div>
                  <div className="w-32 text-right">Último evento</div>
                  <div className="w-14 text-right">Eventos</div>
                  <div className="w-4" />
                </div>
                {sites.map(site => (
                  <SitePanel
                    key={site.site_id}
                    site={site}
                    allEvents={allEvents}
                  />
                ))}
              </>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
