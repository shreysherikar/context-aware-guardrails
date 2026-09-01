import { createContext, useContext, useState, useCallback } from 'react';

const AuthContext = createContext(null);

/**
 * In-memory auth state provider.
 *
 * Token and role live in React state only — no localStorage/sessionStorage.
 * Logging out simply clears the state.
 */
export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(null); // { token, role }

  const login = useCallback((token, role) => {
    setAuth({ token, role });
  }, []);

  const logout = useCallback(() => {
    setAuth(null);
  }, []);

  return (
    <AuthContext.Provider value={{ auth, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
