import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from books.models import Author

authors_data = []
for author in Author.objects.all():
    author_dict = {
        "model": "books.author",
        "pk": author.id,
        "fields": {
            "name": author.name,
            "bio": author.bio,
            "country": author.country,
        }
    }
    authors_data.append(author_dict)

with open('authors_fixed.json', 'w', encoding='utf-8') as f:
    json.dump(authors_data, f, ensure_ascii=False, indent=2)

print(f"Экспортировано {len(authors_data)} авторов в authors_fixed.json")