import React, { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import LoginModal from './LoginModal';

const AuthButton = () => {
  const { user, logoutAction } = useAuth();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleLogout = () => {
    logoutAction();
  };

  const onLoginSuccess = () => {
    setIsModalOpen(false);
  };

  if (user) {
    return (
      <div className="flex items-center gap-4">
        <span className="text-gray-500 text-sm hidden lg:block">{user.email}</span>
        <button 
          onClick={handleLogout}
          className="text-gray-300 border border-white/10 px-6 py-2.5 rounded-xl font-medium hover:bg-white/5 transition-all"
        >
          CERRAR SESIÓN
        </button>
      </div>
    );
  }

  return (
    <>
      <button 
        onClick={() => setIsModalOpen(true)}
        className="bg-primary text-background px-6 py-2.5 rounded-xl font-bold hover:scale-105 transition-transform glow-primary"
      >
        INICIAR SESIÓN
      </button>
      <LoginModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onLoginSuccess={onLoginSuccess}
      />
    </>
  );
};

export default AuthButton;
