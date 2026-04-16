import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ShieldCheck, Menu, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import AuthButton from './AuthButton';

const Navbar = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-md border-b border-white/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-20">
          <Link to="/" className="flex items-center gap-2 hover:opacity-90 transition-opacity">
            <div className="w-10 h-10 bg-primary/20 rounded-xl flex items-center justify-center border border-primary/30">
              <ShieldCheck className="text-primary w-6 h-6" />
            </div>
            <span className="text-2xl font-bold tracking-tight text-white">Hosting<span className="text-primary">Guard</span></span>
          </Link>

          <div className="hidden md:block">
            <div className="ml-10 flex items-baseline space-x-8">
              <a href="#funcionamiento" className="text-gray-300 hover:text-primary transition-colors font-medium">Cómo funciona</a>
              <a href="#beneficios" className="text-gray-300 hover:text-primary transition-colors font-medium">Beneficios</a>
              <a href="#pricing" className="text-gray-300 hover:text-primary transition-colors font-medium">Precios</a>
              <AuthButton />
            </div>
          </div>

          <div className="md:hidden">
            <button onClick={() => setIsOpen(!isOpen)} className="text-gray-300 p-2">
              {isOpen ? <X /> : <Menu />}
            </button>
          </div>
        </div>
      </div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden bg-surface border-b border-white/5"
          >
            <div className="px-2 pt-2 pb-3 space-y-1 sm:px-3">
              <a href="#funcionamiento" className="block px-3 py-2 text-gray-300 hover:text-primary">Cómo funciona</a>
              <a href="#beneficios" className="block px-3 py-2 text-gray-300 hover:text-primary">Beneficios</a>
              <a href="#pricing" className="block px-3 py-2 text-gray-300 hover:text-primary">Precios</a>
              <div className="mt-4 px-3">
                <AuthButton />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
};

export default Navbar;
