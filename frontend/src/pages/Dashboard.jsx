import { useState, useMemo, lazy, Suspense } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { updateUserConfig, topupBalance, resendVerification } from '../services/api';
import { useAuth }                   from '../hooks/useAuth';
import { useHeartbeat }              from '../hooks/useHeartbeat';
import { useDashboardData }          from '../hooks/useDashboardData';
import { useHostingActions }         from '../hooks/useHostingActions';
import { useHostingLogs }            from '../hooks/useHostingLogs';
import { useHostingDiagnostics }     from '../hooks/useHostingDiagnostics';
import { useInfrastructureMetrics }  from '../hooks/useInfrastructureMetrics';
import { useAIAdvisory }             from '../hooks/useAIAdvisory';
import {
  Globe, Loader, RefreshCw, ShieldCheck, Activity,
  Database, Zap, CreditCard, Settings,
  Key, Lock, Mail, BarChart3, Headset,
  ChevronLeft, ChevronRight, Bot, X, AlertTriangle, Bell, Search, GitBranch,
} from 'lucide-react';
import NotificationsPage           from './Notifications';
import '../Dashboard.css';
import HostingList          from '../components/dashboard/HostingList';
import ActivityFeed         from '../components/dashboard/ActivityFeed';
import TrendLine            from '../components/dashboard/TrendLine';
import AIAdvisoryPanel      from '../components/dashboard/AIAdvisoryPanel';
import StatusCommandBar     from '../components/dashboard/StatusCommandBar';
import HostingCreationForm  from '../components/HostingCreationForm';
import LogsModal            from '../components/LogsModal';
import ZipUploadModal       from '../components/ZipUploadModal';
import PixelAnalytics       from '../components/PixelAnalytics';
import AdminDashboard       from './AdminDashboard';
import MonacoFileEditor     from '../components/MonacoFileEditor';
import SupportBanner        from '../components/SupportBanner';
import SupportChat          from '../components/SupportChat';
import SupportTicketList    from '../components/SupportTicketList';
import SiteManagement       from '../components/SiteManagement';
import AIAdvisoryPage       from './AIAdvisory';
import ImportSiteModal      from '../components/dashboard/ImportSiteModal';
import DomainsSection       from '../components/dashboard/sections/DomainsSection';
import BackupsSection       from '../components/dashboard/sections/BackupsSection';
import SSLSection           from '../components/dashboard/sections/SSLSection';
import EmailSection         from '../components/dashboard/sections/EmailSection';
import BillingSection       from '../components/dashboard/sections/BillingSection';
import ConfigSection        from '../components/dashboard/sections/ConfigSection';
import DeployHistorySection from '../components/dashboard/sections/DeployHistorySection';
import NotificationBell    from '../components/dashboard/NotificationBell';
import DashboardOverview   from '../components/dashboard/DashboardOverview';
const BusinessOverview = lazy(() => import('../components/dashboard/BusinessOverview'));

