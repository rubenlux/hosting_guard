/**
 * PixelOverview — executive summary widget for the main Dashboard.
 *
 * Answers: "What is happening right now?" in under 3 seconds.
 * → 4 KPI numbers, insight chips, small sparkline, minimal live dot.
 *
 * PixelAnalytics page answers: "Why is this happening?"
 * → Full charts, breakdowns, funnel, devices, countries.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { Activity, Users, Clock, Zap, ArrowRight, Loader } from 'lucide-react';

// ── Micro-utilities ──────────────────────────────────────────────────────────

function formatTimeAgo(iso) {
  if (!iso) return '';
  const s = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (s < 60)   return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

function countryFlag(code) {
  if (!code || code.length !== 2) return '';
  const base = 127397;
  return String.fromCodePoint(...code.toUpperCase().split('').map(c => base + c.charCodeAt(0)));
}

// ── Sparkline (single thin line, no axes, minimal) ─────────────────────────

function Sparkline({ data, color = '#00ff88' }) {
  const [clipW, setClipW] = useState(0);
  const r1 = useRef(null), r2 = useRef(null);

  const W = 220, H = 40, pad = 3;

  useEffect(() => {
    setClipW(0);
    r1.current = requestAnimationFrame(() => {
      r2.current = requestAnimationFrame(() => setClipW(W + 4));
    });
    return () => { cancelAnimationFrame(r1.current); cancelAnimationFrame(r2.current); };
  }, [data]);

  if (!data || data.length < 2) {
    return <div style={{ width: W, height: H }} className="flex items-center">
      <div className="w-full h-px bg-white/10" />
    </div>;
  }

  const vals  = data.map(d => d.page_views || 0);
  const maxY  = Math.max(...vals, 1);
  const n     = vals.length;
  const xOf   = i => pad + (i / (n - 1)) * (W - pad * 2);
  const yOf   = v => H - pad - ((v / maxY) * (H - pad * 2));
  const pts   = vals.map((v, i) => [xOf(i), yOf(v)]);
  const bottom = H - pad;

  // bezier area
  let line = `M ${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const dx = (x1 - x0) * 0.4;
    line += ` C ${x0 + dx},${y0} ${x1 - dx},${y1} ${x1},${y1}`;
  }
  const area = `${line} L ${pts[pts.length - 1][0]},${bottom} L ${pts[0][0]},${bottom} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: W, height: H }} className="overflow-visible">
      <defs>
        <linearGradient id="spkGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={color} stopOpacity="0.18" />
          <stop offset="100%" stopColor={color} stopOpacity="0"    />
        </linearGradient>
        <clipPath id="spkClip">
          <rect x={0} y={0} width={clipW} height={H}
                style={{ transition: clipW > 0 ? 'width 0.7s ease-out' : 'none' }} />
        </clipPath>
      </defs>
      <g clipPath="url(#spkClip)">
        <path d={area} fill="url(#spkGrad)" />
        <path d={line} fill="none" stroke={color} strokeWidth="1.5"
              strokeLinecap="round" strokeLinejoin="round" />
      </g>
      {/* Last point dot */}
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.5"
              fill={color} />
    </svg>
  );
}

// ── Insights engine ─────────────────────────────────────────────────────────

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
      else               out.push({ icon: '→',  main: 'Estable',   sub: 'sin cambios',       type: 'flat' });
    }
  }

  if (devices?.length > 0) {
    const total = devices.reduce((s, d) => s + Number(d.count), 0);
    const top   = devices[0];
    if (total > 0) {
      const pct = Math.round((Number(top.count) / total) * 100);
      const icon = top.device === 'mobile' ? '📱' : top.device === 'tablet' ? '🖥' : '💻';
      out.push({ icon, main: `${pct}% ${top.device}`, sub: 'dispositivo líder', type: 'device' });
    }
  }

  if (countries?.length > 0) {
    const total = countries.reduce((s, c) => s + Number(c.count), 0);
    const top   = countries[0];
    const pct   = Math.round((Number(top.count) / total) * 100);
    out.push({
      icon: countryFlag(top.country) || '🌍',
      main: `${pct}% ${top.country}`,
      sub:  'país principal',
      type: 'geo',
    });
  }

  if (pages?.length > 0) {
    const path = (pages[0].url || '/').replace(/^https?:\/\/[^/]+/, '') || '/';
    out.push({
      icon: '🔥',
      main: path.length > 16 ? path.slice(0, 14) + '…' : path,
      sub:  `${pages[0].views} vistas`,
      type: 'page',
    });
  }

  return out.slice(0, 4);
}

