import React, { useEffect, useState, useCallback } from 'react';
import {
  Archive, Play, Pause, RefreshCw, Trash2, Shield, ShieldOff,
  ChevronDown, ChevronRight, Loader2, AlertTriangle, CheckCircle2,
  Settings, History, RotateCcw, Zap, Clock, Lock, Database,
} from 'lucide-react';
import {
  getAdminBackupPolicy, updateAdminBackupPolicy, adminCreateBackup,
  adminPauseBackups, adminResumeBackups, adminCleanupBackups,
  getAdminBackupPolicyHistory, revertAdminBackupPolicy,
  getAdminBackupList,
} from '../../services/api';

function getErrorMsg(e, fallback = 'Error inesperado') {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return String(detail.message);
  if (detail?.error_message) return String(detail.error_message);
  if (detail?.code) return `Error: ${detail.code}`;
  if (e?.message) return String(e.message);
  return fallback;
}

// ── helpers ───────────────────────────────────────────────────────────────────

function fmtDate(str) {
  if (!str) return '—';
  return new Date(str).toLocaleString('es-AR', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function fmtBytes(n) {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(1)} ${units[i]}`;
}

// ── status badge ──────────────────────────────────────────────────────────────

function PolicyBadge({ policy }) {
  if (!policy) return null;

  if (policy.paused)
    return <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30">Pausado</span>;
  if (policy.admin_override)
    return <span className="px-2 py-0.5 text-xs rounded-full bg-purple-500/15 text-purple-400 border border-purple-500/30">Override admin</span>;
  if (policy.automatic_backup_enabled && policy.manual_backup_enabled)
    return <span className="px-2 py-0.5 text-xs rounded-full bg-green-500/15 text-green-400 border border-green-500/30">Diario + manual</span>;
  if (policy.manual_backup_enabled)
    return <span className="px-2 py-0.5 text-xs rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/30">Solo manual</span>;
  return <span className="px-2 py-0.5 text-xs rounded-full bg-zinc-600/40 text-zinc-400 border border-zinc-600/40">Sin backups</span>;
}

function SourceBadge({ source }) {
  const map = {
    admin_override: ['Override', 'text-purple-400 bg-purple-500/10'],
    addon:          ['Add-on',   'text-blue-400 bg-blue-500/10'],
    plan:           ['Plan',     'text-green-400 bg-green-500/10'],
    default:        ['Default',  'text-zinc-400 bg-zinc-700/30'],
  };
  const [label, cls] = map[source] || ['Desconocido', 'text-zinc-400 bg-zinc-700/30'];
  return <span className={`px-1.5 py-0.5 text-[11px] rounded font-medium ${cls}`}>{label}</span>;
}

// ── editable policy form ──────────────────────────────────────────────────────

function PolicyForm({ policy, onSave, saving }) {
  const [form, setForm] = useState({
    automatic_backup_enabled: policy.automatic_backup_enabled,
    manual_backup_enabled:    policy.manual_backup_enabled,
    backup_frequency:         policy.backup_frequency,
    retention_policy:         policy.retention_policy,
    max_manual_backups:       policy.max_manual_backups,
    max_backup_storage_mb:    policy.max_backup_storage_mb,
    admin_override:           policy.admin_override,
    addon_active:             policy.addon_active,
    paused:                   policy.paused,
    paused_reason:            policy.paused_reason || '',
    change_reason:            '',
  });

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        {/* toggles */}
        {[
          ['automatic_backup_enabled', 'Backup automático diario'],
          ['manual_backup_enabled',    'Backup manual habilitado'],
          ['admin_override',           'Admin override'],
          ['addon_active',             'Add-on activo'],
          ['paused',                   'Pausado'],
        ].map(([k, label]) => (
          <label key={k} className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              className="accent-indigo-500 w-4 h-4"
              checked={!!form[k]}
              onChange={e => set(k, e.target.checked)}
            />
            <span className="text-sm text-zinc-300">{label}</span>
          </label>
        ))}
      </div>

      {form.paused && (
        <div>
          <label className="text-xs text-zinc-500 uppercase tracking-wide">Motivo pausa</label>
          <input
            className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
            value={form.paused_reason}
            onChange={e => set('paused_reason', e.target.value)}
            placeholder="ej. riesgo de espacio en disco"
          />
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-xs text-zinc-500 uppercase tracking-wide">Frecuencia</label>
          <select
            className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
            value={form.backup_frequency}
            onChange={e => set('backup_frequency', e.target.value)}
          >
            <option value="none">none</option>
            <option value="manual">manual</option>
            <option value="daily">daily</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-zinc-500 uppercase tracking-wide">Retención</label>
          <select
            className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
            value={form.retention_policy}
            onChange={e => set('retention_policy', e.target.value)}
          >
            <option value="latest_only">latest_only</option>
            <option value="ttl">ttl</option>
            <option value="manual_limited">manual_limited</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-zinc-500 uppercase tracking-wide">Max manuales</label>
          <input
            type="number" min={0} max={10}
            className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
            value={form.max_manual_backups}
            onChange={e => set('max_manual_backups', parseInt(e.target.value) || 0)}
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-zinc-500 uppercase tracking-wide">Límite storage MB</label>
          <input
            type="number" min={256}
            className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
            value={form.max_backup_storage_mb}
            onChange={e => set('max_backup_storage_mb', parseInt(e.target.value) || 2048)}
          />
        </div>
        <div>
          <label className="text-xs text-zinc-500 uppercase tracking-wide">Motivo cambio</label>
          <input
            className="mt-1 w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
            value={form.change_reason}
            onChange={e => set('change_reason', e.target.value)}
            placeholder="opcional — queda en historial"
          />
        </div>
      </div>

      {form.automatic_backup_enabled && (
        <p className="text-xs text-amber-400/80 border border-amber-500/20 bg-amber-500/5 rounded px-3 py-2">
          Los backups automáticos diarios conservan solo el último backup exitoso para cuidar disco.
        </p>
      )}

      <button
        onClick={() => onSave(form)}
        disabled={saving}
        className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
      >
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Settings size={14} />}
        Guardar política
      </button>
    </div>
  );
}

// ── history table ─────────────────────────────────────────────────────────────

function HistoryTable({ hostingId, onRevert }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const [reverting, setReverting] = useState(null);
  const [reason, setReason] = useState('');

  useEffect(() => {
    getAdminBackupPolicyHistory(hostingId)
      .then(setHistory)
      .catch(() => setHistory([]))
      .finally(() => setLoading(false));
  }, [hostingId]);

  const doRevert = async (historyId) => {
    setReverting(historyId);
    try {
      await revertAdminBackupPolicy(hostingId, historyId, reason || 'revert manual');
      onRevert();
    } finally {
      setReverting(null);
    }
  };

  if (loading) return <div className="text-zinc-500 text-sm py-4 text-center"><Loader2 size={16} className="animate-spin inline" /></div>;
  if (!history.length) return <p className="text-zinc-500 text-sm py-3">Sin historial de cambios.</p>;

  return (
    <div className="space-y-1">
      {history.map(h => (
        <div key={h.history_id} className="border border-zinc-800 rounded-lg overflow-hidden">
          <button
            onClick={() => setExpanded(expanded === h.history_id ? null : h.history_id)}
            className="w-full flex items-center justify-between px-3 py-2 hover:bg-zinc-800/50 text-left"
          >
            <div className="flex items-center gap-2">
              {expanded === h.history_id ? <ChevronDown size={13} className="text-zinc-500" /> : <ChevronRight size={13} className="text-zinc-500" />}
              <span className="text-xs text-zinc-400">{fmtDate(h.created_at)}</span>
              {h.change_reason && <span className="text-xs text-zinc-500">— {h.change_reason}</span>}
            </div>
            <span className="text-xs text-zinc-600">#{h.history_id}</span>
          </button>
          {expanded === h.history_id && (
            <div className="px-3 pb-3 space-y-2 border-t border-zinc-800 pt-2">
              <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                <div>
                  <p className="text-zinc-500 mb-1">Anterior</p>
                  <pre className="bg-zinc-900 rounded p-2 text-zinc-400 overflow-auto max-h-32 text-[10px]">
                    {JSON.stringify(h.previous_policy_json, null, 2)}
                  </pre>
                </div>
                <div>
                  <p className="text-zinc-500 mb-1">Nuevo</p>
                  <pre className="bg-zinc-900 rounded p-2 text-zinc-400 overflow-auto max-h-32 text-[10px]">
                    {JSON.stringify(h.new_policy_json, null, 2)}
                  </pre>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input
                  className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 focus:outline-none focus:border-indigo-500"
                  placeholder="Motivo reversión (opcional)"
                  value={reason}
                  onChange={e => setReason(e.target.value)}
                />
                <button
                  onClick={() => doRevert(h.history_id)}
                  disabled={reverting === h.history_id}
                  className="flex items-center gap-1 px-3 py-1 bg-amber-600/80 hover:bg-amber-500 disabled:opacity-50 text-white text-xs rounded transition-colors"
                >
                  {reverting === h.history_id ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
                  Revertir
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── admin backup list ─────────────────────────────────────────────────────────

const STATUS_COLOR = {
  completed: 'text-green-400',
  failed:    'text-red-400',
  running:   'text-blue-400',
  pending:   'text-blue-400',
  partial:   'text-amber-400',
};

function BackupListTab({ hostingId }) {
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  useEffect(() => {
    setLoading(true);
    getAdminBackupList(hostingId)
      .then(d => setBackups(d.items || []))
      .catch(e => setError(getErrorMsg(e, 'Error cargando backups')))
      .finally(() => setLoading(false));
  }, [hostingId]);

  if (loading) return (
    <div className="flex items-center gap-2 py-6 text-zinc-500 text-sm">
      <Loader2 size={14} className="animate-spin" /> Cargando backups...
    </div>
  );
  if (error) return (
    <div className="flex items-center gap-2 py-4 text-red-400 text-sm" data-testid="backup-list-error">
      <AlertTriangle size={14} /> {error}
    </div>
  );
  if (!backups.length) return (
    <div className="flex items-center gap-2 py-4 text-zinc-500 text-sm">
      <Database size={14} /> Sin backups registrados.
    </div>
  );

  return (
    <div className="space-y-1.5" data-testid="backup-list">
      {backups.map(b => (
        <div key={b.backup_id}
          className="flex items-center gap-3 px-3 py-2 rounded-lg bg-zinc-800/50 border border-zinc-800 text-xs">
          <span className={`font-medium shrink-0 ${STATUS_COLOR[b.status] || 'text-zinc-400'}`}>
            {b.status}
          </span>
          <span className="text-zinc-400 flex-1 truncate">
            {b.backup_type} · {b.trigger}
            {b.total_size_bytes ? ` · ${(b.total_size_bytes / (1024 * 1024)).toFixed(1)} MB` : ''}
          </span>
          {b.protected && (
            <Shield size={12} className="text-amber-400 shrink-0" title="Protegido" />
          )}
          <span className="text-zinc-600 shrink-0">{fmtDate(b.started_at)}</span>
        </div>
      ))}
    </div>
  );
}


// ── cleanup panel ─────────────────────────────────────────────────────────────

function CleanupPanel({ hostingId }) {
  const [mode, setMode] = useState('all_safe');
  const [dryRun, setDryRun] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const run = async () => {
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const r = await adminCleanupBackups(hostingId, mode, dryRun);
      setResult(r);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Error inesperado');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <select
          className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm text-zinc-200 focus:outline-none focus:border-indigo-500"
          value={mode}
          onChange={e => setMode(e.target.value)}
        >
          <option value="all_safe">all_safe (todos los seguros)</option>
          <option value="expired">expired (TTL vencidos)</option>
          <option value="automatic_previous">automatic_previous</option>
          <option value="old_manual">old_manual (exceso manual)</option>
        </select>
        <label className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
          <input type="checkbox" className="accent-indigo-500" checked={dryRun} onChange={e => setDryRun(e.target.checked)} />
          Dry-run
        </label>
        <button
          onClick={run}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-50 text-zinc-200 text-sm rounded-lg transition-colors"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
          {dryRun ? 'Simular cleanup' : 'Ejecutar cleanup'}
        </button>
      </div>
      {dryRun && <p className="text-xs text-amber-400/70">Dry-run activo — no se borrarán archivos reales.</p>}
      {result && (
        <pre className="bg-zinc-900 rounded p-3 text-xs text-green-400 font-mono overflow-auto">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}

// ── main panel ────────────────────────────────────────────────────────────────

export default function BackupPolicyPanel({ hostingId }) {
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [actionMsg, setActionMsg] = useState(null);
  const [section, setSection] = useState('policy'); // policy | history | cleanup
  const [creatingBackup, setCreatingBackup] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    getAdminBackupPolicy(hostingId)
      .then(setPolicy)
      .catch(e => setError(getErrorMsg(e, 'Error al cargar política')))
      .finally(() => setLoading(false));
  }, [hostingId]);

  useEffect(() => { load(); }, [load]);

  const flash = (msg, ok = true) => {
    setActionMsg({ msg, ok });
    setTimeout(() => setActionMsg(null), 3500);
  };

  const handleSave = async (form) => {
    setSaving(true);
    try {
      await updateAdminBackupPolicy(hostingId, form);
      await load();
      flash('Política guardada');
    } catch (e) {
      flash(getErrorMsg(e, 'Error al guardar'), false);
    } finally {
      setSaving(false);
    }
  };

  const handlePause = async () => {
    const reason = window.prompt('Motivo pausa:');
    if (reason === null) return;
    try {
      await adminPauseBackups(hostingId, reason || 'pausado por admin');
      await load();
      flash('Backups pausados');
    } catch (e) {
      flash(getErrorMsg(e, 'Error al pausar'), false);
    }
  };

  const handleResume = async () => {
    try {
      await adminResumeBackups(hostingId, 'reanudado por admin');
      await load();
      flash('Backups reanudados');
    } catch (e) {
      flash(getErrorMsg(e, 'Error al reanudar'), false);
    }
  };

  const handleForceBackup = async () => {
    setCreatingBackup(true);
    try {
      await adminCreateBackup(hostingId, { backup_type: 'full', reason: 'backup manual admin' });
      flash('Backup iniciado');
    } catch (e) {
      flash(getErrorMsg(e, 'Error al crear backup'), false);
    } finally {
      setCreatingBackup(false);
    }
  };

  if (loading) return (
    <div className="flex items-center gap-2 py-6 text-zinc-500">
      <Loader2 size={16} className="animate-spin" />
      <span className="text-sm">Cargando política...</span>
    </div>
  );

  if (error) return (
    <div className="flex items-center gap-2 py-4 text-red-400 text-sm">
      <AlertTriangle size={15} />
      {error}
    </div>
  );

  const tabs = [
    { id: 'policy',  label: 'Política',  icon: Settings },
    { id: 'backups', label: 'Backups',   icon: Database },
    { id: 'history', label: 'Historial', icon: History },
    { id: 'cleanup', label: 'Cleanup',   icon: Trash2 },
  ];

  return (
    <div className="space-y-4">
      {/* header row */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Archive size={16} className="text-indigo-400" />
          <span className="text-sm font-medium text-zinc-200">Política de Backups</span>
          {policy && <PolicyBadge policy={policy} />}
          {policy && <SourceBadge source={policy.source} />}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleForceBackup}
            disabled={creatingBackup}
            title="Crear backup ahora (ignora pausa y plan)"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-700/60 hover:bg-indigo-600/70 disabled:opacity-50 text-indigo-200 text-xs rounded-lg transition-colors"
          >
            {creatingBackup ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
            Backup ahora
          </button>

          {policy?.paused ? (
            <button
              onClick={handleResume}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-green-700/50 hover:bg-green-600/60 text-green-200 text-xs rounded-lg transition-colors"
            >
              <Play size={13} />
              Reanudar
            </button>
          ) : (
            <button
              onClick={handlePause}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-700/40 hover:bg-amber-600/50 text-amber-200 text-xs rounded-lg transition-colors"
            >
              <Pause size={13} />
              Pausar
            </button>
          )}

          <button onClick={load} className="p-1.5 text-zinc-500 hover:text-zinc-300 transition-colors" title="Recargar">
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* flash message */}
      {actionMsg && (
        <div className={`flex items-center gap-2 text-xs px-3 py-2 rounded-lg border ${
          actionMsg.ok
            ? 'text-green-400 bg-green-500/10 border-green-500/25'
            : 'text-red-400 bg-red-500/10 border-red-500/25'
        }`}>
          {actionMsg.ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
          {actionMsg.msg}
        </div>
      )}

      {/* paused warning */}
      {policy?.paused && (
        <div className="flex items-start gap-2 text-xs px-3 py-2 rounded-lg bg-amber-500/8 border border-amber-500/25 text-amber-300">
          <Lock size={13} className="mt-0.5 shrink-0" />
          <span>Backups automáticos pausados{policy.paused_reason ? `: ${policy.paused_reason}` : ''}. El admin puede ejecutar backup manual aunque esté pausado.</span>
        </div>
      )}

      {/* no entitlement notice */}
      {policy && !policy.manual_backup_enabled && !policy.admin_override && (
        <div className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg bg-zinc-800/60 border border-zinc-700/50 text-zinc-400">
          <ShieldOff size={13} />
          No incluido en plan ({policy.plan}). Activa <strong className="text-zinc-300">admin_override</strong> para habilitar manualmente.
        </div>
      )}

      {/* stat row */}
      {policy && (
        <div className="grid grid-cols-4 gap-2 text-xs">
          {[
            ['Frecuencia',  policy.backup_frequency],
            ['Retención',   policy.retention_policy],
            ['Max manuales', policy.max_manual_backups],
            ['Límite',      `${policy.max_backup_storage_mb} MB`],
          ].map(([k, v]) => (
            <div key={k} className="bg-zinc-800/50 rounded-lg px-3 py-2">
              <p className="text-zinc-500">{k}</p>
              <p className="text-zinc-200 font-medium mt-0.5">{v}</p>
            </div>
          ))}
        </div>
      )}

      {/* tabs */}
      <div className="flex border-b border-zinc-800 gap-0">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setSection(id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-px ${
              section === id
                ? 'border-indigo-500 text-indigo-400'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            }`}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      {/* tab content */}
      {section === 'policy' && policy && (
        <PolicyForm policy={policy} onSave={handleSave} saving={saving} />
      )}
      {section === 'backups' && (
        <BackupListTab hostingId={hostingId} />
      )}
      {section === 'history' && (
        <HistoryTable hostingId={hostingId} onRevert={() => { load(); setSection('policy'); }} />
      )}
      {section === 'cleanup' && (
        <CleanupPanel hostingId={hostingId} />
      )}
    </div>
  );
}
