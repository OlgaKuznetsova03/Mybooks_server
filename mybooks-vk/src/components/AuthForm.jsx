import { useState } from 'react';

export function AuthForm({ onSubmit, onGoSignup, isDarkTheme = false }) {
  const [form, setForm] = useState({ login: '', password: '' });
  const colors = {
    card: isDarkTheme ? '#171920' : '#ffffff',
    text: isDarkTheme ? '#f3f4f6' : '#111827',
    hint: isDarkTheme ? '#9ca3af' : '#6b7280',
    inputBg: isDarkTheme ? '#0f1117' : '#ffffff',
    inputBorder: isDarkTheme ? '#303442' : '#d1d5db',
    primary: isDarkTheme ? '#8b5cf6' : '#111827',
  };

  return (
    <form
      style={{
        background: colors.card,
        color: colors.text,
        borderRadius: 12,
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        maxWidth: 460,
      }}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(form);
      }}
    >
      <h2>Вход</h2>
      <input
        style={{ background: colors.inputBg, color: colors.text, border: `1px solid ${colors.inputBorder}`, borderRadius: 10, padding: '10px 12px' }}
        placeholder="Логин или email"
        value={form.login}
        onChange={(e) => setForm({ ...form, login: e.target.value })}
      />
      <input
        style={{ background: colors.inputBg, color: colors.text, border: `1px solid ${colors.inputBorder}`, borderRadius: 10, padding: '10px 12px' }}
        type="password"
        placeholder="Пароль"
        value={form.password}
        onChange={(e) => setForm({ ...form, password: e.target.value })}
      />
      <button style={{ background: colors.primary, color: '#fff', border: 'none', borderRadius: 10, padding: '10px 12px', fontWeight: 700 }} type="submit">Войти</button>
      <button style={{ background: 'transparent', color: colors.hint, border: 'none', padding: '4px 0', textAlign: 'left' }} type="button" onClick={onGoSignup}>Регистрация</button>
    </form>
  );
}