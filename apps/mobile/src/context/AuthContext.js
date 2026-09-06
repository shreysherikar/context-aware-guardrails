import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';

/**
 * AuthContext for Expo React Native.
 *
 * Provides { auth: {token, role} | null, login(token, role), logout() }.
 * Backed by AsyncStorage so sessions survive app restarts.
 */

const AuthContext = createContext(null);

const AUTH_STORAGE_KEY = '@contextguard:auth';

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(null);
  const [loading, setLoading] = useState(true);

  // Load persisted auth on mount
  useEffect(() => {
    (async () => {
      try {
        const stored = await AsyncStorage.getItem(AUTH_STORAGE_KEY);
        if (stored) {
          setAuth(JSON.parse(stored));
        }
      } catch (err) {
        console.error('Failed to load auth from storage:', err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (token, role) => {
    const authData = { token, role };
    setAuth(authData);
    try {
      await AsyncStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(authData));
    } catch (err) {
      console.error('Failed to persist auth to storage:', err);
    }
  }, []);

  const logout = useCallback(async () => {
    setAuth(null);
    try {
      await AsyncStorage.removeItem(AUTH_STORAGE_KEY);
    } catch (err) {
      console.error('Failed to remove auth from storage:', err);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ auth, login, logout, loading }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
