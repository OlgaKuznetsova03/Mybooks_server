import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Button,
  Card,
  Checkbox,
  Div,
  FormItem,
  Group,
  Input,
  PanelHeader,
  Text,
} from '@vkontakte/vkui';

import { useAuth } from "../../auth/AuthContext";

const roles = [
  { value: 'reader', label: 'Читатель' },
  { value: 'author', label: 'Автор' },
  { value: 'blogger', label: 'Блогер' },
];

export const RegisterPage = () => {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password1, setPassword1] = useState('');
  const [password2, setPassword2] = useState('');
  const [selectedRoles, setSelectedRoles] = useState<string[]>(['reader']);
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [submitting, setSubmitting] = useState(false);

  const toggleRole = (role: string) => {
    setSelectedRoles((prev) =>
      prev.includes(role) ? prev.filter((item) => item !== role) : [...prev, role],
    );
  };

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);

    const formErrors = await register({ username, email, password1, password2, roles: selectedRoles });
    setSubmitting(false);

    if (formErrors) {
      setErrors(formErrors);
      return;
    }

    navigate('/', { replace: true });
  };

  return (
    <>
      <PanelHeader>Регистрация</PanelHeader>
      <Group>
        <Div>
          <Card mode="shadow" style={{ padding: 16 }}>
            <form onSubmit={onSubmit}>
              <FormItem top="Ник / имя" status={errors.username ? 'error' : 'default'} bottom={errors.username?.[0]}>
                <Input value={username} onChange={(event) => setUsername(event.target.value)} />
              </FormItem>
              <FormItem top="Email" status={errors.email ? 'error' : 'default'} bottom={errors.email?.[0]}>
                <Input value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
              </FormItem>
              <FormItem top="Пароль" status={errors.password1 ? 'error' : 'default'} bottom={errors.password1?.[0]}>
                <Input
                  value={password1}
                  onChange={(event) => setPassword1(event.target.value)}
                  type="password"
                />
              </FormItem>
              <FormItem
                top="Повторите пароль"
                status={errors.password2 ? 'error' : 'default'}
                bottom={errors.password2?.[0] ?? errors.__all__?.[0]}
              >
                <Input
                  value={password2}
                  onChange={(event) => setPassword2(event.target.value)}
                  type="password"
                />
              </FormItem>
              <FormItem
                top="Роли"
                status={errors.roles ? 'error' : 'default'}
                bottom={errors.roles?.[0] ?? errors.non_field_errors?.[0]}
              >
                {roles.map((role) => (
                  <Checkbox
                    key={role.value}
                    checked={selectedRoles.includes(role.value)}
                    onChange={() => toggleRole(role.value)}
                  >
                    {role.label}
                  </Checkbox>
                ))}
              </FormItem>
              <Button stretched size="l" type="submit" loading={submitting}>
                Создать аккаунт
              </Button>
            </form>
            <Text style={{ marginTop: 12 }}>
              Уже есть аккаунт? <Link to="/login">Войти</Link>
            </Text>
          </Card>
        </Div>
      </Group>
    </>
  );
};