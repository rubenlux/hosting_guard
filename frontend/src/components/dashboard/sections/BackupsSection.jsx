import { useState, useEffect, useCallback } from 'react';
import {
  Database, RefreshCw, CheckCircle2, AlertTriangle, Clock,
  HardDrive, ChevronDown, Download, Trash2, Loader2, Lock,
  ShieldAlert, Calendar, Info,
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
  const name = (b.site_name || b.subdomain || `hosting-${b.hosting_id}`)
    .replace(/[^a-zA-Z0-9_-]/g, '-');
  const d = new Date(b.started_at || b.created_at);
  const ts = isNaN(d)
    ? 'unknown'
    : `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`
      + `-${String(d.getHours()).padStart(2,'0')}${String(d.getMinutes()).padStart(2,'0')}`;
  return `hostingguard-backup-${name}-${ts}.tar.gz`;
}

// Normalize backup from either tenant_backups or legacy backups table
function normalizeBackup(b) {
  return {
    ...b,
    size_bytes: b.total_size_bytes ?? b.size_bytes ?? 0,
    created_at: b.started_at ?? b.created_at,
    trigger: b.trigger ?? 'manual',
  };
}

const STATUS_CFG = {
  completed: { color: 'text-[#00ff88]', bg: 'bg-[#00ff88]/8 border-[#00ff88]/15', icon: CheckCircle2, label: 'completado' },
  partial:   { color: 'text-amber-400',  bg: 'bg-amber-500/8 border-amber-500/15',  icon: AlertTriangle, label: 'parcial' },
  pending:   { color: 'text-blue-400',   bg: 'bg-blue-500/8 border-blue-500/15',    icon: Clock,         label: 'en proceso' },
  running:   { color: 'text-blue-400',   bg: 'bg-blue-500/8 border-blue-500/15',    icon: Loader2,       label: 'ejecutando' },
  failed:    { color: 'text-red-400',    bg: 'bg-red-500/8 border-red-500/15',      icon: AlertTriangle, label: 'fallido' },
};

const TRIGGER_LABEL = {
  schedule:    'automático',
  manual:      'manual',
  pre_restore: 'pre-restauración',
  pre_delete:  'pre-eliminación',
  system:      'sistema',
};

