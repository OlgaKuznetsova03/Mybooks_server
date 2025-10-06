from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("admin/", admin.site.urls),
    path("books/", include("books.urls")),  # подключаем роуты приложения books
    path("accounts/", include("accounts.urls")), # подключаем роуты приложения accounts
    path("events/", include("shelves.urls")), # подключаем роуты полок с ивентами shelves
    path("games/", include("games.urls")),  # подключаем роуты приложения games
    path("collaborations/", include("collaborations.urls")),
    path("reading-clubs/", include("reading_clubs.urls")),
    path("marathons/", include("reading_marathons.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)