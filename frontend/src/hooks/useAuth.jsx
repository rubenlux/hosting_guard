import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser]       = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Al montar, intentar recuperar la sesión desde el servidor.
    // Si la cookie de access_token es válida, /me devuelve los datos del usuario.
    // No leemos localStorage ni decodificamos el JWT en el cliente.
    const initAuth = async () => {
      try {
        const res = await api.get('/me');
        setUser(res.data);
      } catch {
        // 401 o red caída: no hay sesión activa
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    initAuth();
  }, []);

  // Llamar tras un login exitoso: el servidor ya estableció las cookies.
  // Solo necesitamos obtener los datos del usuario desde /me.
  const loginAction = async () => {
    try {
      const res = await api.get('/me');
      setUser(res.data);
    } catch {
      setUser(null);
    }
  };

  // Llamar al hacer logout: revocamos ambos tokens y el servidor borra las cookies.
  const logoutAction = async () => {
    try {
      // /refresh/revoke está en path=/refresh, por lo que el browser envía el refresh_token cookie.
      // Debe llamarse ANTES de /logout para que la cookie aún exista en el browser.
      await api.post('/refresh/revoke').catch(() => {});
      await api.post('/logout');
    } catch {
      // Si falla (sesión ya expirada), igualmente limpiamos el estado local.
    } finally {
      setUser(null);
      if (typeof window !== 'undefined') {
        window.location.href = '/';
      }
    }
  };

  return (
    <AuthContext.Provider value={{ user, loginAction, logoutAction, loading, setUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
