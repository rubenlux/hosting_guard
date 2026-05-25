import { useState } from 'react';
import {
  CreditCard, Zap, Check, Clock, ExternalLink,
  AlertTriangle, ChevronRight, Loader2, CalendarCheck, Building2,
} from 'lucide-react';
import { createBillingCheckout } from '../../../services/api';

// ── Plan catalog ──────────────────────────────────────────────────────────────
const PLANS = {
  free: {
    label: 'Prueba Gratis', color: '#666', priceAnnual: 0, priceMonthly: 0,
    features: ['1 sitio web', 'Subdominio incluido', 'WordPress one-click', 'SSL automático', 'IA Advisory básico (10 consultas/mes)', 'Soporte por email'],
  },
  personal: {
    label: 'Personal', color: '#60a5fa', priceAnnual: 9, priceMonthly: 15,
    features: ['1 sitio web', 'Subdominio incluido', 'WordPress one-click', 'SSL automático', 'IA Advisory básico (20 consultas/mes)', 'Backups semanales (2 GB)', 'Soporte por email', 'Uso justo incluido'],
  },
  negocio: {
    label: 'Negocio', color: '#a78bfa', priceAnnual: 19, priceMonthly: 25,
    features: ['3 sitios web', 'Subdominio incluido', 'Dominio propio (opcional)', 'WordPress one-click', 'SSL automático', 'IA Advisory avanzado (100 consultas/mes)', 'Backups diarios (10 GB)', 'Soporte prioritario', 'Uso justo incluido'],
  },
  agencia: {
    label: 'Agencia', color: '#f59e0b', priceAnnual: 39, priceMonthly: 50,
    features: ['Hasta 10 sitios web', 'Subdominios incluidos', 'Dominios propios (opcional)', 'WordPress one-click', 'SSL automático', 'IA Advisory premium (300 consultas/mes)', 'Backups diarios (30 GB)', 'Soporte prioritario', 'API access', 'Uso justo incluido'],
  },
  agencia_pro: {
    label: 'Agencia Pro', color: '#f97316', priceAnnual: 59, priceMonthly: 75,
    features: ['Hasta 25 sitios web', 'Subdominios incluidos', 'Dominios propios (opcional)', 'WordPress one-click', 'SSL automático', 'IA Advisory premium ampliado (700 consultas/mes)', 'Backups diarios con mayor retención (75 GB)', 'Soporte prioritario avanzado', 'API access', 'Monitoreo avanzado', 'Reportes de salud', 'Uso justo incluido'],
  },
  // Legacy aliases
  basic: null, pro: null, business: null,
};

const ENTERPRISE = {
  annual:  { id: 'enterprise_annual',  price: '$99',  note: '$1.188/año', cta: 'Elegir Enterprise Anual' },
  monthly: { id: 'enterprise_monthly', price: '$129', note: null,         cta: 'Elegir Enterprise Mensual' },
};

const ENTERPRISE_FEATURES = [
  'Hasta 50 sitios web', 'Soporte prioritario dedicado', 'Monitoreo avanzado',
  'Onboarding asistido', 'API access', 'Recursos ampliados',
  'Backups avanzados (200 GB)', 'Auditoría y reportes', 'Consultoría técnica',
  'Plan personalizado disponible', 'Uso justo incluido',
];

// Normalize legacy / monthly plan names → base slug
const normalizePlan = (plan) => {
  if (!plan) return 'free';
  if (plan === 'basic')    return 'personal';
  if (plan === 'pro')      return 'negocio';
  if (plan === 'business') return 'agencia';
  // Strip _monthly suffix so PLANS lookup always works
  if (plan.endsWith('_monthly')) return plan.replace('_monthly', '');
  return plan;
};

const PLAN_ORDER = ['free', 'personal', 'negocio', 'agencia', 'agencia_pro', 'enterprise'];

const STATUS_LABELS = {
  active:    { label: 'Activa',          color: '#10b981' },
  cancelled: { label: 'Cancelada',       color: '#f59e0b' },
  past_due:  { label: 'Pago pendiente',  color: '#ef4444' },
  expired:   { label: 'Expirada',        color: '#ef4444' },
  paused:    { label: 'Pausada',         color: '#888'    },
  none:      { label: 'Sin suscripción', color: '#555'    },
};

const fmt = (iso) =>
  iso ? new Date(iso).toLocaleDateString('es', { day: '2-digit', month: 'short', year: 'numeric' }) : null;

// ── BillingSection ────────────────────────────────────────────────────────────

