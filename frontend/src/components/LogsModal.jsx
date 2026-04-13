import React, { useEffect, useRef, useState } from 'react';
import { X, Terminal, RefreshCw, Pause, Play } from 'lucide-react';

const LogsModal = ({ isOpen, onClose, logs, projectName, onRefresh, loading }) => {
  const scrollRef = useRef(null);
  const [isPaused, setIsPaused] = useState(false);

  // Auto-refresh (Polling)
  useEffect(() => {
    if (!isOpen || isPaused) return;

    const interval = setInterval(() => {
      onRefresh();
    }, 3000);

    return () => clearInterval(interval);
  }, [isOpen, isPaused, onRefresh]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current && !isPaused) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, isPaused]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" onClick={onClose}></div>
      
      <div className="relative w-full max-w-4xl bg-white border border-gray-100 rounded-3xl shadow-2xl overflow-hidden flex flex-col max-h-[80vh]">
        {/* Header */}
        <div className="p-6 border-bottom border-gray-100 flex items-center justify-between bg-gray-50/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg text-primary">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-gray-900">Logs del Sistema</h3>
              <p className="text-xs text-muted font-mono uppercase tracking-widest">{projectName}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={() => setIsPaused(!isPaused)}
              className={`p-2 rounded-lg transition-colors ${isPaused ? 'bg-amber-100 text-amber-600' : 'hover:bg-gray-100 text-gray-500'}`}
              title={isPaused ? "Reanudar" : "Pausar"}
            >
              {isPaused ? <Play className="w-5 h-5" /> : <Pause className="w-5 h-5" />}
            </button>
            <button 
              onClick={onRefresh}
              disabled={loading}
              className="p-2 hover:bg-gray-100 rounded-lg text-gray-500 transition-colors"
              title="Refrescar ahora"
            >
              <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button 
              onClick={onClose}
              className="p-2 hover:bg-red-50 hover:text-red-500 rounded-lg text-gray-500 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div 
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-6 bg-[#1a1b26] font-mono text-sm leading-relaxed scroll-smooth"
        >
          {loading && !logs ? (
            <div className="h-full flex items-center justify-center text-muted italic">Cargando logs...</div>
          ) : (
            <pre className="whitespace-pre-wrap text-gray-300">
              {logs || "No hay logs disponibles para mostrar."}
            </pre>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-100 bg-gray-50/50 flex justify-between items-center text-[10px] text-gray-500 font-mono uppercase tracking-widest">
          <div className="flex items-center gap-2">
            <span className={`w-1.5 h-1.5 rounded-full ${isPaused ? 'bg-amber-500' : 'bg-indigo-500 animate-pulse'}`}></span>
            <span>{isPaused ? 'PAUSADO' : 'LIVE — AUTO REFRESH (3s)'}</span>
          </div>
          <span>Ultimas 50 líneas</span>
        </div>
      </div>
    </div>
  );
};

export default LogsModal;
