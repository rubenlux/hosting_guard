/**
 * AIAdvisory — full-page advisory center
 *
 * Uses the same data hooks as the dashboard widget — no new fetching.
 * Renders all hostings in a master/detail layout:
 *   Left  — scrollable list (all hostings, color-coded by severity)
 *   Right — full detail for selected hosting
 *
 * Props:
 *   onDiagnose — (hostingId) => void  — opens AI diagnosis modal in Dashboard
 */
import { useState, useMemo, useEffect, useCallback } from 'react';
import { Bot, AlertTriangle, CheckCircle, Zap, Activity, Clock, FileCode, Wrench, ShieldCheck, ShieldAlert, Shield, Loader2 } from 'lucide-react';
import { useDashboardData } from '../hooks/useDashboardData';
import { useAIAdvisory } from '../hooks/useAIAdvisory';
import api from '../services/api';

// ── Severity helpers ──────────────────────────────────────────────────────────
const SEV = {
  critical: {
    badge:      'bg-danger/20 text-danger border border-danger/30',
    label:      'CRÍTICO',
    dot:        'bg-danger',
    rowBorder:  'border-danger/30',
    rowBg:      'bg-danger/5',
    rowHover:   'hover:border-danger/50',
    icon:       <AlertTriangle className="w-3.5 h-3.5 text-danger" />,
    glow:       '0 0 0 1px rgba(255,68,68,0.15), 0 8px 32px rgba(255,68,68,0.1)',
  },
  warning: {
    badge:      'bg-warn/20 text-warn border border-warn/30',
    label:      'ADVERTENCIA',
    dot:        'bg-warn',
    rowBorder:  'border-warn/20',
    rowBg:      'bg-warn/5',
    rowHover:   'hover:border-warn/40',
    icon:       <AlertTriangle className="w-3.5 h-3.5 text-warn" />,
    glow:       'none',
  },
  ok: {
    badge:      'bg-green-500/20 text-green-400 border border-green-500/30',
    label:      'OK',
    dot:        'bg-green-500',
    rowBorder:  'border-white/8',
    rowBg:      'bg-transparent',
    rowHover:   'hover:border-white/20 hover:bg-white/2',
    icon:       <CheckCircle className="w-3.5 h-3.5 text-green-400" />,
    glow:       'none',
  },
};

// ── Sub-components ────────────────────────────────────────────────────────────
function SummaryBar({ counts }) {
  return (
    <div className="flex items-center gap-3">
      {counts.critical > 0 && (
        <span className="flex items-center gap-1.5 text-[11px] font-black px-3 py-1.5 rounded-lg bg-danger/15 text-danger border border-danger/30 animate-pulse">
          <AlertTriangle className="w-3 h-3" />
          {counts.critical} CRÍTICO{counts.critical !== 1 ? 'S' : ''}
        </span>
      )}
      {counts.warning > 0 && (
        <span className="flex items-center gap-1.5 text-[11px] font-black px-3 py-1.5 rounded-lg bg-warn/15 text-warn border border-warn/30">
          <AlertTriangle className="w-3 h-3" />
          {counts.warning} ADVERTENCIA{counts.warning !== 1 ? 'S' : ''}
        </span>
      )}
      <span className="flex items-center gap-1.5 text-[11px] font-black px-3 py-1.5 rounded-lg bg-green-500/10 text-green-400 border border-green-500/20">
        <CheckCircle className="w-3 h-3" />
        {counts.ok} OK
      </span>
    </div>
  );
}

function HostingRow({ advisory, isSelected, onClick }) {
  const cfg = SEV[advisory.severity];
  return (
    <div
      onClick={onClick}
      className={`p-3 rounded-xl border cursor-pointer transition-all ${
        isSelected
          ? 'border-accent bg-accent/8'
          : `${cfg.rowBorder} ${cfg.rowBg} ${cfg.rowHover}`
      }`}
    >
      <div className="flex items-center gap-2">
        <div className="shrink-0">{cfg.icon}</div>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] font-bold text-white truncate">{advisory.hostingName}</div>
          <div className="text-[10px] text-gray-500 truncate mt-0.5">{advisory.summary}</div>
        </div>
        <span className={`text-[9px] font-black px-1.5 py-0.5 rounded shrink-0 ${cfg.badge}`}>
          {cfg.label}
        </span>
      </div>
    </div>
  );
}

