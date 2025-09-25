from django import template

register = template.Library()

ROLE_TRANSLATIONS = {
    "reader": "Читатель",
    "author": "Автор",
    "blogger": "Блогер",
    "publisher": "Издательство",
}

@register.filter
def role_display(value: str) -> str:
    """Переводит название роли на русский язык"""
    return ROLE_TRANSLATIONS.get(value.lower(), value.title())
