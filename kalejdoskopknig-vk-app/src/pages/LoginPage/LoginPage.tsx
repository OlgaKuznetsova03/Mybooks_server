import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, Div, FormItem, Group, Input, PanelHeader, Text } from '@vkontakte/vkui';

import { useAuth } from "../../auth/AuthContext";

export const LoginPage = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    const formErrors = await login({ email, password });
    setSubmitting(false);

    if (formErrors) {
      setErrors(formErrors);
      return;
    }

    navigate('/', { replace: true });
  };

  return (
    <>
      <PanelHeader>Вход в Калейдоскоп Книг</PanelHeader>
      <Group>
        <Div>
          <Card mode="shadow" style={{ padding: 16 }}>
            <form onSubmit={onSubmit}>
              <FormItem top="Email" status={errors.email ? 'error' : 'default'} bottom={errors.email?.[0]}>
                <Input value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
              </FormItem>
              <FormItem
                top="Пароль"
                status={errors.password ? 'error' : 'default'}
                bottom={errors.password?.[0] ?? errors.__all__?.[0] ?? errors.non_field_errors?.[0]}
              >
                <Input
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  type="password"
                />
              </FormItem>
              <Button stretched size="l" type="submit" loading={submitting}>
                Войти
              </Button>
            </form>
            <Text style={{ marginTop: 12 }}>
              Нет аккаунта? <Link to="/register">Зарегистрироваться</Link>
            </Text>
          </Card>
        </Div>
      </Group>
    </>
  );
};