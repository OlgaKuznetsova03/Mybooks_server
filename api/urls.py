from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("feature-map/", views.FeatureMapView.as_view(), name="feature-map"),
    path("home/", views.HomeFeedView.as_view(), name="home"),
    path("stats/", views.StatsView.as_view(), name="stats"),
    path("books/", views.BookListView.as_view(), name="books-list"),
    path("books/<int:pk>/", views.BookDetailView.as_view(), name="books-detail"),
    path("reading-clubs/", views.ReadingClubListView.as_view(), name="reading-clubs"),
    path("marathons/", views.ReadingMarathonListView.as_view(), name="marathons"),
]