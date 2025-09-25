from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Profile

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("avatar", "bio", "website")
        widgets = {"bio": forms.Textarea(attrs={"rows":4})}

class RoleForm(forms.Form):
    roles = forms.MultipleChoiceField(
        choices=[
            ("reader", "Читатель"),
            ("author", "Автор"),
            ("blogger", "Блогер"),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            current = set(user.groups.values_list("name", flat=True))
            self.initial["roles"] = [r for r, _ in self.fields["roles"].choices if r in current]

    def save(self):
        selected = set(self.cleaned_data["roles"])
        # создаём группы, если их ещё нет
        for name, _ in self.fields["roles"].choices:
            Group.objects.get_or_create(name=name)
        # синхронизация ролей
        self.user.groups.set(Group.objects.filter(name__in=selected))
