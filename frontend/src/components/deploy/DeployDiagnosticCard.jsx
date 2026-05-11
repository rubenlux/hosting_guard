import React from 'react';
import { AlertTriangle, Wrench, Zap } from 'lucide-react';
import DeployErrorDetails from './DeployErrorDetails';

export default function DeployDiagnosticCard({ errorData }) {
  const { detail, suggested_fix, code, stage, technical_detail, evidence, request_id } = errorData;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-3 text-red-400 font-bold text-sm">
        <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
        Deploy no completado
      </div>

      <p className="text-gray-200 text-sm leading-relaxed">{detail}</p>

      {evidence?.install_skipped && (
        <div className="flex items-start gap-2 bg-amber-500/8 border border-amber-500/20 rounded-xl px-4 py-3">
          <Zap className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-amber-300 text-xs leading-relaxed">
            Lo detectamos antes de instalar dependencias — no se creó ningún contenedor ni se ejecutó el build.
          </p>
        </div>
      )}

      {suggested_fix && (
        <div className="flex items-start gap-2 bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3">
          <Wrench className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
          <p className="text-blue-300 text-xs leading-relaxed">{suggested_fix}</p>
        </div>
      )}

      <DeployErrorDetails
        code={code}
        stage={stage}
        request_id={request_id}
        technical_detail={technical_detail}
        evidence={evidence}
      />
    </div>
  );
}
