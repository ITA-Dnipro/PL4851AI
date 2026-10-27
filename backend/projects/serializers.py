from django.conf import settings
from rest_framework import serializers

from projects.models import Project, ProjectAudit


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for the Project model.

    `startup` and `slug` are not writable: a project stays with its startup and
    keeps the slug it got on creation.
    """

    logo = serializers.SerializerMethodField()

    def get_logo(self, obj):
        """Returns the URL of the project's logo or a default placeholder."""

        if obj.logo:
            return obj.logo.url

        return f'{settings.MEDIA_URL}thumbs/placeholder.jpg'

    class Meta:
        model = Project
        fields = [
            'id',
            'title',
            'slug',
            'short_description',
            'description',
            'status',
            'target_amount',
            'raised_amount',
            'currency',
            'tags',
            'visibility',
            'logo',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']


class ProjectAuditSerializer(serializers.ModelSerializer):
    """A history entry: who changed which fields and when."""

    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ProjectAudit
        fields = ['id', 'user', 'timestamp', 'changes']
