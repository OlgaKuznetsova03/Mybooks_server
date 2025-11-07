from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
    path("", views.game_list, name="index"),
    path("book-exchange/", views.book_exchange_dashboard, name="book_exchange"),
    path(
        "book-exchange/<str:username>/<int:round_number>/",
        views.book_exchange_detail,
        name="book_exchange_detail",
    ),
    path("read-before-buy/", views.read_before_buy_dashboard, name="read_before_buy"),
    path("journey-map/", views.book_journey_map, name="book_journey_map"),
    path("nobel-laureates/", views.nobel_laureates_challenge, name="nobel_challenge"),
    path("forgotten-books/", views.forgotten_books_dashboard, name="forgotten_books"),
]