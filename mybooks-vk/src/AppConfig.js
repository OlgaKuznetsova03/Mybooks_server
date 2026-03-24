import { useEffect, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';

export const AppConfig = () => {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState('Загрузка...');

  useEffect(() => {
    const timeout = setTimeout(() => {
      setStatus('Работаем вне ВК (это нормально)');
    }, 1000);

    bridge
      .send('VKWebAppGetUserInfo')
      .then((data) => {
        clearTimeout(timeout);
        console.log('VK USER:', data);
        setUser(data);
        setStatus('Пользователь получен');
      })
      .catch((error) => {
        clearTimeout(timeout);
        console.error('VK ошибка:', error);
        setStatus('Работаем вне ВК (это нормально)');
      });
  }, []);

  return (
    <div style={{ padding: 20, background: 'white', color: 'black' }}>
      <h1>📚 Моя книжная полка</h1>

      <p>{status}</p>

      {user && (
        <div>
          <p>Привет, {user.first_name} 👋</p>
          {user.photo_100 && (
            <img src={user.photo_100} alt="avatar" width="100" />
          )}
        </div>
      )}
    </div>
  );
};