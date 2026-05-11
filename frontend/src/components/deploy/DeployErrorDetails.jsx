import React, { useState } from 'react';
import { Info, ChevronDown, ChevronUp } from 'lucide-react';

export default function DeployErrorDetails({ code, stage, request_id, technical_detail, evidence }) {
  const [expanded, setExpanded] = useState(false);
  const hasContent = code || stage || request_id || technical_detail ||
    (evidence && Object.keys(evidence).length > 0);

  if (!hasContent) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setExpanded(e => !e)}
        className="flex items-center gap-1 text-gray-500 hover:text-gray-300 text-xs transition-colors w-fit"
      >
        <Info className="w-3.5 h-3.5" />
        {expanded ? 'Ocultar detalles técnicos' : 'Ver detalles técnicos'}
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      {expanded && (
        <div className="bg-black/40 border border-white/8 rounded-xl p-3 font-mono text-xs text-gray-400 space-y-1 max-h-40 overflow-y-auto">
          {code       && <div><span className="text-gray-600">code:</span>  <span className="text-red-400">{code}</span></div>}
          {stage      && <div><span className="text-gray-600">stage:</span> <span className="text-yellow-400">{stage}</span></div>}
          {request_id && <div><span className="text-gray-600">request_id:</span> {request_id}</div>}
          {technical_detail && (
            <div className="whitespace-pre-wrap break-all text-gray-500 border-t border-white/5 pt-1 mt-1">
              {technical_detail}
            </div>
          )}
          {evidence && Object.keys(evidence).length > 0 && (
            <div className="whitespace-pre-wrap break-all text-gray-500 border-t border-white/5 pt-1 mt-1">
              {JSON.stringify(evidence, null, 2)}
            </div>
          )}
        </div>
      )}
    </>
  );
}
