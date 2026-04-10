import { useNavigate } from 'react-router-dom';

/**
 * Shell card for the Dashboard analytics overview.
 * Owns the card frame, header (site name + nav link), and slot for children.
 *
 * Props:
 *   siteName    — string displayed in the header
 *   headerExtra — optional node rendered between the site name and the "ver todo" link
 *   children    — content sections rendered inside the card
 */
export default function OverviewCard({ siteName, headerExtra, children }) {
  const navigate = useNavigate();

  return (
    <div className="bg-[#050505] border border-white/10 rounded-xl p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
          <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-white">
            {siteName || 'Analítica'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {headerExtra}
          <button
            onClick={() => navigate('/pixel')}
            className="text-[9px] font-mono text-muted hover:text-accent transition-colors"
          >
            ver todo →
          </button>
        </div>
      </div>

      <div className="space-y-4">
        {children}
      </div>
    </div>
  );
}
