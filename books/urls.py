from django.urls import path
from . import views

urlpatterns = [
    # пример: страница со списком книг
    path("book_list", views.book_list, name="book_list"),

    path("lookup/", views.book_lookup, name="book_lookup"),
    path("prefill/", views.book_prefill_external, name="book_prefill_external"),
    
    # детальная страница книги
    path("<int:pk>/", views.book_detail, name="book_detail"),

    # создание книги
    path("create/", views.book_create, name="book_create"),

    # редактирование книги
    path("<int:pk>/edit/", views.book_edit, name="book_edit"),

    # добавление оценки
    path("<int:pk>/rate/", views.rate_book, name="rate_book"),
    path("<int:pk>/print-review/", views.book_review_print, name="book_review_print"),

    # если оставляем добавление одного ISBN к книге
    #path("<int:pk>/add-isbn/", views.add_one_isbn_to_book, name="add_one_isbn_to_book"),
]
