import React, { useEffect, useState, useCallback } from 'react';
import {
  ShieldAlert, RefreshCw, CheckCircle2, ChevronDown, ChevronRight,
  Copy, Loader2, AlertTriangle, Terminal, Globe, Cpu, Zap,
} from 'lucide-react';
import { getSentinelIncidents, resolveIncident } from '../../services/api';

// ─── helpers ─────────────────────────────────────────────────────────────────

function fmt(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

const SEV = {
  critical: 'text-red-400 bg-red-500/10 border-red-500/30',
  high:     'text-orange-400 bg-orange-500/10 border-orange-500/30',
  medium:   'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
  warning:  'text-amber-400 bg-amber-500/10 border-amber-500/30',
  info:     'text-blue-400 bg-blue-500/10 border-blue-500/20',
};

const SOURCE_ICON = {
  deploy:   <Terminal className="w-3.5 h-3.5" />,
  security: <ShieldAlert className="w-3.5 h-3.5" />,
  site:     <Globe className="w-3.5 h-3.5" />,
  system:   <Cpu className="w-3.5 h-3.5" />,
};

const TABS = [
  { id: '',         label: 'Todos' },
  { id: 'deploy',   label: 'Deploy' },
  { id: 'security', label: 'Seguridad' },
  { id: 'site',     label: 'Sitio' },
  { id: 'system',   label: 'Sistema' },
];

const STATUS_TABS = [
  { id: 'open',     label: 'Abiertos' },
  { id: 'resolved', label: 'Resueltos' },
  { id: '',         label: 'Todos' },
];

// ─── Copy report ─────────────────────────────────────────────────────────────

function buildReport(inc) {
  const ev = inc.evidence || {};
  const lines = [
    'INFORME DE INCIDENTE — HostingGuard',
    '─'.repeat(40),
    `Título:      ${inc.title}`,
    `Tipo:        ${inc.incident_type}`,
    `Fuente:      ${inc.source_type}`,
    `Severidad:   ${inc.severity}`,
    `Estado:      ${inc.status}`,
    `Detectado:   ${fmt(inc.first_seen)}`,
    `Último aviso: ${fmt(inc.last_seen)}`,
    `Apariciones: ${inc.count}`,
  ];
  if (ev.repo_url)      lines.push(`Repositorio: ${ev.repo_url}`);
  if (ev.branch)        lines.push(`Rama:        ${ev.branch}`);
  if (ev.project_name)  lines.push(`Proyecto:    ${ev.project_name}`);
  if (ev.stage)         lines.push(`Etapa:       ${ev.stage}`);
  if (ev.message)       lines.push('', `Descripción: ${ev.message}`);
  if (ev.suggested_fix) lines.push('', `Solución sugerida:`, ev.suggested_fix);
  lines.push('', '─'.repeat(40), 'Generado por HostingGuard AI Sentinel');
  return lines.join('\n');
}

// ─── IncidentRow ──────────────────────────────────────────────────────────────

function IncidentRow({ inc, onResolved }) {
  const [open, setOpen]     = useState(false);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const ev = inc.evidence || {};
  const sevClass = SEV[inc.severity] || SEV.info;
  const isOpen = inc.status === 'open';

  async function handleResolve() {
    if (!window.confirm(`¿Resolver incidente #${inc.incident_id}?`)) return;
    setLoading(true);
    try {
      await resolveIncident(inc.incident_id);
      onResolved(inc.incident_id);
    } catch {
      alert('Error al resolver el incidente.');
    } finally {
      setLoading(false);
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(buildReport(inc)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className={`border rounded-xl overflow-hidden transition-colors ${
      isOpen ? 'border-white/10 bg-[#111]' : 'border-white/5 bg-[#0d0d0f]'
    }`}>
      {/* Header row */}
      <div
        className="flex items-start gap-3 p-4 cursor-pointer hover:bg-white/3 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <span className={`mt-0.5 flex-shrink-0 ${sevClass.split(' ')[0]}`}>
          {SOURCE_ICON[inc.source_type] || <Zap className="w-3.5 h-3.5" />}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-0.5">
            <span className="text-sm text-white/90 font-medium truncate">{inc.title}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${sevClass}`}>
              {inc.severity}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
              isOpen
                ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
                : 'text-gray-500 bg-white/5 border-white/8'
            }`}>
              {inc.status}
            </span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-gray-500">
            {ev.project_name && <span>{ev.project_name}</span>}
            {ev.branch && <span>:{ev.branch}</span>}
            {ev.stage && <span>etapa: {ev.stage}</span>}
            <span>×{inc.count} · {fmt(inc.last_seen)}</span>
          </div>
        </div>
        {open ? <ChevronDown className="w-4 h-4 text-gray-600 flex-shrink-0 mt-0.5" />
               : <ChevronRight className="w-4 h-4 text-gray-600 flex-shrink-0 mt-0.5" />}
      </div>

      {/* Expanded detail */}
      {open && (
        <div className="border-t border-white/5 px-4 pb-4 pt-3 space-y-3">
          {ev.message && (
            <p className="text-sm text-gray-300">{ev.message}</p>
          )}
          {ev.suggested_fix && (
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
              <div className="text-[10px] text-emerald-500 uppercase tracking-wide mb-1">Solución sugerida</div>
              <p className="text-sm text-emerald-300">{ev.suggested_fix}</p>
            </div>
          )}
          {ev.repo_url && (
            <div className="text-xs text-gray-500">
              <span className="text-gray-600">Repo: </span>
              <a href={ev.repo_url} target="_blank" rel="noreferrer"
                 className="text-blue-400 hover:underline">{ev.repo_url}</a>
              {ev.branch && <span className="ml-2 text-gray-600">rama: {ev.branch}</span>}
            </div>
          )}

          {/* Raw evidence */}
          <details className="text-xs">
            <summary className="cursor-pointer text-gray-600 hover:text-gray-400 select-none">
              Evidencia técnica
            </summary>
            <pre className="mt-2 bg-black/40 rounded p-2 text-[10px] text-gray-400 overflow-x-auto max-h-40">
              {JSON.stringify(ev, null, 2)}
            </pre>
          </details>

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            {isOpen && (
              <button
                onClick={handleResolve}
                disabled={loading}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 transition-colors disabled:opacity-50"
              >
                {loading
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <CheckCircle2 className="w-3.5 h-3.5" />}
                Marcar resuelto
              </button>
            )}
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-white/5 text-gray-400 border border-white/8 hover:bg-white/8 transition-colors"
            >
              <Copy className="w-3.5 h-3.5" />
              {copied ? 'Copiado' : 'Copiar informe'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── SentinelPanel ────────────────────────────────────────────────────────────

export default function SentinelPanel() {
  const [sourceTab, setSourceTab] = useState('deploy');
  const [statusTab, setStatusTab] = useState('open');
  const [items, setItems]         = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const params = {};
    if (sourceTab) params.source_type = sourceTab;
    if (statusTab) params.status      = statusTab;
    getSentinelIncidents(params)
      .then(d => setItems(d.items || []))
      .catch(e => setError(e?.response?.data?.detail || 'Error cargando incidentes'))
      .finally(() => setLoading(false));
  }, [sourceTab, statusTab]);

  useEffect(() => { load(); }, [load]);

  function handleResolved(id) {
    setItems(prev => prev.map(i =>
      i.incident_id === id ? { ...i, status: 'resolved' } : i
    ));
  }

  const openCount = items.filter(i => i.status === 'open').length;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-amber-400" />
            AI Sentinel
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Incidentes detectados por el motor de análisis
            {openCount > 0 && (
              <span className="ml-2 text-amber-400 font-medium">
                {openCount} abierto{openCount !== 1 ? 's' : ''}
              </span>
            )}
          </p>
        </div>
        <button
          onClick={load}
          className="p-2 rounded-lg bg-white/5 border border-white/8 text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Source tabs */}
      <div className="flex gap-1 mb-4 bg-white/4 p-1 rounded-xl w-fit">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setSourceTab(t.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              sourceTab === t.id
                ? 'bg-white/10 text-white'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Status tabs */}
      <div className="flex gap-2 mb-5">
        {STATUS_TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setStatusTab(t.id)}
            className={`px-3 py-1 rounded-lg text-xs border transition-colors ${
              statusTab === t.id
                ? 'bg-white/10 text-white border-white/15'
                : 'text-gray-500 border-white/5 hover:border-white/10 hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading && (
        <div className="flex items-center gap-2 text-gray-500 py-8 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span className="text-sm">Cargando incidentes…</span>
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl p-4">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span className="text-sm">{error}</span>
        </div>
      )}
      {!loading && !error && items.length === 0 && (
        <div className="text-center py-12 text-gray-600">
          <CheckCircle2 className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">Sin incidentes{statusTab === 'open' ? ' abiertos' : ''} en este segmento</p>
        </div>
      )}
      {!loading && !error && items.length > 0 && (
        <div className="space-y-2">
          {items.map(inc => (
            <IncidentRow key={inc.incident_id} inc={inc} onResolved={handleResolved} />
          ))}
        </div>
      )}
    </div>
  );
}
