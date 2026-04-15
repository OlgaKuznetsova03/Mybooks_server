const TOKEN_KEY = 'mybooks_token';
const VK_ID_KEY = 'mybooks_vk_id';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(VK_ID_KEY);
}

export function getVKId() {
  return localStorage.getItem(VK_ID_KEY) || '';
}

export function setVKId(vkId) {
  localStorage.setItem(VK_ID_KEY, String(vkId));
}

export function clearVKId() {
  localStorage.removeItem(VK_ID_KEY);
}