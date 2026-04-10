import { useEffect } from 'react';
import { motion, useSpring, useTransform } from 'framer-motion';

/**
 * Horizontal KPI strip — no cards, Vercel-style minimal layout.
 * Numbers animate on value change via spring physics.
 *
 * Props:
 *   kpis — { visits, sessions, bounceRate, active }
 */
export default function KPISection({ kpis }) {
  if (!kpis) return null;

  return (
    <div className="grid grid-cols-4 gap-6 mb-6">

      <KPI label="Visitas"  value={kpis.visits} />
      <KPI label="Sesiones" value={kpis.sessions} />

      <KPI
        label="Bounce"
        value={kpis.bounceRate}
        suffix="%"
        color={
          kpis.bounceRate > 50 ? 'text-red-400'
          : kpis.bounceRate > 30 ? 'text-yellow-400'
          : 'text-emerald-400'
        }
      />

      <KPI label="Activos" value={kpis.active} />

    </div>
  );
}

function AnimatedNumber({ value }) {
  const spring = useSpring(0, { stiffness: 80, damping: 20 });

  useEffect(() => {
    spring.set(value);
  }, [spring, value]);

  const display = useTransform(spring, (latest) => Math.round(latest));

  return <motion.span>{display}</motion.span>;
}

function KPI({ label, value, suffix = '', color = 'text-white' }) {
  return (
    <motion.div whileHover={{ scale: 1.01 }} transition={{ duration: 0.2 }}>
      <p className="text-[10px] font-mono text-gray-500 uppercase tracking-wide">
        {label}
      </p>
      <p className={`text-xl font-semibold mt-1 ${color}`}>
        <AnimatedNumber value={value} />{suffix}
      </p>
    </motion.div>
  );
}
