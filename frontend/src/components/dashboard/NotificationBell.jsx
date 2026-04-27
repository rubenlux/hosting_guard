import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, X, Check, CheckCheck, Trash2, ExternalLink, AlertTriangle, Info, CheckCircle2, Zap, Shield, CreditCard, Server, ArrowRight } from 'lucide-react';
import {
  getNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
  archiveNotification,
} from '../../services/api';

/* ── category / severity config ─────────────────────────────────────────── */
const SEVERITY_CFG = {
  critical:       { color: 'text-red-400',    bg: 'bg-red-500/10 border-red-500/20',    dot: 'bg-red-400'     },
  security:       { color: 'text-amber-400',  bg: 'bg-amber-500/10 border-amber-500/20', dot: 'bg-amber-400'   },
  warning:        { color: 'text-amber-400',  bg: 'bg-amber-500/10 border-amber-500/20', dot: 'bg-amber-400'   },
  action_required:{ color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/20', dot: 'bg-orange-400' },
  success:        { color: 'text-[#00ff88]',  bg: 'bg-[#00ff88]/8 border-[#00ff88]/15', dot: 'bg-[#00ff88]'   },
  billing:        { color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/20', dot: 'bg-purple-400' },
  info:           { color: 'text-blue-400',   bg: 'bg-blue-500/10 border-blue-500/20',  dot: 'bg-blue-400'    },
};

const CAT_ICON = {
  security:    <Shield   className="w-3 h-3" />,
  billing:     <CreditCard className="w-3 h-3" />,
  hosting:     <Server   className="w-3 h-3" />,
  performance: <Zap      className="w-3 h-3" />,
  wordpress:   <CheckCircle2 className="w-3 h-3" />,
  system:      <Info     className="w-3 h-3" />,
};

function sevCfg(sev) {
  return SEVERITY_CFG[sev] || SEVERITY_CFG.info;
}

function timeAgo(isoStr) {
  const diff = (Date.now() - new Date(isoStr).getTime()) / 1000;
  if (diff < 60)   return 'ahora';
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

/* ── single notification row ─────────────────────────────────────────────── */
function NotifRow({ item, onRead, onArchive }) {
  const cfg     = sevCfg(item.severity);
  const unread  = item.status === 'unread';
  const icon    = CAT_ICON[item.category] || <Info className="w-3 h-3" />;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, height: 0, marginBottom: 0 }}
      transition={{ duration: 0.15 }}
      className={`group relative flex gap-2.5 px-3 py-2.5 rounded-lg border transition-colors cursor-default
        ${unread ? cfg.bg : 'bg-white/2 border-white/6 opacity-60'}
      `}
    >
      {/* severity dot */}
      <div className="flex flex-col items-center pt-0.5 shrink-0">
        <div className={`w-1.5 h-1.5 rounded-full mt-0.5 ${unread ? cfg.dot : 'bg-white/20'}`} />
      </div>

      {/* content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-1">
          <div className={`text-[11px] font-semibold leading-tight ${unread ? 'text-white' : 'text-white/50'}`}>
            {item.title}
          </div>
          <span className="text-[9px] text-white/30 shrink-0 mt-0.5">{timeAgo(item.created_at)}</span>
        </div>
        <div className="text-[10px] text-white/40 mt-0.5 leading-relaxed line-clamp-2">{item.message}</div>
        <div className="flex items-center gap-2 mt-1.5">
          <span className={`flex items-center gap-1 text-[9px] ${cfg.color} opacity-70`}>
            {icon}{item.category}
          </span>
          {item.action_url && (
            <a
              href={item.action_url.startsWith('http') ? item.action_url : `https://app.hostingguard.lat${item.action_url}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[9px] text-blue-400/70 hover:text-blue-300 flex items-center gap-0.5 transition-colors"
              onClick={(e) => e.stopPropagation()}
            >
              ver <ExternalLink className="w-2.5 h-2.5" />
            </a>
          )}
        </div>
      </div>

      {/* action buttons — visible on hover */}
      <div className="flex flex-col gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        {unread && (
          <button
            onClick={() => onRead(item.notification_id)}
            className="w-5 h-5 rounded flex items-center justify-center bg-white/8 hover:bg-white/15 transition-colors"
            title="Marcar como leída"
          >
            <Check className="w-2.5 h-2.5 text-white/50" />
          </button>
        )}
        <button
          onClick={() => onArchive(item.notification_id)}
          className="w-5 h-5 rounded flex items-center justify-center bg-white/8 hover:bg-red-500/20 hover:text-red-400 transition-colors text-white/30"
          title="Archivar"
        >
          <Trash2 className="w-2.5 h-2.5" />
        </button>
      </div>
    </motion.div>
  );
}

