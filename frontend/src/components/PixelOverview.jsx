/**
 * PixelOverview — compact analytics widget for the main Dashboard.
 * Fetches data from the first pixel site found, renders:
 *   - Business KPIs (page views, sessions, bounce rate, active users)
 *   - Insights chips (trend, device, country, top page)
 *   - Compact TimeSeries (7d, area + bezier)
 *   - Mini Realtime feed (5 events)
 *   - Top 3 pages
 *
 * Keeps PixelAnalytics page as the detailed view — this is summary only.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { Activity, Users, Clock, Zap, ArrowRight, Loader, Globe, Monitor } from 'lucide-react';

// ── Shared micro-utilities (same logic as PixelAnalytics, inlined to avoid
//    creating a circular import from a large page component) ─────────────────

function formatTimeAgo(iso) {
  if (!iso) return '';
  const s = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (s < 60)   return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

function countryFlag(code) {
  if (!code || code.length !== 2) return code || '??';
  const base = 127397;
  return String.fromCodePoint(...code.toUpperCase().split('').map(c => base + c.charCodeAt(0)));
}

function bezierPath(pts) {
  if (!pts || pts.length === 0) return '';
  if (pts.length === 1) return `M ${pts[0][0]},${pts[0][1]}`;
  let d = `M ${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const dx = (x1 - x0) * 0.4;
    d += ` C ${x0 + dx},${y0} ${x1 - dx},${y1} ${x1},${y1}`;
  }
  return d;
}

function areaPath(pts, bottom) {
  if (!pts || pts.length === 0) return '';
  return `${bezierPath(pts)} L ${pts[pts.length - 1][0]},${bottom} L ${pts[0][0]},${bottom} Z`;
}

// ── Insights engine (same logic as PixelAnalytics) ─────────────────────────

function computeInsights(stats, devices, countries, pages, timeseries) {
  const out = [];
  if (!stats) return out;

  if (timeseries?.length >= 6) {
    const half = Math.floor(timeseries.length / 2);
    const a = timeseries.slice(0, half).reduce((s, d) => s + (d.page_views || 0), 0);
    const b = timeseries.slice(half).reduce((s, d) => s + (d.page_views || 0), 0);
    if (a > 0) {
      const pct = Math.round(((b - a) / a) * 100);
      if (pct > 5)       out.push({ icon: '📈', main: `+${pct}%`, sub: 'tráfico subiendo', type: 'up' });
      else if (pct < -5) out.push({ icon: '📉', main: `${pct}%`,  sub: 'tráfico bajando',  type: 'down' });
    }
  }

  if (devices?.length > 0) {
    const total = devices.reduce((s, d) => s + Number(d.count), 0);
    const mob   = devices.find(d => d.device === 'mobile');
    if (mob && total > 0) {
      const pct = Math.round((Number(mob.count) / total) * 100);
      out.push({
        icon: '📱',
        main: pct >= 50 ? `${pct}% móvil` : `${100 - pct}% desktop`,
        sub:  pct >= 50 ? 'optimiza para móvil' : 'mayoría en desktop',
        type: 'device',
      });
    }
  }

  if (countries?.length > 0) {
    const total = countries.reduce((s, c) => s + Number(c.count), 0);
    const top   = countries[0];
    const pct   = Math.round((Number(top.count) / total) * 100);
    out.push({
      icon: countryFlag(top.country),
      main: `${pct}% ${top.country}`,
      sub:  'mercado principal',
      type: 'geo',
    });
  }

  if (pages?.length > 0) {
    const p    = pages[0];
    const path = (p.url || '/').replace(/^https?:\/\/[^/]+/, '') || '/';
    out.push({
      icon: '🔥',
      main: path.length > 18 ? path.slice(0, 16) + '…' : path,
      sub:  `${p.views} vistas`,
      type: 'page',
    });
  }

  return out.slice(0, 4);
}

const INSIGHT_COLOR = {
  up:     'bg-[#00ff88]/[0.07] border-[#00ff88]/20 text-[#00ff88]',
  down:   'bg-[#ff4466]/[0.07] border-[#ff4466]/20 text-[#ff4466]',
  device: 'bg-[#00aaff]/[0.07] border-[#00aaff]/20 text-[#00aaff]',
  geo:    'bg-[#aa44ff]/[0.07] border-[#aa44ff]/20 text-[#aa44ff]',
  page:   'bg-[#ffaa00]/[0.07] border-[#ffaa00]/20 text-[#ffaa00]',
  warn:   'bg-[#ff8800]/[0.07] border-[#ff8800]/20 text-[#ff8800]',
};

// ── Compact TimeSeries (hero chart, 7d) ─────────────────────────────────────

function MiniTimeSeries({ data }) {
  const [tooltip, setTooltip] = useState(null);
  const [clipW, setClipW]     = useState(0);
  const r1 = useRef(null);
  const r2 = useRef(null);

  const W = 480, H = 110, padL = 26, padR = 8, padT = 12, padB = 24;
  const cW = W - padL - padR;
  const cH = H - padT - padB;

  useEffect(() => {
    setClipW(0);
    r1.current = requestAnimationFrame(() => {
      r2.current = requestAnimationFrame(() => setClipW(cW + padR + 4));
    });
    return () => { cancelAnimationFrame(r1.current); cancelAnimationFrame(r2.current); };
  }, [data, cW]);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[110px] text-xs text-muted italic">
        Sin datos todavía
      </div>
    );
  }

  const n    = data.length;
  const maxY = Math.max(...data.map(d => Math.max(d.page_views || 0, d.sessions || 0)), 1);

  const xOf = i => padL + (n > 1 ? (i / (n - 1)) * cW : cW / 2);
  const yOf = v => padT + cH - Math.min((v / maxY) * cH, cH);

  const pvPts  = data.map((d, i) => [xOf(i), yOf(d.page_views || 0)]);
  const sesPts = data.map((d, i) => [xOf(i), yOf(d.sessions   || 0)]);
  const bottom = padT + cH;

  const step  = Math.max(1, Math.floor(n / 4));
  const xIdxs = [];
  for (let i = 0; i < n; i += step) xIdxs.push(i);
  if (xIdxs[xIdxs.length - 1] !== n - 1) xIdxs.push(n - 1);

  const colWidth = n > 1 ? cW / (n - 1) : cW;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full select-none"
      style={{ height: 120 }}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <linearGradient id="ovPvArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#00ff88" stopOpacity="0.28" />
          <stop offset="70%"  stopColor="#00ff88" stopOpacity="0.05" />
          <stop offset="100%" stopColor="#00ff88" stopOpacity="0"    />
        </linearGradient>
        <linearGradient id="ovSesArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#00aaff" stopOpacity="0.16" />
          <stop offset="100%" stopColor="#00aaff" stopOpacity="0"    />
        </linearGradient>
        <clipPath id="ovReveal">
          <rect
            x={padL - 4} y={0}
            width={clipW}
            height={H}
            style={{ transition: clipW > 0 ? 'width 0.85s cubic-bezier(0.4,0,0.2,1)' : 'none' }}
          />
        </clipPath>
      </defs>

      {/* Baseline */}
      <line x1={padL} y1={bottom} x2={W - padR} y2={bottom}
            stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
      {/* Mid grid */}
      <line x1={padL} y1={yOf(Math.round(maxY / 2))} x2={W - padR} y2={yOf(Math.round(maxY / 2))}
            stroke="rgba(255,255,255,0.04)" strokeWidth="1" />

      {/* Animated chart */}
      <g clipPath="url(#ovReveal)">
        <path d={areaPath(pvPts,  bottom)} fill="url(#ovPvArea)"  />
        <path d={areaPath(sesPts, bottom)} fill="url(#ovSesArea)" />
        <path d={bezierPath(pvPts)}  fill="none" stroke="#00ff88" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" />
        <path d={bezierPath(sesPts)} fill="none" stroke="#00aaff" strokeWidth="1.5"
              strokeLinecap="round" strokeLinejoin="round" strokeDasharray="4,3" />
      </g>

      {/* Hover columns */}
      {data.map((d, i) => {
        const cx = xOf(i);
        const hw = colWidth / 2;
        return (
          <rect key={i}
            x={Math.max(padL, cx - hw)} y={padT}
            width={Math.min(hw * 2, W - padR - Math.max(padL, cx - hw))}
            height={cH}
            fill="transparent"
            style={{ cursor: 'crosshair' }}
            onMouseEnter={() => setTooltip(i)}
            onMouseLeave={() => setTooltip(null)}
          />
        );
      })}

      {/* Tooltip */}
      {tooltip !== null && (() => {
        const flip  = tooltip > n * 0.62;
        const ttx   = flip ? xOf(tooltip) - 84 : xOf(tooltip) + 8;
        const tty   = padT + 2;
        const pv    = data[tooltip]?.page_views ?? 0;
        const ses   = data[tooltip]?.sessions   ?? 0;
        const label = data[tooltip]?.label || data[tooltip]?.day?.slice(5) || '';
        return (
          <g>
            <line x1={xOf(tooltip)} y1={padT} x2={xOf(tooltip)} y2={bottom}
                  stroke="rgba(255,255,255,0.2)" strokeWidth="1" strokeDasharray="3,2" />
            <rect x={ttx} y={tty} width="80" height="50" rx="6"
                  fill="rgba(6,6,6,0.96)" stroke="rgba(255,255,255,0.1)" strokeWidth="0.6" />
            <text x={ttx + 7} y={tty + 13} fontSize="7" fill="rgba(255,255,255,0.45)">{label}</text>
            <text x={ttx + 7} y={tty + 28} fontSize="10" fill="#00ff88">▲ {pv} vistas</text>
            <text x={ttx + 7} y={tty + 43} fontSize="10" fill="#00aaff">◈ {ses} sesiones</text>
          </g>
        );
      })()}

      {/* X-axis */}
      {xIdxs.map(i => (
        <text key={i} x={xOf(i)} y={H - 3} textAnchor="middle"
              fontSize="7" fill="rgba(255,255,255,0.35)">
          {data[i]?.label || data[i]?.day?.slice(5)}
        </text>
      ))}
    </svg>
  );
}

