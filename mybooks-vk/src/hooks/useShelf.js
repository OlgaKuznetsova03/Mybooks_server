import { useEffect, useState } from 'react';
import { getShelf } from '../api/vk';

export function useShelf(enabled) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!enabled) return;
    let active = true;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await getShelf();
        if (active) setData(response);
      } catch (e) {
        if (active) setError(e);
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    return () => {
      active = false;
    };
  }, [enabled]);

  return { data, loading, error };
}