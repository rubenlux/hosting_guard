/**
 * StaffAnalytics — componente para el panel admin.
 * Muestra métricas de productividad del equipo de colaboradores.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Users, Activity, Clock, Shield, FileText, RotateCcw,
  RefreshCw, TrendingUp, AlertCircle, ChevronDown, ChevronUp,
  Terminal, CheckCircle,
} from 'lucide-react';
import { getStaffAnalytics, getStaffActivity } from '../services/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDuration(seconds) {
  if (!seconds) return '0m';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
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

const ROLE_LABEL = { support: 'Soporte', billing: 'Billing', readonly: 'Solo lectura' };
const ROLE_COLOR = {
  support:  'bg-amber-500/15 text-amber-400',
  billing:  'bg-blue-500/15 text-blue-400',
  readonly: 'bg-white/5 text-gray-500',
};

const ACTION_LABELS = {
  support_session_start: 'Soporte remoto',
  file_edited:           'Archivos editados',
  hosting_restarted:     'Reinicios',
  issue_resolved:        'Resueltos',
  logs_viewed:           'Logs vistos',
  hosting_viewed:        'Hostings vistos',
};

// ---------------------------------------------------------------------------
// Hourly heatmap bar
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Staff row in the analytics table
// ---------------------------------------------------------------------------

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
            <span className="ml-1.5 px-1.5 py-0.5 rounded text-[9px] bg-red-500/10 text-red-500 font-bold uppercase">
              Inactivo
            </span>
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

      {/* Detail row — expanded activity */}
      {selected && <StaffDetailRow staffId={member.staff_id} />}
    </>
  );
}

function StaffDetailRow({ staffId }) {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStaffActivity(staffId, 20)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [staffId]);

  return (
    <tr className="border-b border-white/5 bg-[#0d0d0d]">
      <td colSpan={10} className="px-6 py-4">
        {loading ? (
          <div className="flex items-center gap-2 text-gray-600 text-[11px]">
            <RefreshCw className="w-3 h-3 animate-spin" /> Cargando actividad...
          </div>
        ) : !data ? (
          <div className="text-[11px] text-red-400">Error cargando actividad</div>
        ) : (
          <div className="space-y-3">
            {/* Heatmap */}
            <div>
              <div className="text-[9px] uppercase tracking-wider text-gray-600 mb-1">
                Distribución horaria (últimos 7 días)
              </div>
              <HourlyBar hours={data.hourly_distribution} />
              <div className="flex justify-between text-[8px] text-gray-700 mt-0.5">
                <span>0h</span><span>6h</span><span>12h</span><span>18h</span><span>23h</span>
              </div>
            </div>

            {/* Recent activity */}
            {data.activity.length > 0 && (
              <div>
                <div className="text-[9px] uppercase tracking-wider text-gray-600 mb-2">
                  Actividad reciente
                </div>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {data.activity.slice(0, 10).map(a => (
                    <div key={a.log_id} className="flex items-center gap-3 text-[10px]">
                      <span className="text-gray-600 font-mono w-32 shrink-0">
                        {new Date(a.created_at).toLocaleString('es-AR', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                      </span>
                      <span className="text-gray-400">{ACTION_LABELS[a.action_type] || a.action_type}</span>
                      {a.target_email && <span className="text-gray-600">→ {a.target_email}</span>}
                      {a.duration_seconds != null && (
                        <span className="text-gray-700 font-mono ml-auto">{a.duration_seconds}s</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Summary cards
// ---------------------------------------------------------------------------

function TeamSummary({ members }) {
  const active = members.filter(m => m.is_active);
  const totalActions  = members.reduce((s, m) => s + (m.total_actions  || 0), 0);
  const totalClients  = new Set(members.flatMap(() => [])).size; // approximation
  const totalSessions = members.reduce((s, m) => s + (m.support_sessions || 0), 0);
  const totalResolved = members.reduce((s, m) => s + (m.issues_resolved || 0), 0);

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div className="bg-[#111] rounded-xl border border-white/5 p-4">
        <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-1">Colaboradores activos</div>
        <div className="text-2xl font-bold font-mono text-white">{active.length}</div>
        <div className="text-[10px] text-gray-600 mt-0.5">de {members.length} en total</div>
      </div>
      <div className="bg-[#111] rounded-xl border border-white/5 p-4">
        <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-1">Acciones totales</div>
        <div className="text-2xl font-bold font-mono text-amber-400">{totalActions}</div>
        <div className="text-[10px] text-gray-600 mt-0.5">en el período</div>
      </div>
      <div className="bg-[#111] rounded-xl border border-white/5 p-4">
        <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-1">Sesiones de soporte</div>
        <div className="text-2xl font-bold font-mono text-purple-400">{totalSessions}</div>
      </div>
      <div className="bg-[#111] rounded-xl border border-white/5 p-4">
        <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-1">Incidencias resueltas</div>
        <div className="text-2xl font-bold font-mono text-emerald-400">{totalResolved}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function StaffAnalytics() {
  const [data, setData]     = useState(null);
  const [days, setDays]     = useState(30);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getStaffAnalytics(days);
      setData(result);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  const members = data?.members || [];

  const cols = [
    'Colaborador', 'Rol', 'Acciones', 'Clientes', 'Soporte', 'Archivos', 'Reinicios', 'Tiempo activo', 'Últ. actividad', '',
  ];

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
          {[7, 14, 30, 90].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-colors ${
                days === d
                  ? 'bg-amber-500/20 text-amber-400'
                  : 'bg-white/5 text-gray-500 hover:text-white'
              }`}
            >
              {d}d
            </button>
          ))}
          <button onClick={load} className="text-gray-600 hover:text-white transition-colors ml-1">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {loading && !data ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-5 h-5 text-gray-600 animate-spin" />
        </div>
      ) : members.length === 0 ? (
        <div className="bg-[#111] rounded-xl border border-white/5 p-12 text-center">
          <Users className="w-8 h-8 text-gray-700 mx-auto mb-3" />
          <div className="text-[11px] text-gray-600 italic">
            Sin colaboradores. Crea el primero en la pestaña "Colaboradores".
          </div>
        </div>
      ) : (
        <>
          <TeamSummary members={members} />

          {/* Analytics table */}
          <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="border-b border-white/5">
                    {cols.map(c => (
                      <th key={c} className="text-left px-4 py-3 text-[9px] uppercase tracking-wider text-gray-600 font-medium whitespace-nowrap">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {members.map(m => (
                    <StaffRow
                      key={m.staff_id}
                      member={m}
                      selected={selected === m.staff_id}
                      onSelect={setSelected}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-[9px] text-gray-700 text-right">
            Haz clic en una fila para ver la distribución horaria y actividad detallada
          </p>
        </>
      )}
    </div>
  );
}
