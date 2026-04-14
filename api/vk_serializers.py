from django.contrib.auth import get_user_model
from rest_framework import serializers

from shelves.models import ShelfItem

from .models import VKAccount


class VKConnectSerializer(serializers.Serializer):
    vk_user_id = serializers.IntegerField(
        min_value=1,
        max_value=9223372036854775807,
    )
    first_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    photo_100 = serializers.URLField(required=False, allow_blank=True)
    screen_name = serializers.CharField(max_length=255, required=False, allow_blank=True)


class VKAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = VKAccount
        fields = [
            "vk_user_id",
            "first_name",
            "last_name",
            "photo_100",
            "screen_name",
            "linked_at",
            "updated_at",
        ]


class VKUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "username", "email", "first_name", "last_name"]


class VKBookSerializer(serializers.ModelSerializer):
    cover_url = serializers.SerializerMethodField()
    authors = serializers.SerializerMethodField()
    progress_percent = serializers.FloatField(required=False, allow_null=True)

    class Meta:
        model = ShelfItem._meta.get_field("book").remote_field.model
        fields = ["id", "title", "cover_url", "authors", "progress_percent"]

    def get_cover_url(self, obj):
        request = self.context.get("request")
        cover_url = obj.get_cover_url()
        if not cover_url:
            return ""
        if request and not cover_url.startswith(("http://", "https://", "//")):
            return request.build_absolute_uri(cover_url)
        return cover_url

    def get_authors(self, obj):
        return list(obj.authors.values_list("name", flat=True)[:3])