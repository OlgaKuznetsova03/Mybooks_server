import { useState, useEffect } from 'react';
import bridge from '@vkontakte/vk-bridge';
import { SplitLayout, SplitCol, ScreenSpinner } from '@vkontakte/vkui';

import { ShelfView } from './components/ShelfView';

export const App = () => {
  const [fetchedUser, setUser] = useState(null);
  const [popout, setPopout] = useState(<ScreenSpinner />);

  useEffect(() => {
    async function fetchData() {
      try {
        const user = await bridge.send('VKWebAppGetUserInfo');
        setUser(user);
      } catch (error) {
        console.error('Ошибка получения пользователя VK:', error);
      } finally {
        setPopout(null);
      }
    }

    fetchData();
  }, []);

  const mockData = {
    profile: {
      username: 'Живу_в_библиотеке',
    },
    current_book: {
      id: 1,
      title: 'Проклятие Желтого императора',
      authors: ['Хунь Юнь'],
      cover_url: '',
      progress_percent: 38,
    },
    recent_books: [
      {
        id: 2,
        title: 'Газовый убийца. История маньяка Джона Кристи',
        authors: ['Кейт Саммерскейл'],
        cover_url: '',
      },
      {
        id: 3,
        title: 'Человек государев',
        authors: ['Александр Горбов', 'Мила Бачурова'],
        cover_url: '',
      },
      {
        id: 4,
        title: 'Часы смерти',
        authors: ['Джон Диксон Карр'],
        cover_url: '',
      },
      {
        id: 5,
        title: 'Продавец секретов',
        authors: ['Ли Чжонван'],
        cover_url: '',
      },
    ],
    stats: {
      books_this_month: 5,
      pages_this_month: 2928,
      audio_minutes_this_month: 1049,
    },
  };

  const handleLogout = () => {
    console.log('Выход');
  };

  return (
    <SplitLayout popout={popout}>
      <SplitCol>
        <ShelfView
          data={mockData}
          vkUser={fetchedUser}
          onLogout={handleLogout}
        />
      </SplitCol>
    </SplitLayout>
  );
};