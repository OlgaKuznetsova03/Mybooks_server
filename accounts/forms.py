from typing import Optional, Set

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import Group, User

from .models import Profile, PremiumPayment


ROLE_CHOICES = [
    ("reader", "Читатель"),
    ("author", "Автор"),
    ("blogger", "Блогер"),
]


class SignUpForm(UserCreationForm):
    username = forms.CharField(label="Ник/имя", max_length=150)
    email = forms.EmailField(required=True, label="Email (логин)")
    roles = forms.MultipleChoiceField(
        choices=ROLE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Роли",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pending_role_names: Optional[Set[str]] = None

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Пользователь с таким email уже зарегистрирован."
            )
        return email

    def _ensure_role_groups(self):
        for name, _ in ROLE_CHOICES:
            Group.objects.get_or_create(name=name)

    def _assign_roles(self, user, selected: Set[str]):
        user.groups.set(Group.objects.filter(name__in=selected))

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["username"]
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()

        selected = set(self.cleaned_data.get("roles", []))
        self._ensure_role_groups()
        if commit:
            self._assign_roles(user, selected)
            self._pending_role_names = None
        else:
            self._pending_role_names = selected
        return user

    def save_m2m(self):
        super().save_m2m()
        if self._pending_role_names is not None:
            self._ensure_role_groups()
            self._assign_roles(self.instance, self._pending_role_names)
            self._pending_role_names = None

            
class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))


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


class PremiumPurchaseForm(forms.Form):
    plan = forms.ChoiceField(label="Тариф", choices=[])
    payment_method = forms.ChoiceField(
        label="Способ оплаты",
        choices=PremiumPayment.PaymentMethod.choices,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["plan"].choices = list(PremiumPayment.get_plan_choices_with_price())
        self.fields["plan"].widget = forms.Select(attrs={"class": "form-select"})
        self.fields["payment_method"].widget.attrs.update({"class": "form-check-input"})

    def clean_plan(self):
        plan_code = self.cleaned_data["plan"]
        PremiumPayment.get_plan(plan_code)
        return plan_code

    def save(self):
        if not self.user:
            raise ValueError("PremiumPurchaseForm.save() requires a user instance")
        plan_code = self.cleaned_data["plan"]
        plan = PremiumPayment.get_plan(plan_code)
        payment = PremiumPayment.objects.create(
            user=self.user,
            plan=plan_code,
            method=self.cleaned_data["payment_method"],
            status=PremiumPayment.Status.PENDING,
            amount=plan.price,
        )
        return payment

