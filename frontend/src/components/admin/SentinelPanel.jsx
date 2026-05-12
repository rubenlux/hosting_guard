import React, {
  useEffect, useState, useCallback, useMemo, memo,
} from 'react';
import {
  ShieldAlert, RefreshCw, CheckCircle2, ChevronDown,
  Copy, Loader2, AlertTriangle, Terminal, Globe, Cpu, Zap, Brain,
} from 'lucide-react';
import {
  getSentinelIncidents, resolveIncident, getDiagnosis, triggerDiagnose,
  getIncidentActions, generateActions, approveAction, rejectAction,
  generateActionPlan, getActionPlans, cancelPlan,
} from '../../services/api';

// ─── stable constants (never recreated) ──────────────────────────────────────

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

// ─── report builder ───────────────────────────────────────────────────────────

function buildReport(inc, diag, actions = []) {
  const ev = inc.evidence || {};
  const lines = [
    'INFORME DE INCIDENTE — HostingGuard',
    '─'.repeat(40),
    `Título:       ${inc.title}`,
    `Tipo:         ${inc.incident_type}`,
    `Fuente:       ${inc.source_type}`,
    `Severidad:    ${inc.severity}`,
    `Estado:       ${inc.status}`,
    `Detectado:    ${fmt(inc.first_seen)}`,
    `Último aviso: ${fmt(inc.last_seen)}`,
    `Apariciones:  ${inc.count}`,
  ];
  if (ev.repo_url)      lines.push(`Repositorio:  ${ev.repo_url}`);
  if (ev.branch)        lines.push(`Rama:         ${ev.branch}`);
  if (ev.project_name)  lines.push(`Proyecto:     ${ev.project_name}`);
  if (ev.stage)         lines.push(`Etapa:        ${ev.stage}`);
  if (ev.message)       lines.push('', `Descripción:  ${ev.message}`);
  if (ev.suggested_fix) lines.push('', 'Solución sugerida:', ev.suggested_fix);

  if (diag?.summary) {
    lines.push('', '─'.repeat(40), 'DIAGNÓSTICO IA');
    lines.push(`Resumen: ${diag.summary}`);
    if (diag.root_cause)       lines.push(`Causa raíz: ${diag.root_cause}`);
    if (diag.customer_message) lines.push('', `Mensaje al usuario: ${diag.customer_message}`);
    const steps = diag.recommended_next_steps;
    if (Array.isArray(steps) && steps.length) {
      lines.push('', 'Próximos pasos:');
      steps.forEach((s, i) => lines.push(`  ${i + 1}. ${s}`));
    }
    if (diag.confidence != null)
      lines.push('', `Confianza: ${Math.round(diag.confidence * 100)}%`);
  }

  const visibleActions = actions.filter(a => a.status !== 'blocked_by_policy');
  if (visibleActions.length > 0) {
    lines.push('', '─'.repeat(40), 'ACCIONES RECOMENDADAS');
    visibleActions.forEach((a, i) => {
      const riskLabel   = RISK_LABEL[a.risk_level]  || a.risk_level;
      const statusLabel = STATUS_LABEL[a.status]    || a.status;
      const ownerLabel  = a.owner_label || '—';
      lines.push(`${i + 1}. ${a.title}`);
      lines.push(`   Responsable: ${ownerLabel}`);
      lines.push(`   Riesgo: ${riskLabel}`);
      lines.push(`   Estado: ${statusLabel}`);
    });
    lines.push(
      '',
      'Nota: HostingGuard no ejecutó cambios sobre tu sitio ni repositorio.',
    );
  }

  lines.push('', '─'.repeat(40), 'Generado por HostingGuard AI Sentinel');
  return lines.join('\n');
}

// ─── skeleton ─────────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <div className="border border-white/5 bg-[#111] rounded-xl p-4 animate-pulse">
      <div className="flex items-start gap-3">
        <div className="w-3.5 h-3.5 rounded-full bg-white/10 mt-0.5 shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="flex gap-2 items-center">
            <div className="h-3.5 bg-white/8 rounded w-52" />
            <div className="h-4 bg-white/6 rounded w-14" />
          </div>
          <div className="h-3 bg-white/5 rounded w-36" />
        </div>
      </div>
    </div>
  );
}

// ─── DiagnosisPanel ───────────────────────────────────────────────────────────

