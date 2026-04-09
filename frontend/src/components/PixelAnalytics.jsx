import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { getAdminPixelOverview, getAdminPixelEvents } from '../services/api';
import { Plus, Trash2, Copy, CheckCircle, BarChart3, Globe, Users, Clock, Monitor, X, Loader, Activity, Database } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

// ── Inline Charts ──────────────────────────────────────────────────────────

function TimeSeriesChart({ data }) {
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
        <div className="text-xs text-muted italic">Recolectando datos... aparecerá aquí cuando lleguen visitas.</div>
      </div>
    );
  }

  const W = 520, H = 110, padL = 28, padR = 8, padT = 18, padB = 22;
  const cW = W - padL - padR;
  const cH = H - padT - padB;

  const maxPV  = Math.max(...data.map(d => d.page_views), 1);
  const maxSes = Math.max(...data.map(d => d.sessions),   1);
  const maxY   = Math.max(maxPV, maxSes, 1);

  const xOf = (i) => padL + (data.length > 1 ? (i / (data.length - 1)) * cW : cW / 2);
  const yOf = (v) => padT + cH - (v / maxY) * cH;

  const pvPts  = data.map((d, i) => `${xOf(i)},${yOf(d.page_views)}`).join(' ');
  const sesPts = data.map((d, i) => `${xOf(i)},${yOf(d.sessions)}`).join(' ');

  // 4 grid lines
  const grid = [0, 0.33, 0.66, 1].map(f => ({
    y:   padT + cH - f * cH,
    val: Math.round(maxY * f),
  }));

  // X-axis labels: first, middle, last (de-dup)
  const xLabels = [...new Set([0, Math.floor((data.length - 1) / 2), data.length - 1])];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 130 }} preserveAspectRatio="xMidYMid meet">
      {/* Grid lines */}
      {grid.map((g, i) => (
        <g key={i}>
          <line x1={padL} y1={g.y} x2={W - padR} y2={g.y} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
          <text x={padL - 3} y={g.y} textAnchor="end" fontSize="7" fill="rgba(255,255,255,0.25)" dy="0.3em">{g.val}</text>
        </g>
      ))}

      {/* Page views area */}
      <polygon
        points={`${xOf(0)},${padT + cH} ${pvPts} ${xOf(data.length - 1)},${padT + cH}`}
        fill="rgba(0,255,136,0.08)"
      />

      {/* Lines */}
      <polyline fill="none" stroke="#00ff88" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" points={pvPts} />
      <polyline fill="none" stroke="#00aaff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="3,2" points={sesPts} />

      {/* Dots on last point */}
      {data.length > 0 && (
        <>
          <circle cx={xOf(data.length - 1)} cy={yOf(data[data.length - 1].page_views)} r="3" fill="#00ff88" />
          <circle cx={xOf(data.length - 1)} cy={yOf(data[data.length - 1].sessions)}   r="3" fill="#00aaff" />
        </>
      )}

      {/* X labels */}
      {xLabels.map(i => (
        <text key={i} x={xOf(i)} y={H - 4} textAnchor="middle" fontSize="7" fill="rgba(255,255,255,0.35)">
          {data[i]?.day?.slice(5)}
        </text>
      ))}

      {/* Legend */}
      <rect x={padL} y={3} width="7" height="7" fill="#00ff88" rx="1.5" />
      <text x={padL + 10} y={9} fontSize="7.5" fill="#00ff88">Vistas</text>
      <rect x={padL + 52} y={3} width="7" height="7" fill="#00aaff" rx="1.5" />
      <text x={padL + 62} y={9} fontSize="7.5" fill="#00aaff">Sesiones</text>
    </svg>
  );
}

const DEVICE_COLORS = { mobile: '#00aaff', desktop: '#00ff88', tablet: '#ffaa00', other: '#aa44ff', unknown: '#666' };
const COUNTRY_COLORS = ['#00ff88', '#00aaff', '#ffaa00', '#aa44ff', '#ff4466', '#44ffcc', '#ff8800', '#ff00aa', '#88ff00', '#0088ff'];

