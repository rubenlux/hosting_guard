import React, { useEffect, useState } from 'react';
import {
  CheckCircle2, XCircle, Clock, RefreshCw,
  ChevronDown, ChevronRight, AlertTriangle, Loader2,
} from 'lucide-react';
import { getMyDeployEvents } from '../../../services/api';

function fmt(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

const STATUS_ICON = {
  success: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
  failed:  <XCircle      className="w-4 h-4 text-red-400" />,
  blocked: <AlertTriangle className="w-4 h-4 text-amber-400" />,
};

const STATUS_PILL = {
  success: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  failed:  'text-red-400 bg-red-500/10 border-red-500/30',
  blocked: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
};

const GENERIC_CODES = new Set(['build_failed', 'npm_install_failed', 'unknown_deploy_error']);

/**
 * Iterates events newest-first. For each repo, once we've seen a specific
 * (non-generic) failure, any older generic-code failure for that same repo
 * is superseded.
 */
function markSuperseded(events) {
  const specificByRepo = new Map();
  return events.map(ev => {
    const repo = ev.repo_url || '';
    const code = ev.code;
    const isFailing = ev.status === 'failed' || ev.status === 'blocked';

    if (!isFailing || !code) return { ...ev, superseded: false };

    if (!GENERIC_CODES.has(code)) {
      if (!specificByRepo.has(repo)) specificByRepo.set(repo, new Set());
      specificByRepo.get(repo).add(code);
      return { ...ev, superseded: false };
    }

    const hasSpecific = specificByRepo.has(repo) && specificByRepo.get(repo).size > 0;
    return { ...ev, superseded: hasSpecific };
  });
}

function DeployRow({ event }) {
  const [open, setOpen] = useState(false);
  const { superseded } = event;
  const isFailed = event.status === 'failed' || event.status === 'blocked';
  const pillClass = STATUS_PILL[event.status] || 'text-gray-400 bg-white/5 border-white/10';

  if (superseded) {
    return (
      <div className="border border-white/5 border-dashed rounded-xl overflow-hidden opacity-40">
        <div className="flex items-start gap-3 px-4 py-3">
          <span className="mt-0.5 flex-shrink-0">
            {STATUS_ICON[event.status] || <Clock className="w-4 h-4 text-gray-500" />}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-0.5">
              <span className="text-sm text-gray-500 font-medium truncate">
                {event.project_name || event.repo_url?.split('/').slice(-1)[0] || 'deploy'}
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded border text-gray-600 bg-white/3 border-white/8">
                {event.code}
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded border text-amber-600 bg-amber-500/8 border-amber-500/20">
                reemplazado
              </span>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-gray-600">
              <span>{event.branch}</span>
              <span>{fmt(event.created_at)}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-white/8 rounded-xl overflow-hidden">
      <div
        className="flex items-start gap-3 p-4 cursor-pointer hover:bg-white/3 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <span className="mt-0.5 flex-shrink-0">
          {STATUS_ICON[event.status] || <Clock className="w-4 h-4 text-gray-500" />}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-0.5">
            <span className="text-sm text-white/90 font-medium truncate">
              {event.project_name || event.repo_url?.split('/').slice(-1)[0] || 'deploy'}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${pillClass}`}>
              {event.status}
            </span>
            {event.code && event.status !== 'success' && (
              <span className="text-[10px] px-1.5 py-0.5 rounded border text-gray-500 bg-white/4 border-white/8">
                {event.code}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-gray-500">
            <span>{event.branch}</span>
            {event.stage && <span>etapa: {event.stage}</span>}
            <span>{fmt(event.created_at)}</span>
          </div>
        </div>
        {isFailed && (
          open
            ? <ChevronDown  className="w-4 h-4 text-gray-600 flex-shrink-0 mt-0.5" />
            : <ChevronRight className="w-4 h-4 text-gray-600 flex-shrink-0 mt-0.5" />
        )}
      </div>

      {open && isFailed && (
        <div className="border-t border-white/5 px-4 pb-4 pt-3 space-y-3">
          {event.message && (
            <p className="text-sm text-gray-300">{event.message}</p>
          )}
          {event.suggested_fix && (
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
              <div className="text-[10px] text-emerald-500 uppercase tracking-wide mb-1">Solución sugerida</div>
              <p className="text-sm text-emerald-300">{event.suggested_fix}</p>
            </div>
          )}
          {event.repo_url && (
            <div className="text-xs text-gray-500">
              <span className="text-gray-600">Repo: </span>
              <a href={event.repo_url} target="_blank" rel="noreferrer"
                 className="text-blue-400 hover:underline break-all">{event.repo_url}</a>
            </div>
          )}
          {event.evidence && Object.keys(event.evidence).some(k =>
            ['node_version', 'npm_version', 'suspected_package'].includes(k)
          ) && (
            <div className="grid grid-cols-2 gap-2 text-xs">
              {event.evidence.node_version && (
                <div>
                  <span className="text-gray-600">Node: </span>
                  <span className="text-gray-400">{event.evidence.node_version}</span>
                </div>
              )}
              {event.evidence.npm_version && (
                <div>
                  <span className="text-gray-600">npm: </span>
                  <span className="text-gray-400">{event.evidence.npm_version}</span>
                </div>
              )}
              {event.evidence.suspected_package && (
                <div className="col-span-2">
                  <span className="text-gray-600">Paquete: </span>
                  <span className="text-gray-400">{event.evidence.suspected_package}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function DeployHistorySection() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  function load() {
    setLoading(true);
    setError(null);
    getMyDeployEvents(20)
      .then(d => setEvents(markSuperseded(d.items || [])))
      .catch(e => setError(e?.response?.data?.detail || 'Error cargando historial'))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-lg font-semibold text-white">Historial de deploys</h2>
          <p className="text-xs text-gray-500 mt-0.5">Últimos 20 deploys desde GitHub</p>
        </div>
        <button
          onClick={load}
          className="p-2 rounded-lg bg-white/5 border border-white/8 text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-gray-500 py-8 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">Cargando historial…</span>
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl p-4">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}
      {!loading && !error && events.length === 0 && (
        <div className="text-center py-12 text-gray-600">
          <Clock className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">Sin deploys registrados todavía</p>
        </div>
      )}
      {!loading && !error && events.length > 0 && (
        <div className="space-y-2">
          {events.map(e => (
            <DeployRow key={e.deploy_event_id} event={e} />
          ))}
        </div>
      )}
    </div>
  );
}
