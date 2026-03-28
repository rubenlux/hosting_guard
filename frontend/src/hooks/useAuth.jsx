import React, { createContext, useContext, useState, useEffect } from 'react';
import { jwtDecode } from 'jwt-decode';
import { getToken, removeToken, setToken as saveToken } from '../services/auth';
import api from '../services/api';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      const token = getToken();
      if (token) {
        try {
          // 1. Decodificar localmente (rápido)
          const decoded = jwtDecode(token);
          if (decoded.exp * 1000 > Date.now()) {
            setUser(decoded);
            
            // 2. Validar con el servidor (Step 4 de la recomendación)
            try {
              const res = await api.get('/me');
              setUser(res.data);
            } catch (err) {
              if (err.response?.status === 401) {
                logoutAction();
              }
            }
          } else {
            logoutAction();
          }
        } catch (err) {
          logoutAction();
        }
      }
      setLoading(false);
    };

    initAuth();
  }, []);

  const loginAction = (token) => {
    saveToken(token);
    setUser(jwtDecode(token));
  };

  const logoutAction = () => {
    removeToken();
    setUser(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/'; 
    }
  };

  return (
    <AuthContext.Provider value={{ user, loginAction, logoutAction, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
