from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User

from .models import Profile


ROLE_CHOICES = [
    ("reader", "Читатель"),
    ("author", "Автор"),
    ("blogger", "Блогер"),
]


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)
    roles = forms.MultipleChoiceField(
        choices=ROLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Роли",
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit)
        selected = set(self.cleaned_data.get("roles", []))
        for name, _ in ROLE_CHOICES:
            Group.objects.get_or_create(name=name)
        if commit:
            user.groups.set(Group.objects.filter(name__in=selected))
        return user
    

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("avatar", "bio", "website")
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}


class RoleForm(forms.Form):
    roles = forms.MultipleChoiceField(
        choices=ROLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user:
            current = set(user.groups.values_list("name", flat=True))
            self.initial["roles"] = [
                role
                for role, _ in self.fields["roles"].choices
                if role in current
            ]

    def save(self):
        if not self.user:
            raise ValueError("RoleForm.save() requires a user instance")
        selected = set(self.cleaned_data["roles"])
        for name, _ in self.fields["roles"].choices:
            Group.objects.get_or_create(name=name)
        self.user.groups.set(Group.objects.filter(name__in=selected))
