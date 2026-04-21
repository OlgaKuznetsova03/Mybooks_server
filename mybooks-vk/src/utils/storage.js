import vkBridge from '@vkontakte/vk-bridge';

const TOKEN_KEY = 'mybooks_token';
const VK_ID_KEY = 'mybooks_vk_id';

async function getFromBridge(keys) {
  try {
    const response = await vkBridge.send('VKWebAppStorageGet', { keys });
    return response?.keys || [];
  } catch {
    return [];
  }
}

function getBridgeValue(items, key) {
  const item = items.find((entry) => entry.key === key);
  return item?.value || '';
}

function setLocalStorageValue(key, value) {
  try {
    if (value) {
      localStorage.setItem(key, value);
      return;
    }

    localStorage.removeItem(key);
  } catch {
    // ignore localStorage errors
  }
}

async function setBridgeStorageValue(key, value) {
  try {
    await vkBridge.send('VKWebAppStorageSet', { key, value: String(value || '') });
  } catch {
    // ignore VK bridge storage errors
  }
}

export async function hydrateStorageFromBridge() {
  const values = await getFromBridge([TOKEN_KEY, VK_ID_KEY]);
  const token = getBridgeValue(values, TOKEN_KEY).trim();
  const vkId = getBridgeValue(values, VK_ID_KEY).trim();

  if (token) {
    setLocalStorageValue(TOKEN_KEY, token);
  }

  if (vkId) {
    setLocalStorageValue(VK_ID_KEY, vkId);
  }
}

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

export function setToken(token) {
  const nextToken = String(token || '');
  setLocalStorageValue(TOKEN_KEY, nextToken);
  return setBridgeStorageValue(TOKEN_KEY, nextToken);
}

export function clearToken() {
  setLocalStorageValue(TOKEN_KEY, '');
  setLocalStorageValue(VK_ID_KEY, '');
  void setBridgeStorageValue(TOKEN_KEY, '');
  void setBridgeStorageValue(VK_ID_KEY, '');
}

export function getVKId() {
  try {
    return localStorage.getItem(VK_ID_KEY) || '';
  } catch {
    return '';
  }
}

export function setVKId(vkId) {
  const nextVkId = String(vkId || '');
  setLocalStorageValue(VK_ID_KEY, nextVkId);
  return setBridgeStorageValue(VK_ID_KEY, nextVkId);
}

export function clearVKId() {
  setLocalStorageValue(VK_ID_KEY, '');
  void setBridgeStorageValue(VK_ID_KEY, '');
}