/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { loginRequest, logoutRequest, meRequest, registerRequest } from '../api/auth';
import type { AuthUser, FieldErrors, LoginPayload, RegisterPayload } from '../types/auth';

const TOKEN_KEY = 'kalejdoskop_auth_token';
const INITIAL_TOKEN = localStorage.getItem(TOKEN_KEY);

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login: (payload: LoginPayload) => Promise<FieldErrors | null>;
  register: (payload: RegisterPayload) => Promise<FieldErrors | null>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const normalizeErrors = (errorPayload: unknown): FieldErrors => {
  const fallback = { non_field_errors: ['Сервер недоступен. Попробуйте позже.'] };

  if (!errorPayload || typeof errorPayload !== 'object') {
    return fallback;
  }

  const apiError = errorPayload as { errors?: FieldErrors; detail?: string };
  if (apiError.errors) {
    return apiError.errors;
  }

  if (apiError.detail) {
    return { non_field_errors: [apiError.detail] };
  }

  const rawErrors = errorPayload as Record<string, unknown>;
  const normalized = Object.entries(rawErrors).reduce<FieldErrors>((acc, [field, value]) => {
    if (Array.isArray(value)) {
      acc[field] = value.map((item) => String(item));
    }
    return acc;
  }, {});

  if (Object.keys(normalized).length > 0) {
    return normalized;
  }

  return fallback;
};

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(INITIAL_TOKEN);
  const [loading, setLoading] = useState(Boolean(INITIAL_TOKEN));

  useEffect(() => {
    if (!token) {
      return;
    }

    void meRequest(token)
      .then((currentUser) => {
        setUser(currentUser);
      })
      .catch(() => {
        setToken(null);
        localStorage.removeItem(TOKEN_KEY);
      })
      .finally(() => setLoading(false));
  }, [token]);

  const login = useCallback(async (payload: LoginPayload) => {
    try {
      const response = await loginRequest(payload);
      setToken(response.token);
      setUser(response.user);
      setLoading(false);
      localStorage.setItem(TOKEN_KEY, response.token);
      return null;
    } catch (error) {
      return normalizeErrors(error);
    }
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    try {
      const response = await registerRequest(payload);
      setToken(response.token);
      setUser(response.user);
      setLoading(false);
      localStorage.setItem(TOKEN_KEY, response.token);
      return null;
    } catch (error) {
      return normalizeErrors(error);
    }
  }, []);

  const logout = useCallback(async () => {
    if (token) {
      try {
        await logoutRequest(token);
      } catch {
        // ignore network/API logout error, still clear local state
      }
    }

    setToken(null);
    setUser(null);
    localStorage.removeItem(TOKEN_KEY);
  }, [token]);

  const value = useMemo<AuthContextValue>(
    () => ({ user, token, loading, login, register, logout }),
    [user, token, loading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }

  return context;
};