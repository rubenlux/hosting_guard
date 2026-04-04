import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, Users, RefreshCw, ArrowRight, Activity, AlertTriangle, XCircle } from 'lucide-react';
import { getAdminPixelHealth, getAdminUsers } from '../services/api';
import { useAuth } from '../hooks/useAuth';

/* ─── helpers ─── */
function fmtDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function StatusBadge({ status }) {
  const map = {
    active:  { label: 'Active',   cls: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20', icon: <Activity className="w-2.5 h-2.5" /> },
    warning: { label: 'Warning',  cls: 'bg-amber-500/15 text-amber-400 border-amber-500/20',       icon: <AlertTriangle className="w-2.5 h-2.5" /> },
    dead:    { label: 'Dead',     cls: 'bg-red-500/15 text-red-400 border-red-500/20',             icon: <XCircle className="w-2.5 h-2.5" /> },
  };
  const s = map[status] || map.dead;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[14px] font-semibold uppercase ${s.cls}`}>
      {s.icon}{s.label}
    </span>
  );
}

function Initials({ email }) {
  const letters = email ? email.slice(0, 2).toUpperCase() : '??';
  const colors = ['bg-blue-600', 'bg-purple-600', 'bg-emerald-600', 'bg-amber-600', 'bg-rose-600'];
  const color = colors[(email?.charCodeAt(0) || 0) % colors.length];
  return (
    <div className={`w-7 h-7 rounded-full ${color} flex items-center justify-center text-[14px] font-bold text-white shrink-0`}>
      {letters}
    </div>
  );
}

/* ─── worst status helper ─── */
function worstStatus(statuses) {
  if (statuses.includes('dead')) return 'dead';
  if (statuses.includes('warning')) return 'warning';
  if (statuses.includes('active')) return 'active';
  return 'dead';
}

/* ════════════════════════════════════════════════
   MAIN
═══════════════════════════════════════════════════ */
export default function AdminPixelUsers() {
  const navigate = useNavigate();
  const { logoutAction, user } = useAuth();

  const [health, setHealth]   = useState([]);
  const [users, setUsers]     = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [h, u] = await Promise.all([getAdminPixelHealth(), getAdminUsers()]);
      setHealth(h);
      setUsers(u);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  /* group health rows by user_id */
  const rows = useMemo(() => {
    const emailMap = {};
    users.forEach(u => { emailMap[u.user_id] = u.email; });

    const grouped = {};
    health.forEach(site => {
      const uid = site.user_id;
      if (!grouped[uid]) grouped[uid] = { user_id: uid, email: emailMap[uid] || `user #${uid}`, sites: [] };
      grouped[uid].sites.push(site);
    });

    return Object.values(grouped).map(g => ({
      ...g,
      site_count:   g.sites.length,
      worst_status: worstStatus(g.sites.map(s => s.status)),
      last_seen_at: g.sites.reduce((best, s) => {
        if (!best) return s.last_seen_at;
        if (!s.last_seen_at) return best;
        return s.last_seen_at > best ? s.last_seen_at : best;
      }, null),
    })).sort((a, b) => {
      if (a.last_seen_at && b.last_seen_at) return b.last_seen_at.localeCompare(a.last_seen_at);
      if (a.last_seen_at) return -1;
      return 1;
    });
  }, [health, users]);

  /* ── users who appear in users list but have no pixel sites ── */
  const usersWithSites = new Set(rows.map(r => r.user_id));
  const noPixel = users.filter(u => !usersWithSites.has(u.user_id));

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
              <div className="text-[14px] font-bold tracking-widest text-white uppercase">Admin Console</div>
              <div className="text-[14px] text-[#00ff88] font-mono tracking-widest">KINETIC COMMAND</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5">
          <button
            onClick={() => navigate('/admin')}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[14px] font-medium text-gray-400 hover:bg-white/5 hover:text-white border border-transparent transition-all text-left"
          >
            <ArrowRight className="w-4 h-4 shrink-0 rotate-180" />
            Volver al Admin
          </button>
          <div className="mt-2 px-3 py-2.5 rounded-lg bg-[#00ff88]/10 border border-[#00ff88]/20 flex items-center gap-3 text-[14px] font-medium text-[#00ff88]">
            <Users className="w-4 h-4 shrink-0" />
            Pixel Users
          </div>
        </nav>
      </aside>

      {/* ── MAIN ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="h-14 shrink-0 flex items-center justify-between px-6 border-b border-white/5 bg-[#0d0d0d]">
          <div className="flex items-center gap-3">
            <h1 className="text-[14px] font-semibold text-white">Pixel Users</h1>
            <span className="text-[14px] text-gray-500 font-mono">
              {rows.length} usuarios con pixel · {health.length} sites registrados
            </span>
          </div>
          <button
            onClick={load}
            className="w-8 h-8 rounded-lg border border-white/10 flex items-center justify-center hover:bg-white/5 transition-all"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-5">

          {/* Stats top */}
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: 'Usuarios con pixel',  val: rows.length,                                           color: '#00aaff' },
              { label: 'Sites activos',        val: health.filter(s => s.status === 'active').length,      color: '#00ff88' },
              { label: 'Sites muertos',        val: health.filter(s => s.status === 'dead').length,        color: '#ff6b6b' },
            ].map((s, i) => (
              <div key={i} className="bg-[#111] rounded-xl border border-white/5 p-4">
                <div className="text-[14px] text-gray-500 uppercase tracking-wider mb-2">{s.label}</div>
                <div className="text-2xl font-bold font-mono" style={{ color: s.color }}>
                  {loading ? <div className="w-10 h-6 bg-white/5 rounded animate-pulse" /> : s.val}
                </div>
              </div>
            ))}
          </div>

          {/* Users with pixel table */}
          <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
            <div className="px-4 py-3 border-b border-white/5 text-[14px] font-semibold text-white">
              Usuarios con Pixel instalado
            </div>
            {loading ? (
              <div className="p-10 flex justify-center">
                <RefreshCw className="w-4 h-4 animate-spin text-gray-500" />
              </div>
            ) : rows.length === 0 ? (
              <div className="p-10 text-center text-gray-600 text-xs italic">
                Ningún usuario tiene sites de pixel registrados.
              </div>
            ) : (
              <table className="w-full text-[14px]">
                <thead>
                  <tr className="border-b border-white/5">
                    {['Usuario', 'Sites', 'Status', 'Último evento', ''].map(h => (
                      <th key={h} className="text-left px-4 py-3 text-[14px] uppercase tracking-wider text-gray-500 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(row => (
                    <tr
                      key={row.user_id}
                      onClick={() => navigate(`/admin/pixel-users/${row.user_id}`)}
                      className="border-b border-white/5 hover:bg-white/3 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Initials email={row.email} />
                          <span className="text-white font-medium">{row.email}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 font-mono text-gray-300">{row.site_count}</td>
                      <td className="px-4 py-3"><StatusBadge status={row.worst_status} /></td>
                      <td className="px-4 py-3 text-gray-500 font-mono text-[14px]">{fmtDate(row.last_seen_at)}</td>
                      <td className="px-4 py-3 text-right">
                        <ArrowRight className="w-3.5 h-3.5 text-gray-600 ml-auto" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Users without pixel */}
          {noPixel.length > 0 && (
            <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
              <div className="px-4 py-3 border-b border-white/5 text-[14px] font-semibold text-gray-500">
                Sin pixel instalado ({noPixel.length})
              </div>
              <div className="divide-y divide-white/5">
                {noPixel.map(u => (
                  <div key={u.user_id} className="px-4 py-2.5 flex items-center gap-3">
                    <Initials email={u.email} />
                    <span className="text-[14px] text-gray-500">{u.email}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
