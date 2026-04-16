import { useEffect, useMemo, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';

import { login, signup } from './api/auth';
import { connectVK, getMe } from './api/vk';
import { AuthForm } from './components/AuthForm';
import { SignupForm } from './components/SignupForm';
import { useShelf } from './hooks/useShelf';
import { useVkUser } from './hooks/useVkUser';
import { clearToken, clearVKId, getToken, setToken, setVKId } from './utils/storage';
import { ShelfView } from './views/ShelfView';

const STATES = {
  LOADING: 'loading',
  AUTH: 'auth',
  SHELF: 'shelf',
  ERROR: 'error',
};

export const AppConfig = () => {
  const [appState, setAppState] = useState(STATES.LOADING);
  const [authMode, setAuthMode] = useState('login');
  const [errorMessage, setErrorMessage] = useState('');
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [isDarkTheme, setIsDarkTheme] = useState(false);

  const {
    vkUser,
    error: vkError,
    loading: vkLoading,
    needsLinking,
  } = useVkUser();

  const {
    data: shelfData,
    loading: shelfLoading,
    error: shelfError,
  } = useShelf(appState === STATES.SHELF);

  useEffect(() => {
    bridge.send('VKWebAppInit').catch(() => null);
  }, []);

  // theme sync (VK + system fallback)
  useEffect(() => {
    const supportsMatchMedia = typeof window.matchMedia === 'function';
    const media = supportsMatchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    setIsDarkTheme(Boolean(media?.matches));

    const onMediaThemeChange = (event) => {
      setIsDarkTheme(event.matches);
    };

    const onVkConfigUpdate = ({ detail }) => {
      const scheme = detail?.data?.scheme || '';
      if (typeof scheme === 'string' && scheme.includes('dark')) {
        setIsDarkTheme(true);
        return;
      }
      if (typeof scheme === 'string' && scheme.length) {
        setIsDarkTheme(false);
      }
    };

    if (media) {
      if (typeof media.addEventListener === 'function') {
        media.addEventListener('change', onMediaThemeChange);
      } else if (typeof media.addListener === 'function') {
        media.addListener(onMediaThemeChange);
      }
    }
    bridge.subscribe(onVkConfigUpdate);

    return () => {
      if (media) {
        if (typeof media.removeEventListener === 'function') {
          media.removeEventListener('change', onMediaThemeChange);
        } else if (typeof media.removeListener === 'function') {
          media.removeListener(onMediaThemeChange);
        }
      }
      bridge.unsubscribe(onVkConfigUpdate);
    };
  }, []);

  useEffect(() => {
    const onOnline = () => setIsOffline(false);
    const onOffline = () => setIsOffline(true);

    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);

    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  useEffect(() => {
    if (vkLoading) return;

    if (needsLinking) {
      setErrorMessage('VK аккаунт не привязан. Войдите с email и паролем.');
      setAppState(STATES.AUTH);
      return;
    }

    if (vkError) {
      setErrorMessage(vkError?.message || String(vkError || 'VK unavailable'));
      setAppState(STATES.ERROR);
      return;
    }

    if (!vkUser) {
      setErrorMessage('VK user not found');
      setAppState(STATES.ERROR);
      return;
    }

    async function bootstrap() {
      const token = getToken();

      if (!token) {
        setAppState(STATES.AUTH);
        return;
      }

      try {
        const me = await getMe();

        if (!me.linked && vkUser?.id) {
          await connectVK({
            vk_user_id: vkUser.id,
            first_name: vkUser.first_name || '',
            last_name: vkUser.last_name || '',
            photo_100: vkUser.photo_100 || '',
            screen_name: vkUser.screen_name || '',
          });
        }

        setAppState(STATES.SHELF);
      } catch (e) {
        clearToken();
        clearVKId();
        setErrorMessage(e.message || 'Auth error');
        setAppState(STATES.AUTH);
      }
    }

    bootstrap();
  }, [vkUser, vkError, vkLoading, needsLinking]);

  async function onLogin(form) {
    setErrorMessage('');

    try {
      const response = await login(form);
      setToken(response.token);

      const me = await getMe();

      if (!me.linked && vkUser?.id) {
        await connectVK({
          vk_user_id: vkUser.id,
          first_name: vkUser.first_name || '',
          last_name: vkUser.last_name || '',
          photo_100: vkUser.photo_100 || '',
          screen_name: vkUser.screen_name || '',
        });
      }

      if (vkUser?.id) {
        setVKId(vkUser.id);
      }
      setAppState(STATES.SHELF);
    } catch (e) {
      setErrorMessage(e.message || 'Auth error');
      setAppState(STATES.AUTH);
    }
  }

  async function onSignup(form) {
    setErrorMessage('');

    try {
      const response = await signup(form);
      setToken(response.token);

      await onLogin({
        login: form.username,
        password: form.password,
      });
    } catch (e) {
      setErrorMessage(e.message || 'Auth error');
      setAppState(STATES.AUTH);
    }
  }

  const pageStyle = useMemo(
    () => ({
      padding: 20,
      minHeight: '100vh',
      background: isDarkTheme ? '#0f1014' : '#f3f4f8',
      color: isDarkTheme ? '#e5e7eb' : '#111827',
      boxSizing: 'border-box',
    }),
    [isDarkTheme],
  );

  const errorStyle = useMemo(
    () => ({
      color: isDarkTheme ? '#fca5a5' : 'red',
    }),
    [isDarkTheme],
  );

  if (appState === STATES.LOADING || vkLoading || shelfLoading) {
    return <div style={pageStyle}>Loading...</div>;
  }

  // ❌ Error
  if (appState === STATES.ERROR) {
    return (
      <div style={pageStyle}>
        Error: {errorMessage || 'Unknown error'}
      </div>
    );
  }

  // 🔐 Auth screen
  if (appState === STATES.AUTH) {
    return (
      <div style={pageStyle}>
        {errorMessage && (
          <p style={errorStyle}>{errorMessage}</p>
        )}

        {authMode === 'login' ? (
          <AuthForm
            isDarkTheme={isDarkTheme}
            onSubmit={onLogin}
            onGoSignup={() => setAuthMode('signup')}
          />
        ) : (
          <SignupForm
            isDarkTheme={isDarkTheme}
            onSubmit={onSignup}
            onGoLogin={() => setAuthMode('login')}
          />
        )}
      </div>
    );
  }

  // 📚 Shelf
  if (appState === STATES.SHELF) {
    return (
      <div style={pageStyle}>
        {shelfData ? (
          <ShelfView
            data={shelfData}
            vkUser={vkUser}
            isDarkTheme={isDarkTheme}
            onLogout={() => {
              clearToken();
              clearVKId();
              setAppState(STATES.AUTH);
            }}
          />
        ) : (
          <p>Empty shelf</p>
        )}
      </div>
    );
  }

  return <div style={pageStyle}>Unknown state</div>;
};