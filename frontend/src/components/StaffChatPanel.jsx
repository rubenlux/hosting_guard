import React, { useEffect, useState, useRef } from 'react';
import {
  ArrowLeft, Send, Bot, User, Headset, Loader,
  Globe, Zap, Clock, CheckCircle, X
} from 'lucide-react';
import { getTicketDetail, sendTicketMessage, resolveTicket, createSupportWebSocket } from '../services/api';

const STATUS_LABELS = {
  open: 'Abierto', ai_handled: 'IA respondió', waiting: 'Esperando',
  in_progress: 'En progreso', resolved: 'Resuelto', closed: 'Cerrado',
};

const StaffChatPanel = ({ ticketId, staffPayload, onBack }) => {
  const [ticket, setTicket]         = useState(null);
  const [messages, setMessages]     = useState([]);
  const [input, setInput]           = useState('');
  const [loading, setLoading]       = useState(true);
  const [sending, setSending]       = useState(false);
  const [resolving, setResolving]   = useState(false);
  const [typing, setTyping]         = useState(false);
  const [noteInput, setNoteInput]   = useState('');
  const [showResolve, setShowResolve] = useState(false);

  const wsRef         = useRef(null);
  const bottomRef     = useRef(null);
  const textareaRef   = useRef(null);

  // Cargar ticket y conectar WS
  useEffect(() => {
    if (!ticketId) return;
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      try {
        const data = await getTicketDetail(ticketId);
        if (!cancelled) {
          setTicket(data);
          setMessages(data.messages || []);
        }
      } catch (err) {
        console.error('Error loading ticket:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();

    // WebSocket
    const ws = createSupportWebSocket(ticketId);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      if (cancelled) return;
      try {
        const data = JSON.parse(evt.data);
        if (data.type === 'init') {
          setMessages(data.messages || []);
        } else if (data.type === 'message') {
          setMessages(prev => {
            const exists = prev.some(m => String(m.message_id) === String(data.message_id));
            return exists ? prev : [...prev, data];
          });
          setTyping(false);
        } else if (data.type === 'typing' && data.sender_type === 'user') {
          setTyping(true);
          setTimeout(() => setTyping(false), 3000);
        } else if (data.type === 'status_change') {
          setTicket(prev => prev ? { ...prev, status: data.status } : prev);
        }
      } catch (e) { /* noop */ }
    };

    ws.onerror = () => console.warn('WS staff error');
    ws.onclose = () => { wsRef.current = null; };

    return () => {
      cancelled = true;
      ws.close();
    };
  }, [ticketId]);

  // Scroll automático
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, typing]);

  const handleSend = async () => {
    const content = input.trim();
    if (!content || sending) return;
    setInput('');
    setSending(true);

    const optimistic = {
      message_id: `opt-${Date.now()}`,
      sender_type: 'staff',
      sender_id: staffPayload?.staff_id,
      sender_name: staffPayload?.full_name,
      content,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, optimistic]);

    try {
      await sendTicketMessage(ticketId, content);
    } catch (err) {
      console.error('Error sending:', err);
    } finally {
      setSending(false);
    }
  };

  const handleResolve = async () => {
    if (!noteInput.trim()) return;
    setResolving(true);
    try {
      await resolveTicket(ticketId, noteInput.trim());
      setTicket(prev => prev ? { ...prev, status: 'resolved' } : prev);
      setShowResolve(false);
    } catch (err) {
      console.error('Error resolving:', err);
    } finally {
      setResolving(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '60vh' }}>
        <Loader size={28} style={{ color: '#00ff88' }} className="animate-spin" />
      </div>
    );
  }

  if (!ticket) return null;

  const isResolved = ['resolved', 'closed'].includes(ticket.status);

  return (
    <div style={{ display: 'flex', gap: '1.5rem', height: '75vh', maxHeight: '75vh' }}>

      {/* COLUMNA IZQUIERDA — contexto del cliente */}
      <div style={{
        width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '0.75rem',
      }}>
        {/* Back */}
        <button
          onClick={onBack}
          style={{
            display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none',
            color: '#888', cursor: 'pointer', fontSize: 12, padding: 0, marginBottom: 4,
          }}
        >
          <ArrowLeft size={14} /> Volver a la cola
        </button>

        {/* Ticket info */}
        <div style={{
          background: '#111', border: '1px solid rgba(255,255,255,0.06)',
          borderRadius: '0.875rem', padding: '1rem',
        }}>
          <div style={{ fontSize: 10, color: '#666', fontWeight: 700, textTransform: 'uppercase', marginBottom: 8 }}>
            Ticket #{ticket.ticket_id}
          </div>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', marginBottom: 8, lineHeight: 1.4 }}>
            {ticket.title}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 11, color: '#666' }}>Categoría</span>
              <span style={{ fontSize: 11, color: '#fff' }}>{ticket.category}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 11, color: '#666' }}>Estado</span>
              <span style={{
                fontSize: 10, fontWeight: 700, padding: '1px 8px', borderRadius: 20,
                background: isResolved ? 'rgba(156,163,175,0.1)' : 'rgba(0,255,136,0.1)',
                color: isResolved ? '#9ca3af' : '#00ff88',
              }}>
                {STATUS_LABELS[ticket.status] || ticket.status}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 11, color: '#666' }}>Prioridad</span>
              <span style={{ fontSize: 11, color: ticket.priority === 'high' ? '#f59e0b' : '#888', fontWeight: 700, textTransform: 'uppercase' }}>
                {ticket.priority}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 11, color: '#666' }}>Cliente</span>
              <span style={{ fontSize: 11, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 120 }}>
                {ticket.user_email}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 11, color: '#666' }}>Creado</span>
              <span style={{ fontSize: 11, color: '#888' }}>
                {new Date(ticket.created_at).toLocaleDateString('es')}
              </span>
            </div>
          </div>
        </div>

        {/* Resumen de IA */}
        {ticket.ai_summary && (
          <div style={{
            background: 'rgba(0,255,136,0.03)', border: '1px solid rgba(0,255,136,0.1)',
            borderRadius: '0.875rem', padding: '0.875rem',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Bot size={12} style={{ color: '#00ff88' }} />
              <span style={{ fontSize: 10, color: '#00ff88', fontWeight: 700, textTransform: 'uppercase' }}>
                Diagnóstico IA
              </span>
            </div>
            <div style={{ fontSize: 11, color: '#888', lineHeight: 1.5 }}>
              {ticket.ai_summary}
            </div>
          </div>
        )}

        {/* Acción resolución */}
        {!isResolved && (
          <div>
            {!showResolve ? (
              <button
                onClick={() => setShowResolve(true)}
                style={{
                  width: '100%', padding: '0.6rem', borderRadius: '0.75rem',
                  background: 'rgba(0,255,136,0.06)', border: '1px solid rgba(0,255,136,0.2)',
                  color: '#00ff88', fontSize: 11, fontWeight: 700, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                }}
              >
                <CheckCircle size={12} /> Marcar como resuelto
              </button>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <textarea
                  value={noteInput}
                  onChange={e => setNoteInput(e.target.value)}
                  placeholder="Nota de resolución..."
                  style={{
                    background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '0.75rem', color: '#fff', padding: '0.6rem', fontSize: 11,
                    resize: 'none', outline: 'none', fontFamily: 'inherit', width: '100%',
                    boxSizing: 'border-box', minHeight: 70,
                  }}
                />
                <div style={{ display: 'flex', gap: '0.4rem' }}>
                  <button onClick={() => setShowResolve(false)} style={{
                    flex: 1, padding: '0.4rem', borderRadius: '0.5rem', background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.08)', color: '#888', fontSize: 11, cursor: 'pointer',
                  }}>
                    Cancelar
                  </button>
                  <button onClick={handleResolve} disabled={!noteInput.trim() || resolving} style={{
                    flex: 1, padding: '0.4rem', borderRadius: '0.5rem', background: 'rgba(0,255,136,0.1)',
                    border: '1px solid rgba(0,255,136,0.25)', color: '#00ff88', fontSize: 11,
                    fontWeight: 700, cursor: resolving ? 'wait' : 'pointer',
                  }}>
                    {resolving ? 'Guardando...' : 'Confirmar'}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* COLUMNA DERECHA — chat en tiempo real */}
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        background: '#0d0d0d', border: '1px solid rgba(255,255,255,0.06)',
        borderRadius: '1rem', overflow: 'hidden',
      }}>
        {/* Chat header */}
        <div style={{
          padding: '0.875rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.05)',
          display: 'flex', alignItems: 'center', gap: '0.75rem',
          background: 'rgba(255,255,255,0.01)',
        }}>
          <div style={{
            width: 32, height: 32, borderRadius: '50%', background: 'rgba(96,165,250,0.15)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <User size={14} style={{ color: '#60a5fa' }} />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>
              {ticket.user_email}
            </div>
            <div style={{ fontSize: 10, color: '#555' }}>
              {typing ? <span style={{ color: '#00ff88' }}>escribiendo...</span> : 'Chat en tiempo real'}
            </div>
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.625rem' }}>
          {messages.map(msg => {
            const isStaff = msg.sender_type === 'staff';
            const isSystem = msg.sender_type === 'system';
            return (
              <div key={msg.message_id} style={{
                display: 'flex', flexDirection: isStaff ? 'row-reverse' : 'row',
                gap: '0.5rem', alignItems: 'flex-end',
              }}>
                {!isStaff && !isSystem && (
                  <div style={{
                    width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
                    background: msg.sender_type === 'ai' ? 'rgba(0,255,136,0.15)' : 'rgba(96,165,250,0.15)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    {msg.sender_type === 'ai' ? <Bot size={12} style={{ color: '#00ff88' }} />
                      : <User size={12} style={{ color: '#60a5fa' }} />}
                  </div>
                )}
                <div style={{
                  maxWidth: isSystem ? '90%' : '75%',
                  padding: '0.5rem 0.75rem',
                  borderRadius: isStaff ? '0.875rem 0.875rem 0.25rem 0.875rem' : '0.875rem 0.875rem 0.875rem 0.25rem',
                  background: isStaff ? 'rgba(96,165,250,0.1)' : isSystem ? 'transparent' : 'rgba(255,255,255,0.04)',
                  border: isStaff ? '1px solid rgba(96,165,250,0.2)' : isSystem ? '1px dashed rgba(255,255,255,0.05)' : '1px solid rgba(255,255,255,0.06)',
                  fontSize: 12, color: isSystem ? '#555' : '#ccc', lineHeight: 1.5,
                  whiteSpace: 'pre-wrap', fontStyle: isSystem ? 'italic' : 'normal',
                  alignSelf: isSystem ? 'center' : undefined,
                }}>
                  {isStaff && (
                    <div style={{ fontSize: 9, color: '#60a5fa', fontWeight: 700, marginBottom: 3 }}>
                      {msg.sender_name || 'Tú'}
                    </div>
                  )}
                  {msg.content}
                  <div style={{ fontSize: 9, color: '#444', marginTop: 3, textAlign: isStaff ? 'right' : 'left' }}>
                    {new Date(msg.created_at).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
              </div>
            );
          })}

          {typing && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <div style={{
                width: 26, height: 26, borderRadius: '50%', background: 'rgba(96,165,250,0.15)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <User size={12} style={{ color: '#60a5fa' }} />
              </div>
              <div style={{
                padding: '0.5rem 0.75rem', background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.06)', borderRadius: '0.875rem',
                fontSize: 16, color: '#555',
              }}>
                ●●●
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        {!isResolved && (
          <div style={{ padding: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => { setInput(e.target.value); const el = textareaRef.current; if (el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; } }}
              onKeyDown={handleKeyDown}
              placeholder="Escribí tu respuesta al cliente..."
              rows={1}
              style={{
                flex: 1, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: '0.75rem', color: '#fff', padding: '0.625rem 0.875rem',
                fontSize: 12, resize: 'none', outline: 'none', fontFamily: 'inherit',
                lineHeight: 1.5, minHeight: 40, maxHeight: 120,
              }}
            />
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              style={{
                width: 36, height: 36, border: 'none', borderRadius: '0.75rem',
                background: sending || !input.trim() ? 'rgba(96,165,250,0.2)' : '#60a5fa',
                cursor: sending || !input.trim() ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                transition: 'all 0.15s',
              }}
            >
              {sending ? <Loader size={14} color="#fff" className="animate-spin" /> : <Send size={14} color="#000" />}
            </button>
          </div>
        )}

        {isResolved && (
          <div style={{
            padding: '0.875rem', textAlign: 'center', borderTop: '1px solid rgba(255,255,255,0.05)',
            color: '#9ca3af', fontSize: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
          }}>
            <CheckCircle size={14} style={{ color: '#00ff88' }} />
            Ticket resuelto — conversación cerrada
          </div>
        )}
      </div>
    </div>
  );
};

export default StaffChatPanel;
