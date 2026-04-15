import { useEffect, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';

import { request } from '../api/client';
import { clearToken, clearVKId, getVKId, setToken, setVKId } from '../utils/storage';

const DEV_FALLBACK_ENABLED =
  import.meta.env.DEV && import.meta.env.VITE_VK_DEV_FALLBACK === '1';

function getDevUser() {
  const storageKey = 'mybooks_vk_dev_user_id';
  const saved = window.localStorage.getItem(storageKey);
  const devId = saved || `${Date.now()}`;

  if (!saved) {
    window.localStorage.setItem(storageKey, devId);
  }

  return {
    id: Number(devId),
    first_name: 'Local',
    last_name: 'Dev',
    photo_100: '',
    screen_name: '',
  };
}

function normalizeErrorMessage(err) {
  const message = String(err?.message || err || '');
  return message.trim();
}

export function useVkUser() {
  const [vkUser, setVkUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [needsLinking, setNeedsLinking] = useState(false);

  useEffect(() => {
    let isMounted = true;

    async function initVK() {
      try {
        await bridge.send('VKWebAppInit');

        let launchParams;
        try {
          launchParams = await bridge.send('VKWebAppGetLaunchParams');
        } catch (_) {
          launchParams = null;
        }

        const bridgeUser = await bridge.send('VKWebAppGetUserInfo');
        const currentVKId = String(
          launchParams?.vk_user_id || bridgeUser?.id || '',
        ).trim();

        if (!currentVKId) {
          throw new Error('Не удалось определить VK ID пользователя.');
        }

        const savedVKId = getVKId();
        if (savedVKId && savedVKId !== currentVKId) {
          clearToken();
          clearVKId();
        }

        const response = await request('/api/v1/vk/login/', {
          method: 'POST',
          body: JSON.stringify({ vk_user_id: Number(currentVKId) }),
        });

        if (!isMounted) return;

        setToken(response.token);
        setVKId(currentVKId);
        setVkUser(response.user || bridgeUser);
        setNeedsLinking(false);
        setError(null);
      } catch (err) {
        if (!isMounted) return;

        const message = normalizeErrorMessage(err);

        if (message.includes('vk_not_linked')) {
          setNeedsLinking(true);
          setError('VK аккаунт не привязан');
          setVkUser(null);
          return;
        }

        if (DEV_FALLBACK_ENABLED) {
          const fallback = getDevUser();
          setVkUser(fallback);
          setNeedsLinking(false);
          setError(null);
          return;
        }

        setError(message || 'VK auth error');
        setNeedsLinking(false);
        setVkUser(null);
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    initVK();

    return () => {
      isMounted = false;
    };
  }, []);

  return { user: vkUser, vkUser, loading, error, needsLinking };
}