import { useEffect, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';

const DEV_USER = {
  id: 999999,
  first_name: 'Local',
  last_name: 'Dev',
  photo_100: '',
  screen_name: '',
};

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

        // 💥 ВАЖНО: fallback всегда в dev
        if (import.meta.env.DEV) {
          console.log('VK fallback user used');

          setVkUser(DEV_USER);
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