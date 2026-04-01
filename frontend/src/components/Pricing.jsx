import React from 'react';
import { CheckCircle2, Zap } from 'lucide-react';

const PLANS = [
  {
    id: 'free',
    name: 'Prueba Gratis',
    price: '$0',
    period: '14 días',
    desc: 'Sin tarjeta de crédito. Probá todo sin compromiso.',
    highlight: false,
    badge: '14 DÍAS GRATIS',
    features: [
      '1 sitio web',
      'Subdominio incluido',
      'WordPress one-click',
      'SSL automático',
      'IA Advisory básico',
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
    desc: 'Ideal para blogs, portfolios y landing pages.',
    highlight: false,
    badge: null,
    features: [
      '1 sitio web',
      'Subdominio incluido',
      'WordPress one-click',
      'SSL automático',
      'IA Advisory básico',
      'Backups semanales',
      'Soporte por email',
    ],
    missing: [],
    cta: 'Elegir Personal',
  },
  {
    id: 'negocio',
    name: 'Negocio',
    price: '$19',
    period: '/mes',
    desc: 'Para tiendas online y empresas en crecimiento.',
    highlight: true,
    badge: 'MÁS POPULAR',
    features: [
      '3 sitios web',
      'Subdominio incluido',
      'Dominio propio (opcional)',
      'WordPress one-click',
      'SSL automático',
      'IA Advisory avanzado',
      'Backups diarios',
      'Soporte prioritario',
    ],
    missing: [],
    cta: 'Elegir Negocio',
  },
  {
    id: 'agencia',
    name: 'Agencia',
    price: '$39',
    period: '/mes',
    desc: 'Para agencias y desarrolladores con múltiples clientes.',
    highlight: false,
    badge: null,
    features: [
      'Sitios ilimitados',
      'Subdominios ilimitados',
      'Dominios propios (opcional)',
      'WordPress one-click',
      'SSL automático',
      'IA Advisory premium con Claude',
      'Backups diarios',
      'Soporte dedicado',
      'API access',
    ],
    missing: [],
    cta: 'Elegir Agencia',
  },
];

const Pricing = ({ onSelectPlan }) => {
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

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`relative rounded-3xl border p-6 flex flex-col gap-6 transition-all ${plan.highlight
                  ? 'border-primary bg-primary/5 shadow-2xl shadow-primary/10 scale-[1.02]'
                  : 'border-white/10 bg-surface hover:border-white/20'
                }`}
            >
              {/* Badge */}
              {plan.badge && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="bg-primary text-background text-[10px] font-black px-4 py-1 rounded-full tracking-widest">
                    {plan.badge}
                  </span>
                </div>
              )}

              {/* Header */}
              <div>
                <h3 className="text-xl font-black mb-1">{plan.name}</h3>
                <div className="flex items-baseline gap-1 mb-2">
                  <span className="text-4xl font-black text-primary">{plan.price}</span>
                  <span className="text-gray-500 text-sm">{plan.period}</span>
                </div>
                <p className="text-gray-500 text-sm leading-relaxed">{plan.desc}</p>
              </div>

              {/* Features */}
              <ul className="flex flex-col gap-2 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-gray-300">
                    <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0" />
                    {f}
                  </li>
                ))}
                {plan.missing.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-gray-600 line-through">
                    <CheckCircle2 className="w-4 h-4 text-gray-700 flex-shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>

              {/* CTA */}
              <button
                onClick={() => onSelectPlan && onSelectPlan(plan.id)}
                className={`w-full py-3 rounded-2xl font-black text-sm transition-all ${plan.highlight
                    ? 'bg-primary text-background hover:scale-[1.02] shadow-lg shadow-primary/30'
                    : plan.id === 'free'
                      ? 'bg-white/5 border border-white/10 text-white hover:bg-white/10'
                      : 'bg-white/5 border border-white/10 text-white hover:bg-white/10'
                  }`}
              >
                {plan.cta}
              </button>
            </div>
          ))}
        </div>

        {/* Free note */}
        <p className="text-center text-gray-600 text-sm mt-8">
          El plan Prueba Gratis expira a los 14 días. No se requiere tarjeta de crédito.
        </p>
      </div>
    </section>
  );
};

export default Pricing;
