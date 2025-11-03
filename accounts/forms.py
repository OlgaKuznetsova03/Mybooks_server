from typing import Set

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import Group, User
from django.utils.translation import gettext_lazy as _

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
        self._apply_widget_styles()
        self.fields["password1"].help_text = _(
            "Пароль должен состоять минимум из 8 символов, хотя бы одну букву и один символ."
        )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def _apply_widget_styles(self):
        styled_fields = {
            "username": {
                "class": "form-control",
                "autocomplete": "nickname",
                "placeholder": self.fields["username"].label,
            },
            "email": {
                "class": "form-control",
                "autocomplete": "email",
                "inputmode": "email",
                "placeholder": self.fields["email"].label,
            },
            "password1": {
                "class": "form-control",
                "autocomplete": "new-password",
                "placeholder": self.fields["password1"].label,
            },
            "password2": {
                "class": "form-control",
                "autocomplete": "new-password",
                "placeholder": self.fields["password2"].label,
            },
        }

        for name, attrs in styled_fields.items():
            widget = self.fields[name].widget
            widget.attrs.update(attrs)

        self.fields["roles"].widget.attrs.update({"class": "form-check-input"})

    def full_clean(self):
        super().full_clean()
        for name, field in self.fields.items():
            widget = field.widget
            base_classes = widget.attrs.get("class", "")
            classes = base_classes.split()
            if name in self.errors:
                if "is-invalid" not in classes:
                    classes.append("is-invalid")
            else:
                classes = [cls for cls in classes if cls != "is-invalid"]
            widget.attrs["class"] = " ".join(classes).strip()

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
        selected_roles = set(self.cleaned_data.get("roles", []))
        self._ensure_role_groups()

        original_save_m2m = self.save_m2m

        def save_m2m_wrapper():
            original_save_m2m()
            self._assign_roles(self.instance, selected_roles)

        self.save_m2m = save_m2m_wrapper  # type: ignore[assignment]

        if commit:
            user.save()
            self.save_m2m()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "class": "form-control",
                "autocomplete": "username",
                "inputmode": "email",
                "autofocus": "autofocus",
                "placeholder": self.fields["username"].label,
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": "form-control",
                "autocomplete": "current-password",
                "placeholder": self.fields["password"].label,
            }
        )

    def full_clean(self):
        super().full_clean()
        for name, field in self.fields.items():
            widget = field.widget
            base_classes = widget.attrs.get("class", "")
            classes = base_classes.split()
            if name in self.errors:
                if "is-invalid" not in classes:
                    classes.append("is-invalid")
            else:
                classes = [cls for cls in classes if cls != "is-invalid"]
            widget.attrs["class"] = " ".join(classes).strip()


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

