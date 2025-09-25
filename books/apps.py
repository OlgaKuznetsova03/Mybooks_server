from django.apps import AppConfig

class BooksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'books'  # ВАЖНО: путь до пакета приложения
    verbose_name = 'Книги'
