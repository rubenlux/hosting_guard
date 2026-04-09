import React, { useState, useEffect, useCallback, useRef } from 'react';
import api from '../services/api';
import { getAdminPixelOverview, getAdminPixelEvents } from '../services/api';
import {
  Plus, Trash2, Copy, CheckCircle, BarChart3, Globe, Users, Clock,
  Monitor, X, Loader, Activity, Database, Zap, TrendingUp, ArrowRight,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

// ── Utilities ──────────────────────────────────────────────────────────────

function formatTimeAgo(iso) {
  if (!iso) return '';
  const s = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (s < 60)  return `${s}s`;
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

// ── Chart: Time Series ──────────────────────────────────────────────────────

function TimeSeriesChart({ data }) {
  const [tooltip, setTooltip] = useState(null);

  if (data === null) {
    return (
      <div className="flex items-center justify-center py-8 gap-2 text-xs text-muted">
        <Loader className="w-3.5 h-3.5 animate-spin text-accent" /> Cargando...
      </div>
    );
  }
  if (data.length === 0) {
    return (
      <div className="py-8 text-center">
        <Activity className="w-5 h-5 mx-auto mb-2 opacity-20" />
        <div className="text-xs text-muted italic">Recolectando datos...</div>
      </div>
    );
  }

  const W = 560, H = 130, padL = 30, padR = 10, padT = 20, padB = 26;
  const cW = W - padL - padR;
  const cH = H - padT - padB;
  const n  = data.length;

  const maxY = Math.max(...data.map(d => Math.max(d.page_views, d.sessions)), 1);

  const xOf = i  => padL + (n > 1 ? (i / (n - 1)) * cW : cW / 2);
  const yOf = v  => padT + cH - Math.min((v / maxY) * cH, cH);

  const pvPts  = data.map((d, i) => [xOf(i), yOf(d.page_views)]);
  const sesPts = data.map((d, i) => [xOf(i), yOf(d.sessions)]);
  const bottom = padT + cH;

  // Grid: 3 horizontal lines
  const gridVals = [0, Math.round(maxY / 2), maxY];

  // X-axis: ~5 evenly-spaced labels
  const step = Math.max(1, Math.floor(n / 5));
  const xIdxs = [];
  for (let i = 0; i < n; i += step) xIdxs.push(i);
  if (xIdxs[xIdxs.length - 1] !== n - 1) xIdxs.push(n - 1);

  // Hover hit-zone per column
  const colWidth = n > 1 ? cW / (n - 1) : cW;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full select-none"
      style={{ height: 150 }}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <linearGradient id="pvArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#00ff88" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#00ff88" stopOpacity="0"    />
        </linearGradient>
        <linearGradient id="sesArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#00aaff" stopOpacity="0.14" />
          <stop offset="100%" stopColor="#00aaff" stopOpacity="0"    />
        </linearGradient>
      </defs>

      {/* Grid */}
      {gridVals.map((v, i) => (
        <g key={i}>
          <line x1={padL} y1={yOf(v)} x2={W - padR} y2={yOf(v)}
                stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
          <text x={padL - 4} y={yOf(v)} textAnchor="end" fontSize="7"
                fill="rgba(255,255,255,0.28)" dy="0.3em">{v}</text>
        </g>
      ))}

      {/* Areas */}
      <path d={areaPath(pvPts,  bottom)} fill="url(#pvArea)"  />
      <path d={areaPath(sesPts, bottom)} fill="url(#sesArea)" />

      {/* Lines */}
      <path d={bezierPath(pvPts)}  fill="none" stroke="#00ff88" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" />
      <path d={bezierPath(sesPts)} fill="none" stroke="#00aaff" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round" strokeDasharray="4,2" />

      {/* Invisible hit columns */}
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
        const ttx = tooltip < n * 0.65 ? xOf(tooltip) + 9 : xOf(tooltip) - 90;
        const tty = padT + 6;
        return (
          <g>
            <line x1={xOf(tooltip)} y1={padT} x2={xOf(tooltip)} y2={bottom}
                  stroke="rgba(255,255,255,0.18)" strokeWidth="1" strokeDasharray="3,2" />
            <rect x={ttx} y={tty} width="82" height="47" rx="5"
                  fill="#0a0a0a" stroke="rgba(255,255,255,0.13)" strokeWidth="0.5" />
            <text x={ttx + 7} y={tty + 13} fontSize="7.5" fill="rgba(255,255,255,0.45)">
              {data[tooltip]?.label || data[tooltip]?.day?.slice(5)}
            </text>
            <text x={ttx + 7} y={tty + 28} fontSize="9" fill="#00ff88">
              ▲ {data[tooltip]?.page_views} vistas
            </text>
            <text x={ttx + 7} y={tty + 42} fontSize="9" fill="#00aaff">
              ◈ {data[tooltip]?.sessions} sesiones
            </text>
            <circle cx={xOf(tooltip)} cy={yOf(data[tooltip]?.page_views)} r="4.5"
                    fill="#00ff88" stroke="#000" strokeWidth="1.5" />
            <circle cx={xOf(tooltip)} cy={yOf(data[tooltip]?.sessions)} r="3.5"
                    fill="#00aaff" stroke="#000" strokeWidth="1.5" />
          </g>
        );
      })()}

      {/* X labels */}
      {xIdxs.map(i => (
        <text key={i} x={xOf(i)} y={H - 5} textAnchor="middle"
              fontSize="7" fill="rgba(255,255,255,0.38)">
          {data[i]?.label || data[i]?.day?.slice(5)}
        </text>
      ))}

      {/* Legend */}
      <rect x={padL} y={4} width="8" height="8" fill="#00ff88" rx="2" />
      <text x={padL + 11} y={10.5} fontSize="8" fill="#00ff88">Page views</text>
      <rect x={padL + 76} y={4} width="8" height="8" fill="#00aaff" rx="2" />
      <text x={padL + 87} y={10.5} fontSize="8" fill="#00aaff">Sesiones</text>
    </svg>
  );
}

