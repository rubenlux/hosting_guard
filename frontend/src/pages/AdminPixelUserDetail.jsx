import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ShieldCheck, RefreshCw, ArrowRight, Activity, AlertTriangle,
  XCircle, ChevronDown, ChevronUp, BarChart3, Users, Eye, MousePointer
} from 'lucide-react';
import { getAdminPixelHealth, getAdminUsers, getPixelSiteStats } from '../services/api';

/* ─── helpers ─── */
function fmtDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}
function fmtTime(secs) {
  if (!secs) return '—';
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

function StatusBadge({ status }) {
  const map = {
    active:  { label: 'Active',  cls: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20', icon: <Activity className="w-2.5 h-2.5" /> },
    warning: { label: 'Warning', cls: 'bg-amber-500/15 text-amber-400 border-amber-500/20',       icon: <AlertTriangle className="w-2.5 h-2.5" /> },
    dead:    { label: 'Dead',    cls: 'bg-red-500/15 text-red-400 border-red-500/20',             icon: <XCircle className="w-2.5 h-2.5" /> },
  };
  const s = map[status] || map.dead;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[9px] font-semibold uppercase ${s.cls}`}>
      {s.icon}{s.label}
    </span>
  );
}

/* ─── Mini stat ─── */
function MiniStat({ label, val, color }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="text-[9px] text-gray-600 uppercase tracking-wider">{label}</div>
      <div className="text-[13px] font-bold font-mono" style={{ color: color || '#fff' }}>{val ?? '—'}</div>
    </div>
  );
}

/* ─── Site stats panel (expandable) ─── */
function SiteStats({ siteId }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPixelSiteStats(siteId, 30)
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [siteId]);

  if (loading) {
    return (
      <div className="px-4 pb-4 flex items-center gap-2 text-[10px] text-gray-500">
        <RefreshCw className="w-3 h-3 animate-spin" /> Cargando stats…
      </div>
    );
  }
  if (!stats) {
    return <div className="px-4 pb-4 text-[10px] text-gray-600 italic">No se pudieron cargar los datos.</div>;
  }

  return (
    <div className="px-4 pb-4 border-t border-white/5 mt-3 pt-4">
      {/* Key numbers */}
      <div className="grid grid-cols-5 gap-4 mb-4">
        <MiniStat label="Sessions"     val={stats.unique_sessions}  color="#00aaff" />
        <MiniStat label="Visitors"     val={stats.unique_visitors}  color="#00ff88" />
        <MiniStat label="Page views"   val={stats.total_events}     color="#ffaa00" />
        <MiniStat label="Bounce rate"  val={stats.bounce_rate != null ? `${stats.bounce_rate}%` : null} color="#ff6b6b" />
        <MiniStat label="Avg time"     val={fmtTime(stats.avg_time_on_page)} color="#4ecdc4" />
      </div>

      {/* Top pages + referrers side by side */}
      {(stats.top_pages?.length > 0 || stats.top_referrers?.length > 0) && (
        <div className="grid grid-cols-2 gap-4 mb-4">
          {stats.top_pages?.length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-wider text-gray-500 mb-2 flex items-center gap-1">
                <Eye className="w-2.5 h-2.5" /> Top páginas
              </div>
              <div className="flex flex-col gap-1">
                {stats.top_pages.slice(0, 5).map((p, i) => (
                  <div key={i} className="flex justify-between text-[10px]">
                    <span className="text-gray-400 truncate w-44" title={p.url}>{p.url?.replace(/^https?:\/\/[^/]+/, '') || '/'}</span>
                    <span className="font-mono text-white ml-2">{p.views}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {stats.top_referrers?.length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-wider text-gray-500 mb-2 flex items-center gap-1">
                <ArrowRight className="w-2.5 h-2.5" /> Referrers
              </div>
              <div className="flex flex-col gap-1">
                {stats.top_referrers.slice(0, 5).map((r, i) => (
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

      {/* Device + Browser */}
      {(stats.by_device?.length > 0 || stats.by_browser?.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          {stats.by_device?.length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-wider text-gray-500 mb-2">Dispositivos</div>
              <div className="flex flex-col gap-1">
                {stats.by_device.map((d, i) => (
                  <div key={i} className="flex justify-between text-[10px]">
                    <span className="text-gray-400 capitalize">{d.device}</span>
                    <span className="font-mono text-white">{d.count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {stats.by_browser?.length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-wider text-gray-500 mb-2">Navegadores</div>
              <div className="flex flex-col gap-1">
                {stats.by_browser.slice(0, 4).map((b, i) => (
                  <div key={i} className="flex justify-between text-[10px]">
                    <span className="text-gray-400 capitalize">{b.browser}</span>
                    <span className="font-mono text-white">{b.count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── Site row ─── */
function SiteRow({ site }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-b border-white/5 last:border-0">
      <div
        className="px-4 py-3 flex items-center gap-4 hover:bg-white/3 cursor-pointer transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[12px] font-medium text-white">{site.name}</span>
            {site.domain && <span className="text-[9px] text-gray-500 font-mono">{site.domain}</span>}
          </div>
          <div className="text-[9px] text-gray-600 font-mono">{site.site_id}</div>
        </div>
        <StatusBadge status={site.status} />
        <div className="text-[10px] text-gray-500 font-mono w-36 text-right shrink-0">
          {fmtDate(site.last_seen_at)}
        </div>
        <div className="text-[10px] text-gray-600 font-mono w-16 text-right shrink-0">
          {site.total_events} ev.
        </div>
        <div className="shrink-0 text-gray-500">
          {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </div>

      {open && <SiteStats siteId={site.site_id} />}
    </div>
  );
}

/* ════════════════════════════════════════════════
   MAIN
═══════════════════════════════════════════════════ */
export default function AdminPixelUserDetail() {
  const navigate = useNavigate();
  const { user_id } = useParams();

  const [health, setHealth]     = useState([]);
  const [users, setUsers]       = useState([]);
  const [loading, setLoading]   = useState(true);

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

  const userInfo = useMemo(() => users.find(u => String(u.user_id) === String(user_id)), [users, user_id]);
  const sites    = useMemo(() => health.filter(s => String(s.user_id) === String(user_id)), [health, user_id]);

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

        <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5">
          <button
            onClick={() => navigate('/admin/pixel-users')}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[12px] font-medium text-gray-400 hover:bg-white/5 hover:text-white border border-transparent transition-all text-left"
          >
            <ArrowRight className="w-4 h-4 shrink-0 rotate-180" />
            Pixel Users
          </button>
          <div className="mt-2 px-3 py-2.5 rounded-lg bg-[#00ff88]/10 border border-[#00ff88]/20 text-[12px] font-medium text-[#00ff88] truncate">
            {loading ? '...' : (userInfo?.email || `User #${user_id}`)}
          </div>
        </nav>
      </aside>

      {/* ── MAIN ── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="h-14 shrink-0 flex items-center justify-between px-6 border-b border-white/5 bg-[#0d0d0d]">
          <div className="flex items-center gap-3">
            <h1 className="text-[13px] font-semibold text-white truncate">
              {loading ? 'Cargando…' : (userInfo?.email || `User #${user_id}`)}
            </h1>
            <span className="text-[10px] text-gray-500 font-mono">{sites.length} sites</span>
          </div>
          <button
            onClick={load}
            className="w-8 h-8 rounded-lg border border-white/10 flex items-center justify-center hover:bg-white/5 transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-5">

          {/* Summary */}
          {!loading && sites.length > 0 && (
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-2">Sites totales</div>
                <div className="text-2xl font-bold font-mono text-[#00aaff]">{sites.length}</div>
              </div>
              <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-2">Sites activos</div>
                <div className="text-2xl font-bold font-mono text-emerald-400">
                  {sites.filter(s => s.status === 'active').length}
                </div>
              </div>
              <div className="bg-[#111] rounded-xl border border-white/5 p-4">
                <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-2">Total eventos</div>
                <div className="text-2xl font-bold font-mono text-[#ffaa00]">
                  {sites.reduce((sum, s) => sum + (s.total_events || 0), 0)}
                </div>
              </div>
            </div>
          )}

          {/* Sites list */}
          <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
            <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
              <span className="text-[11px] font-semibold text-white">Sites de Pixel</span>
              <span className="text-[10px] text-gray-500">Haz click en un site para ver las estadísticas</span>
            </div>

            {loading ? (
              <div className="p-10 flex justify-center">
                <RefreshCw className="w-4 h-4 animate-spin text-gray-500" />
              </div>
            ) : sites.length === 0 ? (
              <div className="p-10 text-center text-gray-600 text-xs italic">
                Este usuario no tiene sites registrados.
              </div>
            ) : (
              <>
                {/* Header row */}
                <div className="px-4 py-2 border-b border-white/5 flex items-center gap-4">
                  <div className="flex-1 text-[9px] uppercase tracking-wider text-gray-600">Site</div>
                  <div className="text-[9px] uppercase tracking-wider text-gray-600 w-20 text-center">Status</div>
                  <div className="text-[9px] uppercase tracking-wider text-gray-600 w-36 text-right">Último evento</div>
                  <div className="text-[9px] uppercase tracking-wider text-gray-600 w-16 text-right">Eventos</div>
                  <div className="w-4" />
                </div>
                {sites.map(site => <SiteRow key={site.site_id} site={site} />)}
              </>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
