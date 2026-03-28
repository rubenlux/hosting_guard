import React from 'react';
import { CheckCircle2 } from 'lucide-react';
import SectionHeading from './SectionHeading';

const Pricing = () => {
    const plans = [
      {
        name: "Starter",
        price: "9",
        color: "gray",
        id: "starter",
        features: ["1 Sitio Web", "SSL Automático", "Subdominio Incluido", "Hosting Nginx base"]
      },
      {
        name: "Pro",
        price: "15",
        color: "primary",
        id: "pro",
        popular: true,
        features: ["5 Sitios Web", "Recursos dedicados (0.5 CPU)", "Dominio Personalizado", "Soporte Prioritario"]
      },
      {
        name: "Business",
        price: "25",
        color: "secondary",
        id: "business",
        features: ["Sitios Ilimitados", "Infraestructura Cloud", "1 GB RAM dedicado", "API Access"]
      }
    ];
  
    return (
      <section id="pricing" className="py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <SectionHeading title="Planes simples y transparentes" subtitle="Sin cargos ocultos ni sorpresas en tu factura." />
          <div className="grid md:grid-cols-3 gap-8">
            {plans.map((plan, i) => (
              <div
                key={i}
                className={`glass-card p-10 rounded-2xl border-t-4 flex flex-col ${plan.popular ? 'border-t-primary relative' : 'border-t-white/10'}`}
              >
                {plan.popular && (
                  <span className="absolute -top-4 left-1/2 -translate-x-1/2 bg-primary text-background text-xs font-bold px-4 py-1.5 rounded-full uppercase tracking-widest leading-none">
                    Más Popular
                  </span>
                )}
                <h3 className="text-2xl font-bold mb-2">{plan.name}</h3>
                <div className="flex items-baseline gap-1 mb-8">
                  <span className="text-4xl font-extrabold text-white">${plan.price}</span>
                  <span className="text-gray-500">/mes</span>
                </div>
                <ul className="space-y-4 mb-10 flex-1">
                  {plan.features.map((f, j) => (
                    <li key={j} className="flex items-center gap-3 text-gray-400 text-sm">
                      <CheckCircle2 className="text-primary w-5 h-5 flex-shrink-0" /> {f}
                    </li>
                  ))}
                </ul>
                <a href="#create" className={`w-full py-4 rounded-xl font-bold transition-all text-center ${plan.popular ? 'bg-primary text-background glow-primary' : 'bg-white/10 text-white hover:bg-white/20'}`}>
                  Elegir {plan.name}
                </a>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  };

  export default Pricing;