function DonutChart({ data, colorMap }) {
  if (data === null) {
    return <div className="flex items-center gap-2 py-3 text-xs text-muted"><Loader className="w-3 h-3 animate-spin text-accent" /> Cargando...</div>;
  }
  if (!data || data.length === 0) {
    return <div className="text-xs text-muted italic">Recolectando datos...</div>;
  }

  const total = data.reduce((s, d) => s + Number(d.count), 0);
  if (!total) return <div className="text-xs text-muted italic">Sin datos</div>;

  const cx = 55, cy = 55, outerR = 46, innerR = 28;
  let angle = -Math.PI / 2;

  const slices = data.map((d, i) => {
    const frac  = Number(d.count) / total;
    const sweep = frac * 2 * Math.PI;
    const x1  = cx + outerR * Math.cos(angle);
    const y1  = cy + outerR * Math.sin(angle);
    const x2  = cx + outerR * Math.cos(angle + sweep);
    const y2  = cy + outerR * Math.sin(angle + sweep);
    const ix1 = cx + innerR * Math.cos(angle + sweep);
    const iy1 = cy + innerR * Math.sin(angle + sweep);
    const ix2 = cx + innerR * Math.cos(angle);
    const iy2 = cy + innerR * Math.sin(angle);
    const large = sweep > Math.PI ? 1 : 0;
    const path = `M${x1},${y1} A${outerR},${outerR} 0 ${large} 1 ${x2},${y2} L${ix1},${iy1} A${innerR},${innerR} 0 ${large} 0 ${ix2},${iy2} Z`;
    const color = colorMap
      ? (colorMap[d.device || d.country] || COUNTRY_COLORS[i % COUNTRY_COLORS.length])
      : COUNTRY_COLORS[i % COUNTRY_COLORS.length];
    angle += sweep;
    return { path, color, label: d.device || d.country || '?', count: d.count, pct: Math.round(frac * 100) };
  });

  return (
    <div className="flex items-center gap-5">
      <svg viewBox="0 0 110 110" className="w-20 h-20 shrink-0">
        {slices.map((s, i) => <path key={i} d={s.path} fill={s.color} />)}
        <text x={cx} y={cy - 5} textAnchor="middle" fontSize="13" fontWeight="bold" fill="white">{total}</text>
        <text x={cx} y={cy + 9} textAnchor="middle" fontSize="7" fill="rgba(255,255,255,0.4)">total</text>
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
        const pct = (Number(d[valueKey]) / max) * 100;
        return (
          <div key={i} className="flex items-center gap-2 text-xs">
            <div className="w-32 truncate text-right text-muted shrink-0 text-[10px]" title={d[labelKey]}>
              {label}
            </div>
            <div className="flex-1 bg-white/5 rounded-full h-2.5 relative overflow-hidden">
              <div
                className="absolute inset-y-0 left-0 rounded-full transition-all duration-500"
                style={{ width: `${pct}%`, background: color, opacity: 0.75 }}
              />
            </div>
            <div className="w-8 text-right font-mono shrink-0 text-[10px]" style={{ color }}>
              {d[valueKey]}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────

export default function PixelAnalytics() {
  const { user } = useAuth();
  const [sites, setSites]             = useState([]);
  const [loading, setLoading]         = useState(true);
  const [selectedSite, setSelectedSite] = useState(null);
  const [days, setDays]               = useState(30);

  // KPI metrics (from /stats)
  const [stats, setStats]             = useState(null);
  // Chart data (from individual endpoints)
  const [timeseries, setTimeseries]   = useState(null);
  const [devices, setDevices]         = useState(null);
  const [countries, setCountries]     = useState(null);
  const [pages, setPages]             = useState(null);
  const [chartsLoading, setChartsLoading] = useState(false);

  // Admin
  const [adminStats, setAdminStats]   = useState(null);
  const [adminOverview, setAdminOverview] = useState(null);
  const [adminEvents, setAdminEvents] = useState([]);

  // Create form
  const [showCreate, setShowCreate]   = useState(false);
  const [newName, setNewName]         = useState('');
  const [newDomain, setNewDomain]     = useState('');
  const [creating, setCreating]       = useState(false);
  const [copiedScript, setCopiedScript] = useState(null);

  const fetchSites = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/pixel/sites');
      setSites(data);
      if (data.length > 0 && !selectedSite) setSelectedSite(data[0]);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
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
    } catch (err) {
      console.error(err);
    }
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
      // Debug: inspect raw chart data
      console.log('[PixelAnalytics] charts loaded:', {
        stats: statsRes.data,
        timeseries: tsRes.data,
        devices: devRes.data,
        countries: cntRes.data,
        pages: pgRes.data,
      });
    } catch (err) {
      console.error('[PixelAnalytics] fetch error:', err);
    } finally {
      setChartsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSites();
    fetchAdminStats();
  }, []);

  useEffect(() => {
    if (!selectedSite) return;
    fetchAllCharts(selectedSite.site_id, days);
    const interval = setInterval(() => fetchAllCharts(selectedSite.site_id, days), 30000);
    return () => clearInterval(interval);
  }, [selectedSite, days, fetchAllCharts]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post('/pixel/sites', { name: newName, domain: newDomain });
      setShowCreate(false);
      setNewName('');
      setNewDomain('');
      fetchSites();
    } catch (err) {
      console.error(err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (siteId) => {
    if (!confirm('¿Seguro que quieres eliminar este sitio web y TODOS sus datos analíticos?')) return;
    try {
      await api.delete(`/pixel/sites/${siteId}`);
      if (selectedSite?.site_id === siteId) { setSelectedSite(null); setStats(null); }
      fetchSites();
    } catch (err) {
      console.error(err);
    }
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
            <BarChart3 className="w-5 h-5 text-accent" /> Pixel Analytics Server
          </h2>
          <p className="text-sm text-gray-400">Rastrea visitas y eventos en cualquier página web.</p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="btn-dash btn-primary-dash text-sm font-bold flex items-center gap-2"
        >
          {showCreate ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          {showCreate ? 'Cancelar' : 'Registrar Sitio'}
        </button>
      </div>

      {/* Admin Panel */}
      {adminStats && (
        <div className="p-4 bg-danger/10 border border-danger/30 rounded-2xl border-scanner-warn">
          <div className="text-[10px] text-danger font-mono tracking-widest uppercase mb-2">⚡ GLOBAL ADMIN STATS</div>
          <div className="flex gap-8 flex-wrap">
            <div>
              <div className="text-[10px] text-muted font-mono uppercase">Total Pixels Activos</div>
              <div className="font-mono text-glow text-danger text-2xl">{adminOverview?.total_sites ?? adminStats.total_sites}</div>
            </div>
            <div>
              <div className="text-[10px] text-muted font-mono uppercase">Eventos Recibidos</div>
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

      {/* Admin events table */}
      {adminEvents.length > 0 && (
        <div className="card-dash overflow-x-auto">
          <div className="p-3 border-b border-white/5 text-[10px] font-mono uppercase text-muted tracking-widest">
            Eventos Globales Recientes ({adminEvents.length})
          </div>
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-white/5 text-muted">
                {['Sitio', 'Tipo', 'URL', 'Dispositivo', 'País', 'Fecha'].map(h => (
                  <th key={h} className="text-left p-3 text-[9px] uppercase tracking-widest">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {adminEvents.map(e => (
                <tr key={e.event_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                  <td className="p-3 text-[#aa00ff]">{e.site_name || e.site_id?.slice(0, 8)}</td>
                  <td className="p-3 text-white">{e.event_type}</td>
                  <td className="p-3 text-muted truncate max-w-[200px]" title={e.url}>{e.url?.replace(/^https?:\/\//, '') || '—'}</td>
                  <td className="p-3 text-muted">{e.device || '—'}</td>
                  <td className="p-3 text-muted">{e.country || '—'}</td>
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
          <h3 className="text-sm font-bold mb-4">Registrar Nuevo Sitio para Pixel</h3>
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

        {/* Sites List */}
        <div className="lg:col-span-1 space-y-3">
          <div className="text-[10px] font-mono text-muted uppercase tracking-widest pl-2">TUS SITIOS (PIXELS)</div>
          {loading ? (
            <div className="p-4 flex justify-center"><Loader className="w-5 h-5 animate-spin text-accent" /></div>
          ) : sites.length === 0 ? (
            <div className="p-4 text-xs text-muted text-center italic bg-white/5 rounded-xl">Sin pixels registrados</div>
          ) : (
            sites.map(site => (
              <div
                key={site.site_id}
                onClick={() => setSelectedSite(site)}
                className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${
                  selectedSite?.site_id === site.site_id
                    ? 'bg-accent/10 border-accent text-white shadow-[0_0_10px_rgba(0,255,136,0.2)]'
                    : 'bg-[#050505] border-white/5 hover:border-white/20'
                }`}
              >
                <div>
                  <div className="text-sm font-bold flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-accent animate-led" />
                    {site.name}
                  </div>
                  <div className="text-[9px] font-mono text-muted mt-1">{site.domain || 'Cualquier dominio'}</div>
                </div>
                <button
                  onClick={e => { e.stopPropagation(); handleDelete(site.site_id); }}
                  className="text-danger/50 hover:text-danger hover:bg-danger/10 p-1.5 rounded-lg"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Stats View */}
        <div className="lg:col-span-3">
          {selectedSite ? (
            <div className="space-y-5">

              {/* Snippet */}
              <div className="card-dash p-5 bg-[#050505] border-dashed border-white/20">
                <div className="flex justify-between items-start mb-2">
                  <div className="text-xs font-mono uppercase text-accent tracking-widest">Código de Inserción</div>
                  <button
                    onClick={() => copySnippet(selectedSite.site_id)}
                    className="text-[10px] bg-white/10 hover:bg-white/20 px-2 py-1 rounded flex items-center gap-1 font-mono uppercase"
                  >
                    {copiedScript === selectedSite.site_id ? <CheckCircle className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                    {copiedScript === selectedSite.site_id ? 'Copiado!' : 'Copiar'}
                  </button>
                </div>
                <div className="p-3 bg-black rounded-lg border border-white/5 overflow-x-auto text-muted text-xs font-mono whitespace-pre">
                  {`<script src="https://api.hostingguard.lat/pixel.js?id=${selectedSite.site_id}"></script>`}
                </div>
                <div className="text-[10px] text-gray-500 mt-2">Pega esto justo antes de cerrar la etiqueta &lt;/head&gt; de tu sitio web.</div>
              </div>

              {/* Period selector */}
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-muted uppercase tracking-widest">Período:</span>
                {[7, 14, 30, 90].map(d => (
                  <button
                    key={d}
                    onClick={() => setDays(d)}
                    className={`text-[10px] font-mono px-2.5 py-1 rounded-lg border transition-all ${
                      days === d ? 'border-accent text-accent bg-accent/10' : 'border-white/10 text-muted hover:border-white/30'
                    }`}
                  >
                    {d}d
                  </button>
                ))}
                {chartsLoading && <Loader className="w-3.5 h-3.5 animate-spin text-accent ml-1" />}
              </div>

              {!stats ? (
                <div className="p-10 flex justify-center"><Loader className="w-6 h-6 animate-spin text-accent" /></div>
              ) : (
                <div className="space-y-5">

                  {/* "Collecting data" banner — shown until first events arrive */}
                  {stats.total_events === 0 && (
                    <div className="card-dash p-5 border border-dashed border-accent/25 text-center">
                      <Activity className="w-6 h-6 mx-auto mb-2 text-accent opacity-30" />
                      <div className="text-sm text-white font-medium mb-1">Pixel instalado — esperando visitas</div>
                      <div className="text-xs text-muted">Los gráficos aparecerán automáticamente cuando el script registre eventos.</div>
                      <div className="mt-3 text-[10px] font-mono text-accent/60">
                        Tip: copia el snippet de arriba y pégalo en tu sitio, luego visita la página.
                      </div>
                    </div>
                  )}

                  {/* KPI cards */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[
                      { title: 'Vistas Hoy',      val: stats.today_events,                icon: <Activity className="w-4 h-4 opacity-50" />, color: 'text-[#00ff88]', bc: 'border-[#00ff88]/20' },
                      { title: 'Eventos Totales', val: stats.total_events,                icon: <Database className="w-4 h-4 opacity-50" />, color: 'text-[#00aaff]', bc: 'border-[#00aaff]/20' },
                      { title: 'Sesiones Únicas', val: stats.unique_sessions,             icon: <Users   className="w-4 h-4 opacity-50" />, color: 'text-[#ffaa00]', bc: 'border-[#ffaa00]/20' },
                      { title: 'Bounce Rate',     val: `${stats.bounce_rate ?? 0}%`,      icon: <Clock   className="w-4 h-4 opacity-50" />, color: 'text-[#aa00ff]', bc: 'border-[#aa00ff]/20' },
                    ].map((m, i) => (
                      <div key={i} className={`p-4 bg-[#050505] rounded-xl border ${m.bc} relative overflow-hidden`}>
                        <div className="flex justify-between items-start mb-2">
                          <div className="text-[9px] font-mono tracking-widest uppercase text-muted">{m.title}</div>
                          {m.icon}
                        </div>
                        <div className={`text-2xl font-black font-mono text-glow ${m.color}`}>{m.val}</div>
                      </div>
                    ))}
                  </div>

                  {/* Time series chart */}
                  <div className="card-dash p-4">
                    <div className="text-xs font-mono font-bold uppercase mb-3 text-white flex items-center gap-2">
                      <Activity className="w-3.5 h-3.5 text-accent" /> Actividad — últimos {days} días
                    </div>
                    <TimeSeriesChart data={timeseries} />
                  </div>

                  {/* 2-col grid: Pages | Devices + Countries */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

                    {/* Top Pages */}
                    <div className="card-dash p-4">
                      <div className="text-xs font-mono font-bold uppercase mb-4 text-white flex items-center gap-2">
                        <Globe className="w-3.5 h-3.5 text-accent" /> Top Páginas
                      </div>
                      <HBarChart
                        data={pages}
                        labelKey="url"
                        valueKey="views"
                        color="#00ff88"
                        formatLabel={url => url?.replace(/^https?:\/\/[^/]+/, '') || '/'}
                      />
                    </div>

                    {/* Devices + Countries */}
                    <div className="space-y-4">

                      {/* Devices donut */}
                      <div className="card-dash p-4">
                        <div className="text-xs font-mono font-bold uppercase mb-3 flex items-center gap-2 text-white">
                          <Monitor className="w-3.5 h-3.5 text-blue-400" /> Por Dispositivo
                        </div>
                        <DonutChart data={devices} colorMap={DEVICE_COLORS} />
                      </div>

                      {/* Countries bar */}
                      <div className="card-dash p-4">
                        <div className="text-xs font-mono font-bold uppercase mb-3 flex items-center gap-2 text-white">
                          <Globe className="w-3.5 h-3.5 text-purple-400" /> Por País (IP)
                        </div>
                        {countries === null ? (
                          <div className="flex items-center gap-2 py-3 text-xs text-muted">
                            <Loader className="w-3 h-3 animate-spin text-accent" /> Cargando...
                          </div>
                        ) : countries.length === 0 ? (
                          <div className="text-[10px] text-muted italic">
                            Recolectando datos... (requiere GeoIP resuelto)
                          </div>
                        ) : (
                          <HBarChart
                            data={countries}
                            labelKey="country"
                            valueKey="count"
                            color="#aa44ff"
                          />
                        )}
                      </div>

                    </div>
                  </div>

                  {/* Performance row */}
                  {(stats.performance?.avg_load_ms > 0 || stats.avg_time_on_page > 0) && (
                    <div className="grid grid-cols-3 gap-4">
                      {[
                        { title: 'Tiempo en Página', val: `${stats.avg_time_on_page}s`,           color: 'text-[#00ff88]' },
                        { title: 'Carga Prom.',      val: `${stats.performance.avg_load_ms}ms`,   color: 'text-[#00aaff]' },
                        { title: 'TTFB Prom.',       val: `${stats.performance.avg_ttfb_ms}ms`,   color: 'text-[#ffaa00]' },
                      ].map((m, i) => (
                        <div key={i} className="p-3 bg-[#050505] rounded-xl border border-white/5 text-center">
                          <div className="text-[9px] font-mono text-muted uppercase mb-1">{m.title}</div>
                          <div className={`font-mono font-bold ${m.color}`}>{m.val}</div>
                        </div>
                      ))}
                    </div>
                  )}

                </div>
              )}
            </div>
          ) : (
            <div className="h-full min-h-[300px] flex items-center justify-center border border-dashed border-white/10 rounded-2xl">
              <div className="text-center text-muted">
                <BarChart3 className="w-8 h-8 opacity-20 mx-auto mb-2" />
                <div className="text-sm font-mono">Selecciona un sitio para ver el tráfico</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
