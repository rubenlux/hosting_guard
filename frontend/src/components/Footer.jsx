import React from 'react';
import { ShieldCheck } from 'lucide-react';

const Footer = () => (
    <footer className="py-20 border-t border-white/5">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col md:flex-row justify-between items-center gap-8">
          <div className="flex items-center gap-2">
            <ShieldCheck className="text-primary w-6 h-6" />
            <span className="text-xl font-bold tracking-tight text-white">Hosting<span className="text-primary">Guard</span></span>
          </div>
          <div className="flex gap-8 text-gray-500 text-sm">
            <a href="#" className="hover:text-white">Privacidad</a>
            <a href="#" className="hover:text-white">Términos</a>
            <a href="#" className="hover:text-white">API Docs</a>
          </div>
          <div className="text-gray-600 text-sm">
            © 2026 HostingGuard. Todos los derechos reservados.
          </div>
        </div>
      </div>
    </footer>
  );

  export default Footer;
