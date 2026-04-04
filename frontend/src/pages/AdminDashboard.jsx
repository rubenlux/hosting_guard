import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users, Globe, BarChart3, RefreshCw, ShieldCheck, Activity,
  LogOut, Zap, Bell, Settings, CheckCircle2,
  XCircle, Clock, DollarSign, FileText, Bot,
  TrendingUp, MousePointer, Eye, Timer, ArrowRight
} from 'lucide-react';
import {
  getAdminUsers, getAdminHostings, getAdminPixelOverview,
  getAdminPixelEvents, getAdminHostingsMetrics,
  getAdminOrchestratorEvents, getAdminFinanceSummary,
} from '../services/api';
import { useAuth } from '../hooks/useAuth';

/* ─── helpers ─────────────────────────────────────────────── */
function groupBy(arr, key) {
  return arr.reduce((acc, item) => {
    const k = item[key] || 'unknown';
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, {});
}
function topN(obj, n = 8) {
  return Object.entries(obj).sort((a, b) => b[1] - a[1]).slice(0, n);
}
function fmtTime(secs) {
  if (!secs) return '—';
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}
function fmtDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/* ─── constants ───────────────────────────────────────────── */
const NAV = [
  { id: 'overview',      label: 'Dashboard',        icon: Activity },
  { id: 'users',         label: 'User Management',  icon: Users },
  { id: 'hostings',      label: 'Hosting',          icon: Globe },
  { id: 'pixel',         label: 'Pixel Analytics',  icon: BarChart3 },
  { id: 'pixel-users',   label: 'Pixel Users',      icon: Users,     path: '/admin/pixel-users' },
  { id: 'orchestrator',  label: 'Orchestrator',     icon: Bot },
  { id: 'finance',       label: 'Finance',          icon: DollarSign },
  { id: 'audit',         label: 'Audit Log',        icon: FileText },
  { id: 'settings',      label: 'Settings',         icon: Settings },
];

const PLAN_STYLE = {
  free:     'bg-white/5 text-gray-400',
  personal: 'bg-blue-500/20 text-blue-400',
  negocio:  'bg-amber-500/20 text-amber-400',
  agencia:  'bg-purple-500/20 text-purple-400',
  pro:      'bg-emerald-500/20 text-emerald-400',
};
const STATUS_COLOR = { active: 'text-emerald-400', stopped: 'text-red-400', expired: 'text-red-600', error: 'text-red-400', starting: 'text-amber-400' };
const STATUS_ICON  = { active: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />, stopped: <XCircle className="w-3.5 h-3.5 text-red-400" />, expired: <XCircle className="w-3.5 h-3.5 text-red-600" />, error: <XCircle className="w-3.5 h-3.5 text-red-400" />, starting: <Clock className="w-3.5 h-3.5 text-amber-400" /> };

const ORC_COLOR = { autoscale: 'text-blue-400 bg-blue-500/10', throttle: 'text-amber-400 bg-amber-500/10', restart: 'text-red-400 bg-red-500/10', alert: 'text-orange-400 bg-orange-500/10', info: 'text-gray-400 bg-white/5' };

/* ─── Initials avatar ─────────────────────────────────────── */
function Initials({ email, size = 7 }) {
  const letters = email ? email.slice(0, 2).toUpperCase() : '??';
  const colors = ['bg-blue-600', 'bg-purple-600', 'bg-emerald-600', 'bg-amber-600', 'bg-rose-600'];
  const color = colors[(email?.charCodeAt(0) || 0) % colors.length];
  return (
    <div className={`w-${size} h-${size} rounded-full ${color} flex items-center justify-center text-[10px] font-bold text-white shrink-0`}>
      {letters}
    </div>
  );
}

/* ─── Bar chart (CSS) ─────────────────────────────────────── */
function HBar({ data, color = '#00ff88', labelWidth = 'w-28' }) {
  const max = Math.max(...data.map(d => d.value), 1);
  return (
    <div className="flex flex-col gap-2">
      {data.map((d, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className={`${labelWidth} text-[10px] text-gray-400 truncate text-right`} title={d.label}>{d.label}</div>
          <div className="flex-1 h-4 bg-white/5 rounded overflow-hidden">
            <div className="h-full rounded transition-all" style={{ width: `${(d.value / max) * 100}%`, background: color }} />
          </div>
          <div className="w-10 text-[10px] text-gray-300 font-mono text-right">{d.value}</div>
          <div className="w-8 text-[9px] text-gray-600 font-mono">{Math.round((d.value / max) * 100)}%</div>
        </div>
      ))}
    </div>
  );
}

/* ─── Donut chart (CSS conic-gradient) ───────────────────── */
const DONUT_COLORS = ['#00ff88', '#00aaff', '#ffaa00', '#aa00ff', '#ff6b6b', '#4ecdc4'];
function DonutChart({ segments }) {
  const total = segments.reduce((a, b) => a + b.value, 0) || 1;
  let acc = 0;
  const gradient = segments.map((s, i) => {
    const pct = (s.value / total) * 100;
    const from = acc; acc += pct;
    return `${DONUT_COLORS[i % DONUT_COLORS.length]} ${from.toFixed(1)}% ${acc.toFixed(1)}%`;
  }).join(', ');
  return (
    <div className="flex items-center gap-6">
      <div className="relative w-24 h-24 shrink-0">
        <div className="w-24 h-24 rounded-full" style={{ background: `conic-gradient(${gradient})` }} />
        <div className="absolute inset-3 rounded-full bg-[#111]" />
      </div>
      <div className="flex flex-col gap-1.5">
        {segments.map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-[10px]">
            <div className="w-2 h-2 rounded-sm shrink-0" style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
            <span className="text-gray-400 truncate">{s.label}</span>
            <span className="font-mono text-white ml-auto pl-3">{Math.round((s.value / total) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── Stat card ───────────────────────────────────────────── */
function StatCard({ label, val, sub, color, icon, loading }) {
  return (
    <div className="bg-[#111] rounded-xl border border-white/5 p-4">
      <div className="flex items-start justify-between mb-3">
        <span className="text-[10px] text-gray-500 uppercase tracking-wider font-medium">{label}</span>
        <div style={{ color }} className="opacity-60">{icon}</div>
      </div>
      <div className="text-2xl font-bold" style={{ color }}>
        {loading ? <div className="w-12 h-6 bg-white/5 rounded animate-pulse" /> : val}
      </div>
      {sub && <div className="text-[10px] text-gray-500 mt-1 font-mono">{sub}</div>}
    </div>
  );
}

/* ─── Section wrapper ─────────────────────────────────────── */
function Section({ title, children }) {
  return (
    <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
      {title && <div className="px-4 py-3 border-b border-white/5 text-[11px] font-semibold text-white">{title}</div>}
      <div className="p-4">{children}</div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════
   MAIN COMPONENT
══════════════════════════════════════════════════════════════ */
export default function AdminDashboard() {
  const navigate = useNavigate();
  const { logoutAction, user } = useAuth();

  const [section, setSection]           = useState('overview');
  const [users, setUsers]               = useState([]);
  const [hostings, setHostings]         = useState([]);
  const [hostingMetrics, setHostingMetrics] = useState([]);
  const [pixelOverview, setPixelOverview]   = useState(null);
  const [pixelEvents, setPixelEvents]       = useState([]);
  const [orcEvents, setOrcEvents]           = useState([]);
  const [finance, setFinance]               = useState(null);
  const [loading, setLoading]           = useState(true);
  const [tab, setTab]                   = useState('users');
  const [pixelFilter, setPixelFilter]   = useState('all');

  const fetchAll = async () => {
    setLoading(true);
    const results = await Promise.allSettled([
      getAdminUsers(),
      getAdminHostings(),
      getAdminHostingsMetrics(),
      getAdminPixelOverview(),
      getAdminPixelEvents(500, 0),
      getAdminOrchestratorEvents(200),
      getAdminFinanceSummary(),
    ]);
    if (results[0].status === 'fulfilled') setUsers(results[0].value);
    if (results[1].status === 'fulfilled') setHostings(results[1].value);
    if (results[2].status === 'fulfilled') setHostingMetrics(results[2].value);
    if (results[3].status === 'fulfilled') setPixelOverview(results[3].value);
    if (results[4].status === 'fulfilled') setPixelEvents(results[4].value);
    if (results[5].status === 'fulfilled') setOrcEvents(results[5].value);
    if (results[6].status === 'fulfilled') setFinance(results[6].value);
    setLoading(false);
  };

  useEffect(() => { fetchAll(); }, []);

  /* ── pixel analytics computed ── */
  const pixelAnalytics = useMemo(() => {
    if (!pixelEvents.length) return null;
    const views   = pixelEvents.filter(e => e.event_type === 'page_view');
    const clicks  = pixelEvents.filter(e => e.event_type === 'click');
    const exits   = pixelEvents.filter(e => e.event_type === 'page_exit');

    const sessions = new Set(pixelEvents.map(e => e.session_id).filter(Boolean));
    const sessionCounts = {};
    pixelEvents.forEach(e => { if (e.session_id) sessionCounts[e.session_id] = (sessionCounts[e.session_id] || 0) + 1; });
    const bounceSessions = Object.values(sessionCounts).filter(c => c === 1).length;
    const bounceRate = sessions.size ? Math.round((bounceSessions / sessions.size) * 100) : 0;

    const exitTimes = exits.map(e => e.properties?.time_on_page).filter(t => typeof t === 'number');
    const avgTime = exitTimes.length ? Math.round(exitTimes.reduce((a, b) => a + b, 0) / exitTimes.length) : null;

    const deviceData  = topN(groupBy(pixelEvents, 'device')).map(([label, value]) => ({ label, value }));
    const browserData = topN(groupBy(pixelEvents, 'browser')).map(([label, value]) => ({ label, value }));
    const osData      = topN(groupBy(pixelEvents, 'os')).map(([label, value]) => ({ label, value }));

    const urlCounts = groupBy(views.map(e => ({ ...e, url: e.url?.replace(/^https?:\/\/[^/]+/, '') || '/' })), 'url');
    const topUrls = topN(urlCounts, 10).map(([label, value]) => ({ label, value }));

    const refCounts = {};
    views.forEach(e => {
      const ref = e.referrer ? (e.referrer.match(/^https?:\/\/([^/]+)/) || [, e.referrer])[1] : 'Directo';
      refCounts[ref] = (refCounts[ref] || 0) + 1;
    });
    const topRefs = topN(refCounts, 8).map(([label, value]) => ({ label, value }));

    const clickTexts = {};
    clicks.forEach(e => {
      const txt = e.properties?.text?.slice(0, 40) || e.properties?.element || '(sin texto)';
      clickTexts[txt] = (clickTexts[txt] || 0) + 1;
    });
    const topClicks = topN(clickTexts, 8).map(([label, value]) => ({ label, value }));

    const exitUrls = groupBy(exits.map(e => ({ ...e, url: e.url?.replace(/^https?:\/\/[^/]+/, '') || '/' })), 'url');
    const topExitPages = topN(exitUrls, 6).map(([label, value]) => ({ label, value }));

    const timeByUrl = {};
    exits.forEach(e => {
      const url = e.url?.replace(/^https?:\/\/[^/]+/, '') || '/';
      const t = e.properties?.time_on_page;
      if (typeof t === 'number') {
        if (!timeByUrl[url]) timeByUrl[url] = [];
        timeByUrl[url].push(t);
      }
    });
    const avgTimeByUrl = Object.entries(timeByUrl)
      .map(([url, times]) => ({ label: url, value: Math.round(times.reduce((a, b) => a + b, 0) / times.length) }))
      .sort((a, b) => b.value - a.value).slice(0, 8);

    const eventTypeDist = [
      { label: 'Page Views', value: views.length },
      { label: 'Clicks',     value: clicks.length },
      { label: 'Exits',      value: exits.length },
    ];

    return {
      totalEvents: pixelEvents.length, sessions: sessions.size,
      views: views.length, clicks: clicks.length, exits: exits.length,
      bounceRate, avgTime,
      deviceData, browserData, osData, topUrls, topRefs, topClicks, topExitPages, avgTimeByUrl, eventTypeDist,
    };
  }, [pixelEvents]);

  /* ── alerts from real data ── */
  const alerts = [
    ...hostings.filter(h => h.status === 'error').map(h => ({ level: 'error', title: `Error en ${h.name}`, body: `Contenedor ${h.container_name} en estado error.` })),
    ...hostings.filter(h => h.status === 'stopped').map(h => ({ level: 'warn', title: 'Sitio detenido', body: `${h.name} (${h.subdomain}) está parado.` })),
    ...hostings.filter(h => h.plan === 'free' && h.days_remaining != null && h.days_remaining > 0 && h.days_remaining <= 3).map(h => ({ level: 'info', title: 'Expira pronto', body: `${h.name} vence en ${h.days_remaining} día(s).` })),
  ];
  const ALERT_STYLE = { error: 'border-red-500/30 bg-red-500/5', warn: 'border-amber-500/30 bg-amber-500/5', info: 'border-blue-500/30 bg-blue-500/5' };
  const ALERT_DOT   = { error: 'bg-red-400', warn: 'bg-amber-400', info: 'bg-blue-400' };

  /* ── metrics map ── */
  const metricsMap = useMemo(() => {
    const m = {};
    hostingMetrics.forEach(h => { m[h.container_name] = h; });
    return m;
  }, [hostingMetrics]);

  /* ── filtered pixel events ── */
  const filteredPixel = useMemo(() => pixelFilter === 'all' ? pixelEvents : pixelEvents.filter(e => e.event_type === pixelFilter), [pixelEvents, pixelFilter]);

  /* ══════════════════════════════════════════════════════════
     RENDER
  ═══════════════════════════════════════════════════════════ */
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

        <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5 overflow-y-auto">
          {NAV.map(({ id, label, icon: Icon, path }) => (
            <button
              key={id}
              onClick={() => path ? navigate(path) : setSection(id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[12px] font-medium transition-all text-left ${
                section === id
                  ? 'bg-[#00ff88]/10 text-[#00ff88] border border-[#00ff88]/20'
                  : 'text-gray-400 hover:bg-white/5 hover:text-white border border-transparent'
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
              {id === 'orchestrator' && orcEvents.length > 0 && (
                <span className="ml-auto bg-amber-500/20 text-amber-400 text-[8px] px-1.5 py-0.5 rounded-full font-mono">
                  {orcEvents.length}
                </span>
              )}
              {id === 'pixel' && alerts.filter(a => a.level === 'error').length > 0 && (
                <span className="ml-auto bg-red-500/20 text-red-400 text-[8px] px-1.5 py-0.5 rounded-full font-mono">!</span>
              )}
            </button>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-white/5">
          <button onClick={logoutAction} className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[12px] text-gray-500 hover:bg-red-500/10 hover:text-red-400 transition-all">
            <LogOut className="w-4 h-4" /> Logout
          </button>
        </div>
      </aside>

      {/* ── MAIN ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Top bar */}
        <header className="h-14 shrink-0 flex items-center justify-between px-6 border-b border-white/5 bg-[#0d0d0d]">
          <div className="flex items-center gap-3">
            <h1 className="text-[13px] font-semibold text-white">{NAV.find(n => n.id === section)?.label}</h1>
            <span className="text-[10px] text-gray-500 font-mono">Real-time performance metrics</span>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={fetchAll} className="w-8 h-8 rounded-lg border border-white/10 flex items-center justify-center hover:bg-white/5 transition-all" title="Refresh">
              <RefreshCw className={`w-3.5 h-3.5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <div className="relative">
              <Bell className="w-4 h-4 text-gray-400" />
              {alerts.length > 0 && <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full text-[7px] flex items-center justify-center font-bold">{alerts.length}</span>}
            </div>
            <div className="flex items-center gap-2">
              <Initials email={user?.email} />
              <div>
                <div className="text-[11px] font-medium text-white leading-none">System Admin</div>
                <div className="text-[9px] text-[#00ff88] font-mono">Superuser</div>
              </div>
            </div>
          </div>
        </header>

        {/* Scrollable content + alerts sidebar */}
        <div className="flex-1 overflow-hidden flex">
          <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-5">

            {/* ══ OVERVIEW ══ */}
            {section === 'overview' && (<>
              <div className="grid grid-cols-4 gap-4">
                <StatCard label="Users"          val={users.length}                       sub={`+${users.filter(u => (new Date() - new Date(u.created_at)) < 7*864e5).length} esta semana`} color="#00aaff" icon={<Users className="w-4 h-4" />} loading={loading} />
                <StatCard label="Total Hostings" val={hostings.length}                    sub={`${hostings.filter(h => h.status === 'active').length} activos`}   color="#00ff88" icon={<Globe className="w-4 h-4" />} loading={loading} />
                <StatCard label="Active Pixels"  val={pixelOverview?.total_sites ?? '—'} sub={`${pixelOverview?.today_events ?? 0} eventos hoy`}                 color="#ffaa00" icon={<Zap className="w-4 h-4" />} loading={loading} />
                <StatCard label="Pixel Events"   val={pixelOverview?.total_events ?? '—'}sub="total acumulado"                                                   color="#aa00ff" icon={<BarChart3 className="w-4 h-4" />} loading={loading} />
              </div>
              <div className="flex gap-1 border-b border-white/5">
                {[{ id:'users', label:`Users (${users.length})` }, { id:'hostings', label:`Hostings (${hostings.length})` }, { id:'pixel', label:`Pixel (${pixelEvents.length})` }].map(t => (
                  <button key={t.id} onClick={() => setTab(t.id)} className={`px-4 py-2 text-[11px] font-medium border-b-2 -mb-px transition-all ${tab===t.id ? 'border-[#00ff88] text-[#00ff88]' : 'border-transparent text-gray-500 hover:text-white'}`}>{t.label}</button>
                ))}
              </div>
              {tab === 'users'    && <UsersTable    users={users}       loading={loading} navigate={navigate} />}
              {tab === 'hostings' && <HostingsTable hostings={hostings} loading={loading} metricsMap={metricsMap} />}
              {tab === 'pixel'    && <PixelLog      events={filteredPixel.slice(0,50)} loading={loading} filter={pixelFilter} setFilter={setPixelFilter} />}
            </>)}

            {/* ══ USER MANAGEMENT ══ */}
            {section === 'users' && <UsersTable users={users} loading={loading} navigate={navigate} />}

            {/* ══ HOSTING ══ */}
            {section === 'hostings' && <HostingsTable hostings={hostings} loading={loading} metricsMap={metricsMap} />}

            {/* ══ PIXEL ANALYTICS ══ */}
            {section === 'pixel' && (
              pixelAnalytics ? (<>
                {/* Overview stats */}
                <div className="grid grid-cols-6 gap-3">
                  {[
                    { label: 'Sesiones',     val: pixelAnalytics.sessions,    icon: <Users className="w-3.5 h-3.5" />,        color: '#00aaff' },
                    { label: 'Page Views',   val: pixelAnalytics.views,       icon: <Eye className="w-3.5 h-3.5" />,          color: '#00ff88' },
                    { label: 'Clicks',       val: pixelAnalytics.clicks,      icon: <MousePointer className="w-3.5 h-3.5" />, color: '#ffaa00' },
                    { label: 'Exits',        val: pixelAnalytics.exits,       icon: <ArrowRight className="w-3.5 h-3.5" />,   color: '#aa00ff' },
                    { label: 'Bounce Rate',  val: `${pixelAnalytics.bounceRate}%`, icon: <TrendingUp className="w-3.5 h-3.5" />, color: '#ff6b6b' },
                    { label: 'Avg Time',     val: fmtTime(pixelAnalytics.avgTime), icon: <Timer className="w-3.5 h-3.5" />,   color: '#4ecdc4' },
                  ].map((s, i) => (
                    <div key={i} className="bg-[#111] rounded-xl border border-white/5 p-3">
                      <div className="flex justify-between mb-2"><span className="text-[9px] text-gray-500 uppercase tracking-wider">{s.label}</span><span style={{color:s.color}} className="opacity-60">{s.icon}</span></div>
                      <div className="text-xl font-bold font-mono" style={{color:s.color}}>{s.val}</div>
                    </div>
                  ))}
                </div>

                {/* Row 1: Top pages + Traffic sources */}
                <div className="grid grid-cols-2 gap-4">
                  <Section title="📄 Top Páginas Visitadas">
                    <HBar data={pixelAnalytics.topUrls} color="#00ff88" labelWidth="w-36" />
                  </Section>
                  <Section title="🔗 Fuentes de Tráfico (Referrers)">
                    <HBar data={pixelAnalytics.topRefs} color="#00aaff" labelWidth="w-28" />
                  </Section>
                </div>

                {/* Row 2: Devices + Browsers + OS */}
                <div className="grid grid-cols-3 gap-4">
                  <Section title="📱 Dispositivos">
                    <DonutChart segments={pixelAnalytics.deviceData} />
                  </Section>
                  <Section title="🌐 Navegadores">
                    <HBar data={pixelAnalytics.browserData} color="#ffaa00" labelWidth="w-16" />
                  </Section>
                  <Section title="💻 Sistema Operativo">
                    <HBar data={pixelAnalytics.osData} color="#aa00ff" labelWidth="w-16" />
                  </Section>
                </div>

                {/* Row 3: Event types + Clicks + Time on page */}
                <div className="grid grid-cols-3 gap-4">
                  <Section title="📊 Tipos de Evento">
                    <DonutChart segments={pixelAnalytics.eventTypeDist} />
                  </Section>
                  <Section title="👆 Clicks más frecuentes">
                    <HBar data={pixelAnalytics.topClicks} color="#ff6b6b" labelWidth="w-28" />
                  </Section>
                  <Section title="⏱ Tiempo promedio por página">
                    {pixelAnalytics.avgTimeByUrl.length ? (
                      <div className="flex flex-col gap-2">
                        {pixelAnalytics.avgTimeByUrl.map((d, i) => (
                          <div key={i} className="flex justify-between text-[10px]">
                            <span className="text-gray-400 truncate w-36" title={d.label}>{d.label}</span>
                            <span className="text-[#4ecdc4] font-mono">{fmtTime(d.value)}</span>
                          </div>
                        ))}
                      </div>
                    ) : <p className="text-[10px] text-gray-600 italic">Sin datos de tiempo (requiere eventos page_exit).</p>}
                  </Section>
                </div>

                {/* Row 4: Exit pages + Log */}
                <div className="grid grid-cols-2 gap-4">
                  <Section title="🚪 Páginas de Salida">
                    <HBar data={pixelAnalytics.topExitPages} color="#ff9f43" labelWidth="w-36" />
                  </Section>
                  <Section title="📋 Log de Eventos Recientes">
                    <div className="flex gap-2 mb-3 flex-wrap">
                      {['all','page_view','click','page_exit'].map(f => (
                        <button key={f} onClick={() => setPixelFilter(f)} className={`px-2 py-1 rounded text-[9px] font-mono transition-all ${pixelFilter===f ? 'bg-[#00ff88]/20 text-[#00ff88]' : 'bg-white/5 text-gray-500 hover:text-white'}`}>{f}</button>
                      ))}
                    </div>
                    <PixelLog events={filteredPixel.slice(0,30)} loading={loading} compact />
                  </Section>
                </div>
              </>) : (
                <div className="bg-[#111] rounded-xl border border-white/5 p-12 text-center text-gray-500">
                  <BarChart3 className="w-8 h-8 mx-auto mb-3 opacity-30" />
                  <p className="text-sm">Sin datos de pixel. Asegúrate de que el script de tracking está instalado en los sitios de clientes.</p>
                </div>
              )
            )}

            {/* ══ ORCHESTRATOR ══ */}
            {section === 'orchestrator' && (
              <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
                <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-white">Eventos del Orquestador AI</span>
                  <span className="text-[10px] text-gray-500 font-mono">{orcEvents.length} eventos</span>
                </div>
                {loading ? (
                  <div className="p-10 flex justify-center"><RefreshCw className="w-4 h-4 animate-spin text-gray-500" /></div>
                ) : orcEvents.length === 0 ? (
                  <div className="p-10 text-center text-gray-600 text-xs italic">Sin eventos registrados aún.</div>
                ) : (
                  <div className="divide-y divide-white/5 max-h-[70vh] overflow-y-auto">
                    {orcEvents.map((e, i) => {
                      const type = e.event_type?.toLowerCase() || 'info';
                      const style = ORC_COLOR[Object.keys(ORC_COLOR).find(k => type.includes(k)) || 'info'];
                      return (
                        <div key={i} className="px-4 py-3 flex items-start gap-4 hover:bg-white/3 transition-colors">
                          <div className="shrink-0 mt-0.5">
                            <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${style}`}>{e.event_type}</span>
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <span className="text-[11px] font-mono text-white truncate">{e.container_name}</span>
                              {e.email && <span className="text-[9px] text-gray-500">({e.email})</span>}
                            </div>
                            <p className="text-[10px] text-gray-400 leading-relaxed">{e.message}</p>
                          </div>
                          <div className="text-[9px] text-gray-600 font-mono shrink-0">{fmtDate(e.created_at)}</div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* ══ FINANCE ══ */}
            {section === 'finance' && finance && (<>
              <div className="grid grid-cols-3 gap-4">
                <StatCard label="Saldo Total en Sistema" val={`$${finance.total_balance.toFixed(2)}`}  sub="suma de todos los usuarios"           color="#00ff88" icon={<DollarSign className="w-4 h-4" />} loading={loading} />
                <StatCard label="Usuarios con Saldo"     val={finance.users_with_balance}              sub="tienen balance > $0"                   color="#00aaff" icon={<Users className="w-4 h-4" />} loading={loading} />
                <StatCard label="Con Método de Pago"     val={finance.users_with_payment}              sub="tarjeta registrada"                    color="#ffaa00" icon={<Zap className="w-4 h-4" />} loading={loading} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <Section title="Distribución de Planes">
                  <HBar data={finance.plan_distribution.map(p => ({ label: p.plan, value: p.count }))} color="#aa00ff" />
                </Section>
                <Section title="Top Saldos por Usuario">
                  <div className="flex flex-col gap-2">
                    {finance.top_balances.map((u, i) => (
                      <div key={i} className="flex items-center gap-3 py-2 border-b border-white/5 last:border-0">
                        <span className="text-[10px] text-gray-500 w-5 font-mono">{i+1}</span>
                        <Initials email={u.email} size={6} />
                        <span className="flex-1 text-[11px] text-white truncate">{u.email}</span>
                        <span className={`px-2 py-0.5 rounded text-[9px] uppercase ${PLAN_STYLE[u.plan] || 'bg-white/5 text-gray-400'}`}>{u.plan}</span>
                        <span className="text-[11px] font-mono text-emerald-400">${u.balance.toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                </Section>
              </div>
            </>)}

            {/* ══ AUDIT LOG ══ */}
            {section === 'audit' && (
              <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
                <div className="px-4 py-3 border-b border-white/5 text-[11px] font-semibold text-white">Audit Log — Usuarios y Acciones</div>
                <div className="divide-y divide-white/5 max-h-[70vh] overflow-y-auto">
                  {users.map(u => (
                    <div key={u.user_id} className="px-4 py-3 flex items-center gap-4 hover:bg-white/3 cursor-pointer transition-colors" onClick={() => navigate(`/admin/users/${u.user_id}`)}>
                      <Initials email={u.email} />
                      <div className="flex-1 min-w-0">
                        <div className="text-[11px] text-white font-medium">{u.email}</div>
                        <div className="text-[9px] text-gray-500 font-mono">Creado: {fmtDate(u.created_at)}</div>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${u.role === 'admin' ? 'bg-red-500/20 text-red-400' : 'bg-white/5 text-gray-400'}`}>{u.role}</span>
                      <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${PLAN_STYLE[u.plan] || 'bg-white/5 text-gray-400'}`}>{u.plan || 'free'}</span>
                      <ArrowRight className="w-3.5 h-3.5 text-gray-600" />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ══ SETTINGS ══ */}
            {section === 'settings' && (
              <div className="flex flex-col gap-4">
                <Section title="Feature Flags del Sistema">
                  <div className="flex flex-col gap-3">
                    {[
                      { name: 'ENABLE_AI_ADVISORY',      desc: 'Enriquece decisiones con LLM. Si está off, solo usa reglas base.' },
                      { name: 'ENABLE_ACTION_EXECUTION', desc: 'Permite ejecutar acciones técnicas aprobadas por humano.' },
                      { name: 'APP_ENV',                 desc: 'Controla cookies Secure, SameSite y nivel de logging.' },
                    ].map((f, i) => (
                      <div key={i} className="p-3 rounded-lg bg-white/3 border border-white/5">
                        <div className="flex items-center justify-between mb-1">
                          <code className="text-[11px] text-[#00ff88] font-mono">{f.name}</code>
                          <span className="text-[9px] bg-white/5 text-gray-400 px-2 py-0.5 rounded">env var</span>
                        </div>
                        <p className="text-[10px] text-gray-500">{f.desc}</p>
                      </div>
                    ))}
                  </div>
                </Section>
                <Section title="Información del Sistema">
                  {[
                    { label: 'API Version',       val: 'v1.16.0' },
                    { label: 'Backend',           val: 'FastAPI + PostgreSQL' },
                    { label: 'Auth',              val: 'JWT Cookie HttpOnly + Redis revocation' },
                    { label: 'Proxy',             val: 'Traefik v3 + docker-socket-proxy' },
                    { label: 'Schedulers activos',val: 'expiration (12h), traffic (5m), health (5m)' },
                  ].map((s, i) => (
                    <div key={i} className="flex justify-between py-2 border-b border-white/5 last:border-0 text-[11px]">
                      <span className="text-gray-500">{s.label}</span>
                      <span className="text-white font-mono">{s.val}</span>
                    </div>
                  ))}
                </Section>
              </div>
            )}

          </div>

          {/* ── Right alerts sidebar ── */}
          <div className="w-60 shrink-0 border-l border-white/5 flex flex-col gap-4 p-4 overflow-y-auto bg-[#0d0d0d]">
            <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
                <span className="text-[11px] font-semibold text-white">Recent Alerts</span>
                {alerts.length > 0 && <span className="text-[9px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded-full">{alerts.length}</span>}
              </div>
              <div className="p-3 flex flex-col gap-2 max-h-64 overflow-y-auto">
                {alerts.length === 0 ? (
                  <div className="py-5 text-center text-[10px] text-gray-600">
                    <CheckCircle2 className="w-5 h-5 mx-auto mb-2 text-emerald-700" />
                    Sistema saludable
                  </div>
                ) : alerts.map((a, i) => (
                  <div key={i} className={`p-3 rounded-lg border text-[10px] ${ALERT_STYLE[a.level]}`}>
                    <div className="flex items-center gap-1.5 mb-1">
                      <div className={`w-1.5 h-1.5 rounded-full ${ALERT_DOT[a.level]}`} />
                      <span className="font-medium text-white">{a.title}</span>
                    </div>
                    <p className="text-gray-400 leading-relaxed">{a.body}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-[#111] rounded-xl border border-white/5 p-4">
              <div className="text-[11px] font-semibold text-white mb-3">System Stats</div>
              {[
                { label: 'Containers activos', val: hostings.filter(h => h.status === 'active').length },
                { label: 'Plan free',          val: hostings.filter(h => h.plan === 'free').length },
                { label: 'Errores',            val: hostings.filter(h => h.status === 'error').length },
                { label: 'Total eventos orc.', val: orcEvents.length },
                { label: 'Usuarios admin',     val: users.filter(u => u.role === 'admin').length },
              ].map((s, i) => (
                <div key={i} className="flex justify-between items-center py-2 border-b border-white/5 last:border-0">
                  <span className="text-[10px] text-gray-500">{s.label}</span>
                  <span className="text-[11px] font-mono font-semibold text-white">{loading ? '—' : s.val}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ─────────────────────────────────────────── */
function UsersTable({ users, loading, navigate }) {
  return (
    <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-white/5">
            {['ID','Email','Role','Plan','Balance','Created Date'].map(h => (
              <th key={h} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-500 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? <tr><td colSpan={6} className="p-10 text-center"><RefreshCw className="w-4 h-4 animate-spin mx-auto text-gray-600" /></td></tr>
          : users.length === 0 ? <tr><td colSpan={6} className="p-10 text-center text-gray-600 italic text-xs">Sin usuarios.</td></tr>
          : users.map(u => (
            <tr key={u.user_id} onClick={() => navigate(`/admin/users/${u.user_id}`)} className="border-b border-white/5 hover:bg-white/3 cursor-pointer transition-colors">
              <td className="px-4 py-3 font-mono text-gray-500">#{String(u.user_id).padStart(4,'0')}</td>
              <td className="px-4 py-3"><div className="flex items-center gap-2"><Initials email={u.email} /><span className="text-white font-medium">{u.email}</span></div></td>
              <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${u.role==='admin' ? 'bg-red-500/20 text-red-400' : 'bg-white/5 text-gray-400'}`}>{u.role}</span></td>
              <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${PLAN_STYLE[u.plan] || 'bg-white/5 text-gray-400'}`}>{u.plan||'free'}</span></td>
              <td className="px-4 py-3 font-mono text-emerald-400">${(u.balance||0).toFixed(2)}</td>
              <td className="px-4 py-3 text-gray-500">{u.created_at ? new Date(u.created_at).toLocaleDateString('es-AR',{day:'2-digit',month:'short',year:'numeric'}) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {users.length > 0 && <div className="px-4 py-3 border-t border-white/5 text-[10px] text-gray-500">Showing 1 to {users.length} of {users.length} entries</div>}
    </div>
  );
}

function HostingsTable({ hostings, loading, metricsMap }) {
  return (
    <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-white/5">
            {['Nombre','Estado','Plan','CPU','RAM','Uptime 24h','Tráfico 24h','Subdominio'].map(h => (
              <th key={h} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-500 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? <tr><td colSpan={8} className="p-10 text-center"><RefreshCw className="w-4 h-4 animate-spin mx-auto text-gray-600" /></td></tr>
          : hostings.length === 0 ? <tr><td colSpan={8} className="p-10 text-center text-gray-600 italic text-xs">Sin hostings.</td></tr>
          : hostings.map(h => {
            const m = metricsMap[h.container_name] || {};
            return (
              <tr key={h.hosting_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="px-4 py-3 text-white font-medium">{h.name}</td>
                <td className="px-4 py-3"><div className={`flex items-center gap-1.5 font-medium ${STATUS_COLOR[h.status]||'text-gray-400'}`}>{STATUS_ICON[h.status]||null}{h.status}</div></td>
                <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${PLAN_STYLE[h.plan]||'bg-white/5 text-gray-400'}`}>{h.plan}</span></td>
                <td className="px-4 py-3 font-mono text-emerald-400">{m.docker?.cpu ?? '—'}</td>
                <td className="px-4 py-3 font-mono text-blue-400">{m.docker?.mem_pct ?? '—'}</td>
                <td className="px-4 py-3 font-mono text-amber-400">{m.uptime_pct != null ? `${m.uptime_pct.toFixed(1)}%` : '—'}</td>
                <td className="px-4 py-3 font-mono text-gray-400">{m.traffic_24h?.total_requests != null ? `${m.traffic_24h.total_requests} req` : '—'}</td>
                <td className="px-4 py-3 text-gray-500 font-mono text-[10px]">{h.subdomain}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PixelLog({ events, loading, filter, setFilter, compact }) {
  return (
    <div className={compact ? '' : 'bg-[#111] rounded-xl border border-white/5 overflow-hidden'}>
      {!compact && filter !== undefined && (
        <div className="px-4 py-3 border-b border-white/5 flex gap-2">
          {['all','page_view','click','page_exit'].map(f => (
            <button key={f} onClick={() => setFilter(f)} className={`px-2 py-1 rounded text-[9px] font-mono transition-all ${filter===f ? 'bg-[#00ff88]/20 text-[#00ff88]' : 'bg-white/5 text-gray-500 hover:text-white'}`}>{f}</button>
          ))}
        </div>
      )}
      <div className={compact ? 'max-h-48 overflow-y-auto' : 'max-h-64 overflow-y-auto'}>
        <table className="w-full text-[10px]">
          <thead className="sticky top-0 bg-[#111]">
            <tr className="border-b border-white/5">
              {['Tipo','URL','Dispositivo','Browser','Fecha'].map(h => (
                <th key={h} className="text-left px-3 py-2 text-[8px] uppercase tracking-wider text-gray-600">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={5} className="p-6 text-center"><RefreshCw className="w-3.5 h-3.5 animate-spin mx-auto text-gray-600" /></td></tr>
            : events.length === 0 ? <tr><td colSpan={5} className="p-6 text-center text-gray-600 italic">Sin eventos.</td></tr>
            : events.map((e, i) => (
              <tr key={i} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="px-3 py-2"><span className={`px-1.5 py-0.5 rounded text-[8px] font-mono ${e.event_type==='page_view'?'bg-emerald-500/10 text-emerald-400':e.event_type==='click'?'bg-amber-500/10 text-amber-400':'bg-purple-500/10 text-purple-400'}`}>{e.event_type}</span></td>
                <td className="px-3 py-2 text-gray-400 truncate max-w-[140px]" title={e.url}>{e.url?.replace(/^https?:\/\/[^/]+/,'') || '/'}</td>
                <td className="px-3 py-2 text-gray-500">{e.device || '—'}</td>
                <td className="px-3 py-2 text-gray-500">{e.browser || '—'}</td>
                <td className="px-3 py-2 text-gray-600 font-mono">{fmtDate(e.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
