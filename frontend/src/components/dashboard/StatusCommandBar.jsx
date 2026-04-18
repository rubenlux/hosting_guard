import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Shield, AlertTriangle, Activity, Server } from 'lucide-react';

// ── Tiny SVG health ring ──────────────────────────────────────────────────────
function HealthRing({ score }) {
  const r = 14;
  const circ = 2 * Math.PI * r;
  const fill = circ * (1 - (score ?? 100) / 100);

  const color =
    score == null ? '#4b5563'
    : score >= 85  ? '#22d3a5'
    : score >= 60  ? '#f59e0b'
    :                '#ef4444';

  return (
    <svg width={36} height={36} viewBox="0 0 36 36" style={{ transform: 'rotate(-90deg)' }}>
      {/* track */}
      <circle cx={18} cy={18} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={3} />
      {/* progress */}
      <motion.circle
        cx={18} cy={18} r={r}
        fill="none"
        stroke={color}
        strokeWidth={3}
        strokeLinecap="round"
        strokeDasharray={circ}
        initial={{ strokeDashoffset: circ }}
        animate={{ strokeDashoffset: fill }}
        transition={{ duration: 1.1, ease: 'easeOut', delay: 0.3 }}
        style={{ filter: `drop-shadow(0 0 4px ${color}88)` }}
      />
      {/* score label — un-rotated via transform */}
      <text
        x={18} y={18}
        textAnchor="middle"
        dominantBaseline="middle"
        fill={color}
        fontSize="8"
        fontWeight="800"
        fontFamily="'JetBrains Mono', 'Fira Code', monospace"
        style={{ transform: 'rotate(90deg)', transformOrigin: '18px 18px' }}
      >
        {score ?? '—'}
      </text>
    </svg>
  );
}

// ── Pulse dot ────────────────────────────────────────────────────────────────
function PulseDot({ color }) {
  return (
    <span className="relative flex h-2 w-2 shrink-0">
      <span
        className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
        style={{ backgroundColor: color }}
      />
      <span
        className="relative inline-flex rounded-full h-2 w-2"
        style={{ backgroundColor: color }}
      />
    </span>
  );
}

// ── Divider ───────────────────────────────────────────────────────────────────
function Divider() {
  return <div className="h-5 w-px bg-white/10 mx-1 shrink-0" />;
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function StatusCommandBar({ hostings = [], healthData = {}, advisories = [], alerts = [] }) {
  const {
    avgScore,
    activeCount,
    criticalCount,
    warnCount,
    unresolvedAlerts,
    isAllHealthy,
    statusLabel,
    statusColor,
  } = useMemo(() => {
    const active = hostings.filter(h => h.status === 'active');
    const scores = active
      .map(h => healthData[h.hosting_id]?.score)
      .filter(s => s != null);

    const avg = scores.length
      ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length)
      : null;

    const criticals = advisories.filter(a => a.severity === 'critical').length;
    const warns     = advisories.filter(a => a.severity === 'warning').length;

    const unresolved = (alerts ?? []).filter(
      a => !a.resolved && (a.level === 'critical' || a.level === 'error'),
    ).length;

    const allOk = criticals === 0 && warns === 0;

    const label = allOk
      ? 'Todo operativo'
      : criticals > 0
        ? `${criticals} sitio${criticals !== 1 ? 's' : ''} con alerta crítica`
        : `${warns} sitio${warns !== 1 ? 's' : ''} requiere atención`;

    const color = allOk ? '#22d3a5' : criticals > 0 ? '#ef4444' : '#f59e0b';

    return {
      avgScore:       avg,
      activeCount:    active.length,
      criticalCount:  criticals,
      warnCount:      warns,
      unresolvedAlerts: unresolved,
      isAllHealthy:   allOk,
      statusLabel:    label,
      statusColor:    color,
    };
  }, [hostings, healthData, advisories, alerts]);

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      className="w-full flex items-center gap-0 px-5 py-0 border-b border-white/[0.07] bg-[#0d0d0f] select-none"
      style={{ height: 40, minHeight: 40 }}
    >
      {/* ── Health ring ── */}
      <div className="flex items-center gap-2 pr-4">
        <HealthRing score={avgScore} />
        <div>
          <div className="text-[9px] font-mono text-gray-500 uppercase tracking-widest leading-none mb-0.5">Salud</div>
          <div
            className="text-[11px] font-black leading-none tabular-nums"
            style={{ color: avgScore == null ? '#4b5563' : avgScore >= 85 ? '#22d3a5' : avgScore >= 60 ? '#f59e0b' : '#ef4444' }}
          >
            {avgScore != null ? `${avgScore}/100` : '—'}
          </div>
        </div>
      </div>

      <Divider />

      {/* ── Status pill ── */}
      <div className="flex items-center gap-2 px-4">
        <PulseDot color={statusColor} />
        <span
          className="text-[11px] font-bold tracking-wide"
          style={{ color: statusColor }}
        >
          {statusLabel}
        </span>
      </div>

      <Divider />

      {/* ── Site count ── */}
      <div className="flex items-center gap-1.5 px-4">
        <Server className="w-3 h-3 text-gray-500 shrink-0" />
        <span className="text-[11px] text-gray-400 font-medium">
          <span className="text-white font-bold">{activeCount}</span>
          {' '}sitio{activeCount !== 1 ? 's' : ''} activo{activeCount !== 1 ? 's' : ''}
        </span>
      </div>

      {/* ── Critical alerts badge (only when present) ── */}
      {unresolvedAlerts > 0 && (
        <>
          <Divider />
          <motion.div
            initial={{ scale: 0.7, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 300, damping: 20, delay: 0.4 }}
            className="flex items-center gap-1.5 px-4"
          >
            <AlertTriangle className="w-3 h-3 text-red-400 shrink-0" />
            <span className="text-[11px] font-bold text-red-400">
              {unresolvedAlerts} alerta{unresolvedAlerts !== 1 ? 's' : ''} sin resolver
            </span>
          </motion.div>
        </>
      )}

      {/* ── Spacer + right-side system indicator ── */}
      <div className="ml-auto flex items-center gap-2 pl-4">
        <Activity className="w-3 h-3 text-gray-600 shrink-0" />
        <span className="text-[10px] font-mono text-gray-600 uppercase tracking-widest hidden sm:block">
          Sistema activo
        </span>
      </div>
    </motion.div>
  );
}
