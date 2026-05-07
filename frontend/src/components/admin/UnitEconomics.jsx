import React, { useEffect, useState, useCallback } from 'react';
import {
  DollarSign, TrendingUp, TrendingDown, AlertTriangle, CheckCircle2,
  Users, Target, RefreshCw, ArrowUp, BarChart3,
} from 'lucide-react';
import { getUnitEconomicsOverview, getUnitEconomicsTenants } from '../../services/api';

function fmtUsd(v, decimals = 2) {
  if (v == null) return '—';
  const n = Number(v);
  return `$${n.toFixed(decimals)}`;
}

function fmtPct(v) {
  if (v == null) return '—';
  return `${Number(v).toFixed(1)}%`;
}

function marginColor(pct) {
  if (pct == null) return 'text-gray-500';
  if (pct >= 40)  return 'text-emerald-400';
  if (pct >= 20)  return 'text-amber-400';
  if (pct >= 0)   return 'text-orange-400';
  return 'text-red-400';
}

const STATUS_BADGE = {
  profitable:           { label: 'Profitable',    cls: 'bg-emerald-500/15 text-emerald-400' },
  review:               { label: 'Revisar',        cls: 'bg-amber-500/15 text-amber-400'    },
  risk:                 { label: 'Riesgo',         cls: 'bg-orange-500/15 text-orange-400'  },
  unprofitable:         { label: 'No rentable',    cls: 'bg-red-500/15 text-red-400'        },
  upgrade_recommended:  { label: 'Upgrade',        cls: 'bg-blue-500/15 text-blue-400'      },
  possible_abuse:       { label: 'Posible abuso',  cls: 'bg-red-500/15 text-red-500'        },
};

function StatusBadge({ status }) {
  const b = STATUS_BADGE[status] || { label: status, cls: 'bg-white/8 text-gray-400' };
  return (
    <span className={`text-[8px] px-1.5 py-0.5 rounded font-bold uppercase ${b.cls}`}>
      {b.label}
    </span>
  );
}

const PLAN_STYLE = {
  free:         'bg-white/8 text-gray-400',
  personal:     'bg-blue-500/20 text-blue-400',
  negocio:      'bg-purple-500/20 text-purple-400',
  agencia:      'bg-amber-500/20 text-amber-400',
  agencia_pro:  'bg-emerald-500/20 text-emerald-400',
};

function MetricCard({ label, value, sub, color, icon: Icon }) {
  return (
    <div className="bg-[#0d0d0f] rounded-xl border border-white/5 p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[9px] text-gray-500 uppercase tracking-wider">{label}</span>
        {Icon && <Icon className="w-3.5 h-3.5 text-gray-600" />}
      </div>
      <div className="text-[20px] font-bold font-mono leading-none" style={{ color }}>{value}</div>
      {sub && <div className="text-[9px] text-gray-600 mt-1">{sub}</div>}
    </div>
  );
}

function BreakEvenPlan({ plan, count }) {
  const label = { personal: 'Personal', negocio: 'Negocio', agencia: 'Agencia', agencia_pro: 'Agencia Pro' }[plan] || plan;
  const impossible = count >= 999;
  return (
    <div className="bg-[#0d0d0f] rounded-lg border border-white/5 p-3 text-center">
      <div className={`text-[9px] uppercase tracking-wider mb-1 ${PLAN_STYLE[plan] || 'text-gray-500'}`}>{label}</div>
      <div className={`text-[22px] font-bold font-mono ${impossible ? 'text-red-400' : 'text-white'}`}>
        {impossible ? '∞' : count}
      </div>
      <div className="text-[8px] text-gray-600 mt-0.5">clientes nuevos</div>
    </div>
  );
}

