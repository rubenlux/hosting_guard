import React, { useEffect, useState, useCallback } from 'react';
import {
  ShieldAlert, ShieldCheck, ShieldOff, AlertTriangle,
  RefreshCw, Filter, ChevronDown, CheckCircle2, XCircle,
  Globe, Upload, Webhook, Users, Lock, Zap, BarChart3,
  Eye, Bot, X, Loader2,
} from 'lucide-react';
import {
  getSecuritySummary, getSecurityEvents,
  resolveSecurityEvent, getSecurityEventAISummary,
} from '../../services/api';

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmtDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

const SEV_STYLE = {
  critical: { pill: 'bg-red-500/15 text-red-400 border border-red-500/30',  dot: 'bg-red-400' },
  warning:  { pill: 'bg-amber-500/15 text-amber-400 border border-amber-500/30', dot: 'bg-amber-400' },
  info:     { pill: 'bg-blue-500/10 text-blue-400 border border-blue-500/20',   dot: 'bg-blue-400' },
};

const CAT_ICON = {
  auth:            <Lock className="w-3.5 h-3.5 text-blue-400" />,
  wordpress_auth:  <Globe className="w-3.5 h-3.5 text-orange-400" />,
  upload:          <Upload className="w-3.5 h-3.5 text-purple-400" />,
  webhook:         <Zap className="w-3.5 h-3.5 text-amber-400" />,
  api:             <BarChart3 className="w-3.5 h-3.5 text-cyan-400" />,
  ownership:       <Users className="w-3.5 h-3.5 text-pink-400" />,
  traffic_anomaly: <Eye className="w-3.5 h-3.5 text-emerald-400" />,
  resource_abuse:  <Zap className="w-3.5 h-3.5 text-red-400" />,
  ddos:            <ShieldAlert className="w-3.5 h-3.5 text-red-500" />,
  scanner:         <Bot className="w-3.5 h-3.5 text-gray-400" />,
};

const SEVERITIES  = ['', 'critical', 'warning', 'info'];
const CATEGORIES  = ['', 'auth', 'wordpress_auth', 'upload', 'webhook', 'api', 'ownership', 'traffic_anomaly', 'resource_abuse', 'scanner', 'ddos'];
const STATUSES    = ['', 'open', 'resolved'];

const THREAT_CONFIG = {
  normal:       { icon: ShieldCheck, color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20', label: 'Sistema normal' },
  warning:      { icon: ShieldAlert, color: 'text-amber-400',   bg: 'bg-amber-500/10 border-amber-500/20',    label: 'Advertencias activas' },
  under_attack: { icon: ShieldOff,   color: 'text-red-400',     bg: 'bg-red-500/10 border-red-500/25',        label: 'BAJO ATAQUE' },
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color = 'text-white', icon }) {
  return (
    <div className="bg-[#111] rounded-xl border border-white/8 p-4 flex flex-col gap-1">
      <div className="flex items-center gap-2 mb-1">
        {icon && <span className={color}>{icon}</span>}
        <span className="text-[10px] text-gray-500 uppercase tracking-wide">{label}</span>
      </div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      {sub && <div className="text-[9px] text-gray-600">{sub}</div>}
    </div>
  );
}

