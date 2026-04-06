import React, { createContext, useContext, useState, useEffect } from 'react';
import { jwtDecode } from 'jwt-decode';
import api from '../services/api';

const AuthContext = createContext();

/**
 * Reads the support_token cookie (client-side visible part) to detect support mode.
 * HttpOnly cookies are NOT accessible via document.cookie — but the backend sets
 * is_support_session in the /me response, so we rely on that as the source of truth.
 * This helper is a fallback that reads it if somehow available.
 */
function readSupportCookieInfo() {
  // The support_token is HttpOnly so we cannot read it here.
  // We rely on the /me endpoint returning is_support_session + support metadata.
  return null;
}

export const AuthProvider = ({ children }) => {
  const [user, setUser]                   = useState(null);
  const [loading, setLoading]             = useState(true);
  const [supportSession, setSupportSession] = useState(null); // { targetEmail, adminEmail, expiresAt }

  useEffect(() => {
    const initAuth = async () => {
      try {
        const res = await api.get('/me', { _noRefresh: true });
        const data = { ...res.data, role: res.data.role?.toLowerCase() ?? 'user' };
        setUser(data);

        // Backend includes support metadata in /me when support_token cookie is active
        if (data.is_support_session) {
          setSupportSession({
            targetEmail: data.email,
            adminEmail:  data.admin_email  ?? null,
            expiresAt:   data.support_expires_at ?? null,
          });
        }
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    const handleSessionExpired = () => { setUser(null); setSupportSession(null); };
    window.addEventListener('auth:session-expired', handleSessionExpired);

    initAuth();

    return () => window.removeEventListener('auth:session-expired', handleSessionExpired);
  }, []);

  const loginAction = async () => {
    try {
      const res = await api.get('/me');
      setUser({ ...res.data, role: res.data.role?.toLowerCase() ?? 'user' });
    } catch {
      setUser(null);
    }
  };

  const logoutAction = async () => {
    try {
      await api.post('/refresh/revoke').catch(() => {});
      await api.post('/logout');
    } catch {
      // ignore
    } finally {
      setUser(null);
      setSupportSession(null);
      if (typeof window !== 'undefined') {
        window.location.href = '/';
      }
    }
  };

  /**
   * Called by the admin panel after receiving a support token.
   * Sends the token to the backend to set the support_token cookie,
   * then reloads /me so the dashboard reflects the impersonated user.
   */
  const activateSupportSession = async (token) => {
    const res = await api.post('/support/activate', { token });
    setSupportSession({
      targetEmail: res.data.target_email,
      adminEmail:  res.data.admin_email,
      expiresAt:   res.data.expires_at,
    });
    // Reload user context as the impersonated client
    const me = await api.get('/me');
    setUser({ ...me.data, role: me.data.role?.toLowerCase() ?? 'user' });
    return res.data;
  };

  /**
   * Called when the admin exits support mode (banner "Salir" button or timer expiry).
   * Clears the support cookie and reloads the admin's own session.
   */
  /**
   * Called when the support banner "Salir" button fires.
   * The banner already handled: session close + /support/deactivate.
   * Here we just clean up React state and redirect.
   */
  const deactivateSupportSession = async (_resolutionData) => {
    // Cookie was already cleared by SupportBanner before calling this.
    setSupportSession(null);
    sessionStorage.removeItem('support_session_id');

    const origin = sessionStorage.getItem('support_origin');
    sessionStorage.removeItem('support_origin');
    if (origin === 'staff') {
      setUser(null);
      window.location.href = '/staff/dashboard';
      return;
    }

    // Admin: restore own session via /me
    try {
      const me = await api.get('/me');
      setUser({ ...me.data, role: me.data.role?.toLowerCase() ?? 'user' });
    } catch {
      setUser(null);
    }
  };

  const isSupportSession = Boolean(supportSession);

  return (
    <AuthContext.Provider value={{
      user, loginAction, logoutAction, loading, setUser,
      isSupportSession, supportSession,
      activateSupportSession, deactivateSupportSession,
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