function BackupRow({ b, onDeleted }) {
  const norm = normalizeBackup(b);
  const cfg = STATUS_CFG[norm.status] || STATUS_CFG.pending;
  const Icon = cfg.icon;
  const [downloading, setDownloading] = useState(false);
  const [deleting, setDeleting]       = useState(false);
  const [err, setErr]                 = useState(null);

  const handleDownload = async () => {
    setDownloading(true); setErr(null);
    try {
      await downloadBackup(norm.backup_id, buildFilename(norm));
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
      await deleteBackup(norm.backup_id);
      onDeleted(norm.backup_id);
    } catch (e) {
      setErr(e.response?.data?.detail || 'Error al eliminar');
      setDeleting(false);
    }
  };

  const triggerLabel = TRIGGER_LABEL[norm.trigger] || norm.trigger;

  return (
    <div className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border ${cfg.bg} text-sm`}>
      <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${cfg.color} ${norm.status === 'running' ? 'animate-spin' : ''}`} />

      <div className="flex-1 min-w-0">
        <div className="text-white/80 text-[12px] font-medium truncate">
          {norm.site_name || norm.subdomain || `hosting-${norm.hosting_id}`}
        </div>
        <div className="text-white/35 text-[10px] mt-0.5 flex items-center gap-2">
          <span>{fmtDate(norm.created_at)}</span>
          <span className="text-white/20">·</span>
          <span className="text-white/25">{triggerLabel}</span>
          {norm.backup_type && norm.backup_type !== 'full' && (
            <>
              <span className="text-white/20">·</span>
              <span className="text-white/25">{norm.backup_type}</span>
            </>
          )}
        </div>
        {norm.error_message && (
          <div className="text-red-400/70 text-[10px] mt-0.5 truncate" title={norm.error_message}>
            {String(norm.error_message).slice(0, 90)}{String(norm.error_message).length > 90 ? '…' : ''}
          </div>
        )}
        {err && <div className="text-red-400 text-[10px] mt-0.5">{err}</div>}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <div className="text-right">
          <div className={`text-[11px] font-semibold ${cfg.color}`}>{cfg.label}</div>
          <div className="text-white/30 text-[10px] flex items-center gap-1 justify-end mt-0.5">
            <HardDrive className="w-2.5 h-2.5" />{fmtSize(norm.size_bytes)}
          </div>
        </div>

        {norm.status === 'completed' && (
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

        {['failed', 'partial', 'pending'].includes(norm.status) && (
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

// Upsell banner shown when manual backups are not available on the plan
function BackupUpsellBanner({ plan }) {
  const isPlanKnown = !!plan;
  return (
    <div className="rounded-xl border border-white/8 bg-[#111] overflow-hidden">
      <div className="px-6 py-10 flex flex-col items-center text-center gap-4">
        <div className="w-12 h-12 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
          <Lock className="w-5 h-5 text-white/30" />
        </div>
        <div>
          <div className="text-white/70 text-sm font-semibold mb-1">
            Backups no incluidos en tu plan
          </div>
          <div className="text-white/35 text-[12px] max-w-xs mx-auto leading-relaxed">
            Los backups manuales y automáticos están disponibles como add-on
            o incluidos en planes superiores.
          </div>
        </div>
        <div className="flex flex-col gap-1.5 w-full max-w-xs">
          <div className="text-[11px] text-white/25 font-medium uppercase tracking-wider">Incluido en</div>
          <div className="flex gap-2 justify-center flex-wrap">
            {['Negocio', 'Agencia', 'Agencia Pro', 'Enterprise'].map(p => (
              <span key={p}
                className="px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-[11px] text-white/50">
                {p}
              </span>
            ))}
          </div>
        </div>
        <div className="mt-1 px-3 py-2 rounded-lg bg-amber-500/8 border border-amber-500/15 flex items-start gap-2 text-left max-w-xs w-full">
          <Info className="w-3.5 h-3.5 text-amber-400/70 shrink-0 mt-0.5" />
          <div className="text-[10px] text-amber-400/70 leading-relaxed">
            Backup local protege contra errores de deploys, pero no contra pérdida
            total del servidor. Backup externo disponible en planes superiores.
          </div>
        </div>
      </div>
    </div>
  );
}

// Banner for plans with manual backup but no automatic daily
function AutomaticUpsellBanner() {
  return (
    <div className="mt-3 px-3 py-2.5 rounded-lg bg-white/3 border border-white/6 flex items-start gap-2">
      <Calendar className="w-3.5 h-3.5 text-white/25 shrink-0 mt-0.5" />
      <div className="text-[11px] text-white/30 leading-relaxed">
        Backups diarios automáticos disponibles en planes <span className="text-white/50">Agencia Pro</span> y <span className="text-white/50">Enterprise</span>.
        Se conserva solo el último backup diario por sitio.
      </div>
    </div>
  );
}

const BackupsSection = ({ hostings = [], user = null }) => {
  const activeHostings = hostings.filter(h => ['active', 'active_with_placeholder'].includes(h.status));
  const [selectedId, setSelectedId]   = useState(null);
  const [backups, setBackups]         = useState([]);
  const [loading, setLoading]         = useState(false);
  const [triggering, setTriggering]   = useState(false);
  const [msg, setMsg]                 = useState(null);

  const activeId   = selectedId ?? activeHostings[0]?.hosting_id ?? null;
  const activeSite = activeHostings.find(h => h.hosting_id === activeId);

  // Derive entitlement from hosting plan or user plan
  const userPlan = activeSite?.plan || user?.plan || 'free';
  const isAdmin  = user?.role === 'admin';
  const manualEnabled = isAdmin
    || ['negocio', 'agencia', 'agencia_pro', 'enterprise', 'enterprise_annual', 'enterprise_monthly'].includes(userPlan);
  const autoEnabled = isAdmin
    || ['agencia_pro', 'enterprise', 'enterprise_annual', 'enterprise_monthly'].includes(userPlan);

  const load = useCallback(async () => {
    if (!activeId) return;
    setLoading(true);
    try {
      const data = await getHostingBackups(activeId);
      const rows = Array.isArray(data) ? data : (data?.items ?? []);
      setBackups(rows.map(normalizeBackup));
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
      setTimeout(load, 4000);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.code === 'backup_plan_required') {
        setMsg({ type: 'plan', text: detail.message || 'Los backups no están incluidos en tu plan.' });
      } else if (detail?.code === 'backup_already_running') {
        setMsg({ type: 'warn', text: 'Ya hay un backup en progreso para este sitio.' });
      } else {
        const text = typeof detail === 'string' ? detail : (detail?.message || 'No se pudo iniciar el backup.');
        setMsg({ type: 'error', text });
      }
    } finally { setTriggering(false); }
  };

  const handleDeleted = (backupId) => {
    setBackups(prev => prev.filter(b => b.backup_id !== backupId));
  };

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

  // No entitlement: show upsell
  if (!manualEnabled) {
    return (
      <div style={{ maxWidth: 700, margin: '0 auto' }}>
        <div className="mb-6">
          <div className="text-[22px] font-black text-white mb-1">Backups</div>
          <div className="text-[13px] text-white/40">
            Respaldos locales del sitio y base de datos.
          </div>
        </div>
        <BackupUpsellBanner plan={userPlan} />
      </div>
    );
  }

  const visibleBackups = backups.filter(b => b.status !== 'deleted');

  return (
    <div style={{ maxWidth: 700, margin: '0 auto' }}>
      <div className="mb-6">
        <div className="text-[22px] font-black text-white mb-1">Backups</div>
        <div className="text-[13px] text-white/40">
          {autoEnabled
            ? 'Backups automáticos diarios + manuales on-demand.'
            : 'Backups manuales on-demand. Descargá cualquier backup completado.'}
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
        <div className={`mb-3 px-3 py-2 rounded-lg text-[12px] border flex items-start gap-2 ${
          msg.type === 'success'
            ? 'bg-[#00ff88]/8 border-[#00ff88]/15 text-[#00ff88]'
            : msg.type === 'plan'
            ? 'bg-amber-500/8 border-amber-500/15 text-amber-400'
            : msg.type === 'warn'
            ? 'bg-blue-500/8 border-blue-500/15 text-blue-400'
            : 'bg-red-500/8 border-red-500/15 text-red-400'
        }`}>
          {msg.type === 'plan' && <Lock className="w-3.5 h-3.5 shrink-0 mt-0.5" />}
          {msg.type === 'warn' && <ShieldAlert className="w-3.5 h-3.5 shrink-0 mt-0.5" />}
          <span>{msg.text}</span>
        </div>
      )}

      {/* Backup list */}
      <div className="rounded-xl border border-white/8 bg-[#111] overflow-hidden">
        <div className="px-4 py-2.5 border-b border-white/6 flex items-center justify-between">
          <span className="text-[11px] font-semibold text-white/40 uppercase tracking-wider">
            Últimos {Math.max(visibleBackups.length, 20)} backups
          </span>
          <div className="flex items-center gap-3">
            <span className="text-[10px] text-white/25">{visibleBackups.length} registros</span>
            {autoEnabled && (
              <span className="text-[10px] text-white/25 flex items-center gap-1">
                <Calendar className="w-2.5 h-2.5" />
                Retención: último diario
              </span>
            )}
            {visibleBackups.some(b => b.status === 'completed') && (
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
                {autoEnabled
                  ? 'Sin backups aún. El primer backup automático se ejecutará esta noche.'
                  : 'Sin backups. Creá uno manualmente con el botón de arriba.'}
              </div>
            </div>
          ) : (
            visibleBackups.map(b => (
              <BackupRow key={b.backup_id} b={b} onDeleted={handleDeleted} />
            ))
          )}
        </div>
      </div>

      {/* Automatic upsell (plan has manual but not auto) */}
      {!autoEnabled && <AutomaticUpsellBanner />}

      {/* Storage notice */}
      <div className="mt-3 px-3 py-2 rounded-lg bg-white/2 border border-white/5">
        <div className="text-[10px] text-white/20 leading-relaxed">
          Backup local · Protege contra errores de deploys y cambios accidentales ·
          No cubre pérdida total del servidor · Descarga como .tar.gz ·
          {autoEnabled ? ' Se conserva solo el último backup diario por sitio' : ' Máx. 2 backups manuales por sitio'}
        </div>
      </div>
    </div>
  );
};

export default BackupsSection;
