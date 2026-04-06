import { useState, useEffect } from 'react';
import { ShieldAlert, X, Clock } from 'lucide-react';
import api from '../services/api';

/**
 * Banner that appears at the top of the client dashboard during a support session.
 * Props:
 *   targetEmail   — email of the client being impersonated
 *   adminEmail    — email of the admin doing the impersonation
 *   expiresAt     — Unix timestamp (seconds) or ISO string when the session expires
 *   onExit        — callback invoked after the support cookie is cleared
 */
export default function SupportBanner({ targetEmail, adminEmail, expiresAt, onExit }) {
  const [secondsLeft, setSecondsLeft] = useState(null);
  const [exiting, setExiting] = useState(false);

  // Countdown timer
  useEffect(() => {
    if (!expiresAt) return;

    const expMs =
      typeof expiresAt === 'number'
        ? expiresAt * 1000          // Unix timestamp from JWT exp claim
        : new Date(expiresAt).getTime();

    const tick = () => {
      const diff = Math.max(0, Math.floor((expMs - Date.now()) / 1000));
      setSecondsLeft(diff);
      if (diff === 0 && onExit) onExit();
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [expiresAt, onExit]);

  const handleExit = async () => {
    setExiting(true);
    try {
      await api.post('/support/deactivate');
    } catch {
      // Cookie cleared server-side; even if request fails, we exit.
    }
    if (onExit) onExit();
  };

  const fmt = (s) => {
    if (s === null) return '—';
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${String(sec).padStart(2, '0')}`;
  };

  const urgent = secondsLeft !== null && secondsLeft < 60;

  return (
    <div
      className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm font-medium z-40
        transition-colors duration-500
        ${urgent
          ? 'bg-red-500/20 border-b border-red-500/40 text-red-300'
          : 'bg-amber-500/15 border-b border-amber-500/30 text-amber-200'
        }`}
    >
      <ShieldAlert className={`w-4 h-4 shrink-0 ${urgent ? 'text-red-400 animate-pulse' : 'text-amber-400'}`} />

      <span className="flex-1 min-w-0 truncate">
        <span className="font-bold">Modo soporte activo</span>
        {' — '}viendo como{' '}
        <span className="font-mono font-bold">{targetEmail}</span>
        {adminEmail && (
          <span className="text-xs opacity-60 ml-2">
            (admin: {adminEmail})
          </span>
        )}
      </span>

      {secondsLeft !== null && (
        <div className={`flex items-center gap-1.5 text-xs font-mono shrink-0
          ${urgent ? 'text-red-300' : 'text-amber-300'}`}
        >
          <Clock className="w-3.5 h-3.5" />
          {fmt(secondsLeft)}
        </div>
      )}

      <button
        onClick={handleExit}
        disabled={exiting}
        className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold transition-colors shrink-0
          ${urgent
            ? 'bg-red-500/30 hover:bg-red-500/50 text-red-200'
            : 'bg-amber-500/20 hover:bg-amber-500/40 text-amber-200'
          }
          disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        <X className="w-3.5 h-3.5" />
        Salir del modo soporte
      </button>
    </div>
  );
}
