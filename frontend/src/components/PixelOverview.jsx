/**
 * PixelOverview — 5-block executive summary. No scroll required.
 *
 * Block 1: KPI row (4 numbers)
 * Block 2: Insight chips
 * Block 3: Sparkline (≤120px, no gradient, no animation, single line)
 * Block 4: Top pages (text only, no bars)
 * Block 5: Live (active count + last event, single row)
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { Activity, Users, Clock, Zap, ArrowRight, Loader } from 'lucide-react';

// ── Utilities ────────────────────────────────────────────────────────────────

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

// ── Block 3: Sparkline — simple polyline, no fill, no animation, ≤120px ─────

function Sparkline({ data }) {
  if (!data || data.length < 2) {
    return <div className="h-[56px] flex items-center justify-center text-[10px] text-muted italic">Sin datos</div>;
  }

  const W = 300, H = 56, padX = 4, padY = 4;
  const vals = data.map(d => d.page_views || 0);
  const maxY = Math.max(...vals, 1);
  const n    = vals.length;

  const points = vals.map((v, i) => {
    const x = padX + (i / (n - 1)) * (W - padX * 2);
    const y = H - padY - ((v / maxY) * (H - padY * 2));
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 56 }} preserveAspectRatio="none">
      <polyline
        fill="none"
        stroke="#00ff88"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
        opacity="0.7"
      />
    </svg>
  );
}

// ── Insights engine ──────────────────────────────────────────────────────────

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
      else               out.push({ icon: '→',  main: 'Estable',   sub: 'sin cambios',      type: 'flat' });
    }
  }

  if (devices?.length > 0) {
    const total = devices.reduce((s, d) => s + Number(d.count), 0);
    const top   = devices[0];
    if (total > 0) {
      const pct  = Math.round((Number(top.count) / total) * 100);
      const icon = top.device === 'mobile' ? '📱' : '💻';
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

const CHIP = {
  up:     'border-[#00ff88]/20 text-[#00ff88]',
  down:   'border-[#ff4466]/20 text-[#ff4466]',
  flat:   'border-white/10    text-muted',
  device: 'border-[#00aaff]/20 text-[#00aaff]',
  geo:    'border-[#aa44ff]/20 text-[#aa44ff]',
  page:   'border-[#ffaa00]/20 text-[#ffaa00]',
};

// ── Block 5: Live — single row ───────────────────────────────────────────────

function LiveRow({ siteId }) {
  const [rt, setRt] = useState(null);

  useEffect(() => {
    if (!siteId) return;
    const fetch = () => api.get(`/pixel/sites/${siteId}/realtime`).then(r => setRt(r.data)).catch(() => {});
    fetch();
    const iv = setInterval(fetch, 10000);
    return () => clearInterval(iv);
  }, [siteId]);

  if (!rt) return <div className="flex items-center gap-1.5 text-[10px] text-muted"><Loader className="w-3 h-3 animate-spin" /> cargando...</div>;

  const last  = rt.recent_pages?.[0];
  const path  = last?.url?.replace(/^https?:\/\/[^/]+/, '') || null;

  return (
    <div className="flex items-center gap-4 text-xs font-mono">
      {/* Active count */}
      <div className="flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full bg-accent ${rt.active_users > 0 ? 'animate-pulse' : 'opacity-30'}`} />
        <span className="font-bold text-white">{rt.active_users}</span>
        <span className="text-[10px] text-muted">activos</span>
      </div>

      {/* Divider */}
      <div className="w-px h-3 bg-white/10" />

      {/* Last event — single line */}
      {path ? (
        <div className="flex items-center gap-1.5 text-[10px] text-muted min-w-0">
          <span className="text-white truncate max-w-[160px]">{path}</span>
          <span>{formatTimeAgo(last.created_at)}</span>
        </div>
      ) : (
        <span className="text-[10px] text-muted italic">sin actividad reciente</span>
      )}
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function PixelOverview() {
  const navigate = useNavigate();

  const [site, setSite]             = useState(null);
  const [stats, setStats]           = useState(null);
  const [timeseries, setTimeseries] = useState(null);
  const [devices, setDevices]       = useState(null);
  const [countries, setCountries]   = useState(null);
  const [pages, setPages]           = useState(null);
  const [loading, setLoading]       = useState(true);

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
      .then(r => { if (r.data.length > 0) { setSite(r.data[0]); return loadData(r.data[0]); } })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [loadData]);

  if (!loading && !site) return null;
  if (loading && !stats)  return null; // don't show skeleton — dashboard loads fast enough

  const insights = computeInsights(stats, devices, countries, pages, timeseries);
  const top3     = (pages || []).slice(0, 3);

  return (
    <div className="mb-5 p-4 bg-[#050505] rounded-2xl border border-white/[0.06] space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
          <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-white">
            Analítica — {site?.name}
          </span>
        </div>
        <button
          onClick={() => navigate('/pixel')}
          className="flex items-center gap-1 text-[9px] font-mono text-muted hover:text-accent transition-colors"
        >
          Ver detalle <ArrowRight className="w-3 h-3" />
        </button>
      </div>

      {/* ── BLOCK 1: KPI row ── */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: 'Vistas hoy', val: stats?.today_events      ?? 0, color: '#00ff88' },
          { label: 'Sesiones',   val: stats?.unique_sessions   ?? 0, color: '#00aaff' },
          { label: 'Bounce',     val: `${stats?.bounce_rate ?? 0}%`, color: '#ffaa00' },
          { label: 'Activos',    val: stats?.active_users_5min ?? 0, color: '#00ff88' },
        ].map(({ label, val, color }, i) => (
          <div key={i} className="text-center">
            <div className="text-2xl font-black font-mono leading-none" style={{ color }}>{val}</div>
            <div className="text-[9px] font-mono text-muted uppercase mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* Divider */}
      <div className="border-t border-white/[0.05]" />

      {/* ── BLOCK 2: Insight chips ── */}
      {insights.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {insights.map((ins, i) => (
            <span key={i}
                  className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border bg-white/[0.02] text-[10px] font-mono ${CHIP[ins.type] || CHIP.page}`}>
              <span className="text-xs leading-none">{ins.icon}</span>
              <span className="font-bold">{ins.main}</span>
            </span>
          ))}
        </div>
      )}

      {/* ── BLOCK 3 + 4: Sparkline & Top pages — side by side ── */}
      <div className="grid grid-cols-2 gap-4">

        {/* Block 3: Sparkline */}
        <div>
          <div className="text-[9px] font-mono text-muted uppercase tracking-widest mb-1.5">7 días</div>
          <Sparkline data={timeseries} />
        </div>

        {/* Block 4: Top pages — text only */}
        <div>
          <div className="text-[9px] font-mono text-muted uppercase tracking-widest mb-1.5">Top páginas</div>
          {top3.length > 0 ? (
            <div className="space-y-1.5">
              {top3.map((p, i) => {
                const path = (p.url || '/').replace(/^https?:\/\/[^/]+/, '') || '/';
                return (
                  <div key={i} className="flex items-center justify-between gap-2 text-[10px] font-mono">
                    <span className="text-muted w-3 shrink-0">{i + 1}</span>
                    <span className="text-gray-300 truncate flex-1" title={p.url}>{path}</span>
                    <span className="text-white font-bold shrink-0">{p.views}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-[10px] text-muted italic">Sin datos</div>
          )}
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-white/[0.05]" />

      {/* ── BLOCK 5: Live — single row ── */}
      {site && <LiveRow siteId={site.site_id} />}

    </div>
  );
}
