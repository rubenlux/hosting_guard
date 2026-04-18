import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, CheckCircle2, Zap, TrendingUp } from 'lucide-react';

function MetricPill({ label, value, warn }) {
  if (value == null) return null;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${
      warn ? 'bg-white/10 text-white' : 'bg-black/20 text-white/70'
    }`}>
      {label}: {typeof value === 'number' ? `${Math.round(value)}%` : value}
    </span>
  );
}

export default function SystemStatusBanner({ capacity }) {
  if (!capacity) return null;

  const { status, cpu_pct, ram_pct, disk_pct, containers, days_to_exhaustion, recommendation } = capacity;

  if (status === 'healthy' || status === 'ok' || status === 'unknown') {
    return (
      <motion.div
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        className="mx-6 mt-3 flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-500/8 border border-emerald-500/15 text-[11px] text-emerald-400"
      >
        <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
        <span className="font-medium">Capacidad OK</span>
        <span className="text-emerald-700 mx-1">·</span>
        <div className="flex items-center gap-2 flex-wrap">
          {cpu_pct != null && <MetricPill label="CPU" value={cpu_pct} />}
          {ram_pct != null && <MetricPill label="RAM" value={ram_pct} />}
          {disk_pct != null && <MetricPill label="Disco" value={disk_pct} />}
          {containers?.used != null && (
            <MetricPill label="Containers" value={`${containers.used}/${containers.capacity}`} />
          )}
        </div>
      </motion.div>
    );
  }

  if (status === 'warning') {
    return (
      <motion.div
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        className="mx-6 mt-3 flex items-center gap-3 px-4 py-2.5 rounded-lg bg-amber-500/10 border border-amber-500/25"
      >
        <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-[11px] font-semibold text-amber-300">Capacidad en riesgo — revisar crecimiento</span>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            {cpu_pct != null && <MetricPill label="CPU" value={cpu_pct} warn={cpu_pct > 70} />}
            {ram_pct != null && <MetricPill label="RAM" value={ram_pct} warn={ram_pct > 70} />}
            {disk_pct != null && <MetricPill label="Disco" value={disk_pct} warn={disk_pct > 70} />}
            {containers?.used != null && (
              <MetricPill label="Containers" value={`${containers.used}/${containers.capacity}`} warn={containers.pct > 70} />
            )}
            {days_to_exhaustion != null && (
              <MetricPill label="Estimación" value={`${days_to_exhaustion}d`} warn />
            )}
          </div>
        </div>
        <TrendingUp className="w-4 h-4 text-amber-500 shrink-0 opacity-60" />
      </motion.div>
    );
  }

  // critical
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        className="mx-6 mt-3 rounded-lg border border-red-500/40 overflow-hidden"
        style={{ background: 'linear-gradient(135deg, rgba(239,68,68,0.12) 0%, rgba(185,28,28,0.08) 100%)' }}
      >
        <motion.div
          animate={{ opacity: [1, 0.7, 1] }}
          transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          className="flex items-center gap-3 px-4 py-3"
        >
          <div className="relative shrink-0">
            <Zap className="w-4 h-4 text-red-400" />
            <motion.div
              animate={{ scale: [1, 1.8, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 1.5, repeat: Infinity }}
              className="absolute inset-0 rounded-full bg-red-400/30"
            />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-bold text-red-300 uppercase tracking-wide">
              ESCALAR INFRAESTRUCTURA AHORA
            </div>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {cpu_pct != null && <MetricPill label="CPU" value={cpu_pct} warn />}
              {ram_pct != null && <MetricPill label="RAM" value={ram_pct} warn />}
              {disk_pct != null && <MetricPill label="Disco" value={disk_pct} warn />}
              {containers?.used != null && (
                <MetricPill label="Containers" value={`${containers.used}/${containers.capacity}`} warn />
              )}
              {days_to_exhaustion != null && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-500/20 text-red-300 text-[10px] font-mono font-bold">
                  Tiempo estimado: {days_to_exhaustion < 1
                    ? `${Math.round(days_to_exhaustion * 24)}h`
                    : `${days_to_exhaustion}d`}
                </span>
              )}
            </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
