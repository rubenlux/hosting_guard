import { useState } from 'react';
import { CreditCard, Zap, TrendingUp, Plus, AlertTriangle, Check, Clock } from 'lucide-react';

const PLAN_FEATURES = {
  free:    { label: 'Free', color: '#888',     features: ['1 sitio WordPress', '512 MB RAM', 'Subdominio .hostingguard.lat', 'SSL gratuito'] },
  basic:   { label: 'Basic', color: '#60a5fa',  features: ['3 sitios WordPress', '1 GB RAM', 'Dominio propio', 'SSL + Backups diarios'] },
  pro:     { label: 'Pro', color: '#818cf8',    features: ['10 sitios', '2 GB RAM', 'Prioridad en soporte', 'Backups horarios + CDN'] },
  business:{ label: 'Business', color: '#f59e0b', features: ['Sitios ilimitados', '4 GB RAM', 'SLA 99.9%', 'Soporte dedicado'] },
};

const BillingSection = ({ user = {}, onTopup, onToggleAutoscale, userActionLoading }) => {
  const plan = PLAN_FEATURES[user.plan] || PLAN_FEATURES.free;
  const expiresAt = user.plan_expires_at ? new Date(user.plan_expires_at) : null;
  const daysLeft = expiresAt ? Math.ceil((expiresAt - Date.now()) / 86400000) : null;
  const balance = parseFloat(user.balance || 0);

  const fmt = (d) => d.toLocaleDateString('es', { day: '2-digit', month: 'short', year: 'numeric' });

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginBottom: 6 }}>Facturación</div>
        <div style={{ fontSize: 13, color: '#666' }}>Tu plan, saldo y métodos de pago.</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        {/* Plan card */}
        <div style={{ background: '#111', border: `1px solid ${plan.color}22`, borderRadius: 16, padding: '24px', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: `linear-gradient(90deg, ${plan.color}, ${plan.color}88)` }} />
          <div style={{ fontSize: 10, fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>Plan actual</div>
          <div style={{ fontSize: 28, fontWeight: 900, color: plan.color, marginBottom: 4 }}>{plan.label}</div>
          {expiresAt && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}>
              <Clock size={11} color={daysLeft <= 3 ? '#ef4444' : '#888'} />
              <span style={{ fontSize: 11, color: daysLeft <= 3 ? '#ef4444' : '#888' }}>
                {daysLeft <= 0 ? 'Expirado' : `Vence en ${daysLeft} días — ${fmt(expiresAt)}`}
              </span>
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: expiresAt ? 0 : 12 }}>
            {plan.features.map(f => (
              <div key={f} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Check size={12} color={plan.color} />
                <span style={{ fontSize: 12, color: '#aaa' }}>{f}</span>
              </div>
            ))}
          </div>
          <button style={{ marginTop: 20, width: '100%', padding: '9px', background: `${plan.color}18`, border: `1px solid ${plan.color}30`, borderRadius: 8, color: plan.color, fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
            <TrendingUp size={12} style={{ display: 'inline', marginRight: 6, verticalAlign: 'middle' }} />
            Mejorar plan
          </button>
        </div>

        {/* Balance card */}
        <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, padding: '24px', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: 'linear-gradient(90deg, #818cf8, #60a5fa)' }} />
          <div style={{ fontSize: 10, fontWeight: 700, color: '#888', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>Saldo disponible</div>
          <div style={{ fontSize: 36, fontWeight: 900, color: '#fff', marginBottom: 4 }}>${balance.toFixed(2)}</div>
          <div style={{ fontSize: 11, color: '#555', marginBottom: 20 }}>USD · Se descuenta automáticamente por uso</div>

          {balance <= 5 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, padding: '8px 12px', marginBottom: 16 }}>
              <AlertTriangle size={12} color="#ef4444" />
              <span style={{ fontSize: 11, color: '#ef4444' }}>Saldo bajo. Recargá para evitar suspensiones.</span>
            </div>
          )}

          <button
            onClick={onTopup}
            disabled={userActionLoading}
            style={{ width: '100%', padding: '10px', background: 'linear-gradient(135deg, #818cf8, #6366f1)', border: 'none', borderRadius: 8, color: '#fff', fontSize: 13, fontWeight: 700, cursor: userActionLoading ? 'wait' : 'pointer', opacity: userActionLoading ? 0.7 : 1, transition: 'opacity 0.2s' }}
          >
            <Plus size={13} style={{ display: 'inline', marginRight: 6, verticalAlign: 'middle' }} />
            {userActionLoading ? 'Procesando...' : 'Recargar $10'}
          </button>
        </div>
      </div>

      {/* Autoscale toggle */}
      <div
        onClick={!userActionLoading ? onToggleAutoscale : undefined}
        style={{ background: '#111', border: `1px solid ${user.autoscale_enabled ? 'rgba(0,255,136,0.2)' : 'rgba(255,255,255,0.08)'}`, borderRadius: 14, padding: '18px 24px', display: 'flex', alignItems: 'center', gap: 16, cursor: 'pointer', marginBottom: 16, transition: 'border-color 0.2s' }}
      >
        <div style={{ width: 40, height: 40, borderRadius: 10, background: user.autoscale_enabled ? 'rgba(0,255,136,0.1)' : 'rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Zap size={18} color={user.autoscale_enabled ? '#00ff88' : '#555'} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', marginBottom: 2 }}>Auto-Scaling</div>
          <div style={{ fontSize: 11, color: '#666' }}>Optimiza recursos automáticamente según la demanda real de tu sitio.</div>
        </div>
        <div style={{ width: 44, height: 24, borderRadius: 12, background: user.autoscale_enabled ? '#00ff88' : 'rgba(255,255,255,0.1)', position: 'relative', transition: 'background 0.2s', flexShrink: 0 }}>
          <div style={{ position: 'absolute', top: 3, left: user.autoscale_enabled ? 23 : 3, width: 18, height: 18, borderRadius: '50%', background: '#fff', transition: 'left 0.2s', boxShadow: '0 1px 4px rgba(0,0,0,0.3)' }} />
        </div>
      </div>

      {/* Payment method — Próximamente */}
      <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, padding: '24px', opacity: 0.7 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', marginBottom: 2 }}>Método de pago</div>
            <div style={{ fontSize: 11, color: '#555' }}>Tarjeta de crédito para recarga automática</div>
          </div>
          <span style={{ fontSize: 10, fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: 'rgba(129,140,248,0.1)', color: '#818cf8', border: '1px solid rgba(129,140,248,0.2)' }}>PRÓXIMAMENTE</span>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          {['Visa', 'Mastercard', 'Amex'].map(brand => (
            <div key={brand} style={{ width: 52, height: 32, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <CreditCard size={14} color="#555" />
            </div>
          ))}
        </div>

        <button disabled style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '9px 16px', color: '#555', fontSize: 12, fontWeight: 600, cursor: 'not-allowed' }}>
          <CreditCard size={14} /> Agregar tarjeta
        </button>
      </div>
    </div>
  );
};

export default BillingSection;
