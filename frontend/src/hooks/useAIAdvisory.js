/**
 * useAIAdvisory — deterministic advisory engine (frontend layer)
 *
 * Architecture: decision tree, NOT rule filter.
 *
 * Priority tiers mirror app/core/health_engine.py semantics:
 *
 *   TIER 1 — INFRA:        container down (site is 100% unreachable)
 *   TIER 2 — FATAL:        error_count > 0 (php_fatal / db_error) — trumps everything else
 *   TIER 3 — PERFORMANCE:  score-based / cpu / ram (resource exhaustion)
 *   TIER 4 — NOISE:        warning_count (404s) — low priority, informational
 *
 * Why tiers matter:
 *   CPU can spike *because* of a php_fatal (PHP looping on crash).
 *   Listing "CPU alta + score bajo" alongside the real cause pollutes the advisory
 *   and trains users to ignore it. Root cause wins; secondary signals are footnotes.
 *
 * Score thresholds match health_engine.py exactly:
 *   db_error   → -70 pts  (score ≤ 30 when only cause)
 *   php_fatal  → -50 pts  (score ≤ 50 when only cause)
 *   cpu > 85   → -20 pts
 *   ram > 80   → -15 pts
 *
 * @param {Array}  hostings   — from useDashboardData
 * @param {Object} healthData — { [hostingId]: { score, status, cpu, ram, error_count, warning_count } }
 * @param {Array}  alerts     — from useDashboardData (site_alerts rows)
 *
 * @returns {Array<Advisory>} sorted critical → warning → ok
 */
import { useMemo } from 'react';

const SEVERITY_RANK = { critical: 2, warning: 1, ok: 0 };

// ─────────────────────────────────────────────────────────────────────────────
// Decision tree — one cause, one narrative, no noise.
// Priority order mirrors backend impact weights:
//   1. container down  (site 100% unreachable)
//   2. error_count     (php_fatal / db_error — root cause)
//   3. alerts          (monitoring system signal)
//   4. cpu / ram       (resource exhaustion)
//   5. score           (degraded health, no clear single cause)
//   6. warning_count   (404 noise)
// ─────────────────────────────────────────────────────────────────────────────
export function evaluateHosting(hosting, healthData, alerts) {
  const hd = healthData[hosting.hosting_id];

  // No metrics yet — wait silently
  if (!hd) {
    return {
      hostingId:         hosting.hosting_id,
      hostingName:       hosting.name,
      severity:          'ok',
      summary:           'Sin datos suficientes.',
      recommendation:    'Esperando métricas iniciales.',
      requiresAttention: false,
      signals:           [],
    };
  }

  // 1. INFRA — container down
  if (hosting.status !== 'active') {
    return {
      hostingId:         hosting.hosting_id,
      hostingName:       hosting.name,
      severity:          'critical',
      summary:           'El contenedor está detenido o inaccesible.',
      recommendation:    'Reiniciar el hosting inmediatamente desde el panel.',
      requiresAttention: true,
      signals:           ['Contenedor no está en ejecución'],
    };
  }

  // 2. FATAL — application errors (root cause; CPU spike may be a side-effect)
  if (hd.error_count > 0) {
    return {
      hostingId:         hosting.hosting_id,
      hostingName:       hosting.name,
      severity:          'critical',
      summary:           `Errores críticos detectados en la aplicación (${hd.error_count}).`,
      recommendation:    'Revisar logs del servidor. Posible fallo en código o base de datos.',
      requiresAttention: true,
      signals: [
        `${hd.error_count} error${hd.error_count !== 1 ? 'es' : ''} crítico${hd.error_count !== 1 ? 's' : ''}`,
        hd.cpu > 85 ? `CPU elevada (${hd.cpu.toFixed(0)}%) — posible efecto secundario` : null,
      ].filter(Boolean),
    };
  }

  // 3. ALERTS — active critical from monitoring system
  // Guard: score >= 90 means the system is objectively healthy right now.
  // A stale unresolved alert (e.g. from a prior incident) must NOT override
  // a live healthy score — that creates the "SALUD 100% + CRÍTICO" contradiction.
  const hasCriticalAlert = hd.score < 90 && alerts.some(
    a => a.site_id === hosting.hosting_id && a.level === 'critical' && !a.resolved && !a.resolved_at,
  );
  if (hasCriticalAlert) {
    return {
      hostingId:         hosting.hosting_id,
      hostingName:       hosting.name,
      severity:          'critical',
      summary:           'Tu sitio puede estar caído o inestable en este momento.',
      recommendation:    'Revisar logs del servidor y ejecutar diagnóstico para identificar la causa.',
      requiresAttention: true,
      signals:           ['Alerta crítica activa sin resolver'],
    };
  }

  // 4. PERFORMANCE — resource exhaustion
  if (hd.cpu > 85 || hd.ram > 80) {
    return {
      hostingId:         hosting.hosting_id,
      hostingName:       hosting.name,
      severity:          'warning',
      summary:           'El sitio está bajo alta carga de recursos.',
      recommendation:    'Activar auto-scaling o optimizar procesos activos.',
      requiresAttention: true,
      signals: [
        hd.cpu > 85 ? `CPU crítica (${hd.cpu.toFixed(0)}%)` : null,
        hd.ram > 80 ? `RAM elevada (${hd.ram.toFixed(0)}%)` : null,
      ].filter(Boolean),
    };
  }

  // 5. SCORE — degraded health, no clear single cause
  if (hd.score < 70) {
    return {
      hostingId:         hosting.hosting_id,
      hostingName:       hosting.name,
      severity:          'warning',
      summary:           `La salud del sistema está degradándose (${hd.score}/100).`,
      recommendation:    'Monitorear comportamiento y considerar diagnóstico preventivo.',
      requiresAttention: true,
      signals:           [`Score actual: ${hd.score}/100`],
    };
  }

  // 6. NOISE — 404 warnings
  if (hd.warning_count > 10) {
    return {
      hostingId:         hosting.hosting_id,
      hostingName:       hosting.name,
      severity:          'warning',
      summary:           'Se detectaron múltiples errores 404.',
      recommendation:    'Verificar enlaces rotos o recursos faltantes.',
      requiresAttention: true,
      signals:           [`${hd.warning_count} errores 404 recientes`],
    };
  }

  // ALL CLEAR
  return {
    hostingId:         hosting.hosting_id,
    hostingName:       hosting.name,
    severity:          'ok',
    summary:           'El sistema opera con normalidad.',
    recommendation:    'No se requiere acción.',
    requiresAttention: false,
    signals:           [],
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────────
export function useAIAdvisory(hostings, healthData, alerts) {
  return useMemo(() => {
    const advisories = hostings.map(h => evaluateHosting(h, healthData, alerts));
    return [...advisories].sort(
      (a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity],
    );
  }, [hostings, healthData, alerts]);
}
