import { request } from './client';

export function login(form) {
  return request('/api/v1/auth/login/', {
    method: 'POST',
    body: JSON.stringify({
      email: form.login,
      password: form.password,
    }),
  });
}

export function signup(form) {
  return request('/api/v1/auth/signup/', {
    method: 'POST',
    body: JSON.stringify({
      username: form.username,
      email: form.email,
      password: form.password,
    }),
  });
}