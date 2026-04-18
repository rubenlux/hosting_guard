import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users, Globe, BarChart3, RefreshCw, ShieldCheck, Activity,
  LogOut, Zap, Bell, Settings, CheckCircle2,
  XCircle, Clock, DollarSign, FileText, Bot,
  TrendingUp, MousePointer, Eye, Timer, ArrowRight,
  HeadsetIcon, ShieldAlert, Ban, UserCog, PlusCircle,
  ToggleLeft, ToggleRight, ChevronDown, Pencil, Trash2,
  Terminal, RotateCcw, Play, Square, KeyRound,
  Crown, Infinity, CalendarClock, ShieldOff, TrendingUp as Upgrade, X,
  Database, Cpu, MemoryStick, HardDrive, Trash, Gauge, Wifi, WifiOff,
} from 'lucide-react';
import {
  getAdminUsers, getAdminHostings, getAdminPixelOverview,
  getAdminPixelEvents, getAdminHostingsMetrics,
  getAdminOrchestratorEvents, getAdminFinanceSummary,
  getSystemHealth, getAdminOpsSummary, getCapacityMetrics, getNodeMetrics,
  startSupportSession, getSupportSessions, revokeSupportSession,
  listStaff, createStaff, updateStaff, deactivateStaff, resetStaffPassword,
  adminRestartHosting, adminStopHosting, adminStartHosting,
  adminGetHostingLogs, adminTerminateHosting,
  adminExtendPlan, adminSetFreePlanForever, adminDeactivateFreePlan, adminUpgradePlan,
} from '../services/api';
import { useAuth } from '../hooks/useAuth';
import StaffAnalytics from '../components/StaffAnalytics';
import StatusCommandBar from '../components/dashboard/StatusCommandBar';
import SystemStatusBanner from '../components/dashboard/SystemStatusBanner';

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
  { id: 'equipo',        label: 'Equipo',           icon: UserCog },
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
  const [systemHealth, setSystemHealth]     = useState(null);
  const [opsSummary, setOpsSummary]         = useState(null);
  const [capacityMetrics, setCapacityMetrics] = useState(null);
  const [nodeMetrics, setNodeMetrics]         = useState(null);
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
      getSystemHealth(),
      getAdminOpsSummary(),
      getCapacityMetrics(),
      getNodeMetrics(),
    ]);
    if (results[0].status === 'fulfilled') setUsers(results[0].value);
    if (results[1].status === 'fulfilled') setHostings(results[1].value);
    if (results[2].status === 'fulfilled') setHostingMetrics(results[2].value);
    if (results[3].status === 'fulfilled') setPixelOverview(results[3].value);
    if (results[4].status === 'fulfilled') setPixelEvents(results[4].value);
    if (results[5].status === 'fulfilled') setOrcEvents(results[5].value);
    if (results[6].status === 'fulfilled') setFinance(results[6].value);
    if (results[7].status === 'fulfilled') setSystemHealth(results[7].value);
    if (results[8].status === 'fulfilled') setOpsSummary(results[8].value);
    if (results[9].status === 'fulfilled') setCapacityMetrics(results[9].value);
    if (results[10].status === 'fulfilled') setNodeMetrics(results[10].value);
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

  /* ── metrics map (keyed by container_name for HostingsTable) ── */
  const metricsMap = useMemo(() => {
    const m = {};
    hostingMetrics.forEach(h => { m[h.container_name] = h; });
    return m;
  }, [hostingMetrics]);

  /* ── health data keyed by hosting_id (for StatusCommandBar) ── */
  const healthDataById = useMemo(() => {
    const m = {};
    hostingMetrics.forEach(h => {
      if (h.hosting_id != null) m[h.hosting_id] = h;
    });
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

        {/* Status command bar */}
        <StatusCommandBar
          hostings={hostings}
          healthData={healthDataById}
          advisories={[]}
          alerts={alerts}
        />

        {/* Capacity status banner — prefers real Prometheus data, falls back to capacity_forecast */}
        {(() => {
          const bannerData = (nodeMetrics?.available && nodeMetrics.status)
            ? {
                status:             nodeMetrics.status,
                cpu_pct:            nodeMetrics.cpu_pct,
                ram_pct:            nodeMetrics.ram_pct,
                disk_pct:           nodeMetrics.disk_pct,
                days_to_exhaustion: nodeMetrics.disk_days_left,
                recommendation:     nodeMetrics.recommendation,
              }
            : capacityMetrics;
          return bannerData && bannerData.status !== 'ok' && bannerData.status !== 'healthy'
            ? <SystemStatusBanner capacity={bannerData} />
            : null;
        })()}

        {/* Scrollable content + alerts sidebar */}
        <div className="flex-1 overflow-hidden flex">
          <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-5">

            {/* ══ OVERVIEW ══ */}
            {section === 'overview' && (<>

              {/* Row 1: Core KPIs */}
              <div className="grid grid-cols-4 gap-4">
                <StatCard
                  label="Users"
                  val={users.length}
                  sub={`${opsSummary?.business?.paid_users ?? users.filter(u => u.plan !== 'free').length} pagos · ${opsSummary?.business?.free_users ?? users.filter(u => u.plan === 'free').length} free`}
                  color="#00aaff"
                  icon={<Users className="w-4 h-4" />}
                  loading={loading}
                />
                <StatCard
                  label="Hostings"
                  val={hostings.filter(h => h.status !== 'deleted').length}
                  sub={`${hostings.filter(h => h.status === 'active').length} activos · ${hostings.filter(h => ['error','zombie'].includes(h.status)).length} con error`}
                  color="#00ff88"
                  icon={<Globe className="w-4 h-4" />}
                  loading={loading}
                />
                <StatCard
                  label="Docker Load"
                  val={systemHealth ? `${systemHealth.docker_ops?.utilization_pct ?? 0}%` : '—'}
                  sub={`${systemHealth?.docker_ops?.inflight ?? 0}/${systemHealth?.docker_ops?.max ?? 20} ops en vuelo`}
                  color={
                    !systemHealth ? '#6b7280'
                    : (systemHealth.docker_ops?.utilization_pct ?? 0) >= 70 ? '#ef4444'
                    : (systemHealth.docker_ops?.utilization_pct ?? 0) >= 40 ? '#ffaa00'
                    : '#00ff88'
                  }
                  icon={<Activity className="w-4 h-4" />}
                  loading={loading}
                />
                <StatCard
                  label="Error Rate"
                  val={`${hostings.length ? Math.round((hostings.filter(h => h.status === 'error').length / hostings.length) * 100) : 0}%`}
                  sub={`${hostings.filter(h => h.status === 'error').length} en error · ${hostings.filter(h => h.status === 'zombie').length} zombie`}
                  color={hostings.filter(h => h.status === 'error').length > 0 ? '#ef4444' : '#00ff88'}
                  icon={<ShieldAlert className="w-4 h-4" />}
                  loading={loading}
                />
              </div>

              {/* Row 2: System capacity + Docker ops + DB/Redis */}
              <div className="grid grid-cols-3 gap-4">
                {/* Capacity forecast */}
                <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wider font-medium">Capacidad del Nodo</div>
                    {nodeMetrics?.available && (nodeMetrics.cpu_pct != null || nodeMetrics.ram_pct != null) && (
                      <span className="text-[9px] font-mono text-emerald-500/60 uppercase tracking-widest">Prometheus</span>
                    )}
                  </div>
                  {(() => {
                    // Per-value fallback: use Prometheus value when non-null, else capacity_forecast
                    const prom = nodeMetrics?.available ? nodeMetrics : null;
                    const fc   = systemHealth?.capacity_forecast;
                    const rows = [
                      {
                        label: 'CPU',
                        icon: <Cpu className="w-3 h-3" />,
                        pct: prom?.cpu_pct ?? fc?.cpu?.usage,
                      },
                      {
                        label: 'RAM',
                        icon: <MemoryStick className="w-3 h-3" />,
                        pct: prom?.ram_pct ?? fc?.ram?.usage,
                      },
                      {
                        label: 'Disco',
                        icon: <HardDrive className="w-3 h-3" />,
                        pct: prom?.disk_pct ?? fc?.disk?.usage,
                      },
                      {
                        label: 'Cont.',
                        icon: <Gauge className="w-3 h-3" />,
                        pct: fc?.containers?.usage,
                      },
                    ];
                    const hasData = rows.some(r => r.pct != null);
                    if (!hasData) return <div className="text-[10px] text-gray-600 italic">Métricas no disponibles</div>;
                    return (
                      <div className="flex flex-col gap-2.5">
                        {rows.map(({ label, icon, pct }) => {
                          const color = pct == null ? '#4b5563' : pct >= 90 ? '#ef4444' : pct >= 70 ? '#f59e0b' : '#22c55e';
                          return (
                            <div key={label} className="flex items-center gap-2">
                              <span style={{ color }} className="opacity-70">{icon}</span>
                              <span className="text-[10px] text-gray-400 w-8 shrink-0">{label}</span>
                              <div className="flex-1 h-1.5 bg-white/5 rounded overflow-hidden">
                                <div className="h-full rounded transition-all" style={{
                                  width: pct != null ? `${Math.min(pct, 100)}%` : '0%',
                                  background: color,
                                }} />
                              </div>
                              <span className="text-[10px] font-mono w-12 text-right" style={{ color }}>
                                {pct != null ? `${Math.round(pct)}%` : 'N/A'}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })()}
                </div>

                {/* Docker ops detail */}
                <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider font-medium mb-3">Docker Operations</div>
                  {systemHealth?.docker_ops?.latency_by_operation && Object.keys(systemHealth.docker_ops.latency_by_operation).length > 0 ? (
                    <div className="flex flex-col gap-2">
                      {Object.entries(systemHealth.docker_ops.latency_by_operation).map(([op, data]) => (
                        <div key={op} className="flex items-center gap-2 text-[10px]">
                          <span className="text-gray-500 w-20 truncate font-mono">{op}</span>
                          <span className="text-gray-300 font-mono ml-auto">{data.mean_seconds != null ? `${data.mean_seconds}s` : '—'}</span>
                          <span className="text-gray-600 font-mono w-12 text-right">{data.total_ops} ops</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-col gap-2">
                      <div className="flex justify-between text-[10px]">
                        <span className="text-gray-500">En vuelo</span>
                        <span className="font-mono text-white">{systemHealth?.docker_ops?.inflight ?? 0} / {systemHealth?.docker_ops?.max ?? 20}</span>
                      </div>
                      <div className="flex justify-between text-[10px]">
                        <span className="text-gray-500">Utilización</span>
                        <span className="font-mono" style={{ color: (systemHealth?.docker_ops?.utilization_pct ?? 0) >= 70 ? '#ef4444' : '#00ff88' }}>
                          {systemHealth?.docker_ops?.utilization_pct ?? 0}%
                        </span>
                      </div>
                      <div className="text-[10px] text-gray-600 italic mt-1">Sin ops registradas aún</div>
                    </div>
                  )}
                </div>

                {/* DB pool + Redis */}
                <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider font-medium mb-3">Infra Interna</div>
                  <div className="flex flex-col gap-3">
                    <div>
                      <div className="flex justify-between text-[10px] mb-1">
                        <span className="text-gray-500 flex items-center gap-1"><Database className="w-3 h-3" /> DB Pool</span>
                        <span className="font-mono text-gray-300">
                          {systemHealth?.db_pool?.maxconn
                            ? systemHealth.db_pool.active_connections != null
                              ? `${systemHealth.db_pool.active_connections}/${systemHealth.db_pool.maxconn} activas`
                              : `max ${systemHealth.db_pool.maxconn}`
                            : 'N/A'}
                        </span>
                      </div>
                      {systemHealth?.db_pool?.maxconn && (
                        <div className="h-1.5 bg-white/5 rounded overflow-hidden">
                          <div className="h-full rounded transition-all" style={{
                            width: systemHealth.db_pool.active_connections != null
                              ? `${Math.min((systemHealth.db_pool.active_connections / systemHealth.db_pool.maxconn) * 100, 100)}%`
                              : '5%',
                            background: systemHealth.db_pool.active_connections / systemHealth.db_pool.maxconn > 0.8 ? '#ef4444'
                              : systemHealth.db_pool.active_connections / systemHealth.db_pool.maxconn > 0.6 ? '#ffaa00'
                              : '#00aaff',
                          }} />
                        </div>
                      )}
                    </div>
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-gray-500 flex items-center gap-1">
                        {systemHealth?.redis?.connected ? <Wifi className="w-3 h-3 text-emerald-400" /> : <WifiOff className="w-3 h-3 text-red-400" />}
                        Redis
                      </span>
                      <span className={`font-mono ${systemHealth?.redis?.connected ? 'text-emerald-400' : 'text-red-400'}`}>
                        {systemHealth?.redis?.connected ? 'Conectado' : 'Desconectado'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="text-gray-500">Containers totales</span>
                      <span className="font-mono text-gray-300">{systemHealth?.containers?.total ?? '—'}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Row 3: Free Tier + Business */}
              <div className="grid grid-cols-2 gap-4">
                {/* Free tier / cleanup */}
                <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider font-medium mb-3">Free Tier & Cleanup</div>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      {
                        label: 'Cupo usado',
                        val: opsSummary ? `${opsSummary.free_tier.active_users}/${opsSummary.free_tier.cap}` : '—',
                        sub: `${opsSummary?.free_tier?.cap_pct ?? 0}% ocupado`,
                        color: (opsSummary?.free_tier?.cap_pct ?? 0) >= 80 ? '#ef4444' : (opsSummary?.free_tier?.cap_pct ?? 0) >= 60 ? '#ffaa00' : '#00ff88',
                      },
                      {
                        label: 'Eliminados hoy',
                        val: opsSummary?.free_tier?.deleted_today ?? '—',
                        sub: 'últimas 24h',
                        color: '#00ff88',
                      },
                      {
                        label: 'Zombies',
                        val: opsSummary?.free_tier?.zombies ?? '—',
                        sub: `${opsSummary?.free_tier?.expired_ready ?? 0} exp. pendientes`,
                        color: (opsSummary?.free_tier?.zombies ?? 0) > 0 ? '#ffaa00' : '#00ff88',
                      },
                    ].map((s, i) => (
                      <div key={i} className="flex flex-col gap-1">
                        <span className="text-[9px] text-gray-600 uppercase tracking-wider">{s.label}</span>
                        <span className="text-xl font-bold font-mono" style={{ color: s.color }}>{s.val}</span>
                        <span className="text-[9px] text-gray-600">{s.sub}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Business KPIs */}
                <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wider font-medium mb-3">Negocio</div>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      {
                        label: 'Conversión',
                        val: opsSummary ? `${opsSummary.business.conversion_pct}%` : '—',
                        sub: `${opsSummary?.business?.paid_users ?? 0} de ${opsSummary?.business?.total_users ?? 0} usuarios`,
                        color: (opsSummary?.business?.conversion_pct ?? 0) >= 50 ? '#00ff88' : (opsSummary?.business?.conversion_pct ?? 0) >= 20 ? '#ffaa00' : '#ef4444',
                      },
                      {
                        label: 'Saldo total',
                        val: opsSummary ? `$${opsSummary.business.total_balance}` : '—',
                        sub: 'balance acumulado',
                        color: '#00aaff',
                      },
                      {
                        label: 'Free / Pagos',
                        val: opsSummary ? `${opsSummary.business.free_users} / ${opsSummary.business.paid_users}` : '—',
                        sub: 'distribución actual',
                        color: '#aa00ff',
                      },
                    ].map((s, i) => (
                      <div key={i} className="flex flex-col gap-1">
                        <span className="text-[9px] text-gray-600 uppercase tracking-wider">{s.label}</span>
                        <span className="text-xl font-bold font-mono" style={{ color: s.color }}>{s.val}</span>
                        <span className="text-[9px] text-gray-600">{s.sub}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Tabs: Users / Hostings / Pixel */}
              <div className="flex gap-1 border-b border-white/5">
                {[{ id:'users', label:`Users (${users.length})` }, { id:'hostings', label:`Hostings (${hostings.length})` }, { id:'pixel', label:`Pixel (${pixelEvents.length})` }].map(t => (
                  <button key={t.id} onClick={() => setTab(t.id)} className={`px-4 py-2 text-[11px] font-medium border-b-2 -mb-px transition-all ${tab===t.id ? 'border-[#00ff88] text-[#00ff88]' : 'border-transparent text-gray-500 hover:text-white'}`}>{t.label}</button>
                ))}
              </div>
              {tab === 'users'    && <UsersTable    users={users}       loading={loading} navigate={navigate} onReloadUsers={fetchAll} />}
              {tab === 'hostings' && <HostingsTable hostings={hostings} loading={loading} metricsMap={metricsMap} onReload={fetchAll} />}
              {tab === 'pixel'    && <PixelLog      events={filteredPixel.slice(0,50)} loading={loading} filter={pixelFilter} setFilter={setPixelFilter} />}
            </>)}

            {/* ══ USER MANAGEMENT ══ */}
            {section === 'users' && <UsersTable users={users} loading={loading} navigate={navigate} onReloadUsers={fetchAll} />}

            {/* ══ HOSTING ══ */}
            {section === 'hostings' && <HostingsTable hostings={hostings} loading={loading} metricsMap={metricsMap} onReload={fetchAll} />}

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

            {/* ══ EQUIPO ══ */}
            {section === 'equipo' && <EquipoSection />}

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

            {/* System alerts (real — from /health/system) */}
            {(() => {
              const sysAlerts = systemHealth?.alerts ?? [];
              const overallStatus = systemHealth?.status ?? 'unknown';
              return (
                <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
                    <span className="text-[11px] font-semibold text-white">Sistema</span>
                    <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-mono ${
                      overallStatus === 'healthy' ? 'bg-emerald-500/20 text-emerald-400'
                      : overallStatus === 'warning' ? 'bg-amber-500/20 text-amber-400'
                      : overallStatus === 'critical' ? 'bg-red-500/20 text-red-400'
                      : 'bg-white/5 text-gray-500'
                    }`}>{overallStatus}</span>
                  </div>
                  <div className="p-3 flex flex-col gap-2">
                    {sysAlerts.length === 0 && !loading ? (
                      <div className="py-4 text-center text-[10px] text-gray-600">
                        <CheckCircle2 className="w-4 h-4 mx-auto mb-1.5 text-emerald-700" />
                        Todos los componentes operativos
                      </div>
                    ) : sysAlerts.map((a, i) => (
                      <div key={i} className={`p-2.5 rounded-lg text-[10px] ${
                        a.level === 'critical' ? 'bg-red-500/10 border border-red-500/20'
                        : 'bg-amber-500/10 border border-amber-500/20'
                      }`}>
                        <div className="flex items-center gap-1.5 mb-1">
                          <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${a.level === 'critical' ? 'bg-red-400' : 'bg-amber-400'}`} />
                          <span className="font-medium text-[10px] uppercase tracking-wide" style={{ color: a.level === 'critical' ? '#f87171' : '#fbbf24' }}>
                            {a.component}
                          </span>
                        </div>
                        <p className="text-gray-400 leading-relaxed text-[9px]">{a.message}</p>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}

            {/* Hosting-level alerts (from orchestrator) */}
            <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
                <span className="text-[11px] font-semibold text-white">Alertas</span>
                {alerts.length > 0 && <span className="text-[9px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded-full">{alerts.length}</span>}
              </div>
              <div className="p-3 flex flex-col gap-2 max-h-48 overflow-y-auto">
                {alerts.length === 0 ? (
                  <div className="py-4 text-center text-[10px] text-gray-600">
                    <CheckCircle2 className="w-4 h-4 mx-auto mb-1.5 text-emerald-700" />
                    Sin alertas activas
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

const FREE_FOREVER_DATE = '2099-12-31T23:59:59+00:00';

function planExpiryLabel(user) {
  if (user.plan !== 'free') return null;
  const exp = user.plan_expires_at;
  if (!exp) return null;
  if (exp.includes('2099')) return { label: 'Free forever', color: 'text-emerald-400' };
  const d = new Date(exp);
  const now = new Date();
  if (d < now) return { label: 'Vencido', color: 'text-red-400' };
  const days = Math.ceil((d - now) / 86400000);
  return { label: `+${days}d`, color: days <= 3 ? 'text-red-400' : 'text-amber-400' };
}

/* ── Plan Management Modal ──────────────────────────────────── */
function PlanManagementModal({ user, onClose, onSuccess }) {
  const [loading, setLoading] = useState(null); // action key being executed
  const [error, setError]     = useState(null);

  const run = async (key, fn) => {
    setLoading(key);
    setError(null);
    try {
      await fn();
      onSuccess();
      onClose();
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Error al ejecutar acción');
    } finally {
      setLoading(null);
    }
  };

  const isFreePlan = user.plan === 'free';
  const isForever  = user.plan_expires_at?.includes('2099');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="relative w-full max-w-md bg-[#111] border border-white/10 rounded-2xl shadow-2xl p-6"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <div className="flex items-center gap-2 mb-0.5">
              <Crown className="w-4 h-4 text-amber-400" />
              <span className="text-sm font-bold text-white">Gestión de Plan</span>
            </div>
            <div className="text-[10px] text-gray-500 truncate max-w-[280px]">{user.email}</div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>

        {/* Current plan badge */}
        <div className="flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/8 mb-5">
          <div>
            <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-0.5">Plan actual</div>
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${PLAN_STYLE[user.plan] || 'bg-white/5 text-gray-400'}`}>
                {user.plan || 'free'}
              </span>
              {(() => {
                const lbl = planExpiryLabel(user);
                return lbl ? (
                  <span className={`text-[10px] font-medium ${lbl.color}`}>{lbl.label}</span>
                ) : null;
              })()}
            </div>
          </div>
          {user.plan_expires_at && !isForever && (
            <div className="ml-auto text-right">
              <div className="text-[9px] text-gray-500">Vence</div>
              <div className="text-[10px] font-mono text-gray-300">
                {new Date(user.plan_expires_at).toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' })}
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-[11px] text-red-400">{error}</div>
        )}

        {/* Free-plan actions */}
        {isFreePlan && (
          <div className="space-y-2 mb-4">
            <div className="text-[9px] uppercase tracking-widest text-gray-600 mb-2">Período de prueba</div>

            <div className="flex gap-2">
              <button
                onClick={() => run('ext14', () => adminExtendPlan(user.user_id, 14))}
                disabled={!!loading}
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-[11px] font-bold
                  bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors disabled:opacity-50"
              >
                {loading === 'ext14' ? <RefreshCw className="w-3 h-3 animate-spin" /> : <CalendarClock className="w-3 h-3" />}
                +14 días
              </button>
              <button
                onClick={() => run('ext30', () => adminExtendPlan(user.user_id, 30))}
                disabled={!!loading}
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-[11px] font-bold
                  bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors disabled:opacity-50"
              >
                {loading === 'ext30' ? <RefreshCw className="w-3 h-3 animate-spin" /> : <CalendarClock className="w-3 h-3" />}
                +30 días
              </button>
            </div>

            <button
              onClick={() => run('forever', () => adminSetFreePlanForever(user.user_id))}
              disabled={!!loading || isForever}
              className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-[11px] font-bold
                bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors
                disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loading === 'forever' ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Infinity className="w-3.5 h-3.5" />}
              {isForever ? 'Ya es Free Forever' : 'Convertir a Free Forever'}
            </button>

            <button
              onClick={() => {
                if (!window.confirm(`¿Desactivar el plan free de ${user.email}?\nEl contenedor se suspenderá en el próximo ciclo del job.`)) return;
                run('deactivate', () => adminDeactivateFreePlan(user.user_id));
              }}
              disabled={!!loading}
              className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-[11px] font-bold
                bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-50"
            >
              {loading === 'deactivate' ? <RefreshCw className="w-3 h-3 animate-spin" /> : <ShieldOff className="w-3 h-3" />}
              Desactivar plan (spam / abuso)
            </button>
          </div>
        )}

        {/* Upgrade section */}
        <div className="space-y-2">
          <div className="text-[9px] uppercase tracking-widest text-gray-600 mb-2">Convertir a plan pago</div>
          {[
            { plan: 'personal', label: 'Personal',  desc: '0.5 CPU · 512 MB',  color: 'text-blue-400   bg-blue-500/10   hover:bg-blue-500/20' },
            { plan: 'negocio',  label: 'Negocio',   desc: '1 CPU · 1 GB',      color: 'text-amber-400  bg-amber-500/10  hover:bg-amber-500/20' },
            { plan: 'agencia',  label: 'Agencia',   desc: '2 CPU · 2 GB',      color: 'text-purple-400 bg-purple-500/10 hover:bg-purple-500/20' },
          ].map(({ plan, label, desc, color }) => (
            <button
              key={plan}
              onClick={() => {
                if (!window.confirm(`¿Convertir a ${user.email} al plan ${label}?\nSe actualizarán los recursos Docker inmediatamente.`)) return;
                run(`upgrade_${plan}`, () => adminUpgradePlan(user.user_id, plan));
              }}
              disabled={!!loading || user.plan === plan}
              className={`w-full flex items-center justify-between px-4 py-2.5 rounded-xl text-[11px] font-bold
                transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${color}`}
            >
              <span className="flex items-center gap-1.5">
                {loading === `upgrade_${plan}` ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Crown className="w-3 h-3" />}
                {label}
                {user.plan === plan && <span className="text-[9px] opacity-60 ml-1">(actual)</span>}
              </span>
              <span className="text-[9px] opacity-70 font-mono">{desc}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ─────────────────────────────────────────── */
function UsersTable({ users, loading, navigate, onReloadUsers }) {
  const { activateSupportSession } = useAuth();
  const [supporting, setSupporting]   = useState(null); // user_id being activated
  const [planModal, setPlanModal]     = useState(null);  // user object for modal

  const handleSupport = async (e, u) => {
    e.stopPropagation();
    if (!window.confirm(`¿Iniciar sesión de soporte para ${u.email}?\n\nDuración: 15 minutos. Quedará registrado en auditoría.`)) return;
    setSupporting(u.user_id);
    try {
      const data = await startSupportSession(u.user_id);
      await activateSupportSession(data.token);
      // Navigate to the client dashboard to see their view
      navigate('/dashboard');
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error iniciando sesión de soporte');
    } finally {
      setSupporting(null);
    }
  };

  return (
    <div className="space-y-4">
      {planModal && (
        <PlanManagementModal
          user={planModal}
          onClose={() => setPlanModal(null)}
          onSuccess={() => { setPlanModal(null); onReloadUsers?.(); }}
        />
      )}
      <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-white/5">
              {['ID','Email','Role','Plan','Balance','Created Date','Soporte',''].map(h => (
                <th key={h} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-500 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={8} className="p-10 text-center"><RefreshCw className="w-4 h-4 animate-spin mx-auto text-gray-600" /></td></tr>
            : users.length === 0 ? <tr><td colSpan={8} className="p-10 text-center text-gray-600 italic text-xs">Sin usuarios.</td></tr>
            : users.map(u => (
              <tr key={u.user_id} onClick={() => navigate(`/admin/users/${u.user_id}`)} className="border-b border-white/5 hover:bg-white/3 cursor-pointer transition-colors">
                <td className="px-4 py-3 font-mono text-gray-500">#{String(u.user_id).padStart(4,'0')}</td>
                <td className="px-4 py-3"><div className="flex items-center gap-2"><Initials email={u.email} /><span className="text-white font-medium">{u.email}</span></div></td>
                <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${u.role==='admin' ? 'bg-red-500/20 text-red-400' : 'bg-white/5 text-gray-400'}`}>{u.role}</span></td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${PLAN_STYLE[u.plan] || 'bg-white/5 text-gray-400'}`}>{u.plan||'free'}</span>
                    {(() => { const l = planExpiryLabel(u); return l ? <span className={`text-[9px] font-medium ${l.color}`}>{l.label}</span> : null; })()}
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-emerald-400">${(u.balance||0).toFixed(2)}</td>
                <td className="px-4 py-3 text-gray-500">{u.created_at ? new Date(u.created_at).toLocaleDateString('es-AR',{day:'2-digit',month:'short',year:'numeric'}) : '—'}</td>
                <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                  {u.role === 'admin' ? (
                    <span className="text-[9px] text-gray-600 flex items-center gap-1"><Ban className="w-3 h-3" /> N/A</span>
                  ) : (
                    <button
                      onClick={(e) => handleSupport(e, u)}
                      disabled={supporting === u.user_id}
                      className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold
                        bg-amber-500/10 text-amber-400 hover:bg-amber-500/25 transition-colors
                        disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Acceder como este cliente (modo soporte)"
                    >
                      {supporting === u.user_id
                        ? <RefreshCw className="w-3 h-3 animate-spin" />
                        : <ShieldAlert className="w-3 h-3" />}
                      Soporte
                    </button>
                  )}
                </td>
                <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                  <button
                    onClick={() => setPlanModal(u)}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold
                      bg-white/5 text-gray-300 hover:bg-white/10 transition-colors"
                    title="Gestionar plan del usuario"
                  >
                    <Crown className="w-3 h-3 text-amber-400" />
                    Plan
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length > 0 && <div className="px-4 py-3 border-t border-white/5 text-[10px] text-gray-500">Showing 1 to {users.length} of {users.length} entries</div>}
      </div>
      <SupportSessionsPanel />
    </div>
  );
}

function SupportSessionsPanel() {
  const [data, setData]         = useState(null);
  const [loading, setLoading]   = useState(false);
  const [revoking, setRevoking] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const result = await getSupportSessions();
      setData(result);
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Error al cargar sesiones';
      setLoadError(msg);
      console.error('[SupportSessionsPanel]', msg, err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load on mount and auto-refresh every 30s
  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  const handleRevoke = async (sessionId) => {
    if (!window.confirm('¿Revocar esta sesión de soporte ahora?')) return;
    setRevoking(sessionId);
    try { await revokeSupportSession(sessionId); await load(); }
    catch (err) { alert(err?.response?.data?.detail || 'Error'); }
    finally { setRevoking(null); }
  };

  const active  = data?.active  || [];
  const history = data?.history || [];

  return (
    <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5">
        <ShieldAlert className="w-4 h-4 text-amber-400" />
        <span className="text-xs font-bold text-white">Sesiones de Soporte</span>
        {active.length > 0 && (
          <span className="ml-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-amber-500/20 text-amber-400">
            {active.length} activa{active.length !== 1 ? 's' : ''}
          </span>
        )}
        <button onClick={load} className="ml-auto text-gray-600 hover:text-white transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {active.length > 0 && (
        <div className="px-4 py-3 border-b border-amber-500/20 bg-amber-500/5">
          <div className="text-[9px] uppercase tracking-wider text-amber-500 font-bold mb-2">Activas ahora</div>
          {active.map(s => (
            <div key={s.session_id} className="flex items-center gap-3 py-1.5 text-[11px]">
              <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse shrink-0" />
              <span className="text-white font-mono">{s.target_email}</span>
              <span className="text-gray-500">← {s.admin_email}</span>
              <span className="text-gray-600 font-mono text-[10px]">exp: {new Date(s.expires_at).toLocaleTimeString()}</span>
              <button
                onClick={() => handleRevoke(s.session_id)}
                disabled={revoking === s.session_id}
                className="ml-auto px-2 py-0.5 rounded text-[9px] bg-red-500/10 text-red-400 hover:bg-red-500/25 transition-colors disabled:opacity-50"
              >
                {revoking === s.session_id ? '...' : 'Revocar'}
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="max-h-48 overflow-y-auto">
        {loadError ? (
          <div className="p-4 text-[11px] text-red-400 flex items-center gap-2">
            <span>⚠ Error: {loadError}</span>
            <button onClick={load} className="underline hover:no-underline">Reintentar</button>
          </div>
        ) : history.length === 0 ? (
          <div className="p-6 text-center text-[11px] text-gray-600 italic">Sin historial de sesiones.</div>
        ) : (
          <table className="w-full text-[10px]">
            <thead className="sticky top-0 bg-[#111]">
              <tr className="border-b border-white/5">
                {['Cliente','Admin','Inicio','Expiración','Estado'].map(h => (
                  <th key={h} className="text-left px-4 py-2 text-[9px] uppercase tracking-wider text-gray-600">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map(s => {
                const now = new Date();
                const exp = new Date(s.expires_at);
                const state = s.revoked_at ? 'revocada' : exp < now ? 'expirada' : 'activa';
                const stateColor = state === 'activa' ? 'text-amber-400' : state === 'revocada' ? 'text-red-400' : 'text-gray-500';
                return (
                  <tr key={s.session_id} className="border-b border-white/5 hover:bg-white/3">
                    <td className="px-4 py-2 text-white font-mono">{s.target_email}</td>
                    <td className="px-4 py-2 text-gray-400">{s.admin_email}</td>
                    <td className="px-4 py-2 text-gray-500">{new Date(s.created_at).toLocaleString('es-AR',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</td>
                    <td className="px-4 py-2 text-gray-500">{exp.toLocaleString('es-AR',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</td>
                    <td className={`px-4 py-2 font-bold uppercase text-[9px] ${stateColor}`}>{state}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function HostingsTable({ hostings, loading, metricsMap, onReload }) {
  const [actioning, setActioning] = useState(null);   // hosting_id being acted on
  const [logsModal, setLogsModal] = useState(null);   // { hosting, logs }
  const [terminateModal, setTerminate] = useState(null); // hosting

  const act = async (hosting, fn, label) => {
    if (!window.confirm(`¿${label} el hosting "${hosting.name}" (${hosting.container_name})?`)) return;
    setActioning(hosting.hosting_id);
    try {
      await fn(hosting.hosting_id);
      onReload?.();
    } catch (err) {
      alert(err?.response?.data?.detail || `Error al ${label.toLowerCase()}`);
    } finally {
      setActioning(null);
    }
  };

  const viewLogs = async (hosting) => {
    setActioning(hosting.hosting_id);
    try {
      const data = await adminGetHostingLogs(hosting.hosting_id);
      setLogsModal({ hosting, logs: data.logs || '(sin logs)' });
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error obteniendo logs');
    } finally {
      setActioning(null);
    }
  };

  const cols = ['Nombre','Estado','Plan','CPU','RAM','Uptime 24h','Tráfico 24h','Subdominio'];

  return (
    <>
      <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-white/5">
                {cols.map(c => (
                  <th key={c} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-500 font-medium whitespace-nowrap">{c}</th>
                ))}
                <th className="sticky right-0 bg-[#111] text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-500 font-medium whitespace-nowrap border-l border-white/5">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={cols.length + 1} className="p-10 text-center"><RefreshCw className="w-4 h-4 animate-spin mx-auto text-gray-600" /></td></tr>
              ) : hostings.length === 0 ? (
                <tr><td colSpan={cols.length + 1} className="p-10 text-center text-gray-600 italic text-xs">Sin hostings.</td></tr>
              ) : hostings.map(h => {
                const m = metricsMap[h.container_name] || {};
                const busy = actioning === h.hosting_id;
                const isStopped = h.status === 'stopped' || h.status === 'expired';
                return (
                  <tr key={h.hosting_id} className="group border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-3">
                      <div className="text-white font-medium">{h.name}</div>
                      <div className="text-[9px] text-gray-600 font-mono mt-0.5">{h.container_name}</div>
                    </td>
                    <td className="px-4 py-3"><div className={`flex items-center gap-1.5 font-medium ${STATUS_COLOR[h.status]||'text-gray-400'}`}>{STATUS_ICON[h.status]||null}{h.status}</div></td>
                    <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${PLAN_STYLE[h.plan]||'bg-white/5 text-gray-400'}`}>{h.plan}</span></td>
                    <td className="px-4 py-3 font-mono text-emerald-400">{m.docker?.cpu ?? '—'}</td>
                    <td className="px-4 py-3 font-mono text-blue-400">{m.docker?.mem_pct ?? '—'}</td>
                    <td className="px-4 py-3 font-mono text-amber-400">{m.uptime_pct != null ? `${m.uptime_pct.toFixed(1)}%` : '—'}</td>
                    <td className="px-4 py-3 font-mono text-gray-400">{m.traffic_24h?.total_requests != null ? `${m.traffic_24h.total_requests} req` : '—'}</td>
                    <td className="px-4 py-3 text-gray-500 font-mono text-[10px]">{h.subdomain}</td>
                    <td className="sticky right-0 bg-[#111] group-hover:bg-[#161616] px-4 py-3 border-l border-white/5 transition-colors">
                      <div className="flex items-center gap-1.5">
                        {/* Logs */}
                        <button
                          onClick={() => viewLogs(h)}
                          disabled={busy}
                          title="Ver logs"
                          className="p-1.5 rounded hover:bg-white/10 text-gray-500 hover:text-purple-400 transition-colors disabled:opacity-40"
                        >
                          {busy ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Terminal className="w-3.5 h-3.5" />}
                        </button>
                        {/* Restart */}
                        <button
                          onClick={() => act(h, adminRestartHosting, 'Reiniciar')}
                          disabled={busy || isStopped}
                          title="Reiniciar"
                          className="p-1.5 rounded hover:bg-amber-500/10 text-gray-500 hover:text-amber-400 transition-colors disabled:opacity-40"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                        </button>
                        {/* Stop / Start */}
                        {isStopped ? (
                          <button
                            onClick={() => act(h, adminStartHosting, 'Iniciar')}
                            disabled={busy}
                            title="Iniciar"
                            className="p-1.5 rounded hover:bg-emerald-500/10 text-gray-500 hover:text-emerald-400 transition-colors disabled:opacity-40"
                          >
                            <Play className="w-3.5 h-3.5" />
                          </button>
                        ) : (
                          <button
                            onClick={() => act(h, adminStopHosting, 'Detener')}
                            disabled={busy}
                            title="Detener"
                            className="p-1.5 rounded hover:bg-orange-500/10 text-gray-500 hover:text-orange-400 transition-colors disabled:opacity-40"
                          >
                            <Square className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {/* Terminate */}
                        <button
                          onClick={() => setTerminate(h)}
                          disabled={busy}
                          title="Terminar (uso indebido / spam)"
                          className="p-1.5 rounded hover:bg-red-500/10 text-gray-600 hover:text-red-400 transition-colors disabled:opacity-40"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Logs modal */}
      {logsModal && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6" onClick={() => setLogsModal(null)}>
          <div className="bg-[#0d0d0d] border border-white/10 rounded-2xl w-full max-w-3xl max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3 px-5 py-4 border-b border-white/5">
              <Terminal className="w-4 h-4 text-purple-400" />
              <span className="text-[12px] font-bold text-white">{logsModal.hosting.name} — Logs</span>
              <button onClick={() => setLogsModal(null)} className="ml-auto text-gray-600 hover:text-white text-lg leading-none">×</button>
            </div>
            <pre className="flex-1 overflow-auto p-5 text-[10px] text-gray-300 font-mono leading-relaxed whitespace-pre-wrap">
              {logsModal.logs}
            </pre>
          </div>
        </div>
      )}

      {/* Terminate modal */}
      {terminateModal && (
        <TerminateModal
          hosting={terminateModal}
          onConfirm={async (reason) => {
            await adminTerminateHosting(terminateModal.hosting_id, reason);
            setTerminate(null);
            onReload?.();
          }}
          onCancel={() => setTerminate(null)}
        />
      )}
    </>
  );
}

function TerminateModal({ hosting, onConfirm, onCancel }) {
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (!reason.trim()) { setErr('La razón es obligatoria.'); return; }
    if (!window.confirm(`⚠️ ACCIÓN IRREVERSIBLE\n\nEsto eliminará "${hosting.name}" y su contenedor Docker permanentemente.\n\n¿Confirmar?`)) return;
    setSaving(true);
    try {
      await onConfirm(reason.trim());
    } catch (ex) {
      setErr(ex?.response?.data?.detail || 'Error terminando hosting');
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-6">
      <form onSubmit={submit} className="bg-[#0d0d0d] border border-red-500/30 rounded-2xl w-full max-w-md p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-red-500/15 flex items-center justify-center">
            <Trash2 className="w-4 h-4 text-red-400" />
          </div>
          <div>
            <div className="text-[12px] font-bold text-white">Terminar hosting</div>
            <div className="text-[10px] text-gray-500">{hosting.name} · {hosting.container_name}</div>
          </div>
        </div>

        <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-3 text-[10px] text-red-400">
          Esta acción elimina el contenedor Docker y el registro de forma <strong>permanente e irreversible</strong>.
          Queda registrado en el audit log con tu email y razón.
        </div>

        {err && <div className="text-[11px] text-red-400">{err}</div>}

        <div>
          <label className="block text-[9px] uppercase tracking-wider text-gray-500 mb-1.5">
            Razón de terminación <span className="text-red-400">*</span>
          </label>
          <select
            value={reason}
            onChange={e => setReason(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[11px] text-white outline-none focus:border-red-500/50 mb-2"
          >
            <option value="">— Selecciona una razón —</option>
            <option value="Uso indebido / spam">Uso indebido / spam</option>
            <option value="Violación de términos de servicio">Violación de términos de servicio</option>
            <option value="Actividad maliciosa / phishing">Actividad maliciosa / phishing</option>
            <option value="Contenido prohibido">Contenido prohibido</option>
            <option value="Solicitud del cliente">Solicitud del cliente</option>
            <option value="Falta de pago">Falta de pago</option>
          </select>
          <textarea
            placeholder="Descripción adicional (opcional)..."
            value={reason.startsWith('Otro:') ? reason.slice(5) : ''}
            onChange={e => setReason(e.target.value ? `Otro: ${e.target.value}` : '')}
            rows={2}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[11px] text-white placeholder-gray-600 outline-none focus:border-red-500/50 resize-none"
          />
        </div>

        <div className="flex gap-2 pt-1">
          <button type="submit" disabled={saving || !reason}
            className="flex-1 py-2 rounded-xl text-[11px] font-bold bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors disabled:opacity-40">
            {saving ? 'Terminando...' : 'Confirmar terminación'}
          </button>
          <button type="button" onClick={onCancel}
            className="px-4 py-2 rounded-xl text-[11px] text-gray-500 bg-white/5 hover:text-white transition-colors">
            Cancelar
          </button>
        </div>
      </form>
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

/* ═══════════════════════════════════════════════════════════
   EQUIPO — Colaboradores + Analytics
   ═══════════════════════════════════════════════════════════ */

const ROLE_LABELS = { support: 'Soporte', billing: 'Billing', readonly: 'Solo lectura' };
const ROLE_COLORS = {
  support:  'bg-amber-500/15 text-amber-400',
  billing:  'bg-blue-500/15 text-blue-400',
  readonly: 'bg-white/5 text-gray-500',
};

function EquipoSection() {
  const [tab, setTab]           = useState('staff');      // 'staff' | 'analytics'
  const [staffList, setStaff]   = useState([]);
  const [loading, setLoading]   = useState(false);
  const [showCreate, setCreate] = useState(false);
  const [created, setCreated]   = useState(null);  // { email, temp_password }
  const [editId, setEditId]     = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setStaff(await listStaff()); }
    catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5">
      {/* Tab switcher */}
      <div className="flex items-center gap-1 border-b border-white/5 pb-3">
        {[
          { id: 'staff',     label: 'Colaboradores', icon: UserCog },
          { id: 'analytics', label: 'Analytics',     icon: TrendingUp },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold transition-colors ${
              tab === t.id
                ? 'bg-amber-500/15 text-amber-400'
                : 'text-gray-500 hover:text-white hover:bg-white/5'
            }`}
          >
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
        {tab === 'staff' && (
          <button
            onClick={() => { setCreate(true); setCreated(null); }}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold
              bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            Nuevo colaborador
          </button>
        )}
      </div>

      {/* Create form */}
      {tab === 'staff' && showCreate && (
        <CreateStaffForm
          onDone={(result) => { setCreated(result); setCreate(false); load(); }}
          onCancel={() => setCreate(false)}
        />
      )}

      {/* Success box after creation */}
      {tab === 'staff' && created && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 space-y-2">
          <div className="text-[11px] font-bold text-emerald-400">✓ Colaborador creado</div>
          <div className="text-[11px] text-gray-300">
            Email: <span className="font-mono text-white">{created.email}</span>
          </div>
          <div className="text-[11px] text-gray-300 flex items-center gap-2">
            Contraseña temporal:
            <code className="font-mono text-amber-300 bg-black/30 px-2 py-0.5 rounded select-all">
              {created.temp_password}
            </code>
          </div>
          <p className="text-[10px] text-gray-600">
            Esta contraseña solo se muestra una vez. Compártela de forma segura.
          </p>
          <button onClick={() => setCreated(null)} className="text-[10px] text-gray-600 hover:text-white underline">
            Cerrar
          </button>
        </div>
      )}

      {/* Staff list */}
      {tab === 'staff' && (
        <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-white/5">
                {['Colaborador', 'Rol', 'Estado', 'Acciones 30d', 'Último login', 'Opciones'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-600 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="p-8 text-center"><RefreshCw className="w-4 h-4 animate-spin mx-auto text-gray-600" /></td></tr>
              ) : staffList.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-10 text-center text-gray-600 italic text-[11px]">
                    Sin colaboradores. Crea el primero con "Nuevo colaborador".
                  </td>
                </tr>
              ) : staffList.map(s => (
                <React.Fragment key={s.staff_id}>
                  <tr className={`border-b border-white/5 transition-colors ${editId === s.staff_id ? 'bg-amber-500/5' : 'hover:bg-white/[0.02]'}`}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold ${s.is_active ? 'bg-amber-500/15 text-amber-400' : 'bg-white/5 text-gray-600'}`}>
                          {s.full_name?.[0]?.toUpperCase() || '?'}
                        </div>
                        <div>
                          <div className={`text-[11px] font-medium ${s.is_active ? 'text-white' : 'text-gray-600'}`}>{s.full_name}</div>
                          <div className="text-[10px] text-gray-600">{s.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${ROLE_COLORS[s.role] || 'bg-white/5 text-gray-500'}`}>
                        {ROLE_LABELS[s.role] || s.role}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {s.is_active
                        ? <span className="text-emerald-400 text-[10px] font-bold">● Activo</span>
                        : <span className="text-red-500 text-[10px] font-bold">● Inactivo</span>}
                    </td>
                    <td className="px-4 py-3 font-mono text-[11px] text-amber-400">{s.total_actions_30d ?? 0}</td>
                    <td className="px-4 py-3 text-[10px] text-gray-500">
                      {s.last_login_at
                        ? new Date(s.last_login_at).toLocaleString('es-AR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
                        : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => setEditId(editId === s.staff_id ? null : s.staff_id)}
                          className="p-1.5 rounded hover:bg-white/10 text-gray-500 hover:text-white transition-colors"
                          title="Editar nombre / rol"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                        {/* Reset password */}
                        <button
                          onClick={async () => {
                            if (!window.confirm(`¿Generar nueva contraseña temporal para ${s.full_name}?\nLa contraseña anterior quedará inválida.`)) return;
                            try {
                              const r = await resetStaffPassword(s.staff_id);
                              alert(`Nueva contraseña para ${r.email}:\n\n${r.new_password}\n\nCópiala ahora — no se mostrará de nuevo.`);
                            } catch (ex) {
                              alert(ex?.response?.data?.detail || 'Error reseteando contraseña');
                            }
                          }}
                          className="p-1.5 rounded hover:bg-blue-500/10 text-gray-500 hover:text-blue-400 transition-colors"
                          title="Resetear contraseña"
                        >
                          <KeyRound className="w-3.5 h-3.5" />
                        </button>
                        {/* Activar / Desactivar */}
                        <button
                          onClick={async () => {
                            if (!window.confirm(`¿${s.is_active ? 'Desactivar' : 'Activar'} a ${s.full_name}?`)) return;
                            await updateStaff(s.staff_id, { is_active: !s.is_active });
                            load();
                          }}
                          className={`p-1.5 rounded transition-colors ${s.is_active ? 'hover:bg-orange-500/10 text-gray-500 hover:text-orange-400' : 'hover:bg-emerald-500/10 text-gray-500 hover:text-emerald-400'}`}
                          title={s.is_active ? 'Desactivar cuenta' : 'Activar cuenta'}
                        >
                          {s.is_active ? <ToggleRight className="w-3.5 h-3.5" /> : <ToggleLeft className="w-3.5 h-3.5" />}
                        </button>
                        {/* Eliminar colaborador (soft delete permanente) */}
                        <button
                          onClick={async () => {
                            if (!window.confirm(`¿Eliminar la cuenta de ${s.full_name} (${s.email})?\n\nSe desactivará permanentemente. El historial de actividad se conserva.`)) return;
                            try {
                              await deactivateStaff(s.staff_id);
                              load();
                            } catch (ex) {
                              alert(ex?.response?.data?.detail || 'Error al eliminar');
                            }
                          }}
                          className="p-1.5 rounded hover:bg-red-500/10 text-gray-600 hover:text-red-400 transition-colors"
                          title="Eliminar colaborador"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {editId === s.staff_id && (
                    <tr className="border-b border-white/5 bg-[#0d0d0d]">
                      <td colSpan={6} className="px-6 py-4">
                        <EditStaffRow
                          staff={s}
                          onSave={async (data) => { await updateStaff(s.staff_id, data); setEditId(null); load(); }}
                          onCancel={() => setEditId(null)}
                        />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Analytics tab */}
      {tab === 'analytics' && <StaffAnalytics />}
    </div>
  );
}

function CreateStaffForm({ onDone, onCancel }) {
  const [form, setForm] = useState({ email: '', full_name: '', role: 'support' });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setErr('');
    try {
      const result = await createStaff(form);
      onDone(result);
    } catch (ex) {
      setErr(ex?.response?.data?.detail || 'Error creando colaborador');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="bg-[#0d0d0d] border border-white/10 rounded-xl p-5 space-y-4">
      <div className="text-[11px] font-bold text-white mb-1">Nuevo colaborador</div>
      {err && <div className="text-[11px] text-red-400">{err}</div>}
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="block text-[9px] uppercase tracking-wider text-gray-500 mb-1">Email</label>
          <input
            required type="email" value={form.email}
            onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[11px] text-white placeholder-gray-600 outline-none focus:border-amber-500/50"
            placeholder="colaborador@empresa.com"
          />
        </div>
        <div>
          <label className="block text-[9px] uppercase tracking-wider text-gray-500 mb-1">Nombre completo</label>
          <input
            required value={form.full_name}
            onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[11px] text-white placeholder-gray-600 outline-none focus:border-amber-500/50"
            placeholder="Juan Pérez"
          />
        </div>
        <div>
          <label className="block text-[9px] uppercase tracking-wider text-gray-500 mb-1">Rol</label>
          <select
            value={form.role}
            onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[11px] text-white outline-none focus:border-amber-500/50"
          >
            <option value="support">Soporte — acceso remoto + edición código</option>
            <option value="billing">Billing — solo facturación</option>
            <option value="readonly">Solo lectura — dashboards y métricas</option>
          </select>
        </div>
      </div>
      <div className="flex gap-2">
        <button type="submit" disabled={saving}
          className="px-4 py-2 rounded-lg text-[11px] font-bold bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 transition-colors disabled:opacity-50">
          {saving ? 'Creando...' : 'Crear colaborador'}
        </button>
        <button type="button" onClick={onCancel}
          className="px-4 py-2 rounded-lg text-[11px] font-bold bg-white/5 text-gray-400 hover:text-white transition-colors">
          Cancelar
        </button>
      </div>
    </form>
  );
}

function EditStaffRow({ staff, onSave, onCancel }) {
  const [role, setRole] = useState(staff.role);
  const [name, setName] = useState(staff.full_name);
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try { await onSave({ role, full_name: name }); }
    finally { setSaving(false); }
  };

  return (
    <form onSubmit={submit} className="flex items-end gap-4">
      <div>
        <label className="block text-[9px] uppercase tracking-wider text-gray-600 mb-1">Nombre</label>
        <input value={name} onChange={e => setName(e.target.value)}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-[11px] text-white outline-none focus:border-amber-500/50 w-48" />
      </div>
      <div>
        <label className="block text-[9px] uppercase tracking-wider text-gray-600 mb-1">Rol</label>
        <select value={role} onChange={e => setRole(e.target.value)}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-[11px] text-white outline-none focus:border-amber-500/50">
          <option value="support">Soporte</option>
          <option value="billing">Billing</option>
          <option value="readonly">Solo lectura</option>
        </select>
      </div>
      <button type="submit" disabled={saving}
        className="px-3 py-1.5 rounded-lg text-[11px] font-bold bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 transition-colors disabled:opacity-50">
        {saving ? '...' : 'Guardar'}
      </button>
      <button type="button" onClick={onCancel}
        className="px-3 py-1.5 rounded-lg text-[11px] text-gray-500 hover:text-white bg-white/5 transition-colors">
        Cancelar
      </button>
    </form>
  );
}
