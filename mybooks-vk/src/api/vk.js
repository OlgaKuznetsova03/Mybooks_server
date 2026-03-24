import { request } from './client';

export function connectVK(payload) {
  return request('/api/v1/vk/connect/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getShelf() {
  return request('/api/v1/vk/shelf/');
}

export function getMe() {
  return request('/api/v1/vk/me/');
}