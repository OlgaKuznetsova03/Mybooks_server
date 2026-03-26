import type { AuthResponse, AuthUser, FieldErrors, LoginPayload, RegisterPayload } from '../types/auth';

const resolveApiOrigin = (): string => {
  const envOrigin = import.meta.env.VITE_API_BASE_URL?.trim();
  if (envOrigin) {
    return envOrigin.replace(/\/$/, '');
  }

  const host = window.location.hostname;
  const isVkHost =
    host === 'vk.com' ||
    host.endsWith('.vk.com') ||
    host === 'vk.ru' ||
    host.endsWith('.vk.ru') ||
    host.endsWith('.vk-apps.com') ||
    host.endsWith('.vk-apps.ru');
  if (isVkHost) {
    return 'https://kalejdoskopknig.ru';
  }

  return '';
};

const API_ORIGIN = resolveApiOrigin();
const API_BASE = `${API_ORIGIN}/api/v1/vk-app`;

const normalizeUser = (user: AuthUser): AuthUser => ({
  ...user,
  roles: Array.isArray(user.roles) ? user.roles : [],
});

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
  const payload = (await response.json()) as T | FieldErrors | { detail?: string };

  if (!response.ok) {
    throw payload;
  }

  return payload as T;
};

export const registerRequest = async (payload: RegisterPayload): Promise<AuthResponse> => {
  const response = await fetch(`${API_BASE}/auth/register/`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify({
      username: payload.username,
      email: payload.email,
      password: payload.password1,
      password2: payload.password2,
      roles: payload.roles,
    }),
  });

  const parsed = await parseJson<AuthResponse>(response);
  return { ...parsed, user: normalizeUser(parsed.user) };
};

export const loginRequest = async (payload: LoginPayload): Promise<AuthResponse> => {
  const response = await fetch(`${API_BASE}/auth/login/`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  });

  const parsed = await parseJson<AuthResponse>(response);
  return { ...parsed, user: normalizeUser(parsed.user) };
};

export const meRequest = async (token: string): Promise<AuthUser> => {
  const response = await fetch(`${API_BASE}/profile/`, {
    method: 'GET',
    headers: buildHeaders(token),
  });

  const payload = await parseJson<{ profile: AuthUser }>(response);
  return normalizeUser(payload.profile);
};

export const logoutRequest = async (_token: string): Promise<void> => {
  return Promise.resolve();
};