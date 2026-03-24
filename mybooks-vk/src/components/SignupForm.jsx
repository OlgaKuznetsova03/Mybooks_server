import { useState } from 'react';

export function SignupForm({ onSubmit, onGoLogin }) {
  const [form, setForm] = useState({ username: '', email: '', password: '' });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(form);
      }}
    >
      <h2>Регистрация</h2>
      <input placeholder="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
      <input placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
      <input type="password" placeholder="Пароль" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
      <button type="submit">Создать аккаунт</button>
      <button type="button" onClick={onGoLogin}>Назад ко входу</button>
    </form>
  );
}