import { useNavigate } from 'react-router-dom';

/**
 * Empty state shown when the user has no sites or no traffic yet.
 *
 * Props:
 *   hasSite — boolean; false = no pixel registered yet, true = pixel installed but no events
 */
export default function EmptyState({ hasSite = false }) {
  const navigate = useNavigate();

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 mb-6 shadow-sm">
      <div className="flex flex-col items-center justify-center py-6 gap-3 text-center">
        <span className="text-2xl opacity-40">◈</span>
        <div>
          <p className="text-[11px] font-mono font-bold text-gray-900">
            {hasSite ? 'Tu sitio aún no tiene tráfico' : 'No hay sitios registrados'}
          </p>
          <p className="text-[10px] font-mono text-gray-500 mt-1">
            {hasSite
              ? 'Instala el pixel para comenzar a ver métricas'
              : 'Registra tu primer sitio para activar el tracking'}
          </p>
        </div>
        <button
          onClick={() => navigate('/pixel')}
          className="text-[10px] font-mono text-accent border border-accent/30 px-3 py-1 rounded hover:bg-accent/10 transition-colors"
        >
          Ver instalación →
        </button>
      </div>
    </div>
  );
}
