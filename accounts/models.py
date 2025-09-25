from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.TextField(blank=True)
    website = models.URLField(blank=True)

    def __str__(self):
        return f"Profile({self.user.username})"
    
    link1 = models.URLField(blank=True, null=True)
    link2 = models.URLField(blank=True, null=True)
    link3 = models.URLField(blank=True, null=True)
    link4 = models.URLField(blank=True, null=True)
    
    @property
    def is_reader(self):
        return self.user.groups.filter(name="reader").exists()

    @property
    def is_author(self):
        return self.user.groups.filter(name="author").exists()

    @property
    def is_blogger(self):
        return self.user.groups.filter(name="blogger").exists()