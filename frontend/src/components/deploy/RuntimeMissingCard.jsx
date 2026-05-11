import React from 'react';
import { Wrench, Info } from 'lucide-react';
import DeployErrorDetails from './DeployErrorDetails';

export default function RuntimeMissingCard({ errorData }) {
  const { code, stage, technical_detail, evidence, request_id } = errorData;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start gap-3 text-orange-400 font-bold text-sm">
        <Wrench className="w-5 h-5 shrink-0 mt-0.5" />
        No pudimos iniciar el deploy
      </div>

      <p className="text-gray-200 text-sm leading-relaxed">
        El problema no está en tu repositorio. HostingGuard necesita una herramienta interna
        para clonar el proyecto y no está disponible en este momento.
      </p>

      <div className="flex items-start gap-2 bg-blue-500/10 border border-blue-500/20 rounded-xl px-4 py-3">
        <Info className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
        <p className="text-blue-300 text-xs leading-relaxed">
          Nuestro equipo debe corregir el entorno de deploy. No necesitás cambiar tu código.
        </p>
      </div>

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
