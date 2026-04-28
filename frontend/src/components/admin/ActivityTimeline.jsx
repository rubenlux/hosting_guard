import React, { useEffect, useState, useCallback } from 'react';
import {
  Activity, RefreshCw, Filter, ChevronDown,
  ShieldAlert, Globe, Database, CreditCard, Upload,
  User, Terminal, AlertTriangle, Info, Zap,
} from 'lucide-react';
import { getAdminActivity, getAdminUserActivity } from '../../services/api';

function fmtDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

const CATEGORY_ICON = {
  auth:     <User className="w-3.5 h-3.5 text-blue-400" />,
  hosting:  <Globe className="w-3.5 h-3.5 text-emerald-400" />,
  backup:   <Database className="w-3.5 h-3.5 text-purple-400" />,
  billing:  <CreditCard className="w-3.5 h-3.5 text-amber-400" />,
  import:   <Upload className="w-3.5 h-3.5 text-cyan-400" />,
  wordpress:<Terminal className="w-3.5 h-3.5 text-orange-400" />,
  security: <ShieldAlert className="w-3.5 h-3.5 text-red-400" />,
  system:   <Zap className="w-3.5 h-3.5 text-gray-400" />,
};

const SEVERITY_STYLE = {
  info:     'bg-blue-500/10 text-blue-400 border-blue-500/20',
  warning:  'bg-amber-500/10 text-amber-400 border-amber-500/20',
  critical: 'bg-red-500/10 text-red-400 border-red-500/20',
};

const CATEGORIES = ['', 'auth', 'hosting', 'backup', 'billing', 'import', 'wordpress', 'security', 'system'];
const SEVERITIES = ['', 'info', 'warning', 'critical'];

