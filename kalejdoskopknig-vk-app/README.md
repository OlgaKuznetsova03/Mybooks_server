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