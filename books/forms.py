# apps/books/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from .models import (
    Author, Publisher, Genre, ISBNModel,
    AudioBook, Book, Rating
)


def _isbn_digits(value: str) -> str:
    """Оставить только цифры и X, привести к верхнему регистру."""
    return "".join(ch for ch in value.upper() if ch.isdigit() or ch == "X")

def _is_valid_isbn10(v: str) -> bool:
    # алгоритм проверки контрольной суммы ISBN-10
    if len(v) != 10: 
        return False
    if not v[:-1].isdigit(): 
        return False
    s = sum((10 - i) * int(x) for i, x in enumerate(v[:9]))
    check = 11 - (s % 11)
    check_char = "X" if check == 10 else "0" if check == 11 else str(check)
    return v[-1] == check_char

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
    class Meta:
        model = ISBNModel
        fields = [
            "isbn", "isbn13", "title", "authors", "publisher",
            "publish_date", "binding", "total_pages", "synopsis",
            "language", "subjects", "image"
        ]
        widgets = {
            "synopsis": forms.Textarea(attrs={"rows": 5}),
            "subjects": forms.Textarea(attrs={"rows": 3, "placeholder": "Жанры/темы через запятую"}),
            "image": forms.URLInput(attrs={"placeholder": "https://…"}),
        }
        help_texts = {
            "isbn": "ISBN-10 или ISBN-13 (можно с дефисами — мы очистим).",
            "isbn13": "Если указали здесь, укажите именно 13-значный ISBN.",
        }

    def clean_isbn(self):
        raw = self.cleaned_data.get("isbn", "") or ""
        val = _isbn_digits(raw)
        if len(val) == 10:
            if not _is_valid_isbn10(val):
                raise ValidationError("Некорректный ISBN-10.")
        elif len(val) == 13:
            if not _is_valid_isbn13(val):
                raise ValidationError("Некорректный ISBN-13.")
        else:
            raise ValidationError("ISBN должен быть 10 или 13 символов.")
        return val

    def clean_isbn13(self):
        v = self.cleaned_data.get("isbn13")
        if not v:
            return v
        v = _isbn_digits(v)
        if len(v) != 13 or not _is_valid_isbn13(v):
            raise ValidationError("Некорректный ISBN-13.")
        return v


class AudioBookForm(forms.ModelForm):
    class Meta:
        model = AudioBook
        fields = ["title", "length", "narrator", "publisher", "genre"]
        widgets = {
            "length": forms.TimeInput(format="%H:%M:%S", attrs={"type": "time", "step": 1}),
        }


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = [
            "title", "authors", "isbn", "synopsis", "series",
            "series_order", "genres", "age_rating", "language",
            "cover", "audio", "publisher"
        ]
        widgets = {
            "synopsis": forms.Textarea(attrs={"rows": 6}),
            "cover": forms.ClearableFileInput(),   # виджет для загрузки файла
        }
        help_texts = {
            "authors": "Можно выбрать нескольких авторов.",
            "publisher": "Можно указать несколько издательств.",
        }

    def clean_series_order(self):
        order = self.cleaned_data.get("series_order")
        if order is not None and order <= 0:
            raise ValidationError("Номер в серии должен быть больше нуля.")
        return order


class RatingForm(forms.ModelForm):
    score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=Rating.SCORE_FIELD[1],
        widget=forms.NumberInput(attrs={"step": 1, "placeholder": "1–10", "class": "form-control"}),
    )
    plot_score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=Rating.CATEGORY_FIELDS[0][1],
        widget=forms.NumberInput(attrs={"step": 1, "class": "form-control"}),
    )
    characters_score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=Rating.CATEGORY_FIELDS[1][1],
        widget=forms.NumberInput(attrs={"step": 1, "class": "form-control"}),
    )
    atmosphere_score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=Rating.CATEGORY_FIELDS[2][1],
        widget=forms.NumberInput(attrs={"step": 1, "class": "form-control"}),
    )
    art_score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=Rating.CATEGORY_FIELDS[3][1],
        widget=forms.NumberInput(attrs={"step": 1, "class": "form-control"}),
    )
    logic_score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=Rating.CATEGORY_FIELDS[4][1],
        widget=forms.NumberInput(attrs={"step": 1, "class": "form-control"}),
    )
    language_score = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        label=Rating.CATEGORY_FIELDS[5][1],
        widget=forms.NumberInput(attrs={"step": 1, "class": "form-control"}),
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
            "logic_score",
            "language_score",
            "review",
        ]

    def __init__(self, *args, **kwargs):
        # ожидаем current_user через kwargs для контроля уникальности
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if "book" in self.fields:
            self.fields["book"].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        user = self.user or getattr(self.instance, "user", None)
        book = cleaned.get("book")
        if user and book:
            exists = Rating.objects.filter(user=user, book=book)
            if self.instance.pk:
                exists = exists.exclude(pk=self.instance.pk)
            if exists.exists():
                raise ValidationError("Вы уже оставляли оценку для этой книги.")
            filled_scores = [
            cleaned.get(field)
            for field, _ in Rating.get_score_fields()
        ]
        if not any(filled_scores) and not cleaned.get("review"):
            raise ValidationError("Поставьте оценку хотя бы в одной категории или напишите отзыв.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.user and not obj.user_id:
            obj.user = self.user
        if commit:
            obj.save()
        return obj
