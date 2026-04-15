import { getToken } from '../utils/storage';

const PROD_API_ORIGIN = 'https://kalejdoskopknig.ru';

function normalizeBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

function resolveApiBaseUrl() {
  const envBaseUrl = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL);
  if (envBaseUrl) {
    return envBaseUrl;
  }

  const host = window.location.hostname;
  const isLocalhost = host === 'localhost' || host === '127.0.0.1' || host === '0.0.0.0';
  if (isLocalhost) {
    return 'http://127.0.0.1:8000';
  }

  return PROD_API_ORIGIN;
}

const API_BASE_URL = resolveApiBaseUrl();

function buildUrl(path) {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }

  return `${API_BASE_URL}${path}`;
}

export async function request(path, options = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  if (token) {
    headers.Authorization = `Token ${token}`;
  }

  let response;
  try {
    response = await fetch(buildUrl(path), {
      ...options,
      headers,
    });
  } catch (error) {
    throw new Error('Network error: unable to reach API');
  }

  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const payload = isJson ? await response.json() : null;

  if (!response.ok) {
    const firstErrorFromMap = (errors) => {
      if (!errors || typeof errors !== 'object') return null;
      for (const value of Object.values(errors)) {
        if (Array.isArray(value) && value.length) {
          return String(value[0]);
        }
      }
      return null;
    };

    const message =
      payload?.detail ||
      firstErrorFromMap(payload?.errors) ||
      payload?.error ||
      `Request failed (${response.status})`;

    throw new Error(message);
  }

  return payload;
}