export default function UnitEconomics() {
  const [overview,  setOverview]  = useState(null);
  const [tenants,   setTenants]   = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);
  const [sortBy,    setSortBy]    = useState('profit_usd');
  const [sortAsc,   setSortAsc]   = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ov, ten] = await Promise.all([
        getUnitEconomicsOverview(),
        getUnitEconomicsTenants(),
      ]);
      setOverview(ov);
      setTenants(ten.items || []);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error al cargar unit economics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const sortedTenants = [...tenants].sort((a, b) => {
    const av = a[sortBy] ?? 0;
    const bv = b[sortBy] ?? 0;
    return sortAsc ? av - bv : bv - av;
  });

  const toggleSort = (col) => {
    if (sortBy === col) setSortAsc(p => !p);
    else { setSortBy(col); setSortAsc(false); }
  };

  const SortTh = ({ col, children }) => (
    <th
      className="px-3 py-2 text-left text-[9px] text-gray-600 uppercase tracking-wide font-medium cursor-pointer hover:text-gray-400 select-none"
      onClick={() => toggleSort(col)}
    >
      {children} {sortBy === col && (sortAsc ? '↑' : '↓')}
    </th>
  );

  if (loading) {
    return (
      <div className="bg-[#111] rounded-xl border border-white/8 p-8 flex items-center justify-center gap-2 text-[11px] text-gray-600">
        <RefreshCw className="w-4 h-4 animate-spin" />
        Cargando unit economics...
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-[#111] rounded-xl border border-red-500/20 p-6 text-center">
        <AlertTriangle className="w-5 h-5 text-red-400 mx-auto mb-2" />
        <p className="text-[11px] text-red-400">{error}</p>
        <button onClick={load} className="mt-3 text-[10px] text-gray-500 hover:text-white transition-colors">
          Reintentar
        </button>
      </div>
    );
  }

  if (!overview) return null;

  const profitColor = overview.estimated_profit >= 0 ? '#22c55e' : '#ef4444';
  const marginPctColor = overview.gross_margin_percent >= 40 ? '#22c55e'
    : overview.gross_margin_percent >= 20 ? '#f59e0b'
    : '#ef4444';

  return (
    <div className="flex flex-col gap-4">
      {/* ── Profitability banner ── */}
      <div className={`rounded-xl border px-5 py-3 flex items-center gap-3 ${
        overview.am_i_profitable
          ? 'bg-emerald-500/8 border-emerald-500/20'
          : 'bg-red-500/8 border-red-500/20'
      }`}>
        {overview.am_i_profitable
          ? <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          : <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />}
        <div>
          <span className={`text-[11px] font-semibold ${overview.am_i_profitable ? 'text-emerald-400' : 'text-red-400'}`}>
            {overview.am_i_profitable ? 'El negocio es rentable este mes' : 'El negocio no es rentable este mes'}
          </span>
          {!overview.am_i_profitable && overview.break_even_gap_usd > 0 && (
            <span className="text-[10px] text-gray-500 ml-2">
              — faltan {fmtUsd(overview.break_even_gap_usd)} para break-even
            </span>
          )}
        </div>
        <button onClick={load} className="ml-auto text-gray-600 hover:text-white transition-colors">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* ── Key metrics ── */}
      <div className="grid grid-cols-3 gap-3 lg:grid-cols-6">
        <MetricCard label="MRR Bruto"   value={fmtUsd(overview.mrr_gross)}            color="#00aaff" icon={DollarSign} />
        <MetricCard label="MRR Neto"    value={fmtUsd(overview.mrr_net)}              color="#60a5fa" icon={DollarSign} sub="tras comisiones de pago" />
        <MetricCard label="Costo Fijo"  value={fmtUsd(overview.monthly_fixed_cost)}   color="#f59e0b" icon={Target} />
        <MetricCard label="Costo Var."  value={fmtUsd(overview.monthly_variable_cost)} color="#fb923c" icon={Target} sub="backups + extras" />
        <MetricCard label="Ganancia"    value={fmtUsd(overview.estimated_profit)}     color={profitColor} icon={overview.estimated_profit >= 0 ? TrendingUp : TrendingDown} />
        <MetricCard label="Margen"      value={fmtPct(overview.gross_margin_percent)} color={marginPctColor} icon={BarChart3} />
      </div>

      {/* ── Customer counts ── */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-[#0d0d0f] rounded-xl border border-white/5 p-4 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/15 flex items-center justify-center">
            <Users className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <div className="text-[20px] font-bold text-emerald-400">{overview.profitable_customers_count}</div>
            <div className="text-[9px] text-gray-500">clientes rentables</div>
          </div>
          <div className="ml-auto w-9 h-9 rounded-lg bg-red-500/15 flex items-center justify-center">
            <Users className="w-4 h-4 text-red-400" />
          </div>
          <div>
            <div className="text-[20px] font-bold text-red-400">{overview.unprofitable_customers_count}</div>
            <div className="text-[9px] text-gray-500">no rentables</div>
          </div>
        </div>
        <div className="bg-[#0d0d0f] rounded-xl border border-white/5 p-4">
          <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">Break-even gap</div>
          <div className="text-[20px] font-bold font-mono text-white">{fmtUsd(overview.break_even_gap_usd)}</div>
          <div className="text-[9px] text-gray-600 mt-0.5">falta para cubrir costos totales</div>
        </div>
      </div>

      {/* ── Break-even by plan ── */}
      {overview.break_even_gap_usd > 0 && (
        <div className="bg-[#111] rounded-xl border border-white/8 p-4">
          <div className="text-[11px] font-semibold text-white mb-3 flex items-center gap-2">
            <ArrowUp className="w-3.5 h-3.5 text-blue-400" />
            Clientes nuevos necesarios para break-even
          </div>
          <div className="grid grid-cols-4 gap-3">
            {Object.entries(overview.customers_needed_for_break_even_by_plan).map(([plan, count]) => (
              <BreakEvenPlan key={plan} plan={plan} count={count} />
            ))}
          </div>
        </div>
      )}

      {/* ── Tenant breakdown table ── */}
      <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
        <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2">
          <DollarSign className="w-3.5 h-3.5 text-[#00ff88]" />
          <span className="text-[11px] font-semibold text-white">Rentabilidad por Cliente</span>
          <span className="ml-auto text-[9px] text-gray-600">{tenants.length} tenants</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/5">
                <th className="px-3 py-2 text-left text-[9px] text-gray-600 uppercase tracking-wide font-medium">Cliente</th>
                <SortTh col="gross_monthly_revenue">Rev. bruto</SortTh>
                <SortTh col="net_monthly_revenue">Rev. neto</SortTh>
                <SortTh col="total_cost_usd">Costo</SortTh>
                <SortTh col="profit_usd">Profit</SortTh>
                <SortTh col="margin_percent">Margen</SortTh>
                <th className="px-3 py-2 text-left text-[9px] text-gray-600 uppercase tracking-wide font-medium">Estado</th>
              </tr>
            </thead>
            <tbody>
              {sortedTenants.map((t) => {
                const rowBg = t.status === 'unprofitable' ? 'bg-red-500/4 border-b border-red-500/8'
                  : t.status === 'risk' ? 'bg-orange-500/4 border-b border-orange-500/8'
                  : 'border-b border-white/3';
                return (
                  <tr key={t.user_id} className={`${rowBg} hover:bg-white/3 transition-colors`}>
                    <td className="px-3 py-2.5">
                      <div className="text-[10px] text-white truncate max-w-[180px]">{t.email}</div>
                      <div className="flex items-center gap-1 mt-0.5">
                        <span className={`text-[8px] px-1 rounded uppercase font-bold ${PLAN_STYLE[t.plan] || 'bg-white/5 text-gray-500'}`}>
                          {t.plan}
                        </span>
                        <span className="text-[8px] text-gray-600">{t.hosting_count} site{t.hosting_count !== 1 ? 's' : ''}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-[10px] font-mono text-blue-400">{fmtUsd(t.gross_monthly_revenue)}</td>
                    <td className="px-3 py-2.5 text-[10px] font-mono text-blue-300">{fmtUsd(t.net_monthly_revenue)}</td>
                    <td className="px-3 py-2.5 text-[10px] font-mono text-amber-400">{fmtUsd(t.total_cost_usd)}</td>
                    <td className={`px-3 py-2.5 text-[10px] font-mono font-bold ${t.profit_usd >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {fmtUsd(t.profit_usd)}
                    </td>
                    <td className={`px-3 py-2.5 text-[10px] font-mono font-bold ${marginColor(t.margin_percent)}`}>
                      {fmtPct(t.margin_percent)}
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={t.status} />
                      {t.reason && (
                        <div className="text-[8px] text-gray-600 mt-0.5 truncate max-w-[120px]">{t.reason}</div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
