# apps/books/forms.py
import json

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from .models import (
    Author, Publisher, Genre, ISBNModel,
    AudioBook, Book, Rating, RatingComment
)
from .utils import normalize_isbn
from .api_clients import transliterate_to_cyrillic


def _isbn_digits(value: str) -> str:
    """Оставить только цифры и X, привести к верхнему регистру."""
    return normalize_isbn(value)

def _is_valid_isbn13(v: str) -> bool:
    # алгоритм проверки контрольной суммы ISBN-13
    if len(v) != 13 or not v.isdigit():
        return False
    s = sum((int(d) * (1 if i % 2 == 0 else 3)) for i, d in enumerate(v[:12]))
    check = (10 - (s % 10)) % 10
    return check == int(v[-1])


class AuthorForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ["name", "bio", "country"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
        }


class PublisherForm(forms.ModelForm):
    class Meta:
        model = Publisher
        fields = ["name", "address"]


class GenreForm(forms.ModelForm):
    class Meta:
        model = Genre
        fields = ["name"]


class ISBNModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        authors_field = self.fields.get("authors")
        if authors_field:
            authors_field.queryset = authors_field.queryset.order_by("name")
            authors_field.widget.attrs.setdefault("data-enhanced-multi", "true")
            authors_field.widget.attrs.setdefault("data-clear-label", "Очистить выбор")
    class Meta:
        model = ISBNModel
        fields = [
            "isbn", "title", "authors", "publisher",
            "publish_date", "binding", "total_pages", "synopsis",
            "language", "subjects", "image"
        ]
        labels = {
            "isbn": "ISBN-13",
            "title": "Название издания",
            "authors": "Авторы",
            "publisher": "Издательство",
            "publish_date": "Дата публикации",
            "binding": "Переплёт",
            "total_pages": "Количество страниц",
            "synopsis": "Краткое описание",
            "language": "Язык",
            "subjects": "Темы и жанры",
            "image": "Ссылка на обложку",
        }
        widgets = {
            "synopsis": forms.Textarea(attrs={"rows": 5}),
            "subjects": forms.Textarea(attrs={"rows": 3, "placeholder": "Жанры/темы через запятую"}),
            "image": forms.URLInput(attrs={"placeholder": "https://…"}),
        }
        help_texts = {
            "isbn": "Введите корректный ISBN-13 (можно с дефисами — мы очистим).",
        }

    def clean_isbn(self):
        raw = self.cleaned_data.get("isbn", "") or ""
        val = _isbn_digits(raw)
        if len(val) != 13 or not _is_valid_isbn13(val):
            raise ValidationError("Некорректный ISBN-13. Убедитесь, что указали 13 цифр.")
        return val

    def save(self, commit=True):
        instance = super().save(commit=False)
        normalized = _isbn_digits(instance.isbn)
        if len(normalized) == 13:
            instance.isbn = normalized
            instance.isbn13 = normalized
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class AudioBookForm(forms.ModelForm):
    class Meta:
        model = AudioBook
        fields = ["title", "length", "narrator", "publisher", "genre"]
        widgets = {
            "length": forms.TimeInput(format="%H:%M:%S", attrs={"type": "time", "step": 1}),
        }


