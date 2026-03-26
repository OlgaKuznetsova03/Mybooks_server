import '@vkontakte/vkui/dist/vkui.css';
import { useEffect, useState } from 'react';
import bridge from 'vk-bridge';

import {
  AdaptivityProvider,
  AppRoot,
  ConfigProvider,
  SplitLayout,
  SplitCol,
  View,
  Panel,
  PanelHeader,
  Group,
  Div,
  Title,
  Text,
  Card,
  CardGrid,
  Avatar,
  Tabbar,
  TabbarItem
} from '@vkontakte/vkui';

import {
  Icon28BookOutline,
  Icon28SearchOutline,
  Icon28UserCircleOutline
} from '@vkontakte/icons';

export default function App() {
  const [activeStory, setActiveStory] = useState('home');

  useEffect(() => {
    bridge.send('VKWebAppInit');
  }, []);

  return (
    <ConfigProvider>
      <AdaptivityProvider>
        <AppRoot>
          <SplitLayout>
            <SplitCol>
              <View activePanel={activeStory}>

                {/* ГЛАВНАЯ */}
                <Panel id="home">
                  <PanelHeader>📚 Моя библиотека</PanelHeader>

                  <Group>
                    <Div>
                      <Title level="2">Привет 👋</Title>
                      <Text>
                        Здесь будет твоя книжная вселенная
                      </Text>
                    </Div>
                  </Group>

                  <Group header={<PanelHeader>Сейчас читаю</PanelHeader>}>
                    <CardGrid size="l">
                      <Card mode="shadow">
                        <Div style={{ display: 'flex', gap: 12 }}>
                          <Avatar
                            size={72}
                            src="https://images.unsplash.com/photo-1544947950-fa07a98d237f"
                          />
                          <div>
                            <Title level="3">Три тела</Title>
                            <Text>Лю Цысинь</Text>
                            <Text>42% прочитано</Text>
                          </div>
                        </Div>
                      </Card>
                    </CardGrid>
                  </Group>

                </Panel>

                {/* ПОИСК */}
                <Panel id="search">
                  <PanelHeader>🔍 Поиск книг</PanelHeader>
                  <Group>
                    <Div>
                      <Text>Тут будет поиск книг</Text>
                    </Div>
                  </Group>
                </Panel>

                {/* ПРОФИЛЬ */}
                <Panel id="profile">
                  <PanelHeader>👤 Профиль</PanelHeader>
                  <Group>
                    <Div>
                      <Text>Тут будет профиль пользователя</Text>
                    </Div>
                  </Group>
                </Panel>

              </View>

              {/* НИЖНЕЕ МЕНЮ */}
              <Tabbar>
                <TabbarItem
                  selected={activeStory === 'home'}
                  onClick={() => setActiveStory('home')}
                  text="Главная"
                >
                  <Icon28BookOutline />
                </TabbarItem>

                <TabbarItem
                  selected={activeStory === 'search'}
                  onClick={() => setActiveStory('search')}
                  text="Поиск"
                >
                  <Icon28SearchOutline />
                </TabbarItem>

                <TabbarItem
                  selected={activeStory === 'profile'}
                  onClick={() => setActiveStory('profile')}
                  text="Профиль"
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