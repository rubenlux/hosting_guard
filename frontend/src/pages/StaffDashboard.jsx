import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Shield, Users, Activity, LogOut, Search, RefreshCw,
  Server, FileText, RotateCcw, Clock, ChevronRight,
  AlertCircle, Eye, Terminal,
} from 'lucide-react';
import {
  getStaffMe, staffLogout, getStaffClients, getMyActivity,
  staffStartSupportSession,
} from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { useStaffTracking } from '../hooks/useStaffTracking';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('es-AR', { day: '2-digit', month: 'short', year: 'numeric' });
}

const ACTION_LABELS = {
  staff_login:           'Inicio de sesión',
  support_session_start: 'Soporte remoto iniciado',
  support_session_end:   'Soporte remoto finalizado',
  hosting_viewed:        'Hosting visto',
  logs_viewed:           'Logs vistos',
  file_edited:           'Archivo editado',
  hosting_restarted:     'Hosting reiniciado',
  hosting_stopped:       'Hosting detenido',
  hosting_started:       'Hosting iniciado',
  issue_resolved:        'Incidencia resuelta',
  client_note_added:     'Nota añadida',
  zip_uploaded:          'Archivo subido',
  metrics_viewed:        'Métricas vistas',
};

const ACTION_ICON = {
  support_session_start: <Shield className="w-3.5 h-3.5 text-amber-400" />,
  file_edited:           <FileText className="w-3.5 h-3.5 text-blue-400" />,
  hosting_restarted:     <RotateCcw className="w-3.5 h-3.5 text-orange-400" />,
  logs_viewed:           <Terminal className="w-3.5 h-3.5 text-purple-400" />,
  issue_resolved:        <AlertCircle className="w-3.5 h-3.5 text-emerald-400" />,
};

function ActionIcon({ type }) {
  return ACTION_ICON[type] ?? <Activity className="w-3.5 h-3.5 text-gray-500" />;
}

// ---------------------------------------------------------------------------
// Subcomponents
// ---------------------------------------------------------------------------

function StatCard({ label, value, sub, color = 'text-white' }) {
  return (
    <div className="bg-[#111] rounded-xl border border-white/5 p-4">
      <div className="text-[9px] uppercase tracking-widest text-gray-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
      {sub && <div className="text-[10px] text-gray-600 mt-0.5">{sub}</div>}
    </div>
  );
}

