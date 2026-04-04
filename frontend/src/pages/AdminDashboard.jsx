import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users, Globe, BarChart3, RefreshCw, ShieldCheck, Activity,
  LogOut, Cpu, Zap, Bell, Settings, ChevronRight, AlertTriangle,
  CheckCircle2, XCircle, Clock, Database
} from 'lucide-react';
import {
  getAdminUsers, getAdminHostings, getAdminPixelOverview,
  getAdminPixelEvents, getAdminHostingsMetrics
} from '../services/api';
import { useAuth } from '../hooks/useAuth';

const NAV_ITEMS = [
  { id: 'overview',  label: 'Dashboard',       icon: Activity },
  { id: 'users',     label: 'User Management', icon: Users },
  { id: 'hostings',  label: 'Hosting',         icon: Globe },
  { id: 'pixel',     label: 'Pixel Metrics',   icon: BarChart3 },
  { id: 'logs',      label: 'Event Logs',      icon: Database },
];

const PLAN_STYLE = {
  free:     'bg-white/5 text-gray-400',
  personal: 'bg-blue-500/20 text-blue-400',
  negocio:  'bg-amber-500/20 text-amber-400',
  agencia:  'bg-purple-500/20 text-purple-400',
  pro:      'bg-emerald-500/20 text-emerald-400',
};

const STATUS_ICON = {
  active:   <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />,
  stopped:  <XCircle className="w-3.5 h-3.5 text-red-400" />,
  expired:  <XCircle className="w-3.5 h-3.5 text-red-600" />,
  error:    <XCircle className="w-3.5 h-3.5 text-red-400" />,
  starting: <Clock className="w-3.5 h-3.5 text-amber-400" />,
};

const STATUS_COLOR = {
  active:   'text-emerald-400',
  stopped:  'text-red-400',
  expired:  'text-red-600',
  error:    'text-red-400',
  starting: 'text-amber-400',
};

function Initials({ email }) {
  const letters = email ? email.slice(0, 2).toUpperCase() : '??';
  const colors = ['bg-blue-600', 'bg-purple-600', 'bg-emerald-600', 'bg-amber-600', 'bg-rose-600'];
  const color = colors[email?.charCodeAt(0) % colors.length] || 'bg-gray-600';
  return (
    <div className={`w-7 h-7 rounded-full ${color} flex items-center justify-center text-[10px] font-bold text-white shrink-0`}>
      {letters}
    </div>
  );
}

