 Kalejdoskop Knig VK App

Мобильный VK Mini App проект хранится в этой папке.

## API (первый этап)

Для приложения добавлен отдельный API-контур в Django-бэкенде:

- `POST /api/v1/vk-app/auth/register/` — регистрация (все поля формы сайта: username, email, password, password2, roles).
- `POST /api/v1/vk-app/auth/login/` — вход по email + password.
- `GET /api/v1/vk-app/profile/` — профиль пользователя с ролями, ссылками и базовой статистикой.
- `GET /api/v1/vk-app/books/?q=...` — поиск книг.
- `POST /api/v1/vk-app/books/` — добавление книги (все поля формы сайта для книги).
- `GET /api/v1/vk-app/books/{id}/` — карточка книги.

## Дальше

Следующий этап: собрать экраны VK Mini App (авторизация, поиск, добавление книги, профиль) и подключить к этим endpoint.
## Настройка API для VK Mini App

Приложение использует `VITE_API_BASE_URL` для запросов к Django API.

Пример `.env`:

```
VITE_API_BASE_URL=https://kalejdoskopknig.ru
```

Если переменная не задана, в окружении VK (`vk.com` / `vk-apps.com`) автоматически используется `https://kalejdoskopknig.ru`.
В локальной разработке без переменной запросы идут на текущий origin.