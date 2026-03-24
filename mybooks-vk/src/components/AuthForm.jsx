import { useState } from 'react';

export function AuthForm({ onSubmit, onGoSignup }) {
  const [form, setForm] = useState({ login: '', password: '' });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(form);
      }}
    >
      <h2>Вход</h2>
      <input placeholder="Логин или email" value={form.login} onChange={(e) => setForm({ ...form, login: e.target.value })} />
      <input type="password" placeholder="Пароль" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
      <button type="submit">Войти</button>
      <button type="button" onClick={onGoSignup}>Регистрация</button>
    </form>
  );
}