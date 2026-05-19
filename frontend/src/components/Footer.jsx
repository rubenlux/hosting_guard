import { ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

const Footer = () => (
  <footer className="py-20 border-t border-white/5">
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <div className="flex flex-col md:flex-row justify-between items-center gap-8">
        <div className="flex items-center gap-2">
          <ShieldCheck className="text-primary w-6 h-6" />
          <span className="text-xl font-bold tracking-tight text-white">Hosting<span className="text-primary">Guard</span></span>
        </div>
        <div className="flex gap-8 text-gray-500 text-sm">
          <Link to="/blog"     className="hover:text-white transition-colors">Blog</Link>
          <Link to="/privacy"  className="hover:text-white transition-colors">Privacidad</Link>
          <Link to="/terminos" className="hover:text-white transition-colors">Términos</Link>
          <Link to="/api-docs" className="hover:text-white transition-colors">API Docs</Link>
        </div>
        <div className="text-gray-600 text-sm">
          © 2026 HostingGuard. Todos los derechos reservados.
        </div>
      </div>
    </div>
  </footer>
);

export default Footer;
