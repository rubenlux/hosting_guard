/**
 * StaffAnalytics — Panel analytics del equipo + auditoría de sesiones de soporte.
 *
 * Tabs:
 *   Productividad — métricas por colaborador (existente, mejorado)
 *   Sesiones      — auditoría completa de todas las sesiones de soporte
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Users, Activity, Clock, Shield, FileText, RotateCcw,
  RefreshCw, TrendingUp, AlertCircle, ChevronDown, ChevronUp,
  Terminal, CheckCircle2, X, Info, Zap, ArrowUpRight,
  Minus, Eye, MessageSquare, List,
} from 'lucide-react';
import { getStaffAnalytics, getStaffActivity, getSupportSessions, getSessionDetail } from '../services/api';

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function fmtDuration(seconds) {
  if (!seconds && seconds !== 0) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function timeAgo(iso) {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'ahora';
  if (m < 60) return `hace ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `hace ${h}h`;
  return `hace ${Math.floor(h / 24)}d`;
}

function fmtDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-AR', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

const ROLE_LABEL = { support: 'Soporte', billing: 'Billing', readonly: 'Solo lectura', admin: 'Admin' };
const ROLE_COLOR = {
  support:  'bg-amber-500/15 text-amber-400',
  billing:  'bg-blue-500/15 text-blue-400',
  readonly: 'bg-white/5 text-gray-500',
  admin:    'bg-emerald-500/15 text-emerald-400',
};

const ORIGIN_LABEL = {
  manual:         'Iniciativa del equipo',
  client_request: 'Cliente solicitó soporte',
  ai_advisory:    'Alerta IA / Advisory',
  scheduled:      'Mantenimiento programado',
};
const ORIGIN_COLOR = {
  manual:         'text-gray-400',
  client_request: 'text-amber-400',
  ai_advisory:    'text-purple-400',
  scheduled:      'text-blue-400',
};

const RESULT_CONFIG = {
  resolved:   { label: 'Resuelto',      color: 'text-emerald-400 bg-emerald-500/10', icon: CheckCircle2 },
  unresolved: { label: 'No resuelto',   color: 'text-red-400 bg-red-500/10',         icon: AlertCircle },
  escalated:  { label: 'Escalado',      color: 'text-amber-400 bg-amber-500/10',     icon: ArrowUpRight },
  ongoing:    { label: 'En seguimiento',color: 'text-blue-400 bg-blue-500/10',       icon: Minus },
  null:       { label: 'Sin resultado', color: 'text-gray-600 bg-white/5',           icon: Clock },
};

const ACTION_LABELS = {
  support_session_start: 'Sesión iniciada',
  support_session_end:   'Sesión cerrada',
  file_edited:           'Archivo editado',
  hosting_restarted:     'Hosting reiniciado',
  hosting_stopped:       'Hosting detenido',
  hosting_started:       'Hosting iniciado',
  logs_viewed:           'Logs vistos',
  hosting_viewed:        'Hosting visto',
  issue_resolved:        'Incidencia resuelta',
  zip_uploaded:          'ZIP subido',
  deploy_executed:       'Deploy ejecutado',
};

const ACTION_COLOR = {
  support_session_start: 'text-amber-400',
  support_session_end:   'text-emerald-400',
  file_edited:           'text-blue-400',
  hosting_restarted:     'text-orange-400',
  logs_viewed:           'text-purple-400',
  issue_resolved:        'text-emerald-400',
  zip_uploaded:          'text-blue-400',
};

// ─────────────────────────────────────────────────────────────────────────────
// Session Detail Modal
// ─────────────────────────────────────────────────────────────────────────────

function SessionDetailModal({ sessionId, onClose }) {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab]       = useState('timeline');

  useEffect(() => {
    getSessionDetail(sessionId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const session    = data?.session || {};
  const activities = data?.activities || [];
  const duration   = data?.duration_seconds;
  const result     = RESULT_CONFIG[session.result] || RESULT_CONFIG['null'];
  const ResultIcon = result.icon;

  return (
    <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-[#0d0d0d] border border-white/10 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/5 shrink-0">
          <div className="w-8 h-8 rounded-full bg-amber-500/15 flex items-center justify-center">
            <Shield className="w-4 h-4 text-amber-400" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-bold text-white truncate">
              Sesión: {session.target_email || '—'}
            </div>
            <div className="text-[10px] text-gray-500 font-mono">{sessionId}</div>
          </div>
          {session.result && (
            <span className={`flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-bold ${result.color}`}>
              <ResultIcon className="w-3 h-3" /> {result.label}
            </span>
          )}
          <button onClick={onClose} className="text-gray-600 hover:text-white text-lg leading-none ml-2">×</button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-white/5 shrink-0">
          {[
            { id: 'timeline', label: 'Timeline', icon: List },
            { id: 'context',  label: 'Contexto', icon: Info },
            { id: 'result',   label: 'Resultado', icon: CheckCircle2 },
          ].map(t => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-[11px] font-bold transition-colors border-b-2 ${
                  tab === t.id
                    ? 'border-amber-500 text-amber-400'
                    : 'border-transparent text-gray-500 hover:text-gray-300'
                }`}
              >
                <Icon className="w-3.5 h-3.5" /> {t.label}
              </button>
            );
          })}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="w-5 h-5 text-gray-600 animate-spin" />
            </div>
          ) : !data ? (
            <div className="p-6 text-center text-[11px] text-red-400">Error cargando detalle</div>
          ) : (
            <>
              {/* ── CONTEXT tab ─────────────────────────────────────── */}
              {tab === 'context' && (
                <div className="p-5 space-y-4">
                  {/* Who / when */}
                  <div className="grid grid-cols-2 gap-3">
                    <InfoCard label="Iniciado por" value={session.initiator_name || '—'} sub={session.initiator_email} />
                    <InfoCard label="Rol del iniciador" value={ROLE_LABEL[session.initiator_role] || session.initiator_role || '—'} />
                    <InfoCard label="Cliente" value={session.target_email || '—'} sub={`Plan: ${session.target_plan || 'free'}`} />
                    <InfoCard label="Origen" value={ORIGIN_LABEL[session.origin] || session.origin || '—'} valueColor={ORIGIN_COLOR[session.origin]} />
                  </div>

                  {/* Issue */}
                  {session.issue_description && (
                    <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-4">
                      <div className="text-[9px] uppercase tracking-wider text-amber-600 mb-1">Motivo reportado</div>
                      <div className="text-[12px] text-amber-100">{session.issue_description}</div>
                    </div>
                  )}

                  {/* Timing */}
                  <div className="grid grid-cols-3 gap-3">
                    <InfoCard label="Inicio" value={fmtDateTime(session.created_at)} />
                    <InfoCard label="Fin" value={session.ended_at ? fmtDateTime(session.ended_at) : '—'} />
                    <InfoCard label="Duración" value={duration != null ? fmtDuration(duration) : '—'} valueColor="text-amber-400" />
                  </div>

                  {/* Technical */}
                  <div className="grid grid-cols-2 gap-3">
                    <InfoCard label="IP del operador" value={session.ip_address || '—'} mono />
                    <InfoCard label="Tipo de sesión" value={session.session_type === 'write' ? 'Lectura / Escritura' : 'Solo lectura'} />
                  </div>

                  {session.staff_agent && (
                    <InfoCard label="User Agent" value={session.staff_agent} mono small />
                  )}
                </div>
              )}

              {/* ── TIMELINE tab ────────────────────────────────────── */}
              {tab === 'timeline' && (
                <div className="p-5">
                  {activities.length === 0 ? (
                    <div className="text-center py-8 text-[11px] text-gray-600 italic">
                      Sin actividad registrada en esta sesión
                    </div>
                  ) : (
                    <div className="space-y-0">
                      {activities.map((a, i) => {
                        const isLast = i === activities.length - 1;
                        const color = ACTION_COLOR[a.action_type] || 'text-gray-500';
                        return (
                          <div key={a.log_id} className="flex gap-3">
                            {/* Timeline line */}
                            <div className="flex flex-col items-center">
                              <div className={`w-2 h-2 rounded-full mt-1 shrink-0 ${
                                a.action_type === 'support_session_start' ? 'bg-amber-400' :
                                a.action_type === 'support_session_end'   ? 'bg-emerald-400' :
                                'bg-white/20'
                              }`} />
                              {!isLast && <div className="w-px flex-1 bg-white/5 my-0.5" />}
                            </div>
                            {/* Content */}
                            <div className={`pb-3 flex-1 min-w-0 ${isLast ? '' : ''}`}>
                              <div className="flex items-baseline gap-2 flex-wrap">
                                <span className={`text-[11px] font-medium ${color}`}>
                                  {ACTION_LABELS[a.action_type] || a.action_type}
                                </span>
                                <span className="text-[9px] text-gray-600 font-mono">
                                  {fmtDateTime(a.created_at)}
                                </span>
                                {a.duration_seconds != null && (
                                  <span className="text-[9px] text-gray-700 font-mono ml-auto">
                                    {fmtDuration(a.duration_seconds)}
                                  </span>
                                )}
                              </div>
                              {a.description && (
                                <div className="text-[10px] text-gray-500 mt-0.5 truncate">
                                  {a.description}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Summary counts */}
                  <div className="mt-4 pt-4 border-t border-white/5 grid grid-cols-3 gap-3">
                    <MiniStat
                      label="Acciones"
                      value={activities.length}
                      color="text-white"
                    />
                    <MiniStat
                      label="Archivos editados"
                      value={activities.filter(a => a.action_type === 'file_edited').length}
                      color="text-blue-400"
                    />
                    <MiniStat
                      label="Reinicios"
                      value={activities.filter(a => a.action_type === 'hosting_restarted').length}
                      color="text-orange-400"
                    />
                  </div>
                </div>
              )}

              {/* ── RESULT tab ──────────────────────────────────────── */}
              {tab === 'result' && (
                <div className="p-5 space-y-4">
                  {session.result ? (
                    <>
                      <div className={`flex items-center gap-2 p-4 rounded-xl border ${
                        session.result === 'resolved'   ? 'bg-emerald-500/5 border-emerald-500/20' :
                        session.result === 'unresolved' ? 'bg-red-500/5 border-red-500/20' :
                        session.result === 'escalated'  ? 'bg-amber-500/5 border-amber-500/20' :
                        'bg-blue-500/5 border-blue-500/20'
                      }`}>
                        <ResultIcon className={`w-5 h-5 ${result.color.split(' ')[0]}`} />
                        <span className="text-[13px] font-bold text-white">{result.label}</span>
                      </div>

                      {session.action_taken && (
                        <div>
                          <div className="text-[9px] uppercase tracking-wider text-gray-500 mb-1.5">Acción realizada</div>
                          <div className="bg-white/3 border border-white/5 rounded-xl px-4 py-3 text-[11px] text-gray-200">
                            {session.action_taken}
                          </div>
                        </div>
                      )}

                      {session.resolution_notes && (
                        <div>
                          <div className="text-[9px] uppercase tracking-wider text-gray-500 mb-1.5">Notas del operador</div>
                          <div className="bg-white/3 border border-white/5 rounded-xl px-4 py-3 text-[11px] text-gray-200 leading-relaxed">
                            {session.resolution_notes}
                          </div>
                        </div>
                      )}

                      <div className="grid grid-cols-2 gap-3">
                        <InfoCard label="Duración total" value={duration != null ? fmtDuration(duration) : '—'} valueColor="text-amber-400" />
                        <InfoCard label="Acciones realizadas" value={`${activities.length} acciones`} />
                      </div>
                    </>
                  ) : (
                    <div className="text-center py-8 space-y-2">
                      <Clock className="w-8 h-8 text-gray-700 mx-auto" />
                      <div className="text-[11px] text-gray-600 italic">
                        Sesión sin resultado registrado
                      </div>
                      <div className="text-[10px] text-gray-700">
                        El operador no cerró la sesión explícitamente
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function InfoCard({ label, value, sub, valueColor = 'text-white', mono = false, small = false }) {
  return (
    <div className="bg-white/3 border border-white/5 rounded-xl px-4 py-3">
      <div className="text-[9px] uppercase tracking-wider text-gray-600 mb-1">{label}</div>
      <div className={`${small ? 'text-[9px]' : 'text-[11px]'} font-medium ${valueColor} ${mono ? 'font-mono' : ''} truncate`}>
        {value}
      </div>
      {sub && <div className="text-[9px] text-gray-600 mt-0.5 truncate">{sub}</div>}
    </div>
  );
}

function MiniStat({ label, value, color }) {
  return (
    <div className="text-center">
      <div className={`text-xl font-bold font-mono ${color}`}>{value}</div>
      <div className="text-[9px] text-gray-600 mt-0.5">{label}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sessions List Tab
// ─────────────────────────────────────────────────────────────────────────────

function SessionsTab() {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState(null);  // session_id of open modal
  const [filter, setFilter] = useState('all'); // all | resolved | unresolved | active

  useEffect(() => {
    getSupportSessions()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  const sessions = data?.history || [];
  const summary  = data?.summary || {};

  const filtered = sessions.filter(s => {
    if (filter === 'resolved')   return s.result === 'resolved';
    if (filter === 'unresolved') return s.result === 'unresolved' || s.result === 'escalated';
    if (filter === 'active')     return !s.ended_at && !s.revoked_at;
    return true;
  });

  return (
    <>
      {detail && <SessionDetailModal sessionId={detail} onClose={() => setDetail(null)} />}

      <div className="space-y-4">
        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Sesiones (30d)', value: summary.total ?? '—',      color: 'text-white' },
            { label: 'Resueltas',      value: summary.resolved ?? '—',   color: 'text-emerald-400' },
            { label: 'Sin resolver',   value: summary.unresolved ?? '—', color: 'text-red-400' },
            { label: 'Duración media', value: summary.avg_duration_seconds != null
                ? fmtDuration(Math.round(summary.avg_duration_seconds)) : '—', color: 'text-amber-400' },
          ].map(card => (
            <div key={card.label} className="bg-[#111] rounded-xl border border-white/5 p-4">
              <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-1">{card.label}</div>
              <div className={`text-2xl font-bold font-mono ${card.color}`}>{card.value}</div>
            </div>
          ))}
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-2">
          {[
            { id: 'all',        label: 'Todas' },
            { id: 'active',     label: 'Activas' },
            { id: 'resolved',   label: 'Resueltas' },
            { id: 'unresolved', label: 'Sin resolver' },
          ].map(f => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition-colors ${
                filter === f.id
                  ? 'bg-amber-500/20 text-amber-400'
                  : 'bg-white/5 text-gray-500 hover:text-white'
              }`}
            >
              {f.label}
            </button>
          ))}
          <span className="ml-auto text-[10px] text-gray-600">{filtered.length} sesiones</span>
        </div>

        {/* Table */}
        <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="w-5 h-5 text-gray-600 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-[11px] text-gray-600 italic">Sin sesiones</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="border-b border-white/5">
                    {['Cliente', 'Operador', 'Motivo', 'Origen', 'Resultado', 'Duración', 'Fecha', ''].map(h => (
                      <th key={h} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-600 font-medium whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(s => {
                    const res = RESULT_CONFIG[s.result] || RESULT_CONFIG['null'];
                    const ResIcon = res.icon;
                    let dur = null;
                    if (s.ended_at && s.created_at) {
                      try {
                        dur = Math.round((new Date(s.ended_at) - new Date(s.created_at)) / 1000);
                      } catch { /* ignore */ }
                    }
                    return (
                      <tr key={s.session_id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                        <td className="px-4 py-3">
                          <div className="text-white font-medium">{s.target_email || '—'}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-gray-400">{s.initiator_name || '—'}</div>
                          <div className="text-[9px] text-gray-600">
                            <span className={`px-1 py-0.5 rounded text-[8px] font-bold uppercase ${ROLE_COLOR[s.initiator_role] || 'bg-white/5 text-gray-500'}`}>
                              {ROLE_LABEL[s.initiator_role] || s.initiator_role}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3 max-w-[160px]">
                          <div className="text-gray-400 truncate" title={s.issue_description}>
                            {s.issue_description || <span className="text-gray-700 italic">Sin motivo</span>}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-[10px] ${ORIGIN_COLOR[s.origin] || 'text-gray-600'}`}>
                            {ORIGIN_LABEL[s.origin] || s.origin || '—'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold w-fit ${res.color}`}>
                            <ResIcon className="w-2.5 h-2.5" />{res.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-gray-500">
                          {dur != null ? fmtDuration(dur) : '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                          {fmtDateTime(s.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => setDetail(s.session_id)}
                            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-bold
                              bg-white/5 text-gray-400 hover:bg-amber-500/10 hover:text-amber-400 transition-colors"
                          >
                            <Eye className="w-3 h-3" /> Ver
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Productivity tab (existing, refactored)
// ─────────────────────────────────────────────────────────────────────────────

function HourlyBar({ hours = [] }) {
  if (hours.length === 0) return <div className="text-[10px] text-gray-700 italic">Sin datos</div>;
  const max = Math.max(...hours.map(h => h.events), 1);
  const map = Object.fromEntries(hours.map(h => [h.hour, h.events]));
  return (
    <div className="flex gap-px items-end h-8">
      {Array.from({ length: 24 }, (_, i) => {
        const v = map[i] || 0;
        const pct = Math.round((v / max) * 100);
        return (
          <div
            key={i}
            title={`${i}:00 — ${v} eventos`}
            className="flex-1 rounded-sm transition-all"
            style={{
              height: `${Math.max(4, pct)}%`,
              background: pct > 60 ? '#f59e0b' : pct > 30 ? '#d97706aa' : '#ffffff15',
            }}
          />
        );
      })}
    </div>
  );
}

function StaffDetailRow({ staffId }) {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStaffActivity(staffId, 20)
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [staffId]);

  return (
    <tr className="border-b border-white/5 bg-[#0d0d0d]">
      <td colSpan={10} className="px-6 py-4">
        {loading ? (
          <div className="flex items-center gap-2 text-gray-600 text-[11px]">
            <RefreshCw className="w-3 h-3 animate-spin" /> Cargando...
          </div>
        ) : !data ? (
          <div className="text-[11px] text-red-400">Error cargando actividad</div>
        ) : (
          <div className="space-y-3">
            <div>
              <div className="text-[9px] uppercase tracking-wider text-gray-600 mb-1">
                Distribución horaria (últimos 7 días)
              </div>
              <HourlyBar hours={data.hourly_distribution} />
              <div className="flex justify-between text-[8px] text-gray-700 mt-0.5">
                <span>0h</span><span>6h</span><span>12h</span><span>18h</span><span>23h</span>
              </div>
            </div>
            {data.activity?.length > 0 && (
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {data.activity.slice(0, 10).map(a => (
                  <div key={a.log_id} className="flex items-center gap-3 text-[10px]">
                    <span className="text-gray-600 font-mono w-32 shrink-0">
                      {fmtDateTime(a.created_at)}
                    </span>
                    <span className={`${ACTION_COLOR[a.action_type] || 'text-gray-400'}`}>
                      {ACTION_LABELS[a.action_type] || a.action_type}
                    </span>
                    {a.target_email && <span className="text-gray-600">→ {a.target_email}</span>}
                    {a.duration_seconds != null && (
                      <span className="text-gray-700 font-mono ml-auto">{fmtDuration(a.duration_seconds)}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </td>
    </tr>
  );
}

function StaffRow({ member, onSelect, selected }) {
  const isActive = member.is_active;
  return (
    <>
      <tr
        className={`border-b border-white/5 cursor-pointer transition-colors ${
          selected ? 'bg-amber-500/5' : 'hover:bg-white/[0.02]'
        }`}
        onClick={() => onSelect(selected ? null : member.staff_id)}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold ${
              isActive ? 'bg-amber-500/15 text-amber-400' : 'bg-white/5 text-gray-600'
            }`}>
              {member.full_name?.[0]?.toUpperCase() || '?'}
            </div>
            <div>
              <div className={`text-[11px] font-medium ${isActive ? 'text-white' : 'text-gray-600'}`}>
                {member.full_name}
              </div>
              <div className="text-[10px] text-gray-600">{member.email}</div>
            </div>
          </div>
        </td>
        <td className="px-4 py-3">
          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${ROLE_COLOR[member.role] || 'bg-white/5 text-gray-500'}`}>
            {ROLE_LABEL[member.role] || member.role}
          </span>
          {!isActive && (
            <span className="ml-1.5 px-1.5 py-0.5 rounded text-[9px] bg-red-500/10 text-red-500 font-bold uppercase">Inactivo</span>
          )}
        </td>
        <td className="px-4 py-3 font-mono text-[12px] text-white font-bold">{member.total_actions}</td>
        <td className="px-4 py-3 font-mono text-[11px] text-amber-400">{member.clients_served}</td>
        <td className="px-4 py-3 font-mono text-[11px] text-emerald-400">{member.support_sessions}</td>
        <td className="px-4 py-3 font-mono text-[11px] text-blue-400">{member.files_edited}</td>
        <td className="px-4 py-3 font-mono text-[11px] text-orange-400">{member.restarts}</td>
        <td className="px-4 py-3 text-[10px] text-gray-500">{fmtDuration(member.total_seconds)}</td>
        <td className="px-4 py-3 text-[10px] text-gray-600">{timeAgo(member.last_activity_at)}</td>
        <td className="px-4 py-3">
          {selected
            ? <ChevronUp className="w-3.5 h-3.5 text-amber-400" />
            : <ChevronDown className="w-3.5 h-3.5 text-gray-600" />}
        </td>
      </tr>
      {selected && <StaffDetailRow staffId={member.staff_id} />}
    </>
  );
}

function TeamSummary({ members }) {
  const active        = members.filter(m => m.is_active);
  const totalActions  = members.reduce((s, m) => s + (m.total_actions  || 0), 0);
  const totalSessions = members.reduce((s, m) => s + (m.support_sessions || 0), 0);
  const totalResolved = members.reduce((s, m) => s + (m.issues_resolved || 0), 0);
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {[
        { label: 'Colaboradores activos', value: active.length, sub: `de ${members.length} en total`, color: 'text-white' },
        { label: 'Acciones totales', value: totalActions, sub: 'en el período', color: 'text-amber-400' },
        { label: 'Sesiones de soporte', value: totalSessions, color: 'text-purple-400' },
        { label: 'Incidencias resueltas', value: totalResolved, color: 'text-emerald-400' },
      ].map(card => (
        <div key={card.label} className="bg-[#111] rounded-xl border border-white/5 p-4">
          <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-1">{card.label}</div>
          <div className={`text-2xl font-bold font-mono ${card.color}`}>{card.value}</div>
          {card.sub && <div className="text-[10px] text-gray-600 mt-0.5">{card.sub}</div>}
        </div>
      ))}
    </div>
  );
}

function ProductivityTab({ days, setDays }) {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await getStaffAnalytics(days); setData(r); }
    catch { setData(null); }
    finally { setLoading(false); }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  const members = data?.members || [];
  const cols = ['Colaborador', 'Rol', 'Acciones', 'Clientes', 'Soporte', 'Archivos', 'Reinicios', 'Tiempo activo', 'Últ. actividad', ''];

  return (
    <div className="space-y-4">
      {loading && !data ? (
        <div className="flex items-center justify-center py-12"><RefreshCw className="w-5 h-5 text-gray-600 animate-spin" /></div>
      ) : members.length === 0 ? (
        <div className="bg-[#111] rounded-xl border border-white/5 p-12 text-center">
          <Users className="w-8 h-8 text-gray-700 mx-auto mb-3" />
          <div className="text-[11px] text-gray-600 italic">Sin colaboradores.</div>
        </div>
      ) : (
        <>
          <TeamSummary members={members} />
          <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="border-b border-white/5">
                    {cols.map(c => (
                      <th key={c} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-600 font-medium whitespace-nowrap">{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {members.map(m => (
                    <StaffRow key={m.staff_id} member={m} selected={selected === m.staff_id} onSelect={setSelected} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <p className="text-[9px] text-gray-700 text-right">Haz clic en una fila para ver la distribución horaria y actividad detallada</p>
        </>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main export
// ─────────────────────────────────────────────────────────────────────────────

export default function StaffAnalytics() {
  const [tab, setTab] = useState('productivity');
  const [days, setDays] = useState(30);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <TrendingUp className="w-5 h-5 text-amber-400" />
        <div>
          <h2 className="text-sm font-bold text-white">Analytics del equipo</h2>
          <p className="text-[10px] text-gray-500">Productividad por colaborador</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {tab === 'productivity' && [7, 14, 30, 90].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-colors ${
                days === d ? 'bg-amber-500/20 text-amber-400' : 'bg-white/5 text-gray-500 hover:text-white'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex border-b border-white/5">
        {[
          { id: 'productivity', label: 'Productividad', icon: Activity },
          { id: 'sessions',     label: 'Sesiones de soporte', icon: Shield },
        ].map(t => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-[11px] font-bold transition-colors border-b-2 ${
                tab === t.id
                  ? 'border-amber-500 text-amber-400'
                  : 'border-transparent text-gray-500 hover:text-gray-300'
              }`}
            >
              <Icon className="w-3.5 h-3.5" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'productivity' && <ProductivityTab days={days} setDays={setDays} />}
      {tab === 'sessions'     && <SessionsTab />}
    </div>
  );
}
