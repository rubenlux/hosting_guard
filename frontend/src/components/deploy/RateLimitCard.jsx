import React, { useState, useEffect } from 'react';
import { Clock } from 'lucide-react';

export default function RateLimitCard({ detail, retry_after_seconds = 0 }) {
  const [countdown, setCountdown] = useState(retry_after_seconds);

  useEffect(() => { setCountdown(retry_after_seconds); }, [retry_after_seconds]);

  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown(c => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const mins = Math.ceil(countdown / 60);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 text-yellow-400 font-bold text-sm">
        <Clock className="w-5 h-5 shrink-0" />
        Límite temporal alcanzado
      </div>
      <p className="text-gray-300 text-sm">{detail}</p>
      {countdown > 0 && (
        <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl px-4 py-2 text-yellow-300 font-mono text-sm text-center">
          Podés volver a intentar en {countdown >= 60 ? `${mins} min` : `${countdown}s`}
        </div>
      )}
    </div>
  );
}
