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
    // Stronger border + glow for critical items
    cardBorder: 'border-danger/50',
    cardBg:     'bg-danger/8',
    cardGlow:   '0 0 0 1px rgba(255,68,68,0.15), 0 4px 20px rgba(255,68,68,0.12)',
  },
  warning: {
    icon:       <AlertTriangle className="w-3.5 h-3.5" />,
    badge:      'bg-warn/20 text-warn border border-warn/30',
    label:      'ADVERTENCIA',
    dot:        'bg-warn',
    cardBorder: 'border-warn/20',
    cardBg:     'bg-warn/5',
    cardGlow:   'none',
  },
  ok: {
    icon:       <CheckCircle className="w-3.5 h-3.5" />,
    badge:      'bg-green-500/20 text-green-400 border border-green-500/30',
    label:      'OK',
    dot:        'bg-green-500',
    cardBorder: 'border-gray-200',
    cardBg:     'bg-white/2',
    cardGlow:   'none',
  },
};

function AdvisoryItem({ advisory, onDiagnose }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = SEVERITY_CONFIG[advisory.severity];
  const isCritical = advisory.severity === 'critical';

  return (
    <div
      className={`rounded-xl border p-3 ${cfg.cardBorder} ${cfg.cardBg} transition-all ${isCritical ? 'animate-pulse-border' : ''}`}
      style={isCritical ? { boxShadow: cfg.cardGlow } : undefined}
    >
      <div
        className="flex items-start gap-2 cursor-pointer select-none"
        onClick={() => setExpanded(v => !v)}
      >
        <div className={`mt-0.5 shrink-0 ${isCritical ? 'text-danger animate-pulse' : advisory.severity === 'ok' ? 'text-green-400' : 'text-warn'}`}>
          {cfg.icon}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-bold text-gray-900 truncate">{advisory.hostingName}</span>
            <span className={`text-[9px] font-black px-1.5 py-0.5 rounded uppercase tracking-wider ${cfg.badge} ${isCritical ? 'animate-pulse' : ''}`}>
              {cfg.label}
            </span>
          </div>
          <p className={`text-[10px] mt-0.5 leading-snug ${isCritical ? 'text-gray-300' : 'text-gray-400'}`}>
            {advisory.summary}
          </p>
        </div>

        <div className="shrink-0 text-muted mt-0.5">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </div>
      </div>

      {expanded && (
        <div className="mt-3 pl-5 space-y-2">
          {advisory.signals.length > 0 && (
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
              Diagnosticar problema →
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
    <div className={`p-4 space-y-3 rounded-xl shadow-sm ${criticalCount > 0 ? 'bg-red-50 border border-red-200 text-red-700' : warningCount > 0 ? 'bg-amber-50 border border-amber-200 text-amber-700' : 'bg-emerald-50 border border-emerald-200 text-emerald-700'}`}
      style={criticalCount > 0 ? { boxShadow: '0 0 0 1px rgba(255,68,68,0.1), 0 8px 32px rgba(255,68,68,0.08)' } : undefined}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className={`w-4 h-4 ${criticalCount > 0 ? 'text-red-600' : warningCount > 0 ? 'text-amber-600' : 'text-emerald-600'}`} />
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
            <span className="text-[9px] font-black px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 border border-emerald-200">
              TODO OK
            </span>
          )}
        </div>
      </div>

      {/* Items */}
      {attention.length === 0 ? (
        <div className="flex items-center gap-3 p-3">
          <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
          <div>
            <div className="text-[11px] font-bold text-emerald-700">Sistema estable</div>
            <div className="text-[10px] text-emerald-600/80">Todos los hostings operando con normalidad.</div>
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