const BillingSection = ({ user = {}, onTopup, onToggleAutoscale, userActionLoading }) => {
  // Pre-select interval based on user's current billing_interval
  const [upgrading,       setUpgrading]       = useState(null);
  const [billingInterval, setBillingInterval] = useState(
    () => user?.billing_interval === 'monthly' ? 'monthly' : 'annual'
  );

  const isMonthly = billingInterval === 'monthly';

  const currentPlanSlug = normalizePlan(user.plan);
  const currentPlan     = PLANS[currentPlanSlug] || PLANS.free;
  const subStatus       = user.subscription_status || 'none';
  const statusInfo      = STATUS_LABELS[subStatus] || STATUS_LABELS.none;
  const periodEnd       = user.current_period_end ? fmt(user.current_period_end) : null;
  const portalUrl       = user.billing_portal_url;
  const isPaid          = currentPlanSlug !== 'free';
  const currentIdx      = PLAN_ORDER.indexOf(currentPlanSlug);

  const eb = ENTERPRISE[billingInterval];

  const handleUpgrade = async (plan) => {
    try {
      setUpgrading(plan);
      const { url } = await createBillingCheckout(plan);
      window.location.href = url;
    } catch (err) {
      console.error('Checkout error:', err);
      setUpgrading(null);
    }
  };

  return (
    <div style={{ maxWidth: 820, margin: '0 auto', paddingBottom: 48 }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginBottom: 4 }}>Facturación</div>
        <div style={{ fontSize: 13, color: '#555' }}>Sin cargos ocultos · Cancela cuando quieras</div>
      </div>

      {/* Current plan banner */}
      <div style={{
        background: '#111',
        border: `1px solid ${currentPlan.color}25`,
        borderRadius: 16,
        padding: '20px 24px',
        marginBottom: 16,
        position: 'relative',
        overflow: 'hidden',
      }}>
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: `linear-gradient(90deg, ${currentPlan.color}, ${currentPlan.color}60)` }} />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div>
              <div style={{ fontSize: 11, color: '#555', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 3 }}>Plan actual</div>
              <div style={{ fontSize: 24, fontWeight: 900, color: currentPlan.color }}>{currentPlan.label}</div>
            </div>
            {subStatus !== 'none' && (
              <span style={{
                fontSize: 11, fontWeight: 700, padding: '4px 10px', borderRadius: 20,
                background: `${statusInfo.color}15`, color: statusInfo.color,
                border: `1px solid ${statusInfo.color}30`,
              }}>
                {statusInfo.label}
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {periodEnd && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <CalendarCheck size={13} color="#555" />
                <span style={{ fontSize: 12, color: subStatus === 'cancelled' ? '#f59e0b' : '#666' }}>
                  {subStatus === 'cancelled' ? `Activo hasta ${periodEnd}` : `Renueva ${periodEnd}`}
                </span>
              </div>
            )}
            {portalUrl && isPaid && (
              <a
                href={portalUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  fontSize: 12, fontWeight: 600, color: '#888',
                  padding: '7px 12px', borderRadius: 8,
                  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
                  textDecoration: 'none',
                }}
              >
                <ExternalLink size={12} /> Administrar suscripción
              </a>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 20px', marginTop: 14 }}>
          {currentPlan.features.map(f => (
            <div key={f} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Check size={11} color={currentPlan.color} />
              <span style={{ fontSize: 12, color: '#888' }}>{f}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Trial warning */}
      {currentPlanSlug === 'free' && user.plan_expires_at && (() => {
        const daysLeft = Math.ceil((new Date(user.plan_expires_at) - Date.now()) / 86400000);
        if (daysLeft > 14 || daysLeft < 0) return null;
        return (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)',
            borderRadius: 10, padding: '10px 16px', marginBottom: 16,
          }}>
            <Clock size={14} color="#f59e0b" />
            <span style={{ fontSize: 12, color: '#d97706' }}>
              Tu prueba gratuita {daysLeft <= 0 ? 'ha vencido' : `vence en ${daysLeft} día${daysLeft !== 1 ? 's' : ''}`}.
              Elegí un plan para continuar sin interrupciones.
            </span>
          </div>
        );
      })()}

      {/* Payment failed warning */}
      {subStatus === 'past_due' && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)',
          borderRadius: 10, padding: '10px 16px', marginBottom: 16,
        }}>
          <AlertTriangle size={14} color="#ef4444" />
          <span style={{ fontSize: 12, color: '#ef4444' }}>
            Hay un problema con tu pago. Actualizá tu método de pago para evitar la suspensión.
            {portalUrl && <a href={portalUrl} target="_blank" rel="noopener noreferrer" style={{ marginLeft: 6, color: '#ef4444', fontWeight: 700 }}>Actualizar →</a>}
          </span>
        </div>
      )}

      {/* ── Global billing interval toggle ────────────────────────────────── */}
      <div style={{ marginTop: 24, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#444', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          Facturación
        </span>
        <div style={{
          display: 'flex', borderRadius: 8, overflow: 'hidden',
          border: '1px solid rgba(255,255,255,0.1)', fontSize: 12,
        }}>
          {[['annual', 'Anual'], ['monthly', 'Mensual']].map(([k, label]) => (
            <button
              key={k}
              onClick={() => setBillingInterval(k)}
              style={{
                padding: '6px 18px', fontWeight: 700, cursor: 'pointer', border: 'none',
                background: billingInterval === k ? '#60a5fa' : 'transparent',
                color: billingInterval === k ? '#000' : '#555',
                transition: 'all 0.15s',
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {!isMonthly && (
          <span style={{ fontSize: 11, color: '#10b981', fontWeight: 700 }}>Ahorrá ~25%</span>
        )}
      </div>

      {/* ── Upgrade plans grid ────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 }}>
        {['personal', 'negocio', 'agencia', 'agencia_pro'].map((slug) => {
          const plan         = PLANS[slug];
          const planIdx      = PLAN_ORDER.indexOf(slug);
          const checkoutSlug = isMonthly ? `${slug}_monthly` : slug;
          const isCurrent    = slug === currentPlanSlug;
          const isDowngrade  = planIdx < currentIdx;
          const displayPrice = isMonthly ? plan.priceMonthly : plan.priceAnnual;
          const billingNote  = isMonthly
            ? 'Pago mensual automático'
            : `$${plan.priceAnnual * 12} USD facturado anualmente`;

          return (
            <div key={slug} style={{
              background: isCurrent ? `${plan.color}08` : '#0e0e0e',
              border: `1px solid ${isCurrent ? plan.color + '35' : 'rgba(255,255,255,0.07)'}`,
              borderRadius: 14, padding: '20px', position: 'relative', overflow: 'hidden',
              transition: 'border-color 0.2s',
            }}>
              {slug === 'negocio' && (
                <div style={{
                  position: 'absolute', top: 10, right: 10,
                  fontSize: 9, fontWeight: 800, padding: '3px 8px', borderRadius: 20,
                  background: `${plan.color}20`, color: plan.color, border: `1px solid ${plan.color}40`,
                  letterSpacing: '0.05em',
                }}>
                  MÁS POPULAR
                </div>
              )}

              <div style={{ fontSize: 14, fontWeight: 800, color: plan.color, marginBottom: 4 }}>{plan.label}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 2 }}>
                <span style={{ fontSize: 26, fontWeight: 900, color: '#fff' }}>${displayPrice}</span>
                <span style={{ fontSize: 11, color: '#555' }}>/mes</span>
              </div>
              <div style={{ fontSize: 11, color: '#444', marginBottom: 14 }}>
                {billingNote}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 16 }}>
                {plan.features.slice(0, 5).map(f => (
                  <div key={f} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                    <Check size={11} color={isCurrent ? plan.color : '#444'} />
                    <span style={{ fontSize: 11, color: isCurrent ? '#aaa' : '#555' }}>{f}</span>
                  </div>
                ))}
              </div>

              {isCurrent ? (
                <div style={{
                  width: '100%', padding: '8px', borderRadius: 8, textAlign: 'center',
                  background: `${plan.color}10`, border: `1px solid ${plan.color}30`,
                  color: plan.color, fontSize: 12, fontWeight: 700,
                }}>
                  Plan actual
                </div>
              ) : isDowngrade ? (
                <div style={{
                  width: '100%', padding: '8px', borderRadius: 8, textAlign: 'center',
                  background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
                  color: '#444', fontSize: 12, fontWeight: 600, cursor: 'default',
                }}>
                  Plan inferior
                </div>
              ) : (
                <button
                  onClick={() => handleUpgrade(checkoutSlug)}
                  disabled={upgrading !== null}
                  style={{
                    width: '100%', padding: '9px', borderRadius: 8, cursor: upgrading ? 'wait' : 'pointer',
                    background: slug === 'negocio' ? plan.color : `${plan.color}18`,
                    border: `1px solid ${plan.color}${slug === 'negocio' ? '' : '40'}`,
                    color: slug === 'negocio' ? '#000' : plan.color,
                    fontSize: 12, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                    opacity: upgrading && upgrading !== checkoutSlug ? 0.5 : 1,
                    transition: 'opacity 0.15s',
                  }}
                >
                  {upgrading === checkoutSlug
                    ? <><Loader2 size={12} className="animate-spin" /> Abriendo checkout…</>
                    : <>Elegir {plan.label} <ChevronRight size={12} /></>
                  }
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Enterprise block ───────────────────────────────────────────────── */}
      {(() => {
        const isEnterp = currentPlanSlug === 'enterprise';
        return (
          <div style={{
            marginTop: 12,
            background: isEnterp ? 'rgba(0,255,136,0.04)' : '#0e0e0e',
            border: `1px solid ${isEnterp ? 'rgba(0,255,136,0.25)' : 'rgba(255,255,255,0.07)'}`,
            borderRadius: 14, padding: '20px 24px',
            display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'flex-start',
          }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <Building2 size={16} color="#00ff88" />
                <span style={{ fontSize: 16, fontWeight: 800, color: '#fff' }}>Enterprise</span>
              </div>
              <div style={{ fontSize: 12, color: '#555', marginBottom: 14 }}>
                Para organizaciones con necesidades avanzadas de infraestructura, seguridad y soporte.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px' }}>
                {ENTERPRISE_FEATURES.map(f => (
                  <div key={f} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Check size={10} color={isEnterp ? '#00ff88' : '#444'} />
                    <span style={{ fontSize: 11, color: isEnterp ? '#aaa' : '#555' }}>{f}</span>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 12, minWidth: 180 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                  <span style={{ fontSize: 28, fontWeight: 900, color: '#fff' }}>{eb.price}</span>
                  <span style={{ fontSize: 11, color: '#555' }}>/mes</span>
                </div>
                {eb.note && (
                  <div style={{ fontSize: 11, color: '#444', textAlign: 'right' }}>{eb.note}</div>
                )}
              </div>

              {isEnterp ? (
                <div style={{
                  padding: '8px 20px', borderRadius: 8, textAlign: 'center',
                  background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.3)',
                  color: '#00ff88', fontSize: 12, fontWeight: 700,
                }}>
                  Plan actual
                </div>
              ) : (
                <button
                  onClick={() => handleUpgrade(eb.id)}
                  disabled={upgrading !== null}
                  style={{
                    padding: '9px 20px', borderRadius: 8, cursor: upgrading ? 'wait' : 'pointer',
                    background: 'rgba(0,255,136,0.08)', border: '1px solid rgba(0,255,136,0.25)',
                    color: '#00ff88', fontSize: 12, fontWeight: 700,
                    display: 'flex', alignItems: 'center', gap: 6,
                    opacity: upgrading && upgrading !== eb.id ? 0.5 : 1,
                    transition: 'opacity 0.15s',
                  }}
                >
                  {upgrading === eb.id
                    ? <><Loader2 size={12} className="animate-spin" /> Abriendo checkout…</>
                    : <>{eb.cta} <ChevronRight size={12} /></>
                  }
                </button>
              )}
            </div>
          </div>
        );
      })()}

      {/* ── Autoscale toggle ──────────────────────────────────────────────── */}
      <div
        onClick={!userActionLoading && isPaid ? onToggleAutoscale : undefined}
        style={{
          marginTop: 20,
          background: '#111',
          border: `1px solid ${user.autoscale_enabled ? 'rgba(0,255,136,0.2)' : 'rgba(255,255,255,0.06)'}`,
          borderRadius: 14, padding: '16px 20px',
          display: 'flex', alignItems: 'center', gap: 14,
          cursor: isPaid ? 'pointer' : 'default',
          opacity: isPaid ? 1 : 0.4,
          transition: 'border-color 0.2s',
        }}
      >
        <div style={{
          width: 38, height: 38, borderRadius: 10, flexShrink: 0,
          background: user.autoscale_enabled ? 'rgba(0,255,136,0.1)' : 'rgba(255,255,255,0.04)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Zap size={17} color={user.autoscale_enabled ? '#00ff88' : '#555'} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', marginBottom: 2 }}>Auto-Scaling</div>
          <div style={{ fontSize: 11, color: '#555' }}>
            {isPaid
              ? 'Optimiza recursos automáticamente según la demanda real de tu sitio.'
              : 'Disponible en planes pagos.'}
          </div>
        </div>
        <div style={{
          width: 42, height: 22, borderRadius: 11, flexShrink: 0,
          background: user.autoscale_enabled && isPaid ? '#00ff88' : 'rgba(255,255,255,0.1)',
          position: 'relative', transition: 'background 0.2s',
        }}>
          <div style={{
            position: 'absolute', top: 3,
            left: user.autoscale_enabled && isPaid ? 21 : 3,
            width: 16, height: 16, borderRadius: '50%', background: '#fff',
            transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.4)',
          }} />
        </div>
      </div>

      {/* ── Card brands footer ────────────────────────────────────────────── */}
      <div style={{ marginTop: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
        <CreditCard size={14} color="#333" />
        <span style={{ fontSize: 11, color: '#333' }}>Pago seguro procesado por MercadoPago · Visa · Mastercard · Amex</span>
      </div>
    </div>
  );
};

export default BillingSection;
