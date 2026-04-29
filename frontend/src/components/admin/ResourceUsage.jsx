import React, { useEffect, useState, useCallback } from 'react';
import { Cpu, MemoryStick, RefreshCw, AlertTriangle, TrendingUp } from 'lucide-react';
import { getAdminResourcesOverview, getAdminResourcesTenants } from '../../services/api';

function fmtMb(mb) {
  if (mb == null) return '—';
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

function fmtPct(v) {
  if (v == null) return '—';
  return `${Number(v).toFixed(1)}%`;
}

function cpuColor(pct) {
  if (pct == null) return 'text-gray-500';
  if (pct >= 80) return 'text-red-400';
  if (pct >= 50) return 'text-amber-400';
  return 'text-emerald-400';
}

function memColor(mb, limitMb) {
  if (!mb || !limitMb) return 'text-gray-500';
  const ratio = mb / limitMb;
  if (ratio >= 0.85) return 'text-red-400';
  if (ratio >= 0.6)  return 'text-amber-400';
  return 'text-emerald-400';
}

function Bar({ value, max, colorClass }) {
  const pct = max ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${colorClass}`}
        style={{ width: `${pct}%`, background: 'currentColor' }}
      />
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

export default function ResourceUsage() {
  const [overview, setOverview]   = useState(null);
  const [tenants,  setTenants]    = useState([]);
  const [loading,  setLoading]    = useState(true);
  const [error,    setError]      = useState(null);
  const [noData,   setNoData]     = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ov, ten] = await Promise.all([
        getAdminResourcesOverview(),
        getAdminResourcesTenants(),
      ]);
      setOverview(ov);
      setTenants(ten.items || []);
      setNoData(!ov.total_hostings && !(ten.items?.length));
    } catch (e) {
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

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-bold text-white">Resource Usage</div>
          <div className="text-[11px] text-gray-500 mt-0.5">CPU · RAM por contenedor — actualiza cada 60s</div>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="p-1.5 rounded-lg hover:bg-white/5 transition-colors"
        >
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
          <div className="text-[10px] text-gray-600 mt-1">
            El scheduler recopila datos cada 60s. Recarga en un momento.
          </div>
        </div>
      )}

      {/* Summary cards */}
      {overview && !noData && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard icon={Cpu}         label="CPU promedio"    value={fmtPct(overview.avg_cpu_pct)}  sub={`max ${fmtPct(overview.max_cpu_pct)}`}  color="bg-blue-500/10 text-blue-400" />
          <StatCard icon={TrendingUp}  label="CPU máx"        value={fmtPct(overview.max_cpu_pct)}  sub={`${overview.total_hostings ?? 0} hostings`} color="bg-amber-500/10 text-amber-400" />
          <StatCard icon={MemoryStick} label="RAM total"       value={fmtMb(overview.total_mem_mb)}  sub={`prom ${fmtMb(overview.avg_mem_mb)}`}   color="bg-purple-500/10 text-purple-400" />
          <StatCard icon={MemoryStick} label="RAM máx hosting" value={fmtMb(overview.max_mem_mb)}   sub="último snapshot"                         color="bg-rose-500/10 text-rose-400" />
        </div>
      )}

      {/* Tenant table */}
      {tenants.length > 0 && (
        <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
          <div className="px-4 py-3 border-b border-white/5 text-[11px] font-semibold text-white flex items-center gap-2">
            <Cpu className="w-3.5 h-3.5 text-blue-400" />
            Por Hosting
            <span className="ml-auto text-[9px] text-gray-600 font-normal">{tenants.length} activos</span>
          </div>

          {/* Table header */}
          <div className="grid grid-cols-[1fr_120px_120px_80px_80px] gap-2 px-4 py-2 border-b border-white/5 text-[9px] text-gray-600 uppercase tracking-wide">
            <span>Hosting / Email</span>
            <span>CPU</span>
            <span>RAM</span>
            <span>Net RX</span>
            <span>Net TX</span>
          </div>

          <div className="divide-y divide-white/5 max-h-[500px] overflow-y-auto">
            {tenants.map((t) => (
              <div
                key={t.hosting_id}
                className="grid grid-cols-[1fr_120px_120px_80px_80px] gap-2 items-center px-4 py-2.5 hover:bg-white/3 transition-colors"
              >
                {/* Name + email */}
                <div className="min-w-0">
                  <div className="text-[11px] text-white font-medium truncate">{t.name}</div>
                  <div className="text-[9px] text-gray-500 truncate font-mono">{t.user_email}</div>
                </div>

                {/* CPU */}
                <div>
                  <span className={`text-[11px] font-mono font-bold ${cpuColor(t.cpu_pct)}`}>
                    {fmtPct(t.cpu_pct)}
                  </span>
                  <Bar value={t.cpu_pct || 0} max={100} colorClass={cpuColor(t.cpu_pct)} />
                </div>

                {/* RAM */}
                <div>
                  <span className={`text-[11px] font-mono font-bold ${memColor(t.mem_mb, t.mem_limit_mb)}`}>
                    {fmtMb(t.mem_mb)}
                  </span>
                  {t.mem_limit_mb && (
                    <Bar value={t.mem_mb || 0} max={t.mem_limit_mb} colorClass={memColor(t.mem_mb, t.mem_limit_mb)} />
                  )}
                </div>

                {/* Net */}
                <span className="text-[10px] text-gray-400 font-mono">{fmtMb(t.net_rx_mb)}</span>
                <span className="text-[10px] text-gray-400 font-mono">{fmtMb(t.net_tx_mb)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