class BookForm(forms.ModelForm):
    authors = forms.CharField(
        label="Авторы",
        help_text="Укажите имена через запятую.",
        widget=forms.TextInput(attrs={"placeholder": "Имя автора, Ещё один автор"}),
    )
    isbn = forms.CharField(
        label="Связанные ISBN",
        required=False,
        help_text="Введите ISBN-13 через запятую.",
        widget=forms.TextInput(attrs={"placeholder": "9785000000001"}),
    )
    isbn_metadata = forms.CharField(required=False, widget=forms.HiddenInput())
    genres = forms.CharField(
        label="Жанры",
        help_text="Перечислите жанры через запятую.",
        widget=forms.TextInput(attrs={"placeholder": "Фэнтези, Приключения"}),
    )
    publisher = forms.CharField(
        label="Издательства",
        required=False,
        help_text="Можно указать несколько издательств через запятую.",
        widget=forms.TextInput(attrs={"placeholder": "Эксмо, Азбука"}),
    )

    class Meta:
        model = Book
        fields = [
            "title", "authors", "isbn", "synopsis", "series",
            "series_order", "genres", "age_rating", "language",
            "cover", "audio", "publisher"
        ]
        labels = {
            "title": "Название",
            "synopsis": "Описание",
            "series": "Серия",
            "series_order": "Номер в серии",
            "age_rating": "Возрастной рейтинг",
            "language": "Язык",
            "cover": "Обложка",
            "audio": "Аудиоверсия",
        }
        widgets = {
            "synopsis": forms.Textarea(attrs={"rows": 6}),
            "cover": forms.ClearableFileInput(),   # виджет для загрузки файла
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.is_bound and self.instance.pk:
            self.fields["authors"].initial = ", ".join(
                self.instance.authors.order_by("name").values_list("name", flat=True)
            )
            self.fields["genres"].initial = ", ".join(
                self.instance.genres.order_by("name").values_list("name", flat=True)
            )
            self.fields["publisher"].initial = ", ".join(
                self.instance.publisher.order_by("name").values_list("name", flat=True)
            )
            self.fields["isbn"].initial = ", ".join(
                self.instance.isbn.order_by("title").values_list("isbn", flat=True)
            )

        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.TextInput, forms.NumberInput, forms.URLInput, forms.Textarea, forms.ClearableFileInput)):
                widget.attrs.setdefault("class", "form-control")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
    def _split_list(self, value: str):
        if not value:
            return []
        parts = [part.strip() for part in value.replace("\n", ",").split(",")]
        return [part for part in parts if part]

    def clean_authors(self):
        value = self.cleaned_data.get("authors", "")
        names = self._split_list(value)
        if not names:
            raise ValidationError("Укажите хотя бы одного автора.")
        authors = []
        for name in names:
            author, _ = Author.objects.get_or_create(name=name)
            authors.append(author)
        return authors

    def clean_genres(self):
        value = self.cleaned_data.get("genres", "")
        names = self._split_list(value)
        if not names:
            raise ValidationError("Укажите хотя бы один жанр.")
        genres = []
        for name in names:
            genre, _ = Genre.objects.get_or_create(name=name)
            genres.append(genre)
        return genres

    def clean_publisher(self):
        value = self.cleaned_data.get("publisher", "")
        names = self._split_list(value)
        seen: set[str] = set()
        publishers: list[Publisher] = []
        for name in names:
            normalized = transliterate_to_cyrillic(name).strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            publisher, _ = Publisher.objects.get_or_create(name=normalized)
            publishers.append(publisher)
        return publishers

    def clean_isbn(self):
        value = self.cleaned_data.get("isbn", "")
        numbers = self._split_list(value)
        isbn_objects = []
        errors = []
        seen = set()
        for raw in numbers:
            digits = _isbn_digits(raw)
            if len(digits) != 13:
                errors.append(f"ISBN '{raw}' должен содержать 13 цифр.")
                continue
            if not _is_valid_isbn13(digits):
                errors.append(f"ISBN-13 '{raw}' некорректен.")
                continue
            if digits in seen:
                continue
            seen.add(digits)
            isbn_obj, _ = ISBNModel.objects.get_or_create(
                isbn=digits,
                defaults={"isbn13": digits},
            )
            if not isbn_obj.isbn13:
                isbn_obj.isbn13 = digits
                isbn_obj.save(update_fields=["isbn13"])
            isbn_objects.append(isbn_obj)
        if errors:
            raise ValidationError(errors)
        return isbn_objects


    def clean_series_order(self):
        order = self.cleaned_data.get("series_order")
        if order is not None and order <= 0:
            raise ValidationError("Номер в серии должен быть больше нуля.")
        return order

    def clean_isbn_metadata(self):
        value = self.cleaned_data.get("isbn_metadata")
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            raise ValidationError("Не удалось обработать данные об издании из API.")
        if not isinstance(parsed, dict):
            raise ValidationError("Получены некорректные данные из API.")
        return parsed


class RatingForm(forms.ModelForm):
    CATEGORY_LABELS = dict(Rating.CATEGORY_FIELDS)

    score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=Rating.SCORE_FIELD[1],
        widget=forms.HiddenInput(attrs={"data-role": "rating-value"}),
    )

    plot_score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=CATEGORY_LABELS["plot_score"],
        widget=forms.HiddenInput(attrs={"data-role": "rating-value"}),
    )

    characters_score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=CATEGORY_LABELS["characters_score"],
        widget=forms.HiddenInput(attrs={"data-role": "rating-value"}),
    )
    atmosphere_score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=CATEGORY_LABELS["atmosphere_score"],
        widget=forms.HiddenInput(attrs={"data-role": "rating-value"}),
    )
    art_score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=CATEGORY_LABELS["art_score"],
        widget=forms.HiddenInput(attrs={"data-role": "rating-value"}),
    )


    review = forms.CharField(
        required=False,
        label="Текст отзыва",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Поделитесь впечатлениями...", "class": "form-control"}),
    )

    class Meta:
        model = Rating
        fields = [
            "book",
            "score",
            "plot_score",
            "characters_score",
            "atmosphere_score",
            "art_score",
            "review",
        ]

    def __init__(self, *args, **kwargs):
        """Accept the current user and lock the book field to the target book."""
        # ожидаем current_user через kwargs для контроля уникальности
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        book_field = self.fields["book"]
        book_field.widget = forms.HiddenInput()
        book_field.empty_label = None

        book_pk = self.initial.get("book") or getattr(self.instance, "book_id", None)
        if book_pk:
            try:
                book_pk = int(book_pk)
            except (TypeError, ValueError):
                book_pk = None

        if book_pk:
            book_field.initial = book_pk
            book_field.queryset = Book.objects.filter(pk=book_pk)

    def clean(self):
        cleaned_data = super().clean()

        book = cleaned_data.get("book")
        if not book:
            return cleaned_data

        if self.user and Rating.objects.filter(book=book, user=self.user).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Вы уже оставляли отзыв на эту книгу.")

        return cleaned_data


class RatingCommentForm(forms.ModelForm):
    class Meta:
        model = RatingComment
        fields = ["body"]
        labels = {"body": "Комментарий"}
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "form-control",
                    "placeholder": "Поддержите автора отзыва или задайте вопрос...",
                }
            )
        }