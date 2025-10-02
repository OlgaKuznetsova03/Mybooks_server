from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
    path("", views.game_list, name="index"),
    path("read-before-buy/", views.read_before_buy_dashboard, name="read_before_buy"),
    path("journey-map/", views.book_journey_map, name="book_journey_map"),
]