const Dashboard = () => {
  const { user, logoutAction, setUser, isSupportSession, supportSession, deactivateSupportSession } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // ── Presence heartbeat — runs for both regular users and admins ─────────────
  useHeartbeat(location.pathname);

  // ── Active view (derived from URL) ──────────────────────────────────────────
  const activeView = location.pathname === '/pixel'    ? 'pixel'
                   : location.pathname === '/admin'    ? 'admin'
                   : location.pathname === '/sites'    ? 'sites'
                   : location.pathname === '/advisory' ? 'advisory'
                   : 'dashboard';

  // ── Data hooks ───────────────────────────────────────────────────────────────
  const {
    hostings, healthData, healthHistory, alerts, events,
    loading, refresh,
  } = useDashboardData();

  const {
    selectedHosting, logs, loading: logsLoading,
    openLogs, refreshLogs,
  } = useHostingLogs();

  const {
    diagnose, data: diagnosisData, loading: diagnosisLoading, reset: resetDiagnosis,
  } = useHostingDiagnostics(hostings);

  const { avgHealthScore, avgCpu, totalRam, healthTrend, unresolved } =
    useInfrastructureMetrics(hostings, healthData, healthHistory, alerts);

  const advisories = useAIAdvisory(hostings, healthData, alerts);

  // ── Derived (UI-level only — no business logic) ──────────────────────────────
  const expiringHostings = useMemo(
    () => hostings.filter(h => h.plan === 'free' && h.expires_in_days != null && h.expires_in_days >= 0 && h.expires_in_days <= 3),
    [hostings],
  );

  const primaryHosting = useMemo(
    () => hostings.find(h => h.is_primary) ?? hostings[0] ?? null,
    [hostings],
  );
  const primaryHostingHistory = primaryHosting ? healthHistory[primaryHosting.hosting_id] : null;

  // ── Hosting mutations (React Query) ─────────────────────────────────────────
  const { start, stop, restart, remove } = useHostingActions();

  // Derived per-row loading id — whichever mutation is in-flight owns the spinner
  const activeHostingActionId =
    (start.isPending   && start.variables)   ||
    (stop.isPending    && stop.variables)    ||
    (restart.isPending && restart.variables) ||
    (remove.isPending  && remove.variables)  ||
    null;

  // ── UI state ─────────────────────────────────────────────────────────────────
  const [userActionLoading,     setUserActionLoading]     = useState(false); // autoscale / topup
  const [showCreate,            setShowCreate]            = useState(false);
  const [showLogs,              setShowLogs]              = useState(false);
  const [showUpload,            setShowUpload]            = useState(false);
  const [selectedUploadHosting, setSelectedUploadHosting] = useState(null);
  const [importModal,           setImportModal]           = useState(null);
  const [showFiles,             setShowFiles]             = useState(false);
  const [selectedFilesHosting,  setSelectedFilesHosting]  = useState(null);
  const [isSidebarCollapsed,    setIsSidebarCollapsed]    = useState(false);
  const [sidebarSection,        setSidebarSection]        = useState(null); // 'domains'|'backups'|'ssl'|'email'|'billing'|'config'
  const [dangerHostingId,       setDangerHostingId]       = useState('');
  const [showSupport,           setShowSupport]           = useState(false);
  const [supportView,           setSupportView]           = useState('chat');
  const [openTicketId,          setOpenTicketId]          = useState(null);
  const [showDiagnosis,         setShowDiagnosis]         = useState(false);
  const [errorToast,            setErrorToast]            = useState(null);
  const [resendingVerif,        setResendingVerif]        = useState(false);
  const [verifSent,             setVerifSent]             = useState(false);

  // ── Event handlers ────────────────────────────────────────────────────────────
  const showError = (msg) => {
    setErrorToast(msg);
    setTimeout(() => setErrorToast(null), 5000);
  };

  const handleOpenLogs = (hosting) => { openLogs(hosting); setShowLogs(true); };

  const handleDelete = (id) => {
    setDangerHostingId(String(id));
    setSidebarSection('config');
    navigate('/dashboard');
  };

  const handleDiagnose = async (id) => {
    setShowDiagnosis(true);
    await diagnose(id);
    refresh();
  };

  // Optimistic autoscale toggle: update UI instantly, roll back on error
  const handleToggleAutoscale = async () => {
    if (userActionLoading) return;
    const newValue = !user?.autoscale_enabled;
    setUser(prev => ({ ...prev, autoscale_enabled: newValue })); // optimistic
    setUserActionLoading(true);
    try {
      await updateUserConfig({ autoscale_enabled: newValue });
    } catch (err) {
      setUser(prev => ({ ...prev, autoscale_enabled: !newValue })); // rollback
      showError(err.response?.data?.detail || 'Error al actualizar la configuración.');
    } finally {
      setUserActionLoading(false);
    }
  };

  const handleTopup = async () => {
    if (userActionLoading) return;
    setUserActionLoading(true);
    try {
      const res = await topupBalance(10);
      setUser(prev => ({ ...prev, balance: res.balance }));
    } catch (err) { showError(err.response?.data?.detail || 'Error al recargar el saldo.'); }
    finally { setUserActionLoading(false); }
  };

  const handleResendVerif = async () => {
    if (resendingVerif || verifSent || !user?.email) return;
    setResendingVerif(true);
    try { await resendVerification(user.email); setVerifSent(true); }
    catch (_) { setVerifSent(true); } // silent — same message regardless
    finally { setResendingVerif(false); }
  };

  // ── Admin shortcut ────────────────────────────────────────────────────────────
  if (user?.role === 'admin') return <AdminDashboard />;

  const showVerifBanner = user && user.email_verified === false;
  const bannerHeight = (isSupportSession && supportSession ? 44 : 0) + (showVerifBanner ? 44 : 0);

  return (
    <>
      {showVerifBanner && (
        <div className="fixed top-0 left-0 right-0 z-[59] h-11 flex items-center justify-center gap-3 px-4 bg-amber-500/10 border-b border-amber-500/20"
          style={isSupportSession && supportSession ? { top: 44 } : undefined}>
          <Mail className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <span className="text-amber-300 text-xs">Verificá tu email para poder crear hostings.</span>
          <button onClick={handleResendVerif} disabled={resendingVerif || verifSent}
            className="text-[11px] font-bold text-amber-400 hover:text-amber-300 underline disabled:opacity-50 transition-colors">
            {verifSent ? 'Enviado' : resendingVerif ? 'Enviando...' : 'Reenviar email'}
          </button>
        </div>
      )}

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
        className={`dashboard-container fixed inset-0 z-50 overflow-hidden bg-[#0a0a0c] ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}
        style={bannerHeight ? { top: bannerHeight } : undefined}
      >
        {/* ── SIDEBAR ── */}
        <aside className="sidebar bg-[#121214] border-r border-white/10">
          <div className="logo-dash">
            <div className="logo-icon-dash text-white"><ShieldCheck className="w-5 h-5" /></div>
            {!isSidebarCollapsed && (
              <div className="flex-1 opacity-fadeIn">
                <div className="logo-text-dash">HostingGuard</div>
                <div className="text-[10px] text-accent font-mono tracking-widest">.LAT</div>
              </div>
            )}
            <button onClick={() => setIsSidebarCollapsed(v => !v)} className="sidebar-toggle-btn">
              {isSidebarCollapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
            </button>
          </div>

          <nav className="nav-dash">
            <div className="nav-label-dash">{isSidebarCollapsed ? '•' : 'Principal'}</div>
            <div className={`nav-item-dash ${activeView === 'dashboard' && !showCreate && !sidebarSection ? 'active' : ''}`} onClick={() => { setShowCreate(false); setSidebarSection(null); navigate('/dashboard'); }}>
              <div className="nav-icon-dash icon-green"><Activity size={18} /></div>
              {!isSidebarCollapsed && <span>Dashboard</span>}
            </div>
            <div className={`nav-item-dash ${activeView === 'sites' ? 'active' : ''}`} onClick={() => { setShowCreate(false); setSidebarSection(null); navigate('/sites'); }}>
              <div className="nav-icon-dash icon-blue"><Globe size={18} /></div>
              {!isSidebarCollapsed && <span>Mis Sitios</span>}
            </div>
            <div className={`nav-item-dash ${activeView === 'pixel' ? 'active' : ''}`} onClick={() => { setShowCreate(false); setSidebarSection(null); navigate('/pixel'); }}>
              <div className="nav-icon-dash icon-multi"><BarChart3 size={18} /></div>
              {!isSidebarCollapsed && <span>Pixel Analytics</span>}
            </div>
            <div className={`nav-item-dash ${activeView === 'advisory' ? 'active' : ''}`} onClick={() => { setShowCreate(false); setSidebarSection(null); navigate('/advisory'); }}>
              <div className="nav-icon-dash icon-ia"><Bot size={18} /></div>
              {!isSidebarCollapsed && <span>IA Advisory</span>}
              {!isSidebarCollapsed && advisories.filter(a => a.requiresAttention).length > 0 && (
                <span className={`ml-auto text-[9px] px-1.5 py-0.5 rounded-full ${
                  advisories.some(a => a.severity === 'critical')
                    ? 'bg-danger/20 text-danger'
                    : 'bg-warn/20 text-warn'
                }`}>
                  {advisories.filter(a => a.requiresAttention).length}
                </span>
              )}
            </div>
            {user?.role === 'admin' && (
              <div className={`nav-item-dash ${activeView === 'admin' ? 'active' : ''}`} onClick={() => { setShowCreate(false); setSidebarSection(null); navigate('/admin'); }}>
                <div className="nav-icon-dash icon-orange"><ShieldCheck size={18} /></div>
                {!isSidebarCollapsed && <span>Admin Panel</span>}
              </div>
            )}

            <div className="nav-label-dash">{isSidebarCollapsed ? '•' : 'Gestión'}</div>
            <div className={`nav-item-dash ${sidebarSection === 'domains' ? 'active' : ''}`} onClick={() => { setSidebarSection('domains'); setShowCreate(false); navigate('/dashboard'); }}>
              <div className="nav-icon-dash icon-gold"><Key size={18} /></div>
              {!isSidebarCollapsed && <span>Dominios</span>}
            </div>
            <div className={`nav-item-dash ${sidebarSection === 'backups' ? 'active' : ''}`} onClick={() => { setSidebarSection('backups'); setShowCreate(false); navigate('/dashboard'); }}>
              <div className="nav-icon-dash icon-purple"><Database size={18} /></div>
              {!isSidebarCollapsed && <span>Backups</span>}
            </div>
            <div className={`nav-item-dash ${sidebarSection === 'ssl' ? 'active' : ''}`} onClick={() => { setSidebarSection('ssl'); setShowCreate(false); navigate('/dashboard'); }}>
              <div className="nav-icon-dash icon-orange"><Lock size={18} /></div>
              {!isSidebarCollapsed && <span>SSL</span>}
            </div>
            <div className={`nav-item-dash ${sidebarSection === 'email' ? 'active' : ''}`} onClick={() => { setSidebarSection('email'); setShowCreate(false); navigate('/dashboard'); }}>
              <div className="nav-icon-dash icon-blue"><Mail size={18} /></div>
              {!isSidebarCollapsed && <span>Email</span>}
            </div>

            <div className={`nav-item-dash ${sidebarSection === 'deploys' ? 'active' : ''}`} onClick={() => { setSidebarSection('deploys'); setShowCreate(false); navigate('/dashboard'); }}>
              <div className="nav-icon-dash" style={{ color: '#34d399' }}><GitBranch size={18} /></div>
              {!isSidebarCollapsed && <span>Historial deploys</span>}
            </div>

            <div className="nav-label-dash">{isSidebarCollapsed ? '•' : 'Cuenta'}</div>
            <div className={`nav-item-dash ${sidebarSection === 'notifications' ? 'active' : ''}`} onClick={() => { setSidebarSection('notifications'); setShowCreate(false); navigate('/dashboard'); }}>
              <div className="nav-icon-dash" style={{ color: '#60a5fa' }}><Bell size={18} /></div>
              {!isSidebarCollapsed && <span>Notificaciones</span>}
            </div>
            <div className="nav-item-dash" onClick={() => { setShowSupport(true); setSupportView('history'); setOpenTicketId(null); }}>
              <div className="nav-icon-dash" style={{ color: '#818cf8' }}><Headset size={18} /></div>
              {!isSidebarCollapsed && <span>Soporte</span>}
            </div>
            <div className={`nav-item-dash ${sidebarSection === 'billing' ? 'active' : ''}`} onClick={() => { setSidebarSection('billing'); setShowCreate(false); navigate('/dashboard'); }}>
              <div className="nav-icon-dash icon-blue"><CreditCard size={18} /></div>
              {!isSidebarCollapsed && <span>Facturación</span>}
            </div>
            <div className={`nav-item-dash ${sidebarSection === 'config' ? 'active' : ''}`} onClick={() => { setSidebarSection('config'); setShowCreate(false); navigate('/dashboard'); }}>
              <div className="nav-icon-dash"><Settings size={18} /></div>
              {!isSidebarCollapsed && <span>Configuración</span>}
            </div>
          </nav>

          <div className="p-4 border-t border-[var(--border)] mt-auto">
            <div className={`flex items-center gap-3 p-3 bg-[var(--surface2)] border border-[var(--border)] rounded-xl shadow-sm ${isSidebarCollapsed ? 'justify-center p-2' : ''}`}>
              <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-bold text-xs uppercase shrink-0">
                {user?.email?.[0] || 'U'}
              </div>
              {!isSidebarCollapsed && (
                <div className="flex-1 min-w-0 opacity-fadeIn">
                  <div className="text-[11px] font-bold text-white truncate">{user?.email}</div>
                  <div className="text-[9px] text-[var(--accent)] font-mono uppercase font-bold tracking-wide">Plan {user?.plan || 'Free'}</div>
                </div>
              )}
              {!isSidebarCollapsed && (
                <button onClick={logoutAction} className="text-muted hover:text-danger"><RefreshCw className="w-3.5 h-3.5" /></button>
              )}
            </div>
            {isSidebarCollapsed && (
              <button onClick={logoutAction} className="mt-2 w-full flex justify-center text-muted hover:text-danger"><RefreshCw className="w-4 h-4" /></button>
            )}
          </div>
        </aside>

        {/* ── MAIN ── */}
        <main className="main-dash">
          <div className="topbar-dash">
            {/* Dashboard overview: breadcrumb + search */}
            {activeView === 'dashboard' && !showCreate && !sidebarSection ? (
              <>
                <div className="flex items-center gap-2 text-[13px] text-white/40 shrink-0">
                  <span className="text-white/25">{user?.email?.split('@')[0] ?? 'cuenta'}</span>
                  <ChevronRight size={12} className="text-white/20" />
                  <span className="text-white/80 font-medium">Dashboard</span>
                </div>
                <div className="hidden md:flex flex-1 max-w-xs mx-4 items-center gap-2 bg-[#131313] border border-[#1f1f1f] rounded-lg px-3 py-1.5 text-[12px] text-white/30 cursor-text">
                  <Search size={13} className="shrink-0 text-white/25" />
                  <span>Buscar sitios, dominios, métricas…</span>
                  <span className="ml-auto text-[10px] font-mono px-1.5 py-0.5 border border-[#2a2a2a] rounded text-white/20">⌘K</span>
                </div>
              </>
            ) : (
              <div className="text-[15px] font-medium flex-1">
                {showCreate ? 'Nuevo Proyecto'
                  : sidebarSection === 'domains'  ? 'Dominios'
                  : sidebarSection === 'backups'  ? 'Backups'
                  : sidebarSection === 'ssl'      ? 'SSL / HTTPS'
                  : sidebarSection === 'email'    ? 'Email / SMTP'
                  : sidebarSection === 'billing'        ? 'Facturación'
                  : sidebarSection === 'notifications'  ? 'Notificaciones'
                  : sidebarSection === 'config'         ? 'Configuración'
                  : activeView === 'pixel'    ? 'Pixel Analytics'
                  : activeView === 'admin'    ? 'Panel de Administración'
                  : activeView === 'sites'    ? 'Mis Sitios (Operaciones)'
                  : activeView === 'advisory' ? 'AI Advisory Center'
                  : 'Dashboard Overview'}
              </div>
            )}
            <div className="hidden md:flex items-center gap-2 bg-emerald-500/10 text-emerald-400 px-3 py-1.5 rounded-full border border-emerald-500/20 text-xs font-medium shrink-0">
              <div className="pulse-dash" /> Servicios Operativos
            </div>
            {activeView !== 'admin' && !sidebarSection && (
              <button
                onClick={() => {
                  if (showCreate) { setShowCreate(false); }
                  else { navigate(activeView === 'sites' ? '/sites' : '/dashboard'); setShowCreate(true); }
                }}
                className="px-3 py-2 text-sm font-medium rounded-lg border border-white/10 bg-[#121214] hover:bg-white/5 transition shrink-0"
              >
                {showCreate ? 'Volver' : '+ Nuevo sitio'}
              </button>
            )}
            <NotificationBell />
            {!sidebarSection && (
              <button
                onClick={() => { setSidebarSection('billing'); setShowCreate(false); navigate('/dashboard'); }}
                className="btn-dash btn-primary-dash shrink-0"
              >
                Mejorar plan
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto bg-[#0a0a0a]" style={{ padding: activeView === 'dashboard' && !showCreate && !sidebarSection ? 0 : undefined }}>
            {showCreate ? (
              <div className="max-w-4xl mx-auto">
                <HostingCreationForm onSuccess={() => { setShowCreate(false); refresh(); }} />
              </div>
            ) : activeView === 'pixel' ? (
              <PixelAnalytics />
            ) : activeView === 'advisory' ? (
              <AIAdvisoryPage onDiagnose={handleDiagnose} />
            ) : activeView === 'admin' ? (
              <AdminDashboard />
            ) : activeView === 'sites' ? (
              <SiteManagement
                hostings={hostings}
                loading={loading}
                healthData={healthData}
                onRefresh={refresh}
                onAction={(id, action) => {
                  if (action === 'start')   handleAction(id, startHosting);
                  else if (action === 'stop')    handleAction(id, stopHosting);
                  else if (action === 'restart') handleAction(id, restartHosting);
                }}
                onOpenLogs={handleOpenLogs}
                onDelete={handleDelete}
                onUploadZip={(h) => { setSelectedUploadHosting(h); setShowUpload(true); }}
                onOpenFiles={(h) => { setSelectedFilesHosting(h); setShowFiles(true); }}
                onImportBackup={(h) => setImportModal(h)}
                onDiagnose={handleDiagnose}
              />
            ) : sidebarSection ? (
              <div style={{ paddingBottom: '3rem' }}>
                {sidebarSection === 'domains'        && <DomainsSection hostings={hostings} />}
                {sidebarSection === 'backups'        && <BackupsSection hostings={hostings} />}
                {sidebarSection === 'ssl'            && <SSLSection hostings={hostings} />}
                {sidebarSection === 'email'          && <EmailSection hostings={hostings} />}
                {sidebarSection === 'notifications'  && <NotificationsPage embedded />}
                {sidebarSection === 'billing'  && (
                  <BillingSection
                    user={user}
                    onTopup={handleTopup}
                    onToggleAutoscale={handleToggleAutoscale}
                    userActionLoading={userActionLoading}
                  />
                )}
                {sidebarSection === 'config'   && (
                  <ConfigSection
                    user={user}
                    setUser={setUser}
                    hostings={hostings}
                    logoutAction={logoutAction}
                    initialDangerHostingId={dangerHostingId}
                    onHostingDeleted={() => { setDangerHostingId(''); refresh(); setSidebarSection(null); navigate('/sites'); }}
                  />
                )}
                {sidebarSection === 'deploys' && <DeployHistorySection />}
              </div>
            ) : (
              <DashboardOverview
                hostings={hostings}
                healthData={healthData}
                healthHistory={healthHistory}
                alerts={alerts}
                events={events}
                advisories={advisories}
                avgHealthScore={avgHealthScore}
                avgCpu={avgCpu}
                unresolved={unresolved}
                user={user}
                onTopup={handleTopup}
                onGoBilling={() => { setSidebarSection('billing'); setShowCreate(false); }}
                onRefresh={refresh}
                onOpenLogs={handleOpenLogs}
                onOpenFiles={(h) => { setSelectedFilesHosting(h); setShowFiles(true); }}
                onUpload={(h) => { setSelectedUploadHosting(h); setShowUpload(true); }}
                onRestart={(id) => restart.mutate(id)}
                userActionLoading={userActionLoading}
              />
            )}
          </div>
        </main>

        <LogsModal
          isOpen={showLogs}
          onClose={() => setShowLogs(false)}
          logs={logs}
          projectName={selectedHosting?.name}
          onRefresh={refreshLogs}
          loading={logsLoading}
        />

        <ZipUploadModal
          isOpen={showUpload}
          onClose={() => { setShowUpload(false); setSelectedUploadHosting(null); }}
          hosting={selectedUploadHosting}
        />

        {importModal && (
          <ImportSiteModal
            hosting={importModal}
            onClose={() => setImportModal(null)}
            onComplete={() => { setImportModal(null); refresh(); }}
          />
        )}

        {showFiles && selectedFilesHosting && (
          <MonacoFileEditor
            hosting={selectedFilesHosting}
            readOnly={false}
            onClose={() => { setShowFiles(false); setSelectedFilesHosting(null); }}
          />
        )}

        {/* ERROR TOAST */}
        {errorToast && (
          <div style={{ position: 'fixed', top: 24, left: '50%', transform: 'translateX(-50%)', zIndex: 9999, display: 'flex', alignItems: 'center', gap: 12, padding: '16px 24px', background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(12px)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 16, boxShadow: '0 10px 40px rgba(0,0,0,0.08)', color: '#111827', animation: 'toastSlideDown 0.3s cubic-bezier(0.175,0.885,0.32,1.275) forwards' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 32, height: 32, borderRadius: '50%', background: 'rgba(239,68,68,0.1)', color: '#ef4444' }}><AlertTriangle size={16} /></div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#ef4444', marginBottom: 2 }}>Acción Bloqueada</div>
              <div style={{ fontSize: 13, color: '#4b5563', lineHeight: 1.4, maxWidth: 320 }}>{errorToast}</div>
            </div>
            <button onClick={() => setErrorToast(null)} style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', padding: 4, marginLeft: 8 }}><X size={16} /></button>
            <style>{`@keyframes toastSlideDown { from { opacity:0; transform:translate(-50%,-20px) scale(0.9); } to { opacity:1; transform:translate(-50%,0) scale(1); } }`}</style>
          </div>
        )}
      </div>

      {/* FLOATING SUPPORT BUTTON */}
      {!showSupport && (
        <button
          id="support-chat-bubble"
          onClick={() => { setShowSupport(true); setSupportView('chat'); setOpenTicketId(null); }}
          style={{ position: 'fixed', bottom: '1.75rem', right: '1.75rem', zIndex: 999, width: 56, height: 56, borderRadius: '50%', border: 'none', background: 'linear-gradient(135deg,#6366f1,#8b5cf6)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 8px 24px rgba(99,102,241,0.3)', transition: 'all 0.2s ease' }}
          onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.05)'; }}
          onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; }}
          title="Abrir soporte"
        >
          <Headset size={24} color="#fff" />
        </button>
      )}

      {/* AI DIAGNOSIS MODAL */}
      {showDiagnosis && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(17,24,39,0.4)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1.5rem' }}>
          <div style={{ width: 640, maxWidth: '95%', maxHeight: '85vh', background: '#ffffff', border: '1px solid #e5e7eb', borderRadius: '1.5rem', boxShadow: '0 20px 40px rgba(0,0,0,0.1)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '1.25rem', borderBottom: '1px solid #f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'linear-gradient(90deg,rgba(139,92,246,0.05),transparent)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <div style={{ width: 32, height: 32, borderRadius: '0.75rem', background: 'rgba(139,92,246,0.1)', color: '#8b5cf6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Bot size={18} /></div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 800, color: '#111827', letterSpacing: '0.5px' }}>AI DEBUG ENGINE</div>
                  <div style={{ fontSize: 11, color: '#6b7280' }}>{diagnosisData?.hostingName || 'Analizando...'}</div>
                </div>
              </div>
              <button onClick={() => { setShowDiagnosis(false); resetDiagnosis(); }} style={{ background: '#f3f4f6', border: 'none', borderRadius: '50%', width: 28, height: 28, cursor: 'pointer', color: '#6b7280', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><X size={14} /></button>
            </div>
            <div style={{ padding: '1.5rem', flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', scrollbarWidth: 'thin', scrollbarColor: 'rgba(139,92,246,0.3) transparent' }}>
              {diagnosisLoading ? (
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1rem', color: '#8b5cf6' }}>
                  <Loader className="animate-spin" size={32} />
                  <span style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', letterSpacing: '1px' }}>ESCANEANDO LOGS Y MÉTRICAS...</span>
                </div>
              ) : diagnosisData ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <div style={{ display: 'flex', gap: '1rem' }}>
                    <div style={{ flex: 1, background: '#f9fafb', padding: '0.75rem', borderRadius: '0.75rem', border: '1px solid #f3f4f6' }}>
                      <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 800, marginBottom: '0.25rem' }}>STATUS</div>
                      <div style={{ fontSize: 13, color: diagnosisData.status === 'running' ? '#059669' : '#dc2626', fontWeight: 600 }}>{diagnosisData.status?.toUpperCase()}</div>
                    </div>
                    <div style={{ flex: 1, background: '#f9fafb', padding: '0.75rem', borderRadius: '0.75rem', border: '1px solid #f3f4f6' }}>
                      <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 800, marginBottom: '0.25rem' }}>CPU / RAM</div>
                      <div style={{ fontSize: 13, color: '#111827', fontFamily: 'monospace', fontWeight: 600 }}>{diagnosisData.metrics?.cpu} / {diagnosisData.metrics?.memory}</div>
                    </div>
                  </div>
                  {diagnosisData.has_hard_errors && (
                    <div style={{ background: 'rgba(239,68,68,0.05)', border: '1px solid rgba(239,68,68,0.2)', padding: '0.75rem', borderRadius: '0.75rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                      <AlertTriangle color="#ef4444" size={20} />
                      <span style={{ fontSize: 12, color: '#b91c1c', fontWeight: 600 }}>Se detectaron errores en el código (Logs)</span>
                    </div>
                  )}
                  {(() => {
                    const severity = diagnosisData.diagnosis?.severity || 'ok';
                    const colors = {
                      critical: { bg: 'rgba(239,68,68,0.05)',    border: 'rgba(239,68,68,0.2)',    text: '#dc2626' },
                      warning:  { bg: 'rgba(245,158,11,0.05)',   border: 'rgba(245,158,11,0.2)',   text: '#d97706' },
                      ok:       { bg: 'rgba(16,185,129,0.05)',   border: 'rgba(16,185,129,0.1)',   text: '#059669' },
                    }[severity] || { bg: 'rgba(139,92,246,0.05)', border: 'rgba(139,92,246,0.1)', text: '#7c3aed' };
                    return (
                      <div style={{ background: colors.bg, borderRadius: '1rem', padding: '1.25rem', border: `1px solid ${colors.border}`, display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <div style={{ width: 8, height: 8, borderRadius: '50%', background: colors.text, boxShadow: `0 0 10px ${colors.text}` }} />
                          <div style={{ fontSize: 10, color: colors.text, fontWeight: 800, letterSpacing: '1px' }}>ANÁLISIS DEL ASESOR ({severity.toUpperCase()}):</div>
                        </div>
                        <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.6 }}>
                          {diagnosisData.diagnosis?.llm_explanation || diagnosisData.diagnosis?.summary || 'No se detectaron problemas evidentes.'}
                        </div>
                        {diagnosisData.diagnosis?.recommendation && (
                          <div style={{ fontSize: 11, color: '#4b5563', fontStyle: 'italic', borderTop: '1px solid #e5e7eb', paddingTop: '0.5rem' }}>
                            💡 {diagnosisData.diagnosis.recommendation}
                          </div>
                        )}
                      </div>
                    );
                  })()}
                  <div style={{ marginTop: '0.5rem', borderTop: '1px dashed #e5e7eb', paddingTop: '1rem' }}>
                    <div style={{ fontSize: 10, color: '#6b7280', fontWeight: 800, letterSpacing: '1px', marginBottom: '0.75rem' }}>🔍 DEBUG TÉCNICO (ADMIN):</div>
                    {diagnosisData.debug_info?.parsed_errors?.length > 0 ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
                        {diagnosisData.debug_info.parsed_errors.map((err, i) => {
                          const isCritical = err.severity === 'critical';
                          const color = isCritical ? '#dc2626' : '#d97706';
                          return (
                            <div key={i} style={{ fontSize: 11, fontFamily: 'monospace', color, background: isCritical ? 'rgba(239,68,68,0.05)' : 'rgba(245,158,11,0.05)', padding: '0.5rem', borderRadius: '0.5rem', border: `1px solid ${isCritical ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)'}` }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <span style={{ fontWeight: 800 }}>[{err.type?.toUpperCase()}]</span>
                                <span style={{ fontSize: 9, opacity: 0.6 }}>{err.severity?.toUpperCase()}</span>
                              </div>
                              <div style={{ marginTop: '2px' }}>{err.file} {err.line > 0 && `(Línea ${err.line})`}</div>
                              <div style={{ color: '#6b7280', marginTop: '2px', fontSize: 10 }}>{err.message}</div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: '1rem' }}>No se encontraron patrones de error conocidos en los logs.</div>
                    )}
                    <div style={{ fontSize: 10, color: '#6b7280', marginBottom: '0.25rem', fontWeight: 700 }}>SNIPPET DE LOGS RECIENTES:</div>
                    <pre style={{ fontSize: '10px', fontFamily: 'monospace', color: '#4b5563', background: '#f8fafc', padding: '0.75rem', borderRadius: '0.5rem', overflowX: 'auto', maxHeight: '120px', border: '1px solid #e2e8f0' }}>
                      {diagnosisData.debug_info?.raw_snippet || 'Sin logs disponibles.'}
                    </pre>
                  </div>
                </div>
              ) : (
                <div style={{ color: '#9ca3af', textAlign: 'center', marginTop: '2rem' }}>Error al cargar datos.</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* SUPPORT MODAL */}
      {showSupport && (
        supportView === 'history' && !openTicketId ? (
          <div style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end', padding: '1.5rem' }}
            onClick={e => e.target === e.currentTarget && setShowSupport(false)}>
            <div style={{ width: 460, maxHeight: '80vh', background: '#0d0d0d', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '1.5rem', overflow: 'hidden', display: 'flex', flexDirection: 'column', boxShadow: '0 24px 80px rgba(0,0,0,0.8)', animation: 'slideUp 0.25s ease' }}>
              <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid rgba(255,255,255,0.06)', background: 'linear-gradient(135deg, rgba(0,255,136,0.06), rgba(0,0,0,0))', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>Historial de Soporte</div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button onClick={() => { setSupportView('chat'); setOpenTicketId(null); }} style={{ fontSize: 11, padding: '0.4rem 0.8rem', borderRadius: '0.5rem', background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.2)', color: '#00ff88', cursor: 'pointer', fontWeight: 600 }}>+ Nuevo ticket</button>
                  <button onClick={() => setShowSupport(false)} style={{ background: 'rgba(255,255,255,0.06)', border: 'none', borderRadius: '50%', width: 28, height: 28, cursor: 'pointer', color: '#888', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><X size={14} /></button>
                </div>
              </div>
              <div style={{ flex: 1, overflowY: 'auto', padding: '1rem' }}>
                <SupportTicketList onOpenTicket={id => { setOpenTicketId(id); setSupportView('chat'); }} />
              </div>
            </div>
          </div>
        ) : (
          <SupportChat onClose={() => setShowSupport(false)} initialTicketId={openTicketId} />
        )
      )}
    </>
  );
};

export default Dashboard;
