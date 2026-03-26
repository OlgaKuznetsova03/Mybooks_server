import type { AuthResponse, AuthUser, FieldErrors, LoginPayload, RegisterPayload } from '../types/auth';

const API_BASE = '/api/v1/auth';

const buildHeaders = (token?: string): HeadersInit => {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  if (token) {
    headers.Authorization = `Token ${token}`;
  }

  return headers;
};

const parseJson = async <T>(response: Response): Promise<T> => {
  const payload = (await response.json()) as T | { errors?: FieldErrors; detail?: string };

  if (!response.ok) {
    throw payload;
  }

  return payload as T;
};

export const registerRequest = async (payload: RegisterPayload): Promise<AuthResponse> => {
  const response = await fetch(`${API_BASE}/register/`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });

  return parseJson<AuthResponse>(response);
};

export const loginRequest = async (payload: LoginPayload): Promise<AuthResponse> => {
  const response = await fetch(`${API_BASE}/login/`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });

  return parseJson<AuthResponse>(response);
};

export const meRequest = async (token: string): Promise<AuthUser> => {
  const response = await fetch(`${API_BASE}/me/`, {
    method: 'GET',
    headers: buildHeaders(token),
  });

  return parseJson<AuthUser>(response);
};

export const logoutRequest = async (token: string): Promise<void> => {
  const response = await fetch(`${API_BASE}/logout/`, {
    method: 'POST',
    headers: buildHeaders(token),
  });

  if (!response.ok) {
    throw await response.json();
  }
};