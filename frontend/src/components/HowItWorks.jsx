import React from 'react';
import { motion } from 'framer-motion';
import { Zap, Rocket, Globe } from 'lucide-react';
import SectionHeading from './SectionHeading';

const HowItWorks = () => {
    const steps = [
      {
        title: "Elige el nombre",
        desc: "Define cómo quieres que se llame tu sitio: mi-app, portfolio, etc.",
        icon: <Zap className="text-primary w-8 h-8" />,
      },
      {
        title: "Auto-Provisión",
        desc: "Nuestra infraestructura crea contenedores aislados y SSL en milisegundos.",
        icon: <Rocket className="text-secondary w-8 h-8" />,
      },
      {
        title: "Lanza tu web",
        desc: "Tu sitio está en vivo. Sube tu contenido y empieza a recibir visitas.",
        icon: <Globe className="text-accent w-8 h-8" />,
      }
    ];
  
    return (
      <section id="funcionamiento" className="py-24 relative">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <SectionHeading
            title="Hosting simple en 3 pasos"
            subtitle="Diseñamos el proceso para que cualquier persona pueda desplegar su web sin ayuda de técnicos."
          />
          <div className="grid md:grid-cols-3 gap-8">
            {steps.map((step, idx) => (
              <motion.div
                key={idx}
                whileHover={{ y: -5 }}
                className="glass-card p-8 rounded-2xl relative group"
              >
                <div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center mb-6 border border-white/10 group-hover:border-primary/50 transition-colors">
                  {step.icon}
                </div>
                <h3 className="text-xl font-bold mb-3">{step.title}</h3>
                <p className="text-gray-400">{step.desc}</p>
                <div className="absolute top-8 right-8 text-6xl font-black text-white/5 -z-10">{idx + 1}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>
    );
  };

  export default HowItWorks;