// ── Mini Realtime feed (5 events) ───────────────────────────────────────────

function MiniRealtime({ siteId }) {
  const [rt, setRt]           = useState(null);
  const [newSet, setNewSet]   = useState(new Set());
  const prevTimesRef          = useRef(new Set());

  useEffect(() => {
    if (!siteId) return;
    const fetch = () =>
      api.get(`/pixel/sites/${siteId}/realtime`)
        .then(r => {
          const d = r.data;
          const news = new Set(
            (d.recent_pages || [])
              .filter(p => p.created_at && !prevTimesRef.current.has(p.created_at))
              .map(p => p.created_at)
          );
          if (news.size > 0) {
            setNewSet(news);
            setTimeout(() => setNewSet(new Set()), 2500);
          }
          prevTimesRef.current = new Set((d.recent_pages || []).map(p => p.created_at));
          setRt(d);
        })
        .catch(() => {});

    fetch();
    const iv = setInterval(fetch, 10000);
    return () => clearInterval(iv);
  }, [siteId]);

  if (!rt) return (
    <div className="flex items-center justify-center py-6">
      <Loader className="w-4 h-4 animate-spin text-accent" />
    </div>
  );

  const pages = (rt.recent_pages || []).slice(0, 5);

  return (
    <div>
      {/* KPIs */}
      <div className="flex gap-3 mb-3">
        <div className="flex-1 text-center bg-white/[0.04] rounded-xl py-2">
          <div className="text-xl font-black font-mono text-glow" style={{ color: '#00ff88' }}>
            {rt.active_users}
          </div>
          <div className="text-[9px] text-muted uppercase font-mono">activos</div>
        </div>
        <div className="flex-1 text-center bg-white/[0.04] rounded-xl py-2">
          <div className="text-xl font-black font-mono text-glow" style={{ color: '#ffaa00' }}>
            {rt.events_60s}
          </div>
          <div className="text-[9px] text-muted uppercase font-mono">ev/60s</div>
        </div>
      </div>

      {/* Page feed */}
      {pages.length > 0 ? (
        <div className="space-y-1">
          {pages.map((p, i) => {
            const isNew = newSet.has(p.created_at);
            return (
              <div
                key={p.created_at || i}
                className={`flex items-center gap-1.5 text-[10px] font-mono rounded px-2 py-1.5 transition-all duration-500 ${
                  isNew ? 'bg-accent/10 border border-accent/25' : 'bg-white/[0.03]'
                }`}
                style={{ opacity: isNew ? 1 : Math.max(0.45, 1 - i * 0.12) }}
              >
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isNew ? 'bg-accent animate-pulse' : 'bg-white/15'}`} />
                <span className="text-gray-300 truncate flex-1 text-[9px]" title={p.url}>
                  {p.url?.replace(/^https?:\/\/[^/]+/, '') || '/'}
                </span>
                <span className="text-[11px] shrink-0">{p.country ? countryFlag(p.country) : '??'}</span>
                <span className="text-muted shrink-0 w-5 text-right">{formatTimeAgo(p.created_at)}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-xs text-muted italic text-center py-2">Sin actividad reciente</div>
      )}
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────────────────────

export default function PixelOverview() {
  const navigate = useNavigate();

  const [site, setSite]           = useState(null);       // first pixel site
  const [stats, setStats]         = useState(null);
  const [timeseries, setTimeseries] = useState(null);
  const [devices, setDevices]     = useState(null);
  const [countries, setCountries] = useState(null);
  const [pages, setPages]         = useState(null);
  const [loading, setLoading]     = useState(true);

  const load = useCallback(async (s) => {
    if (!s) return;
    const id = s.site_id;
    try {
      const [statsR, tsR, devR, cntR, pgR] = await Promise.all([
        api.get(`/pixel/sites/${id}/stats?days=7`),
        api.get(`/pixel/sites/${id}/timeseries?days=7`),
        api.get(`/pixel/sites/${id}/devices?days=7`),
        api.get(`/pixel/sites/${id}/countries?days=7`),
        api.get(`/pixel/sites/${id}/pages?days=7`),
      ]);
      setStats(statsR.data);
      setTimeseries(tsR.data);
      setDevices(devR.data);
      setCountries(cntR.data);
      setPages(pgR.data);
    } catch (err) {
      console.error('[PixelOverview] fetch error:', err);
    }
  }, []);

  // Load first pixel site on mount
  useEffect(() => {
    setLoading(true);
    api.get('/pixel/sites')
      .then(r => {
        if (r.data.length > 0) {
          setSite(r.data[0]);
          return load(r.data[0]);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [load]);

  // No pixel sites yet → silent (don't pollute dashboard)
  if (!loading && !site) return null;

  if (loading && !stats) {
    return (
      <div className="mb-6 card-dash p-6 flex items-center gap-3">
        <Loader className="w-4 h-4 animate-spin text-accent" />
        <span className="text-xs text-muted">Cargando analítica...</span>
      </div>
    );
  }

  const insights = computeInsights(stats, devices, countries, pages, timeseries);
  const topPages  = (pages || []).slice(0, 3);

  const KPI_CONFIG = [
    { title: 'Vistas hoy',    val: stats?.today_events         ?? 0, color: '#00ff88', icon: <Activity className="w-3.5 h-3.5 opacity-30" /> },
    { title: 'Sesiones',      val: stats?.unique_sessions      ?? 0, color: '#00aaff', icon: <Users    className="w-3.5 h-3.5 opacity-30" /> },
    { title: 'Bounce rate',   val: `${stats?.bounce_rate ?? 0}%`,   color: '#ffaa00', icon: <Clock    className="w-3.5 h-3.5 opacity-30" /> },
    { title: 'Activos ahora', val: stats?.active_users_5min    ?? 0, color: '#00ff88', icon: <Zap     className="w-3.5 h-3.5 opacity-30" /> },
  ];

  return (
    <div className="mb-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          <span className="text-xs font-mono font-bold uppercase tracking-widest text-white">
            Business Overview
          </span>
          {site && (
            <span className="text-[9px] font-mono text-muted px-2 py-0.5 rounded bg-white/5">
              {site.name}
            </span>
          )}
        </div>
        <button
          onClick={() => navigate('/pixel')}
          className="flex items-center gap-1 text-[10px] font-mono text-accent hover:text-white transition-colors"
        >
          Ver detalle <ArrowRight className="w-3 h-3" />
        </button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {KPI_CONFIG.map((m, i) => (
          <div key={i}
               className="p-3 bg-[#050505] rounded-xl border"
               style={{ borderColor: `${m.color}22` }}>
            <div className="flex justify-between items-start mb-1.5">
              <div className="text-[9px] font-mono tracking-widest uppercase text-muted">{m.title}</div>
              {m.icon}
            </div>
            <div className="text-2xl font-black font-mono text-glow" style={{ color: m.color }}>{m.val}</div>
          </div>
        ))}
      </div>

      {/* Insights chips */}
      {insights.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {insights.map((ins, i) => (
            <div key={i}
                 className={`flex items-center gap-2 px-2.5 py-1.5 rounded-xl border text-xs ${INSIGHT_COLOR[ins.type] || INSIGHT_COLOR.page}`}>
              <span className="text-sm leading-none select-none">{ins.icon}</span>
              <div>
                <div className="font-mono font-bold leading-tight text-[10px]">{ins.main}</div>
                <div className="text-[9px] text-muted leading-tight">{ins.sub}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Hero: chart (2/3) + realtime (1/3) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
        {/* TimeSeries */}
        <div className="lg:col-span-2 card-dash p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-mono font-bold uppercase text-white flex items-center gap-2">
              <Activity className="w-3.5 h-3.5 text-accent" /> Últimos 7 días
            </div>
            <div className="flex items-center gap-3 text-[9px] font-mono text-muted">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-sm inline-block" style={{ background: '#00ff88' }} /> Vistas
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-sm inline-block" style={{ background: '#00aaff' }} /> Sesiones
              </span>
            </div>
          </div>
          {timeseries === null ? (
            <div className="flex items-center justify-center h-[110px]">
              <Loader className="w-4 h-4 animate-spin text-accent" />
            </div>
          ) : (
            <MiniTimeSeries data={timeseries} />
          )}
        </div>

        {/* Realtime panel */}
        <div className="card-dash p-4">
          <div className="text-xs font-mono font-bold uppercase text-white mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-accent animate-pulse" /> Tiempo real
          </div>
          {site ? <MiniRealtime siteId={site.site_id} /> : (
            <div className="text-xs text-muted italic text-center py-4">Sin sitio</div>
          )}
        </div>
      </div>

      {/* Bottom: Top pages */}
      {topPages.length > 0 && (
        <div className="card-dash p-4">
          <div className="text-xs font-mono font-bold uppercase text-white mb-3 flex items-center gap-2">
            <Globe className="w-3.5 h-3.5 text-accent" /> Top páginas (7d)
          </div>
          <div className="space-y-2">
            {topPages.map((p, i) => {
              const path  = (p.url || '/').replace(/^https?:\/\/[^/]+/, '') || '/';
              const maxV  = topPages[0].views || 1;
              const pct   = Math.round((p.views / maxV) * 100);
              return (
                <div key={i} className="flex items-center gap-3 text-xs">
                  <span className="font-mono text-[10px] text-muted w-4 shrink-0">{i + 1}</span>
                  <span className="text-gray-300 truncate flex-1 text-[10px]" title={p.url}>{path}</span>
                  <div className="w-24 bg-white/5 rounded-full h-1.5 overflow-hidden shrink-0">
                    <div className="bg-[#00ff88]/70 h-1.5 rounded-full transition-all duration-700"
                         style={{ width: `${pct}%` }} />
                  </div>
                  <span className="font-mono text-[#00ff88] text-[10px] w-8 text-right shrink-0">{p.views}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
