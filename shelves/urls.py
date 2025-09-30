from django.urls import path
from . import views

urlpatterns = [
    path("<int:pk>/", views.event_detail, name="event_detail"),
    path("<int:pk>/join/", views.event_join, name="event_join"),
    path("<int:pk>/leave/", views.event_leave, name="event_leave"),

    #полки
    path("me/shelves/", views.my_shelves, name="my_shelves"),
    path("me/home-library/", views.home_library, name="home_library"),
    path("me/home-library/item/<int:item_id>/", views.home_library_edit, name="home_library_edit"),
    path("me/shelves/create/", views.shelf_create, name="shelf_create"),
    path("add-to-shelf/<int:book_id>/", views.add_book_to_shelf, name="add_book_to_shelf"),
    path("remove-from-shelf/<int:shelf_id>/<int:book_id>/", views.remove_book_from_shelf, name="remove_book_from_shelf"),
    path("quick-add/<int:book_id>/<str:code>/", views.quick_add_default_shelf, name="quick_add_shelf"),
    path("add-to-event/<int:book_id>/", views.add_book_to_event, name="add_book_to_event"),

    # чтение
    path("reading/", views.reading_now, name="reading_now"),
    path("reading/book/<int:book_id>/", views.reading_track, name="reading_track"),
    path("reading/set-page/<int:progress_id>/", views.reading_set_page, name="reading_set_page"),
    path("reading/inc/<int:progress_id>/<int:delta>/", views.reading_increment, name="reading_increment"),
    path("reading/finish/<int:progress_id>/", views.reading_mark_finished, name="reading_mark_finished"),
    path("reading/notes/<int:progress_id>/", views.reading_update_notes, name="reading_update_notes"),
    path("reading/characters/<int:progress_id>/", views.reading_add_character, name="reading_add_character"),
    path("reading/format/<int:progress_id>/", views.reading_update_format, name="reading_update_format"),
]