function AISummaryPanel({ eventId, onClose }) {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  useEffect(() => {
    getSecurityEventAISummary(eventId)
      .then(r => setData(r))
      .catch(e => setError(e?.response?.data?.detail || 'Error generando resumen'))
      .finally(() => setLoading(false));
  }, [eventId]);

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-[#111] border border-white/10 rounded-xl w-full max-w-lg max-h-[80vh] overflow-y-auto">
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
          <div className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-[#00ff88]" />
            <span className="text-[11px] font-semibold text-white">Resumen de incidente (IA)</span>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-white/5 rounded transition-colors">
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>
        <div className="p-4">
          {loading && (
            <div className="flex items-center gap-2 text-[11px] text-gray-500 py-8 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" /> Analizando...
            </div>
          )}
          {error && <div className="text-[11px] text-red-400">{error}</div>}
          {data && !data.ok && (
            <div className="text-[11px] text-gray-500">{data.reason}</div>
          )}
          {data?.ok && data.summary && (
            <div className="space-y-3 text-[11px]">
              {[
                ['Causa probable',       data.summary.causa_probable],
                ['Evidencia',            data.summary.evidencia],
                ['Impacto',              data.summary.impacto],
              ].filter(([, v]) => v).map(([k, v]) => (
                <div key={k}>
                  <div className="text-[9px] text-gray-600 uppercase mb-0.5">{k}</div>
                  <div className="text-gray-300 leading-relaxed">{v}</div>
                </div>
              ))}
              {data.summary.acciones_recomendadas?.length > 0 && (
                <div>
                  <div className="text-[9px] text-gray-600 uppercase mb-1">Acciones recomendadas</div>
                  <ul className="space-y-1 list-disc list-inside text-gray-300">
                    {data.summary.acciones_recomendadas.map((a, i) => <li key={i}>{a}</li>)}
                  </ul>
                </div>
              )}
              <div className="flex gap-3 mt-2 pt-2 border-t border-white/5">
                <span className="flex items-center gap-1 text-[9px]">
                  {data.summary.notificar_cliente
                    ? <><CheckCircle2 className="w-3 h-3 text-amber-400" /> Notificar cliente</>
                    : <><XCircle className="w-3 h-3 text-gray-600" /> No notificar cliente</>}
                </span>
                <span className="flex items-center gap-1 text-[9px]">
                  {data.summary.aplicar_proteccion
                    ? <><ShieldAlert className="w-3 h-3 text-orange-400" /> Activar protección</>
                    : <><ShieldCheck className="w-3 h-3 text-emerald-400" /> No se requiere protección</>}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EventRow({ e, onResolved }) {
  const [expanded, setExpanded]   = useState(false);
  const [resolving, setResolving] = useState(false);
  const [aiEvent, setAiEvent]     = useState(null);

  const sev  = SEV_STYLE[e.severity] || SEV_STYLE.info;
  const icon = CAT_ICON[e.category];

  const handleResolve = async (ev) => {
    ev.stopPropagation();
    setResolving(true);
    try {
      await resolveSecurityEvent(e.event_id);
      onResolved(e.event_id);
    } finally {
      setResolving(false);
    }
  };

  return (
    <>
      {aiEvent && <AISummaryPanel eventId={aiEvent} onClose={() => setAiEvent(null)} />}
      <div className="border-b border-white/5 last:border-0">
        <div
          className="flex items-start gap-3 px-4 py-3 hover:bg-white/[0.02] cursor-pointer transition-colors"
          onClick={() => setExpanded(x => !x)}
        >
          {/* severity dot */}
          <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${sev.dot} ${e.severity === 'critical' ? 'animate-pulse' : ''}`} />

          {/* icon + content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              {icon && <span>{icon}</span>}
              <span className="text-[11px] text-white font-medium">{e.title}</span>
              <span className={`text-[8px] font-bold uppercase px-1.5 py-0.5 rounded ${sev.pill}`}>
                {e.severity}
              </span>
              {e.count > 1 && (
                <span className="text-[8px] bg-white/5 text-gray-500 px-1.5 py-0.5 rounded">
                  ×{e.count}
                </span>
              )}
              {e.status === 'resolved' && (
                <span className="text-[8px] bg-emerald-500/10 text-emerald-500 px-1.5 py-0.5 rounded">
                  resuelto
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-0.5 flex-wrap">
              <span className="text-[9px] text-gray-600 font-mono">{e.event_type}</span>
              {e.hosting_name && (
                <span className="text-[9px] text-gray-500">{e.hosting_name}</span>
              )}
              {e.user_email && (
                <span className="text-[9px] text-gray-500 truncate">{e.user_email}</span>
              )}
              {e.ip && (
                <span className="text-[9px] text-gray-600 font-mono">{e.ip}</span>
              )}
            </div>
          </div>

          {/* timestamp + actions */}
          <div className="flex flex-col items-end gap-1.5 shrink-0">
            <span className="text-[9px] text-gray-600">{fmtDate(e.last_seen || e.created_at)}</span>
            <div className="flex gap-1">
              <button
                onClick={(ev) => { ev.stopPropagation(); setAiEvent(e.event_id); }}
                className="p-1 rounded hover:bg-white/5 transition-colors"
                title="Resumen IA"
              >
                <Bot className="w-3 h-3 text-gray-600 hover:text-[#00ff88]" />
              </button>
              {e.status === 'open' && (
                <button
                  onClick={handleResolve}
                  disabled={resolving}
                  className="p-1 rounded hover:bg-emerald-500/10 transition-colors"
                  title="Marcar como resuelto"
                >
                  {resolving
                    ? <Loader2 className="w-3 h-3 text-gray-500 animate-spin" />
                    : <CheckCircle2 className="w-3 h-3 text-gray-600 hover:text-emerald-400" />}
                </button>
              )}
              <ChevronDown className={`w-3 h-3 text-gray-600 transition-transform mt-0.5 ${expanded ? 'rotate-180' : ''}`} />
            </div>
          </div>
        </div>

        {/* Expanded detail */}
        {expanded && (
          <div className="ml-8 px-4 pb-3 space-y-2">
            {e.message && (
              <p className="text-[10px] text-gray-400 leading-relaxed">{e.message}</p>
            )}
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {e.source   && <Detail label="Source"    val={e.source} />}
              {e.path     && <Detail label="Path"      val={e.path} />}
              {e.category && <Detail label="Category"  val={e.category} />}
              {e.created_at && <Detail label="First seen" val={fmtDate(e.created_at)} />}
            </div>
            {e.metadata && Object.keys(e.metadata).length > 0 && (
              <pre className="text-[9px] text-gray-500 bg-[#0d0d0f] rounded p-2 overflow-x-auto font-mono border border-white/5">
                {JSON.stringify(e.metadata, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </>
  );
}

function Detail({ label, val }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[8px] text-gray-600 uppercase w-14 shrink-0">{label}</span>
      <span className="text-[9px] text-gray-400 font-mono truncate">{val}</span>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function SecurityCenter() {
  const [summary, setSummary]   = useState(null);
  const [events, setEvents]     = useState([]);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(true);
  const [loadingSum, setLoadingSum] = useState(true);
  const [error, setError]       = useState(null);
  const [offset, setOffset]     = useState(0);
  const LIMIT = 50;

  // Filters
  const [severity, setSeverity] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus]     = useState('open');
  const [search, setSearch]     = useState('');

  const loadSummary = useCallback(async () => {
    setLoadingSum(true);
    try {
      const r = await getSecuritySummary();
      setSummary(r);
    } catch { /* silent */ }
    finally { setLoadingSum(false); }
  }, []);

  const loadEvents = useCallback(async (off = 0) => {
    setLoading(true);
    setError(null);
    try {
      const params = { limit: LIMIT, offset: off };
      if (severity) params.severity = severity;
      if (category) params.category = category;
      if (status)   params.status   = status;
      if (search)   params.search   = search;
      const r = await getSecurityEvents(params);
      setEvents(r.items || []);
      setOffset(off);
      // Rough total for pagination
      setTotal((r.items?.length === LIMIT) ? off + LIMIT + 1 : off + (r.items?.length || 0));
    } catch (e) {
      setError('Error cargando eventos de seguridad');
    } finally {
      setLoading(false);
    }
  }, [severity, category, status, search]);

  useEffect(() => {
    loadSummary();
    const id = setInterval(loadSummary, 30_000);
    return () => clearInterval(id);
  }, [loadSummary]);

  useEffect(() => { loadEvents(0); }, [loadEvents]);

  const handleResolved = useCallback((eventId) => {
    setEvents(prev => prev.map(e =>
      e.event_id === eventId ? { ...e, status: 'resolved' } : e
    ));
    loadSummary();
  }, [loadSummary]);

  const threat = summary?.threat_level || 'normal';
  const tc = THREAT_CONFIG[threat] || THREAT_CONFIG.normal;
  const ThreatIcon = tc.icon;

  return (
    <div className="flex flex-col gap-5">
      {/* ── Threat status banner ── */}
      <div className={`rounded-xl border p-4 flex items-center gap-4 ${tc.bg}`}>
        <ThreatIcon className={`w-8 h-8 ${tc.color} shrink-0`} />
        <div className="flex-1">
          <div className={`text-sm font-bold ${tc.color}`}>{tc.label}</div>
          <div className="text-[10px] text-gray-500 mt-0.5">
            {summary?.open_events ?? '—'} evento{summary?.open_events !== 1 ? 's' : ''} abierto{summary?.open_events !== 1 ? 's' : ''} ·{' '}
            {summary?.critical_24h ?? '—'} crítico{summary?.critical_24h !== 1 ? 's' : ''} en las últimas 24h
          </div>
        </div>
        <button
          onClick={() => { loadSummary(); loadEvents(0); }}
          disabled={loadingSum || loading}
          className="p-1.5 rounded hover:bg-white/5 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-gray-500 ${(loadingSum || loading) ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* ── Stats grid ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Críticos abiertos"
          value={summary?.severity_counts?.critical ?? '—'}
          color="text-red-400"
          icon={<ShieldOff className="w-4 h-4" />}
        />
        <StatCard
          label="Advertencias abiertas"
          value={summary?.severity_counts?.warning ?? '—'}
          color="text-amber-400"
          icon={<AlertTriangle className="w-4 h-4" />}
        />
        <StatCard
          label="Críticos 24h"
          value={summary?.critical_24h ?? '—'}
          color="text-orange-400"
          sub="últimas 24 horas"
          icon={<ShieldAlert className="w-4 h-4" />}
        />
        <StatCard
          label="Categorías activas"
          value={Object.keys(summary?.category_counts || {}).length || '—'}
          color="text-blue-400"
          sub="con eventos hoy"
          icon={<BarChart3 className="w-4 h-4" />}
        />
      </div>

      {/* ── Top attacked sites + Top IPs ── */}
      {(summary?.top_attacked_sites?.length > 0 || summary?.top_suspect_ips?.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {summary?.top_attacked_sites?.length > 0 && (
            <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
              <div className="px-4 py-2.5 border-b border-white/5 text-[10px] font-semibold text-white uppercase tracking-wide flex items-center gap-2">
                <Globe className="w-3.5 h-3.5 text-emerald-400" /> Sitios más afectados (24h)
              </div>
              <div className="divide-y divide-white/5">
                {summary.top_attacked_sites.map((s, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                    <span className="text-[10px] text-gray-600 w-4 font-mono">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-[11px] text-white truncate">{s.name || `hosting:${s.hosting_id}`}</div>
                      <div className="text-[9px] text-gray-600 font-mono truncate">{s.subdomain}</div>
                    </div>
                    <span className="text-[11px] font-bold text-red-400">{s.cnt}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {summary?.top_suspect_ips?.length > 0 && (
            <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
              <div className="px-4 py-2.5 border-b border-white/5 text-[10px] font-semibold text-white uppercase tracking-wide flex items-center gap-2">
                <Lock className="w-3.5 h-3.5 text-red-400" /> IPs sospechosas (24h)
              </div>
              <div className="divide-y divide-white/5">
                {summary.top_suspect_ips.slice(0, 6).map((ip, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                    <span className="text-[10px] text-gray-600 w-4 font-mono">{i + 1}</span>
                    <span className="flex-1 text-[10px] text-gray-300 font-mono">{ip.ip}</span>
                    <span className="text-[11px] font-bold text-amber-400">{ip.cnt}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Event table ── */}
      <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
        {/* Filters */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/5 flex-wrap">
          <Filter className="w-3 h-3 text-gray-600 shrink-0" />
          <select value={severity} onChange={e => setSeverity(e.target.value)}
            className="bg-[#0d0d0f] border border-white/8 text-[10px] text-gray-300 rounded px-2 py-1 outline-none focus:border-white/20">
            {SEVERITIES.map(s => <option key={s} value={s}>{s || 'Toda severidad'}</option>)}
          </select>
          <select value={category} onChange={e => setCategory(e.target.value)}
            className="bg-[#0d0d0f] border border-white/8 text-[10px] text-gray-300 rounded px-2 py-1 outline-none focus:border-white/20">
            {CATEGORIES.map(c => <option key={c} value={c}>{c || 'Todas las categorías'}</option>)}
          </select>
          <select value={status} onChange={e => setStatus(e.target.value)}
            className="bg-[#0d0d0f] border border-white/8 text-[10px] text-gray-300 rounded px-2 py-1 outline-none focus:border-white/20">
            {STATUSES.map(s => <option key={s} value={s}>{s || 'Todos los estados'}</option>)}
          </select>
          <input
            type="text"
            placeholder="Buscar..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadEvents(0)}
            className="bg-[#0d0d0f] border border-white/8 text-[10px] text-gray-300 rounded px-2 py-1 outline-none focus:border-white/20 w-36"
          />
        </div>

        {/* Events list */}
        {error && (
          <div className="px-4 py-3 flex items-center gap-2 text-[11px] text-red-400">
            <AlertTriangle className="w-3.5 h-3.5" /> {error}
          </div>
        )}
        {loading && events.length === 0 && (
          <div className="flex items-center justify-center py-12 gap-2 text-[11px] text-gray-600">
            <RefreshCw className="w-4 h-4 animate-spin" /> Cargando...
          </div>
        )}
        {!loading && events.length === 0 && !error && (
          <div className="py-12 text-center text-[11px] text-gray-600">
            No hay eventos de seguridad que mostrar.
          </div>
        )}

        <div className="max-h-[600px] overflow-y-auto">
          {events.map(e => (
            <EventRow key={e.event_id} e={e} onResolved={handleResolved} />
          ))}
        </div>

        {/* Pagination */}
        {(events.length === LIMIT || offset > 0) && (
          <div className="flex items-center justify-between px-4 py-2.5 border-t border-white/5">
            <button
              onClick={() => loadEvents(Math.max(0, offset - LIMIT))}
              disabled={offset === 0 || loading}
              className="text-[10px] text-gray-500 hover:text-white disabled:opacity-30 transition-colors"
            >
              ← Anterior
            </button>
            <span className="text-[9px] text-gray-600">{offset + 1}–{offset + events.length}</span>
            <button
              onClick={() => loadEvents(offset + LIMIT)}
              disabled={events.length < LIMIT || loading}
              className="text-[10px] text-gray-500 hover:text-white disabled:opacity-30 transition-colors"
            >
              Siguiente →
            </button>
          </div>
        )}
      </div>

      {/* ── Category breakdown ── */}
      {summary?.category_counts && Object.keys(summary.category_counts).length > 0 && (
        <div className="bg-[#111] rounded-xl border border-white/8 p-4">
          <div className="text-[10px] font-semibold text-white mb-3 uppercase tracking-wide">Eventos por categoría (24h)</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(summary.category_counts)
              .sort((a, b) => b[1] - a[1])
              .map(([cat, cnt]) => (
                <button
                  key={cat}
                  onClick={() => { setCategory(cat); loadEvents(0); }}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 border border-white/8 hover:border-white/20 transition-all text-[10px] text-gray-400"
                >
                  {CAT_ICON[cat]}
                  <span>{cat}</span>
                  <span className="font-bold text-white">{cnt}</span>
                </button>
              ))
            }
          </div>
        </div>
      )}
    </div>
  );
}
