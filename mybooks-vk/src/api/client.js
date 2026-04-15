import { getToken } from '../utils/storage';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export async function request(path, options = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  if (token) {
    headers.Authorization = `Token ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  const isJson = response.headers.get('content-type')?.includes('application/json');
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
      'Request failed';
    throw new Error(message);
  }

  return payload;
}