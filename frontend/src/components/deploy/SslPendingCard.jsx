import React, { useState, useEffect, useRef } from 'react';
import { CheckCircle2, Loader2, ShieldCheck, ExternalLink, ArrowRight } from 'lucide-react';
import { getSslStatus } from '../../services/api';

const STEPS = [
  'Repositorio clonado',
  'Dependencias instaladas',
  'Proyecto compilado',
  'Sitio publicado',
  'Activando SSL',
  'Sitio en línea',
];

export default function SslPendingCard({ hostingId, url, onClose }) {
  const [sslOnline, setSslOnline] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    intervalRef.current = setInterval(async () => {
      try {
        const data = await getSslStatus(hostingId);
        if (data.ssl_status === 'online') {
          clearInterval(intervalRef.current);
          setSslOnline(true);
        }
      } catch {
        // ignore transient errors, keep polling
      }
    }, 5000);
    return () => clearInterval(intervalRef.current);
  }, [hostingId]);

  return (
    <div className="flex flex-col gap-4">
      <div className={`flex items-center gap-3 font-bold text-sm ${sslOnline ? 'text-emerald-400' : 'text-blue-400'}`}>
        {sslOnline
          ? <CheckCircle2 className="w-5 h-5 shrink-0" />
          : <ShieldCheck className="w-5 h-5 shrink-0" />
        }
        {sslOnline ? 'Tu sitio está en línea' : 'Tu sitio fue publicado — activando SSL…'}
      </div>

      <div className="space-y-2">
        {STEPS.map((label, i) => {
          const isSSL    = i === 4;
          const isOnline = i === 5;
          const done   = isOnline ? sslOnline : (isSSL ? sslOnline : i < 4);
          const active = isSSL && !sslOnline;

          return (
            <div key={i} className="flex items-center gap-3">
              <span className="w-4 h-4 shrink-0 flex items-center justify-center">
                {done ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : active ? (
                  <Loader2 className="w-4 h-4 text-amber-400 animate-spin" />
                ) : (
                  <span className="w-2 h-2 rounded-full bg-white/10 mx-auto block" />
                )}
              </span>
              <span className={`text-sm ${done ? 'text-gray-300' : active ? 'text-amber-300' : 'text-gray-600'}`}>
                {label}
              </span>
            </div>
          );
        })}
      </div>

      {sslOnline ? (
        <>
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
        </>
      ) : (
        <p className="text-xs text-gray-500">
          El certificado SSL se genera automáticamente. Tomará unos segundos.
        </p>
      )}
    </div>
  );
}