// ── Chart: Donut ────────────────────────────────────────────────────────────

const DEVICE_COLORS = {
  mobile:  '#00aaff',
  desktop: '#00ff88',
  tablet:  '#ffaa00',
  other:   '#aa44ff',
  unknown: '#555',
};
const PIE_COLORS = ['#00ff88','#00aaff','#ffaa00','#aa44ff','#ff4466','#44ffcc','#ff8800','#0088ff'];

function DonutChart({ data, colorMap }) {
  if (data === null) {
    return <div className="flex items-center gap-2 py-3 text-xs text-muted"><Loader className="w-3 h-3 animate-spin text-accent" /> Cargando...</div>;
  }
  if (!data || data.length === 0) {
    return <div className="text-xs text-muted italic">Recolectando datos...</div>;
  }
  const total = data.reduce((s, d) => s + Number(d.count), 0);
  if (!total) return <div className="text-xs text-muted italic">Sin datos</div>;

  const cx = 56, cy = 56, outerR = 48, innerR = 29;
  let angle = -Math.PI / 2;

  const slices = data.map((d, i) => {
    const frac  = Number(d.count) / total;
    const sweep = frac * 2 * Math.PI;
    const x1 = cx + outerR * Math.cos(angle),           y1 = cy + outerR * Math.sin(angle);
    const x2 = cx + outerR * Math.cos(angle + sweep),   y2 = cy + outerR * Math.sin(angle + sweep);
    const ix1 = cx + innerR * Math.cos(angle + sweep),  iy1 = cy + innerR * Math.sin(angle + sweep);
    const ix2 = cx + innerR * Math.cos(angle),          iy2 = cy + innerR * Math.sin(angle);
    const large = sweep > Math.PI ? 1 : 0;
    const path  = `M${x1},${y1} A${outerR},${outerR} 0 ${large} 1 ${x2},${y2} L${ix1},${iy1} A${innerR},${innerR} 0 ${large} 0 ${ix2},${iy2} Z`;
    const color = colorMap?.[d.device || d.country] || PIE_COLORS[i % PIE_COLORS.length];
    angle += sweep;
    return { path, color, label: d.device || d.country || '?', count: d.count, pct: Math.round(frac * 100) };
  });

  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 112 112" className="w-20 h-20 shrink-0">
        {slices.map((s, i) => <path key={i} d={s.path} fill={s.color} />)}
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize="13" fontWeight="bold" fill="white">{total}</text>
        <text x={cx} y={cx + 8} textAnchor="middle" fontSize="7"  fill="rgba(255,255,255,0.4)">total</text>
      </svg>
      <div className="space-y-1.5 min-w-0">
        {slices.map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-xs min-w-0">
            <div className="w-2 h-2 rounded-full shrink-0" style={{ background: s.color }} />
            <span className="text-gray-300 capitalize truncate">{s.label}</span>
            <span className="font-mono text-muted ml-auto shrink-0">{s.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Chart: Horizontal Bars ──────────────────────────────────────────────────

function HBarChart({ data, labelKey, valueKey, color = '#00ff88', formatLabel }) {
  if (data === null) {
    return <div className="flex items-center gap-2 py-3 text-xs text-muted"><Loader className="w-3 h-3 animate-spin text-accent" /> Cargando...</div>;
  }
  if (!data || data.length === 0) {
    return <div className="text-xs text-muted italic">Recolectando datos...</div>;
  }
  const max = Math.max(...data.map(d => Number(d[valueKey])), 1);
  return (
    <div className="space-y-2">
      {data.map((d, i) => {
        const label = formatLabel ? formatLabel(d[labelKey]) : (d[labelKey] || '—');
        const pct   = (Number(d[valueKey]) / max) * 100;
        return (
          <div key={i} className="flex items-center gap-2 text-xs">
            <div className="w-28 truncate text-right text-muted shrink-0 text-[10px]" title={d[labelKey]}>{label}</div>
            <div className="flex-1 bg-white/5 rounded-full h-2.5 relative overflow-hidden">
              <div className="absolute inset-y-0 left-0 rounded-full transition-all duration-700"
                   style={{ width: `${pct}%`, background: color, opacity: 0.78 }} />
            </div>
            <div className="w-8 text-right font-mono shrink-0 text-[10px]" style={{ color }}>{d[valueKey]}</div>
          </div>
        );
      })}
    </div>
  );
}

// ── Panel: Realtime ─────────────────────────────────────────────────────────

function RealtimePanel({ siteId }) {
  const [data, setData] = useState(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!siteId) return;
    api.get(`/pixel/sites/${siteId}/realtime`).then(r => setData(r.data)).catch(() => {});
    const iv = setInterval(() => {
      api.get(`/pixel/sites/${siteId}/realtime`).then(r => { setData(r.data); setTick(t => t + 1); }).catch(() => {});
    }, 10000);
    return () => clearInterval(iv);
  }, [siteId]);

  return (
    <div className="card-dash p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="text-xs font-mono font-bold uppercase text-white flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          Tiempo Real
        </div>
        <div className="text-[10px] text-muted font-mono">actualiza cada 10 s</div>
      </div>

      {!data ? (
        <div className="flex justify-center py-4"><Loader className="w-4 h-4 animate-spin text-accent" /></div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            {[
              { val: data.active_users, label: 'Activos ahora',  color: 'text-[#00ff88]' },
              { val: data.events_60s,   label: 'Eventos / 60 s', color: 'text-[#ffaa00]' },
              { val: data.recent_pages?.length ?? 0, label: 'Páginas (log)', color: 'text-[#00aaff]' },
            ].map((m, i) => (
              <div key={i} className="text-center bg-white/3 rounded-xl p-2">
                <div className={`text-xl font-black font-mono text-glow ${m.color}`}>{m.val}</div>
                <div className="text-[9px] text-muted uppercase font-mono mt-0.5">{m.label}</div>
              </div>
            ))}
          </div>

          {data.recent_pages?.length > 0 && (
            <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
              {data.recent_pages.map((p, i) => (
                <div key={i} className="flex items-center gap-2 text-[10px] font-mono bg-white/3 rounded px-2 py-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent shrink-0" style={{ opacity: 1 - i * 0.08 }} />
                  <span className="text-gray-300 truncate flex-1" title={p.url}>
                    {p.url?.replace(/^https?:\/\/[^/]+/, '') || '/'}
                  </span>
                  <span className="text-muted shrink-0 w-10 text-center">{p.device || '?'}</span>
                  <span className="text-muted shrink-0 w-8 text-center" title={p.country}>
                    {p.country ? countryFlag(p.country) : '??'}
                  </span>
                  <span className="text-muted shrink-0 w-6 text-right">{formatTimeAgo(p.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Panel: Funnel ───────────────────────────────────────────────────────────

function FunnelPanel({ siteId, days }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!siteId) return;
    api.get(`/pixel/sites/${siteId}/funnel?days=${days}`).then(r => setData(r.data)).catch(() => {});
  }, [siteId, days]);

  if (!data) return null;
  if (!data.total_sessions) return null;

  const stripDomain = url => url?.replace(/^https?:\/\/[^/]+/, '') || '/';

  return (
    <div className="card-dash p-4">
      <div className="text-xs font-mono font-bold uppercase mb-4 text-white flex items-center gap-2">
        <TrendingUp className="w-3.5 h-3.5 text-accent" /> Funnel de Navegación
      </div>

      <div className="grid grid-cols-2 gap-5 mb-4">
        <div>
          <div className="text-[9px] text-[#00ff88]/70 font-mono uppercase tracking-widest mb-2 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#00ff88]" /> Páginas de Entrada
          </div>
          <div className="space-y-1.5">
            {data.entry_pages.map((p, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-[10px] text-muted w-4 shrink-0">{i + 1}</span>
                <span className="text-gray-300 truncate flex-1 text-[10px]" title={p.url}>{stripDomain(p.url)}</span>
                <span className="font-mono text-[#00ff88] text-[10px] shrink-0">{p.entries}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="text-[9px] text-[#ff4466]/70 font-mono uppercase tracking-widest mb-2 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#ff4466]" /> Páginas de Salida
          </div>
          <div className="space-y-1.5">
            {data.exit_pages.map((p, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-[10px] text-muted w-4 shrink-0">{i + 1}</span>
                <span className="text-gray-300 truncate flex-1 text-[10px]" title={p.url}>{stripDomain(p.url)}</span>
                <span className="font-mono text-[#ff4466] text-[10px] shrink-0">{p.exits}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-6 pt-3 border-t border-white/5">
        <div>
          <div className="text-[9px] text-muted uppercase font-mono">Drop-off</div>
          <div className="font-mono font-bold text-[#ffaa00]">{data.dropoff_rate}%</div>
        </div>
        <div>
          <div className="text-[9px] text-muted uppercase font-mono">Sesiones analizadas</div>
          <div className="font-mono font-bold text-white">{data.total_sessions}</div>
        </div>
        <div className="flex-1">
          <div className="bg-white/5 rounded-full h-1.5 overflow-hidden">
            <div className="bg-[#ffaa00] h-1.5 rounded-full transition-all duration-700"
                 style={{ width: `${data.dropoff_rate}%` }} />
          </div>
          <div className="text-[9px] text-muted mt-0.5">de sesiones vieron solo 1 página</div>
        </div>
      </div>
    </div>
  );
}

// ── Gate: collecting data ───────────────────────────────────────────────────

function CollectingGate({ total, threshold = 50, children }) {
  if (total < threshold) {
    const pct = Math.min(100, Math.round((total / threshold) * 100));
    return (
      <div className="card-dash p-6 text-center border border-dashed border-accent/20">
        <div className="text-3xl mb-3">📡</div>
        <div className="text-sm font-bold text-white mb-1">Recolectando datos...</div>
        <div className="text-xs text-muted mb-4">
          Vuelve en unos minutos. Los gráficos se activarán con más tráfico.
        </div>
        <div className="max-w-xs mx-auto">
          <div className="flex justify-between text-[10px] font-mono text-muted mb-1.5">
            <span>{total} eventos recibidos</span>
            <span>objetivo: {threshold}</span>
          </div>
          <div className="bg-white/5 rounded-full h-2 overflow-hidden">
            <div className="bg-accent rounded-full h-2 transition-all duration-700"
                 style={{ width: `${pct}%` }} />
          </div>
          <div className="text-[10px] text-accent mt-1.5">{pct}% completo</div>
        </div>
      </div>
    );
  }
  return children;
}

// ── Main Component ─────────────────────────────────────────────────────────

export default function PixelAnalytics() {
  const { user } = useAuth();
  const [sites, setSites]               = useState([]);
  const [loading, setLoading]           = useState(true);
  const [selectedSite, setSelectedSite] = useState(null);
  const [days, setDays]                 = useState(30);

  const [stats, setStats]         = useState(null);
  const [timeseries, setTimeseries] = useState(null);
  const [devices, setDevices]     = useState(null);
  const [countries, setCountries] = useState(null);
  const [pages, setPages]         = useState(null);
  const [chartsLoading, setChartsLoading] = useState(false);

  const [adminStats, setAdminStats]       = useState(null);
  const [adminOverview, setAdminOverview] = useState(null);
  const [adminEvents, setAdminEvents]     = useState([]);

  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName]       = useState('');
  const [newDomain, setNewDomain]   = useState('');
  const [creating, setCreating]     = useState(false);
  const [copiedScript, setCopiedScript] = useState(null);

  const fetchSites = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/pixel/sites');
      setSites(data);
      if (data.length > 0 && !selectedSite) setSelectedSite(data[0]);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  const fetchAdminStats = async () => {
    if (user?.role !== 'admin') return;
    try {
      const { data } = await api.get('/pixel/admin/stats');
      setAdminStats(data);
      const [overview, events] = await Promise.all([
        getAdminPixelOverview(),
        getAdminPixelEvents(50, 0),
      ]);
      setAdminOverview(overview);
      setAdminEvents(events);
    } catch (err) { console.error(err); }
  };

  const fetchAllCharts = useCallback(async (siteId, d) => {
    setChartsLoading(true);
    try {
      const [statsRes, tsRes, devRes, cntRes, pgRes] = await Promise.all([
        api.get(`/pixel/sites/${siteId}/stats?days=${d}`),
        api.get(`/pixel/sites/${siteId}/timeseries?days=${d}`),
        api.get(`/pixel/sites/${siteId}/devices?days=${d}`),
        api.get(`/pixel/sites/${siteId}/countries?days=${d}`),
        api.get(`/pixel/sites/${siteId}/pages?days=${d}`),
      ]);
      setStats(statsRes.data);
      setTimeseries(tsRes.data);
      setDevices(devRes.data);
      setCountries(cntRes.data);
      setPages(pgRes.data);
      console.log('[PixelAnalytics]', { stats: statsRes.data, timeseries: tsRes.data, devices: devRes.data, countries: cntRes.data, pages: pgRes.data });
    } catch (err) { console.error('[PixelAnalytics] fetch error:', err); }
    finally { setChartsLoading(false); }
  }, []);

  useEffect(() => { fetchSites(); fetchAdminStats(); }, []);

  useEffect(() => {
    if (!selectedSite) return;
    setStats(null); setTimeseries(null); setDevices(null); setCountries(null); setPages(null);
    fetchAllCharts(selectedSite.site_id, days);
    const iv = setInterval(() => fetchAllCharts(selectedSite.site_id, days), 30000);
    return () => clearInterval(iv);
  }, [selectedSite, days, fetchAllCharts]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post('/pixel/sites', { name: newName, domain: newDomain });
      setShowCreate(false); setNewName(''); setNewDomain('');
      fetchSites();
    } catch (err) { console.error(err); }
    finally { setCreating(false); }
  };

  const handleDelete = async (siteId) => {
    if (!confirm('¿Eliminar este sitio y TODOS sus datos analíticos?')) return;
    try {
      await api.delete(`/pixel/sites/${siteId}`);
      if (selectedSite?.site_id === siteId) { setSelectedSite(null); setStats(null); }
      fetchSites();
    } catch (err) { console.error(err); }
  };

  const copySnippet = (siteId) => {
    navigator.clipboard.writeText(`<script src="https://api.hostingguard.lat/pixel.js?id=${siteId}"></script>`);
    setCopiedScript(siteId);
    setTimeout(() => setCopiedScript(null), 2000);
  };

  return (
    <div className="flex flex-col gap-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-accent" /> Pixel Analytics
          </h2>
          <p className="text-sm text-gray-400">Analítica de primer partido para cualquier sitio web.</p>
        </div>
        <button onClick={() => setShowCreate(!showCreate)}
                className="btn-dash btn-primary-dash text-sm font-bold flex items-center gap-2">
          {showCreate ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {showCreate ? 'Cancelar' : 'Registrar Sitio'}
        </button>
      </div>

      {/* Admin Panel */}
      {adminStats && (
        <div className="p-4 bg-danger/10 border border-danger/30 rounded-2xl">
          <div className="text-[10px] text-danger font-mono tracking-widest uppercase mb-2">⚡ GLOBAL ADMIN STATS</div>
          <div className="flex gap-8 flex-wrap">
            <div>
              <div className="text-[10px] text-muted font-mono uppercase">Pixels Activos</div>
              <div className="font-mono text-glow text-danger text-2xl">{adminOverview?.total_sites ?? adminStats.total_sites}</div>
            </div>
            <div>
              <div className="text-[10px] text-muted font-mono uppercase">Eventos Totales</div>
              <div className="font-mono text-glow text-danger text-2xl">{adminOverview?.total_events ?? adminStats.total_events}</div>
            </div>
            {adminOverview?.today_events !== undefined && (
              <div>
                <div className="text-[10px] text-muted font-mono uppercase">Hoy</div>
                <div className="font-mono text-glow text-danger text-2xl">{adminOverview.today_events}</div>
              </div>
            )}
          </div>
          {adminOverview?.by_event_type?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {adminOverview.by_event_type.map((t, i) => (
                <span key={i} className="bg-danger/10 text-danger text-[10px] font-mono px-2 py-0.5 rounded">
                  {t.event_type}: {t.count}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {adminEvents.length > 0 && (
        <div className="card-dash overflow-x-auto">
          <div className="p-3 border-b border-white/5 text-[10px] font-mono uppercase text-muted tracking-widest">
            Eventos Globales Recientes ({adminEvents.length})
          </div>
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-white/5 text-muted">
                {['Sitio','Tipo','URL','Dispositivo','País','Fecha'].map(h => (
                  <th key={h} className="text-left p-3 text-[9px] uppercase tracking-widest">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {adminEvents.map(e => (
                <tr key={e.event_id} className="border-b border-white/5 hover:bg-white/3">
                  <td className="p-3 text-[#aa00ff]">{e.site_name || e.site_id?.slice(0, 8)}</td>
                  <td className="p-3 text-white">{e.event_type}</td>
                  <td className="p-3 text-muted truncate max-w-[200px]" title={e.url}>{e.url?.replace(/^https?:\/\//, '') || '—'}</td>
                  <td className="p-3 text-muted">{e.device || '—'}</td>
                  <td className="p-3 text-muted">{e.country ? `${countryFlag(e.country)} ${e.country}` : '—'}</td>
                  <td className="p-3 text-muted">{e.created_at ? new Date(e.created_at).toLocaleString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Form */}
      {showCreate && (
        <div className="card-dash p-6 border-scanner">
          <h3 className="text-sm font-bold mb-4">Registrar Nuevo Sitio</h3>
          <form onClick={e => e.stopPropagation()} onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono text-muted mb-1 uppercase">Nombre del Proyecto</label>
                <input required value={newName} onChange={e => setNewName(e.target.value)}
                  className="input-dash bg-[#050505] font-mono text-sm" placeholder="Ej: Tienda Maria" />
              </div>
              <div>
                <label className="block text-xs font-mono text-muted mb-1 uppercase">Dominio (Opcional)</label>
                <input value={newDomain} onChange={e => setNewDomain(e.target.value)}
                  className="input-dash bg-[#050505] font-mono text-sm" placeholder="Ej: mitienda.com" />
              </div>
            </div>
            <div className="flex justify-end">
              <button disabled={creating} type="submit" className="btn-dash btn-primary-dash">
                {creating ? 'Generando...' : 'Generar Código Tracker'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Main Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">

        {/* Sites Sidebar */}
        <div className="lg:col-span-1 space-y-3">
          <div className="text-[10px] font-mono text-muted uppercase tracking-widest pl-2">Tus Pixels</div>
          {loading ? (
            <div className="p-4 flex justify-center"><Loader className="w-5 h-5 animate-spin text-accent" /></div>
          ) : sites.length === 0 ? (
            <div className="p-4 text-xs text-muted text-center italic bg-white/5 rounded-xl">Sin pixels registrados</div>
          ) : sites.map(site => (
            <div key={site.site_id} onClick={() => setSelectedSite(site)}
                 className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${
                   selectedSite?.site_id === site.site_id
                   ? 'bg-accent/10 border-accent shadow-[0_0_10px_rgba(0,255,136,0.2)]'
                   : 'bg-[#050505] border-white/5 hover:border-white/20'}`}>
              <div>
                <div className="text-sm font-bold flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-accent animate-led" />
                  {site.name}
                </div>
                <div className="text-[9px] font-mono text-muted mt-1">{site.domain || 'Cualquier dominio'}</div>
              </div>
              <button onClick={e => { e.stopPropagation(); handleDelete(site.site_id); }}
                      className="text-danger/50 hover:text-danger hover:bg-danger/10 p-1.5 rounded-lg">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>

        {/* Stats Panel */}
        <div className="lg:col-span-3">
          {!selectedSite ? (
            <div className="h-full min-h-[300px] flex items-center justify-center border border-dashed border-white/10 rounded-2xl">
              <div className="text-center text-muted">
                <BarChart3 className="w-8 h-8 opacity-20 mx-auto mb-2" />
                <div className="text-sm font-mono">Selecciona un sitio para ver el tráfico</div>
              </div>
            </div>
          ) : (
            <div className="space-y-5">

              {/* Snippet */}
              <div className="card-dash p-4 bg-[#050505] border-dashed border-white/20">
                <div className="flex justify-between items-start mb-2">
                  <div className="text-xs font-mono uppercase text-accent tracking-widest">Código de Inserción</div>
                  <button onClick={() => copySnippet(selectedSite.site_id)}
                          className="text-[10px] bg-white/10 hover:bg-white/20 px-2 py-1 rounded flex items-center gap-1 font-mono uppercase">
                    {copiedScript === selectedSite.site_id ? <CheckCircle className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                    {copiedScript === selectedSite.site_id ? 'Copiado!' : 'Copiar'}
                  </button>
                </div>
                <div className="p-3 bg-black rounded-lg border border-white/5 overflow-x-auto text-muted text-xs font-mono whitespace-pre">
                  {`<script src="https://api.hostingguard.lat/pixel.js?id=${selectedSite.site_id}"></script>`}
                </div>
                <div className="text-[10px] text-gray-500 mt-2">Pega esto antes de &lt;/head&gt;</div>
              </div>

              {/* Period selector */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-mono text-muted uppercase tracking-widest">Período:</span>
                {[
                  { label: '1h',  value: 0.042 },
                  { label: '24h', value: 1 },
                  { label: '7d',  value: 7 },
                  { label: '30d', value: 30 },
                  { label: '90d', value: 90 },
                ].map(({ label, value }) => (
                  <button key={label} onClick={() => setDays(value)}
                          className={`text-[10px] font-mono px-2.5 py-1 rounded-lg border transition-all ${
                            days === value ? 'border-accent text-accent bg-accent/10' : 'border-white/10 text-muted hover:border-white/30'}`}>
                    {label}
                  </button>
                ))}
                {chartsLoading && <Loader className="w-3.5 h-3.5 animate-spin text-accent ml-1" />}
              </div>

              {/* Realtime panel — always visible */}
              <RealtimePanel siteId={selectedSite.site_id} />

              {!stats ? (
                <div className="p-10 flex justify-center"><Loader className="w-6 h-6 animate-spin text-accent" /></div>
              ) : (
                <div className="space-y-5">

                  {/* KPI row 1 — primary metrics */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                      { title: 'Vistas Hoy',    val: stats.today_events,              color: 'text-[#00ff88]', bc: 'border-[#00ff88]/20', icon: <Activity className="w-4 h-4 opacity-40" /> },
                      { title: 'Sesiones',       val: stats.unique_sessions,           color: 'text-[#00aaff]', bc: 'border-[#00aaff]/20', icon: <Users    className="w-4 h-4 opacity-40" /> },
                      { title: 'Bounce Rate',    val: `${stats.bounce_rate ?? 0}%`,    color: 'text-[#ffaa00]', bc: 'border-[#ffaa00]/20', icon: <Clock    className="w-4 h-4 opacity-40" /> },
                      { title: 'Activos 5 min',  val: stats.active_users_5min ?? 0,   color: 'text-[#00ff88]', bc: 'border-[#00ff88]/20', icon: <Zap      className="w-4 h-4 opacity-40" /> },
                    ].map((m, i) => (
                      <div key={i} className={`p-3 bg-[#050505] rounded-xl border ${m.bc}`}>
                        <div className="flex justify-between items-start mb-1.5">
                          <div className="text-[9px] font-mono tracking-widest uppercase text-muted">{m.title}</div>
                          {m.icon}
                        </div>
                        <div className={`text-2xl font-black font-mono text-glow ${m.color}`}>{m.val}</div>
                      </div>
                    ))}
                  </div>

                  {/* KPI row 2 — engagement metrics */}
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { title: 'Páginas / Sesión', val: stats.avg_pages_per_session  ?? 0, color: 'text-[#aa44ff]' },
                      { title: 'Tiempo en Pág.',   val: `${stats.avg_time_on_page    ?? 0}s`, color: 'text-[#00aaff]' },
                      { title: 'Eventos / Sesión', val: stats.avg_events_per_session ?? 0, color: 'text-[#ffaa00]' },
                    ].map((m, i) => (
                      <div key={i} className="p-3 bg-[#050505] rounded-xl border border-white/5 text-center">
                        <div className="text-[9px] font-mono text-muted uppercase mb-1">{m.title}</div>
                        <div className={`font-mono font-bold text-lg ${m.color}`}>{m.val}</div>
                      </div>
                    ))}
                  </div>

                  {/* Gate: charts only after 50 events */}
                  <CollectingGate total={stats.total_events}>
                    <div className="space-y-5">

                      {/* Time series */}
                      <div className="card-dash p-4">
                        <div className="text-xs font-mono font-bold uppercase mb-3 text-white flex items-center gap-2">
                          <Activity className="w-3.5 h-3.5 text-accent" />
                          Actividad — {days <= 1 ? 'últimas 24 h (por hora)' : `últimos ${days} días`}
                        </div>
                        <TimeSeriesChart data={timeseries} />
                      </div>

                      {/* Pages + Devices/Countries */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

                        <div className="card-dash p-4">
                          <div className="text-xs font-mono font-bold uppercase mb-4 text-white flex items-center gap-2">
                            <Globe className="w-3.5 h-3.5 text-accent" /> Top Páginas
                          </div>
                          <HBarChart data={pages} labelKey="url" valueKey="views" color="#00ff88"
                            formatLabel={url => url?.replace(/^https?:\/\/[^/]+/, '') || '/'} />
                        </div>

                        <div className="space-y-4">
                          <div className="card-dash p-4">
                            <div className="text-xs font-mono font-bold uppercase mb-3 flex items-center gap-2 text-white">
                              <Monitor className="w-3.5 h-3.5 text-blue-400" /> Por Dispositivo
                            </div>
                            <DonutChart data={devices} colorMap={DEVICE_COLORS} />
                          </div>

                          <div className="card-dash p-4">
                            <div className="text-xs font-mono font-bold uppercase mb-3 flex items-center gap-2 text-white">
                              <Globe className="w-3.5 h-3.5 text-purple-400" /> Por País
                            </div>
                            {countries === null ? (
                              <div className="flex items-center gap-2 py-3 text-xs text-muted">
                                <Loader className="w-3 h-3 animate-spin text-accent" /> Cargando...
                              </div>
                            ) : countries.length === 0 ? (
                              <div className="text-[10px] text-muted italic">GeoIP resolviendo...</div>
                            ) : (
                              <HBarChart data={countries} labelKey="country" valueKey="count" color="#aa44ff"
                                formatLabel={c => c ? `${countryFlag(c)} ${c}` : '??'} />
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Funnel */}
                      <FunnelPanel siteId={selectedSite.site_id} days={days} />

                      {/* Performance (only if data exists) */}
                      {(stats.performance?.avg_load_ms > 0) && (
                        <div className="grid grid-cols-2 gap-3">
                          <div className="p-3 bg-[#050505] rounded-xl border border-white/5 text-center">
                            <div className="text-[9px] font-mono text-muted uppercase mb-1">Carga Prom.</div>
                            <div className="font-mono font-bold text-[#00aaff]">{stats.performance.avg_load_ms}ms</div>
                          </div>
                          <div className="p-3 bg-[#050505] rounded-xl border border-white/5 text-center">
                            <div className="text-[9px] font-mono text-muted uppercase mb-1">TTFB Prom.</div>
                            <div className="font-mono font-bold text-[#ffaa00]">{stats.performance.avg_ttfb_ms}ms</div>
                          </div>
                        </div>
                      )}

                    </div>
                  </CollectingGate>

                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
