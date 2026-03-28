import React from 'react';
import { Globe, Lock, Cpu, Zap } from 'lucide-react';

const Benefits = () => {
    const benefitList = [
      { title: "Dominio Incluido", icon: <Globe />, desc: "Subdominio gratuito .hostingguard.lat listo para usar." },
      { title: "SSL Gratuito (LE)", icon: <Lock />, desc: "Certificados Let's Encrypt automáticos para tu seguridad." },
      { title: "Docker Ready", icon: <Cpu />, desc: "Arquitectura basada en contenedores para máximo aislamiento." },
      { title: "Panel intuitivo", icon: <Zap />, desc: "Gestiona tu hosting sin comandos complicados." }
    ];
  
    return (
      <section id="beneficios" className="py-24 bg-surface/30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <div>
              <h2 className="text-3xl md:text-5xl font-bold mb-8 leading-tight">
                Diseñado para la <span className="text-secondary">nueva web</span>, pensado para vos.
              </h2>
              <div className="grid sm:grid-cols-2 gap-6">
                {benefitList.map((b, i) => (
                  <div key={i} className="flex gap-4 p-4 rounded-xl border border-white/5 bg-white/5">
                    <div className="text-primary mt-1">{b.icon}</div>
                    <div>
                      <h4 className="font-bold text-lg">{b.title}</h4>
                      <p className="text-sm text-gray-500">{b.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="relative">
              <div className="absolute -inset-4 bg-secondary/20 blur-3xl opacity-30 rounded-full" />
              <img
                src="https://images.unsplash.com/photo-1551288049-bebda4e38f71?q=80&w=2070&auto=format&fit=crop"
                alt="Dashboard"
                className="rounded-2xl shadow-2xl relative border border-white/10"
              />
            </div>
          </div>
        </div>
      </section>
    );
  };

  export default Benefits;
