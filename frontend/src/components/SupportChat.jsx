import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  X, Send, Bot, User, Users, ChevronRight, CheckCircle,
  AlertTriangle, Loader, MessageSquare, Clock, Headset
} from 'lucide-react';
import {
  getSupportCategories, createSupportTicket, sendTicketMessage,
  escalateTicket, resolveTicket, createSupportWebSocket
} from '../services/api';

// Iconos de categoría → emoji
const CAT_ICONS = {
  'Sitio caído':        '🔴',
  'Sitio lento':        '🐌',
  'Error en WordPress': '⚠️',
  'Problema de billing':'💳',
  'Ayuda técnica':      '🔧',
  'Otro':               '❓',
};

// ── Estilos inline ────────────────────────────────────────────────────────────
const S = {
  overlay: {
    position: 'fixed', inset: 0, zIndex: 1000,
    background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
    display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end',
    padding: '1.5rem',
  },
  panel: {
    width: '420px', height: '620px', maxHeight: '90vh',
    background: '#0d0d0d', border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: '1.5rem', display: 'flex', flexDirection: 'column',
    overflow: 'hidden', boxShadow: '0 24px 80px rgba(0,0,0,0.8)',
    animation: 'slideUp 0.25s ease',
  },
  header: {
    padding: '1rem 1.25rem',
    background: 'linear-gradient(135deg, rgba(0,255,136,0.08), rgba(0,0,0,0))',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
    display: 'flex', alignItems: 'center', gap: '0.75rem',
  },
  iconBadge: {
    width: 36, height: 36, borderRadius: '50%',
    background: 'rgba(0,255,136,0.15)', display: 'flex',
    alignItems: 'center', justifyContent: 'center', flexShrink: 0,
  },
  title: { flex: 1 },
  titleText: { fontSize: 13, fontWeight: 700, color: '#fff' },
  titleSub: { fontSize: 10, color: '#666', marginTop: 2 },
  closeBtn: {
    width: 28, height: 28, borderRadius: '50%', border: 'none',
    background: 'rgba(255,255,255,0.06)', cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: '#888',
  },
  body: { flex: 1, overflowY: 'auto', padding: '1rem' },
  footer: {
    padding: '0.75rem 1rem',
    borderTop: '1px solid rgba(255,255,255,0.06)',
  },
  // Categorías
  catGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem' },
  catCard: {
    background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: '0.875rem', padding: '0.875rem 0.75rem',
    cursor: 'pointer', transition: 'all 0.15s ease',
    display: 'flex', flexDirection: 'column', gap: 6,
  },
  catIcon: { fontSize: 22, lineHeight: 1 },
  catName: { fontSize: 11, fontWeight: 700, color: '#fff' },
  catDesc: { fontSize: 10, color: '#666', lineHeight: 1.4 },
  // Mensajes
  msgRow: (type) => ({
    display: 'flex',
    flexDirection: type === 'user' ? 'row-reverse' : 'row',
    gap: '0.5rem', marginBottom: '0.75rem', alignItems: 'flex-end',
  }),
  msgAvatar: (type) => ({
    width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    background: type === 'ai' ? 'rgba(0,255,136,0.15)'
               : type === 'staff' ? 'rgba(96,165,250,0.15)'
               : type === 'system' ? 'transparent'
               : 'rgba(255,255,255,0.1)',
    fontSize: 11,
  }),
  msgBubble: (type) => ({
    maxWidth: '78%', padding: '0.6rem 0.875rem',
    borderRadius: type === 'user' ? '1rem 1rem 0.25rem 1rem' : '1rem 1rem 1rem 0.25rem',
    background: type === 'user' ? 'rgba(0,255,136,0.12)'
               : type === 'ai' ? 'rgba(255,255,255,0.05)'
               : type === 'system' ? 'rgba(255,255,255,0.03)'
               : 'rgba(96,165,250,0.08)',
    border: type === 'user' ? '1px solid rgba(0,255,136,0.2)'
           : type === 'system' ? '1px dashed rgba(255,255,255,0.06)'
           : '1px solid rgba(255,255,255,0.06)',
    fontSize: 12, color: type === 'system' ? '#666' : '#ccc',
    lineHeight: 1.5, whiteSpace: 'pre-wrap',
    fontStyle: type === 'system' ? 'italic' : 'normal',
  }),
  // Input
  inputRow: {
    display: 'flex', gap: '0.5rem', alignItems: 'flex-end',
  },
  textarea: {
    flex: 1, background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.1)', borderRadius: '0.75rem',
    color: '#fff', padding: '0.6rem 0.875rem', fontSize: 12,
    resize: 'none', outline: 'none', fontFamily: 'inherit',
    lineHeight: 1.5, minHeight: 40, maxHeight: 100,
  },
  sendBtn: {
    width: 36, height: 36, border: 'none', borderRadius: '0.75rem',
    background: '#00ff88', cursor: 'pointer', display: 'flex',
    alignItems: 'center', justifyContent: 'center', flexShrink: 0,
  },
  escalateBtn: {
    width: '100%', padding: '0.5rem', marginTop: '0.5rem',
    background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.2)',
    borderRadius: '0.75rem', color: '#60a5fa', fontSize: 11, fontWeight: 600,
    cursor: 'pointer', display: 'flex', alignItems: 'center',
    justifyContent: 'center', gap: 6,
  },
  resolveBtn: {
    width: '100%', padding: '0.5rem', marginTop: '0.5rem',
    background: 'rgba(0,255,136,0.08)', border: '1px solid rgba(0,255,136,0.2)',
    borderRadius: '0.75rem', color: '#00ff88', fontSize: 11, fontWeight: 600,
    cursor: 'pointer', display: 'flex', alignItems: 'center',
    justifyContent: 'center', gap: 6,
  },
};

