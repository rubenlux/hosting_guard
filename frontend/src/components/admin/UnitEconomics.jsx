import React, { useEffect, useState, useCallback } from 'react';
import {
  DollarSign, TrendingUp, TrendingDown, AlertTriangle, CheckCircle2,
  Users, Target, RefreshCw, ArrowUp, BarChart3, Cpu, HardDrive,
  Crown, Zap, Trophy, Flame,
} from 'lucide-react';
import { getUnitEconomicsOverview, getUnitEconomicsTenants } from '../../services/api';

// ── formatters ────────────────────────────────────────────────────────────────

function fmtUsd(v, decimals = 2) {
  if (v == null) return '—';
  return `$${Number(v).toFixed(decimals)}`;
}

function fmtPct(v) {
  if (v == null) return '—';
  return `${Number(v).toFixed(1)}%`;
}

function profitColor(v) {
  if (v == null) return 'text-gray-500';
  return v >= 0 ? 'text-emerald-400' : 'text-red-400';
}

function marginColor(pct) {
  if (pct == null) return 'text-gray-500';
  if (pct >= 40)  return 'text-emerald-400';
  if (pct >= 20)  return 'text-amber-400';
  if (pct >= 0)   return 'text-orange-400';
  return 'text-red-400';
}

// ── constants ─────────────────────────────────────────────────────────────────

const PLAN_META = {
  free:               { cls: 'bg-white/8 text-gray-400',          label: 'Free' },
  personal:           { cls: 'bg-blue-500/20 text-blue-400',      label: 'Personal' },
  negocio:            { cls: 'bg-purple-500/20 text-purple-400',  label: 'Negocio' },
  agencia:            { cls: 'bg-amber-500/20 text-amber-400',    label: 'Agencia' },
  agencia_pro:        { cls: 'bg-emerald-500/20 text-emerald-400',label: 'Agencia Pro' },
  enterprise_annual:  { cls: 'bg-rose-500/20 text-rose-400',      label: 'Enterprise' },
  enterprise_monthly: { cls: 'bg-rose-500/20 text-rose-400',      label: 'Enterprise' },
};

const STATUS_BADGE = {
  profitable:          { label: 'Rentable',     cls: 'bg-emerald-500/15 text-emerald-400' },
  review:              { label: 'Revisar',      cls: 'bg-amber-500/15  text-amber-400'    },
  risk:                { label: 'Riesgo',       cls: 'bg-orange-500/15 text-orange-400'   },
  unprofitable:        { label: 'No rentable',  cls: 'bg-red-500/15    text-red-400'      },
  upgrade_recommended: { label: 'Upgrade',      cls: 'bg-blue-500/15   text-blue-400'     },
  possible_abuse:      { label: 'Posible abuso',cls: 'bg-red-500/15    text-red-500'      },
};

const BREAK_EVEN_PLANS = [
  'personal', 'negocio', 'agencia', 'agencia_pro', 'enterprise_annual',
];

// ── small components ──────────────────────────────────────────────────────────

function PlanBadge({ plan }) {
  const m = PLAN_META[plan] || { cls: 'bg-white/5 text-gray-400', label: plan };
  return <span className={`text-[8px] px-1.5 py-0.5 rounded font-bold uppercase ${m.cls}`}>{m.label}</span>;
}

function StatusBadge({ status }) {
  const b = STATUS_BADGE[status] || { label: status, cls: 'bg-white/8 text-gray-400' };
  return <span className={`text-[8px] px-1.5 py-0.5 rounded font-bold uppercase ${b.cls}`}>{b.label}</span>;
}

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

function BreakEvenCard({ plan, count }) {
  const m = PLAN_META[plan] || { cls: 'text-gray-500', label: plan };
  const impossible = count >= 999;
  return (
    <div className="bg-[#0d0d0f] rounded-lg border border-white/5 p-3 text-center">
      <div className={`text-[9px] uppercase tracking-wider mb-1 font-bold ${m.cls.split(' ')[1] || 'text-gray-400'}`}>
        {m.label}
      </div>
      <div className={`text-[22px] font-bold font-mono ${impossible ? 'text-red-400' : 'text-white'}`}>
        {impossible ? '∞' : count}
      </div>
      <div className="text-[8px] text-gray-600 mt-0.5">nuevos clientes</div>
    </div>
  );
}

