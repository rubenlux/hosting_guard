import React, { useEffect, useState, useCallback } from 'react';
import {
  Clock, User, Zap, MessageSquare, RefreshCw,
  Loader, AlertTriangle, CheckCircle, ChevronRight
} from 'lucide-react';
import { getSupportQueue, assignTicket } from '../services/api';

const PRIORITY_CONFIG = {
  urgent: { color: '#ef4444', bg: 'rgba(239,68,68,0.1)', label: 'URGENTE' },
  high:   { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', label: 'ALTO' },
  medium: { color: '#60a5fa', bg: 'rgba(96,165,250,0.1)', label: 'MEDIO' },
  low:    { color: '#9ca3af', bg: 'rgba(156,163,175,0.1)', label: 'BAJO' },
};

const CAT_ICONS = {
  'Sitio caído': '🔴', 'Sitio lento': '🐌', 'Error en WordPress': '⚠️',
  'Problema de billing': '💳', 'Ayuda técnica': '🔧', 'Otro': '❓',
};

const SupportQueue = ({ onOpenTicket }) => {
  const [queue, setQueue]       = useState({ tickets: [], waiting_count: 0 });
  const [loading, setLoading]   = useState(true);
  const [assigning, setAssigning] = useState(null);

  const fetchQueue = useCallback(async () => {
    try {
      const data = await getSupportQueue();
      setQueue(data);
    } catch (err) {
      console.error('Error fetching queue:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQueue();
    const interval = setInterval(fetchQueue, 15000);
    return () => clearInterval(interval);
  }, [fetchQueue]);

  const handleAssign = async (ticketId, e) => {
    e.stopPropagation();
    setAssigning(ticketId);
    try {
      await assignTicket(ticketId);
      await fetchQueue();
      onOpenTicket?.(ticketId);
    } catch (err) {
      console.error('Error assigning ticket:', err);
    } finally {
      setAssigning(null);
    }
  };

  const timeWaiting = (createdAt) => {
    const diff = Date.now() - new Date(createdAt).getTime();
    const m = Math.floor(diff / 60000);
    const h = Math.floor(m / 60);
    return h > 0 ? `${h}h ${m % 60}m` : `${m}m`;
  };

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: '#fff', margin: 0 }}>Cola de Soporte</h2>
          {queue.waiting_count > 0 && (
            <span style={{
              background: 'rgba(239,68,68,0.15)', color: '#ef4444',
              border: '1px solid rgba(239,68,68,0.3)', borderRadius: 20,
              fontSize: 11, fontWeight: 700, padding: '2px 10px',
            }}>
              {queue.waiting_count} esperando
            </span>
          )}
        </div>
        <button
          onClick={fetchQueue}
          style={{
            background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: '0.75rem', padding: '0.5rem', color: '#888', cursor: 'pointer',
          }}
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
          <Loader size={24} style={{ color: '#00ff88' }} className="animate-spin" />
        </div>
      ) : queue.tickets.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '3rem 1rem',
          background: 'rgba(0,255,136,0.02)', borderRadius: '1rem',
          border: '1px dashed rgba(0,255,136,0.1)',
        }}>
          <CheckCircle size={32} style={{ color: '#00ff88', marginBottom: 12 }} />
          <div style={{ color: '#00ff88', fontSize: 14, fontWeight: 600 }}>Cola vacía</div>
          <div style={{ color: '#555', fontSize: 12, marginTop: 6 }}>
            No hay tickets pendientes en este momento.
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {queue.tickets.map(ticket => {
            const pc = PRIORITY_CONFIG[ticket.priority] || PRIORITY_CONFIG.medium;
            const waiting = timeWaiting(ticket.created_at);
            const isUrgent = ticket.priority === 'urgent' || ticket.priority === 'high';

            return (
              <div
                key={ticket.ticket_id}
                onClick={() => onOpenTicket?.(ticket.ticket_id)}
                style={{
                  background: '#111',
                  border: `1px solid ${isUrgent ? 'rgba(245,158,11,0.2)' : 'rgba(255,255,255,0.06)'}`,
                  borderRadius: '1rem', padding: '1rem', cursor: 'pointer',
                  transition: 'all 0.15s', position: 'relative', overflow: 'hidden',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = '#161616'; }}
                onMouseLeave={e => { e.currentTarget.style.background = '#111'; }}
              >
                {/* Badge animado para urgente */}
                {isUrgent && (
                  <div style={{
                    position: 'absolute', top: 0, left: 0, right: 0, height: 2,
                    background: 'linear-gradient(90deg, transparent, rgba(245,158,11,0.5), transparent)',
                    animation: 'shimmer 2s infinite',
                  }} />
                )}

                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                  {/* Ícono categoría */}
                  <div style={{
                    width: 44, height: 44, borderRadius: '0.875rem', flexShrink: 0,
                    background: 'rgba(255,255,255,0.04)', display: 'flex',
                    alignItems: 'center', justifyContent: 'center', fontSize: 20,
                  }}>
                    {CAT_ICONS[ticket.category] || '❓'}
                  </div>

                  {/* Info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {/* Title + priority */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: 4 }}>
                      <div style={{
                        fontSize: 13, fontWeight: 600, color: '#fff',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
                      }}>
                        {ticket.title}
                      </div>
                      <span style={{
                        fontSize: 9, fontWeight: 800, padding: '2px 7px', borderRadius: 20,
                        background: pc.bg, color: pc.color, flexShrink: 0,
                      }}>
                        {pc.label}
                      </span>
                    </div>

                    {/* Meta */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 11, color: '#888', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <User size={10} /> {ticket.user_email || `Usuario #${ticket.user_id}`}
                      </span>
                      <span style={{ fontSize: 10, color: '#555' }}>•</span>
                      <span style={{ fontSize: 11, color: '#888', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Zap size={10} /> Plan {ticket.user_plan || 'free'}
                      </span>
                      <span style={{ fontSize: 10, color: '#555' }}>•</span>
                      <span style={{
                        fontSize: 11, display: 'flex', alignItems: 'center', gap: 4,
                        color: parseInt(waiting) > 30 ? '#ef4444' : '#888',
                      }}>
                        <Clock size={10} /> {waiting}
                      </span>
                    </div>

                    {/* Resumen de IA */}
                    {ticket.ai_summary && (
                      <div style={{
                        marginTop: '0.5rem', fontSize: 11, color: '#555',
                        background: 'rgba(0,255,136,0.03)', borderRadius: '0.5rem',
                        padding: '0.4rem 0.6rem', borderLeft: '2px solid rgba(0,255,136,0.2)',
                        overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box',
                        WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                      }}>
                        🤖 {ticket.ai_summary}
                      </div>
                    )}
                  </div>
                </div>

                {/* Footer: botón tomar ticket */}
                <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    onClick={(e) => handleAssign(ticket.ticket_id, e)}
                    disabled={assigning === ticket.ticket_id}
                    style={{
                      background: assigning === ticket.ticket_id ? 'rgba(0,255,136,0.05)' : 'rgba(0,255,136,0.1)',
                      border: '1px solid rgba(0,255,136,0.25)', borderRadius: '0.625rem',
                      color: '#00ff88', fontSize: 11, fontWeight: 700, padding: '0.4rem 0.875rem',
                      cursor: assigning === ticket.ticket_id ? 'wait' : 'pointer',
                      display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.15s',
                    }}
                  >
                    {assigning === ticket.ticket_id
                      ? <><Loader size={11} className="animate-spin" /> Tomando...</>
                      : <><MessageSquare size={11} /> Tomar ticket</>
                    }
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SupportQueue;
