import React, { useState } from 'react';
import { CheckCircle2, Building2 } from 'lucide-react';

const PLANS = [
  {
    id: 'free',
    name: 'Prueba Gratis',
    price: '$0',
    period: '14 días',
    annual: null,
    desc: 'Sin tarjeta. Probá todo sin compromiso.',
    highlight: false,
    badge: '14 DÍAS GRATIS',
    features: [
      '1 sitio web',
      'Subdominio incluido',
      'WordPress one-click',
      'SSL automático',
      'IA Advisory básico (10 consultas/mes)',
      'Soporte por email',
    ],
    missing: ['Backups', 'Dominio propio', 'Soporte prioritario'],
    cta: 'Empezar Gratis',
  },
  {
    id: 'personal',
    name: 'Personal',
    price: '$9',
    period: '/mes',
    annual: 'Facturado anual: $108/año',
    desc: 'Ideal para blogs, portfolios y landing pages.',
    highlight: false,
    badge: null,
    features: [
      '1 sitio web',
      'Subdominio incluido',
      'WordPress one-click',
      'SSL automático',
      'IA Advisory básico (20 consultas/mes)',
      'Backups semanales (2 GB)',
      'Soporte por email',
      'Uso justo incluido',
    ],
    missing: [],
    cta: 'Elegir Personal',
  },
  {
    id: 'negocio',
    name: 'Negocio',
    price: '$19',
    period: '/mes',
    annual: 'Facturado anual: $228/año',
    desc: 'Para tiendas online y empresas en crecimiento.',
    highlight: true,
    badge: 'MÁS POPULAR',
    features: [
      '3 sitios web',
      'Subdominio incluido',
      'Dominio propio (opcional)',
      'WordPress one-click',
      'SSL automático',
      'IA Advisory avanzado (100 consultas/mes)',
      'Backups diarios (10 GB)',
      'Soporte prioritario',
      'Uso justo incluido',
    ],
    missing: [],
    cta: 'Elegir Negocio',
  },
  {
    id: 'agencia',
    name: 'Agencia',
    price: '$39',
    period: '/mes',
    annual: 'Facturado anual: $468/año',
    desc: 'Para agencias y desarrolladores con múltiples clientes.',
    highlight: false,
    badge: null,
    features: [
      'Hasta 10 sitios web',
      'Subdominios incluidos',
      'Dominios propios (opcional)',
      'WordPress one-click',
      'SSL automático',
      'IA Advisory premium (300 consultas/mes)',
      'Backups diarios (30 GB)',
      'Soporte prioritario',
      'API access',
      'Uso justo incluido',
    ],
    missing: [],
    cta: 'Elegir Agencia',
  },
  {
    id: 'agencia_pro',
    name: 'Agencia Pro',
    price: '$59',
    period: '/mes',
    annual: 'Facturado anual: $708/año',
    desc: 'Máximo rendimiento para agencias en escala.',
    highlight: false,
    badge: null,
    features: [
      'Hasta 25 sitios web',
      'Subdominios incluidos',
      'Dominios propios (opcional)',
      'WordPress one-click',
      'SSL automático',
      'IA Advisory premium ampliado (700 consultas/mes)',
      'Backups diarios con mayor retención (75 GB)',
      'Soporte prioritario avanzado',
      'API access',
      'Monitoreo avanzado',
      'Reportes de salud',
      'Uso justo incluido',
    ],
    missing: [],
    cta: 'Elegir Agencia Pro',
  },
];

const ENTERPRISE_BILLING = {
  annual: {
    id: 'enterprise_annual',
    price: '$99',
    note: 'Facturado anual: $1.188/año',
    cta: 'Elegir Enterprise Anual',
  },
  monthly: {
    id: 'enterprise_monthly',
    price: '$129',
    note: 'Pago mensual — sin compromiso anual',
    cta: 'Elegir Enterprise Mensual',
  },
};

const ENTERPRISE_FEATURES = [
  'Hasta 50 sitios web',
  'Recursos ampliados',
  'Soporte prioritario dedicado',
  'Backups avanzados (200 GB)',
  'Monitoreo avanzado',
  'Auditoría y reportes',
  'Onboarding asistido',
  'Consultoría técnica',
  'API access',
  'Plan personalizado disponible',
  'Uso justo incluido',
];

