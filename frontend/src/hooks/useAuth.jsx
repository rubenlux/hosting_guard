import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../services/api';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser]       = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Al montar, intentar recuperar la sesión desde el servidor.
    // _noRefresh: true evita que el interceptor intente POST /refresh cuando no hay
    // cookies — sin este flag, un usuario no logueado generaría un loop infinito:
    // GET /me → 401 → POST /refresh → 401 → reload → GET /me → 401 → ...
    const initAuth = async () => {
      try {
        const res = await api.get('/me', { _noRefresh: true });
        // Normalizar role a minúsculas para que todas las comparaciones
        // (=== 'admin') funcionen independientemente de cómo esté en la DB.
        setUser({ ...res.data, role: res.data.role?.toLowerCase() ?? 'user' });
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    // Cuando el interceptor detecta que ambos tokens han expirado (refresh también falla),
    // emite este evento en lugar de recargar la página. Aquí limpiamos la sesión y
    // PrivateRoute redirige a '/' via React Router sin causar un reload.
    const handleSessionExpired = () => setUser(null);
    window.addEventListener('auth:session-expired', handleSessionExpired);

    initAuth();

    return () => window.removeEventListener('auth:session-expired', handleSessionExpired);
  }, []);

  // Llamar tras un login exitoso: el servidor ya estableció las cookies.
  // Solo necesitamos obtener los datos del usuario desde /me.
  const loginAction = async () => {
    try {
      const res = await api.get('/me');
      setUser({ ...res.data, role: res.data.role?.toLowerCase() ?? 'user' });
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
