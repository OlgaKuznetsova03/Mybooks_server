import { useCallback, useEffect, useState } from 'react';
import { getShelf } from '../api/vk';

export function useShelf(enabled) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastLoadedAt, setLastLoadedAt] = useState(null);

  const load = useCallback(async ({ silent = false } = {}) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError(null);
    try {
      const response = await getShelf();
      setData(response);
      setLastLoadedAt(new Date());
      return response;
    } catch (e) {
      setError(e);
      throw e;
    } finally {
      if (silent) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    load().catch(() => null);
  }, [enabled, load]);

  useEffect(() => {
    if (!enabled) return;

    const intervalId = window.setInterval(() => {
      load({ silent: true }).catch(() => null);
    }, 60_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [enabled, load]);

  const refresh = useCallback(async () => {
    return load({ silent: true });
  }, [load]);

  return {
    data,
    loading,
    refreshing,
    error,
    lastLoadedAt,
    refresh,
  };
}