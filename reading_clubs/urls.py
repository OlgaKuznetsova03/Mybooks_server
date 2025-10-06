from django.urls import path

from . import views

app_name = "reading_clubs"

urlpatterns = [
    path("", views.ReadingClubListView.as_view(), name="list"),
    path("create/", views.ReadingClubCreateView.as_view(), name="create"),
    path("<slug:slug>/", views.ReadingClubDetailView.as_view(), name="detail"),
    path("<slug:slug>/join/", views.reading_join, name="join"),
    path(
        "<slug:slug>/participants/<int:participant_id>/approve/",
        views.reading_approve_participant,
        name="approve_participant",
    ),
    path("<slug:slug>/topics/add/", views.ReadingNormCreateView.as_view(), name="topic_add"),
    path(
        "<slug:slug>/topics/<int:pk>/",
        views.ReadingTopicDetailView.as_view(),
        name="topic_detail",
    ),
    path(
        "<slug:slug>/topics/<int:pk>/posts/add/",
        views.DiscussionPostCreateView.as_view(),
        name="post_add",
    ),
]