import React, { useEffect, useState } from 'react';
import api, { listHostings, deleteHosting, restartHosting, stopHosting, startHosting, getLogs, getMetrics, getOrchestratorEvents } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import {
  Globe,
  Cpu,
  CheckCircle2,
  Loader,
  RefreshCw,
  ShieldCheck,
  Trash2,
  Plus,
  Activity,
  Database,
  Zap,
  Bell,
  CreditCard,
  Settings,
  LifeBuoy,
  Play,
  Square,
  RotateCcw,
  FileText,
  Key,
  Lock,
  Mail,
  BarChart3,
  Headset,
  ChevronLeft,
  ChevronRight,
  Bot
} from 'lucide-react';
import '../Dashboard.css';
import HostingCreationForm from '../components/HostingCreationForm';
import LogsModal from '../components/LogsModal';
import ZipUploadModal from '../components/ZipUploadModal';
import { AlertTriangle, Upload } from "lucide-react"

const Dashboard = () => {
  const { user, logoutAction, setUser } = useAuth();
  const [hostings, setHostings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [selectedHosting, setSelectedHosting] = useState(null);
  const [showUpload, setShowUpload] = useState(false);
  const [selectedUploadHosting, setSelectedUploadHosting] = useState(null);
  const [currentLogs, setCurrentLogs] = useState('');
  const [lastLogsTimestamp, setLastLogsTimestamp] = useState(null);
  const [logsLoading, setLogsLoading] = useState(false);
  const [metrics, setMetrics] = useState({});
  const [events, setEvents] = useState([]);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  const expiringHostings = hostings.filter(
    h => h.plan === 'free' && h.days_remaining !== null && h.days_remaining <= 3
  );
  const expiredHostings = hostings.filter(
    h => h.plan === 'free' && h.days_remaining === 0
  );

  const getStatusClass = (status) => {
    switch (status) {
      case 'active': return 'ok';
      case 'starting': return 'starting';
      case 'stopped': return 'error';
      case 'error': return 'error';
      case 'not_found': return 'error';
      default: return 'warn';
    }
  };

  const fetchHostings = async () => {
    setLoading(true);
    try {
      const data = await listHostings();
      setHostings(data);

      // Check for errors to show alerts
      data.forEach(h => {
        if (h.status === 'error') {
          console.warn(`Alerta: El proyecto ${h.name} está en estado de error.`);
        }
      });
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchMetrics = async (hostingId) => {
    try {
      const data = await getMetrics(hostingId);
      setMetrics(prev => ({ ...prev, [hostingId]: data }));
    } catch (err) {
      console.error(`Error fetching metrics for ${hostingId}:`, err);
    }
  };

  const fetchEvents = async () => {
    try {
      const data = await getOrchestratorEvents();
      setEvents(data);
    } catch (err) {
      console.error("Error fetching events:", err);
    }
  };

  const handleDelete = async (id, name) => {
    if (window.confirm(`¿Seguro que quieres eliminar el hosting "${name}"? Esta acción es irreversible.`)) {
      try {
        await deleteHosting(id);
        setHostings(hostings.filter(h => h.hosting_id !== id));
      } catch (err) {
        alert("Error al eliminar: " + err.message);
      }
    }
  };

  const handleAction = async (id, actionFn) => {
    try {
      await actionFn(id);
      fetchHostings(); // Refresh status
    } catch (err) {
      alert("Error en la acción: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleOpenLogs = async (hosting) => {
    setSelectedHosting(hosting);
    setShowLogs(true);
    setLogsLoading(true);
    setCurrentLogs(''); // Reset logs for new modal
    setLastLogsTimestamp(null);
    try {
      const data = await getLogs(hosting.hosting_id);
      setCurrentLogs(data.logs);
      setLastLogsTimestamp(data.timestamp);
    } catch (err) {
      setCurrentLogs("Error al cargar logs: " + (err.response?.data?.detail || err.message));
    } finally {
      setLogsLoading(false);
    }
  };

  const handleRefreshLogs = async () => {
    if (!selectedHosting) return;
    setLogsLoading(true);
    try {
      // Usamos el último timestamp para obtener solo lo nuevo
      const data = await getLogs(selectedHosting.hosting_id, lastLogsTimestamp);
      if (data.logs) {
        setCurrentLogs(prev => prev + data.logs);
      }
      setLastLogsTimestamp(data.timestamp);
    } catch (err) {
      console.error("Error al recargar logs:", err);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleToggleAutoscale = async () => {
    if (actionLoading) return;
    const newValue = !user?.autoscale_enabled;
    setActionLoading(true);
    try {
      await api.post("/user/config", { autoscale_enabled: newValue });
      setUser(prev => ({ ...prev, autoscale_enabled: newValue }));
    } catch (err) {
      alert("Error al actualizar config: " + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleTopup = async () => {
    if (actionLoading) return;
    setActionLoading(true);
    try {
      // Recarga fija de $10 para la demo
      const res = await api.post("/user/topup", { amount: 10 });
      setUser(prev => ({ ...prev, balance: res.data.balance }));
    } catch (err) {
      alert("Error al recargar: " + (err.response?.data?.detail || err.message));
    } finally {
      setActionLoading(false);
    }
  };

  const handleRefreshUser = async () => {
    try {
      const res = await api.get('/me');
      setUser(res.data);
    } catch (err) {
      console.error("Error refreshing user info:", err);
    }
  };

  useEffect(() => {
    fetchHostings();
    fetchEvents();

    // Polling de métricas cada 10 segundos
    const metricsInterval = setInterval(() => {
      hostings.forEach(h => {
        if (h.status === 'active') {
          fetchMetrics(h.hosting_id);
        }
      });
    }, 10000);

    // Polling de eventos cada 15 segundos
    const eventsInterval = setInterval(() => {
      fetchEvents();
    }, 15000);

    return () => {
      clearInterval(metricsInterval);
      clearInterval(eventsInterval);
    };
  }, [hostings.length]); // Re-run when list changes

  const uptimeData = Array.from({ length: 40 }, (_, i) => Math.random() > 0.95 ? 'warn' : 'ok');

  return (
    <div className={`dashboard-container fixed inset-0 z-50 overflow-hidden ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="logo-dash">
          <div className="logo-icon-dash text-background"><ShieldCheck className="w-5 h-5" /></div>
          {!isSidebarCollapsed && (
            <div className="flex-1 opacity-fadeIn">
              <div className="logo-text-dash">HostingGuard</div>
              <div className="text-[10px] text-accent font-mono tracking-widest">.LAT</div>
            </div>
          )}
          <button 
            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            className="sidebar-toggle-btn"
          >
            {isSidebarCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>
        </div>

        <nav className="nav-dash">
          <div className="nav-label-dash">{isSidebarCollapsed ? '•' : 'Principal'}</div>
          <div className="nav-item-dash active" onClick={() => setShowCreate(false)}>
            <div className="nav-icon-dash icon-green"><Activity size={18} /></div>
            {!isSidebarCollapsed && <span>Dashboard</span>}
          </div>
          <div className="nav-item-dash" onClick={() => setShowCreate(false)}>
            <div className="nav-icon-dash icon-blue"><Globe size={18} /></div>
            {!isSidebarCollapsed && <span>Mis Sitios</span>}
          </div>
          <div className="nav-item-dash">
            <div className="nav-icon-dash icon-multi"><BarChart3 size={18} /></div>
            {!isSidebarCollapsed && <span>Métricas</span>}
          </div>
          <div className="nav-item-dash">
            <div className="nav-icon-dash icon-ia"><Bot size={18} /></div>
            {!isSidebarCollapsed && <span>IA Advisory</span>}
            {!isSidebarCollapsed && <span className="ml-auto bg-danger/20 text-danger text-[9px] px-1.5 py-0.5 rounded-full">2</span>}
          </div>

          <div className="nav-label-dash">{isSidebarCollapsed ? '•' : 'Gestión'}</div>
          <div className="nav-item-dash">
            <div className="nav-icon-dash icon-gold"><Key size={18} /></div>
            {!isSidebarCollapsed && <span>Dominios</span>}
          </div>
          <div className="nav-item-dash">
            <div className="nav-icon-dash icon-purple"><Database size={18} /></div>
            {!isSidebarCollapsed && <span>Backups</span>}
          </div>
          <div className="nav-item-dash">
            <div className="nav-icon-dash icon-orange"><Lock size={18} /></div>
            {!isSidebarCollapsed && <span>SSL</span>}
          </div>
          <div className="nav-item-dash">
            <div className="nav-icon-dash icon-blue"><Mail size={18} /></div>
            {!isSidebarCollapsed && <span>Email</span>}
          </div>

          <div className="nav-label-dash">{isSidebarCollapsed ? '•' : 'Cuenta'}</div>
          <div className="nav-item-dash">
            <div className="nav-icon-dash icon-blue"><CreditCard size={18} /></div>
            {!isSidebarCollapsed && <span>Facturación</span>}
          </div>
          <div className="nav-item-dash">
            <div className="nav-icon-dash"><Settings size={18} /></div>
            {!isSidebarCollapsed && <span>Configuración</span>}
          </div>
          <div className="nav-item-dash">
            <div className="nav-icon-dash"><Headset size={18} /></div>
            {!isSidebarCollapsed && <span>Soporte</span>}
          </div>
        </nav>

        <div className="p-4 border-t border-white/5 mt-auto">
          <div className={`flex items-center gap-3 p-3 bg-surface2 rounded-xl ${isSidebarCollapsed ? 'justify-center p-2' : ''}`}>
            <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold text-xs uppercase shrink-0">
              {user?.email?.[0] || 'U'}
            </div>
            {!isSidebarCollapsed && (
              <div className="flex-1 min-w-0 opacity-fadeIn">
                <div className="text-[11px] font-bold text-white truncate">{user?.email}</div>
                <div className="text-[9px] text-accent font-mono uppercase">Plan {user?.plan || 'Free'}</div>
              </div>
            )}
            {!isSidebarCollapsed && (
              <button onClick={logoutAction} className="text-muted hover:text-danger">
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
          {isSidebarCollapsed && (
            <button onClick={logoutAction} className="mt-2 w-full flex justify-center text-muted hover:text-danger">
              <RefreshCw className="w-4 h-4" />
            </button>
          )}
        </div>
      </aside>

      {/* MAIN */}
      <main className="main-dash">
        <div className="topbar-dash">
          <div className="text-[15px] font-medium flex-1">
            {showCreate ? 'Nuevo Proyecto' : 'Dashboard Overview'}
          </div>
          <div className="hidden md:flex items-center gap-2 bg-accent/5 text-accent px-3 py-1.5 rounded-full border border-accent/10 text-xs font-medium">
            <div className="pulse-dash"></div> Servicios Operativos
          </div>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="btn-dash btn-ghost-dash"
          >
            {showCreate ? 'Volver' : '+ Nuevo sitio'}
          </button>
          <button className="btn-dash btn-primary-dash">Upgrade</button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 lg:p-10">
          {showCreate ? (
            <div className="max-w-4xl mx-auto">
              <HostingCreationForm onSuccess={() => { setShowCreate(false); fetchHostings(); }} />
            </div>
          ) : (
            <>
              {/* EXPIRATION WARNINGS */}
              {expiringHostings.map(h => (
                <div key={h.hosting_id} className={`flex items-center justify-between gap-4 px-5 py-3 rounded-2xl border mb-3 ${
                  h.days_remaining === 0
                    ? 'bg-red-500/10 border-red-500/30 text-red-400'
                    : 'bg-warn/10 border-warn/30 text-warn'
                }`}>
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span className="text-xs font-medium">
                      {h.days_remaining === 0
                        ? `Tu sitio "${h.name}" ha expirado. Actualizá tu plan para reactivarlo.`
                        : `Tu sitio "${h.name}" vence en ${h.days_remaining} día${h.days_remaining === 1 ? '' : 's'}. ¡Actualizá tu plan!`
                      }
                    </span>
                  </div>
                  <button className="text-[10px] font-black uppercase tracking-wider bg-warn/20 hover:bg-warn/30 px-3 py-1.5 rounded-lg transition-all whitespace-nowrap">
                    Upgrade →
                  </button>
                </div>
              ))}

              {/* AI ADVISORY */}
              <div className="advisory-box-dash border-scanner-warn flex flex-col md:flex-row gap-4 items-start md:items-center bg-[#050505]">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="ai-badge-dash">🤖 IA ADVISORY</span>
                    <span className="text-[11px] text-muted font-mono uppercase tracking-widest">Hace 3 min</span>
                  </div>
                  <div className="text-sm text-gray-400 leading-relaxed">
                    Detectamos un <strong className="text-white">aumento del 40% en el uso de CPU</strong>.
                    El patrón coincide con un plugin mal configurado tras la última actualización. Riesgo: <strong className="text-warn">MEDIO</strong>.
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button className="btn-dash btn-primary-dash text-xs">Diagnosticar</button>
                  <button className="btn-dash btn-ghost-dash text-xs">Cerrar</button>
                </div>
              </div>

              {/* METRICS */}
              <div className="metrics-row-dash overflow-x-auto pb-4">
                <div className="metric-card-dash green min-w-[200px] bg-[#050505] border-[#00ff88]/20">
                  <div className="text-[10px] text-muted font-mono uppercase mb-4 tracking-widest">Uptime General</div>
                  <div className="metric-value-dash font-mono text-glow text-[#00ff88]">99.9<span className="text-sm text-[#00ff88]/50 ml-0.5">%</span></div>
                  <div className="text-xs text-success mt-2">↑ Últimos 30 días</div>
                </div>
                <div className="metric-card-dash blue min-w-[200px] bg-[#050505] border-[#00aaff]/20">
                  <div className="text-[10px] text-muted font-mono uppercase mb-4 tracking-widest">CPU Promedio</div>
                  <div className="metric-value-dash font-mono text-glow text-[#00aaff]">23<span className="text-sm text-[#00aaff]/50 ml-0.5">%</span></div>
                  <div className="w-full h-1 bg-surface2 mt-4 rounded-full overflow-hidden">
                    <div className="h-full bg-accent" style={{ width: '23%' }}></div>
                  </div>
                </div>
                <div className="metric-card-dash amber min-w-[200px] bg-[#050505] border-[#ffaa00]/20">
                  <div className="text-[10px] text-muted font-mono uppercase mb-4 tracking-widest">RAM Usada</div>
                  <div className="metric-value-dash font-mono text-glow text-[#ffaa00]">2.1<span className="text-sm text-[#ffaa00]/50 ml-0.5">GB</span></div>
                  <div className="text-xs text-warn mt-2">52% en uso</div>
                </div>
                <div className="metric-card-dash purple min-w-[200px] bg-[#050505] border-[#aa00ff]/20">
                  <div className="text-[10px] text-muted font-mono uppercase mb-4 tracking-widest">Almacenamiento</div>
                  <div className="metric-value-dash font-mono text-glow text-[#aa00ff]">18<span className="text-sm text-[#aa00ff]/50 ml-0.5">GB</span></div>
                </div>
              </div>

              {/* GRID */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                  {/* SITES */}
                  <div className="card-dash">
                    <div className="card-header-dash">
                      <div className="text-sm font-bold flex items-center gap-2">
                        <Globe className="w-4 h-4 text-accent" /> Sus Proyectos
                      </div>
                      <button onClick={fetchHostings} className="text-muted hover:text-white transition-colors">
                        <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                      </button>
                    </div>
                    <div className="p-4 space-y-2">
                      {loading && hostings.length === 0 ? (
                        <div className="py-12 flex justify-center"><Loader className="animate-spin text-accent" /></div>
                      ) : hostings.length === 0 ? (
                        <div className="py-12 text-center text-muted italic">No hay hostings activos.</div>
                      ) : hostings.map(h => (
                        <div key={h.hosting_id} className="domain-row-dash group">
                          <div className="w-10 h-10 bg-surface2 rounded-xl flex items-center justify-center font-bold text-accent transition-colors group-hover:bg-accent/10">
                            {h.name[0].toUpperCase()}
                          </div>
                          <div className="flex-1">
                            <div className="text-sm font-bold text-white group-hover:text-accent transition-colors">{h.name}</div>
                            {h.plan === 'free' && h.days_remaining !== null && (
                              <span className={`text-[9px] font-black px-2 py-0.5 rounded-full uppercase tracking-wider ${
                                h.days_remaining <= 0
                                  ? 'bg-red-500/20 text-red-400'
                                  : h.days_remaining <= 3
                                  ? 'bg-warn/20 text-warn'
                                  : 'bg-accent/20 text-accent'
                              }`}>
                                {h.days_remaining <= 0 ? 'Expirado' : `${h.days_remaining}d restantes`}
                              </span>
                            )}
                            <div className="flex items-center gap-2">
                              <a href={h.url || `https://${h.subdomain}`} target="_blank" rel="noopener" className="text-[11px] text-muted font-mono hover:underline">
                                {h.subdomain}
                              </a>
                              {metrics[h.hosting_id] && (
                                <div className="flex items-center gap-2 text-[10px] bg-white/5 px-2 py-0.5 rounded border border-white/5 font-mono text-muted">
                                  <span className="flex items-center gap-1"><Cpu className="w-2.5 h-2.5" /> {metrics[h.hosting_id].cpu}</span>
                                  <span className="flex items-center gap-1"><Database className="w-2.5 h-2.5" /> {metrics[h.hosting_id].memory}</span>
                                </div>
                              )}
                            </div>
                          </div>
                          <div className="ml-auto flex items-center gap-2">
                            <div className={`domain-status-dash ${getStatusClass(h.status)} ${h.status === 'active' ? 'animate-led shadow-[0_0_10px_rgba(0,255,136,0.5)]' : ''}`}>● {h.status}</div>

                            <div className="flex items-center gap-1 border-l border-white/5 pl-2 ml-2">
                              {h.status === 'active' && (
                                <>
                                  {/* Botón ZIP upload — disponible para Sitios Web estáticos */}
                                  <button
                                    onClick={() => { setSelectedUploadHosting(h); setShowUpload(true); }}
                                    title="Subir archivos (.zip)"
                                    className="w-8 h-8 rounded-lg bg-white/5 text-muted hover:bg-[#00ff88]/20 hover:text-[#00ff88] flex items-center justify-center transition-all"
                                  >
                                    <Upload className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() => handleAction(h.hosting_id, stopHosting)}
                                    title="Detener"
                                    className="w-8 h-8 rounded-lg bg-white/5 text-muted hover:bg-danger/20 hover:text-danger flex items-center justify-center transition-all"
                                  >
                                    <Square className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() => handleAction(h.hosting_id, restartHosting)}
                                    title="Reiniciar"
                                    className="w-8 h-8 rounded-lg bg-white/5 text-muted hover:bg-accent/20 hover:text-accent flex items-center justify-center transition-all"
                                  >
                                    <RotateCcw className="w-3.5 h-3.5" />
                                  </button>
                                </>
                              )}

                              {/* Siempre permitir ver logs si el contenedor existe */}
                              {h.status !== 'not_found' && (
                                <button
                                  onClick={() => handleOpenLogs(h)}
                                  title="Ver Logs"
                                  className="w-8 h-8 rounded-lg bg-white/5 text-muted hover:bg-accent/20 hover:text-accent flex items-center justify-center transition-all"
                                >
                                  <FileText className="w-3.5 h-3.5" />
                                </button>
                              )}

                              {h.status === 'stopped' && (
                                <button
                                  onClick={() => handleAction(h.hosting_id, startHosting)}
                                  title="Iniciar"
                                  className="w-8 h-8 rounded-lg bg-accent/10 text-accent hover:bg-accent hover:text-background flex items-center justify-center transition-all"
                                >
                                  <Play className="w-3.5 h-3.5" />
                                </button>
                              )}

                              {h.status === 'starting' && (
                                <div className="w-8 h-8 flex items-center justify-center">
                                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-muted" />
                                </div>
                              )}

                              <button
                                onClick={() => handleDelete(h.hosting_id, h.name)}
                                title="Eliminar"
                                className="w-8 h-8 rounded-lg bg-danger/10 text-danger flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all hover:bg-danger hover:text-white"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* ACTIVITY */}
                  <div className="card-dash">
                    <div className="card-header-dash">
                      <div className="text-sm font-bold">Actividad Reciente</div>
                    </div>
                    <div className="p-4 space-y-4 max-h-[400px] overflow-y-auto">
                      {events.length === 0 ? (
                        <div className="text-[11px] text-muted italic p-2">Sin actividad reciente.</div>
                      ) : events.map(event => (
                        <div key={event.event_id} className="flex gap-4 items-start border-l-2 border-white/5 pl-4 ml-1">
                          <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${event.event_type === 'restart' ? 'bg-danger shadow-[0_0_8px_red] animate-led' :
                              event.event_type === 'panic' ? 'bg-warn shadow-[0_0_8px_orange] animate-led' :
                              event.event_type === 'PLAN_EXPIRED' ? 'bg-red-500 shadow-[0_0_8px_red] animate-led' :
                              event.event_type === 'PLAN_EXPIRING_SOON' ? 'bg-warn shadow-[0_0_8px_orange] animate-led' :
                                'bg-accent shadow-[0_0_8px_rgba(0,255,136,0.5)]'
                            }`}></div>
                          <div className="space-y-1">
                            <div className="text-xs font-bold text-white flex items-center gap-2">
                              {event.event_type.toUpperCase()}
                              <span className="text-[9px] text-muted font-normal bg-white/5 px-1.5 py-0.5 rounded capitalize">{event.container_name.split('_').slice(-1)[0]}</span>
                            </div>
                            <div className="text-[11px] text-gray-400 leading-tight">{event.message}</div>
                            <div className="text-[9px] text-muted font-mono uppercase tracking-tighter">
                              {new Date(event.created_at).toLocaleString()}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* RIGHT COLUMN */}
                <div className="space-y-6">
                  {/* PLAN & MONETIZATION */}
                  <div className="card-dash p-6 bg-gradient-to-br from-accent/5 to-transparent border-accent/20 font-sans">
                    <div className="flex justify-between items-start mb-6">
                      <div>
                        <div className="text-[10px] text-accent font-mono uppercase tracking-[0.2em] mb-2">Tu Saldo</div>
                        <div className="text-3xl font-black text-white">${user?.balance?.toFixed(2) || '0.00'}</div>
                      </div>
                      <div className={`px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-wider ${user?.has_payment_method ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-red-500/20 text-red-400 border border-red-500/30'}`}>
                        {user?.has_payment_method ? '💳 Vinculada' : '⚠️ Sin Tarjeta'}
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div 
                        onClick={handleToggleAutoscale}
                        className={`p-4 bg-white/5 rounded-2xl border relative overflow-hidden group transition-all cursor-pointer ${user?.autoscale_enabled ? 'border-scanner bg-[#00ff88]/5' : 'border-white/5 hover:border-white/20'}`}
                      >
                        {actionLoading && <div className="absolute inset-0 bg-black/20 flex items-center justify-center z-10"><RefreshCw className="w-4 h-4 animate-spin text-accent" /></div>}
                        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                          <Zap className="w-12 h-12 text-accent" />
                        </div>
                        <div className="relative">
                          <div className="flex justify-between items-center mb-1">
                            <span className="text-xs font-bold text-white flex items-center gap-2 italic">
                              <Zap className={`w-3 h-3 ${user?.autoscale_enabled ? 'text-accent fill-accent' : 'text-muted'}`} /> Auto-Scaling
                            </span>
                            <span className={`text-[10px] font-black uppercase ${user?.autoscale_enabled ? 'text-accent' : 'text-muted'}`}>
                              {user?.autoscale_enabled ? 'Activado' : 'Desactivado'}
                            </span>
                          </div>
                          <p className="text-[10px] text-gray-500 leading-relaxed pr-8">Optimiza recursos dinámicamente según picos de demanda real.</p>
                        </div>
                      </div>

                      {!user?.has_payment_method && (user?.balance <= 0) && (
                        <div className="text-[10px] bg-red-400/10 text-red-400 p-3 rounded-xl border border-red-400/20 flex items-center gap-3 font-medium animate-pulse">
                          <AlertTriangle className="w-4 h-4 shrink-0" /> Recarga saldo para evitar suspensiones por consumo excesivo.
                        </div>
                      )}

                      <button 
                        onClick={handleTopup}
                        disabled={actionLoading}
                        className="w-full py-4 bg-accent text-background rounded-2xl font-black text-xs hover:scale-[1.02] transition-all shadow-lg shadow-accent/20 active:scale-95 disabled:opacity-50 disabled:scale-100"
                      >
                        {actionLoading ? 'PROCESANDO...' : 'RECARGAR SALDO +$10'}
                      </button>
                    </div>
                  </div>

                  {/* UPTIME */}
                  <div className="card-dash p-6">
                    <div className="text-sm font-bold mb-1">📡 Uptime — 90 días</div>
                    <div className="text-2xl font-black text-accent mb-4">99.9%</div>
                    <div className="flex flex-wrap gap-1">
                      {uptimeData.map((s, i) => (
                        <div key={i} className={`w-2 h-6 rounded-[1px] ${s === 'ok' ? 'bg-accent/40' : 'bg-warn/60'}`}></div>
                      ))}
                    </div>
                  </div>

                  {/* NOTIFS */}
                  <div className="card-dash p-4 space-y-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Bell className="w-4 h-4 text-muted" />
                      <span className="text-xs font-bold">Notificaciones</span>
                    </div>
                    <div className="p-3 bg-warn/10 border border-warn/20 rounded-xl">
                      <div className="text-[10px] font-bold text-warn uppercase mb-1">Alerta de CPU</div>
                      <div className="text-[10px] text-gray-400">Picos detectados en tu proyecto principal.</div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </main>

      <LogsModal
        isOpen={showLogs}
        onClose={() => setShowLogs(false)}
        logs={currentLogs}
        projectName={selectedHosting?.name}
        onRefresh={handleRefreshLogs}
        loading={logsLoading}
      />

      <ZipUploadModal
        isOpen={showUpload}
        onClose={() => { setShowUpload(false); setSelectedUploadHosting(null); }}
        hosting={selectedUploadHosting}
      />
    </div>
  );
};

export default Dashboard;