function SortableHeader({ col, label, sortBy, sortAsc, onSort }) {
  const active = sortBy === col;
  return (
    <th
      className={`px-3 py-2 text-left text-[9px] uppercase tracking-wide font-medium cursor-pointer select-none whitespace-nowrap
        ${active ? 'text-white' : 'text-gray-600 hover:text-gray-400'}`}
      onClick={() => onSort(col)}
    >
      {label} {active && (sortAsc ? '↑' : '↓')}
    </th>
  );
}

function ClientCell({ email, plan, hosting_count }) {
  return (
    <td className="px-3 py-2.5 min-w-[160px]">
      <div className="text-[10px] text-white truncate max-w-[200px]">{email}</div>
      <div className="flex items-center gap-1 mt-0.5">
        <PlanBadge plan={plan} />
        <span className="text-[8px] text-gray-600">{hosting_count} site{hosting_count !== 1 ? 's' : ''}</span>
      </div>
    </td>
  );
}

// ── tab: profitability table ──────────────────────────────────────────────────

function ProfitabilityTable({ tenants }) {
  const [sortBy,  setSortBy]  = useState('profit_usd');
  const [sortAsc, setSortAsc] = useState(false);

  const onSort = (col) => {
    if (sortBy === col) setSortAsc(p => !p);
    else { setSortBy(col); setSortAsc(false); }
  };

  const sorted = [...tenants].sort((a, b) => {
    const av = a[sortBy] ?? 0, bv = b[sortBy] ?? 0;
    return sortAsc ? av - bv : bv - av;
  });

  const th = (col, label) => (
    <SortableHeader key={col} col={col} label={label} sortBy={sortBy} sortAsc={sortAsc} onSort={onSort} />
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-white/5">
            <th className="px-3 py-2 text-left text-[9px] text-gray-600 uppercase tracking-wide">Cliente</th>
            {th('gross_monthly_revenue', 'Rev. bruto')}
            {th('payment_fee_monthly', 'Fee pago')}
            {th('net_monthly_revenue', 'Rev. neto')}
            {th('total_cost_usd', 'Costo total')}
            {th('profit_usd', 'Profit')}
            {th('margin_percent', 'Margen')}
            <th className="px-3 py-2 text-left text-[9px] text-gray-600 uppercase tracking-wide">Estado</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((t) => {
            const rowCls = t.status === 'unprofitable'
              ? 'bg-red-500/4 border-b border-red-500/8'
              : t.status === 'risk'
              ? 'bg-orange-500/4 border-b border-orange-500/8'
              : 'border-b border-white/3';
            return (
              <tr key={t.user_id} className={`${rowCls} hover:bg-white/3 transition-colors`}>
                <ClientCell email={t.email} plan={t.plan} hosting_count={t.hosting_count} />
                <td className="px-3 py-2.5 text-[10px] font-mono text-blue-400">{fmtUsd(t.gross_monthly_revenue)}</td>
                <td className="px-3 py-2.5 text-[10px] font-mono text-red-400 opacity-70">{fmtUsd(t.payment_fee_monthly)}</td>
                <td className="px-3 py-2.5 text-[10px] font-mono text-blue-300">{fmtUsd(t.net_monthly_revenue)}</td>
                <td className="px-3 py-2.5 text-[10px] font-mono text-amber-400">{fmtUsd(t.total_cost_usd)}</td>
                <td className={`px-3 py-2.5 text-[10px] font-mono font-bold ${profitColor(t.profit_usd)}`}>{fmtUsd(t.profit_usd)}</td>
                <td className={`px-3 py-2.5 text-[10px] font-mono font-bold ${marginColor(t.margin_percent)}`}>{fmtPct(t.margin_percent)}</td>
                <td className="px-3 py-2.5">
                  <StatusBadge status={t.status} />
                  {t.reason && (
                    <div className="text-[8px] text-gray-600 mt-0.5 max-w-[140px] truncate">{t.reason}</div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── tab: cost breakdown table ─────────────────────────────────────────────────

function CostTable({ tenants }) {
  const [sortBy,  setSortBy]  = useState('total_cost_usd');
  const [sortAsc, setSortAsc] = useState(false);

  const onSort = (col) => {
    if (sortBy === col) setSortAsc(p => !p);
    else { setSortBy(col); setSortAsc(false); }
  };

  const sorted = [...tenants].sort((a, b) => {
    const av = a[sortBy] ?? 0, bv = b[sortBy] ?? 0;
    return sortAsc ? av - bv : bv - av;
  });

  const th = (col, label) => (
    <SortableHeader key={col} col={col} label={label} sortBy={sortBy} sortAsc={sortAsc} onSort={onSort} />
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-white/5">
            <th className="px-3 py-2 text-left text-[9px] text-gray-600 uppercase tracking-wide">Cliente</th>
            {th('cpu_cost_usd',      'CPU')}
            {th('ram_cost_usd',      'RAM')}
            {th('disk_cost_usd',     'Disk')}
            {th('backup_cost_usd',   'Backup')}
            {th('overhead_cost_usd', 'Overhead')}
            {th('ai_cost_usd',       'IA')}
            {th('support_cost_usd',  'Soporte')}
            {th('payment_fee_monthly','Fee pago')}
            {th('total_cost_usd',    'Total')}
          </tr>
        </thead>
        <tbody>
          {sorted.map((t) => (
            <tr key={t.user_id} className="border-b border-white/3 hover:bg-white/3 transition-colors">
              <ClientCell email={t.email} plan={t.plan} hosting_count={t.hosting_count} />
              <td className="px-3 py-2.5 text-[10px] font-mono text-gray-400">{fmtUsd(t.cpu_cost_usd, 3)}</td>
              <td className="px-3 py-2.5 text-[10px] font-mono text-gray-400">{fmtUsd(t.ram_cost_usd, 3)}</td>
              <td className="px-3 py-2.5 text-[10px] font-mono text-gray-400">{fmtUsd(t.disk_cost_usd, 3)}</td>
              <td className="px-3 py-2.5 text-[10px] font-mono text-gray-400">{fmtUsd(t.backup_cost_usd, 3)}</td>
              <td className="px-3 py-2.5 text-[10px] font-mono text-gray-400">{fmtUsd(t.overhead_cost_usd, 3)}</td>
              <td className="px-3 py-2.5 text-[10px] font-mono text-gray-400">{fmtUsd(t.ai_cost_usd, 3)}</td>
              <td className="px-3 py-2.5 text-[10px] font-mono text-gray-400">{fmtUsd(t.support_cost_usd, 3)}</td>
              <td className="px-3 py-2.5 text-[10px] font-mono text-red-400 opacity-70">{fmtUsd(t.payment_fee_monthly, 3)}</td>
              <td className="px-3 py-2.5 text-[10px] font-mono font-bold text-amber-400">{fmtUsd(t.total_cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── tab: rankings ─────────────────────────────────────────────────────────────

function RankingList({ title, icon: Icon, iconCls, items, valueKey, valueLabel, valueColor }) {
  return (
    <div className="bg-[#0d0d0f] rounded-xl border border-white/5 overflow-hidden">
      <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2">
        <Icon className={`w-3.5 h-3.5 ${iconCls}`} />
        <span className="text-[11px] font-semibold text-white">{title}</span>
      </div>
      <div className="divide-y divide-white/5">
        {items.map((r, i) => (
          <div key={r.user_id} className="px-4 py-2.5 flex items-center gap-3 hover:bg-white/3 transition-colors">
            <span className="text-[9px] text-gray-600 font-mono w-4 shrink-0">{i + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="text-[10px] text-white truncate">{r.email}</div>
              <div className="flex items-center gap-1 mt-0.5">
                <PlanBadge plan={r.plan} />
                <span className="text-[8px] text-gray-600">{r.hosting_count} site{r.hosting_count !== 1 ? 's' : ''}</span>
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className={`text-[12px] font-mono font-bold ${valueColor(r[valueKey])}`}>{fmtUsd(r[valueKey])}</div>
              <div className="text-[8px] text-gray-600">{valueLabel}</div>
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <div className="px-4 py-6 text-center text-[10px] text-gray-600">Sin datos</div>
        )}
      </div>
    </div>
  );
}

function RankingsTab({ overview }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <RankingList
        title="Clientes más rentables"
        icon={Trophy}
        iconCls="text-amber-400"
        items={overview.top_profitable_customers || []}
        valueKey="profit_usd"
        valueLabel="profit/mes"
        valueColor={(v) => v >= 0 ? 'text-emerald-400' : 'text-red-400'}
      />
      <RankingList
        title="Mayor costo de infraestructura"
        icon={Flame}
        iconCls="text-red-400"
        items={overview.top_expensive_customers || []}
        valueKey="total_cost_usd"
        valueLabel="costo/mes"
        valueColor={() => 'text-amber-400'}
      />
    </div>
  );
}

// ── tab: upgrade recommendations ─────────────────────────────────────────────

function UpgradeTab({ overview }) {
  const items = overview.upgrade_recommended_customers || [];
  if (items.length === 0) {
    return (
      <div className="bg-[#0d0d0f] rounded-xl border border-white/5 p-8 text-center">
        <CheckCircle2 className="w-6 h-6 text-emerald-400 mx-auto mb-2" />
        <div className="text-[11px] text-gray-500">Ningún cliente supera los límites de su plan.</div>
      </div>
    );
  }
  return (
    <div className="bg-[#0d0d0f] rounded-xl border border-white/5 overflow-hidden">
      <div className="px-4 py-3 border-b border-white/5 flex items-center gap-2">
        <ArrowUp className="w-3.5 h-3.5 text-blue-400" />
        <span className="text-[11px] font-semibold text-white">Clientes que deberían cambiar de plan</span>
        <span className="ml-auto text-[9px] bg-blue-500/15 text-blue-400 px-2 py-0.5 rounded font-bold">{items.length}</span>
      </div>
      <div className="divide-y divide-white/5">
        {items.map((r) => (
          <div key={r.user_id} className="px-4 py-3 flex items-start gap-3 hover:bg-white/3 transition-colors">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] text-white font-medium truncate max-w-[220px]">{r.email}</span>
                <PlanBadge plan={r.plan} />
                <StatusBadge status={r.recommendation} />
              </div>
              <div className="text-[9px] text-gray-500 mt-1">{r.reason}</div>
            </div>
            <div className="text-right shrink-0">
              <div className={`text-[11px] font-mono font-bold ${profitColor(r.profit_usd)}`}>{fmtUsd(r.profit_usd)}</div>
              <div className="text-[8px] text-gray-600">profit/mes</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

const TABS = [
  { id: 'profit',   label: 'Rentabilidad',   icon: DollarSign },
  { id: 'costs',    label: 'Desglose Costos', icon: BarChart3 },
  { id: 'rankings', label: 'Rankings',        icon: Trophy },
  { id: 'upgrade',  label: 'Upgrade',         icon: ArrowUp },
];

export default function UnitEconomics() {
  const [overview, setOverview] = useState(null);
  const [tenants,  setTenants]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState(null);
  const [tab,      setTab]      = useState('profit');

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

  if (loading) return (
    <div className="bg-[#111] rounded-xl border border-white/8 p-8 flex items-center justify-center gap-2 text-[11px] text-gray-600">
      <RefreshCw className="w-4 h-4 animate-spin" /> Cargando unit economics...
    </div>
  );

  if (error) return (
    <div className="bg-[#111] rounded-xl border border-red-500/20 p-6 text-center">
      <AlertTriangle className="w-5 h-5 text-red-400 mx-auto mb-2" />
      <p className="text-[11px] text-red-400">{error}</p>
      <button onClick={load} className="mt-3 text-[10px] text-gray-500 hover:text-white transition-colors">Reintentar</button>
    </div>
  );

  if (!overview) return null;

  const profitable     = overview.am_i_profitable;
  const profitHex      = overview.estimated_profit >= 0 ? '#22c55e' : '#ef4444';
  const marginHex      = overview.gross_margin_percent >= 40 ? '#22c55e'
    : overview.gross_margin_percent >= 20 ? '#f59e0b' : '#ef4444';

  return (
    <div className="flex flex-col gap-4">

      {/* ── 1. Profitability banner ── */}
      <div className={`rounded-xl border px-5 py-3 flex items-center gap-3 ${
        profitable ? 'bg-emerald-500/8 border-emerald-500/20' : 'bg-red-500/8 border-red-500/20'
      }`}>
        {profitable
          ? <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          : <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />}
        <div>
          <span className={`text-[11px] font-semibold ${profitable ? 'text-emerald-400' : 'text-red-400'}`}>
            {profitable ? 'El negocio es rentable este mes' : 'El negocio no es rentable este mes'}
          </span>
          {!profitable && overview.break_even_gap_usd > 0 && (
            <span className="text-[10px] text-gray-500 ml-2">
              — faltan {fmtUsd(overview.break_even_gap_usd)} para break-even
            </span>
          )}
        </div>
        <button onClick={load} className="ml-auto text-gray-600 hover:text-white transition-colors">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* ── 2. Key metrics ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard label="MRR Bruto"    value={fmtUsd(overview.mrr_gross)}             color="#60a5fa" icon={DollarSign} />
        <MetricCard label="MRR Neto"     value={fmtUsd(overview.mrr_net)}               color="#93c5fd" icon={DollarSign} sub="tras fee de pago" />
        <MetricCard label="Costo Fijo"   value={fmtUsd(overview.monthly_fixed_cost)}    color="#f59e0b" icon={Target}     sub="servidor" />
        <MetricCard label="Costo Var."   value={fmtUsd(overview.monthly_variable_cost)} color="#fb923c" icon={Cpu}        sub="backups + extras" />
        <MetricCard label="Profit/mes"   value={fmtUsd(overview.estimated_profit)}      color={profitHex} icon={profitable ? TrendingUp : TrendingDown} />
        <MetricCard label="Margen"       value={fmtPct(overview.gross_margin_percent)}  color={marginHex} icon={BarChart3} />
      </div>

      {/* ── 3. Customer count + break-even gap ── */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-[#0d0d0f] rounded-xl border border-white/5 p-4 flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/15 flex items-center justify-center">
              <Users className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <div className="text-[18px] font-bold text-emerald-400">{overview.profitable_customers_count}</div>
              <div className="text-[9px] text-gray-500">rentables</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-red-500/15 flex items-center justify-center">
              <Users className="w-4 h-4 text-red-400" />
            </div>
            <div>
              <div className="text-[18px] font-bold text-red-400">{overview.unprofitable_customers_count}</div>
              <div className="text-[9px] text-gray-500">no rentables</div>
            </div>
          </div>
          <div className="ml-auto text-right">
            <div className="text-[10px] text-gray-600">Total</div>
            <div className="text-[18px] font-bold text-white">{overview.total_clients}</div>
          </div>
        </div>
        <div className="bg-[#0d0d0f] rounded-xl border border-white/5 p-4">
          <div className="text-[9px] text-gray-500 uppercase tracking-wider mb-1">Break-even gap</div>
          <div className={`text-[20px] font-bold font-mono ${overview.break_even_gap_usd > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
            {overview.break_even_gap_usd > 0 ? fmtUsd(overview.break_even_gap_usd) : 'Cubierto'}
          </div>
          <div className="text-[9px] text-gray-600 mt-0.5">
            {overview.break_even_gap_usd > 0 ? 'ingreso neto adicional necesario' : 'costos fijos cubiertos por MRR'}
          </div>
        </div>
      </div>

      {/* ── 3b. Customers needed per plan to break even ── */}
      {overview.break_even_gap_usd > 0 && (
        <div className="bg-[#111] rounded-xl border border-white/8 p-4">
          <div className="text-[11px] font-semibold text-white mb-3 flex items-center gap-2">
            <ArrowUp className="w-3.5 h-3.5 text-blue-400" />
            Clientes nuevos para cubrir el break-even
          </div>
          <div className="grid grid-cols-5 gap-2">
            {BREAK_EVEN_PLANS.map((plan) => (
              <BreakEvenCard
                key={plan}
                plan={plan}
                count={overview.customers_needed_for_break_even_by_plan?.[plan] ?? 999}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── 4/5/6/7/8. Tabbed detail ── */}
      <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
        {/* Tab header */}
        <div className="flex border-b border-white/5 overflow-x-auto">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 px-4 py-3 text-[10px] font-semibold whitespace-nowrap transition-all border-b-2 ${
                tab === id
                  ? 'text-white border-blue-500 bg-white/3'
                  : 'text-gray-500 border-transparent hover:text-gray-300 hover:bg-white/2'
              }`}
            >
              <Icon className="w-3 h-3" />
              {label}
              {id === 'upgrade' && (overview.upgrade_recommended_customers?.length ?? 0) > 0 && (
                <span className="ml-1 bg-blue-500/20 text-blue-400 text-[8px] px-1.5 py-0.5 rounded font-bold">
                  {overview.upgrade_recommended_customers.length}
                </span>
              )}
            </button>
          ))}
          <div className="ml-auto px-3 py-3">
            <span className="text-[9px] text-gray-600">{tenants.length} clientes</span>
          </div>
        </div>

        {/* Tab content */}
        <div>
          {tab === 'profit'   && <ProfitabilityTable tenants={tenants} />}
          {tab === 'costs'    && <CostTable tenants={tenants} />}
          {tab === 'rankings' && <div className="p-4"><RankingsTab overview={overview} /></div>}
          {tab === 'upgrade'  && <div className="p-4"><UpgradeTab overview={overview} /></div>}
        </div>
      </div>
    </div>
  );
}
