const DEFAULT_MESSAGE = 'No pudimos cargar tus métricas';

/**
 * Reusable error state for the Dashboard analytics card.
 *
 * Props:
 *   message — optional string; overrides default error heading
 *   onRetry — optional callback; shows "Reintentar" button when provided
 */
export default function ErrorState({ message, onRetry }) {
  return (
    <div className="bg-[#121214] border border-white/10 rounded-xl p-4 mb-6 shadow-sm">
      <div className="flex flex-col items-center justify-center py-6 gap-3 text-center">
        <span className="text-2xl opacity-60">⚠</span>
        <div>
          <p className="text-[11px] font-mono font-bold text-white">
            {message || DEFAULT_MESSAGE}
          </p>
          <p className="text-[10px] font-mono text-gray-400 mt-1">
            Comprueba tu conexión e inténtalo de nuevo
          </p>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="text-[10px] font-mono text-accent border border-accent/30 px-3 py-1 rounded hover:bg-accent/10 transition-colors"
          >
            Reintentar
          </button>
        )}
      </div>
    </div>
  );
}
