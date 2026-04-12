/**
 * useAIAdvisory — deterministic advisory engine (frontend layer)
 *
 * Mirrors the thresholds from app/core/health_engine.py so the frontend
 * advisory is always consistent with backend health scores.
 * No backend calls, no LLM — pure computation over existing data.
 *
 * @param {Array}  hostings   — from useDashboardData
 * @param {Object} healthData — { [hostingId]: { score, cpu, ram, error_count, ... } }
 * @param {Array}  alerts     — from useDashboardData (site_alerts rows)
 *
 * @returns {Array<Advisory>} sorted critical → warning → ok
 */
import { useMemo } from 'react';

// Severity ranking — higher = worse
const SEVERITY_RANK = { critical: 2, warning: 1, ok: 0 };

// ─────────────────────────────────────────────────────────────────────────────
// Rule definitions
// Each rule: { id, severity, test(hosting, hd, alerts), signal, recommendation }
// signal can be a string or fn(hosting, hd) → string
// Rules are evaluated top-to-bottom; ALL that match contribute signals.
// The highest severity among triggered rules becomes the advisory severity.
// ─────────────────────────────────────────────────────────────────────────────
const RULES = [
  // ── CRITICAL ────────────────────────────────────────────────────────────────
  {
    id: 'container_down',
    severity: 'critical',
    test: (h) => h.status !== 'active',
    signal: 'Contenedor inactivo o caído',
    recommendation: 'Iniciar o reiniciar el hosting desde el panel de proyectos.',
  },
  {
    id: 'score_critical',
    severity: 'critical',
    test: (_h, hd) => hd && hd.score < 40,
    signal: (_h, hd) => `Score de salud crítico: ${hd.score}/100`,
    recommendation: 'Ejecutar diagnóstico IA y revisar logs del servidor.',
  },
  {
    id: 'cpu_critical',
    severity: 'critical',
    // Mirrors health_engine.py: cpu > 85 → -20pts
    test: (_h, hd) => hd && hd.cpu > 85,
    signal: (_h, hd) => `CPU al ${hd.cpu.toFixed(0)}% — límite crítico superado`,
    recommendation: 'Activar auto-scaling o revisar procesos en ejecución.',
  },
  {
    id: 'error_count',
    severity: 'critical',
    test: (_h, hd) => hd && hd.error_count > 0,
    signal: (_h, hd) =>
      `${hd.error_count} error${hd.error_count !== 1 ? 'es' : ''} crítico${hd.error_count !== 1 ? 's' : ''} detectado${hd.error_count !== 1 ? 's' : ''}`,
    recommendation: 'Revisar logs del servidor. Posibles errores PHP o de base de datos.',
  },
  {
    id: 'alert_critical',
    severity: 'critical',
    test: (h, _hd, alerts) =>
      alerts.some(a => a.site_id === h.hosting_id && a.level === 'critical' && !a.resolved_at),
    signal: 'Alerta crítica activa generada por el sistema de monitoreo',
    recommendation: 'Resolver la alerta desde el panel de notificaciones.',
  },

  // ── WARNING ─────────────────────────────────────────────────────────────────
  {
    id: 'score_warning',
    severity: 'warning',
    // Mirrors health_engine.py: score 40–69 = "warning" status
    test: (_h, hd) => hd && hd.score >= 40 && hd.score < 70,
    signal: (_h, hd) => `Score de salud degradado: ${hd.score}/100`,
    recommendation: 'Monitorear tendencia. Considerar diagnóstico preventivo.',
  },
  {
    id: 'cpu_warning',
    severity: 'warning',
    // Mirrors health_engine.py: cpu 70–85 = approaching threshold
    test: (_h, hd) => hd && hd.cpu > 70 && hd.cpu <= 85,
    signal: (_h, hd) => `CPU al ${hd.cpu.toFixed(0)}% — cerca del límite`,
    recommendation: 'Considerar activar auto-scaling preventivo.',
  },
  {
    id: 'ram_warning',
    severity: 'warning',
    // Mirrors health_engine.py: ram > 80 → -15pts
    test: (_h, hd) => hd && hd.ram > 80,
    signal: (_h, hd) => `RAM al ${hd.ram.toFixed(0)}% — uso elevado`,
    recommendation: 'Revisar posibles fugas de memoria o considerar upgrade de plan.',
  },
  {
    id: 'warning_count',
    severity: 'warning',
    test: (_h, hd) => hd && hd.warning_count > 10,
    signal: (_h, hd) => `${hd.warning_count} errores 404 detectados en la última hora`,
    recommendation: 'Verificar rutas de archivos y enlaces rotos en el sitio.',
  },
  {
    id: 'alert_warning',
    severity: 'warning',
    test: (h, _hd, alerts) =>
      alerts.some(a => a.site_id === h.hosting_id && a.level === 'warning' && !a.resolved_at),
    signal: 'Alerta de advertencia activa',
    recommendation: 'Atender la advertencia para evitar degradación del servicio.',
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// Pure evaluation function — exported for unit testing
// ─────────────────────────────────────────────────────────────────────────────
export function evaluateHosting(hosting, healthData, alerts) {
  const hd = healthData[hosting.hosting_id];

  // Only evaluate health rules when health data exists and container is active
  const triggered = RULES.filter(r => {
    try { return r.test(hosting, hd, alerts); }
    catch { return false; }
  });

  if (triggered.length === 0) {
    return {
      hostingId:        hosting.hosting_id,
      hostingName:      hosting.name,
      severity:         'ok',
      summary:          'Operando con normalidad.',
      recommendation:   'Continuar con monitoreo regular.',
      requiresAttention: false,
      signals:          [],
    };
  }

  // Highest severity among all triggered rules
  const topSeverity = triggered.reduce(
    (best, r) => SEVERITY_RANK[r.severity] > SEVERITY_RANK[best] ? r.severity : best,
    'ok',
  );

  const signals = triggered.map(r =>
    typeof r.signal === 'function' ? r.signal(hosting, hd) : r.signal,
  );

  // Recommendation from the first (most severe) triggered rule
  const topRule = triggered.find(r => r.severity === topSeverity);
  const recommendation = topRule?.recommendation ?? '';

  return {
    hostingId:         hosting.hosting_id,
    hostingName:       hosting.name,
    severity:          topSeverity,
    summary:           signals[0],
    recommendation,
    requiresAttention: true,
    signals,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────────
export function useAIAdvisory(hostings, healthData, alerts) {
  return useMemo(() => {
    const advisories = hostings.map(h => evaluateHosting(h, healthData, alerts));
    // Sort: critical → warning → ok
    return advisories.sort(
      (a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity],
    );
  }, [hostings, healthData, alerts]);
}
