from django.urls import path

from . import auth_views, views, vk_app_views, vk_views

app_name = "api"

urlpatterns = [
    path("auth/register/", auth_views.AuthRegisterView.as_view(), name="auth-register"),
    path("auth/login/", auth_views.AuthLoginView.as_view(), name="auth-login"),
    path("auth/me/", auth_views.AuthMeView.as_view(), name="auth-me"),
    path("auth/logout/", auth_views.AuthLogoutView.as_view(), name="auth-logout"),
    path("auth/signup/", views.MobileSignupView.as_view(), name="auth-signup-legacy"),
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
    path("vk/login/", vk_views.VKLoginView.as_view(), name="vk-login"),
    path("vk/connect/", vk_views.VKConnectView.as_view(), name="vk-connect"),
    path("vk/me/", vk_views.VKMeView.as_view(), name="vk-me"),
    path("vk/shelf/", vk_views.VKShelfView.as_view(), name="vk-shelf"),
    path("vk/public-shelf/<int:vk_user_id>/", vk_views.VKPublicShelfView.as_view(), name="vk-public-shelf"),
    path("vk/widget/<int:vk_user_id>/", vk_views.VKWidgetView.as_view(), name="vk-widget"),
    path("vk-app/auth/login/", vk_app_views.VKAppLoginView.as_view(), name="vk-app-login"),
    path("vk-app/auth/register/", vk_app_views.VKAppRegisterView.as_view(), name="vk-app-register"),
    path("vk-app/profile/", vk_app_views.VKAppProfileView.as_view(), name="vk-app-profile"),
    path("vk-app/books/", vk_app_views.VKAppBookListCreateView.as_view(), name="vk-app-books-list"),
    path("vk-app/books/<int:pk>/", vk_app_views.VKAppBookDetailView.as_view(), name="vk-app-books-detail"),
]