function DetailPanel({ advisory, onDiagnose }) {
  const cfg = SEV[advisory.severity];
  const isCritical = advisory.severity === 'critical';

  return (
    <div
      className={`card-dash p-6 space-y-5 ${isCritical ? 'border-danger/40' : ''}`}
      style={isCritical ? { boxShadow: cfg.glow } : undefined}
    >
      {/* Hosting name + badge */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-1">Hosting</div>
          <div className="text-base font-black text-white">{advisory.hostingName}</div>
        </div>
        <span className={`text-[9px] font-black px-2 py-1 rounded-lg ${cfg.badge} ${isCritical ? 'animate-pulse' : ''} border border-white/5`}>
          {cfg.label}
        </span>
      </div>

      <hr className="border-white/5" />

      {/* Summary */}
      <div>
        <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-2">Diagnóstico</div>
        <p className={`text-sm font-semibold leading-relaxed ${isCritical ? 'text-white' : 'text-gray-300'}`}>
          {advisory.summary}
        </p>
      </div>

      {/* Signals */}
      {advisory.signals.length > 0 && (
        <div>
          <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-2">Señales detectadas</div>
          <ul className="space-y-1.5">
            {advisory.signals.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-[11px] text-gray-400">
                <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
                {s}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Recommendation */}
      <div className="p-3 rounded-xl bg-accent/5 border border-accent/15">
        <div className="flex items-start gap-2">
          <Zap className="w-3.5 h-3.5 text-accent mt-0.5 shrink-0" />
          <div>
            <div className="text-[10px] font-mono text-accent uppercase tracking-widest mb-1">Recomendación</div>
            <p className="text-[11px] text-gray-300 leading-relaxed">{advisory.recommendation}</p>
          </div>
        </div>
      </div>

      {/* CTA */}
      {advisory.severity !== 'ok' && onDiagnose && (
        <button
          onClick={() => onDiagnose(advisory.hostingId)}
          className="w-full py-3 rounded-xl bg-accent/10 text-accent hover:bg-accent/20 transition-all border border-accent/20 text-xs font-black uppercase tracking-wider"
        >
          Diagnosticar problema →
        </button>
      )}

      {advisory.severity === 'ok' && (
        <div className="flex items-center gap-2 text-[11px] text-green-400">
          <Activity className="w-3.5 h-3.5" />
          No se requiere ninguna acción en este momento.
        </div>
      )}
    </div>
  );
}

// ── Diagnosis history timeline ────────────────────────────────────────────────
const SEV_DESIGN = {
  critical: {
    container: 'border-l-[3px] border-l-red-500 bg-[#0d1117] border border-white/5',
    titleColor: 'text-red-400',
    badge: 'bg-red-500/10 text-red-400 px-2 py-0.5 rounded-full border border-red-500/20 uppercase font-semibold text-[9px]',
  },
  warning: {
    container: 'border-l-[3px] border-l-amber-500 bg-[#0d1117] border border-white/5',
    titleColor: 'text-amber-400',
    badge: 'bg-amber-500/10 text-amber-500 px-2 py-0.5 rounded-full border border-amber-500/20 uppercase font-semibold text-[9px]',
  },
  info: {
    container: 'border-l-[3px] border-l-blue-500 bg-[#0d1117] border border-white/5',
    titleColor: 'text-blue-400',
    badge: 'bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded-full border border-blue-500/20 uppercase font-semibold text-[9px]',
  }
};

function relTime(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 1)   return 'Ahora mismo';
  if (m < 60)  return `Hace ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `Hace ${h}h`;
  return `Hace ${Math.floor(h / 24)}d`;
}

function DiagnosisHistory({ hostingId }) {
  const [items, setItems]     = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!hostingId) return;
    setLoading(true);
    api.get(`/hosting/${hostingId}/ai-history?limit=10`)
      .then(r => setItems(r.data ?? []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [hostingId]);

  if (loading) {
    return <div className="text-[10px] text-muted italic py-2">Cargando historial...</div>;
  }
  if (items.length === 0) {
    return (
      <div className="text-[10px] text-muted italic py-2">
        Sin diagnósticos previos. Presioná "Diagnosticar problema" para generar el primero.
      </div>
    );
  }

  return (
    <div className="space-y-10">
      {items.map(item => {
        const design = SEV_DESIGN[item.severity] || SEV_DESIGN.info;

        return (
          <div key={item.id} className="pt-2">
            <div className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest mb-1.5 flex items-center gap-2">
              <ShieldCheck className="w-3 h-3" /> Informe de Evidencia
            </div>
            <h2 className="text-xl font-bold text-white mb-3">
              Análisis de Inteligencia: <span className="text-cyan-300">{item.failure_type || 'Excepción del Sistema'}</span>
            </h2>
            
            <div className={`rounded-xl shadow-2xl ${design.container} p-6 space-y-6`}>
               {/* Header status */}
               <div className="flex justify-between items-center border-b border-white/5 pb-4">
                 <div className={design.badge}>
                   ● {item.severity}
                 </div>
                 <div className="flex items-center gap-4">
                   {item.confidence != null && (
                     <span className="text-[9px] font-mono text-gray-500 border border-white/10 px-2 py-0.5 rounded text-white/50 bg-black/20">
                       CONFIA: {Math.round(item.confidence * 100)}%
                     </span>
                   )}
                   <span className="text-[10px] text-gray-500 font-mono flex items-center gap-1.5">
                     <Clock className="w-3 h-3 opacity-60" /> {relTime(item.created_at)}
                   </span>
                 </div>
               </div>

               {/* Summary context */}
               <div className="text-lg font-medium text-gray-100 leading-snug">
                 {item.summary}
               </div>

               {/* Grid analysis details */}
               <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                 {item.impact && (
                   <div>
                      <div className="flex items-center gap-2 mb-2.5">
                        <AlertTriangle className={`w-4 h-4 ${design.titleColor}`} />
                        <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Análisis de Impacto</span>
                      </div>
                      <div className="bg-black/20 rounded-lg border border-white/5 p-4 h-[calc(100%-28px)]">
                        <div className="text-[11px] text-gray-300 leading-relaxed font-medium">
                          {item.impact}
                        </div>
                      </div>
                   </div>
                 )}

                 {item.file_path && (
                   <div>
                      <div className="flex items-center gap-2 mb-2.5">
                        <FileCode className={`w-4 h-4 text-[#8b949e]`} />
                        <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Alcance del Recurso</span>
                      </div>
                      <div className="flex gap-2 flex-wrap items-start">
                        <span className="bg-[#1b1f28] border border-[#2b3245] text-gray-300 px-3 py-1.5 rounded-full text-[10px] font-mono shadow-sm">
                          {item.file_path}{item.line_number ? `:${item.line_number}` : ''}
                        </span>
                      </div>
                   </div>
                 )}
               </div>

               {/* Forensics logs */}
               {(item.root_cause || (item.evidence && item.evidence.length > 0)) && (
                 <div>
                    <div className="flex items-center justify-between mb-2.5">
                      <div className="flex items-center gap-2">
                        <Activity className="w-4 h-4 text-[#8b949e]" />
                        <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Registros Forenses</span>
                      </div>
                      <div className="text-[9px] font-mono text-[#8b949e] opacity-50 tracking-widest px-2 relative uppercase">
                        NODE_HASH: {item.id ? String(item.id).substring(0, 8) : 'NA'}
                      </div>
                    </div>
                    
                    <div className="bg-[#050505] border border-white/10 rounded-lg p-5 font-mono text-[11px] overflow-hidden space-y-2 shadow-inner">
                      {item.root_cause && <div className="text-[#a5d6ff] mb-4 opacity-80 leading-relaxed">{item.root_cause}</div>}
                      {item.evidence && item.evidence.map((ev, i) => (
                        <div key={i} className="flex gap-4">
                          <span className="text-gray-600 select-none opacity-50 w-4 text-right">0{i+1}</span>
                          <span className="text-[#ff7b72] leading-relaxed break-all">{ev}</span>
                        </div>
                      ))}
                    </div>
                 </div>
               )}

               {/* Steps and recommended action */}
               {item.fix_steps && item.fix_steps.length > 0 && (
                 <div className="pt-2">
                    <h3 className="text-sm font-bold text-white mb-3 tracking-wide">Resolución Recomendada</h3>
                    <div className="space-y-2">
                      {item.fix_steps.map((step, i) => (
                        <div key={i} className="flex items-start gap-3 bg-[#161b22] shadow-sm border border-[#30363d] rounded-lg p-3.5 transition-colors hover:bg-[#1c2128]">
                          <CheckCircle className="w-4 h-4 text-cyan-500 shrink-0 mt-0.5 opacity-80" />
                          <span className="text-[12px] font-medium text-gray-200 leading-relaxed">{step}</span>
                        </div>
                      ))}
                    </div>
                 </div>
               )}
               
               {!item.fix_steps && item.fix_action && (
                 <div className="pt-2">
                    <h3 className="text-sm font-bold text-white mb-3 tracking-wide">Acción Sugerida</h3>
                    <div className="flex items-start gap-3 bg-[#161b22] shadow-sm border border-[#30363d] rounded-lg p-3.5 transition-colors hover:bg-[#1c2128]">
                      <Zap className="w-4 h-4 text-cyan-500 shrink-0 mt-0.5 opacity-80" />
                      <span className="text-[12px] font-medium text-gray-200 leading-relaxed">{item.fix_action}</span>
                    </div>
                 </div>
               )}

            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Fix Proposal Card ─────────────────────────────────────────────────────────
const RISK_STYLE = {
  low:    { badge: 'bg-green-500/15 text-green-400 border border-green-500/25',  icon: <ShieldCheck className="w-3.5 h-3.5 text-green-400" />,  label: 'RIESGO BAJO' },
  medium: { badge: 'bg-warn/15 text-warn border border-warn/25',                 icon: <ShieldAlert className="w-3.5 h-3.5 text-warn" />,       label: 'RIESGO MEDIO' },
  high:   { badge: 'bg-danger/15 text-danger border border-danger/25',           icon: <Shield className="w-3.5 h-3.5 text-danger" />,           label: 'RIESGO ALTO' },
  none:   { badge: 'bg-white/5 text-gray-500 border border-white/10',            icon: <Wrench className="w-3.5 h-3.5 text-gray-500" />,         label: 'MANUAL' },
};

function FixProposalCard({ hostingId }) {
  const [proposal, setProposal] = useState(null);
  const [loading, setLoading]   = useState(false);
  const [applying, setApplying] = useState(false);
  const [result, setResult]     = useState(null);
  const [error, setError]       = useState(null);

  useEffect(() => {
    if (!hostingId) return;
    let cancelled = false;
    setProposal(null);
    setResult(null);
    setError(null);
    setLoading(true);
    api.get(`/hosting/${hostingId}/fix`)
      .then(r => { if (!cancelled) setProposal(r.data?.proposed_fix ?? null); })
      .catch(() => { if (!cancelled) setProposal(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [hostingId]);

  const handleApply = useCallback(async () => {
    if (!proposal) return;
    setApplying(true);
    setResult(null);
    setError(null);
    try {
      const r = await api.post('/fix/apply', {
        hosting_id:  proposal.hosting_id,
        fingerprint: proposal.fingerprint,
        approved:    true,
      });
      setResult(r.data);
      if (r.data.success) setProposal(null); // consumed
    } catch (e) {
      setError(e?.response?.data?.detail ?? 'Error al aplicar el fix.');
    } finally {
      setApplying(false);
    }
  }, [proposal]);

  if (loading) {
    return (
      <div className="card-dash p-4 flex items-center gap-2 text-[10px] text-muted">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Buscando fix disponible…
      </div>
    );
  }

  // Show execution result even after proposal is consumed
  if (result) {
    return (
      <div className={`card-dash p-4 space-y-2 ${result.success ? 'border-green-500/30' : 'border-danger/30'}`}>
        <div className="flex items-center gap-2">
          {result.success
            ? <CheckCircle className="w-3.5 h-3.5 text-green-400" />
            : <AlertTriangle className="w-3.5 h-3.5 text-danger" />}
          <span className={`text-[11px] font-black ${result.success ? 'text-green-400' : 'text-danger'}`}>
            {result.success ? 'Fix aplicado correctamente' : 'Fix fallido'}
          </span>
          {result.rolled_back && (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-warn/10 text-warn border border-warn/20">
              ROLLBACK
            </span>
          )}
        </div>
        {result.error && <p className="text-[10px] text-red-400">{result.error}</p>}
        {result.stdout && (
          <pre className="text-[9px] font-mono text-gray-500 bg-white/3 rounded p-2 overflow-x-auto max-h-20">
            {result.stdout.trim()}
          </pre>
        )}
      </div>
    );
  }

  if (!proposal) return null;

  const risk = RISK_STYLE[proposal.risk_level] ?? RISK_STYLE.none;
  const canApply = proposal.can_auto_fix && proposal.risk_level !== 'high';

  return (
    <div className="card-dash p-4 space-y-3 border-accent/20">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Wrench className="w-3.5 h-3.5 text-accent" />
        <span className="text-[10px] font-mono text-accent uppercase tracking-widest flex-1">
          Fix Propuesto
        </span>
        <span className={`text-[9px] font-black px-2 py-0.5 rounded-lg ${risk.badge} flex items-center gap-1`}>
          {risk.icon} {risk.label}
        </span>
      </div>

      {/* Title + description */}
      <div>
        <div className="text-[12px] font-black text-white">{proposal.title}</div>
        <p className="text-[10px] text-gray-400 mt-0.5 leading-relaxed">{proposal.description}</p>
      </div>

      {/* Downtime */}
      <div className="flex items-center gap-4 text-[10px] text-muted">
        <span>
          <span className="text-gray-400 font-semibold">Acción:</span>{' '}
          <span className="font-mono text-accent">{proposal.action}</span>
        </span>
        <span>
          <span className="text-gray-400 font-semibold">Downtime estimado:</span>{' '}
          {proposal.estimated_downtime}
        </span>
      </div>

      {/* Manual fix notice */}
      {!proposal.can_auto_fix && (
        <div className="text-[10px] text-gray-500 italic border border-white/8 rounded-lg p-2">
          Este fix no se puede aplicar automáticamente. Requiere intervención manual del desarrollador.
        </div>
      )}

      {/* High-risk notice */}
      {proposal.risk_level === 'high' && (
        <div className="flex items-start gap-1.5 text-[10px] text-danger">
          <Shield className="w-3 h-3 mt-0.5 shrink-0" />
          Riesgo alto — aplica manualmente desde el panel de control.
        </div>
      )}

      {/* Error feedback */}
      {error && <p className="text-[10px] text-danger">{error}</p>}

      {/* CTA */}
      {canApply && (
        <button
          onClick={handleApply}
          disabled={applying}
          className="w-full py-2.5 rounded-xl bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all border border-accent/20 text-[11px] font-black uppercase tracking-wider flex items-center justify-center gap-2"
        >
          {applying
            ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Aplicando…</>
            : <><Zap className="w-3.5 h-3.5" /> Aprobar y Aplicar Fix</>}
        </button>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AIAdvisoryPage({ onDiagnose }) {
  const { hostings, healthData, alerts } = useDashboardData();
  const advisories = useAIAdvisory(hostings, healthData, alerts);

  const [selectedId, setSelectedId] = useState(null);

  // Auto-select the first (highest-severity) hosting when data loads or changes.
  // Only fires when nothing is selected — preserves explicit user selection.
  useEffect(() => {
    if (!selectedId && advisories.length > 0) {
      setSelectedId(advisories[0].hostingId);
    }
  }, [advisories, selectedId]);

  const selectedAdvisory = useMemo(
    () => advisories.find(a => a.hostingId === selectedId) ?? null,
    [advisories, selectedId],
  );

  const counts = useMemo(() => ({
    critical: advisories.filter(a => a.severity === 'critical').length,
    warning:  advisories.filter(a => a.severity === 'warning').length,
    ok:       advisories.filter(a => a.severity === 'ok').length,
  }), [advisories]);

  return (
    <div className="p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${counts.critical > 0 ? 'bg-danger/15' : 'bg-accent/10'}`}>
            <Bot className={`w-4 h-4 ${counts.critical > 0 ? 'text-danger' : 'text-accent'}`} />
          </div>
          <div>
            <div className="text-sm font-black text-white">AI Advisory Center</div>
            <div className="text-[10px] text-muted">Análisis en tiempo real de todos tus hostings</div>
          </div>
        </div>
        <SummaryBar counts={counts} />
      </div>

      {/* Main grid */}
      {advisories.length === 0 ? (
        <div className="card-dash p-8 text-center space-y-2">
          <Bot className="w-8 h-8 text-muted mx-auto" />
          <div className="text-sm text-muted">Sin hostings para analizar.</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">

          {/* Left — hosting list */}
          <div className="space-y-2">
            <div className="text-[10px] font-mono text-muted uppercase tracking-widest mb-3">
              {advisories.length} hosting{advisories.length !== 1 ? 's' : ''}
            </div>
            {advisories.map(a => (
              <HostingRow
                key={a.hostingId}
                advisory={a}
                isSelected={selectedAdvisory?.hostingId === a.hostingId}
                onClick={() => setSelectedId(a.hostingId)}
              />
            ))}
          </div>

          {/* Right — detail + history */}
          <div className="lg:col-span-2 space-y-4">
            {selectedAdvisory
              ? <DetailPanel advisory={selectedAdvisory} onDiagnose={onDiagnose} />
              : (
                <div className="card-dash p-8 text-center text-sm text-muted">
                  Seleccioná un hosting para ver el análisis.
                </div>
              )
            }

            {selectedAdvisory && (
              <>
                <div className="pt-2">
                  <DiagnosisHistory hostingId={selectedAdvisory.hostingId} />
                </div>
                <FixProposalCard hostingId={selectedAdvisory.hostingId} />
              </>
            )}
          </div>

        </div>
      )}

    </div>
  );
}
