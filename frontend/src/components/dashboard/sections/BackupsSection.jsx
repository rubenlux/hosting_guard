import { useState, useEffect, useCallback } from 'react';
import {
  Database, RefreshCw, CheckCircle2, AlertTriangle, Clock,
  HardDrive, ChevronDown, Download, Trash2, Loader2,
} from 'lucide-react';
import { getHostingBackups, triggerBackup, downloadBackup, deleteBackup } from '../../../services/api';

function fmtSize(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('es-AR', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function buildFilename(b) {
  const name = (b.site_name || `hosting-${b.hosting_id}`)
    .replace(/[^a-zA-Z0-9_-]/g, '-');
  const d = new Date(b.created_at);
  const ts = isNaN(d)
    ? 'unknown'
    : `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`
      + `-${String(d.getHours()).padStart(2,'0')}${String(d.getMinutes()).padStart(2,'0')}${String(d.getSeconds()).padStart(2,'0')}`;
  return `hostingguard-backup-${name}-${ts}.tar.gz`;
}

const STATUS_CFG = {
  completed: { color: 'text-[#00ff88]', bg: 'bg-[#00ff88]/8 border-[#00ff88]/15', icon: CheckCircle2, label: 'completado' },
  partial:   { color: 'text-amber-400',  bg: 'bg-amber-500/8 border-amber-500/15',  icon: AlertTriangle, label: 'parcial' },
  pending:   { color: 'text-blue-400',   bg: 'bg-blue-500/8 border-blue-500/15',    icon: Clock,         label: 'en proceso' },
  running:   { color: 'text-blue-400',   bg: 'bg-blue-500/8 border-blue-500/15',    icon: Loader2,       label: 'ejecutando' },
  failed:    { color: 'text-red-400',    bg: 'bg-red-500/8 border-red-500/15',       icon: AlertTriangle, label: 'fallido' },
};

function BackupRow({ b, onDeleted }) {
  const cfg = STATUS_CFG[b.status] || STATUS_CFG.pending;
  const Icon = cfg.icon;
  const [downloading, setDownloading] = useState(false);
  const [deleting, setDeleting]       = useState(false);
  const [err, setErr]                 = useState(null);

  const handleDownload = async () => {
    setDownloading(true); setErr(null);
    try {
      await downloadBackup(b.backup_id, buildFilename(b));
    } catch (e) {
      setErr(e.response?.data?.detail || 'Error al descargar');
    } finally {
      setDownloading(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('¿Eliminar este backup? Esta acción no se puede deshacer.')) return;
    setDeleting(true); setErr(null);
    try {
      await deleteBackup(b.backup_id);
      onDeleted(b.backup_id);
    } catch (e) {
      setErr(e.response?.data?.detail || 'Error al eliminar');
      setDeleting(false);
    }
  };

  return (
    <div className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border ${cfg.bg} text-sm`}>
      <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${cfg.color} ${b.status === 'running' ? 'animate-spin' : ''}`} />

      <div className="flex-1 min-w-0">
        <div className="text-white/80 text-[12px] font-medium truncate">{b.site_name}</div>
        <div className="text-white/35 text-[10px] mt-0.5">{fmtDate(b.created_at)}</div>
        {b.error_message && (
          <div className="text-red-400/70 text-[10px] mt-0.5 truncate" title={b.error_message}>
            {b.error_message.slice(0, 90)}{b.error_message.length > 90 ? '…' : ''}
          </div>
        )}
        {err && <div className="text-red-400 text-[10px] mt-0.5">{err}</div>}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <div className="text-right">
          <div className={`text-[11px] font-semibold ${cfg.color}`}>{cfg.label}</div>
          <div className="text-white/30 text-[10px] flex items-center gap-1 justify-end mt-0.5">
            <HardDrive className="w-2.5 h-2.5" />{fmtSize(b.size_bytes)}
          </div>
        </div>

        {/* Download — only for completed */}
        {b.status === 'completed' && (
          <button
            onClick={handleDownload}
            disabled={downloading}
            title="Descargar backup"
            className="p-1.5 rounded-lg bg-[#00ff88]/10 border border-[#00ff88]/20 text-[#00ff88] hover:bg-[#00ff88]/20 transition-colors disabled:opacity-40"
          >
            {downloading
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Download className="w-3.5 h-3.5" />}
          </button>
        )}

        {/* Delete — failed/partial/pending only */}
        {(b.status === 'failed' || b.status === 'partial' || b.status === 'pending') && (
          <button
            onClick={handleDelete}
            disabled={deleting}
            title="Eliminar backup"
            className="p-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-40"
          >
            {deleting
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Trash2 className="w-3.5 h-3.5" />}
          </button>
        )}
      </div>
    </div>
  );
}

const BackupsSection = ({ hostings = [] }) => {
  const activeHostings = hostings.filter(h => h.status === 'active');
  const [selectedId, setSelectedId] = useState(null);
  const [backups, setBackups]       = useState([]);
  const [loading, setLoading]       = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [msg, setMsg]               = useState(null);

  const activeId   = selectedId ?? activeHostings[0]?.hosting_id ?? null;
  const activeSite = activeHostings.find(h => h.hosting_id === activeId);

  const load = useCallback(async () => {
    if (!activeId) return;
    setLoading(true);
    try {
      const data = await getHostingBackups(activeId);
      setBackups(data.items || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [activeId]);

  useEffect(() => { load(); }, [load]);

  const handleTrigger = async () => {
    if (!activeId || triggering) return;
    setTriggering(true); setMsg(null);
    try {
      await triggerBackup(activeId);
      setMsg({ type: 'success', text: 'Backup iniciado. Aparecerá en la lista en unos segundos.' });
      setTimeout(load, 5000);
    } catch (err) {
      const d = err.response?.data?.detail;
      setMsg({ type: 'error', text: d || 'No se pudo iniciar el backup.' });
    } finally { setTriggering(false); }
  };

  const handleDeleted = (backupId) => {
    setBackups(prev => prev.filter(b => b.backup_id !== backupId));
  };

  // Separate by visibility policy
  const visibleBackups = backups.filter(b => b.status !== 'partial' || false); // partial shown to client as-is

  if (activeHostings.length === 0) {
    return (
      <div style={{ maxWidth: 700, margin: '0 auto' }}>
        <div className="mb-6">
          <div className="text-[22px] font-black text-white mb-1">Backups</div>
          <div className="text-[13px] text-white/40">Respaldos automáticos y manuales de tus sitios.</div>
        </div>
        <div className="rounded-2xl border border-white/8 bg-[#111] px-8 py-12 text-center">
          <Database className="w-10 h-10 text-white/15 mx-auto mb-3" />
          <div className="text-white/40 text-sm">No tenés sitios activos.</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 700, margin: '0 auto' }}>
      <div className="mb-6">
        <div className="text-[22px] font-black text-white mb-1">Backups</div>
        <div className="text-[13px] text-white/40">
          Respaldos automáticos diarios + manuales on-demand. Descargá cualquier backup completado.
        </div>
      </div>

      {/* Site selector + action bar */}
      <div className="flex items-center gap-3 mb-4">
        {activeHostings.length > 1 ? (
          <div className="relative flex-1">
            <select
              value={activeId ?? ''}
              onChange={e => setSelectedId(Number(e.target.value))}
              className="w-full appearance-none bg-[#111] border border-white/10 text-white text-sm rounded-lg px-3 py-2 pr-8 focus:outline-none focus:border-white/25"
            >
              {activeHostings.map(h => (
                <option key={h.hosting_id} value={h.hosting_id}>{h.name || h.subdomain}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 pointer-events-none" />
          </div>
        ) : (
          <div className="flex-1 text-sm text-white/60 font-medium">{activeSite?.name || activeSite?.subdomain}</div>
        )}

        <button
          onClick={handleTrigger}
          disabled={triggering}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white/6 border border-white/10 text-white/70 text-[12px] font-semibold hover:bg-white/10 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${triggering ? 'animate-spin' : ''}`} />
          {triggering ? 'Iniciando...' : 'Crear backup ahora'}
        </button>

        <button
          onClick={load}
          disabled={loading}
          className="p-2 rounded-lg bg-white/4 border border-white/8 text-white/40 hover:text-white/70 hover:bg-white/8 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Feedback banner */}
      {msg && (
        <div className={`mb-3 px-3 py-2 rounded-lg text-[12px] border ${
          msg.type === 'success'
            ? 'bg-[#00ff88]/8 border-[#00ff88]/15 text-[#00ff88]'
            : 'bg-red-500/8 border-red-500/15 text-red-400'
        }`}>
          {msg.text}
        </div>
      )}

      {/* Backup list */}
      <div className="rounded-xl border border-white/8 bg-[#111] overflow-hidden">
        <div className="px-4 py-2.5 border-b border-white/6 flex items-center justify-between">
          <span className="text-[11px] font-semibold text-white/40 uppercase tracking-wider">Últimos 20 backups</span>
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-white/25">{visibleBackups.length} registros</span>
            {visibleBackups.filter(b => b.status === 'completed').length > 0 && (
              <span className="text-[10px] text-[#00ff88]/50 flex items-center gap-1">
                <Download className="w-2.5 h-2.5" />
                Descarga disponible
              </span>
            )}
          </div>
        </div>
        <div className="p-3 flex flex-col gap-2">
          {loading && visibleBackups.length === 0 ? (
            <div className="py-8 text-center text-[12px] text-white/25">Cargando...</div>
          ) : visibleBackups.length === 0 ? (
            <div className="py-10 text-center">
              <Database className="w-8 h-8 text-white/10 mx-auto mb-2" />
              <div className="text-[12px] text-white/25">
                Sin backups aún. El primer backup automático se ejecutará esta noche.
              </div>
            </div>
          ) : (
            visibleBackups.map(b => (
              <BackupRow key={b.backup_id} b={b} onDeleted={handleDeleted} />
            ))
          )}
        </div>
      </div>

      <div className="mt-3 text-[10px] text-white/20 text-center">
        Backups automáticos diarios · DB + wp-content · Descarga como .tar.gz
      </div>
    </div>
  );
};

export default BackupsSection;
