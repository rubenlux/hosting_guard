import React, { useEffect, useState, useCallback } from 'react';
import { Cpu, MemoryStick, RefreshCw, AlertTriangle, TrendingUp, HardDrive, Users, DollarSign } from 'lucide-react';
import { getAdminResourcesOverview, getAdminResourcesTenants, getAdminResourcesUsers } from '../../services/api';

function fmtMb(mb) {
  if (mb == null) return '—';
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

function fmtPct(v) {
  if (v == null) return '—';
  return `${Number(v).toFixed(1)}%`;
}

function fmtNum(v) {
  if (v == null || v === 0) return '—';
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`;
  return String(v);
}

function fmtMs(v) {
  if (v == null) return '—';
  return `${Math.round(v)}ms`;
}

function fmtUsd(v) {
  if (v == null) return '—';
  return `$${Number(v).toFixed(0)}`;
}

function cpuColor(pct) {
  if (pct == null) return 'text-gray-500';
  if (pct >= 80) return 'text-red-400';
  if (pct >= 50) return 'text-amber-400';
  return 'text-emerald-400';
}

function memColor(mb, limitMb) {
  if (!mb || !limitMb) return 'text-gray-500';
  const r = mb / limitMb;
  if (r >= 0.85) return 'text-red-400';
  if (r >= 0.6)  return 'text-amber-400';
  return 'text-emerald-400';
}

function marginColor(m) {
  if (m == null) return 'text-gray-500';
  if (m < 0) return 'text-red-400';
  if (m < 5) return 'text-amber-400';
  return 'text-emerald-400';
}

const REC_BADGE = {
  ok:              { label: 'OK',           cls: 'bg-emerald-500/15 text-emerald-400' },
  upgrade:         { label: 'Upgrade',      cls: 'bg-amber-500/15 text-amber-400'    },
  revisar:         { label: 'Revisar',      cls: 'bg-orange-500/15 text-orange-400'  },
  posible_abuso:   { label: 'Abuso?',       cls: 'bg-red-500/15 text-red-400'        },
  margen_negativo: { label: 'Margen neg.',  cls: 'bg-red-500/15 text-red-400'        },
};

function RecBadge({ rec }) {
  const b = REC_BADGE[rec] || { label: rec, cls: 'bg-white/8 text-gray-400' };
  return <span className={`text-[8px] px-1.5 py-0.5 rounded font-bold uppercase ${b.cls}`}>{b.label}</span>;
}

function Bar({ value, max, colorClass }) {
  const pct = max ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden mt-0.5">
      <div className={`h-full rounded-full transition-all ${colorClass}`} style={{ width: `${pct}%`, background: 'currentColor' }} />
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, color }) {
  return (
    <div className="bg-[#0d0d0f] rounded-xl border border-white/5 p-4 flex items-center gap-3">
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${color}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div>
        <div className="text-[18px] font-bold text-white leading-none">{value}</div>
        <div className="text-[10px] text-gray-500 mt-0.5">{label}</div>
        {sub && <div className="text-[9px] text-gray-600 mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

function HostingTable({ rows }) {
  return (
    <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
      <div className="px-4 py-3 border-b border-white/5 text-[11px] font-semibold text-white flex items-center gap-2">
        <Cpu className="w-3.5 h-3.5 text-blue-400" />
        Por Hosting
        <span className="ml-auto text-[9px] text-gray-600 font-normal">{rows.length} activos</span>
      </div>
      <div className="grid grid-cols-[1fr_70px_80px_60px_60px_60px_60px_70px] gap-1 px-4 py-2 border-b border-white/5 text-[9px] text-gray-600 uppercase tracking-wide">
        <span>Hosting / Email</span>
        <span>CPU</span>
        <span>RAM</span>
        <span>Disk</span>
        <span>Req/24h</span>
        <span>5xx</span>
        <span>Resp</span>
        <span>Rec.</span>
      </div>
      <div className="divide-y divide-white/5 max-h-[500px] overflow-y-auto">
        {rows.map((t) => (
          <div key={t.hosting_id}
               className="grid grid-cols-[1fr_70px_80px_60px_60px_60px_60px_70px] gap-1 items-center px-4 py-2.5 hover:bg-white/3 transition-colors">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] text-white font-medium truncate">{t.name}</span>
                {t.status && t.status !== 'active' && (
                  <span className="text-[8px] bg-amber-500/15 text-amber-400 px-1 rounded">{t.status}</span>
                )}
              </div>
              <div className="text-[9px] text-gray-500 truncate font-mono">{t.user_email}</div>
              {t.restart_count_24h > 0 && (
                <div className="text-[8px] text-red-400">{t.restart_count_24h} restart{t.restart_count_24h !== 1 ? 's' : ''}/24h</div>
              )}
            </div>
            <div>
              <span className={`text-[11px] font-mono font-bold ${cpuColor(t.cpu_pct)}`}>{fmtPct(t.cpu_pct)}</span>
              <Bar value={t.cpu_pct || 0} max={100} colorClass={cpuColor(t.cpu_pct)} />
            </div>
            <div>
              <span className={`text-[11px] font-mono font-bold ${memColor(t.mem_mb, t.mem_limit_mb)}`}>{fmtMb(t.mem_mb)}</span>
              {t.mem_limit_mb && <Bar value={t.mem_mb || 0} max={t.mem_limit_mb} colorClass={memColor(t.mem_mb, t.mem_limit_mb)} />}
            </div>
            <span className="text-[10px] text-gray-400 font-mono">{fmtMb(t.disk_mb)}</span>
            <span className="text-[10px] text-gray-400 font-mono">{fmtNum(t.requests_24h)}</span>
            <span className={`text-[10px] font-mono ${(t.errors_5xx_24h || 0) > 0 ? 'text-red-400' : 'text-gray-600'}`}>
              {fmtNum(t.errors_5xx_24h)}
            </span>
            <span className="text-[10px] text-gray-400 font-mono">{fmtMs(t.avg_response_ms)}</span>
            <RecBadge rec={t.recommendation} />
          </div>
        ))}
      </div>
    </div>
  );
}

function UserTable({ rows }) {
  return (
    <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
      <div className="px-4 py-3 border-b border-white/5 text-[11px] font-semibold text-white flex items-center gap-2">
        <Users className="w-3.5 h-3.5 text-purple-400" />
        Por Cliente
        <span className="ml-auto text-[9px] text-gray-600 font-normal">{rows.length} tenants</span>
      </div>
      <div className="grid grid-cols-[1fr_55px_55px_70px_70px_60px_60px_60px_65px_70px] gap-1 px-4 py-2 border-b border-white/5 text-[9px] text-gray-600 uppercase tracking-wide">
        <span>Email / Plan</span>
        <span>Billing</span>
        <span>Sites</span>
        <span>CPU avg</span>
        <span>RAM tot.</span>
        <span>Rev/mo</span>
        <span>Costo rec.</span>
        <span>Contribución</span>
        <span>Margen contrib.</span>
        <span>Rec.</span>
      </div>
      <div className="divide-y divide-white/5 max-h-[500px] overflow-y-auto">
        {rows.map((u) => {
          const billing = u.billing_interval === 'monthly' ? 'Monthly' : 'Annual';
          const billingCls = u.billing_interval === 'monthly'
            ? 'bg-purple-500/15 text-purple-400'
            : 'bg-blue-500/15 text-blue-400';
          const contrib = (u.revenue || 0) - (u.estimated_cost || 0);
          return (
            <div key={u.user_id}
                 className="grid grid-cols-[1fr_55px_55px_70px_70px_60px_60px_60px_65px_70px] gap-1 items-center px-4 py-2.5 hover:bg-white/3 transition-colors">
              <div className="min-w-0">
                <div className="text-[11px] text-white font-medium truncate">{u.email}</div>
                <div className="flex items-center gap-1 mt-0.5">
                  <span className="text-[8px] bg-white/8 text-gray-400 px-1 rounded uppercase">{u.plan || 'free'}</span>
                  {u.subscription_status && u.subscription_status !== 'active' && (
                    <span className="text-[8px] bg-amber-500/15 text-amber-400 px-1 rounded">{u.subscription_status}</span>
                  )}
                </div>
              </div>
              <span className={`text-[8px] font-bold px-1 py-0.5 rounded text-center ${billingCls}`}>{billing}</span>
              <span className="text-[10px] text-gray-400 font-mono text-center">{u.hosting_count ?? '—'}</span>
              <span className={`text-[10px] font-mono ${cpuColor(u.avg_cpu_pct)}`}>{fmtPct(u.avg_cpu_pct)}</span>
              <span className="text-[10px] text-gray-400 font-mono">{fmtMb(u.total_ram_mb)}</span>
              <span className="text-[10px] text-emerald-400 font-mono">{fmtUsd(u.revenue)}</span>
              <span className="text-[10px] text-amber-400 font-mono">{fmtUsd(u.estimated_cost)}</span>
              <span className={`text-[10px] font-mono font-bold ${marginColor(contrib)}`}>{fmtUsd(contrib)}</span>
              <span className={`text-[10px] font-mono font-bold ${marginColor(contrib)}`}>
                {u.revenue > 0 ? `${Math.round((contrib / u.revenue) * 100)}%` : '—'}
              </span>
              <RecBadge rec={u.recommendation} />
            </div>
          );
        })}
      </div>
      <div className="px-4 py-2 border-t border-white/5 text-[8px] text-gray-600 italic">
        * Contribución = Rev. bruto − costos de recursos (CPU/RAM/disco). No descuenta el costo fijo del servidor. Para rentabilidad real ver Finance → Unit Economics.
      </div>
    </div>
  );
}

export default function ResourceUsage() {
  const [overview,  setOverview]  = useState(null);
  const [tenants,   setTenants]   = useState([]);
  const [userRows,  setUserRows]  = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);
  const [tab,       setTab]       = useState('hosting'); // 'hosting' | 'users'

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ov, ten, usr] = await Promise.all([
        getAdminResourcesOverview(),
        getAdminResourcesTenants(),
        getAdminResourcesUsers(),
      ]);
      setOverview(ov);
      setTenants(ten.items || []);
      setUserRows(usr.items || []);
    } catch {
      setError('Error cargando recursos');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  const noData = !overview?.total_hostings && !tenants.length;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-bold text-white">Resource Usage</div>
          <div className="text-[11px] text-gray-500 mt-0.5">CPU · RAM · Disco · Tráfico · Costos — actualiza cada 60s</div>
        </div>
        <button onClick={load} disabled={loading} className="p-1.5 rounded-lg hover:bg-white/5 transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 text-gray-500 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" /> {error}
        </div>
      )}

      {noData && !loading && !error && (
        <div className="bg-[#111] rounded-xl border border-white/5 p-10 text-center">
          <Cpu className="w-8 h-8 text-gray-600 mx-auto mb-3" />
          <div className="text-[12px] text-gray-500">No hay muestras todavía.</div>
          <div className="text-[10px] text-gray-600 mt-1">El scheduler recopila datos cada 60s.</div>
        </div>
      )}

      {/* Summary cards */}
      {overview && !noData && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard icon={Cpu}         label="CPU promedio"    value={fmtPct(overview.avg_cpu_pct)}  sub={`max ${fmtPct(overview.max_cpu_pct)}`}     color="bg-blue-500/10 text-blue-400"    />
          <StatCard icon={TrendingUp}  label="Hostings activos" value={overview.total_hostings ?? 0}  sub={`snapshot ${overview.snapshot_count ?? 0}`}  color="bg-amber-500/10 text-amber-400"  />
          <StatCard icon={MemoryStick} label="RAM total"       value={fmtMb(overview.total_mem_mb)}  sub={`prom ${fmtMb(overview.avg_mem_mb)}`}        color="bg-purple-500/10 text-purple-400"/>
          <StatCard icon={HardDrive}   label="RAM máx hosting" value={fmtMb(overview.max_mem_mb)}   sub="último snapshot"                              color="bg-rose-500/10 text-rose-400"   />
        </div>
      )}

      {/* Tab switcher */}
      {(tenants.length > 0 || userRows.length > 0) && (
        <>
          <div className="flex rounded-lg p-1 gap-1" style={{ background: 'rgba(255,255,255,0.05)', width: 'fit-content' }}>
            {[
              { id: 'hosting', label: 'Por Hosting', icon: Cpu    },
              { id: 'users',   label: 'Por Cliente', icon: Users  },
            ].map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className="flex items-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-semibold transition-all"
                style={tab === id
                  ? { background: 'rgba(255,255,255,0.1)', color: 'white' }
                  : { color: 'rgba(255,255,255,0.4)' }}
              >
                <Icon className="w-3 h-3" /> {label}
              </button>
            ))}
          </div>

          {tab === 'hosting' && tenants.length > 0 && <HostingTable rows={tenants} />}
          {tab === 'users'   && userRows.length > 0 && <UserTable   rows={userRows} />}
        </>
      )}
    </div>
  );
}
