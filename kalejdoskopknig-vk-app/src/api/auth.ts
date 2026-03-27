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
const VK_APP_API_BASE = `${API_ORIGIN}/api/v1/vk-app`;
const AUTH_API_BASE = `${API_ORIGIN}/api/v1/auth`;

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

const readErrorPayload = async (response: Response): Promise<FieldErrors | { detail: string }> => {
  const responseText = await response.text();

  if (!responseText) {
    return { detail: `HTTP ${response.status}` };
  }

  try {
    const parsed = JSON.parse(responseText) as
      | FieldErrors
      | { detail?: string; errors?: FieldErrors; [key: string]: unknown };

    if (parsed && typeof parsed === 'object') {
      if ('errors' in parsed && parsed.errors && typeof parsed.errors === 'object') {
        return parsed.errors as FieldErrors;
      }

      if ('detail' in parsed && typeof parsed.detail === 'string') {
        return { detail: parsed.detail };
      }

      return parsed as FieldErrors;
    }
  } catch {
    // non-JSON response (for example HTML 404/5xx page)
  }

  return { detail: `HTTP ${response.status}` };
};

const parseJson = async <T>(response: Response): Promise<T> => {
  const payload = (await response.json()) as T | FieldErrors | { detail?: string; errors?: FieldErrors };

  if (!response.ok) {
    if (payload && typeof payload === 'object' && 'errors' in payload && payload.errors) {
      throw payload.errors;
    }

    throw payload;
  }

  return payload as T;
};

const postWithFallback = async <T>(
  paths: [string, ...string[]],
  body: object,
): Promise<T> => {
  let lastError: unknown;

  for (const path of paths) {
    try {
      const response = await fetch(path, {
        method: 'POST',
        headers: buildHeaders(),
        body: JSON.stringify(body),
      });

      if (response.ok) {
        return await parseJson<T>(response);
      }

      if (response.status === 404) {
        lastError = await readErrorPayload(response);
        continue;
      }

      throw await readErrorPayload(response);
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError;
};

export const registerRequest = async (payload: RegisterPayload): Promise<AuthResponse> => {
  const parsed = await postWithFallback<AuthResponse>(
    [`${VK_APP_API_BASE}/auth/register/`, `${AUTH_API_BASE}/register/`],
    {
      username: payload.username,
      email: payload.email,
      password: payload.password1,
      password2: payload.password2,
      roles: payload.roles,
    },
  );

  return { ...parsed, user: normalizeUser(parsed.user) };
};

export const loginRequest = async (payload: LoginPayload): Promise<AuthResponse> => {
  const parsed = await postWithFallback<AuthResponse>(
    [`${VK_APP_API_BASE}/auth/login/`, `${AUTH_API_BASE}/login/`],
    payload,
  );

  return { ...parsed, user: normalizeUser(parsed.user) };
};

export const meRequest = async (token: string): Promise<AuthUser> => {
  const vkProfileResponse = await fetch(`${VK_APP_API_BASE}/profile/`, {
    method: 'GET',
    headers: buildHeaders(token),
  });

  if (vkProfileResponse.ok) {
    const payload = await parseJson<{ profile: AuthUser }>(vkProfileResponse);
    return normalizeUser(payload.profile);
  }

  if (vkProfileResponse.status !== 404) {
    throw await readErrorPayload(vkProfileResponse);
  }

  const fallbackMeResponse = await fetch(`${AUTH_API_BASE}/me/`, {
    method: 'GET',
    headers: buildHeaders(token),
  });
  const payload = await parseJson<AuthUser>(fallbackMeResponse);
  return normalizeUser(payload);
};

export const logoutRequest = async (_token: string): Promise<void> => {
  return Promise.resolve();
};