const DiagnosisPanel = memo(function DiagnosisPanel({
  incidentId,
  diagSummary, diagRootCause, diagSteps, diagCustomerMessage,
  diagConfidence, diagSource, diagUpdatedAt,
  onDiagReady,
}) {
  const [diag, setDiag] = useState(() =>
    diagSummary
      ? {
          summary:                diagSummary,
          root_cause:             diagRootCause,
          recommended_next_steps: diagSteps,
          customer_message:       diagCustomerMessage,
          confidence:             diagConfidence,
          fingerprint:            diagSource,
          updated_at:             diagUpdatedAt,
        }
      : null
  );
  const [status, setStatus] = useState('idle'); // 'idle' | 'generating' | 'regenerating'
  const [error, setError]   = useState(null);

  // Sync if parent fetched fresher diagnosis data (compare updated_at string)
  useEffect(() => {
    if (diagUpdatedAt && diag?.updated_at !== diagUpdatedAt) {
      setDiag({
        summary:                diagSummary,
        root_cause:             diagRootCause,
        recommended_next_steps: diagSteps,
        customer_message:       diagCustomerMessage,
        confidence:             diagConfidence,
        fingerprint:            diagSource,
        updated_at:             diagUpdatedAt,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [diagUpdatedAt]);

  const isGenerating   = status === 'generating';
  const isRegenerating = status === 'regenerating';
  const isLoading      = isGenerating || isRegenerating;
  const isRuleBased    = diag?.fingerprint === 'rule_based';
  const steps          = diag?.recommended_next_steps;
  const confidence     = diag?.confidence;

  async function handleTrigger() {
    setStatus(diag ? 'regenerating' : 'generating');
    setError(null);
    try {
      await triggerDiagnose(incidentId);
      // Give the background task time to complete
      await new Promise(r => setTimeout(r, 2500));
      const fresh = await getDiagnosis(incidentId);
      setDiag(fresh);
      onDiagReady?.(fresh);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error al generar diagnóstico');
    } finally {
      setStatus('idle');
    }
  }

  return (
    <div className="border border-white/8 rounded-lg overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-white/[0.02] border-b border-white/5">
        <div className="flex items-center gap-1.5 text-[10px] text-purple-400 uppercase tracking-wide font-medium">
          <Brain className="w-3 h-3" />
          Diagnóstico IA
          {isRuleBased && (
            <span className="text-gray-600 normal-case tracking-normal font-normal">(reglas)</span>
          )}
          {isRegenerating && (
            <span className="flex items-center gap-1 text-purple-400/60 normal-case tracking-normal font-normal ml-1">
              <Loader2 className="w-2.5 h-2.5 animate-spin" />
              Regenerando…
            </span>
          )}
        </div>
        <button
          data-testid="diagnose-btn"
          onClick={handleTrigger}
          disabled={isLoading}
          className="flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-purple-500/10 text-purple-400 border border-purple-500/20 hover:bg-purple-500/20 transition-colors disabled:opacity-40"
        >
          {isGenerating
            ? <Loader2 className="w-3 h-3 animate-spin" />
            : <Brain className="w-3 h-3" />}
          {diag ? 'Regenerar' : 'Generar diagnóstico'}
        </button>
      </div>

      {/* Body */}
      <div className="px-3 pb-3 pt-2.5 min-h-[3rem]">
        {error && (
          <p className="text-xs text-red-400 mb-2">{error}</p>
        )}

        {isGenerating && !diag && (
          <div className="flex items-center gap-1.5 text-xs text-gray-500 py-2">
            <Loader2 className="w-3 h-3 animate-spin" />
            Analizando incidente…
          </div>
        )}

        {!diag && !isGenerating && !error && (
          <p className="text-xs text-gray-600 py-1">Sin diagnóstico IA todavía.</p>
        )}

        {diag && (
          <div
            className={`space-y-2 transition-opacity duration-200 ${
              isRegenerating ? 'opacity-40' : 'opacity-100'
            }`}
          >
            {diag.summary && (
              <p className="text-xs text-gray-300">{diag.summary}</p>
            )}
            {diag.root_cause && (
              <div>
                <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-0.5">Causa raíz</div>
                <p className="text-xs text-gray-400">{diag.root_cause}</p>
              </div>
            )}
            {Array.isArray(steps) && steps.length > 0 && (
              <div>
                <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-1">Próximos pasos</div>
                <ol className="space-y-0.5">
                  {steps.map((s, i) => (
                    <li key={i} className="flex gap-1.5 text-xs text-gray-400">
                      <span className="text-purple-500 shrink-0">{i + 1}.</span>
                      {s}
                    </li>
                  ))}
                </ol>
              </div>
            )}
            {diag.customer_message && (
              <div className="bg-blue-500/5 border border-blue-500/15 rounded p-2">
                <div className="text-[10px] text-blue-500 uppercase tracking-wide mb-0.5">Mensaje al usuario</div>
                <p className="text-xs text-blue-300">{diag.customer_message}</p>
              </div>
            )}
            {confidence != null && (
              <div className="flex items-center gap-2 pt-0.5">
                <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-purple-500/60 rounded-full transition-all duration-500"
                    style={{ width: `${Math.round(confidence * 100)}%` }}
                  />
                </div>
                <span className="text-[10px] text-gray-600">
                  {Math.round(confidence * 100)}% confianza
                </span>
              </div>
            )}
            {diag.updated_at && (
              <div className="text-[10px] text-gray-700">{fmt(diag.updated_at)}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

// ─── PlanCard ─────────────────────────────────────────────────────────────────

const PLAN_STATUS_LABEL = {
  draft:              'Borrador',
  ready_for_review:   'Listo para revisión',
  blocked_by_policy:  'Bloqueado por política',
  superseded:         'Reemplazado',
  cancelled:          'Cancelado',
};

const PLAN_STATUS_CLASS = {
  draft:             'text-amber-400',
  ready_for_review:  'text-emerald-400',
  blocked_by_policy: 'text-red-400',
  superseded:        'text-gray-600',
  cancelled:         'text-gray-600',
};

function PlanCard({ plan, onCancel, isCancelling }) {
  const [expanded, setExpanded] = useState(false);
  const statusLabel = PLAN_STATUS_LABEL[plan.status] || plan.status;
  const statusClass = PLAN_STATUS_CLASS[plan.status] || 'text-gray-400';
  const riskLabel   = RISK_LABEL[plan.risk_level] || plan.risk_level;
  const riskClass   = RISK_CLASS[plan.risk_level]  || RISK_CLASS.medium;

  const steps        = Array.isArray(plan.steps)         ? plan.steps         : [];
  const prechecks    = Array.isArray(plan.prechecks)      ? plan.prechecks      : [];
  const rollback     = Array.isArray(plan.rollback_steps) ? plan.rollback_steps : [];

  return (
    <div
      data-testid="plan-card"
      className="border border-white/6 rounded-lg bg-black/30 overflow-hidden"
    >
      {/* Plan header */}
      <div
        className="flex items-start justify-between gap-2 px-2.5 py-2 cursor-pointer hover:bg-white/[0.02] transition-colors"
        onClick={() => setExpanded(v => !v)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] font-medium text-white/80 leading-snug">{plan.title}</span>
            <span className={`text-[10px] ${statusClass}`} data-testid="plan-status-label">
              {statusLabel}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${riskClass}`}>
              {riskLabel}
            </span>
          </div>
          <p className="text-[10px] text-gray-600 mt-0.5" data-testid="plan-no-execute-notice">
            Este plan no ejecuta comandos. Solo describe un procedimiento seguro para revisión.
          </p>
        </div>
        <ChevronDown
          className={`w-3.5 h-3.5 text-gray-600 shrink-0 mt-0.5 transition-transform duration-150 ${
            expanded ? 'rotate-0' : '-rotate-90'
          }`}
        />
      </div>

      {/* Expandable body */}
      <div
        className={`grid transition-[grid-template-rows] duration-150 ease-out ${
          expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
        }`}
      >
        <div className="overflow-hidden min-h-0">
          <div className="border-t border-white/5 px-2.5 py-2 space-y-2">
            {plan.summary && (
              <p className="text-[11px] text-gray-400">{plan.summary}</p>
            )}

            {plan.blocked_reason && (
              <p className="text-[10px] text-red-400" data-testid="plan-blocked-reason">
                {plan.blocked_reason}
              </p>
            )}

            {prechecks.length > 0 && (
              <div>
                <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-0.5">Verificaciones previas</div>
                <ol className="space-y-0.5">
                  {prechecks.map((p, i) => (
                    <li key={i} className="flex gap-1.5 text-[10px] text-gray-400">
                      <span className="text-amber-500 shrink-0">{p.order ?? i + 1}.</span>
                      {p.description}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {steps.length > 0 && (
              <div>
                <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-0.5">Pasos</div>
                <ol className="space-y-0.5">
                  {steps.map((s, i) => (
                    <li key={i} className="flex gap-1.5 text-[10px] text-gray-400">
                      <span className="text-blue-500 shrink-0">{s.order ?? i + 1}.</span>
                      {s.description}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {rollback.length > 0 && (
              <div>
                <div className="text-[10px] text-gray-600 uppercase tracking-wide mb-0.5">Rollback</div>
                <ol className="space-y-0.5">
                  {rollback.map((r, i) => (
                    <li key={i} className="flex gap-1.5 text-[10px] text-gray-400">
                      <span className="text-red-500 shrink-0">{r.order ?? i + 1}.</span>
                      {r.description}
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {plan.safety_notes && (
              <p className="text-[10px] text-gray-600">
                <span className="text-gray-500">Seguridad: </span>{plan.safety_notes}
              </p>
            )}

            {/* execution_allowed is ALWAYS false — never show Ejecutar */}
            <div className="flex items-center gap-2 pt-0.5">
              {plan.status !== 'cancelled' && (
                <button
                  data-testid="cancel-plan-btn"
                  onClick={() => onCancel(plan.plan_id)}
                  disabled={isCancelling}
                  className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-white/5 text-gray-500 border border-white/8 hover:bg-white/8 transition-colors disabled:opacity-40"
                >
                  {isCancelling ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : null}
                  Cancelar plan
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── ActionsPanel ─────────────────────────────────────────────────────────────

const RISK_CLASS = {
  low:      'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  medium:   'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
  high:     'text-orange-400 bg-orange-500/10 border-orange-500/30',
  critical: 'text-red-400 bg-red-500/10 border-red-500/30',
};

const RISK_LABEL = {
  low:      'Bajo',
  medium:   'Medio',
  high:     'Alto',
  critical: 'Crítico',
};

const RISK_TOOLTIP = {
  low:      'Recomendación informativa o de bajo impacto. No cambia infraestructura.',
  medium:   'Requiere revisión operativa antes de aplicar.',
  high:     'Puede afectar disponibilidad, tráfico o configuración. Requiere aprobación estricta.',
  critical: 'No permitido para ejecución automática.',
};

const STATUS_LABEL = {
  pending_approval:  'Pendiente de revisión',
  approved:          'Aprobada, no ejecutada',
  rejected:          'Rechazada',
  superseded:        'Reemplazada',
  blocked_by_policy: 'Bloqueada por política',
};

const STATUS_CLASS = {
  pending_approval:  'text-gray-400',
  approved:          'text-emerald-400',
  rejected:          'text-red-400',
  superseded:        'text-gray-600',
  blocked_by_policy: 'text-red-500',
};

const ActionsPanel = memo(function ActionsPanel({ incidentId, hasDiagnosis, onActionsLoaded, incidentStatus = 'open' }) {
  const [actions, setActions]         = useState([]);
  const [status, setStatus]           = useState('idle'); // idle | loading | generating
  const [error, setError]             = useState(null);
  const [actingId, setActingId]       = useState(null);
  const [confirmId, setConfirmId]     = useState(null); // action_id pending confirm
  const [plansMap, setPlansMap]       = useState({});   // action_id → plan | null
  const [planGenId, setPlanGenId]     = useState(null); // action_id currently generating plan
  const [planCancelId, setPlanCancelId] = useState(null); // plan_id being cancelled

  const load = useCallback(async () => {
    setStatus('loading');
    setError(null);
    try {
      const data = await getIncidentActions(incidentId);
      const items = data.items || [];
      setActions(items);
      onActionsLoaded?.(items);
      // Load plans for approved actions
      const approvedIds = items
        .filter(a => a.status === 'approved')
        .map(a => a.action_id);
      if (approvedIds.length > 0) {
        const results = await Promise.all(
          approvedIds.map(id => getActionPlans(id).then(d => ({ id, plans: d.items || [] })))
        );
        const map = {};
        results.forEach(({ id, plans }) => {
          const active = plans.find(p => p.status !== 'cancelled');
          map[id] = active || null;
        });
        setPlansMap(map);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error al cargar acciones');
    } finally {
      setStatus('idle');
    }
  }, [incidentId]);

  useEffect(() => { load(); }, [load]);

  const hasActions = actions.length > 0;

  async function handleGenerate() {
    // Use force=true when re-generating over existing actions (picks up new rules copy).
    const force = hasActions;
    setStatus('generating');
    setError(null);
    try {
      await generateActions(incidentId, force);
      await new Promise(r => setTimeout(r, 1500));
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error al generar recomendaciones');
      setStatus('idle');
    }
  }

  async function handleApprove(actionId) {
    setConfirmId(null);
    setActingId(actionId);
    try {
      await approveAction(actionId);
      setActions(prev => prev.map(a =>
        a.action_id === actionId
          ? { ...a, status: 'approved', can_approve: false, can_reject: true }
          : a,
      ));
      // Initialize plan slot for this newly approved action
      setPlansMap(prev => ({ ...prev, [actionId]: prev[actionId] ?? null }));
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error al aprobar acción');
    } finally {
      setActingId(null);
    }
  }

  async function handleGeneratePlan(actionId) {
    setPlanGenId(actionId);
    try {
      const result = await generateActionPlan(actionId);
      setPlansMap(prev => ({ ...prev, [actionId]: result.plan || null }));
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error al generar plan');
    } finally {
      setPlanGenId(null);
    }
  }

  async function handleCancelPlan(planId, actionId) {
    setPlanCancelId(planId);
    try {
      await cancelPlan(planId);
      setPlansMap(prev => ({
        ...prev,
        [actionId]: prev[actionId] ? { ...prev[actionId], status: 'cancelled' } : null,
      }));
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error al cancelar plan');
    } finally {
      setPlanCancelId(null);
    }
  }

  async function handleReject(actionId) {
    setActingId(actionId);
    try {
      await rejectAction(actionId);
      setActions(prev => prev.map(a =>
        a.action_id === actionId
          ? { ...a, status: 'rejected', can_approve: false, can_reject: false }
          : a,
      ));
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error al rechazar acción');
    } finally {
      setActingId(null);
    }
  }

  const isLoading    = status === 'loading';
  const isGenerating = status === 'generating';
  const isResolved   = incidentStatus === 'resolved';

  return (
    <div className="border border-white/8 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-white/[0.02] border-b border-white/5">
        <div className="flex items-center gap-1.5 text-[10px] text-amber-400 uppercase tracking-wide font-medium">
          <Zap className="w-3 h-3" />
          Acciones recomendadas
          {actions.length > 0 && (
            <span className="text-gray-600 normal-case tracking-normal font-normal ml-1">
              ({actions.length})
            </span>
          )}
        </div>
        {!isResolved && (
          <button
            data-testid="generate-actions-btn"
            onClick={handleGenerate}
            disabled={isLoading || isGenerating || !hasDiagnosis}
            title={!hasDiagnosis ? 'Genera un diagnóstico primero' : undefined}
            className="flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors disabled:opacity-40"
          >
            {isGenerating
              ? <Loader2 className="w-3 h-3 animate-spin" />
              : <Zap className="w-3 h-3" />}
            {isGenerating ? 'Generando…' : hasActions ? 'Regenerar recomendaciones' : 'Generar recomendaciones'}
          </button>
        )}
      </div>

      {/* Persistent notices */}
      <div className="px-3 pt-2 pb-0 space-y-1">
        {isResolved ? (
          <p className="text-[10px] text-gray-500 leading-snug" data-testid="resolved-notice">
            Este incidente ya está resuelto. No se generan nuevas acciones recomendadas.
          </p>
        ) : (
          <p className="text-[10px] text-gray-600 leading-snug" data-testid="phase-notice">
            En esta fase, aprobar una recomendación solo registra la decisión. No ejecuta comandos,
            no reinicia servicios y no modifica infraestructura.
          </p>
        )}
      </div>

      {/* Body */}
      <div className="px-3 pb-3 pt-2">
        {error && <p className="text-xs text-red-400 mb-2">{error}</p>}

        {isLoading && (
          <div className="flex items-center gap-1.5 text-xs text-gray-500 py-2">
            <Loader2 className="w-3 h-3 animate-spin" />
            Cargando…
          </div>
        )}

        {!isLoading && actions.length === 0 && !isResolved && (
          <p className="text-xs text-gray-600 py-1">
            {hasDiagnosis
              ? 'Sin recomendaciones todavía. Haz clic en "Generar recomendaciones".'
              : 'Genera un diagnóstico IA antes de generar recomendaciones.'}
          </p>
        )}

        {actions.length > 0 && (
          <div className="space-y-2">
            {actions.map(action => {
              const riskClass   = RISK_CLASS[action.risk_level] || RISK_CLASS.medium;
              const riskLabel   = RISK_LABEL[action.risk_level]  || action.risk_level;
              const riskTip     = RISK_TOOLTIP[action.risk_level] || '';
              const statusLabel = STATUS_LABEL[action.status]    || action.status;
              const statusClass = STATUS_CLASS[action.status]    || 'text-gray-500';
              const isPending      = action.status === 'pending_approval';
              const isApproved     = action.status === 'approved';
              const isBlocked      = action.status === 'blocked_by_policy';
              const isBusy         = actingId === action.action_id;
              const isConfirm      = confirmId === action.action_id;
              const canApprove     = action.can_approve ?? isPending;
              const canReject      = action.can_reject  ?? isPending;
              const existingPlan   = plansMap[action.action_id];
              const isGenPlan      = planGenId === action.action_id;
              const hasPlan        = isApproved && existingPlan && existingPlan.status !== 'cancelled';

              return (
                <div
                  key={action.action_id}
                  data-testid="action-card"
                  className="border border-white/6 rounded-lg p-2.5 bg-black/20 space-y-1.5"
                >
                  {/* Title + badges */}
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs text-white/85 font-medium leading-snug">
                      {action.title}
                    </span>
                    <div className="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded border ${riskClass}`}
                        title={riskTip}
                        data-testid="risk-badge"
                      >
                        {riskLabel}
                      </span>
                      <span className={`text-[10px] ${statusClass}`} data-testid="status-label">
                        {statusLabel}
                      </span>
                    </div>
                  </div>

                  {/* Meta row: owner + requires_approval */}
                  <div className="flex items-center gap-3 text-[10px] text-gray-600">
                    {action.owner_label && (
                      <span data-testid="owner-label">
                        <span className="text-gray-500">Responsable: </span>{action.owner_label}
                      </span>
                    )}
                    {action.requires_approval && (
                      <span className="text-gray-700">Requiere aprobación</span>
                    )}
                  </div>

                  {/* Description */}
                  {action.description && (
                    <p className="text-[11px] text-gray-400">{action.description}</p>
                  )}

                  {/* Impact */}
                  {action.expected_impact && (
                    <p className="text-[10px] text-gray-600">
                      <span className="text-gray-500">Impacto esperado: </span>{action.expected_impact}
                    </p>
                  )}

                  {/* Safety notes */}
                  {action.safety_notes && (
                    <p className="text-[10px] text-gray-600">
                      <span className="text-gray-500">Seguridad: </span>{action.safety_notes}
                    </p>
                  )}

                  {/* Approved state notice + plan controls */}
                  {isApproved && (
                    <div className="space-y-1.5">
                      <p className="text-[10px] text-emerald-600" data-testid="approved-notice">
                        Esta recomendación fue aprobada, pero todavía no existe ejecución automática en esta fase.
                      </p>
                      {!hasPlan && (
                        <button
                          data-testid="generate-plan-btn"
                          onClick={() => handleGeneratePlan(action.action_id)}
                          disabled={isGenPlan}
                          className="flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors disabled:opacity-40"
                        >
                          {isGenPlan ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : null}
                          {isGenPlan ? 'Generando plan…' : 'Generar plan'}
                        </button>
                      )}
                      {hasPlan && (
                        <PlanCard
                          plan={existingPlan}
                          onCancel={planId => handleCancelPlan(planId, action.action_id)}
                          isCancelling={planCancelId === existingPlan.plan_id}
                        />
                      )}
                    </div>
                  )}

                  {/* Blocked state notice */}
                  {isBlocked && (
                    <p className="text-[10px] text-red-500" data-testid="blocked-notice">
                      Esta acción no puede ejecutarse desde HostingGuard.
                    </p>
                  )}

                  {/* Approve confirmation inline */}
                  {isConfirm && (
                    <div className="flex items-center gap-2 pt-0.5 bg-amber-500/5 border border-amber-500/20 rounded px-2 py-1.5">
                      <span className="text-[10px] text-amber-400 flex-1">
                        ¿Aprobar esta recomendación? Esto no ejecutará la acción.
                      </span>
                      <button
                        data-testid="confirm-approve-btn"
                        onClick={() => handleApprove(action.action_id)}
                        disabled={isBusy}
                        className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25 transition-colors disabled:opacity-40"
                      >
                        Confirmar
                      </button>
                      <button
                        onClick={() => setConfirmId(null)}
                        className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-gray-500 border border-white/8 hover:bg-white/8 transition-colors"
                      >
                        Cancelar
                      </button>
                    </div>
                  )}

                  {/* Approve / Reject buttons — only for eligible statuses, not in confirm mode */}
                  {!isConfirm && (canApprove || canReject) && (
                    <div className="flex items-center gap-2 pt-0.5">
                      {canApprove && (
                        <button
                          data-testid="approve-btn"
                          onClick={() => setConfirmId(action.action_id)}
                          disabled={isBusy}
                          className="flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 transition-colors disabled:opacity-40"
                        >
                          <CheckCircle2 className="w-2.5 h-2.5" />
                          Aprobar
                        </button>
                      )}
                      {canReject && (
                        <button
                          data-testid="reject-btn"
                          onClick={() => handleReject(action.action_id)}
                          disabled={isBusy}
                          className="flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20 transition-colors disabled:opacity-40"
                        >
                          {isBusy ? <Loader2 className="w-2.5 h-2.5 animate-spin" /> : <AlertTriangle className="w-2.5 h-2.5" />}
                          Rechazar
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
});

// ─── IncidentRow ──────────────────────────────────────────────────────────────

const IncidentRow = memo(function IncidentRow({ inc, expanded, onToggle, onResolved }) {
  const [resolving, setResolving]         = useState(false);
  const [copied, setCopied]               = useState(false);
  const [currentDiag, setCurrentDiag]     = useState(null);
  const [currentActions, setCurrentActions] = useState([]);

  const ev       = inc.evidence || {};
  const sevClass = SEV[inc.severity] || SEV.info;
  const isOpen   = inc.status === 'open';

  async function handleResolve() {
    if (!window.confirm(`¿Resolver incidente #${inc.incident_id}?`)) return;
    setResolving(true);
    try {
      await resolveIncident(inc.incident_id);
      onResolved(inc.incident_id);
    } catch {
      alert('Error al resolver el incidente.');
    } finally {
      setResolving(false);
    }
  }

  function handleCopy() {
    const diagForReport = currentDiag ?? (inc.diagnosis_summary ? {
      summary:                inc.diagnosis_summary,
      root_cause:             inc.diagnosis_root_cause,
      recommended_next_steps: inc.diagnosis_steps,
      customer_message:       inc.diagnosis_customer_message,
      confidence:             inc.diagnosis_confidence,
    } : null);
    navigator.clipboard.writeText(buildReport(inc, diagForReport, currentActions)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div
      data-incident-id={inc.incident_id}
      className={`border rounded-xl overflow-hidden transition-colors duration-150 ${
        isOpen ? 'border-white/10 bg-[#111]' : 'border-white/5 bg-[#0d0d0f]'
      }`}
    >
      {/* Header — always visible */}
      <div
        className="flex items-start gap-3 p-4 cursor-pointer hover:bg-white/[0.025] transition-colors select-none"
        onClick={() => onToggle(inc.incident_id)}
      >
        <span className={`mt-0.5 shrink-0 ${sevClass.split(' ')[0]}`}>
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
        <ChevronDown
          className={`w-4 h-4 text-gray-600 shrink-0 mt-0.5 transition-transform duration-200 ${
            expanded ? 'rotate-0' : '-rotate-90'
          }`}
        />
      </div>

      {/* Accordion — CSS grid trick: smooth height, always-mounted children */}
      <div
        className={`grid transition-[grid-template-rows] duration-200 ease-out ${
          expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
        }`}
      >
        <div className="overflow-hidden min-h-0">
          <div className="border-t border-white/5 px-4 pb-4 pt-3 space-y-3">
            {ev.message && (
              <p className="text-sm text-gray-300">{ev.message}</p>
            )}
            {ev.suggested_fix && (
              <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
                <div className="text-[10px] text-emerald-500 uppercase tracking-wide mb-1">
                  Solución sugerida
                </div>
                <p className="text-sm text-emerald-300">{ev.suggested_fix}</p>
              </div>
            )}
            {ev.repo_url && (
              <div className="text-xs text-gray-500">
                <span className="text-gray-600">Repo: </span>
                <a
                  href={ev.repo_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-blue-400 hover:underline"
                >
                  {ev.repo_url}
                </a>
                {ev.branch && (
                  <span className="ml-2 text-gray-600">rama: {ev.branch}</span>
                )}
              </div>
            )}

            {/* DiagnosisPanel — always mounted to preserve its state */}
            <DiagnosisPanel
              incidentId={inc.incident_id}
              diagSummary={inc.diagnosis_summary}
              diagRootCause={inc.diagnosis_root_cause}
              diagSteps={inc.diagnosis_steps}
              diagCustomerMessage={inc.diagnosis_customer_message}
              diagConfidence={inc.diagnosis_confidence}
              diagSource={inc.diagnosis_source}
              diagUpdatedAt={inc.diagnosis_updated_at}
              onDiagReady={setCurrentDiag}
            />

            {/* ActionsPanel — always rendered; generate button hidden for resolved */}
            <ActionsPanel
              incidentId={inc.incident_id}
              hasDiagnosis={!!(currentDiag || inc.diagnosis_summary)}
              onActionsLoaded={setCurrentActions}
              incidentStatus={inc.status}
            />

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
                  disabled={resolving}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 transition-colors disabled:opacity-50"
                >
                  {resolving
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
        </div>
      </div>
    </div>
  );
});

// ─── SentinelPanel ────────────────────────────────────────────────────────────

export default function SentinelPanel() {
  const [sourceTab, setSourceTab]   = useState('deploy');
  const [statusTab, setStatusTab]   = useState('open');
  // allItems holds ALL source types for the current statusTab (sourceTab is client-side filtered)
  const [allItems, setAllItems]     = useState([]);
  const [isFirstLoad, setIsFirstLoad] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError]           = useState(null);
  // Stable expand state by incident_id — survives tab changes
  const [expandedIds, setExpandedIds] = useState(() => new Set());

  // sourceTab → client-side filter, no refetch
  const filteredItems = useMemo(
    () => sourceTab ? allItems.filter(i => i.source_type === sourceTab) : allItems,
    [allItems, sourceTab],
  );

  const openCount = useMemo(
    () => filteredItems.filter(i => i.status === 'open').length,
    [filteredItems],
  );

  // Only fetch when statusTab changes (sourceTab is filtered client-side)
  const load = useCallback(async () => {
    setIsRefreshing(true);
    setError(null);
    const params = {};
    if (statusTab) params.status = statusTab;
    try {
      const d = await getSentinelIncidents(params);
      setAllItems(d.items || []);
      setIsFirstLoad(false);
    } catch (e) {
      // Keep previous data visible on error
      setError(e?.response?.data?.detail || 'Error al cargar incidentes');
      setIsFirstLoad(false);
    } finally {
      setIsRefreshing(false);
    }
  }, [statusTab]);

  useEffect(() => { load(); }, [load]);

  function handleResolved(id) {
    if (statusTab === 'open') {
      // Optimistic remove from open list
      setAllItems(prev => prev.filter(i => i.incident_id !== id));
    } else {
      setAllItems(prev => prev.map(i =>
        i.incident_id === id ? { ...i, status: 'resolved' } : i,
      ));
    }
  }

  const toggleExpanded = useCallback((id) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

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

        <div className="flex items-center gap-3">
          {isRefreshing && (
            <span className="flex items-center gap-1.5 text-xs text-gray-600">
              <Loader2 className="w-3 h-3 animate-spin" />
              Actualizando…
            </span>
          )}
          <button
            onClick={load}
            disabled={isRefreshing || isFirstLoad}
            className="p-2 rounded-lg bg-white/5 border border-white/8 text-gray-400 hover:text-white hover:bg-white/10 transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-4 h-4 ${(isRefreshing || isFirstLoad) ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Source tabs — switching these never triggers a refetch */}
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

      {/* Status tabs — switching triggers refetch */}
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

      {/* Incident list — min-height prevents collapse flicker */}
      <div className="min-h-[300px]">
        {isFirstLoad && (
          <div className="space-y-2">
            {[1, 2, 3].map(i => <SkeletonRow key={i} />)}
          </div>
        )}

        {!isFirstLoad && (
          <>
            {error && (
              <div className="flex items-center gap-2 text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-4">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span className="text-sm">{error} — mostrando últimos datos disponibles</span>
              </div>
            )}

            {filteredItems.length === 0 && !isRefreshing ? (
              <div className="text-center py-12 text-gray-600">
                <CheckCircle2 className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm">
                  Sin incidentes{statusTab === 'open' ? ' abiertos' : ''} en este segmento
                </p>
              </div>
            ) : (
              <div
                className={`space-y-2 transition-opacity duration-150 ${
                  isRefreshing ? 'opacity-60' : 'opacity-100'
                }`}
              >
                {filteredItems.map(inc => (
                  <IncidentRow
                    key={inc.incident_id}
                    inc={inc}
                    expanded={expandedIds.has(inc.incident_id)}
                    onToggle={toggleExpanded}
                    onResolved={handleResolved}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