const CHIP_STYLE = {
  up:     'border-[#00ff88]/25 text-[#00ff88]',
  down:   'border-[#ff4466]/25 text-[#ff4466]',
  flat:   'border-white/10    text-muted',
  device: 'border-[#00aaff]/25 text-[#00aaff]',
  geo:    'border-[#aa44ff]/25 text-[#aa44ff]',
  page:   'border-[#ffaa00]/25 text-[#ffaa00]',
};

// ── Live dot — minimal realtime indicator ────────────────────────────────────

function LiveDot({ siteId }) {
  const [rt, setRt]         = useState(null);
  const [flash, setFlash]   = useState(false);
  const prevCount           = useRef(0);

  useEffect(() => {
    if (!siteId) return;
    const fetch = () =>
      api.get(`/pixel/sites/${siteId}/realtime`)
        .then(r => {
          const d = r.data;
          // Flash animation when new events arrive
          if (prevCount.current > 0 && d.events_60s > prevCount.current) {
            setFlash(true);
            setTimeout(() => setFlash(false), 800);
          }
          prevCount.current = d.events_60s;
          setRt(d);
        })
        .catch(() => {});

    fetch();
    const iv = setInterval(fetch, 10000);
    return () => clearInterval(iv);
  }, [siteId]);

  if (!rt) return null;

  const last = rt.recent_pages?.[0];
  const lastPath = last?.url?.replace(/^https?:\/\/[^/]+/, '') || '/';

  return (
    <div className="flex items-center gap-4">
      {/* Active users badge */}
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full bg-accent shrink-0 ${rt.active_users > 0 ? 'animate-pulse' : 'opacity-40'}`} />
        <span className="font-mono font-bold text-white tabular-nums">{rt.active_users}</span>
        <span className="text-[10px] text-muted">activos</span>
      </div>

      {/* Separator */}
      <div className="w-px h-4 bg-white/10" />

      {/* Last event */}
      {last && (
        <div className={`flex items-center gap-1.5 text-[10px] font-mono transition-all duration-300 ${flash ? 'text-accent' : 'text-muted'}`}>
          <span className={`w-1 h-1 rounded-full bg-accent shrink-0 ${flash ? 'animate-ping' : 'opacity-50'}`} />
          <span className="truncate max-w-[140px]" title={last.url}>{lastPath}</span>
          <span className="text-muted shrink-0">{formatTimeAgo(last.created_at)}</span>
        </div>
      )}
    </div>
  );
}

// ── Main export ──────────────────────────────────────────────────────────────

export default function PixelOverview() {
  const navigate = useNavigate();

  const [site, setSite]           = useState(null);
  const [stats, setStats]         = useState(null);
  const [timeseries, setTimeseries] = useState(null);
  const [devices, setDevices]     = useState(null);
  const [countries, setCountries] = useState(null);
  const [pages, setPages]         = useState(null);
  const [loading, setLoading]     = useState(true);

  const loadData = useCallback(async (s) => {
    const id = s.site_id;
    try {
      const [sR, tR, dR, cR, pR] = await Promise.all([
        api.get(`/pixel/sites/${id}/stats?days=7`),
        api.get(`/pixel/sites/${id}/timeseries?days=7`),
        api.get(`/pixel/sites/${id}/devices?days=7`),
        api.get(`/pixel/sites/${id}/countries?days=7`),
        api.get(`/pixel/sites/${id}/pages?days=7`),
      ]);
      setStats(sR.data);
      setTimeseries(tR.data);
      setDevices(dR.data);
      setCountries(cR.data);
      setPages(pR.data);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    setLoading(true);
    api.get('/pixel/sites')
      .then(r => {
        if (r.data.length > 0) {
          setSite(r.data[0]);
          return loadData(r.data[0]);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [loadData]);

  // No pixel sites → don't render anything
  if (!loading && !site) return null;

  if (loading && !stats) {
    return (
      <div className="mb-6 flex items-center gap-2 text-xs text-muted">
        <Loader className="w-3.5 h-3.5 animate-spin text-accent" />
        Cargando analítica...
      </div>
    );
  }

  const insights = computeInsights(stats, devices, countries, pages, timeseries);
  const topPages  = (pages || []).slice(0, 3);
  const totalViews = timeseries?.reduce((s, d) => s + (d.page_views || 0), 0) ?? 0;

  return (
    <div className="mb-6">
      {/* ── Row 1: header + "Ver detalle" ── */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
          <span className="text-xs font-mono font-bold uppercase tracking-widest text-white">
            Analítica del sitio
          </span>
          {site && (
            <span className="text-[9px] text-muted font-mono px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/8">
              {site.name}
            </span>
          )}
        </div>
        <button
          onClick={() => navigate('/pixel')}
          className="flex items-center gap-1 text-[10px] font-mono text-muted hover:text-accent transition-colors"
        >
          Análisis completo <ArrowRight className="w-3 h-3" />
        </button>
      </div>

      {/* ── Row 2: 4 KPI cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {[
          { label: 'Vistas hoy',   val: stats?.today_events         ?? 0, color: '#00ff88', Icon: Activity },
          { label: 'Sesiones',     val: stats?.unique_sessions      ?? 0, color: '#00aaff', Icon: Users    },
          { label: 'Bounce',       val: `${stats?.bounce_rate ?? 0}%`,   color: '#ffaa00', Icon: Clock    },
          { label: 'Activos',      val: stats?.active_users_5min    ?? 0, color: '#00ff88', Icon: Zap      },
        ].map(({ label, val, color, Icon }, i) => (
          <div key={i} className="p-3.5 bg-[#050505] rounded-xl border border-white/[0.06] flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                 style={{ background: `${color}12` }}>
              <Icon className="w-3.5 h-3.5" style={{ color }} />
            </div>
            <div className="min-w-0">
              <div className="text-[9px] font-mono uppercase tracking-wider text-muted truncate">{label}</div>
              <div className="text-xl font-black font-mono leading-tight" style={{ color }}>{val}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Row 3: Insight chips (primary highlight) ── */}
      {insights.length > 0 && (
        <div className="flex gap-2 flex-wrap mb-4">
          {insights.map((ins, i) => (
            <div key={i}
                 className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border bg-white/[0.02] text-xs ${CHIP_STYLE[ins.type] || CHIP_STYLE.page}`}>
              <span className="text-sm leading-none select-none">{ins.icon}</span>
              <span className="font-mono font-bold text-[10px]">{ins.main}</span>
              <span className="text-[9px] text-muted hidden sm:inline">{ins.sub}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Row 4: Sparkline (context) + Live + Top pages ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">

        {/* Sparkline card — narrow, just context */}
        <div className="md:col-span-1 p-4 bg-[#050505] rounded-xl border border-white/[0.06]">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[9px] font-mono uppercase tracking-widest text-muted">Últimos 7 días</div>
            <div className="font-mono text-xs font-bold text-white">{totalViews.toLocaleString()} vistas</div>
          </div>
          <Sparkline data={timeseries} color="#00ff88" />
        </div>

        {/* Live status card */}
        <div className="md:col-span-1 p-4 bg-[#050505] rounded-xl border border-white/[0.06]">
          <div className="text-[9px] font-mono uppercase tracking-widest text-muted mb-3">En vivo</div>
          {site
            ? <LiveDot siteId={site.site_id} />
            : <div className="text-xs text-muted italic">Sin sitio</div>
          }
          {/* Second recent event */}
          {stats?.active_users_5min === 0 && (
            <div className="mt-2 text-[9px] text-muted italic font-mono">sin actividad últimos 5 min</div>
          )}
        </div>

        {/* Top 3 pages — compact list */}
        <div className="md:col-span-1 p-4 bg-[#050505] rounded-xl border border-white/[0.06]">
          <div className="text-[9px] font-mono uppercase tracking-widest text-muted mb-3">Top páginas</div>
          {topPages.length > 0 ? (
            <div className="space-y-2">
              {topPages.map((p, i) => {
                const path = (p.url || '/').replace(/^https?:\/\/[^/]+/, '') || '/';
                const maxV = topPages[0].views || 1;
                const pct  = Math.round((p.views / maxV) * 100);
                return (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-[9px] font-mono text-muted w-3 shrink-0">{i + 1}</span>
                    {/* thin progress bar */}
                    <div className="flex-1 h-1 bg-white/[0.06] rounded-full overflow-hidden">
                      <div className="h-1 rounded-full bg-[#00ff88]/60 transition-all duration-700"
                           style={{ width: `${pct}%` }} />
                    </div>
                    <span className="text-[9px] font-mono text-gray-400 truncate max-w-[80px]" title={p.url}>{path}</span>
                    <span className="text-[9px] font-mono text-[#00ff88] shrink-0 w-6 text-right">{p.views}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-[10px] text-muted italic">Sin datos</div>
          )}
        </div>

      </div>
    </div>
  );
}
