import os
import django

# Сначала настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import User
from reading_clubs.models import ReadingClub
from reading_clubs.views import ReadingClubDetailView

try:
    # Создаем запрос с пользователем
    factory = RequestFactory()
    request = factory.get('/reading-clubs/pochtalonsha/')

    # Создаем тестового пользователя
    user, created = User.objects.get_or_create(username='testuser')
    request.user = user

    # Получаем клуб
    club = ReadingClub.objects.get(slug='pochtalonsha')
    print(f'✅ Club found: {club.title}')

    # Тестируем DetailView
    view = ReadingClubDetailView()
    view.request = request
    view.kwargs = {'slug': 'pochtalonsha'}

    # Получаем объект
    obj = view.get_object()
    print(f'✅ Object retrieved: {obj.title}')

    # Устанавливаем object для view
    view.object = obj

    # Пробуем получить контекст
    context = view.get_context_data()
    print('✅ Context created successfully')
    print('Context keys:', list(context.keys()))

    # Проверим основные данные в контексте
    required_keys = ['reading', 'topics', 'approved_participants', 'pending_participants', 'is_participant']
    for key in required_keys:
        if key in context:
            print(f'✅ {key}: {type(context[key])}')
        else:
            print(f'❌ {key}: MISSING')

    print('🎉 DetailView works correctly!')

except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
