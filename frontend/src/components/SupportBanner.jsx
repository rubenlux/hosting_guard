import { useState, useEffect } from 'react';
import { ShieldAlert, X, Clock, CheckCircle2, AlertCircle, ArrowUpRight, Minus } from 'lucide-react';
import api from '../services/api';

const RESULT_OPTIONS = [
  { value: 'resolved',   label: 'Resuelto',           color: 'text-emerald-400', icon: CheckCircle2 },
  { value: 'unresolved', label: 'No resuelto',         color: 'text-red-400',     icon: AlertCircle },
  { value: 'escalated',  label: 'Escalado',            color: 'text-amber-400',   icon: ArrowUpRight },
  { value: 'ongoing',    label: 'En seguimiento',      color: 'text-blue-400',    icon: Minus },
];

/**
 * Resolution modal — shown when staff clicks "Salir del modo soporte".
 * Collects result + action taken + notes before actually closing the session.
 */
function ResolutionModal({ targetEmail, onConfirm, onCancel }) {
  const [result, setResult]   = useState('resolved');
  const [action, setAction]   = useState('');
  const [notes, setNotes]     = useState('');
  const [saving, setSaving]   = useState(false);

  const submit = async () => {
    setSaving(true);
    await onConfirm({ result, action_taken: action.trim(), resolution_notes: notes.trim() });
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black/75 flex items-center justify-center p-6">
      <div className="bg-[#0d0d0d] border border-white/10 rounded-2xl w-full max-w-md p-6 space-y-4 shadow-2xl">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-full bg-amber-500/15 flex items-center justify-center">
            <ShieldAlert className="w-4 h-4 text-amber-400" />
          </div>
          <div>
            <div className="text-[12px] font-bold text-white">Cerrar sesión de soporte</div>
            <div className="text-[10px] text-gray-500 font-mono">{targetEmail}</div>
          </div>
        </div>

        {/* Result */}
        <div>
          <label className="block text-[9px] uppercase tracking-wider text-gray-500 mb-2">
            Resultado de la sesión <span className="text-red-400">*</span>
          </label>
          <div className="grid grid-cols-2 gap-2">
            {RESULT_OPTIONS.map(opt => {
              const Icon = opt.icon;
              return (
                <button
                  key={opt.value}
                  onClick={() => setResult(opt.value)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-[11px] font-bold border transition-colors
                    ${result === opt.value
                      ? 'border-white/20 bg-white/10 text-white'
                      : 'border-white/5 bg-white/3 text-gray-500 hover:border-white/10 hover:text-gray-300'
                    }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${result === opt.value ? opt.color : ''}`} />
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Action taken */}
        <div>
          <label className="block text-[9px] uppercase tracking-wider text-gray-500 mb-1.5">
            Acción realizada
          </label>
          <input
            value={action}
            onChange={e => setAction(e.target.value)}
            placeholder='Ej: "Reinicio de contenedor", "Fix en index.html", "Deploy ejecutado"'
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[11px] text-white
              placeholder-gray-600 outline-none focus:border-amber-500/50"
          />
        </div>

        {/* Notes */}
        <div>
          <label className="block text-[9px] uppercase tracking-wider text-gray-500 mb-1.5">
            Notas adicionales
          </label>
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder='Ej: "El cliente tenía mal configurado el env. Se corrigió y se hizo deploy."'
            rows={2}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-[11px] text-white
              placeholder-gray-600 outline-none focus:border-amber-500/50 resize-none"
          />
        </div>

        <div className="flex gap-2 pt-1">
          <button
            onClick={onCancel}
            disabled={saving}
            className="flex-1 py-2 rounded-lg text-[11px] bg-white/5 text-gray-400 hover:bg-white/10 transition-colors disabled:opacity-40"
          >
            Seguir en soporte
          </button>
          <button
            onClick={submit}
            disabled={saving}
            className="flex-1 py-2 rounded-lg text-[11px] font-bold bg-amber-500/20 text-amber-400
              hover:bg-amber-500/30 transition-colors disabled:opacity-40"
          >
            {saving ? 'Cerrando...' : 'Cerrar sesión'}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Banner that appears at the top of the client dashboard during a support session.
 */
export default function SupportBanner({ targetEmail, adminEmail, expiresAt, onExit }) {
  const [secondsLeft, setSecondsLeft]     = useState(null);
  const [exiting, setExiting]             = useState(false);
  const [showResolution, setShowResolution] = useState(false);

  useEffect(() => {
    if (!expiresAt) return;
    const expMs =
      typeof expiresAt === 'number'
        ? expiresAt * 1000
        : new Date(expiresAt).getTime();

    const tick = () => {
      const diff = Math.max(0, Math.floor((expMs - Date.now()) / 1000));
      setSecondsLeft(diff);
      // Auto-expire: skip resolution modal, just exit
      if (diff === 0 && onExit) onExit({ result: 'ongoing', action_taken: '', resolution_notes: 'Sesión expirada automáticamente' });
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [expiresAt, onExit]);

  const handleExitClick = () => {
    if (!exiting) setShowResolution(true);
  };

  const handleResolutionConfirm = async (resolutionData) => {
    setExiting(true);
    setShowResolution(false);
    // Close the session on the backend first
    const sessionId = sessionStorage.getItem('support_session_id');
    if (sessionId) {
      try {
        await api.post(`/admin/impersonate/staff/${sessionId}/close`, {
          result: resolutionData.result,
          resolution_notes: resolutionData.resolution_notes,
          action_taken: resolutionData.action_taken,
        });
      } catch {
        // Don't block exit if close fails
      }
    }
    // Deactivate the cookie
    try { await api.post('/support/deactivate'); } catch { /* ignore */ }
    if (onExit) onExit(resolutionData);
  };

  const fmt = (s) => {
    if (s === null) return '—';
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  };

  const urgent = secondsLeft !== null && secondsLeft < 60;

  return (
    <>
      {showResolution && (
        <ResolutionModal
          targetEmail={targetEmail}
          onConfirm={handleResolutionConfirm}
          onCancel={() => setShowResolution(false)}
        />
      )}

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
            <span className="text-xs opacity-60 ml-2">(admin: {adminEmail})</span>
          )}
        </span>

        {secondsLeft !== null && (
          <div className={`flex items-center gap-1.5 text-xs font-mono shrink-0 ${urgent ? 'text-red-300' : 'text-amber-300'}`}>
            <Clock className="w-3.5 h-3.5" />
            {fmt(secondsLeft)}
          </div>
        )}

        <button
          onClick={handleExitClick}
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
    </>
  );
}