// ── Componente principal ──────────────────────────────────────────────────────
const SupportChat = ({ onClose, initialTicketId = null }) => {
  const [phase, setPhase]           = useState(initialTicketId ? 'chat' : 'category'); // category | chat
  const [categories, setCategories] = useState([]);
  const [selectedCat, setSelectedCat] = useState(null);
  const [messages, setMessages]     = useState([]);
  const [ticketId, setTicketId]     = useState(initialTicketId);
  const [ticketStatus, setTicketStatus] = useState('open');
  const [staffName, setStaffName]   = useState(null);
  const [input, setInput]           = useState('');
  const [loading, setLoading]       = useState(false);
  const [sending, setSending]       = useState(false);
  const [aiTyping, setAiTyping]     = useState(false);

  const messagesEndRef = useRef(null);
  const wsRef          = useRef(null);
  const textareaRef    = useRef(null);

  // Scroll al último mensaje
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);

  // Cargar categorías
  useEffect(() => {
    getSupportCategories().then(setCategories).catch(console.error);
  }, []);

  // Conectar WebSocket cuando hay ticket
  useEffect(() => {
    if (!ticketId) return;

    const ws = createSupportWebSocket(ticketId);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === 'init') {
          setMessages(data.messages || []);
          setTicketStatus(data.ticket?.status || 'open');
        } else if (data.type === 'message') {
          setMessages(prev => {
            const exists = prev.some(m => m.message_id === data.message_id);
            return exists ? prev : [...prev, data];
          });
          setAiTyping(false);
        } else if (data.type === 'typing') {
          if (data.sender_type !== 'user') setAiTyping(true);
          // Auto-ocultar después de 3s
          setTimeout(() => setAiTyping(false), 3000);
        } else if (data.type === 'status_change') {
          setTicketStatus(data.status);
          if (data.staff_name) setStaffName(data.staff_name);
          setMessages(prev => [...prev, {
            message_id: Date.now(),
            sender_type: 'system',
            content: data.message || `Estado: ${data.status}`,
            created_at: new Date().toISOString(),
          }]);
        }
      } catch (e) { /* noop */ }
    };

    ws.onerror = () => console.warn('WS support error');
    ws.onclose = () => { wsRef.current = null; };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [ticketId]);

  // Seleccionar categoría → pedir descripción inicial
  const handleCategorySelect = async (cat) => {
    setSelectedCat(cat);
    setLoading(true);
    setPhase('chat');

    // Mensaje placeholder mientras el usuario escribe
    setMessages([{
      message_id: 'placeholder',
      sender_type: 'system',
      content: `📂 Categoría seleccionada: ${cat.name}\n\nContame tu problema con más detalle y la IA te responderá enseguida.`,
      created_at: new Date().toISOString(),
    }]);
    setLoading(false);
  };

  // Enviar primer mensaje (crea el ticket)
  const handleFirstSend = async (content) => {
    if (!selectedCat || !content.trim()) return;
    setLoading(true);
    setAiTyping(true);

    try {
      const res = await createSupportTicket({
        category: selectedCat.name,
        description: content,
      });
      setTicketId(res.ticket_id);
      setTicketStatus(res.status);
      // El WebSocket recibirá los mensajes vía init
    } catch (err) {
      setMessages(prev => [...prev, {
        message_id: Date.now(),
        sender_type: 'system',
        content: '❌ Error al crear el ticket. Intentá de nuevo.',
        created_at: new Date().toISOString(),
      }]);
      setAiTyping(false);
    } finally {
      setLoading(false);
    }
  };

  // Enviar mensaje en ticket existente
  const handleSend = async () => {
    const content = input.trim();
    if (!content || sending) return;
    setInput('');

    if (!ticketId) {
      await handleFirstSend(content);
      return;
    }

    setSending(true);
    const optimistic = {
      message_id: `opt-${Date.now()}`,
      sender_type: 'user',
      content,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, optimistic]);

    try {
      await sendTicketMessage(ticketId, content);
    } catch (err) {
      console.error('Error sending message:', err);
    } finally {
      setSending(false);
    }
  };

  const handleEscalate = async () => {
    if (!ticketId) return;
    try {
      await escalateTicket(ticketId, 'Quiero hablar con un colaborador.');
      setTicketStatus('waiting');
    } catch (err) {
      console.error(err);
    }
  };

  const handleResolve = async () => {
    if (!ticketId) return;
    try {
      await resolveTicket(ticketId, 'Cliente confirmó resolución desde el chat.');
      setTicketStatus('resolved');
    } catch (err) {
      console.error(err);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Ajusta altura del textarea automáticamente
  const handleInputChange = (e) => {
    setInput(e.target.value);
    const el = textareaRef.current;
    if (el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }
  };

  // ── Status badge del header ──
  const statusLabel = {
    'open':        { text: 'Soporte IA', color: '#00ff88' },
    'ai_handled':  { text: 'IA respondió', color: '#00ff88' },
    'waiting':     { text: 'Buscando colaborador...', color: '#f59e0b' },
    'in_progress': { text: staffName ? `Con ${staffName}` : 'Colaborador conectado', color: '#60a5fa' },
    'resolved':    { text: 'Resuelto', color: '#9ca3af' },
    'closed':      { text: 'Cerrado', color: '#9ca3af' },
  }[ticketStatus] || { text: 'Soporte', color: '#00ff88' };

  return (
    <>
      <style>{`
        @keyframes slideUp { from { transform: translateY(40px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        .support-cat-card:hover { background: rgba(0,255,136,0.06) !important; border-color: rgba(0,255,136,0.25) !important; transform: translateY(-1px); }
        .support-textarea:focus { border-color: rgba(0,255,136,0.3) !important; }
        .support-send-btn:hover { background: #00cc70 !important; transform: scale(1.05); }
        .support-escalate-btn:hover { background: rgba(96,165,250,0.15) !important; }
        .support-resolve-btn:hover { background: rgba(0,255,136,0.15) !important; }
        .support-body::-webkit-scrollbar { width: 4px; }
        .support-body::-webkit-scrollbar-track { background: transparent; }
        .support-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
        .ai-typing-dots span { animation: blink 1.2s infinite; display: inline-block; }
        .ai-typing-dots span:nth-child(2) { animation-delay: 0.2s; }
        .ai-typing-dots span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes blink { 0%,80%,100% { opacity: 0.3; } 40% { opacity: 1; } }
      `}</style>

      <div style={S.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div style={S.panel}>

          {/* HEADER */}
          <div style={S.header}>
            <div style={S.iconBadge}>
              {ticketStatus === 'in_progress'
                ? <Users size={16} color="#60a5fa" />
                : <Bot size={16} color="#00ff88" />}
            </div>
            <div style={S.title}>
              <div style={S.titleText}>
                {phase === 'category' ? 'Centro de Soporte' : selectedCat?.name || 'Chat de Soporte'}
              </div>
              <div style={{ ...S.titleSub, color: statusLabel.color }}>
                ● {statusLabel.text}
              </div>
            </div>
            <button style={S.closeBtn} onClick={onClose}>
              <X size={14} />
            </button>
          </div>

          {/* BODY */}
          <div className="support-body" style={S.body}>

            {/* FASE 1: Selección de categoría */}
            {phase === 'category' && (
              <>
                <p style={{ fontSize: 12, color: '#888', marginBottom: '1rem', lineHeight: 1.5 }}>
                  ¿En qué podemos ayudarte? Seleccioná el tipo de problema y la IA te responderá enseguida.
                </p>
                <div style={S.catGrid}>
                  {categories.map(cat => (
                    <div
                      key={cat.category_id}
                      className="support-cat-card"
                      style={S.catCard}
                      onClick={() => handleCategorySelect(cat)}
                    >
                      <div style={S.catIcon}>{cat.icon || CAT_ICONS[cat.name] || '❓'}</div>
                      <div style={S.catName}>{cat.name}</div>
                      <div style={S.catDesc}>{cat.description}</div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* FASE 2 y 3: Chat */}
            {phase === 'chat' && (
              <>
                {messages.map((msg) => (
                  <div key={msg.message_id} style={S.msgRow(msg.sender_type)}>
                    {msg.sender_type !== 'user' && msg.sender_type !== 'system' && (
                      <div style={S.msgAvatar(msg.sender_type)}>
                        {msg.sender_type === 'ai' ? <Bot size={14} color="#00ff88" />
                          : <Headset size={14} color="#60a5fa" />}
                      </div>
                    )}
                    <div style={S.msgBubble(msg.sender_type)}>
                      {msg.sender_type === 'staff' && msg.sender_name && (
                        <div style={{ fontSize: 9, color: '#60a5fa', fontWeight: 700, marginBottom: 4 }}>
                          {msg.sender_name}
                        </div>
                      )}
                      {msg.content}
                      <div style={{ fontSize: 9, color: '#555', marginTop: 4, textAlign: msg.sender_type === 'user' ? 'right' : 'left' }}>
                        {new Date(msg.created_at).toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                  </div>
                ))}

                {/* Indicador de escritura */}
                {aiTyping && (
                  <div style={S.msgRow('ai')}>
                    <div style={S.msgAvatar('ai')}><Bot size={14} color="#00ff88" /></div>
                    <div style={{ ...S.msgBubble('ai'), padding: '0.6rem 0.875rem' }}>
                      <div className="ai-typing-dots" style={{ color: '#666', fontSize: 16 }}>
                        <span>●</span><span>●</span><span>●</span>
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* FOOTER */}
          {phase === 'chat' && ticketStatus !== 'resolved' && ticketStatus !== 'closed' && (
            <div style={S.footer}>
              <div style={S.inputRow}>
                <textarea
                  ref={textareaRef}
                  className="support-textarea"
                  style={S.textarea}
                  placeholder={loading ? 'Analizando...' : 'Escribí tu mensaje...'}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  disabled={loading}
                  rows={1}
                />
                <button
                  className="support-send-btn"
                  style={{ ...S.sendBtn, opacity: (loading || sending || !input.trim()) ? 0.5 : 1 }}
                  onClick={handleSend}
                  disabled={loading || sending || !input.trim()}
                >
                  {sending ? <Loader size={14} color="#000" className="animate-spin" /> : <Send size={14} color="#000" />}
                </button>
              </div>

              {/* Botones de acción */}
              {ticketId && ticketStatus !== 'in_progress' && ticketStatus !== 'waiting' && (
                <button className="support-escalate-btn" style={S.escalateBtn} onClick={handleEscalate}>
                  <Headset size={12} /> Hablar con un colaborador
                </button>
              )}
              {ticketId && (
                <button className="support-resolve-btn" style={S.resolveBtn} onClick={handleResolve}>
                  <CheckCircle size={12} /> Esto resolvió mi problema ✓
                </button>
              )}
            </div>
          )}

          {/* Ticket resuelto */}
          {(ticketStatus === 'resolved' || ticketStatus === 'closed') && (
            <div style={{ ...S.footer, textAlign: 'center', color: '#00ff88', fontSize: 12 }}>
              <CheckCircle size={16} style={{ marginBottom: 4 }} />
              <div style={{ fontWeight: 700 }}>Ticket resuelto</div>
              <div style={{ color: '#666', fontSize: 11, marginTop: 4 }}>
                Podés ver el historial en la sección Soporte del menú.
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default SupportChat;
