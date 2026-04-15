import { useEffect, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';

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

export function useVkUser() {
  const [vkUser, setVkUser] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    async function loadUser() {
      try {
        const timeout = new Promise((_, reject) =>
          setTimeout(() => reject(new Error('VK timeout')), 1500)
        );

        const user = await Promise.race([
          bridge.send('VKWebAppGetUserInfo'),
          timeout,
        ]);

        if (isMounted) {
          setVkUser(user);
          setError(null);
          setLoading(false);
        }
      } catch (e) {
        if (!isMounted) return;

        // Используем fallback в dev только при явном флаге,
        // чтобы не привязывать всех к одному и тому же vk_user_id.
        if (DEV_FALLBACK_ENABLED) {
          console.log('VK fallback user used (VITE_VK_DEV_FALLBACK=1)');

          setVkUser(getDevUser());
          setError(null);
        } else {
          setError(e);
          setVkUser(null);
        }

        setLoading(false);
      }
    }

    loadUser();

    return () => {
      isMounted = false;
    };
  }, []);

  return { vkUser, error, loading };
}