const Pricing = ({ onSelectPlan }) => {
  const [enterpriseBilling, setEnterpriseBilling] = useState('annual');
  const eb = ENTERPRISE_BILLING[enterpriseBilling];

  return (
    <section className="py-24 px-4" id="pricing">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-4xl md:text-5xl font-black mb-4">
            Planes simples y transparentes
          </h2>
          <p className="text-gray-400 text-lg">
            Sin cargos ocultos ni sorpresas en tu factura.
          </p>
        </div>

        {/* ── Standard plans ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-5 mb-6">
          {PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`relative rounded-3xl border p-6 flex flex-col gap-4 transition-all ${
                plan.highlight
                  ? 'border-primary bg-primary/5 shadow-2xl shadow-primary/10 scale-[1.02]'
                  : 'border-white/10 bg-surface hover:border-white/20'
              }`}
            >
              {plan.badge && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="bg-primary text-background text-[10px] font-black px-4 py-1 rounded-full tracking-widest">
                    {plan.badge}
                  </span>
                </div>
              )}

              <div>
                <h3 className="text-lg font-black mb-1">{plan.name}</h3>
                <div className="flex items-baseline gap-1 mb-1">
                  <span className="text-3xl font-black text-primary">{plan.price}</span>
                  <span className="text-gray-500 text-sm">{plan.period}</span>
                </div>
                {plan.annual && (
                  <p className="text-[11px] text-gray-600">{plan.annual}</p>
                )}
                <p className="text-gray-500 text-xs leading-relaxed mt-2">{plan.desc}</p>
              </div>

              <ul className="flex flex-col gap-2 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-xs text-gray-300">
                    <CheckCircle2 className="w-3.5 h-3.5 text-primary flex-shrink-0 mt-0.5" />
                    {f}
                  </li>
                ))}
                {plan.missing.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-xs text-gray-600 line-through">
                    <CheckCircle2 className="w-3.5 h-3.5 text-gray-700 flex-shrink-0 mt-0.5" />
                    {f}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => onSelectPlan && onSelectPlan(plan.id)}
                className={`w-full py-3 rounded-2xl font-black text-sm transition-all ${
                  plan.highlight
                    ? 'bg-primary text-background hover:scale-[1.02] shadow-lg shadow-primary/30'
                    : 'bg-white/5 border border-white/10 text-white hover:bg-white/10'
                }`}
              >
                {plan.cta}
              </button>
            </div>
          ))}
        </div>

        {/* ── Enterprise card ── */}
        <div className="rounded-3xl border border-white/10 bg-surface p-6 flex flex-col md:flex-row gap-6 items-start">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <Building2 className="w-5 h-5 text-primary" />
              <h3 className="text-xl font-black">Enterprise</h3>
            </div>
            <p className="text-gray-500 text-sm mb-4">
              Para organizaciones con necesidades avanzadas de infraestructura, seguridad y soporte.
            </p>
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2">
              {ENTERPRISE_FEATURES.map((f) => (
                <li key={f} className="flex items-start gap-2 text-xs text-gray-300">
                  <CheckCircle2 className="w-3.5 h-3.5 text-primary flex-shrink-0 mt-0.5" />
                  {f}
                </li>
              ))}
            </ul>
          </div>

          <div className="flex flex-col gap-3 md:w-56 shrink-0">
            {/* Annual / Monthly toggle */}
            <div className="flex rounded-xl overflow-hidden border border-white/10 text-sm">
              <button
                onClick={() => setEnterpriseBilling('annual')}
                className={`flex-1 py-2 font-bold transition-all ${
                  enterpriseBilling === 'annual'
                    ? 'bg-primary text-background'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                Anual
              </button>
              <button
                onClick={() => setEnterpriseBilling('monthly')}
                className={`flex-1 py-2 font-bold transition-all ${
                  enterpriseBilling === 'monthly'
                    ? 'bg-primary text-background'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                Mensual
              </button>
            </div>

            <div className="text-center py-2">
              <div className="flex items-baseline justify-center gap-1">
                <span className="text-4xl font-black text-primary">{eb.price}</span>
                <span className="text-gray-500 text-sm">/mes</span>
              </div>
              <p className="text-[11px] text-gray-600 mt-1">{eb.note}</p>
            </div>

            <button
              onClick={() => onSelectPlan && onSelectPlan(eb.id)}
              className="w-full py-3 rounded-2xl font-black text-sm bg-white/5 border border-white/10 text-white hover:bg-white/10 transition-all"
            >
              {eb.cta}
            </button>
          </div>
        </div>

        {/* Legal disclaimer */}
        <div className="mt-8 space-y-2 text-center">
          <p className="text-gray-600 text-xs max-w-2xl mx-auto">
            Todos los planes incluyen uso justo de recursos. Si un sitio requiere más capacidad,
            te avisamos antes de recomendar un upgrade o recursos dedicados.
          </p>
          <p className="text-gray-600 text-xs">
            El plan Prueba Gratis expira a los 14 días. No se requiere tarjeta de crédito.
          </p>
        </div>
      </div>
    </section>
  );
};

export default Pricing;
