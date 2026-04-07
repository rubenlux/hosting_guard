import React from 'react';
import { 
  Globe, Play, Square, RotateCcw, AlertTriangle, 
  Trash2, FileText, Bot, Upload, FolderOpen, RefreshCw,
  Cpu, Database
} from 'lucide-react';

const SiteManagement = ({ 
  hostings, 
  loading, 
  onRefresh, 
  onAction,
  onOpenLogs,
  onDelete,
  onUploadZip,
  onOpenFiles,
  onDiagnose
}) => {

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <Globe className="text-blue-500 w-6 h-6" />
            Mis Sitios (Operaciones)
          </h2>
          <p className="text-muted text-sm mt-1">
            Revisá métricas en tiempo real, gestioná archivos y diagnosticá con IA.
          </p>
        </div>
        <button 
          onClick={onRefresh}
          className="btn-dash btn-ghost-dash flex items-center gap-2 text-sm"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {loading ? 'Refrescando...' : 'Actualizar'}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {loading && hostings.length === 0 ? (
          <div className="py-12 flex justify-center text-muted">Cargando sitios...</div>
        ) : hostings.length === 0 ? (
          <div className="py-12 text-center text-muted italic border border-white/5 rounded-2xl">
            No tienes sitios desplegados aún.
          </div>
        ) : (
          hostings.map(h => (
            <div key={h.hosting_id} className="bg-[#08080a] border border-white/5 rounded-xl p-5 hover:border-white/10 transition-all flex flex-col md:flex-row md:items-center gap-6">
              
              {/* Identity */}
              <div className="flex items-center gap-4 min-w-[200px]">
                <div className="w-12 h-12 bg-blue-500/10 text-blue-500 rounded-2xl flex items-center justify-center font-black text-xl">
                  {h.name[0].toUpperCase()}
                </div>
                <div>
                  <h3 className="font-bold text-white text-base">{h.name}</h3>
                  <a href={`https://${h.subdomain}`} target="_blank" rel="noreferrer" className="text-xs text-muted hover:text-blue-400 font-mono transition-colors">
                    {h.subdomain}
                  </a>
                  <div className="mt-1">
                    <span className="text-[10px] font-black tracking-widest uppercase bg-white/5 px-2 py-0.5 rounded text-gray-400">
                      {h.plan}
                    </span>
                  </div>
                </div>
              </div>

              {/* Metrics & State */}
              <div className="flex-1 flex gap-6 mt-4 md:mt-0 px-4 md:border-l border-white/5">
                <div className="flex flex-col gap-2">
                  <div className="flex justify-between items-center w-full min-w-[120px]">
                    <span className="text-xs text-muted flex items-center gap-1.5"><Cpu size={12}/> CPU</span>
                    <span className="text-xs font-mono font-medium text-white">{h.metrics?.cpu || '0%'}</span>
                  </div>
                  <div className="flex justify-between items-center w-full min-w-[120px]">
                    <span className="text-xs text-muted flex items-center gap-1.5"><Database size={12}/> RAM</span>
                    <span className="text-xs font-mono font-medium text-white">{h.metrics?.memory || '0MiB'}</span>
                  </div>
                </div>
                
                <div className="flex items-center ml-auto">
                   <div className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${h.status === 'active' ? 'bg-[#00ff88]/10 text-[#00ff88]' : h.status === 'stopped' ? 'bg-danger/10 text-danger' : 'bg-warn/10 text-warn'}`}>
                     ● {h.status || 'unknown'}
                   </div>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 mt-4 md:mt-0 shrink-0">
                
                {h.status === 'active' && (
                  <>
                    <button onClick={() => onAction(h.hosting_id, 'restart')} className="w-9 h-9 flex items-center justify-center rounded-lg bg-white/5 hover:bg-accent/20 hover:text-accent transition-colors" title="Reiniciar">
                      <RotateCcw size={15} />
                    </button>
                    <button onClick={() => onAction(h.hosting_id, 'stop')} className="w-9 h-9 flex items-center justify-center rounded-lg bg-white/5 hover:bg-danger/20 hover:text-danger transition-colors" title="Detener">
                      <Square size={15} />
                    </button>
                  </>
                )}

                {h.status === 'stopped' && (
                  <button onClick={() => onAction(h.hosting_id, 'start')} className="w-9 h-9 flex items-center justify-center rounded-lg bg-accent/10 hover:bg-accent hover:text-[#000] text-accent transition-colors" title="Arrancar">
                    <Play size={15} />
                  </button>
                )}

                {/* Always active actions */}
                <button onClick={() => onOpenLogs(h)} className="w-9 h-9 flex items-center justify-center rounded-lg bg-white/5 hover:bg-blue-500/20 hover:text-blue-400 transition-colors" title="Logs">
                  <FileText size={15} />
                </button>
                
                {(!h.container_name || !h.container_name.includes('_wp_')) && (
                  <button onClick={() => onOpenFiles(h)} className="w-9 h-9 flex items-center justify-center rounded-lg bg-white/5 hover:bg-purple-500/20 hover:text-purple-400 transition-colors" title="Archivos">
                    <FolderOpen size={15} />
                  </button>
                )}
                
                <div className="w-[1px] h-6 bg-white/10 mx-1"></div>
                
                <button 
                  onClick={() => onDiagnose?.(h.hosting_id)}
                  className="px-3 h-9 flex items-center gap-2 rounded-lg bg-ia/10 text-ia hover:bg-ia hover:text-[#000] font-bold text-[11px] transition-all"
                >
                  <Bot size={14} /> Diagnosticar
                </button>

              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default SiteManagement;
