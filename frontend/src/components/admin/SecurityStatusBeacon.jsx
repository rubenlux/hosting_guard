import React, { useEffect, useState, useCallback } from 'react';
import { ShieldCheck, ShieldAlert, ShieldOff } from 'lucide-react';
import { getSecurityStatus } from '../../services/api';

const CFG = {
  green: {
    dot:       'bg-emerald-500',
    pulse:     false,
    Icon:      ShieldCheck,
    iconColor: 'text-emerald-400',
    textColor: 'text-emerald-400',
    label:     'Sin alertas',
  },
  yellow: {
    dot:       'bg-amber-400',
    pulse:     false,
    Icon:      ShieldAlert,
    iconColor: 'text-amber-400',
    textColor: 'text-amber-400',
    label:     'Actividad sospechosa',
  },
  red: {
    dot:       'bg-red-500',
    pulse:     true,
    Icon:      ShieldOff,
    iconColor: 'text-red-400',
    textColor: 'text-red-400',
    label:     'Alerta activa',
  },
};

export default function SecurityStatusBeacon({ onNavigateToSecurity }) {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    try {
      const r = await getSecurityStatus();
      setData(r);
    } catch {
      // silently ignore — never disrupt the admin header
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
    const id = setInterval(fetch, 30_000);
    return () => clearInterval(id);
  }, [fetch]);

  if (loading || !data) return null;

  const cfg = CFG[data.status] ?? CFG.green;
  const { Icon } = cfg;

  const countLabel =
    data.status === 'red' && data.open_events_total > 0
      ? `${data.open_events_total} alerta${data.open_events_total !== 1 ? 's' : ''}`
      : cfg.label;

  return (
    <button
      onClick={onNavigateToSecurity}
      title={data.label}
      className="flex items-center gap-1.5 px-2 py-1 rounded-lg hover:bg-white/5 transition-colors"
    >
      {/* Dot indicator */}
      <span className="relative flex h-2 w-2">
        <span className={`absolute inline-flex h-full w-full rounded-full ${cfg.dot} opacity-75 ${cfg.pulse ? 'animate-ping' : ''}`} />
        <span className={`relative inline-flex h-2 w-2 rounded-full ${cfg.dot}`} />
      </span>

      <Icon className={`w-3.5 h-3.5 ${cfg.iconColor}`} />

      <span className={`text-[10px] font-medium ${cfg.textColor}`}>
        {countLabel}
      </span>
    </button>
  );
}
