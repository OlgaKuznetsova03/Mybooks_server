from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("auth/login/", views.MobileLoginView.as_view(), name="auth-login"),
    path("auth/login", views.MobileLoginView.as_view()),
    path("auth/signup/", views.MobileSignupView.as_view(), name="auth-signup"),
    path("auth/signup", views.MobileSignupView.as_view()),
    path("health/", views.HealthView.as_view(), name="health"),
    path("health", views.HealthView.as_view()),
    path("feature-map/", views.FeatureMapView.as_view(), name="feature-map"),
    path("feature-map", views.FeatureMapView.as_view()),
    path("home/", views.HomeFeedView.as_view(), name="home"),
    path("home", views.HomeFeedView.as_view()),
    path("stats/", views.StatsView.as_view(), name="stats"),
    path("stats", views.StatsView.as_view()),
    path("books/", views.BookListView.as_view(), name="books-list"),
    path("books", views.BookListView.as_view()),
    path("books/<int:pk>/", views.BookDetailView.as_view(), name="books-detail"),
    path("books/<int:pk>", views.BookDetailView.as_view()),
    path("reading-clubs/", views.ReadingClubListView.as_view(), name="reading-clubs"),
    path("reading-clubs", views.ReadingClubListView.as_view()),
    path("marathons/", views.ReadingMarathonListView.as_view(), name="marathons"),
    path("marathons", views.ReadingMarathonListView.as_view()),
]