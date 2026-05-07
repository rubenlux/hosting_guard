import React, { useEffect, useState, useCallback } from 'react';
import { Wifi, Clock, Activity, RefreshCw, Monitor, ChevronDown, ChevronRight } from 'lucide-react';
import { getAdminOnlineUsers } from '../../services/api';

function timeSince(str) {
  if (!str) return '—';
  const secs = Math.floor((Date.now() - new Date(str).getTime()) / 1000);
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  return `${Math.floor(secs / 3600)}h`;
}

function presenceDot(status) {
  if (status === 'online') return 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]';
  if (status === 'active') return 'bg-amber-400';
  return 'bg-gray-600';
}

function presenceColor(status) {
  if (status === 'online') return 'text-emerald-400';
  if (status === 'active') return 'text-amber-400';
  return 'text-gray-500';
}

function Initials({ email }) {
  const letters = email ? email.slice(0, 2).toUpperCase() : '??';
  const colors = ['bg-blue-600', 'bg-purple-600', 'bg-emerald-600', 'bg-amber-600', 'bg-rose-600'];
  const color = colors[(email?.charCodeAt(0) || 0) % colors.length];
  return (
    <div className={`w-7 h-7 rounded-full ${color} flex items-center justify-center text-[10px] font-bold text-white shrink-0`}>
      {letters}
    </div>
  );
}

function UserRow({ u, expanded, onToggle }) {
  const hasSessions = (u.sessions?.length || 0) > 1;
  return (
    <>
      <div
        className="flex items-center gap-3 px-4 py-2.5 hover:bg-white/3 transition-colors"
        style={{ cursor: hasSessions ? 'pointer' : 'default' }}
        onClick={() => hasSessions && onToggle(u.user_id)}
      >
        <Initials email={u.email} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-white font-medium truncate">{u.email}</span>
            {u.role === 'admin' && (
              <span className="text-[8px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded font-bold uppercase">admin</span>
            )}
            {u.plan && u.plan !== 'free' && (
              <span className="text-[8px] bg-blue-500/15 text-blue-400 px-1.5 py-0.5 rounded uppercase">{u.plan}</span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <Monitor className="w-2.5 h-2.5 text-gray-600 shrink-0" />
            <span className="text-[9px] text-gray-500 truncate font-mono">{u.current_path || '/'}</span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <div className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${presenceDot(u.status)}`} />
            <span className={`text-[9px] font-semibold uppercase ${presenceColor(u.status)}`}>{u.status}</span>
            {hasSessions && (
              <span className="text-[8px] px-1 rounded text-gray-500" style={{ background: 'rgba(255,255,255,0.08)' }}>
                {u.session_count}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <span className="text-[9px] text-gray-600">{timeSince(u.last_seen)}</span>
            {hasSessions && (
              expanded
                ? <ChevronDown className="w-2.5 h-2.5 text-gray-600" />
                : <ChevronRight className="w-2.5 h-2.5 text-gray-600" />
            )}
          </div>
        </div>
      </div>

      {expanded && hasSessions && (
        <div className="border-t border-white/4 divide-y divide-white/4" style={{ background: 'rgba(255,255,255,0.02)' }}>
          {u.sessions.map((s) => (
            <div key={s.session_id} className="flex items-center gap-3 pl-12 pr-4 py-2 hover:bg-white/3 transition-colors">
              <div className="flex-1 min-w-0">
                <div className="text-[9px] text-gray-400 font-mono truncate">{s.current_path || '/'}</div>
                <div className="text-[8px] text-gray-600 mt-0.5">{s.device} · {s.ip || '—'}</div>
              </div>
              <div className="text-[9px] text-gray-600 shrink-0">{timeSince(s.last_seen)}</div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export default function OnlineUsersCard() {
  const [data, setData]         = useState(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [expanded, setExpanded] = useState({});
  const [tick, setTick]         = useState(0);

  const load = useCallback(async () => {
    try {
      setError(null);
      const r = await getAdminOnlineUsers();
      setData(r);
    } catch {
      setError('Error cargando presencia');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const poll   = setInterval(load, 30_000);
    const ticker = setInterval(() => setTick(t => t + 1), 15_000);
    return () => { clearInterval(poll); clearInterval(ticker); };
  }, [load]);

  const toggle = (uid) => setExpanded(e => ({ ...e, [uid]: !e[uid] }));

  const summary = data || {};
  const users   = data?.users || [];

  return (
    <div className="bg-[#111] rounded-xl border border-white/8 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Wifi className="w-4 h-4 text-emerald-400" />
          <span className="text-[11px] font-semibold text-white">Usuarios Online</span>
        </div>
        <button onClick={load} disabled={loading} className="p-1 rounded hover:bg-white/5 transition-colors">
          <RefreshCw className={`w-3.5 h-3.5 text-gray-500 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Summary pills — unique user counts */}
      <div className="grid grid-cols-3 divide-x divide-white/5 border-b border-white/5">
        {[
          { icon: Wifi,     label: 'Online ahora', val: summary.online_now ?? '—', color: 'text-emerald-400' },
          { icon: Activity, label: 'Activo 15min', val: summary.active_15m ?? '—', color: 'text-amber-400'   },
          { icon: Clock,    label: 'Idle 30min',   val: summary.idle_30m   ?? '—', color: 'text-gray-400'    },
        ].map(({ icon: Icon, label, val, color }) => (
          <div key={label} className="flex flex-col items-center py-3 gap-0.5">
            <span className={`text-lg font-bold ${color}`}>{val}</span>
            <span className="text-[9px] text-gray-600 uppercase tracking-wide">{label}</span>
          </div>
        ))}
      </div>

      {error && <div className="px-4 py-3 text-[11px] text-red-400">{error}</div>}
      {!error && users.length === 0 && !loading && (
        <div className="px-4 py-6 text-center text-[11px] text-gray-600">
          No hay usuarios activos en los últimos 30 min.
        </div>
      )}

      {users.length > 0 && (
        <div className="divide-y divide-white/5 max-h-[420px] overflow-y-auto">
          {users.map((u) => (
            <UserRow key={u.user_id} u={u} expanded={!!expanded[u.user_id]} onToggle={toggle} tick={tick} />
          ))}
        </div>
      )}

      {users.length > 0 && (
        <div className="px-4 py-2 border-t border-white/5 text-[9px] text-gray-600 text-right">
          {users.length} usuario{users.length !== 1 ? 's' : ''} único{users.length !== 1 ? 's' : ''} — actualiza cada 30s
        </div>
      )}
    </div>
  );
}
