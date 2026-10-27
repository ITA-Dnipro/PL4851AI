from django.contrib import admin
from django.db import transaction
from django.utils import timezone

from .audit import record_audit, snapshot
from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'startup',
        'status',
        'visibility',
        'target_amount',
        'raised_amount',
        'currency',
        'deleted_at',
        'created_at',
    )
    list_filter = (
        'status',
        'visibility',
        ('deleted_at', admin.EmptyFieldListFilter),
    )
    search_fields = ('title', 'slug', 'startup__startup_name')
    list_select_related = ('startup',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    actions = [
        'make_public',
        'make_private',
        'make_unlisted',
        'soft_delete',
        'restore',
    ]

    def _apply(self, request, queryset, message, **fields):
        """Changes the selected projects and writes an audit entry for each."""
        projects = list(queryset)
        with transaction.atomic():
            for project in projects:
                before = snapshot(project)
                for name, value in fields.items():
                    setattr(project, name, value)
                project.save()
                record_audit(project, request.user, before)

        self.message_user(request, f'{message}: {len(projects)}.')

    @admin.action(description='Make selected projects public')
    def make_public(self, request, queryset):
        self._apply(
            request, queryset, 'Made public', visibility=Project.Visibility.PUBLIC
        )

    @admin.action(description='Make selected projects private')
    def make_private(self, request, queryset):
        self._apply(
            request, queryset, 'Made private', visibility=Project.Visibility.PRIVATE
        )

    @admin.action(description='Make selected projects unlisted')
    def make_unlisted(self, request, queryset):
        self._apply(
            request, queryset, 'Made unlisted', visibility=Project.Visibility.UNLISTED
        )

    @admin.action(description='Delete selected projects (soft delete)')
    def soft_delete(self, request, queryset):
        self._apply(
            request,
            queryset.filter(deleted_at__isnull=True),
            'Deleted',
            deleted_at=timezone.now(),
        )

    @admin.action(description='Restore selected deleted projects')
    def restore(self, request, queryset):
        self._apply(
            request,
            queryset.filter(deleted_at__isnull=False),
            'Restored',
            deleted_at=None,
        )
