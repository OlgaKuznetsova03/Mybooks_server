import '@vkontakte/vkui/dist/vkui.css';
import { useMemo, useState } from 'react';

import {
  AdaptivityProvider,
  AppRoot,
  Avatar,
  Badge,
  Button,
  Card,
  CardGrid,
  ConfigProvider,
  Div,
  Group,
  Header,
  Panel,
  PanelHeader,
  Progress,
  Search,
  SimpleCell,
  SplitCol,
  SplitLayout,
  Tabbar,
  TabbarItem,
  Text,
  Title,
  View,
} from '@vkontakte/vkui';

import {
  Icon28BookOutline,
  Icon28CompassOutline,
  Icon28SearchOutline,
  Icon28UserCircleOutline,
} from '@vkontakte/icons';

type Story = 'home' | 'library' | 'discover' | 'profile';

const booksInProgress = [
  {
    title: 'Три товарища',
    author: 'Эрих Мария Ремарк',
    progress: 62,
    cover: 'https://images.unsplash.com/photo-1512820790803-83ca734da794?w=200',
  },
  {
    title: 'Мастер и Маргарита',
    author: 'Михаил Булгаков',
    progress: 31,
    cover: 'https://images.unsplash.com/photo-1495446815901-a7297e633e8d?w=200',
  },
];

const shelfBooks = [
  { title: 'Сто лет одиночества', status: 'Хочу прочитать' },
  { title: 'Имя розы', status: 'В процессе' },
  { title: 'Пикник на обочине', status: 'Прочитано' },
  { title: 'Дюна', status: 'Хочу прочитать' },
];

const recommendations = [
  { title: '451° по Фаренгейту', tag: 'Антиутопия' },
  { title: 'Понедельник начинается в субботу', tag: 'Фантастика' },
  { title: 'Норвежский лес', tag: 'Современная проза' },
  { title: 'Дом, в котором...', tag: 'Магический реализм' },
];

export default function App() {
  const [activeStory, setActiveStory] = useState<Story>('home');
  const [query, setQuery] = useState('');

  const filteredRecommendations = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return recommendations;
    }
    return recommendations.filter((book) =>
      book.title.toLowerCase().includes(normalized),
    );
  }, [query]);

  return (
    <ConfigProvider>
      <AdaptivityProvider>
        <AppRoot>
          <SplitLayout>
            <SplitCol autoSpaced>
              <View activePanel={activeStory}>
                <Panel id="home">
                  <PanelHeader>Калейдоскоп книг</PanelHeader>

                  <Group>
                    <Div>
                      <Title level="2" weight="2" style={{ marginBottom: 8 }}>
                        Добро пожаловать 👋
                      </Title>
                      <Text>
                        Главная страница приложения: прогресс чтения, цели недели и быстрый
                        доступ к твоей библиотеке.
                      </Text>
                    </Div>
                  </Group>

                  <Group header={<Header>Читаю сейчас</Header>}>
                    <CardGrid size="l">
                      {booksInProgress.map((book) => (
                        <Card key={book.title} mode="shadow">
                          <Div style={{ display: 'flex', gap: 12 }}>
                            <Avatar size={72} src={book.cover} alt={book.title} />
                            <div style={{ flex: 1 }}>
                              <Title level="3" weight="2">
                                {book.title}
                              </Title>
                              <Text style={{ marginTop: 4, marginBottom: 8 }}>{book.author}</Text>
                              <Progress value={book.progress} />
                              <Text style={{ marginTop: 8 }}>{book.progress}% прочитано</Text>
                            </div>
                          </Div>
                        </Card>
                      ))}
                    </CardGrid>
                  </Group>

                  <Group header={<Header size="s">Цель недели</Header>}>
                    <SimpleCell subtitle="Прочитать 180 страниц">Осталось 74 страницы</SimpleCell>
                  </Group>
                </Panel>

                <Panel id="library">
                  <PanelHeader>Моя полка</PanelHeader>

                  <Group header={<Header>Текущие списки</Header>}>
                    {shelfBooks.map((book) => (
                      <SimpleCell
                        key={book.title}
                        after={<Badge mode="prominent">{book.status}</Badge>}
                        subtitle="Нажми, чтобы открыть карточку книги"
                      >
                        {book.title}
                      </SimpleCell>
                    ))}
                  </Group>

                  <Group>
                    <Div>
                      <Button stretched size="l" mode="secondary">
                        Добавить книгу на полку
                      </Button>
                    </Div>
                  </Group>
                </Panel>

                <Panel id="discover">
                  <PanelHeader>Поиск и подборки</PanelHeader>

                  <Group>
                    <Div>
                      <Search
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                        placeholder="Найти книгу"
                      />
                    </Div>
                  </Group>

                  <Group header={<Header>Рекомендуем начать</Header>}>
                    {filteredRecommendations.length > 0 ? (
                      filteredRecommendations.map((book) => (
                        <SimpleCell
                          key={book.title}
                          after={<Badge mode="prominent">{book.tag}</Badge>}
                          subtitle="Добавь в свою полку, чтобы не потерять"
                        >
                          {book.title}
                        </SimpleCell>
                      ))
                    ) : (
                      <Div>
                        <Text>
                          По вашему запросу ничего не найдено. Попробуйте другое название.
                        </Text>
                      </Div>
                    )}
                  </Group>
                </Panel>

                <Panel id="profile">
                  <PanelHeader>Профиль</PanelHeader>

                  <Group>
                    <Div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <Avatar
                        size={72}
                        src="https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200"
                      />
                      <div>
                        <Title level="2" weight="2">
                          Алина
                        </Title>
                        <Text>24 книги за 2026 год</Text>
                      </div>
                    </Div>
                  </Group>

                  <Group header={<Header size="s">Мой ритм</Header>}>
                    <SimpleCell subtitle="Текущая серия чтения">15 дней подряд 🔥</SimpleCell>
                    <SimpleCell subtitle="Среднее время чтения">42 минуты в день</SimpleCell>
                    <Div>
                      <Button size="l" stretched mode="primary">
                        Открыть статистику
                      </Button>
                    </Div>
                  </Group>
                </Panel>
              </View>

              <Tabbar>
                <TabbarItem
                  label="Главная"
                  selected={activeStory === 'home'}
                  onClick={() => setActiveStory('home')}
                >
                  <Icon28BookOutline />
                </TabbarItem>
                <TabbarItem
                  label="Полка"
                  selected={activeStory === 'library'}
                  onClick={() => setActiveStory('library')}
                >
                  <Icon28CompassOutline />
                </TabbarItem>
                <TabbarItem
                  label="Поиск"
                  selected={activeStory === 'discover'}
                  onClick={() => setActiveStory('discover')}
                >
                  <Icon28SearchOutline />
                </TabbarItem>
                <TabbarItem
                  label="Профиль"
                  selected={activeStory === 'profile'}
                  onClick={() => setActiveStory('profile')}
                >
                  <Icon28UserCircleOutline />
                </TabbarItem>
              </Tabbar>
            </SplitCol>
          </SplitLayout>
        </AppRoot>
      </AdaptivityProvider>
    </ConfigProvider>
  );
}
