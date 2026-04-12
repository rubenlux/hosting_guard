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
import { useState, useMemo } from 'react';
import { Bot, AlertTriangle, CheckCircle, Zap, Activity } from 'lucide-react';
import { useDashboardData } from '../hooks/useDashboardData';
import { useAIAdvisory } from '../hooks/useAIAdvisory';

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
        <span className={`text-[9px] font-black px-2 py-1 rounded-lg ${cfg.badge} ${isCritical ? 'animate-pulse' : ''}`}>
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

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AIAdvisoryPage({ onDiagnose }) {
  const { hostings, healthData, alerts } = useDashboardData();
  const advisories = useAIAdvisory(hostings, healthData, alerts);

  const [selectedId, setSelectedId] = useState(null);

  const selectedAdvisory = useMemo(
    () => advisories.find(a => a.hostingId === selectedId) ?? advisories[0] ?? null,
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

          {/* Right — detail */}
          <div className="lg:col-span-2">
            {selectedAdvisory
              ? <DetailPanel advisory={selectedAdvisory} onDiagnose={onDiagnose} />
              : (
                <div className="card-dash p-8 text-center text-sm text-muted">
                  Seleccioná un hosting para ver el análisis.
                </div>
              )
            }
          </div>

        </div>
      )}

    </div>
  );
}
