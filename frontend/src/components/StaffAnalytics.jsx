/**
 * StaffAnalytics — Panel analytics del equipo + auditoría profesional de sesiones.
 * Tabs: Productividad | Sesiones de soporte
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Users, Activity, Clock, Shield, FileText, RotateCcw,
  RefreshCw, TrendingUp, AlertCircle, ChevronDown, ChevronUp,
  CheckCircle2, X, Info, ArrowUpRight, Minus, Eye,
  List, Terminal, Zap, Monitor, Globe, Hash, MessageSquare,
  Download, ExternalLink, Search,
} from 'lucide-react';
import { getStaffAnalytics, getStaffActivity, getSupportSessions, getSessionDetail } from '../services/api';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtDuration(s) {
  if (s == null) return '—';
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}
function timeAgo(iso) {
  if (!iso) return '—';
  const m = Math.floor((Date.now() - new Date(iso)) / 60000);
  if (m < 1) return 'ahora';
  if (m < 60) return `hace ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `hace ${h}h`;
  return `hace ${Math.floor(h / 24)}d`;
}
function fmtDateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-AR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}
function fmtTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

const ROLE_LABEL = { support: 'Soporte', billing: 'Billing', readonly: 'Solo lectura', admin: 'Admin' };
const ROLE_COLOR = {
  support: 'bg-amber-500/15 text-amber-400', billing: 'bg-blue-500/15 text-blue-400',
  readonly: 'bg-white/5 text-gray-500', admin: 'bg-emerald-500/15 text-emerald-400',
};
const ORIGIN_LABEL = {
  manual: 'Iniciativa del equipo', client_request: 'Cliente solicitó soporte',
  ai_advisory: 'Alerta IA / Advisory', scheduled: 'Mantenimiento programado',
};
const ORIGIN_COLOR = {
  manual: 'text-gray-400', client_request: 'text-amber-400',
  ai_advisory: 'text-purple-400', scheduled: 'text-blue-400',
};
const ORIGIN_BG = {
  manual: 'bg-gray-500/10 border-gray-500/20',
  client_request: 'bg-amber-500/10 border-amber-500/20',
  ai_advisory: 'bg-purple-500/10 border-purple-500/20',
  scheduled: 'bg-blue-500/10 border-blue-500/20',
};
const RESULT_CONFIG = {
  resolved:   { label: 'Resuelto',        color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/30', icon: CheckCircle2 },
  unresolved: { label: 'No resuelto',     color: 'text-red-400',     bg: 'bg-red-500/10 border-red-500/30',         icon: AlertCircle },
  escalated:  { label: 'Escalado',        color: 'text-amber-400',   bg: 'bg-amber-500/10 border-amber-500/30',     icon: ArrowUpRight },
  ongoing:    { label: 'En seguimiento',  color: 'text-blue-400',    bg: 'bg-blue-500/10 border-blue-500/30',       icon: Minus },
};
const RESULT_NONE = { label: 'Sin resultado', color: 'text-gray-600', bg: 'bg-white/5 border-white/10', icon: Clock };

const ACTION_LABELS = {
  support_session_start: 'Sesión iniciada', support_session_end: 'Sesión cerrada',
  file_edited: 'Archivo editado', hosting_restarted: 'Hosting reiniciado',
  hosting_stopped: 'Hosting detenido', hosting_started: 'Hosting iniciado',
  logs_viewed: 'Logs vistos', hosting_viewed: 'Hosting visto',
  issue_resolved: 'Incidencia resuelta', zip_uploaded: 'ZIP subido',
  deploy_executed: 'Deploy ejecutado', file_deleted: 'Archivo eliminado',
};
const ACTION_COLOR = {
  support_session_start: 'text-amber-400 bg-amber-500/10',
  support_session_end:   'text-emerald-400 bg-emerald-500/10',
  file_edited:           'text-blue-400 bg-blue-500/10',
  hosting_restarted:     'text-orange-400 bg-orange-500/10',
  deploy_executed:       'text-purple-400 bg-purple-500/10',
  logs_viewed:           'text-cyan-400 bg-cyan-500/10',
  issue_resolved:        'text-emerald-400 bg-emerald-500/10',
  zip_uploaded:          'text-blue-400 bg-blue-500/10',
  file_deleted:          'text-red-400 bg-red-500/10',
};
const ACTION_DOT = {
  support_session_start: 'bg-amber-400', support_session_end: 'bg-emerald-400',
  file_edited: 'bg-blue-400', hosting_restarted: 'bg-orange-400',
  deploy_executed: 'bg-purple-400', issue_resolved: 'bg-emerald-400',
};

// ─── Shared UI blocks ─────────────────────────────────────────────────────────

function InfoCard({ label, value, sub, valueColor = 'text-white', mono = false, small = false, icon: Icon }) {
  return (
    <div className="bg-white/3 border border-white/5 rounded-xl px-4 py-3">
      <div className="flex items-center gap-1.5 mb-1">
        {Icon && <Icon className="w-3 h-3 text-gray-600" />}
        <div className="text-[9px] uppercase tracking-wider text-gray-600">{label}</div>
      </div>
      <div className={`${small ? 'text-[9px]' : 'text-[11px]'} font-medium ${valueColor} ${mono ? 'font-mono' : ''} break-all`}>
        {value || '—'}
      </div>
      {sub && <div className="text-[9px] text-gray-600 mt-0.5 truncate">{sub}</div>}
    </div>
  );
}

function StatBadge({ value, label, color = 'text-white' }) {
  return (
    <div className="text-center">
      <div className={`text-xl font-bold font-mono ${color}`}>{value}</div>
      <div className="text-[9px] text-gray-600 mt-0.5">{label}</div>
    </div>
  );
}

function SectionTitle({ children }) {
  return <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-3 font-bold">{children}</div>;
}

// ─── Session Detail Modal (8 sections) ────────────────────────────────────────

function SessionDetailModal({ sessionId, onClose }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab]         = useState('timeline');
  const [search, setSearch]   = useState('');

  useEffect(() => {
    getSessionDetail(sessionId)
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [sessionId]);

  const session    = data?.session    || {};
  const activities = data?.activities || [];
  const duration   = data?.duration_seconds;
  const result     = RESULT_CONFIG[session.result] || RESULT_NONE;
  const ResultIcon = result.icon;

  const filteredActivities = search
    ? activities.filter(a =>
        (ACTION_LABELS[a.action_type] || a.action_type).toLowerCase().includes(search.toLowerCase()) ||
        (a.description || '').toLowerCase().includes(search.toLowerCase()))
    : activities;

  // Derived stats
  const filesEdited   = activities.filter(a => a.action_type === 'file_edited').length;
  const restarts      = activities.filter(a => a.action_type === 'hosting_restarted').length;
  const deploys       = activities.filter(a => a.action_type === 'deploy_executed').length;
  const logsViewed    = activities.filter(a => a.action_type === 'logs_viewed').length;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-[#0a0a0a] border border-white/10 rounded-2xl w-full max-w-4xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/5 shrink-0 bg-white/[0.02]">
          <div className={`w-9 h-9 rounded-full flex items-center justify-center border ${result.bg}`}>
            <ResultIcon className={`w-4 h-4 ${result.color}`} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-bold text-white">
              {session.target_email || '—'}
            </div>
            <div className="text-[9px] text-gray-600 font-mono mt-0.5">{sessionId}</div>
          </div>

          {/* Quick stats */}
          <div className="hidden md:flex items-center gap-4 px-4 border-l border-white/5">
            <StatBadge value={activities.length} label="acciones" color="text-white" />
            <StatBadge value={filesEdited} label="archivos" color="text-blue-400" />
            <StatBadge value={restarts} label="reinicios" color="text-orange-400" />
            <StatBadge value={duration != null ? fmtDuration(duration) : '—'} label="duración" color="text-amber-400" />
          </div>

          {session.result && (
            <span className={`hidden sm:flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold border ${result.bg} ${result.color}`}>
              <ResultIcon className="w-3 h-3" />{result.label}
            </span>
          )}
          <button onClick={onClose} className="text-gray-600 hover:text-white transition-colors ml-1">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* ── Tabs ───────────────────────────────────────────────────────── */}
        <div className="flex border-b border-white/5 shrink-0 overflow-x-auto">
          {[
            { id: 'timeline', label: 'Timeline',  icon: List },
            { id: 'context',  label: 'Contexto',  icon: Info },
            { id: 'system',   label: 'Sistema',   icon: Monitor },
            { id: 'result',   label: 'Resultado', icon: CheckCircle2 },
            { id: 'identity', label: 'Identidad', icon: Shield },
          ].map(t => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-[10px] font-bold whitespace-nowrap transition-colors border-b-2 ${
                  tab === t.id ? 'border-amber-500 text-amber-400' : 'border-transparent text-gray-500 hover:text-gray-300'
                }`}
              >
                <Icon className="w-3 h-3" />{t.label}
              </button>
            );
          })}
        </div>

        {/* ── Body ───────────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <RefreshCw className="w-5 h-5 text-amber-500 animate-spin" />
            </div>
          ) : !data ? (
            <div className="p-8 text-center text-[11px] text-red-400">Error cargando detalle de sesión</div>
          ) : (
            <>
              {/* ════ TIMELINE ════════════════════════════════════════════ */}
              {tab === 'timeline' && (
                <div className="p-5">
                  {/* Search */}
                  <div className="flex items-center gap-2 mb-4">
                    <div className="relative flex-1">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-600" />
                      <input
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        placeholder="Filtrar actividades..."
                        className="w-full bg-white/5 border border-white/8 rounded-lg pl-8 pr-3 py-2 text-[11px] text-white placeholder-gray-600 outline-none focus:border-amber-500/40"
                      />
                    </div>
                    <div className="text-[10px] text-gray-600">{filteredActivities.length} eventos</div>
                  </div>

                  {/* Summary row */}
                  <div className="grid grid-cols-4 gap-2 mb-4">
                    {[
                      { v: activities.length, l: 'Acciones', c: 'text-white' },
                      { v: filesEdited,        l: 'Archivos',  c: 'text-blue-400' },
                      { v: restarts,           l: 'Reinicios', c: 'text-orange-400' },
                      { v: deploys,            l: 'Deploys',   c: 'text-purple-400' },
                    ].map(s => (
                      <div key={s.l} className="bg-white/3 border border-white/5 rounded-xl p-3 text-center">
                        <div className={`text-lg font-bold font-mono ${s.c}`}>{s.v}</div>
                        <div className="text-[9px] text-gray-600 mt-0.5">{s.l}</div>
                      </div>
                    ))}
                  </div>

                  {filteredActivities.length === 0 ? (
                    <div className="text-center py-10 text-[11px] text-gray-600 italic">
                      {search ? 'Sin resultados para ese filtro' : 'Sin actividad registrada en esta sesión'}
                    </div>
                  ) : (
                    <div className="space-y-0 relative">
                      {filteredActivities.map((a, i) => {
                        const isLast = i === filteredActivities.length - 1;
                        const chipStyle = ACTION_COLOR[a.action_type] || 'text-gray-400 bg-white/5';
                        const dotColor  = ACTION_DOT[a.action_type]   || 'bg-white/20';
                        return (
                          <div key={a.log_id || i} className="flex gap-3 group">
                            <div className="flex flex-col items-center pt-1">
                              <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${dotColor} ring-1 ring-black`} />
                              {!isLast && <div className="w-px flex-1 bg-white/5 my-1" />}
                            </div>
                            <div className="pb-3 flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${chipStyle}`}>
                                  {ACTION_LABELS[a.action_type] || a.action_type}
                                </span>
                                <span className="text-[9px] text-gray-600 font-mono">{fmtTime(a.created_at)}</span>
                                {a.duration_seconds != null && (
                                  <span className="text-[9px] text-gray-700 font-mono ml-auto">{fmtDuration(a.duration_seconds)}</span>
                                )}
                              </div>
                              {a.description && (
                                <div className="text-[10px] text-gray-500 mt-0.5 leading-relaxed">{a.description}</div>
                              )}
                              {a.target_email && (
                                <div className="text-[9px] text-gray-700 mt-0.5 font-mono">→ {a.target_email}</div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* ════ CONTEXT ═════════════════════════════════════════════ */}
              {tab === 'context' && (
                <div className="p-5 space-y-5">
                  {/* Issue box */}
                  {session.issue_description ? (
                    <div className={`p-4 rounded-xl border ${ORIGIN_BG[session.origin] || 'bg-amber-500/5 border-amber-500/20'}`}>
                      <div className="text-[9px] uppercase tracking-wider text-amber-600 mb-1.5">Motivo reportado</div>
                      <div className="text-[13px] text-white font-medium leading-relaxed">{session.issue_description}</div>
                      <div className="mt-2 flex items-center gap-2">
                        <span className={`text-[9px] font-bold ${ORIGIN_COLOR[session.origin] || 'text-gray-500'}`}>
                          {ORIGIN_LABEL[session.origin] || session.origin}
                        </span>
                        <span className="text-[9px] text-gray-600">·</span>
                        <span className="text-[9px] text-gray-600">
                          {session.session_type === 'write' ? 'Sesión con escritura' : 'Solo lectura'}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-white/3 border border-white/5 rounded-xl p-4 text-center text-[10px] text-gray-600 italic">
                      Sin motivo registrado
                    </div>
                  )}

                  <div>
                    <SectionTitle>¿Quién y cuándo?</SectionTitle>
                    <div className="grid grid-cols-2 gap-2">
                      <InfoCard icon={Users} label="Operador" value={session.initiator_name} sub={session.initiator_email} />
                      <InfoCard icon={Shield} label="Rol del operador" value={ROLE_LABEL[session.initiator_role] || session.initiator_role} valueColor={ROLE_COLOR[session.initiator_role]?.split(' ')[1] || 'text-gray-400'} />
                      <InfoCard icon={Users} label="Cliente" value={session.target_email} sub={`Plan: ${session.target_plan || 'free'}`} />
                      <InfoCard icon={Hash} label="ID de sesión" value={sessionId.slice(0, 18) + '…'} mono small />
                    </div>
                  </div>

                  <div>
                    <SectionTitle>Timing</SectionTitle>
                    <div className="grid grid-cols-3 gap-2">
                      <InfoCard icon={Clock} label="Inicio" value={fmtDateTime(session.created_at)} />
                      <InfoCard icon={Clock} label="Fin" value={session.ended_at ? fmtDateTime(session.ended_at) : 'Activa'} />
                      <InfoCard icon={Clock} label="Duración" value={duration != null ? fmtDuration(duration) : '—'} valueColor="text-amber-400" />
                    </div>
                  </div>
                </div>
              )}

              {/* ════ SYSTEM ══════════════════════════════════════════════ */}
              {tab === 'system' && (
                <div className="p-5 space-y-4">
                  <SectionTitle>Estado del sistema durante la sesión</SectionTitle>

                  {/* Activity breakdown */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {[
                      { v: filesEdited, l: 'Archivos editados', c: 'text-blue-400', icon: FileText },
                      { v: restarts,    l: 'Reinicios',         c: 'text-orange-400', icon: RotateCcw },
                      { v: deploys,     l: 'Deploys',           c: 'text-purple-400', icon: Zap },
                      { v: logsViewed,  l: 'Logs vistos',       c: 'text-cyan-400', icon: Terminal },
                    ].map(s => {
                      const Icon = s.icon;
                      return (
                        <div key={s.l} className="bg-white/3 border border-white/5 rounded-xl p-4 flex flex-col gap-2">
                          <Icon className={`w-4 h-4 ${s.c}`} />
                          <div className={`text-2xl font-bold font-mono ${s.c}`}>{s.v}</div>
                          <div className="text-[9px] text-gray-600">{s.l}</div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Files touched */}
                  {activities.filter(a => a.action_type === 'file_edited').length > 0 && (
                    <div>
                      <SectionTitle>Archivos modificados</SectionTitle>
                      <div className="bg-[#111] border border-white/5 rounded-xl overflow-hidden">
                        {activities.filter(a => a.action_type === 'file_edited').map((a, i) => (
                          <div key={i} className="flex items-center gap-3 px-4 py-2.5 border-b border-white/5 last:border-0">
                            <FileText className="w-3 h-3 text-blue-400 shrink-0" />
                            <span className="text-[10px] text-gray-300 font-mono flex-1 truncate">{a.description}</span>
                            <span className="text-[9px] text-gray-600 font-mono shrink-0">{fmtTime(a.created_at)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Timeline of technical events */}
                  {restarts > 0 && (
                    <div>
                      <SectionTitle>Eventos de infraestructura</SectionTitle>
                      <div className="space-y-1">
                        {activities
                          .filter(a => ['hosting_restarted','hosting_stopped','hosting_started','deploy_executed'].includes(a.action_type))
                          .map((a, i) => (
                          <div key={i} className="flex items-center gap-3 bg-white/2 rounded-lg px-3 py-2">
                            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${ACTION_COLOR[a.action_type] || 'text-gray-400 bg-white/5'}`}>
                              {ACTION_LABELS[a.action_type]}
                            </span>
                            <span className="text-[9px] text-gray-500 truncate flex-1">{a.description}</span>
                            <span className="text-[9px] text-gray-700 font-mono">{fmtTime(a.created_at)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {activities.length === 0 && (
                    <div className="text-center py-8 text-[11px] text-gray-600 italic">Sin actividad registrada</div>
                  )}
                </div>
              )}

              {/* ════ RESULT ══════════════════════════════════════════════ */}
              {tab === 'result' && (
                <div className="p-5 space-y-4">
                  {session.result ? (
                    <>
                      <div className={`flex items-center gap-3 p-4 rounded-xl border ${result.bg}`}>
                        <ResultIcon className={`w-6 h-6 ${result.color} shrink-0`} />
                        <div>
                          <div className={`text-[14px] font-bold ${result.color}`}>{result.label}</div>
                          <div className="text-[10px] text-gray-500 mt-0.5">
                            {session.ended_at ? `Cerrada ${fmtDateTime(session.ended_at)}` : 'En curso'}
                          </div>
                        </div>
                        {duration != null && (
                          <div className="ml-auto text-right">
                            <div className="text-[18px] font-bold font-mono text-amber-400">{fmtDuration(duration)}</div>
                            <div className="text-[9px] text-gray-600">duración total</div>
                          </div>
                        )}
                      </div>

                      {session.action_taken && (
                        <div>
                          <SectionTitle>Acción realizada</SectionTitle>
                          <div className="bg-white/3 border border-white/5 rounded-xl px-4 py-3 text-[11px] text-gray-200 leading-relaxed">
                            {session.action_taken}
                          </div>
                        </div>
                      )}

                      {session.resolution_notes && (
                        <div>
                          <SectionTitle>Notas del operador</SectionTitle>
                          <div className="bg-white/3 border border-white/5 rounded-xl px-4 py-3 text-[11px] text-gray-200 leading-relaxed whitespace-pre-wrap">
                            {session.resolution_notes}
                          </div>
                        </div>
                      )}

                      <div className="grid grid-cols-3 gap-2">
                        <InfoCard icon={Activity} label="Acciones realizadas" value={`${activities.length} acciones`} />
                        <InfoCard icon={FileText} label="Archivos modificados" value={`${filesEdited} archivos`} valueColor="text-blue-400" />
                        <InfoCard icon={Clock} label="Tiempo en sesión" value={duration != null ? fmtDuration(duration) : '—'} valueColor="text-amber-400" />
                      </div>
                    </>
                  ) : (
                    <div className="text-center py-12 space-y-3">
                      <Clock className="w-10 h-10 text-gray-700 mx-auto" />
                      <div className="text-[12px] text-gray-500 font-medium">Sin resultado registrado</div>
                      <div className="text-[10px] text-gray-700">El operador no cerró la sesión explícitamente</div>
                    </div>
                  )}
                </div>
              )}

              {/* ════ IDENTITY ════════════════════════════════════════════ */}
              {tab === 'identity' && (
                <div className="p-5 space-y-5">
                  <SectionTitle>Identidad completa del operador</SectionTitle>
                  <div className="grid grid-cols-2 gap-2">
                    <InfoCard icon={Users} label="Nombre completo" value={session.initiator_name} />
                    <InfoCard icon={Users} label="Email del operador" value={session.initiator_email} mono small />
                    <InfoCard icon={Shield} label="Rol" value={ROLE_LABEL[session.initiator_role] || session.initiator_role} />
                    <InfoCard icon={Globe} label="IP del operador" value={session.ip_address} mono />
                  </div>

                  {session.staff_agent && (
                    <div>
                      <SectionTitle>User Agent del navegador</SectionTitle>
                      <div className="bg-white/3 border border-white/5 rounded-xl px-4 py-3 text-[9px] text-gray-400 font-mono leading-relaxed break-all">
                        {session.staff_agent}
                      </div>
                    </div>
                  )}

                  <div>
                    <SectionTitle>Trazabilidad de sesión</SectionTitle>
                    <div className="grid grid-cols-2 gap-2">
                      <InfoCard icon={Hash} label="Session ID" value={sessionId} mono small />
                      <InfoCard icon={Clock} label="Tipo de sesión" value={session.session_type === 'write' ? 'Lectura + Escritura' : 'Solo lectura'} />
                      <InfoCard icon={Info} label="Iniciado por" value={session.initiated_by === 'staff' ? 'Colaborador' : 'Administrador'} />
                      <InfoCard icon={Clock} label="Origen" value={ORIGIN_LABEL[session.origin] || session.origin} valueColor={ORIGIN_COLOR[session.origin] || 'text-gray-400'} />
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Sessions Tab ─────────────────────────────────────────────────────────────

function SessionsTab() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail]   = useState(null);
  const [filter, setFilter]   = useState('all');
  const [search, setSearch]   = useState('');

  const load = useCallback(() => {
    setLoading(true);
    getSupportSessions()
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const sessions = data?.history || [];
  const summary  = data?.summary  || {};

  const filtered = sessions.filter(s => {
    const matchFilter =
      filter === 'resolved'   ? s.result === 'resolved' :
      filter === 'unresolved' ? ['unresolved','escalated'].includes(s.result) :
      filter === 'active'     ? !s.ended_at && !s.revoked_at :
      true;
    const matchSearch = !search ||
      (s.target_email || '').toLowerCase().includes(search.toLowerCase()) ||
      (s.initiator_name || '').toLowerCase().includes(search.toLowerCase()) ||
      (s.issue_description || '').toLowerCase().includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  return (
    <>
      {detail && <SessionDetailModal sessionId={detail} onClose={() => setDetail(null)} />}

      <div className="space-y-4">
        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Sesiones (30d)', value: summary.total     ?? '—', color: 'text-white'        },
            { label: 'Resueltas',      value: summary.resolved   ?? '—', color: 'text-emerald-400'  },
            { label: 'Sin resolver',   value: summary.unresolved ?? '—', color: 'text-red-400'      },
            { label: 'Duración media', value: summary.avg_duration_seconds != null
                ? fmtDuration(Math.round(summary.avg_duration_seconds)) : '—', color: 'text-amber-400' },
          ].map(c => (
            <div key={c.label} className="bg-[#111] rounded-xl border border-white/5 p-4">
              <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-1.5">{c.label}</div>
              <div className={`text-2xl font-bold font-mono ${c.color}`}>{c.value}</div>
            </div>
          ))}
        </div>

        {/* Filters + search */}
        <div className="flex items-center gap-2 flex-wrap">
          {[
            { id: 'all', label: 'Todas' }, { id: 'active', label: 'Activas' },
            { id: 'resolved', label: 'Resueltas' }, { id: 'unresolved', label: 'Sin resolver' },
          ].map(f => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition-colors ${
                filter === f.id ? 'bg-amber-500/20 text-amber-400' : 'bg-white/5 text-gray-500 hover:text-white'
              }`}
            >{f.label}</button>
          ))}
          <div className="relative ml-auto">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-600" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Buscar cliente, operador, motivo…"
              className="bg-white/5 border border-white/8 rounded-lg pl-7 pr-3 py-1.5 text-[10px] text-white placeholder-gray-600 outline-none focus:border-amber-500/40 w-56"
            />
          </div>
          <button onClick={load} title="Actualizar" className="p-1.5 rounded-lg bg-white/5 text-gray-500 hover:text-white transition-colors">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <span className="text-[10px] text-gray-600">{filtered.length} sesiones</span>
        </div>

        {/* Table */}
        <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="w-5 h-5 text-amber-500 animate-spin" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-[11px] text-gray-600 italic">Sin sesiones</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="border-b border-white/5">
                    {['Cliente','Operador','Motivo','Origen','Resultado','Duración','Fecha',''].map(h => (
                      <th key={h} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-600 font-medium whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(s => {
                    const res = RESULT_CONFIG[s.result] || RESULT_NONE;
                    const ResIcon = res.icon;
                    let dur = null;
                    if (s.ended_at && s.created_at) {
                      try { dur = Math.round((new Date(s.ended_at) - new Date(s.created_at)) / 1000); } catch {}
                    }
                    const isActive = !s.ended_at && !s.revoked_at;
                    return (
                      <tr key={s.session_id} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                        <td className="px-4 py-3">
                          <div className="text-white font-medium">{s.target_email || '—'}</div>
                          {isActive && <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block mr-1 animate-pulse" />}
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-gray-300">{s.initiator_name || '—'}</div>
                          <span className={`px-1 py-0.5 rounded text-[8px] font-bold ${ROLE_COLOR[s.initiator_role] || 'bg-white/5 text-gray-500'}`}>
                            {ROLE_LABEL[s.initiator_role] || s.initiator_role}
                          </span>
                        </td>
                        <td className="px-4 py-3 max-w-[150px]">
                          <div className="text-gray-400 truncate" title={s.issue_description}>
                            {s.issue_description || <span className="text-gray-700 italic">Sin motivo</span>}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-[10px] font-medium ${ORIGIN_COLOR[s.origin] || 'text-gray-600'}`}>
                            {ORIGIN_LABEL[s.origin] || s.origin || '—'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-bold w-fit border ${res.bg} ${res.color}`}>
                            <ResIcon className="w-2.5 h-2.5" />{res.label}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-gray-500">{dur != null ? fmtDuration(dur) : '—'}</td>
                        <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{fmtDateTime(s.created_at)}</td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => setDetail(s.session_id)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-bold bg-white/5 text-gray-400 hover:bg-amber-500/15 hover:text-amber-400 transition-colors"
                          >
                            <Eye className="w-3 h-3" />Ver
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

// ─── Productivity Tab ─────────────────────────────────────────────────────────

function HourlyBar({ hours = [] }) {
  if (!hours.length) return <div className="text-[10px] text-gray-700 italic">Sin datos</div>;
  const max = Math.max(...hours.map(h => h.events), 1);
  const map  = Object.fromEntries(hours.map(h => [h.hour, h.events]));
  return (
    <div className="flex gap-px items-end h-8">
      {Array.from({ length: 24 }, (_, i) => {
        const v = map[i] || 0, pct = Math.round((v / max) * 100);
        return (
          <div key={i} title={`${i}:00 — ${v} eventos`} className="flex-1 rounded-sm transition-all"
            style={{ height: `${Math.max(4, pct)}%`, background: pct > 60 ? '#f59e0b' : pct > 30 ? '#d97706aa' : '#ffffff15' }} />
        );
      })}
    </div>
  );
}

function StaffDetailRow({ staffId }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    getStaffActivity(staffId, 20)
      .then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [staffId]);
  return (
    <tr className="border-b border-white/5 bg-[#0d0d0d]">
      <td colSpan={10} className="px-6 py-4">
        {loading ? (
          <div className="flex items-center gap-2 text-gray-600 text-[11px]"><RefreshCw className="w-3 h-3 animate-spin" />Cargando...</div>
        ) : !data ? (
          <div className="text-[11px] text-red-400">Error cargando actividad</div>
        ) : (
          <div className="space-y-3">
            <div>
              <div className="text-[9px] uppercase tracking-wider text-gray-600 mb-1">Distribución horaria (últimos 7 días)</div>
              <HourlyBar hours={data.hourly_distribution} />
              <div className="flex justify-between text-[8px] text-gray-700 mt-0.5">
                <span>0h</span><span>6h</span><span>12h</span><span>18h</span><span>23h</span>
              </div>
            </div>
            {data.activity?.length > 0 && (
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {data.activity.slice(0, 10).map(a => (
                  <div key={a.log_id} className="flex items-center gap-3 text-[10px]">
                    <span className="text-gray-600 font-mono w-32 shrink-0">{fmtDateTime(a.created_at)}</span>
                    <span className={`${(ACTION_COLOR[a.action_type] || 'text-gray-400 bg-white/5').split(' ')[0]}`}>
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
        className={`border-b border-white/5 cursor-pointer transition-colors ${selected ? 'bg-amber-500/5' : 'hover:bg-white/[0.02]'}`}
        onClick={() => onSelect(selected ? null : member.staff_id)}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2.5">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold ${isActive ? 'bg-amber-500/15 text-amber-400' : 'bg-white/5 text-gray-600'}`}>
              {member.full_name?.[0]?.toUpperCase() || '?'}
            </div>
            <div>
              <div className={`text-[11px] font-medium ${isActive ? 'text-white' : 'text-gray-600'}`}>{member.full_name}</div>
              <div className="text-[10px] text-gray-600">{member.email}</div>
            </div>
          </div>
        </td>
        <td className="px-4 py-3">
          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${ROLE_COLOR[member.role] || 'bg-white/5 text-gray-500'}`}>
            {ROLE_LABEL[member.role] || member.role}
          </span>
          {!isActive && <span className="ml-1.5 px-1.5 py-0.5 rounded text-[9px] bg-red-500/10 text-red-500 font-bold uppercase">Inactivo</span>}
        </td>
        <td className="px-4 py-3 font-mono text-[12px] text-white font-bold">{member.total_actions}</td>
        <td className="px-4 py-3 font-mono text-[11px] text-amber-400">{member.clients_served}</td>
        <td className="px-4 py-3 font-mono text-[11px] text-emerald-400">{member.support_sessions}</td>
        <td className="px-4 py-3 font-mono text-[11px] text-blue-400">{member.files_edited}</td>
        <td className="px-4 py-3 font-mono text-[11px] text-orange-400">{member.restarts}</td>
        <td className="px-4 py-3 text-[10px] text-gray-500">{fmtDuration(member.total_seconds)}</td>
        <td className="px-4 py-3 text-[10px] text-gray-600">{timeAgo(member.last_activity_at)}</td>
        <td className="px-4 py-3">
          {selected ? <ChevronUp className="w-3.5 h-3.5 text-amber-400" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-600" />}
        </td>
      </tr>
      {selected && <StaffDetailRow staffId={member.staff_id} />}
    </>
  );
}

function TeamSummary({ members }) {
  const active        = members.filter(m => m.is_active);
  const totalActions  = members.reduce((s, m) => s + (m.total_actions   || 0), 0);
  const totalSessions = members.reduce((s, m) => s + (m.support_sessions || 0), 0);
  const totalResolved = members.reduce((s, m) => s + (m.issues_resolved  || 0), 0);
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {[
        { label: 'Colaboradores activos', value: active.length, sub: `de ${members.length} en total`, color: 'text-white' },
        { label: 'Acciones totales',      value: totalActions,  sub: 'en el período',                 color: 'text-amber-400' },
        { label: 'Sesiones de soporte',   value: totalSessions, color: 'text-purple-400' },
        { label: 'Incidencias resueltas', value: totalResolved, color: 'text-emerald-400' },
      ].map(c => (
        <div key={c.label} className="bg-[#111] rounded-xl border border-white/5 p-4">
          <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-1">{c.label}</div>
          <div className={`text-2xl font-bold font-mono ${c.color}`}>{c.value}</div>
          {c.sub && <div className="text-[10px] text-gray-600 mt-0.5">{c.sub}</div>}
        </div>
      ))}
    </div>
  );
}

function ProductivityTab({ days }) {
  const [data, setData]       = useState(null);
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
  const cols = ['Colaborador','Rol','Acciones','Clientes','Soporte','Archivos','Reinicios','Tiempo activo','Últ. actividad',''];

  return (
    <div className="space-y-4">
      {loading && !data ? (
        <div className="flex items-center justify-center py-12"><RefreshCw className="w-5 h-5 text-amber-500 animate-spin" /></div>
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
          <p className="text-[9px] text-gray-700 text-right">Haz clic en una fila para ver distribución horaria y actividad detallada</p>
        </>
      )}
    </div>
  );
}

// ─── Main Export ──────────────────────────────────────────────────────────────

export default function StaffAnalytics() {
  const [tab, setTab]   = useState('productivity');
  const [days, setDays] = useState(30);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <TrendingUp className="w-5 h-5 text-amber-400" />
        <div>
          <h2 className="text-sm font-bold text-white">Analytics del equipo</h2>
          <p className="text-[10px] text-gray-500">Productividad · Auditoría de soporte · Identidad</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {tab === 'productivity' && [7,14,30,90].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-colors ${days === d ? 'bg-amber-500/20 text-amber-400' : 'bg-white/5 text-gray-500 hover:text-white'}`}
            >{d}d</button>
          ))}
        </div>
      </div>

      <div className="flex border-b border-white/5">
        {[
          { id: 'productivity', label: 'Productividad',        icon: Activity },
          { id: 'sessions',     label: 'Sesiones de soporte',  icon: Shield  },
        ].map(t => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-[11px] font-bold transition-colors border-b-2 ${
                tab === t.id ? 'border-amber-500 text-amber-400' : 'border-transparent text-gray-500 hover:text-gray-300'
              }`}
            ><Icon className="w-3.5 h-3.5" />{t.label}</button>
          );
        })}
      </div>

      {tab === 'productivity' && <ProductivityTab days={days} setDays={setDays} />}
      {tab === 'sessions'     && <SessionsTab />}
    </div>
  );
}