/* ── main component ──────────────────────────────────────────────────────── */
export default function NotificationBell() {
  const navigate  = useNavigate();
  const [open,    setOpen]    = useState(false);
  const [items,   setItems]   = useState([]);
  const [unread,  setUnread]  = useState(0);
  const [loading, setLoading] = useState(false);
  const panelRef = useRef(null);
  const pollRef  = useRef(null);

  /* load notifications */
  const load = useCallback(async () => {
    try {
      const data = await getNotifications({ limit: 40 });
      setItems(data.items || []);
      setUnread(data.unread || 0);
    } catch { /* ignore */ }
  }, []);

  /* poll unread count every 30s when closed; full reload when open */
  useEffect(() => {
    load();
    const pollCount = async () => {
      try {
        const { unread: cnt } = await getUnreadCount();
        setUnread(cnt);
      } catch { /* ignore */ }
    };
    pollRef.current = setInterval(open ? load : pollCount, open ? 10000 : 30000);
    return () => clearInterval(pollRef.current);
  }, [open, load]);

  /* reload when opening */
  useEffect(() => {
    if (open) { setLoading(true); load().finally(() => setLoading(false)); }
  }, [open, load]);

  /* close on outside click */
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleRead = async (id) => {
    try {
      await markNotificationRead(id);
      setItems(prev => prev.map(n => n.notification_id === id ? { ...n, status: 'read' } : n));
      setUnread(prev => Math.max(0, prev - 1));
    } catch { /* ignore */ }
  };

  const handleArchive = async (id) => {
    const item = items.find(n => n.notification_id === id);
    try {
      await archiveNotification(id);
      setItems(prev => prev.filter(n => n.notification_id !== id));
      if (item?.status === 'unread') setUnread(prev => Math.max(0, prev - 1));
    } catch { /* ignore */ }
  };

  const handleMarkAll = async () => {
    try {
      await markAllNotificationsRead();
      setItems(prev => prev.map(n => ({ ...n, status: 'read' })));
      setUnread(0);
    } catch { /* ignore */ }
  };

  const visible = items.filter(n => n.status !== 'archived');

  return (
    <div className="relative" ref={panelRef}>
      {/* bell button */}
      <button
        onClick={() => setOpen(v => !v)}
        className={`relative w-8 h-8 flex items-center justify-center rounded-lg border transition-colors
          ${open ? 'bg-white/10 border-white/15' : 'bg-white/4 border-white/8 hover:bg-white/8'}`}
      >
        <Bell className="w-4 h-4 text-white/60" />
        <AnimatePresence>
          {unread > 0 && (
            <motion.span
              key="badge"
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
              className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-white text-[8px] font-bold flex items-center justify-center leading-none"
            >
              {unread > 9 ? '9+' : unread}
            </motion.span>
          )}
        </AnimatePresence>
      </button>

      {/* dropdown panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            key="panel"
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0,  scale: 1 }}
            exit={  { opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-10 w-80 bg-[#111113] border border-white/10 rounded-xl shadow-2xl overflow-hidden z-50"
          >
            {/* header */}
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/6">
              <div className="flex items-center gap-2">
                <span className="text-[12px] font-semibold text-white">Notificaciones</span>
                {unread > 0 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-400 font-medium border border-red-500/20">
                    {unread} nueva{unread !== 1 && 's'}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {unread > 0 && (
                  <button
                    onClick={handleMarkAll}
                    className="flex items-center gap-1 text-[10px] text-white/40 hover:text-white/70 transition-colors px-1.5 py-1 rounded"
                    title="Marcar todas como leídas"
                  >
                    <CheckCheck className="w-3 h-3" />
                    <span>Leer todo</span>
                  </button>
                )}
                <button
                  onClick={() => setOpen(false)}
                  className="w-5 h-5 flex items-center justify-center rounded hover:bg-white/10 transition-colors"
                >
                  <X className="w-3 h-3 text-white/30" />
                </button>
              </div>
            </div>

            {/* list */}
            <div className="max-h-[380px] overflow-y-auto p-2 flex flex-col gap-1.5">
              {loading && visible.length === 0 ? (
                <div className="py-8 text-center text-[11px] text-white/25">Cargando...</div>
              ) : visible.length === 0 ? (
                <div className="py-10 text-center">
                  <Bell className="w-7 h-7 text-white/10 mx-auto mb-2" />
                  <div className="text-[11px] text-white/25">Sin notificaciones</div>
                </div>
              ) : (
                <AnimatePresence initial={false}>
                  {visible.map(item => (
                    <NotifRow
                      key={item.notification_id}
                      item={item}
                      onRead={handleRead}
                      onArchive={handleArchive}
                    />
                  ))}
                </AnimatePresence>
              )}
            </div>

            {/* footer */}
            <div className="border-t border-white/6 px-3 py-2 flex items-center justify-between">
              <span className="text-[9px] text-white/20 font-mono">
                {visible.length} · últimas 40
              </span>
              <button
                onClick={() => { setOpen(false); navigate('/notifications'); }}
                className="flex items-center gap-1 text-[10px] text-white/40 hover:text-white/70 transition-colors"
              >
                Ver todas <ArrowRight className="w-2.5 h-2.5" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
