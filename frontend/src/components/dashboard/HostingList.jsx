import React, { useState } from 'react';
import {
  Globe, Cpu, Database, RefreshCw, Upload, FolderOpen,
  Square, RotateCcw, FileText, Play, Trash2, Loader, HardDriveDownload,
  KeyRound, Copy, Check,
} from 'lucide-react';

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button onClick={handle} className="text-gray-500 hover:text-indigo-400 transition-colors ml-1">
      {copied ? <Check className="w-3 h-3 text-green-400" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

/**
 * Maps a hosting status string to the CSS class used for the status badge.
 * Defined at module level (not inside the component) so it is never re-created on render.
 */
function getStatusClass(status) {
  switch (status) {
    case 'active':    return 'ok';
    case 'starting':  return 'starting';
    case 'stopped':   return 'error';
    case 'error':     return 'error';
    case 'not_found': return 'error';
    default:          return 'warn';
  }
}

/**
 * Renders the list of hosting cards with action buttons.
 * Pure presentation — all data and handlers come via props.
 */
export default function HostingList({
  hostings,
  loading,
  healthData,
  isSupportSession,
  actionLoading,
  onRefresh,
  onStart,
  onStop,
  onRestart,
  onOpenLogs,
  onDelete,
  onUploadZip,
  onOpenFiles,
  onImportBackup,
}) {
  return (
    <div className="card-dash">
      <div className="card-header-dash">
        <div className="text-sm font-bold flex items-center gap-2">
          <Globe className="w-4 h-4 text-accent" /> Sus Proyectos
        </div>
        <button onClick={onRefresh} className="text-gray-400 hover:text-indigo-600 transition-colors">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="p-4 space-y-2">
        {loading && hostings.length === 0 ? (
          <div className="py-12 flex justify-center">
            <Loader className="animate-spin text-accent" />
          </div>
        ) : hostings.length === 0 ? (
          <div className="py-12 text-center text-muted italic">No hay hostings activos.</div>
        ) : hostings.map(h => (
          <div key={h.hosting_id} className="domain-row-dash group">
            <div className="w-10 h-10 bg-[#1a1a24] border border-white/10 rounded-xl flex items-center justify-center font-bold text-indigo-400 transition-colors group-hover:bg-[#20202c]">
              {h.name[0].toUpperCase()}
            </div>

            <div className="flex-1">
              <div className="text-sm font-bold text-white group-hover:text-indigo-400 transition-colors">{h.name}</div>
              {h.plan === 'free' && h.expires_in_days != null && (
                <span className={`text-[9px] font-black px-2 py-0.5 rounded-full uppercase tracking-wider ${
                  h.expires_in_days <= 0    ? 'bg-red-500/20 text-red-400'
                  : h.expires_in_days <= 3  ? 'bg-warn/20 text-warn'
                  : 'bg-accent/20 text-accent'
                }`}>
                  {h.expires_in_days <= 0 ? 'Expirado' : `${h.expires_in_days}d restantes`}
                </span>
              )}
              <div className="flex items-center gap-2">
                <a
                  href={h.url || `https://${h.subdomain}`}
                  target="_blank" rel="noopener"
                  className="text-[11px] text-muted font-mono hover:underline"
                >
                  {h.subdomain}
                </a>
                {healthData[h.hosting_id] && (
                  <div className="flex items-center gap-2 text-[10px] bg-[#121214] px-2 py-0.5 rounded border border-white/10 font-mono text-gray-400">
                    <span className="flex items-center gap-1"><Cpu className="w-2.5 h-2.5" /> {healthData[h.hosting_id].cpu}%</span>
                    <span className="flex items-center gap-1"><Database className="w-2.5 h-2.5" /> {healthData[h.hosting_id].ram}%</span>
                  </div>
                )}
                {healthData[h.hosting_id] && (
                  <div className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider ${
                    healthData[h.hosting_id].score >= 90 ? 'bg-green-500/20 text-green-400'
                    : healthData[h.hosting_id].score >= 70 ? 'bg-warn/20 text-warn'
                    : 'bg-danger/20 text-danger'
                  }`}>
                    Salud: {healthData[h.hosting_id].score ?? 0}%
                  </div>
                )}
              </div>
              {h.wp_admin_password && (
                <div className="flex items-center gap-2 mt-1 text-[10px] font-mono text-gray-500">
                  <KeyRound className="w-3 h-3 text-indigo-500/60" />
                  <span>admin</span>
                  <span className="text-gray-600">/</span>
                  <span className="text-indigo-400">{h.wp_admin_password}</span>
                  <CopyButton text={h.wp_admin_password} />
                  <a
                    href={`${h.url || `https://${h.subdomain}`}/wp-admin`}
                    target="_blank" rel="noopener"
                    className="ml-1 text-[9px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20 border border-indigo-500/20 transition-colors"
                  >
                    wp-admin
                  </a>
                </div>
              )}
            </div>

            <div className="ml-auto flex items-center gap-2">
              <div className={`domain-status-dash ${getStatusClass(h.status)} ${h.status === 'active' ? 'animate-led shadow-[0_0_10px_rgba(0,255,136,0.5)]' : ''}`}>
                ● {h.status}
              </div>

              <div className="flex items-center gap-1 border-l border-white/10 pl-2 ml-2">
                {actionLoading === h.hosting_id ? (
                  <div className="w-8 h-8 flex items-center justify-center">
                    <Loader className="w-3.5 h-3.5 animate-spin text-indigo-600" />
                  </div>
                ) : (
                  <>
                    {h.status === 'active' && (
                      <>
                        <button
                          onClick={() => onUploadZip(h)}
                          title="Subir archivos (.zip)"
                          className="w-8 h-8 rounded-lg bg-white/5 text-gray-400 hover:bg-emerald-500/10 hover:text-emerald-400 flex items-center justify-center transition-all border border-transparent hover:border-emerald-500/20"
                        >
                          <Upload className="w-3.5 h-3.5" />
                        </button>
                        {!h.container_name?.includes('_wp_') && (
                          <button
                            onClick={() => onOpenFiles(h)}
                            title="Gestor de archivos"
                            className="w-8 h-8 rounded-lg bg-white/5 text-gray-400 hover:bg-blue-500/10 hover:text-blue-400 flex items-center justify-center transition-all border border-transparent hover:border-blue-500/20"
                          >
                            <FolderOpen className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          onClick={() => onImportBackup?.(h)}
                          title="Importar backup"
                          className="w-8 h-8 rounded-lg bg-white/5 text-gray-400 hover:bg-blue-500/10 hover:text-blue-400 flex items-center justify-center transition-all border border-transparent hover:border-blue-500/20"
                        >
                          <HardDriveDownload className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => onStop(h.hosting_id)}
                          title="Detener"
                          className="w-8 h-8 rounded-lg bg-white/5 text-gray-400 hover:bg-red-500/10 hover:text-red-400 flex items-center justify-center transition-all border border-transparent hover:border-red-500/20"
                        >
                          <Square className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => onRestart(h.hosting_id)}
                          title="Reiniciar"
                          className="w-8 h-8 rounded-lg bg-white/5 text-gray-400 hover:bg-indigo-500/10 hover:text-indigo-400 flex items-center justify-center transition-all border border-transparent hover:border-indigo-500/20"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                        </button>
                      </>
                    )}

                    {h.status !== 'not_found' && (
                      <button
                        onClick={() => onOpenLogs(h)}
                        title="Ver Logs"
                        className="w-8 h-8 rounded-lg bg-white/5 text-gray-400 hover:bg-indigo-500/10 hover:text-indigo-400 flex items-center justify-center transition-all border border-transparent hover:border-indigo-500/20"
                      >
                        <FileText className="w-3.5 h-3.5" />
                      </button>
                    )}

                    {h.status === 'stopped' && (
                      <button
                        onClick={() => onStart(h.hosting_id)}
                        title="Iniciar"
                        className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 hover:bg-indigo-600 hover:text-white flex items-center justify-center transition-all"
                      >
                        <Play className="w-3.5 h-3.5" />
                      </button>
                    )}

                    {h.status === 'starting' && (
                      <div className="w-8 h-8 flex items-center justify-center">
                        <RefreshCw className="w-3.5 h-3.5 animate-spin text-muted" />
                      </div>
                    )}

                    {!isSupportSession && (
                      <button
                        onClick={() => onDelete(h.hosting_id, h.name)}
                        title="Eliminar"
                        className="w-8 h-8 rounded-lg bg-danger/10 text-danger flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all hover:bg-danger hover:text-white"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
