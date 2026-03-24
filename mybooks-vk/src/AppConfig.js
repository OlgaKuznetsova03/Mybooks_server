import { useEffect, useMemo, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';

import { login, signup } from './api/auth';
import { connectVK, getMe } from './api/vk';
import { AuthForm } from './components/AuthForm';
import { SignupForm } from './components/SignupForm';
import { useShelf } from './hooks/useShelf';
import { useVkUser } from './hooks/useVkUser';
import { clearToken, getToken, setToken } from './utils/storage';
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

  // ✅ VK user + loading
  const { vkUser, error: vkError, loading: vkLoading } = useVkUser();

  // ✅ Shelf data
  const {
    data: shelfData,
    loading: shelfLoading,
    error: shelfError,
  } = useShelf(appState === STATES.SHELF);

  // VK init
  useEffect(() => {
    bridge.send('VKWebAppInit').catch(() => null);
  }, []);

  // online/offline
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

  // 🚀 Главная инициализация
  useEffect(() => {
    if (vkLoading) return;

    if (vkError) {
      setErrorMessage('VK unavailable');
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

        if (!me.linked) {
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
        setErrorMessage(e.message || 'Auth error');
        setAppState(STATES.AUTH);
      }
    }

    bootstrap();
  }, [vkUser, vkError, vkLoading]);

  // 🔐 LOGIN
  async function onLogin(form) {
    setErrorMessage('');
    try {
      const response = await login(form);
      setToken(response.token);

      const me = await getMe();

      if (!me.linked) {
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
      setErrorMessage(e.message || 'Auth error');
      setAppState(STATES.AUTH);
    }
  }

  // 🆕 SIGNUP
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

  // 📊 Status line
  const statusLine = useMemo(() => {
    if (isOffline) return 'No internet';
    if (shelfError) return shelfError.message;
    return appState;
  }, [isOffline, shelfError, appState]);

  // ⏳ Loading
  if (appState === STATES.LOADING || vkLoading || shelfLoading) {
    return <div style={{ padding: 20 }}>Loading...</div>;
  }

  // ❌ Error
  if (appState === STATES.ERROR) {
    return (
      <div style={{ padding: 20 }}>
        Error: {errorMessage || 'Unknown error'}
      </div>
    );
  }

  // 🔐 Auth screen
  if (appState === STATES.AUTH) {
    return (
      <div style={{ padding: 20 }}>
        <p>{statusLine}</p>

        {errorMessage && (
          <p style={{ color: 'red' }}>{errorMessage}</p>
        )}

        {authMode === 'login' ? (
          <AuthForm
            onSubmit={onLogin}
            onGoSignup={() => setAuthMode('signup')}
          />
        ) : (
          <SignupForm
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
      <div style={{ padding: 20 }}>
        <p>{statusLine}</p>

        {shelfData ? (
          <ShelfView
            data={shelfData}
            vkUser={vkUser}
            onLogout={() => {
              clearToken();
              setAppState(STATES.AUTH);
            }}
          />
        ) : (
          <p>Empty shelf</p>
        )}
      </div>
    );
  }

  return <div style={{ padding: 20 }}>Unknown state</div>;
};