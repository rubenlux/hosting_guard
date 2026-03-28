import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, ArrowRight, Lock } from 'lucide-react';

const projects = [
  { name: 'Ecommerce', url: 'https://mi-tienda.hostingguard.lat', img: '/screenshots/ecommerce.png' },
  { name: 'Blog', url: 'https://mi-blog.hostingguard.lat', img: '/screenshots/blog.png' },
  { name: 'Noticias', url: 'https://la-capital.hostingguard.lat', img: '/screenshots/news.png' },
  { name: 'Academia', url: 'https://lms-pro.hostingguard.lat', img: '/screenshots/lms.png' },
];

const Hero = () => {
    const [currentProject, setCurrentProject] = useState(0);
  
    useEffect(() => {
      const timer = setInterval(() => {
        setCurrentProject((prev) => (prev + 1) % projects.length);
      }, 4000);
      return () => clearInterval(timer);
    }, []);
  
    return (
      <section className="relative pt-32 pb-20 lg:pt-48 lg:pb-32 overflow-hidden">
        {/* Background Gradients */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[1000px] h-[600px] bg-primary/10 blur-[120px] rounded-full -z-10 opacity-30" />
        <div className="absolute top-40 right-0 w-[400px] h-[400px] bg-secondary/10 blur-[100px] rounded-full -z-10 opacity-20" />
  
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <span className="inline-flex items-center rounded-full px-3 py-1 text-sm font-medium bg-primary/10 text-primary ring-1 ring-inset ring-primary/20 mb-8">
              <Plus className="w-4 h-4 mr-1" /> Nuevo: SSL automático en todos los planes
            </span>
            <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-6 leading-tight">
              Crea tu web en <span className="text-primary italic">segundos</span> 🚀
            </h1>
            <p className="text-xl text-gray-400 max-w-2xl mx-auto mb-10 leading-relaxed">
              Hosting + dominio + SSL automático. Sin configuraciones técnicas pesadas.
              Pensado para emprendedores y desarrolladores que valoran su tiempo.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <a
                href="#create"
                className="bg-primary text-background px-8 py-4 rounded-xl font-bold text-lg hover:scale-105 transition-transform shadow-2xl glow-primary flex items-center gap-2 w-full sm:w-auto justify-center"
              >
                Crear mi web ahora <ArrowRight className="w-5 h-5" />
              </a>
              <button className="bg-surface/50 backdrop-blur-sm text-white border border-white/10 px-8 py-4 rounded-xl font-bold text-lg hover:border-white/20 transition-colors w-full sm:w-auto">
                Ver cómo funciona
              </button>
            </div>
          </motion.div>
  
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2 }}
            className="mt-20 relative px-4"
          >
            <div className="max-w-4xl mx-auto glass-card rounded-2xl p-2 shadow-[0_0_80px_rgba(0,0,0,0.6)] border border-white/10">
              <div className="bg-[#1A1A1A] w-full h-full rounded-xl overflow-hidden flex flex-col relative group">
                <div className="flex items-center gap-2 px-4 py-2 bg-[#1A1A1A] border-b border-white/5 z-10 shrink-0">
                  <div className="flex gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full bg-red-500/50" />
                    <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/50" />
                    <div className="w-2.5 h-2.5 rounded-full bg-green-500/50" />
                  </div>
                  <div className="bg-background/50 px-4 py-1 rounded-full text-[10px] sm:text-xs text-gray-400 flex-1 max-w-lg mx-auto truncate border border-white/5 flex items-center justify-center gap-2">
                    <Lock className="w-3 h-3 text-primary" />
                    {projects[currentProject].url}
                  </div>
                  <div className="w-16 hidden sm:block" />
                </div>
  
                <div className="aspect-video relative bg-background overflow-hidden">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={currentProject}
                      initial={{ opacity: 0, scale: 1.05 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.95 }}
                      transition={{ duration: 0.5, ease: "easeOut" }}
                      className="absolute inset-0"
                    >
                      <img
                        src={projects[currentProject].img}
                        alt={projects[currentProject].name}
                        className="w-full h-full object-cover object-top hover:object-bottom transition-all duration-[6000ms] ease-in-out cursor-pointer"
                      />
                      <div className="absolute top-4 right-4 bg-primary text-background text-[10px] font-black px-3 py-1 rounded-full uppercase tracking-widest shadow-xl">
                        {projects[currentProject].name}
                      </div>
                    </motion.div>
                  </AnimatePresence>
                  
                  <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2 z-20">
                    {projects.map((_, idx) => (
                      <div
                        key={idx}
                        className={`w-1.5 h-1.5 rounded-full transition-all ${idx === currentProject ? 'bg-primary w-4' : 'bg-white/20'}`}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>
    );
  };

  export default Hero;
