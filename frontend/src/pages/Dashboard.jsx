import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { listHostings, deleteHosting, restartHosting, stopHosting, startHosting, getLogs, getMetrics, getOrchestratorEvents, updateUserConfig, topupBalance, getMe, diagnoseHosting } from '../services/api';
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
  Bot,
  X,
  AlertTriangle,
  Upload,
  FolderOpen
} from 'lucide-react';
import '../Dashboard.css';
import HostingCreationForm from '../components/HostingCreationForm';
import LogsModal from '../components/LogsModal';
import ZipUploadModal from '../components/ZipUploadModal';
import PixelAnalytics from '../components/PixelAnalytics';
import AdminDashboard from './AdminDashboard';
import MonacoFileEditor from '../components/MonacoFileEditor';
import SupportBanner from '../components/SupportBanner';
import SupportChat from '../components/SupportChat';
import SupportTicketList from '../components/SupportTicketList';
import SiteManagement from '../components/SiteManagement';

const Dashboard = () => {
  const { user, logoutAction, setUser, isSupportSession, supportSession, deactivateSupportSession } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Determina la vista activa por URL; showCreate sobreescribe localmente
  const activeView = location.pathname === '/pixel' ? 'pixel'
                   : location.pathname === '/admin' ? 'admin'
                   : location.pathname === '/sites' ? 'sites'
                   : 'dashboard';

  const [hostings, setHostings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [selectedHosting, setSelectedHosting] = useState(null);
  const [showUpload, setShowUpload] = useState(false);
  const [selectedUploadHosting, setSelectedUploadHosting] = useState(null);
  const [showFiles, setShowFiles] = useState(false);
  const [selectedFilesHosting, setSelectedFilesHosting] = useState(null);
  const [currentLogs, setCurrentLogs] = useState('');
  const [lastLogsTimestamp, setLastLogsTimestamp] = useState(null);
  const [logsLoading, setLogsLoading] = useState(false);
  const [metrics, setMetrics] = useState({});
  const [events, setEvents] = useState([]);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [showSupport, setShowSupport] = useState(false);
  const [supportView, setSupportView] = useState('chat'); // 'chat' | 'history'
  const [openTicketId, setOpenTicketId] = useState(null);
  
  // AI Diagnostics State
  const [showDiagnosis, setShowDiagnosis] = useState(false);
  const [diagnosisData, setDiagnosisData] = useState(null);
  const [diagnosisLoading, setDiagnosisLoading] = useState(false);

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
    try {
      setLoading(true);
      const data = await listHostings();
      setHostings(data);
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
        toast.error("Error al eliminar el hosting. Inténtalo de nuevo.");
      }
    }
  };

  const handleAction = async (id, actionFn, needRefresh = true) => {
    setActionLoading(true);
    try {
      await actionFn(id);
      if (needRefresh) {
        fetchHostings();
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Error al ejecutar la acción');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDiagnose = async (id) => {
    try {
      setShowDiagnosis(true);
      setDiagnosisLoading(true);
      setDiagnosisData(null);
      const host = hostings.find(h => h.hosting_id === id);
      const result = await diagnoseHosting(id);
      setDiagnosisData({ hostingName: host?.name, ...result });
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Fallo AI Engine al diagnosticar.');
      setShowDiagnosis(false);
    } finally {
      setDiagnosisLoading(false);
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
      setCurrentLogs("Error al cargar logs. Inténtalo de nuevo.");
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

  const [errorToast, setErrorToast] = useState(null);

  const showError = (message) => {
    setErrorToast(message);
    setTimeout(() => setErrorToast(null), 5000);
  };

  const handleToggleAutoscale = async () => {
    if (actionLoading) return;
    const newValue = !user?.autoscale_enabled;
    setActionLoading(true);
    try {
      await updateUserConfig({ autoscale_enabled: newValue });
      setUser(prev => ({ ...prev, autoscale_enabled: newValue }));
    } catch (err) {
      if (err.response && err.response.data && err.response.data.detail) {
        showError(err.response.data.detail);
      } else {
        showError("Error al actualizar la configuración. Inténtalo de nuevo.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleTopup = async () => {
    if (actionLoading) return;
    setActionLoading(true);
    try {
      // Recarga fija de $10 para la demo
      const res = await topupBalance(10);
      setUser(prev => ({ ...prev, balance: res.balance }));
    } catch (err) {
      if (err.response && err.response.data && err.response.data.detail) {
        showError(err.response.data.detail);
      } else {
        showError("Error al recargar el saldo. Inténtalo de nuevo.");
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleRefreshUser = async () => {
    try {
      const res = await getMe();
      setUser(res);
    } catch (err) {
      console.error("Error refreshing user info:", err);
    }
  };

  // Ref always points to latest hostings so the metrics interval never closes over a stale snapshot
  const hostingsRef = useRef(hostings);
  useEffect(() => { hostingsRef.current = hostings; }, [hostings]);

  useEffect(() => {
    if (user?.role === 'admin') return;

    fetchHostings();
    fetchEvents();

    // Polling de métricas cada 10 segundos — lee hostingsRef para ver el estado actual
    const metricsInterval = setInterval(() => {
      hostingsRef.current.forEach(h => {
        if (h.status === 'active') {
          fetchMetrics(h.hosting_id);
        }
      });
    }, 10000);

    // Polling de eventos cada 15 segundos
    const eventsInterval = setInterval(fetchEvents, 15000);

    return () => {
      clearInterval(metricsInterval);
      clearInterval(eventsInterval);
    };
  }, [user?.role]); // eslint-disable-line react-hooks/exhaustive-deps

  if (user?.role === 'admin') {
    return <AdminDashboard />;
  }

  // Banner height: ~44px. Push the dashboard down when it's active.
  const bannerHeight = isSupportSession && supportSession ? 44 : 0;

  return (
    <>
      {/* SUPPORT BANNER — fixed above everything, outside the flex row container */}
      {isSupportSession && supportSession && (
        <div className="fixed top-0 left-0 right-0 z-[60]">
          <SupportBanner
            targetEmail={supportSession.targetEmail}
            adminEmail={supportSession.adminEmail}
            expiresAt={supportSession.expiresAt}
            onExit={deactivateSupportSession}
          />
        </div>
      )}

      <div
        className={`dashboard-container fixed inset-0 z-50 overflow-hidden ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}
        style={bannerHeight ? { top: bannerHeight } : undefined}
      >
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
          <div className={`nav-item-dash ${activeView === 'dashboard' && !showCreate ? 'active' : ''}`} onClick={() => { setShowCreate(false); navigate('/dashboard'); }}>
            <div className="nav-icon-dash icon-green"><Activity size={18} /></div>
            {!isSidebarCollapsed && <span>Dashboard</span>}
          </div>
          <div className={`nav-item-dash ${activeView === 'sites' ? 'active' : ''}`} onClick={() => { setShowCreate(false); navigate('/sites'); }}>
            <div className="nav-icon-dash icon-blue"><Globe size={18} /></div>
            {!isSidebarCollapsed && <span>Mis Sitios</span>}
          </div>
          <div className={`nav-item-dash ${activeView === 'pixel' ? 'active' : ''}`} onClick={() => { setShowCreate(false); navigate('/pixel'); }}>
            <div className="nav-icon-dash icon-multi"><BarChart3 size={18} /></div>
            {!isSidebarCollapsed && <span>Pixel Analytics</span>}
          </div>
          <div className="nav-item-dash">
            <div className="nav-icon-dash icon-ia"><Bot size={18} /></div>
            {!isSidebarCollapsed && <span>IA Advisory</span>}
            {!isSidebarCollapsed && <span className="ml-auto bg-danger/20 text-danger text-[9px] px-1.5 py-0.5 rounded-full">2</span>}
          </div>

          {user?.role === 'admin' && (
            <div className={`nav-item-dash ${activeView === 'admin' ? 'active' : ''}`} onClick={() => { setShowCreate(false); navigate('/admin'); }}>
              <div className="nav-icon-dash icon-orange"><ShieldCheck size={18} /></div>
              {!isSidebarCollapsed && <span>Admin Panel</span>}
            </div>
          )}

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
          <div className="nav-item-dash"
            onClick={() => { setShowSupport(true); setSupportView('history'); setOpenTicketId(null); }}
          >
            <div className="nav-icon-dash" style={{ color: '#818cf8' }}><Headset size={18} /></div>
            {!isSidebarCollapsed && <span>Soporte</span>}
          </div>
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
            {showCreate ? 'Nuevo Proyecto'
              : activeView === 'pixel' ? 'Pixel Analytics'
              : activeView === 'admin' ? 'Panel de Administración'
              : activeView === 'sites' ? 'Mis Sitios (Operaciones)'
              : 'Dashboard Overview'}
          </div>
          <div className="hidden md:flex items-center gap-2 bg-accent/5 text-accent px-3 py-1.5 rounded-full border border-accent/10 text-xs font-medium">
            <div className="pulse-dash"></div> Servicios Operativos
          </div>
          {activeView !== 'admin' && (
            <button
              onClick={() => {
                if (showCreate) {
                  setShowCreate(false);
                } else {
                  navigate(activeView === 'sites' ? '/sites' : '/dashboard');
                  setShowCreate(true);
                }
              }}
              className="btn-dash btn-ghost-dash"
            >
              {showCreate ? 'Volver' : '+ Nuevo sitio'}
            </button>
          )}
          <button className="btn-dash btn-primary-dash">Upgrade</button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 lg:p-10">
          {showCreate ? (
            <div className="max-w-4xl mx-auto">
              <HostingCreationForm onSuccess={() => { setShowCreate(false); fetchHostings(); }} />
            </div>
          ) : activeView === 'pixel' ? (
            <PixelAnalytics />
          ) : activeView === 'admin' ? (
            <AdminDashboard />
          ) : activeView === 'sites' ? (
            <SiteManagement 
              hostings={hostings} 
              loading={loading} 
              onRefresh={fetchHostings}
              onAction={(id, action) => {
                if (action === 'start') handleAction(id, startHosting);
                else if (action === 'stop') handleAction(id, stopHosting);
                else if (action === 'restart') handleAction(id, restartHosting);
              }}
              onOpenLogs={handleOpenLogs}
              onDelete={handleDelete}
              onUploadZip={(h) => { setSelectedUploadHosting(h); setShowUpload(true); }}
              onOpenFiles={(h) => { setSelectedFilesHosting(h); setShowFiles(true); }}
              onDiagnose={handleDiagnose}
            />
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
              <div className="advisory-box-dash border-scanner-warn flex flex-col md:flex-row gap-4 items-start md:items-center bg-[#050505] mb-6">
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
                  <button className="btn-dash btn-primary-dash text-xs !bg-[#00ff88] !text-black !border-none hover:shadow-[0_0_15px_#00ff88]">Diagnosticar</button>
                  <button className="btn-dash btn-ghost-dash text-xs border border-white/10 hover:bg-white/5">Cerrar</button>
                </div>
              </div>

              {/* DASHBOARD SUMMARY CARDS (DYNAMIC) */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                {/* UPTIME */}
                <div className="bg-[#0a0a0c] border border-[rgba(0,255,136,0.15)] rounded-xl p-5 flex flex-col justify-between" style={{ borderTop: "2px solid #00ff88" }}>
                  <div className="text-[10px] font-black tracking-widest text-[#666] uppercase mb-3">Uptime General</div>
                  <div>
                    <div className="text-3xl font-black text-[#00ff88] [text-shadow:0_0_15px_rgba(0,255,136,0.5)]">99.9<span className="text-lg">%</span></div>
                    <div className="text-[11px] text-gray-400 mt-2 flex items-center gap-1">
                      <span className="text-white">↑</span> Últimos 30 días
                    </div>
                  </div>
                </div>

                {/* CPU */}
                <div className="bg-[#0a0a0c] border border-[rgba(0,195,255,0.15)] rounded-xl p-5 flex flex-col justify-between" style={{ borderTop: "2px solid #00c3ff" }}>
                  <div className="text-[10px] font-black tracking-widest text-[#666] uppercase mb-3">CPU Promedio</div>
                  <div>
                    <div className="text-3xl font-black text-[#00c3ff] [text-shadow:0_0_15px_rgba(0,195,255,0.5)]">
                      {hostings.length ? (hostings.reduce((acc, h) => acc + parseFloat(h.metrics?.cpu || 0), 0) / hostings.length).toFixed(1) : "0"}<span className="text-lg">%</span>
                    </div>
                    <div className="w-16 h-1 bg-[#00c3ff] rounded-full mt-3 shadow-[0_0_8px_rgba(0,195,255,0.8)]"></div>
                  </div>
                </div>

                {/* RAM */}
                <div className="bg-[#0a0a0c] border border-[rgba(255,170,0,0.15)] rounded-xl p-5 flex flex-col justify-between" style={{ borderTop: "2px solid #ffaa00" }}>
                  <div className="text-[10px] font-black tracking-widest text-[#666] uppercase mb-3">RAM Usada</div>
                  <div>
                    <div className="text-3xl font-black text-[#ffaa00] [text-shadow:0_0_15px_rgba(255,170,0,0.5)]">
                      {(() => {
                        let totalMiB = hostings.reduce((acc, h) => {
                          const memStr = h.metrics?.memory || "0MiB";
                          const val = parseFloat(memStr);
                          return acc + (isNaN(val) ? 0 : (memStr.includes('GiB') ? val * 1024 : val));
                        }, 0);
                        return totalMiB > 1024 ? (totalMiB / 1024).toFixed(1) + " GB" : totalMiB.toFixed(1) + " MB";
                      })()}
                    </div>
                    <div className="text-[11px] text-gray-400 mt-2">Medición en tiempo real</div>
                  </div>
                </div>

                {/* ALMACENAMIENTO */}
                <div className="bg-[#0a0a0c] border border-[rgba(166,0,255,0.15)] rounded-xl p-5 flex flex-col justify-between" style={{ borderTop: "2px solid #a600ff" }}>
                  <div className="text-[10px] font-black tracking-widest text-[#666] uppercase mb-3">Almacenamiento</div>
                  <div>
                    <div className="text-3xl font-black text-[#a600ff] [text-shadow:0_0_15px_rgba(166,0,255,0.5)]">
                      18<span className="text-lg font-bold text-gray-300"> GB</span>
                    </div>
                  </div>
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
                                  {/* Botón Archivos — solo para ZIP upload y GitHub (no WordPress) */}
                                  {!h.container_name?.includes('_wp_') && (
                                    <button
                                      onClick={() => { setSelectedFilesHosting(h); setShowFiles(true); }}
                                      title="Gestor de archivos"
                                      className="w-8 h-8 rounded-lg bg-white/5 text-muted hover:bg-blue-500/20 hover:text-blue-400 flex items-center justify-center transition-all"
                                    >
                                      <FolderOpen className="w-3.5 h-3.5" />
                                    </button>
                                  )}
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

                              {!isSupportSession && (
                                <button
                                  onClick={() => handleDelete(h.hosting_id, h.name)}
                                  title="Eliminar"
                                  className="w-8 h-8 rounded-lg bg-danger/10 text-danger flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all hover:bg-danger hover:text-white"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              )}
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

      {showFiles && selectedFilesHosting && (
        <MonacoFileEditor
          hosting={selectedFilesHosting}
          readOnly={false}
          onClose={() => { setShowFiles(false); setSelectedFilesHosting(null); }}
        />
      )}

      {/* ── CUSTOM ERROR TOAST (STITCH DESIGN) ── */}
      {errorToast && (
        <div style={{
          position: 'fixed',
          top: 24,
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '16px 24px',
          background: 'rgba(10, 10, 12, 0.95)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(255, 68, 68, 0.4)',
          borderRadius: 16,
          boxShadow: '0 16px 40px rgba(255, 0, 0, 0.2), 0 0 0 1px rgba(255,68,68,0.1) inset',
          color: '#fff',
          animation: 'toastSlideDown 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards',
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 32, height: 32, borderRadius: '50%',
            background: 'rgba(255, 68, 68, 0.1)', color: '#ff4444'
          }}>
            <AlertTriangle size={16} />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#ff4444', marginBottom: 2 }}>
              Acción Bloqueada
            </div>
            <div style={{ fontSize: 13, color: '#aaa', lineHeight: 1.4, maxWidth: 320 }}>
              {errorToast}
            </div>
          </div>
          <button 
            onClick={() => setErrorToast(null)}
            style={{ 
              background: 'none', border: 'none', color: '#666', 
              cursor: 'pointer', padding: 4, marginLeft: 8 
            }}
          >
            <X size={16} />
          </button>
          <style>{`
            @keyframes toastSlideDown {
              from { opacity: 0; transform: translate(-50%, -20px) scale(0.9); }
              to { opacity: 1; transform: translate(-50%, 0) scale(1); }
            }
          `}</style>
        </div>
      )}
    </div>
    {/* ── BOTÓN FLOTANTE + MODAL ───────────── se inyectan aquí sin romper el Fragment */}

    {/* ── BOTÓN FLOTANTE DE SOPORTE ───────────────────────────── */}
    {!showSupport && (
      <button
        id="support-chat-bubble"
        onClick={() => { setShowSupport(true); setSupportView('chat'); setOpenTicketId(null); }}
        style={{
          position: 'fixed', bottom: '1.75rem', right: '1.75rem', zIndex: 999,
          width: 52, height: 52, borderRadius: '50%', border: 'none',
          background: 'linear-gradient(135deg, #00ff88, #00cc70)',
          cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 8px 32px rgba(0,255,136,0.4)', transition: 'all 0.2s ease',
        }}
        onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.1)'; }}
        onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; }}
        title="Abrir soporte"
      >
        <Headset size={22} color="#000" />
      </button>
    )}

    {/* ── MODAL DE DIAGNOSTICO AI ────────────────────────────────────── */}
    {showDiagnosis && (
      <div style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '1.5rem',
      }}>
        <div style={{
          width: 500, maxWidth: '100%', background: '#0a0a0c',
          border: '1px solid rgba(166,0,255,0.2)', borderRadius: '1.5rem',
          boxShadow: '0 0 40px rgba(166,0,255,0.1)', overflow: 'hidden'
        }}>
          <div style={{
            padding: '1.25rem', borderBottom: '1px solid rgba(255,255,255,0.05)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            background: 'linear-gradient(90deg, rgba(166,0,255,0.1), transparent)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{
                width: 32, height: 32, borderRadius: '0.75rem',
                background: 'rgba(166,0,255,0.2)', color: '#d088ff',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}>
                <Bot size={18} />
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', letterSpacing: '0.5px' }}>AI DEBUG ENGINE</div>
                <div style={{ fontSize: 11, color: '#888' }}>{diagnosisData?.hostingName || 'Analizando...'}</div>
              </div>
            </div>
            <button onClick={() => setShowDiagnosis(false)} style={{
              background: 'rgba(255,255,255,0.05)', border: 'none', borderRadius: '50%',
              width: 28, height: 28, cursor: 'pointer', color: '#888',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <X size={14} />
            </button>
          </div>
          
          <div style={{ padding: '1.5rem', minHeight: 150, display: 'flex', flexDirection: 'column' }}>
            {diagnosisLoading ? (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1rem', color: '#a600ff' }}>
                <Loader className="animate-spin" size={32} />
                <span style={{ fontSize: 12, fontWeight: 600, color: '#888', letterSpacing: '1px' }}>ESCANENADO LOGS Y MÉTRICAS...</span>
              </div>
            ) : diagnosisData ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                <div style={{ display: 'flex', gap: '1rem' }}>
                  <div style={{ flex: 1, background: '#111', padding: '0.75rem', borderRadius: '0.75rem', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ fontSize: 10, color: '#666', fontWeight: 800, uppercase: true, marginBottom: '0.25rem' }}>STATUS</div>
                    <div style={{ fontSize: 13, color: diagnosisData.status === 'running' ? '#00ff88' : '#ff4444', fontWeight: 600 }}>{diagnosisData.status.toUpperCase()}</div>
                  </div>
                  <div style={{ flex: 1, background: '#111', padding: '0.75rem', borderRadius: '0.75rem', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ fontSize: 10, color: '#666', fontWeight: 800, uppercase: true, marginBottom: '0.25rem' }}>CPU / RAM</div>
                    <div style={{ fontSize: 13, color: '#fff', fontFamily: 'monospace' }}>{diagnosisData.metrics.cpu} / {diagnosisData.metrics.memory}</div>
                  </div>
                </div>
                
                {diagnosisData.has_hard_errors && (
                  <div style={{ background: 'rgba(255,68,68,0.1)', border: '1px solid rgba(255,68,68,0.2)', padding: '0.75rem', borderRadius: '0.75rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                    <AlertTriangle color="#ff4444" size={20} />
                    <span style={{ fontSize: 12, color: '#ff4444', fontWeight: 600 }}>Se detectaron errores en el código (Logs)</span>
                  </div>
                )}
                
                {/* REPORTE DINÁMICO SEGÚN SEVERIDAD */}
                {(() => {
                  const severity = diagnosisData.diagnosis?.severity || 'ok';
                  const colors = {
                    critical: { bg: 'rgba(255,68,68,0.05)', border: 'rgba(255,68,68,0.2)', text: '#ff4444' },
                    warning: { bg: 'rgba(255,170,0,0.05)', border: 'rgba(255,170,0,0.2)', text: '#ffaa00' },
                    ok: { bg: 'rgba(0,255,136,0.05)', border: 'rgba(0,255,136,0.1)', text: '#00ff88' }
                  }[severity] || { bg: 'rgba(166,0,255,0.05)', border: 'rgba(166,0,255,0.1)', text: '#a600ff' };

                  return (
                    <div style={{ background: colors.bg, borderRadius: '1rem', padding: '1.25rem', border: `1px solid ${colors.border}`, display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                         <div style={{ width: 8, height: 8, borderRadius: '50%', background: colors.text, boxShadow: `0 0 10px ${colors.text}` }} />
                         <div style={{ fontSize: 10, color: colors.text, fontWeight: 800, letterSpacing: '1px' }}>
                           ANÁLISIS DEL ASESOR ({severity.toUpperCase()}):
                         </div>
                      </div>
                      <div style={{ fontSize: 13, color: '#ddd', lineHeight: 1.6 }}>
                        {diagnosisData.diagnosis?.llm_explanation || diagnosisData.diagnosis?.summary || "No se detectaron problemas evidentes."}
                      </div>
                      {diagnosisData.diagnosis?.recommendation && (
                        <div style={{ fontSize: 11, color: '#888', fontStyle: 'italic', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '0.5rem' }}>
                          💡 {diagnosisData.diagnosis.recommendation}
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* DEBUG TÉCNICO SECTION */}
                <div style={{ marginTop: '0.5rem', borderTop: '1px dashed rgba(255,255,255,0.1)', pt: '1rem' }}>
                    <div style={{ fontSize: 10, color: '#555', fontWeight: 800, letterSpacing: '1px', marginBottom: '0.75rem' }}>🔍 DEBUG TÉCNICO (ADMIN):</div>
                    
                    {diagnosisData.debug_info?.parsed_errors?.length > 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
                            {diagnosisData.debug_info.parsed_errors.map((err, i) => {
                                const isCritical = err.severity === 'critical';
                                const color = isCritical ? '#ff4444' : '#ffaa00';
                                return (
                                    <div key={i} style={{ 
                                        fontSize: 11, fontAttributes: 'monospace', color: color, 
                                        background: isCritical ? 'rgba(255,68,68,0.05)' : 'rgba(255,170,0,0.05)', 
                                        padding: '0.5rem', borderRadius: '0.5rem', border: `1px solid ${isCritical ? 'rgba(255,68,68,0.1)' : 'rgba(255,170,0,0.1)'}` 
                                    }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                            <span style={{ fontWeight: 800 }}>[{err.type.toUpperCase()}]</span>
                                            <span style={{ fontSize: 9, opacity: 0.6 }}>{err.severity.toUpperCase()}</span>
                                        </div>
                                        <div style={{ marginTop: '2px' }}>{err.file} {err.line > 0 && `(Línea ${err.line})`}</div>
                                        <div style={{ color: '#aaa', marginTop: '2px', fontSize: 10 }}>{err.message}</div>
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <div style={{ fontSize: 11, color: '#444', marginBottom: '1rem' }}>No se encontraron patrones de error conocidos en los logs.</div>
                    )}

                    <div style={{ fontSize: 10, color: '#444', marginBottom: '0.25rem' }}>SNIPPET DE LOGS RECIENTES:</div>
                    <pre style={{ 
                        fontSize: '9px', fontAttributes: 'monospace', color: '#666', background: '#050505', 
                        padding: '0.75rem', borderRadius: '0.5rem', overflowX: 'auto', maxHeight: '100px',
                        border: '1px solid rgba(255,255,255,0.03)'
                    }}>
                        {diagnosisData.debug_info?.raw_snippet || 'Sin logs disponibles.'}
                    </pre>
                </div>
              </div>
            ) : (
               <div style={{ color: '#888', textAlign: 'center', marginTop: '2rem' }}>Error al cargar datos.</div>
            )}
          </div>
        </div>
      </div>
    )}

    {/* ── MODAL DE SOPORTE ────────────────────────────────────── */}
    {showSupport && (
      supportView === 'history' && !openTicketId ? (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)',
          display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end',
          padding: '1.5rem',
        }} onClick={(e) => e.target === e.currentTarget && setShowSupport(false)}>
          <div style={{
            width: 460, maxHeight: '80vh', background: '#0d0d0d',
            border: '1px solid rgba(255,255,255,0.08)', borderRadius: '1.5rem',
            overflow: 'hidden', display: 'flex', flexDirection: 'column',
            boxShadow: '0 24px 80px rgba(0,0,0,0.8)',
          }}>
            <div style={{
              padding: '1rem 1.25rem', borderBottom: '1px solid rgba(255,255,255,0.06)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>Historial de Soporte</div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button onClick={() => { setSupportView('chat'); setOpenTicketId(null); }} style={{
                  fontSize: 11, padding: '0.3rem 0.75rem', borderRadius: '0.5rem',
                  background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.2)',
                  color: '#00ff88', cursor: 'pointer',
                }}>+ Nuevo ticket</button>
                <button onClick={() => setShowSupport(false)} style={{
                  background: 'rgba(255,255,255,0.06)', border: 'none', borderRadius: '50%',
                  width: 28, height: 28, cursor: 'pointer', color: '#888',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}><X size={14} /></button>
              </div>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '1rem' }}>
              <SupportTicketList onOpenTicket={(id) => { setOpenTicketId(id); setSupportView('chat'); }} />
            </div>
          </div>
        </div>
      ) : (
        <SupportChat
          onClose={() => setShowSupport(false)}
          initialTicketId={openTicketId}
        />
      )
    )}
  </>
  );
};

export default Dashboard;
