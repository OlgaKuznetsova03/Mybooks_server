import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import RequestFactory
from reading_clubs.views import ReadingClubDetailView

try:
    factory = RequestFactory()
    request = factory.get('/reading-clubs/pochtalonsha/')
    
    view = ReadingClubDetailView()
    view.setup(request, slug='pochtalonsha')
    
    # Получаем объект
    club = view.get_object()
    print(f"Club found: {club.title}")
    
    # Получаем контекст
    context = view.get_context_data()
    print("Context keys:", list(context.keys()))
    
    print("SUCCESS: No errors in view logic")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