export default function AdminDashboard() {
  const navigate = useNavigate();
  const { logoutAction, user } = useAuth();

  const [activeSection, setActiveSection] = useState('overview');
  const [users, setUsers]           = useState([]);
  const [hostings, setHostings]     = useState([]);
  const [hostingMetrics, setHostingMetrics] = useState([]);
  const [pixelOverview, setPixelOverview]   = useState(null);
  const [pixelEvents, setPixelEvents]       = useState([]);
  const [loading, setLoading]       = useState(true);
  const [activeTab, setActiveTab]   = useState('users');

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [u, h, hm, po, pe] = await Promise.allSettled([
        getAdminUsers(),
        getAdminHostings(),
        getAdminHostingsMetrics(),
        getAdminPixelOverview(),
        getAdminPixelEvents(50, 0),
      ]);
      if (u.status === 'fulfilled')  setUsers(u.value);
      if (h.status === 'fulfilled')  setHostings(h.value);
      if (hm.status === 'fulfilled') setHostingMetrics(hm.value);
      if (po.status === 'fulfilled') setPixelOverview(po.value);
      if (pe.status === 'fulfilled') setPixelEvents(pe.value);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  // Alerts from real hosting data
  const alerts = [
    ...hostings.filter(h => h.status === 'error').map(h => ({
      level: 'error', title: `Error en ${h.name}`, body: `Contenedor ${h.container_name} en estado error.`
    })),
    ...hostings.filter(h => h.status === 'stopped').map(h => ({
      level: 'warn', title: `Sitio detenido`, body: `${h.name} (${h.subdomain}) está parado.`
    })),
    ...hostings.filter(h => h.plan === 'free' && h.days_remaining !== undefined && h.days_remaining <= 3 && h.days_remaining > 0).map(h => ({
      level: 'info', title: `Expira pronto`, body: `${h.name} vence en ${h.days_remaining} día(s).`
    })),
  ];

  const ALERT_STYLE = {
    error: 'border-red-500/30 bg-red-500/5',
    warn:  'border-amber-500/30 bg-amber-500/5',
    info:  'border-blue-500/30 bg-blue-500/5',
  };
  const ALERT_DOT = { error: 'bg-red-400', warn: 'bg-amber-400', info: 'bg-blue-400' };

  return (
    <div className="fixed inset-0 flex bg-[#0a0a0a] text-white overflow-hidden" style={{ fontFamily: 'Inter, sans-serif' }}>

      {/* ── SIDEBAR ── */}
      <aside className="w-56 shrink-0 flex flex-col border-r border-white/5 bg-[#0d0d0d]">
        {/* Logo */}
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

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5 overflow-y-auto">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveSection(id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[12px] font-medium transition-all text-left ${
                activeSection === id
                  ? 'bg-[#00ff88]/10 text-[#00ff88] border border-[#00ff88]/20'
                  : 'text-gray-400 hover:bg-white/5 hover:text-white border border-transparent'
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </button>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-3 py-4 border-t border-white/5 flex flex-col gap-1">
          <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[12px] text-gray-500 hover:bg-white/5 hover:text-white transition-all">
            <Settings className="w-4 h-4" /> Settings
          </button>
          <button
            onClick={logoutAction}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[12px] text-gray-500 hover:bg-red-500/10 hover:text-red-400 transition-all"
          >
            <LogOut className="w-4 h-4" /> Logout
          </button>
        </div>
      </aside>

      {/* ── MAIN ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Top bar */}
        <header className="h-14 shrink-0 flex items-center justify-between px-6 border-b border-white/5 bg-[#0d0d0d]">
          <div className="flex items-center gap-3">
            <h1 className="text-[13px] font-semibold text-white">
              {NAV_ITEMS.find(n => n.id === activeSection)?.label ?? 'Admin Console'}
            </h1>
            <span className="text-[10px] text-gray-500 font-mono">Real-time performance metrics</span>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={fetchAll} className="w-8 h-8 rounded-lg border border-white/10 flex items-center justify-center hover:bg-white/5 transition-all" title="Refresh">
              <RefreshCw className={`w-3.5 h-3.5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <div className="relative">
              <Bell className="w-4 h-4 text-gray-400" />
              {alerts.length > 0 && (
                <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full text-[7px] flex items-center justify-center font-bold">
                  {alerts.length}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Initials email={user?.email} />
              <div className="text-right">
                <div className="text-[11px] font-medium text-white leading-none">System Admin</div>
                <div className="text-[9px] text-[#00ff88] font-mono">Superuser</div>
              </div>
            </div>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          <div className="p-6 flex gap-5">

            {/* Main content column */}
            <div className="flex-1 min-w-0 flex flex-col gap-5">

              {/* OVERVIEW / DASHBOARD */}
              {(activeSection === 'overview') && (
                <>
                  {/* Stats cards */}
                  <div className="grid grid-cols-4 gap-4">
                    {[
                      { label: 'Users',         val: users.length,                       sub: `+${users.filter(u => {
                          const d = new Date(u.created_at); const now = new Date();
                          return (now - d) < 7*24*3600*1000;
                        }).length} esta semana`, color: '#00aaff', icon: <Users className="w-4 h-4" /> },
                      { label: 'Total Hostings', val: hostings.length,                   sub: `${hostings.filter(h => h.status === 'active').length} activos`, color: '#00ff88', icon: <Globe className="w-4 h-4" /> },
                      { label: 'Active Pixels',  val: pixelOverview?.total_sites ?? '—', sub: `${pixelOverview?.today_events ?? 0} eventos hoy`, color: '#ffaa00', icon: <Zap className="w-4 h-4" /> },
                      { label: 'Pixel Events',   val: pixelOverview?.total_events ?? '—',sub: 'total acumulado', color: '#aa00ff', icon: <BarChart3 className="w-4 h-4" /> },
                    ].map((m, i) => (
                      <div key={i} className="bg-[#111] rounded-xl border border-white/5 p-4">
                        <div className="flex items-start justify-between mb-3">
                          <span className="text-[10px] text-gray-500 uppercase tracking-wider font-medium">{m.label}</span>
                          <div style={{ color: m.color }} className="opacity-60">{m.icon}</div>
                        </div>
                        <div className="text-2xl font-bold" style={{ color: m.color }}>
                          {loading ? <div className="w-12 h-6 bg-white/5 rounded animate-pulse" /> : m.val}
                        </div>
                        <div className="text-[10px] text-gray-500 mt-1 font-mono">{m.sub}</div>
                      </div>
                    ))}
                  </div>

                  {/* Tabs for overview */}
                  <div>
                    <div className="flex gap-1 border-b border-white/5 mb-4">
                      {[
                        { id: 'users',    label: `Users (${users.length})` },
                        { id: 'hostings', label: `Hostings (${hostings.length})` },
                        { id: 'pixel',    label: `Pixel (${pixelEvents.length})` },
                      ].map(tab => (
                        <button
                          key={tab.id}
                          onClick={() => setActiveTab(tab.id)}
                          className={`px-4 py-2 text-[11px] font-medium border-b-2 transition-all -mb-px ${
                            activeTab === tab.id
                              ? 'border-[#00ff88] text-[#00ff88]'
                              : 'border-transparent text-gray-500 hover:text-white'
                          }`}
                        >
                          {tab.label}
                        </button>
                      ))}
                    </div>

                    {activeTab === 'users' && <UsersTable users={users} loading={loading} navigate={navigate} />}
                    {activeTab === 'hostings' && <HostingsTable hostings={hostings} metrics={hostingMetrics} loading={loading} />}
                    {activeTab === 'pixel' && <PixelTable events={pixelEvents} overview={pixelOverview} loading={loading} />}
                  </div>
                </>
              )}

              {/* USER MANAGEMENT */}
              {activeSection === 'users' && (
                <>
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] text-gray-500">Mostrando {users.length} usuarios registrados</div>
                  </div>
                  <UsersTable users={users} loading={loading} navigate={navigate} />
                </>
              )}

              {/* HOSTING */}
              {activeSection === 'hostings' && (
                <HostingsTable hostings={hostings} metrics={hostingMetrics} loading={loading} />
              )}

              {/* PIXEL METRICS */}
              {activeSection === 'pixel' && (
                <PixelTable events={pixelEvents} overview={pixelOverview} loading={loading} />
              )}

              {/* EVENT LOGS */}
              {activeSection === 'logs' && (
                <div className="bg-[#111] rounded-xl border border-white/5 p-6 text-center text-gray-500 text-sm">
                  Los eventos de orquestación se registran por usuario. Entra en un usuario desde User Management para ver su historial.
                </div>
              )}
            </div>

            {/* Alerts sidebar */}
            <div className="w-64 shrink-0 flex flex-col gap-4">
              <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
                  <span className="text-[11px] font-semibold text-white">Recent Alerts</span>
                  {alerts.length > 0 && (
                    <span className="text-[9px] text-gray-500 cursor-pointer hover:text-white">Clear All</span>
                  )}
                </div>
                <div className="p-3 flex flex-col gap-2 max-h-80 overflow-y-auto">
                  {alerts.length === 0 ? (
                    <div className="py-6 text-center text-[11px] text-gray-600">
                      <CheckCircle2 className="w-5 h-5 mx-auto mb-2 text-emerald-600" />
                      Sistema saludable
                    </div>
                  ) : alerts.map((a, i) => (
                    <div key={i} className={`p-3 rounded-lg border text-[11px] ${ALERT_STYLE[a.level]}`}>
                      <div className="flex items-center gap-1.5 mb-1">
                        <div className={`w-1.5 h-1.5 rounded-full ${ALERT_DOT[a.level]}`} />
                        <span className="font-medium text-white">{a.title}</span>
                      </div>
                      <p className="text-gray-400 leading-relaxed">{a.body}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* System stats */}
              <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                <div className="text-[11px] font-semibold text-white mb-3">System Stats</div>
                {[
                  { label: 'Containers activos', val: hostings.filter(h => h.status === 'active').length },
                  { label: 'Plan free',           val: hostings.filter(h => h.plan === 'free').length },
                  { label: 'Errores detectados',  val: hostings.filter(h => h.status === 'error').length },
                  { label: 'Usuarios admin',      val: users.filter(u => u.role === 'admin').length },
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
    </div>
  );
}

/* ── Sub-components ── */

function UsersTable({ users, loading, navigate }) {
  return (
    <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-white/5">
            {['ID', 'Email', 'Role', 'Plan', 'Balance', 'Created Date'].map(h => (
              <th key={h} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-500 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-600">
              <RefreshCw className="w-4 h-4 animate-spin mx-auto" />
            </td></tr>
          ) : users.length === 0 ? (
            <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-600 text-xs italic">Sin usuarios.</td></tr>
          ) : users.map(u => (
            <tr
              key={u.user_id}
              onClick={() => navigate(`/admin/users/${u.user_id}`)}
              className="border-b border-white/5 hover:bg-white/3 cursor-pointer transition-colors group"
            >
              <td className="px-4 py-3 font-mono text-gray-500">#{String(u.user_id).padStart(4, '0')}</td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <Initials email={u.email} />
                  <span className="text-white font-medium">{u.email}</span>
                </div>
              </td>
              <td className="px-4 py-3">
                <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${
                  u.role === 'admin' ? 'bg-red-500/20 text-red-400' : 'bg-white/5 text-gray-400'
                }`}>{u.role}</span>
              </td>
              <td className="px-4 py-3">
                <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${PLAN_STYLE[u.plan] || 'bg-white/5 text-gray-400'}`}>
                  {u.plan || 'free'}
                </span>
              </td>
              <td className="px-4 py-3 font-mono text-emerald-400">${(u.balance || 0).toFixed(2)}</td>
              <td className="px-4 py-3 text-gray-500">
                {u.created_at ? new Date(u.created_at).toLocaleDateString('es-AR', { day:'2-digit', month:'short', year:'numeric' }) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {users.length > 0 && (
        <div className="px-4 py-3 border-t border-white/5 text-[10px] text-gray-500">
          Showing 1 to {users.length} of {users.length} entries
        </div>
      )}
    </div>
  );
}

function HostingsTable({ hostings, metrics, loading }) {
  // Build a map container_name → live metrics
  const metricsMap = {};
  metrics.forEach(m => { metricsMap[m.container_name] = m; });

  return (
    <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-white/5">
            {['Nombre', 'Estado', 'Plan', 'CPU', 'RAM', 'Uptime 24h', 'Tráfico 24h', 'Subdominio'].map(h => (
              <th key={h} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-500 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={8} className="px-4 py-10 text-center text-gray-600">
              <RefreshCw className="w-4 h-4 animate-spin mx-auto" />
            </td></tr>
          ) : hostings.length === 0 ? (
            <tr><td colSpan={8} className="px-4 py-10 text-center text-gray-600 text-xs italic">Sin hostings.</td></tr>
          ) : hostings.map(h => {
            const m = metricsMap[h.container_name] || {};
            return (
              <tr key={h.hosting_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="px-4 py-3 text-white font-medium">{h.name}</td>
                <td className="px-4 py-3">
                  <div className={`flex items-center gap-1.5 font-medium ${STATUS_COLOR[h.status] || 'text-gray-400'}`}>
                    {STATUS_ICON[h.status] || null}
                    {h.status}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${PLAN_STYLE[h.plan] || 'bg-white/5 text-gray-400'}`}>
                    {h.plan}
                  </span>
                </td>
                <td className="px-4 py-3 font-mono text-[#00ff88]">{m.docker?.cpu ?? '—'}</td>
                <td className="px-4 py-3 font-mono text-blue-400">{m.docker?.mem_pct ?? '—'}</td>
                <td className="px-4 py-3 font-mono text-amber-400">
                  {m.uptime_pct != null ? `${m.uptime_pct.toFixed(1)}%` : '—'}
                </td>
                <td className="px-4 py-3 font-mono text-gray-400">
                  {m.traffic_24h?.total_requests != null ? `${m.traffic_24h.total_requests} req` : '—'}
                </td>
                <td className="px-4 py-3 text-gray-500 font-mono text-[10px]">{h.subdomain}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PixelTable({ events, overview, loading }) {
  return (
    <div className="flex flex-col gap-4">
      {overview && (
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: 'Total Eventos', val: overview.total_events, color: '#aa00ff' },
            { label: 'Hoy',           val: overview.today_events, color: '#00aaff' },
            { label: 'Sitios',        val: overview.total_sites,  color: '#00ff88' },
            { label: 'Tipos',         val: overview.by_event_type?.length ?? 0, color: '#ffaa00' },
          ].map((m, i) => (
            <div key={i} className="bg-[#111] rounded-xl border border-white/5 p-4">
              <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-2">{m.label}</div>
              <div className="text-xl font-bold font-mono" style={{ color: m.color }}>{loading ? '—' : m.val}</div>
            </div>
          ))}
        </div>
      )}
      <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-white/5">
              {['Sitio', 'Tipo', 'URL', 'Dispositivo', 'Browser', 'Fecha'].map(h => (
                <th key={h} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-500 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-600"><RefreshCw className="w-4 h-4 animate-spin mx-auto" /></td></tr>
            ) : events.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-gray-600 text-xs italic">Sin eventos registrados.</td></tr>
            ) : events.map(e => (
              <tr key={e.event_id} className="border-b border-white/5 hover:bg-white/3 transition-colors">
                <td className="px-4 py-3 text-purple-400 font-mono">{e.site_name || e.site_id?.slice(0, 8)}</td>
                <td className="px-4 py-3 text-white">{e.event_type}</td>
                <td className="px-4 py-3 text-gray-500 truncate max-w-[180px]" title={e.url}>{e.url?.replace(/^https?:\/\//, '') || '—'}</td>
                <td className="px-4 py-3 text-gray-500">{e.device || '—'}</td>
                <td className="px-4 py-3 text-gray-500">{e.browser || '—'}</td>
                <td className="px-4 py-3 text-gray-500 font-mono">{e.created_at ? new Date(e.created_at).toLocaleString('es-AR') : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
