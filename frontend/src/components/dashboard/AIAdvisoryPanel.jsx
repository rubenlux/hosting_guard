/**
 * AIAdvisoryPanel — deterministic advisory UI
 *
 * Pure presentation. Receives `advisories` from useAIAdvisory — no data
 * fetching or business logic here.
 *
 * Props:
 *   advisories  — Array<Advisory> sorted by severity (from useAIAdvisory)
 *   onDiagnose  — (hostingId) => void  — triggers full AI diagnosis
 */
import { useState } from 'react';
import { Bot, AlertTriangle, CheckCircle, ChevronDown, ChevronUp, Zap } from 'lucide-react';

const SEVERITY_CONFIG = {
  critical: {
    icon:       <AlertTriangle className="w-3.5 h-3.5" />,
    badge:      'bg-danger/20 text-danger border border-danger/30',
    label:      'CRÍTICO',
    dot:        'bg-danger',
    cardBorder: 'border-danger/30',
    cardBg:     'bg-danger/5',
  },
  warning: {
    icon:       <AlertTriangle className="w-3.5 h-3.5" />,
    badge:      'bg-warn/20 text-warn border border-warn/30',
    label:      'ADVERTENCIA',
    dot:        'bg-warn',
    cardBorder: 'border-warn/20',
    cardBg:     'bg-warn/5',
  },
  ok: {
    icon:       <CheckCircle className="w-3.5 h-3.5" />,
    badge:      'bg-green-500/20 text-green-400 border border-green-500/30',
    label:      'OK',
    dot:        'bg-green-500',
    cardBorder: 'border-white/5',
    cardBg:     'bg-white/2',
  },
};

function AdvisoryItem({ advisory, onDiagnose }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = SEVERITY_CONFIG[advisory.severity];

  return (
    <div className={`rounded-xl border p-3 ${cfg.cardBorder} ${cfg.cardBg} transition-all`}>
      <div
        className="flex items-start gap-2 cursor-pointer select-none"
        onClick={() => setExpanded(v => !v)}
      >
        <div className={`mt-0.5 shrink-0 ${advisory.severity === 'ok' ? 'text-green-400' : advisory.severity === 'critical' ? 'text-danger' : 'text-warn'}`}>
          {cfg.icon}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-bold text-white truncate">{advisory.hostingName}</span>
            <span className={`text-[9px] font-black px-1.5 py-0.5 rounded uppercase tracking-wider ${cfg.badge}`}>
              {cfg.label}
            </span>
          </div>
          <p className="text-[10px] text-gray-400 mt-0.5 leading-snug">{advisory.summary}</p>
        </div>

        <div className="shrink-0 text-muted mt-0.5">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </div>
      </div>

      {expanded && (
        <div className="mt-3 pl-5 space-y-2">
          {advisory.signals.length > 1 && (
            <ul className="space-y-1">
              {advisory.signals.map((s, i) => (
                <li key={i} className="flex items-start gap-1.5 text-[10px] text-gray-400">
                  <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot}`} />
                  {s}
                </li>
              ))}
            </ul>
          )}

          <div className="flex items-start gap-1.5 text-[10px] text-accent">
            <Zap className="w-3 h-3 mt-0.5 shrink-0" />
            <span>{advisory.recommendation}</span>
          </div>

          {advisory.severity !== 'ok' && onDiagnose && (
            <button
              onClick={(e) => { e.stopPropagation(); onDiagnose(advisory.hostingId); }}
              className="mt-1 text-[9px] font-black uppercase tracking-wider px-3 py-1.5 rounded-lg bg-accent/10 text-accent hover:bg-accent/20 transition-all border border-accent/20"
            >
              Ejecutar diagnóstico IA →
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function AIAdvisoryPanel({ advisories, onDiagnose }) {
  const attention = advisories.filter(a => a.requiresAttention);
  const criticalCount = advisories.filter(a => a.severity === 'critical').length;
  const warningCount  = advisories.filter(a => a.severity === 'warning').length;

  return (
    <div className="card-dash p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-accent" />
          <span className="text-xs font-bold">AI Advisory</span>
        </div>
        <div className="flex items-center gap-1.5">
          {criticalCount > 0 && (
            <span className="text-[9px] font-black px-1.5 py-0.5 rounded bg-danger/20 text-danger border border-danger/30 animate-pulse">
              {criticalCount} CRÍTICO{criticalCount !== 1 ? 'S' : ''}
            </span>
          )}
          {warningCount > 0 && (
            <span className="text-[9px] font-black px-1.5 py-0.5 rounded bg-warn/20 text-warn border border-warn/30">
              {warningCount} AVISO{warningCount !== 1 ? 'S' : ''}
            </span>
          )}
          {attention.length === 0 && (
            <span className="text-[9px] font-black px-1.5 py-0.5 rounded bg-green-500/20 text-green-400 border border-green-500/30">
              TODO OK
            </span>
          )}
        </div>
      </div>

      {/* Items */}
      {attention.length === 0 ? (
        <div className="flex items-center gap-3 p-3 rounded-xl bg-green-500/5 border border-green-500/15">
          <CheckCircle className="w-4 h-4 text-green-400 shrink-0" />
          <div>
            <div className="text-[11px] font-bold text-green-400">Sistema estable</div>
            <div className="text-[10px] text-gray-500">Todos los hostings operando con normalidad.</div>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {attention.map(advisory => (
            <AdvisoryItem
              key={advisory.hostingId}
              advisory={advisory}
              onDiagnose={onDiagnose}
            />
          ))}
        </div>
      )}
    </div>
  );
}