function EventRow({ e }) {
  const [expanded, setExpanded] = useState(false);
  const icon = CATEGORY_ICON[e.category] || <Info className="w-3.5 h-3.5 text-gray-400" />;

  return (
    <div className="border-b border-white/5 last:border-0">
      <div
        className="flex items-start gap-3 px-4 py-2.5 hover:bg-white/3 cursor-pointer transition-colors"
        onClick={() => setExpanded(x => !x)}
      >
        {/* Icon */}
        <div className="mt-0.5 shrink-0 w-5 flex justify-center">{icon}</div>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] text-white font-medium">{e.title}</span>
            <span className={`text-[8px] font-bold uppercase px-1.5 py-0.5 rounded border ${SEVERITY_STYLE[e.severity] || SEVERITY_STYLE.info}`}>
              {e.severity}
            </span>
            {e.category && (
              <span className="text-[8px] bg-white/5 text-gray-500 px-1.5 py-0.5 rounded uppercase">{e.category}</span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-0.5">
            <span className="text-[9px] text-gray-500 truncate">{e.actor_email || `user:${e.user_id}`}</span>
            {e.hosting_id && (
              <span className="text-[9px] text-gray-600 font-mono">hosting:{e.hosting_id}</span>
            )}
          </div>
        </div>

        {/* Timestamp + expand */}
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className="text-[9px] text-gray-600">{fmtDate(e.created_at)}</span>
          <ChevronDown className={`w-3 h-3 text-gray-600 transition-transform ${expanded ? 'rotate-180' : ''}`} />
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="ml-11 px-4 pb-3 space-y-1.5">
          {e.message && (
            <p className="text-[10px] text-gray-400 leading-relaxed">{e.message}</p>
          )}
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {e.source && <Detail label="Source" val={e.source} />}
            {e.actor_type && <Detail label="Actor" val={e.actor_type} />}
            {e.ip && <Detail label="IP" val={e.ip} />}
            {e.event_type && <Detail label="Type" val={e.event_type} />}
          </div>
          {e.metadata && Object.keys(e.metadata).length > 0 && (
            <pre className="text-[9px] text-gray-500 bg-[#0d0d0f] rounded p-2 overflow-x-auto font-mono border border-white/5 mt-1">
              {JSON.stringify(e.metadata, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function Detail({ label, val }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[8px] text-gray-600 uppercase w-10 shrink-0">{label}</span>
      <span className="text-[9px] text-gray-400 font-mono truncate">{val}</span>
    </div>
  );
}

export default function ActivityTimeline({ userId = null }) {
  const [events, setEvents]     = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [total, setTotal]       = useState(0);
  const [offset, setOffset]     = useState(0);
  const [category, setCategory] = useState('');
  const [severity, setSeverity] = useState('');
  const [search, setSearch]     = useState('');
  const LIMIT = 50;

  const load = useCallback(async (off = 0) => {
    setLoading(true);
    setError(null);
    try {
      const params = { limit: LIMIT, offset: off };
      if (category) params.category = category;
      if (severity) params.severity = severity;
      if (userId)   params.user_id  = userId;
      const r = userId
        ? await getAdminUserActivity(userId, params)
        : await getAdminActivity(params);
      setEvents(r.items || []);
      setTotal(r.total_count ?? (r.items?.length ?? 0));
      setOffset(off);
    } catch (e) {
      setError('Error cargando actividad');
    } finally {
      setLoading(false);
    }
  }, [category, severity, userId]);

  useEffect(() => { load(0); }, [load]);

  const visible = search
    ? events.filter(e =>
        (e.title || '').toLowerCase().includes(search.toLowerCase()) ||
        (e.actor_email || '').toLowerCase().includes(search.toLowerCase()) ||
        (e.event_type || '').toLowerCase().includes(search.toLowerCase())
      )
    : events;

  return (
    <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-[#00ff88]" />
          <span className="text-[11px] font-semibold text-white">
            {userId ? 'Actividad del usuario' : 'Activity Timeline'}
          </span>
          {total > 0 && (
            <span className="text-[9px] bg-white/5 text-gray-500 px-1.5 py-0.5 rounded">{total}</span>
          )}
        </div>
        <button
          onClick={() => load(0)}
          disabled={loading}
          className="p-1 rounded hover:bg-white/5 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-gray-500 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/5 flex-wrap">
        <Filter className="w-3 h-3 text-gray-600 shrink-0" />

        <select
          value={category}
          onChange={e => setCategory(e.target.value)}
          className="bg-[#0d0d0f] border border-white/8 text-[10px] text-gray-300 rounded px-2 py-1 outline-none focus:border-white/20"
        >
          {CATEGORIES.map(c => (
            <option key={c} value={c}>{c || 'Todas las categorías'}</option>
          ))}
        </select>

        <select
          value={severity}
          onChange={e => setSeverity(e.target.value)}
          className="bg-[#0d0d0f] border border-white/8 text-[10px] text-gray-300 rounded px-2 py-1 outline-none focus:border-white/20"
        >
          {SEVERITIES.map(s => (
            <option key={s} value={s}>{s || 'Toda severidad'}</option>
          ))}
        </select>

        <input
          type="text"
          placeholder="Buscar..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="bg-[#0d0d0f] border border-white/8 text-[10px] text-gray-300 rounded px-2 py-1 outline-none focus:border-white/20 w-40"
        />
      </div>

      {/* Events */}
      {error && (
        <div className="px-4 py-3 text-[11px] text-red-400 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5" /> {error}
        </div>
      )}
      {loading && events.length === 0 && (
        <div className="flex items-center justify-center py-12 gap-2 text-[11px] text-gray-600">
          <RefreshCw className="w-4 h-4 animate-spin" /> Cargando...
        </div>
      )}
      {!loading && visible.length === 0 && !error && (
        <div className="py-12 text-center text-[11px] text-gray-600">
          No hay eventos que mostrar.
        </div>
      )}

      <div className="max-h-[600px] overflow-y-auto divide-y divide-white/5">
        {visible.map(e => <EventRow key={e.event_id} e={e} />)}
      </div>

      {/* Pagination */}
      {!search && (events.length === LIMIT || offset > 0) && (
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-white/5">
          <button
            onClick={() => load(Math.max(0, offset - LIMIT))}
            disabled={offset === 0 || loading}
            className="text-[10px] text-gray-500 hover:text-white disabled:opacity-30 transition-colors"
          >
            ← Anterior
          </button>
          <span className="text-[9px] text-gray-600">{offset + 1}–{offset + visible.length}</span>
          <button
            onClick={() => load(offset + LIMIT)}
            disabled={events.length < LIMIT || loading}
            className="text-[10px] text-gray-500 hover:text-white disabled:opacity-30 transition-colors"
          >
            Siguiente →
          </button>
        </div>
      )}
    </div>
  );
}
