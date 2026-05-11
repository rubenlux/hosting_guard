import React from 'react';
import { CheckCircle2, ExternalLink, ArrowRight } from 'lucide-react';

export default function DeploySuccessCard({ url, onClose }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 text-emerald-400 font-bold text-sm">
        <CheckCircle2 className="w-5 h-5 shrink-0" />
        Tu sitio está en línea
      </div>

      <div className="bg-background/50 border border-white/8 p-4 rounded-xl">
        <p className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-1.5">Tu URL está lista:</p>
        <a href={url} target="_blank" rel="noopener noreferrer"
           className="text-primary font-mono block hover:underline text-lg break-all">
          {url}
        </a>
      </div>

      <div className="flex gap-2">
        <a href={url} target="_blank" rel="noopener noreferrer"
           className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm font-bold hover:bg-emerald-500/20 transition-colors">
          <ExternalLink className="w-4 h-4" /> Abrir sitio
        </a>
        {onClose && (
          <button type="button" onClick={onClose}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl bg-white/5 border border-white/10 text-gray-300 text-sm font-bold hover:bg-white/10 transition-colors">
            <ArrowRight className="w-4 h-4" /> Ir a Mis sitios
          </button>
        )}
      </div>
    </div>
  );
}
