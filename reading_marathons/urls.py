from django.urls import path

from . import views

app_name = "reading_marathons"

urlpatterns = [
    path("", views.MarathonListView.as_view(), name="list"),
    path("create/", views.MarathonCreateView.as_view(), name="create"),
    path("<slug:slug>/", views.MarathonDetailView.as_view(), name="detail"),
    path("<slug:slug>/join/", views.marathon_join, name="join"),
    path(
        "participants/<int:pk>/approve/",
        views.marathon_participant_approve,
        name="participant_approve",
    ),
    path("<slug:slug>/entries/add/", views.marathon_entry_create, name="entry_add"),
    path("entries/<int:pk>/update/", views.marathon_entry_update, name="entry_update"),
    path("entries/<int:pk>/approve/", views.marathon_entry_approve, name="entry_approve"),
    path(
        "entries/<int:pk>/confirm/",
        views.marathon_entry_confirm_completion,
        name="entry_confirm",
    ),
]