import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from projects.models import Project
from startups.models import StartupProfile

User = get_user_model()


@pytest.fixture
def api_client():
    """Fixture that provides an instance of APIClient."""
    return APIClient()


@pytest.fixture
def test_data(db):
    """Populates the test database with a user, startup, and 8 projects.

    The first 5 projects are public, the last 3 are private.
    """
    user = User.objects.create_user(email='testowner@test.com', password='password123')
    startup = StartupProfile.objects.create(
        user=user,
        startup_name='Test Startup',
        startup_phone='380990000000',
        startup_description='Description',
    )
    projects = []
    for i in range(8):
        if i < 5:
            visibility = Project.Visibility.PUBLIC
        else:
            visibility = Project.Visibility.PRIVATE
        project = Project.objects.create(
            startup=startup,
            title=f'Project {i}',
            short_description=f'Short desc {i}',
            description=f'Full description {i}',
            target_amount=10000.00,
            status=Project.ProjectStatus.FUNDRAISING,
            visibility=visibility,
        )
        projects.append(project)

    return {'startup': startup, 'projects': projects}


@pytest.mark.django_db
def test_project_list_pagination(api_client, test_data):
    """Check default pagination (page 1 should return at most 6 items)."""
    startup_id = test_data['startup'].pk
    url = reverse('projects:startup-projects-list', kwargs={'startup_id': startup_id})
    response = api_client.get(url, {'page': 1, 'page_size': 6})

    assert response.status_code == status.HTTP_200_OK
    assert response.data['count'] == 5
    assert len(response.data['results']) == 5
    assert response.data['next'] is None


@pytest.mark.django_db
def test_project_list_pagination_configurable(api_client, test_data):
    """Check configurable pagination by changing the page_size parameter."""
    startup_id = test_data['startup'].pk
    url = reverse('projects:startup-projects-list', kwargs={'startup_id': startup_id})
    response = api_client.get(url, {'page_size': 2})

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data['results']) == 2


@pytest.mark.django_db
def test_project_list_filtering_by_status(api_client, test_data):
    """Check optional filtering of projects by their status."""
    startup = test_data['startup']
    Project.objects.create(
        startup=startup,
        title='Early',
        description='D',
        target_amount=100,
        status=Project.ProjectStatus.IDEA,
    )
    url = reverse('projects:startup-projects-list', kwargs={'startup_id': startup.pk})
    response = api_client.get(url, {'status': 'fundraising'})

    assert response.status_code == status.HTTP_200_OK
    assert response.data['count'] == 5
    for project in response.data['results']:
        assert project['status'] == 'fundraising'


@pytest.mark.django_db
def test_project_list_keys_match_spec(api_client, test_data):
    """Check that the JSON response contains the correct fields"""
    startup_id = test_data['startup'].pk
    url = reverse('projects:startup-projects-list', kwargs={'startup_id': startup_id})
    response = api_client.get(url)
    first_project = response.data['results'][0]
    expected_keys = {
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
    }
    assert set(first_project.keys()) == expected_keys


@pytest.mark.django_db
def test_project_list_returns_real_logo_url(api_client, test_data, tmp_path):
    """Check that the serializer returns the actual logo URL if an image exists."""
    with override_settings(MEDIA_ROOT=tmp_path):
        startup = test_data['startup']
        fake_image = SimpleUploadedFile(
            name='test_logo.jpg', content=b'fake_image_bytes', content_type='image/jpeg'
        )
        project_with_logo = Project.objects.create(
            startup=startup,
            title='Project with Logo',
            short_description='Short desc',
            description='Full description',
            target_amount=5000.00,
            status=Project.ProjectStatus.FUNDRAISING,
            logo=fake_image,
        )
        url = reverse(
            'projects:startup-projects-list', kwargs={'startup_id': startup.pk}
        )
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK

        results = response.data['results']
        project_data = next(p for p in results if p['id'] == str(project_with_logo.pk))

        assert 'test_logo' in project_data['logo']
        assert 'placeholder.jpg' not in project_data['logo']


@pytest.mark.django_db
def test_projects_startup_not_found(api_client):
    url = reverse('projects:startup-projects-list', kwargs={'startup_id': 999999})

    response = api_client.get(url)

    assert response.status_code == 404
