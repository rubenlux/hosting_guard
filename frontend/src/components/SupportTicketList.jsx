import React, { useEffect, useState } from 'react';
import { MessageSquare, Clock, CheckCircle, AlertTriangle, ChevronRight, Loader, RefreshCw } from 'lucide-react';
import { getMyTickets } from '../services/api';

const STATUS_CONFIG = {
  open:        { label: 'Abierto',         color: '#f59e0b', bg: 'rgba(245,158,11,0.1)',  Icon: Clock },
  ai_handled:  { label: 'IA respondió',    color: '#00ff88', bg: 'rgba(0,255,136,0.1)',   Icon: MessageSquare },
  waiting:     { label: 'Esperando',       color: '#f59e0b', bg: 'rgba(245,158,11,0.1)',  Icon: Clock },
  in_progress: { label: 'En progreso',     color: '#60a5fa', bg: 'rgba(96,165,250,0.1)',  Icon: MessageSquare },
  resolved:    { label: 'Resuelto',        color: '#9ca3af', bg: 'rgba(156,163,175,0.1)', Icon: CheckCircle },
  closed:      { label: 'Cerrado',         color: '#6b7280', bg: 'rgba(107,114,128,0.1)', Icon: CheckCircle },
};

const CAT_ICONS = {
  'Sitio caído': '🔴', 'Sitio lento': '🐌', 'Error en WordPress': '⚠️',
  'Problema de billing': '💳', 'Ayuda técnica': '🔧', 'Otro': '❓',
};

const PRIORITY_COLOR = { urgent: '#ef4444', high: '#f59e0b', medium: '#60a5fa', low: '#9ca3af' };

const SupportTicketList = ({ onOpenTicket }) => {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchTickets = async () => {
    setLoading(true);
    try {
      const data = await getMyTickets();
      setTickets(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Error fetching tickets:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchTickets(); }, []);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}>
        <Loader size={24} className="animate-spin" style={{ color: '#00ff88' }} />
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: '#fff', margin: 0 }}>Mis Tickets de Soporte</h2>
          <p style={{ fontSize: 12, color: '#666', margin: '4px 0 0' }}>Historial de todas tus consultas</p>
        </div>
        <button
          onClick={fetchTickets}
          style={{
            background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: '0.75rem', padding: '0.5rem 0.875rem', color: '#888',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12,
          }}
        >
          <RefreshCw size={12} /> Actualizar
        </button>
      </div>

      {tickets.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '3rem 1rem',
          background: 'rgba(255,255,255,0.02)', borderRadius: '1rem',
          border: '1px dashed rgba(255,255,255,0.06)',
        }}>
          <MessageSquare size={32} style={{ color: '#333', marginBottom: 12 }} />
          <div style={{ color: '#666', fontSize: 14 }}>No tenés tickets aún</div>
          <div style={{ color: '#444', fontSize: 12, marginTop: 6 }}>
            Usá el botón de soporte para crear tu primera consulta.
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {tickets.map(ticket => {
            const sc = STATUS_CONFIG[ticket.status] || STATUS_CONFIG.open;
            const StatusIcon = sc.Icon;
            const timeAgo = (() => {
              const diff = Date.now() - new Date(ticket.created_at).getTime();
              const h = Math.floor(diff / 3600000);
              const d = Math.floor(h / 24);
              return d > 0 ? `hace ${d}d` : h > 0 ? `hace ${h}h` : 'ahora';
            })();

            return (
              <div
                key={ticket.ticket_id}
                onClick={() => onOpenTicket?.(ticket.ticket_id)}
                style={{
                  background: '#111', border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '0.875rem', padding: '0.875rem 1rem',
                  cursor: 'pointer', transition: 'all 0.15s',
                  display: 'flex', alignItems: 'center', gap: '0.875rem',
                }}
                onMouseEnter={e => { e.currentTarget.style.border = '1px solid rgba(255,255,255,0.12)'; e.currentTarget.style.background = '#161616'; }}
                onMouseLeave={e => { e.currentTarget.style.border = '1px solid rgba(255,255,255,0.06)'; e.currentTarget.style.background = '#111'; }}
              >
                {/* Ícono de categoría */}
                <div style={{
                  width: 40, height: 40, borderRadius: '0.75rem', flexShrink: 0,
                  background: 'rgba(255,255,255,0.04)', display: 'flex',
                  alignItems: 'center', justifyContent: 'center', fontSize: 18,
                }}>
                  {CAT_ICONS[ticket.category] || '❓'}
                </div>

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#fff', marginBottom: 3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {ticket.title}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <span style={{
                      fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 20,
                      background: sc.bg, color: sc.color, display: 'flex', alignItems: 'center', gap: 4,
                    }}>
                      <StatusIcon size={10} /> {sc.label}
                    </span>
                    <span style={{ fontSize: 10, color: '#555' }}>•</span>
                    <span style={{ fontSize: 10, color: '#555' }}>{timeAgo}</span>
                    {ticket.priority && ticket.priority !== 'low' && (
                      <>
                        <span style={{ fontSize: 10, color: '#555' }}>•</span>
                        <span style={{ fontSize: 10, color: PRIORITY_COLOR[ticket.priority] || '#888', fontWeight: 600, textTransform: 'uppercase' }}>
                          {ticket.priority}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                <ChevronRight size={14} style={{ color: '#444', flexShrink: 0 }} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SupportTicketList;
