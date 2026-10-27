from django.urls import path

from .views import (
    ProjectDetailView,
    ProjectHistoryView,
    StartupProjectListCreateView,
)

app_name = 'projects'

urlpatterns = [
    path(
        'startups/<int:startup_id>/projects/',
        StartupProjectListCreateView.as_view(),
        name='startup-projects-list',
    ),
    path('projects/<uuid:id>/', ProjectDetailView.as_view(), name='project-detail'),
    path(
        'projects/<uuid:id>/history/',
        ProjectHistoryView.as_view(),
        name='project-history',
    ),
]
