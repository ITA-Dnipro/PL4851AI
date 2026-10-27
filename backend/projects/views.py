from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.reverse import reverse

from startups.models import StartupProfile

from .audit import EMPTY_SNAPSHOT, record_audit, snapshot
from .models import Project
from .permissions import IsStartupOwnerOrReadOnly, is_startup_owner
from .serializers import ProjectAuditSerializer, ProjectSerializer


class ProjectPagination(PageNumberPagination):
    """Custom pagination class for Project list view."""

    page_size = 6
    page_size_query_param = 'page_size'
    max_page_size = 100


class StartupProjectListCreateView(generics.ListCreateAPIView):
    """Lists the projects of a startup and lets its owner create new ones.

    Everyone sees public projects; the owner also sees private and unlisted ones.
    """

    serializer_class = ProjectSerializer
    pagination_class = ProjectPagination
    permission_classes = [IsStartupOwnerOrReadOnly]

    def get_startup(self):
        if not hasattr(self, '_startup'):
            self._startup = get_object_or_404(
                StartupProfile, pk=self.kwargs['startup_id']
            )

        return self._startup

    def get_queryset(self):
        startup = self.get_startup()
        queryset = Project.objects.alive().filter(startup=startup)
        if not is_startup_owner(self.request.user, startup):
            queryset = queryset.filter(visibility=Project.Visibility.PUBLIC)

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset.order_by('-created_at', 'id')

    def create(self, request, *args, **kwargs):
        # Check the owner before validating the data, so a stranger gets 403
        if not is_startup_owner(request.user, self.get_startup()):
            raise PermissionDenied()

        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        with transaction.atomic():
            project = serializer.save(startup=self.get_startup())
            record_audit(project, self.request.user, EMPTY_SNAPSHOT)

    def get_success_headers(self, data):
        location = reverse(
            'projects:project-detail',
            kwargs={'id': data['id']},
            request=self.request,
        )

        return {'Location': location}


def get_visible_project(request, project_id):
    """Returns an existing project, or raises 404.

    Private and unlisted projects are visible only to the owner; for everyone else
    they don't exist.
    """
    project = get_object_or_404(
        Project.objects.alive().select_related('startup'), pk=project_id
    )
    if project.visibility != Project.Visibility.PUBLIC and not is_startup_owner(
        request.user, project.startup
    ):
        raise Http404

    return project


class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Reads a project; its owner can update it or delete it (soft delete)."""

    serializer_class = ProjectSerializer
    permission_classes = [IsStartupOwnerOrReadOnly]

    def get_queryset(self):
        return Project.objects.alive().select_related('startup')

    def get_object(self):
        project = get_visible_project(self.request, self.kwargs['id'])
        self.check_object_permissions(self.request, project)

        return project

    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        with transaction.atomic():
            project = serializer.save()
            record_audit(project, self.request.user, before)

    def perform_destroy(self, instance):
        before = snapshot(instance)
        instance.deleted_at = timezone.now()
        with transaction.atomic():
            instance.save(update_fields=['deleted_at', 'updated_at'])
            record_audit(instance, self.request.user, before)


class ProjectHistoryView(generics.ListAPIView):
    """Change history of a project. Available only to the owner."""

    serializer_class = ProjectAuditSerializer
    pagination_class = ProjectPagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project = get_visible_project(self.request, self.kwargs['id'])
        if not is_startup_owner(self.request.user, project.startup):
            raise PermissionDenied()

        return project.audits.select_related('user')
