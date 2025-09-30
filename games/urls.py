from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
    path("read-before-buy/", views.read_before_buy_dashboard, name="read_before_buy"),
]