function ClientRow({ client, canSupport, onSupport, supporting }) {
  return (
    <tr className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
      <td className="px-4 py-3 font-mono text-gray-500 text-[10px]">
        #{String(client.user_id).padStart(4, '0')}
      </td>
      <td className="px-4 py-3 text-white text-[11px]">{client.email}</td>
      <td className="px-4 py-3 text-gray-500 text-[10px]">{fmtDate(client.created_at)}</td>
      <td className="px-4 py-3 text-[10px]">
        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
          client.plan === 'pro' ? 'bg-purple-500/20 text-purple-400' : 'bg-white/5 text-gray-500'
        }`}>{client.plan || 'free'}</span>
      </td>
      <td className="px-4 py-3">
        {canSupport && (
          <button
            onClick={() => onSupport(client)}
            disabled={supporting === client.user_id}
            className="flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-bold
              bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {supporting === client.user_id
              ? <RefreshCw className="w-3 h-3 animate-spin" />
              : <Shield className="w-3 h-3" />}
            Soporte
          </button>
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function StaffDashboard() {
  const navigate = useNavigate();
  const { activateSupportSession } = useAuth();
  const { track } = useStaffTracking();

  const [staff, setStaff]         = useState(null);
  const [clients, setClients]     = useState([]);
  const [activity, setActivity]   = useState([]);
  const [search, setSearch]       = useState('');
  const [loading, setLoading]     = useState(true);
  const [supporting, setSupporting] = useState(null);
  const [error, setError]         = useState(null);

  const load = useCallback(async () => {
    try {
      const [me, cls, act] = await Promise.all([
        getStaffMe(),
        getStaffClients(),
        getMyActivity(30),
      ]);
      setStaff(me);
      setClients(cls);
      setActivity(act);
      setError(null);
    } catch (err) {
      if (err?.response?.status === 401) {
        navigate('/staff/login');
      } else {
        setError('Error cargando datos. Reintentando...');
      }
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  const handleLogout = async () => {
    await staffLogout().catch(() => {});
    navigate('/staff/login');
  };

  const handleSupport = async (client) => {
    if (!window.confirm(`¿Iniciar sesión de soporte para ${client.email}?\n\nDuración: 15 minutos. Quedará registrado.`)) return;
    setSupporting(client.user_id);
    try {
      // 1. Obtener el token de soporte del backend (verifica permisos, crea sesión)
      const data = await staffStartSupportSession(client.user_id);

      // 2. Activar el support_token cookie Y actualizar el contexto de auth en un solo paso.
      //    activateSupportSession llama a POST /support/activate (setea la cookie HttpOnly)
      //    y luego GET /me con el nuevo cookie → setUser(clientData), setSupportSession({...})
      //    Esto es CRÍTICO: sin actualizar useAuth el PrivateRoute ve user=null y redirige a '/'
      await activateSupportSession(data.token);

      track('support_session_start', {
        target_user_id: client.user_id,
        description: `Sesión de soporte iniciada para ${client.email}`,
      });

      // Mark origin so that "Salir del modo soporte" returns here, not to login page
      sessionStorage.setItem('support_origin', 'staff');
      navigate('/dashboard');
    } catch (err) {
      alert(err?.response?.data?.detail || 'Error iniciando sesión de soporte');
    } finally {
      setSupporting(null);
    }
  };

  const filtered = clients.filter(c =>
    !search || c.email.toLowerCase().includes(search.toLowerCase())
  );

  // Stats rápidas del día de hoy
  const today = new Date().toISOString().slice(0, 10);
  const todayActivity = activity.filter(a => a.created_at?.startsWith(today));
  const todayClients  = new Set(todayActivity.map(a => a.target_user_id).filter(Boolean)).size;
  const todaySessions = todayActivity.filter(a => a.action_type === 'support_session_start').length;

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center">
        <RefreshCw className="w-6 h-6 text-gray-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">

      {/* Header */}
      <header className="border-b border-white/5 bg-[#0d0d0d]">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-amber-400" />
            <span className="text-sm font-bold text-white">Panel de Colaborador</span>
          </div>

          {staff && (
            <div className="ml-4 flex items-center gap-2">
              <div className="w-6 h-6 rounded-full bg-amber-500/20 flex items-center justify-center text-[10px] font-bold text-amber-400">
                {staff.full_name?.[0]?.toUpperCase() || 'S'}
              </div>
              <div>
                <div className="text-[11px] text-white font-medium leading-none">{staff.full_name}</div>
                <div className="text-[9px] text-amber-400 uppercase tracking-wider mt-0.5">{staff.role}</div>
              </div>
            </div>
          )}

          <div className="ml-auto flex items-center gap-3">
            <button onClick={load} className="text-gray-600 hover:text-white transition-colors">
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold
                bg-white/5 text-gray-400 hover:bg-red-500/10 hover:text-red-400 transition-colors"
            >
              <LogOut className="w-3 h-3" /> Salir
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-3 text-[11px] text-red-400">
            {error}
          </div>
        )}

        {/* Stats del día */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Acciones hoy"    value={todayActivity.length} color="text-white" />
          <StatCard label="Clientes atendidos" value={todayClients}       color="text-amber-400" />
          <StatCard label="Sesiones soporte"   value={todaySessions}      color="text-purple-400" />
          <StatCard label="Total clientes"     value={clients.length}     color="text-emerald-400" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Lista de clientes */}
          <div className="lg:col-span-2 bg-[#111] rounded-xl border border-white/5 overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-3 border-b border-white/5">
              <Users className="w-4 h-4 text-gray-500" />
              <span className="text-xs font-bold text-white">Clientes</span>
              <span className="text-[9px] text-gray-600">{filtered.length} de {clients.length}</span>
              <div className="ml-auto flex items-center gap-2 bg-white/5 rounded-lg px-2.5 py-1.5">
                <Search className="w-3 h-3 text-gray-600" />
                <input
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Buscar por email..."
                  className="bg-transparent text-[11px] text-white placeholder-gray-600 outline-none w-40"
                />
              </div>
            </div>

            <div className="overflow-auto max-h-[480px]">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-[#111]">
                  <tr className="border-b border-white/5">
                    {['ID', 'Email', 'Fecha', 'Plan', 'Acción'].map(h => (
                      <th key={h} className="text-left px-4 py-2 text-[9px] uppercase tracking-wider text-gray-600 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr><td colSpan={5} className="p-8 text-center text-gray-600 italic text-[11px]">Sin resultados</td></tr>
                  ) : filtered.map(c => (
                    <ClientRow
                      key={c.user_id}
                      client={c}
                      canSupport={staff?.role === 'support'}
                      onSupport={handleSupport}
                      supporting={supporting}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Actividad reciente */}
          <div className="bg-[#111] rounded-xl border border-white/5 overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-white/5">
              <Clock className="w-4 h-4 text-gray-500" />
              <span className="text-xs font-bold text-white">Mi actividad</span>
            </div>

            <div className="overflow-auto max-h-[480px]">
              {activity.length === 0 ? (
                <div className="p-6 text-center text-[11px] text-gray-600 italic">Sin actividad registrada</div>
              ) : (
                <div className="divide-y divide-white/5">
                  {activity.map(a => (
                    <div key={a.log_id} className="flex items-start gap-3 px-4 py-3">
                      <div className="mt-0.5 shrink-0">
                        <ActionIcon type={a.action_type} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] text-white leading-snug truncate">
                          {ACTION_LABELS[a.action_type] || a.action_type}
                        </div>
                        {a.target_email && (
                          <div className="text-[10px] text-gray-500 truncate">{a.target_email}</div>
                        )}
                        <div className="text-[9px] text-gray-700 mt-0.5">{timeAgo(a.created_at)}</div>
                      </div>
                      {a.duration_seconds != null && (
                        <div className="text-[9px] text-gray-600 font-mono shrink-0">
                          {a.duration_seconds}s
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
