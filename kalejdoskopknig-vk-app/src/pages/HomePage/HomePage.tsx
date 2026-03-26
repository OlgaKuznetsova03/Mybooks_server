import { Avatar, Button, Div, Group, PanelHeader, SimpleCell, Text, Title } from '@vkontakte/vkui';

import { useAuth } from '../../auth/AuthContext';

export const HomePage = () => {
  const { user, logout } = useAuth();

  return (
    <>
      <PanelHeader>Калейдоскоп книг</PanelHeader>
      <Group>
        <Div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <Avatar size={64} src={user?.avatar ?? undefined} />
          <div>
            <Title level="2">{user?.username}</Title>
            <Text>{user?.email}</Text>
          </div>
        </Div>
      </Group>
      <Group>
        <SimpleCell subtitle="Ваши роли">
          {(user?.roles ?? []).length > 0 ? user?.roles.join(', ') : 'Без роли'}
        </SimpleCell>
        <Div>
          <Button stretched mode="secondary" onClick={() => void logout()}>
            Выйти
          </Button>
        </Div>
      </Group>
    </>
  );
};