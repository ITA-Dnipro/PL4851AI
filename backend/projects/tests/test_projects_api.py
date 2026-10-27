import uuid
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from dashboard.models import SavedProject
from investors.models import InvestorProfile
from projects.models import Project, ProjectAudit
from startups.models import StartupProfile

User = get_user_model()

pytestmark = pytest.mark.api

PROJECT_FIELDS = {
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
VALID_PAYLOAD = {
    'title': 'Handmade Chairs',
    'short_description': 'Oak chairs',
    'description': '<p>full text</p>',
    'target_amount': '50000',
    'currency': 'UAH',
    'tags': ['wood', 'furniture'],
    'visibility': 'public',
}


def create_user(email, role='startup'):
    return User.objects.create_user(
        email=email, first_name='Name', last_name='Surname', role=role
    )


def create_startup(user, name):
    return StartupProfile.objects.create(
        user=user, startup_name=name, startup_phone='380990000000'
    )


def create_project(startup, title='Project', **overrides):
    fields = {
        'startup': startup,
        'title': title,
        'description': 'Description',
        'target_amount': 1000,
    }
    fields.update(overrides)

    return Project.objects.create(**fields)


class ProjectAPITestCase(APITestCase):
    """Common data: an owner and a stranger, each with a startup, and an investor."""

    def setUp(self):
        self.owner = create_user('owner@test.com')
        self.startup = create_startup(self.owner, 'Owner Startup')
        self.stranger = create_user('stranger@test.com')
        self.stranger_startup = create_startup(self.stranger, 'Stranger Startup')
        self.investor = create_user('investor@test.com', role='investor')
        self.list_url = reverse(
            'projects:startup-projects-list', kwargs={'startup_id': self.startup.pk}
        )

    def detail_url(self, project):
        return reverse('projects:project-detail', kwargs={'id': project.pk})

    def history_url(self, project):
        return reverse('projects:project-history', kwargs={'id': project.pk})


class ProjectCreateTest(ProjectAPITestCase):
    def test_owner_creates_project(self):
        """Verify an owner creates a project and gets 201 with Location."""
        self.client.force_authenticate(self.owner)

        response = self.client.post(self.list_url, VALID_PAYLOAD, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get()
        self.assertEqual(project.startup, self.startup)
        self.assertEqual(response.data['id'], str(project.pk))
        self.assertTrue(
            response['Location'].endswith(f'/api/projects/{project.pk}/'),
            response['Location'],
        )
        self.assertEqual(set(response.data), PROJECT_FIELDS)
        self.assertEqual(response.data['slug'], 'handmade-chairs')
        self.assertEqual(response.data['status'], 'idea')
        self.assertEqual(response.data['visibility'], 'public')
        self.assertEqual(response.data['currency'], 'UAH')
        self.assertEqual(response.data['raised_amount'], '0.00')
        self.assertEqual(response.data['target_amount'], '50000.00')
        self.assertEqual(response.data['tags'], ['wood', 'furniture'])

    def test_only_required_fields_are_enough(self):
        """Verify title, description and target_amount are the only required fields."""
        self.client.force_authenticate(self.owner)
        payload = {'title': 'T', 'description': 'D', 'target_amount': '100'}

        response = self.client.post(self.list_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['currency'], 'UAH')
        self.assertEqual(response.data['tags'], [])

    def test_slug_and_startup_in_payload_are_ignored(self):
        """Verify the client can neither choose a slug nor another startup."""
        self.client.force_authenticate(self.owner)
        payload = dict(
            VALID_PAYLOAD, slug='my-own-slug', startup=self.stranger_startup.pk
        )

        response = self.client.post(self.list_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get()
        self.assertEqual(project.slug, 'handmade-chairs')
        self.assertEqual(project.startup, self.startup)

    def test_anonymous_gets_401(self):
        """Verify anonymous creation is rejected."""
        response = self.client.post(self.list_url, VALID_PAYLOAD, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(Project.objects.exists())

    def test_owner_of_another_startup_gets_403(self):
        """Verify a stranger cannot create projects for someone else's startup."""
        self.client.force_authenticate(self.stranger)

        response = self.client.post(self.list_url, VALID_PAYLOAD, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Project.objects.exists())

    def test_investor_without_startup_gets_403(self):
        """Verify a user without a startup profile cannot create projects."""
        self.client.force_authenticate(self.investor)

        response = self.client.post(self.list_url, VALID_PAYLOAD, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_stranger_gets_403_even_with_invalid_data(self):
        """Verify permissions are checked before validation."""
        self.client.force_authenticate(self.stranger)

        response = self.client.post(self.list_url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unknown_startup_gets_404(self):
        """Verify creating for a startup that does not exist gives 404."""
        self.client.force_authenticate(self.owner)
        url = reverse('projects:startup-projects-list', kwargs={'startup_id': 999999})

        response = self.client.post(url, VALID_PAYLOAD, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invalid_data_gets_400_with_field_errors(self):
        """Verify each invalid value is rejected and names the faulty field."""
        self.client.force_authenticate(self.owner)
        cases = {
            'target_amount zero': ({'target_amount': '0'}, 'target_amount'),
            'target_amount negative': ({'target_amount': '-5'}, 'target_amount'),
            'target_amount not a number': ({'target_amount': 'abc'}, 'target_amount'),
            'raised_amount negative': ({'raised_amount': '-1'}, 'raised_amount'),
            'unknown status': ({'status': 'draft'}, 'status'),
            'unknown visibility': ({'visibility': 'secret'}, 'visibility'),
            'lowercase currency': ({'currency': 'uah'}, 'currency'),
            'long currency': ({'currency': 'UAHH'}, 'currency'),
            'tags is a string': ({'tags': 'wood'}, 'tags'),
            'too many tags': ({'tags': [f't{i}' for i in range(11)]}, 'tags'),
            'too long tag': ({'tags': ['x' * 31]}, 'tags'),
            'blank tag': ({'tags': ['']}, 'tags'),
            'missing title': ({'title': None}, 'title'),
            'missing description': ({'description': None}, 'description'),
            'missing target_amount': ({'target_amount': None}, 'target_amount'),
        }
        for name, (overrides, field) in cases.items():
            with self.subTest(name):
                payload = dict(VALID_PAYLOAD, **overrides)
                payload = {k: v for k, v in payload.items() if v is not None}

                response = self.client.post(self.list_url, payload, format='json')

                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.data)
                self.assertFalse(Project.objects.exists())

    def test_logo_cannot_be_set_through_the_api(self):
        """Verify the logo is read-only (uploads are out of scope)."""
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            self.list_url, dict(VALID_PAYLOAD, logo='x.jpg'), format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Project.objects.get().logo)


class ProjectListVisibilityTest(ProjectAPITestCase):
    def setUp(self):
        super().setUp()
        self.public_one = create_project(self.startup, 'Public 1')
        self.public_two = create_project(self.startup, 'Public 2')
        self.private = create_project(self.startup, 'Private', visibility='private')
        self.unlisted = create_project(self.startup, 'Unlisted', visibility='unlisted')
        self.deleted = create_project(
            self.startup, 'Deleted', deleted_at=timezone.now()
        )
        create_project(self.stranger_startup, 'Other startup')

    def titles(self, response):
        return {item['title'] for item in response.data['results']}

    def test_anonymous_sees_only_public_and_not_deleted(self):
        """Verify the public view hides private, unlisted and deleted projects."""
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(self.titles(response), {'Public 1', 'Public 2'})

    def test_stranger_sees_the_same_as_anonymous(self):
        """Verify another user does not see non-public projects either."""
        self.client.force_authenticate(self.stranger)

        response = self.client.get(self.list_url)

        self.assertEqual(self.titles(response), {'Public 1', 'Public 2'})

    def test_owner_sees_own_non_public_but_not_deleted(self):
        """Verify the owner also sees private and unlisted, but not deleted ones."""
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.list_url)

        self.assertEqual(response.data['count'], 4)
        self.assertEqual(
            self.titles(response), {'Public 1', 'Public 2', 'Private', 'Unlisted'}
        )

    def test_newest_first(self):
        """Verify the list is ordered from the newest project."""
        response = self.client.get(self.list_url)

        self.assertEqual(
            [item['title'] for item in response.data['results']],
            ['Public 2', 'Public 1'],
        )

    def test_status_filter(self):
        """Verify the status filter still works."""
        self.public_one.status = Project.ProjectStatus.FUNDRAISING
        self.public_one.save()

        response = self.client.get(self.list_url, {'status': 'fundraising'})

        self.assertEqual(self.titles(response), {'Public 1'})

    def test_number_of_queries_does_not_grow_with_projects(self):
        """Verify the list does not run extra queries per project."""
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.list_url)
        for index in range(5):
            create_project(self.startup, f'More {index}')

        with CaptureQueriesContext(connection) as many:
            response = self.client.get(self.list_url, {'page_size': 100})

        self.assertEqual(response.data['count'], 7)
        self.assertEqual(len(many), len(few))


class ProjectRetrieveTest(ProjectAPITestCase):
    def setUp(self):
        super().setUp()
        self.public = create_project(self.startup, 'Public')
        self.private = create_project(self.startup, 'Private', visibility='private')
        self.unlisted = create_project(self.startup, 'Unlisted', visibility='unlisted')

    def test_public_project_for_anonymous(self):
        """Verify a public project is readable by anyone, with the documented fields."""
        response = self.client.get(self.detail_url(self.public))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), PROJECT_FIELDS)
        self.assertNotIn('deleted_at', response.data)
        self.assertEqual(response.data['id'], str(self.public.pk))

    def test_non_public_projects_are_hidden_from_everyone_but_owner(self):
        """Verify private and unlisted projects give 404 to anonymous and strangers."""
        for project in (self.private, self.unlisted):
            for user in (None, self.stranger, self.investor):
                with self.subTest(project=project.title, user=user):
                    self.client.force_authenticate(user)

                    response = self.client.get(self.detail_url(project))

                    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_reads_non_public_projects(self):
        """Verify the owner reads private and unlisted projects."""
        self.client.force_authenticate(self.owner)

        for project in (self.private, self.unlisted):
            with self.subTest(project=project.title):
                response = self.client.get(self.detail_url(project))

                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unknown_id_gets_404(self):
        """Verify a well-formed but unknown id gives 404."""
        url = reverse('projects:project-detail', kwargs={'id': uuid.uuid4()})

        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_malformed_id_gets_404(self):
        """Verify an id that is not a UUID gives 404."""
        response = self.client.get('/api/projects/not-a-uuid/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deleted_project_gets_404_even_for_owner(self):
        """Verify a soft-deleted project is gone for everyone."""
        self.public.deleted_at = timezone.now()
        self.public.save()
        self.client.force_authenticate(self.owner)

        response = self.client.get(self.detail_url(self.public))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ProjectUpdateTest(ProjectAPITestCase):
    def setUp(self):
        super().setUp()
        self.project = create_project(self.startup, 'Original')
        self.url = self.detail_url(self.project)

    def test_patch_changes_only_given_fields(self):
        """Verify PATCH updates the title, keeps the slug and touches updated_at."""
        self.client.force_authenticate(self.owner)
        before = self.project.updated_at

        response = self.client.patch(self.url, {'title': 'New title'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.title, 'New title')
        self.assertEqual(self.project.slug, 'original')
        self.assertGreater(self.project.updated_at, before)
        self.assertEqual(response.data['title'], 'New title')

    def test_put_replaces_all_given_fields(self):
        """Verify PUT with a complete body replaces the fields."""
        self.client.force_authenticate(self.owner)
        payload = dict(
            VALID_PAYLOAD,
            status='mvp',
            raised_amount='1500.50',
            visibility='private',
        )

        response = self.client.put(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.title, 'Handmade Chairs')
        self.assertEqual(self.project.status, 'mvp')
        self.assertEqual(str(self.project.raised_amount), '1500.50')
        self.assertEqual(self.project.visibility, 'private')
        self.assertEqual(self.project.tags, ['wood', 'furniture'])
        self.assertEqual(self.project.slug, 'original')

    def test_put_without_required_fields_gets_400(self):
        """Verify PUT needs the required fields."""
        self.client.force_authenticate(self.owner)

        response = self.client.put(self.url, {'title': 'Only title'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('description', response.data)
        self.assertIn('target_amount', response.data)

    def test_slug_and_startup_cannot_be_changed(self):
        """Verify slug and startup in the payload are ignored."""
        self.client.force_authenticate(self.owner)

        response = self.client.patch(
            self.url,
            {'slug': 'hacked', 'startup': self.stranger_startup.pk, 'title': 'X'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.slug, 'original')
        self.assertEqual(self.project.startup, self.startup)

    def test_invalid_values_get_400_and_change_nothing(self):
        """Verify invalid updates are rejected."""
        self.client.force_authenticate(self.owner)

        response = self.client.patch(self.url, {'target_amount': '0'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.project.refresh_from_db()
        self.assertEqual(self.project.target_amount, 1000)

    def test_any_status_can_be_set_in_this_iteration(self):
        """Verify status transitions are not checked yet (known gap, see the spec)."""
        self.client.force_authenticate(self.owner)

        response = self.client.patch(self.url, {'status': 'funded'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, 'funded')

    def test_owner_sets_raised_amount(self):
        """Verify the owner updates raised_amount by hand."""
        self.client.force_authenticate(self.owner)

        response = self.client.patch(self.url, {'raised_amount': '250'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['raised_amount'], '250.00')

    def test_anonymous_gets_401(self):
        """Verify anonymous users cannot modify projects."""
        for method in ('patch', 'put', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url, {}, format='json')

                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_stranger_gets_403_for_public_project(self):
        """Verify another startup's owner cannot modify a public project."""
        self.client.force_authenticate(self.stranger)

        for method in ('patch', 'put', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    self.url, {'title': 'Hacked'}, format='json'
                )

                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.project.refresh_from_db()
        self.assertEqual(self.project.title, 'Original')
        self.assertIsNone(self.project.deleted_at)

    def test_stranger_gets_404_for_non_public_project(self):
        """Verify the existence of a private project is not revealed on writes."""
        self.project.visibility = 'private'
        self.project.save()
        self.client.force_authenticate(self.stranger)

        for method in ('patch', 'put', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url, {}, format='json')

                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unknown_project_gets_404_for_owner(self):
        """Verify updating a missing project gives 404."""
        self.client.force_authenticate(self.owner)
        url = reverse('projects:project-detail', kwargs={'id': uuid.uuid4()})

        response = self.client.patch(url, {'title': 'X'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ProjectDeleteTest(ProjectAPITestCase):
    def setUp(self):
        super().setUp()
        self.project = create_project(self.startup, 'Doomed')
        self.url = self.detail_url(self.project)

    def test_delete_is_soft(self):
        """Verify DELETE gives 204, hides the project and keeps the row."""
        self.client.force_authenticate(self.owner)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.project.refresh_from_db()
        self.assertIsNotNone(self.project.deleted_at)
        self.assertEqual(self.client.get(self.list_url).data['count'], 0)

    def test_second_delete_gets_404(self):
        """Verify deleting an already deleted project gives 404."""
        self.client.force_authenticate(self.owner)
        self.client.delete(self.url)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deleted_project_stays_saved_for_investor(self):
        """Verify deleting a project does not remove investors' saved records."""
        investor = InvestorProfile.objects.create(
            user=self.investor, investor_name='I', investor_type='fund'
        )
        saved = SavedProject.objects.create(investor=investor, project=self.project)
        self.client.force_authenticate(self.owner)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(SavedProject.objects.filter(pk=saved.pk).exists())


class ProjectAuditTest(ProjectAPITestCase):
    def test_create_writes_an_audit_entry(self):
        """Verify creation is audited with the author and the initial values."""
        self.client.force_authenticate(self.owner)

        self.client.post(self.list_url, VALID_PAYLOAD, format='json')

        audit = ProjectAudit.objects.get()
        self.assertEqual(audit.user, self.owner)
        self.assertEqual(
            audit.changes['title'], {'before': None, 'after': 'Handmade Chairs'}
        )
        self.assertEqual(
            audit.changes['target_amount'], {'before': None, 'after': '50000.00'}
        )
        self.assertEqual(
            audit.changes['tags'], {'before': None, 'after': ['wood', 'furniture']}
        )
        self.assertNotIn('deleted_at', audit.changes)

    def test_patch_records_before_and_after(self):
        """Verify an update stores exactly the changed fields."""
        project = create_project(self.startup, 'A')
        self.client.force_authenticate(self.owner)

        self.client.patch(self.detail_url(project), {'title': 'B'}, format='json')

        audit = ProjectAudit.objects.get()
        self.assertEqual(audit.project, project)
        self.assertEqual(audit.user, self.owner)
        self.assertEqual(audit.changes, {'title': {'before': 'A', 'after': 'B'}})

    def test_unchanged_patch_writes_nothing(self):
        """Verify an update without real changes is not audited."""
        project = create_project(self.startup, 'A')
        self.client.force_authenticate(self.owner)

        self.client.patch(self.detail_url(project), {'title': 'A'}, format='json')

        self.assertFalse(ProjectAudit.objects.exists())

    def test_delete_is_audited(self):
        """Verify soft delete is audited as a change of deleted_at."""
        project = create_project(self.startup, 'A')
        self.client.force_authenticate(self.owner)

        self.client.delete(self.detail_url(project))

        changes = ProjectAudit.objects.get().changes
        self.assertEqual(list(changes), ['deleted_at'])
        self.assertIsNone(changes['deleted_at']['before'])
        self.assertIsNotNone(changes['deleted_at']['after'])

    def test_change_and_audit_are_saved_together(self):
        """Verify a failing audit rolls the project change back."""
        project = create_project(self.startup, 'A')
        self.client.force_authenticate(self.owner)

        with mock.patch('projects.views.record_audit', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.client.patch(
                    self.detail_url(project), {'title': 'B'}, format='json'
                )

        project.refresh_from_db()
        self.assertEqual(project.title, 'A')

    def test_audit_does_not_store_logo_or_timestamps(self):
        """Verify only the audited fields appear in changes."""
        project = create_project(self.startup, 'A')
        self.client.force_authenticate(self.owner)

        self.client.patch(
            self.detail_url(project), {'title': 'B', 'status': 'mvp'}, format='json'
        )

        changes = ProjectAudit.objects.get().changes
        self.assertEqual(set(changes), {'title', 'status'})


class ProjectHistoryTest(ProjectAPITestCase):
    def setUp(self):
        super().setUp()
        self.project = create_project(self.startup, 'v1')
        self.url = self.history_url(self.project)
        self.client.force_authenticate(self.owner)
        for title in ('v2', 'v3', 'v4'):
            self.client.patch(
                self.detail_url(self.project), {'title': title}, format='json'
            )

    def test_owner_reads_history_newest_first(self):
        """Verify the history is a paginated list, newest entry first."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(
            [entry['changes']['title']['after'] for entry in response.data['results']],
            ['v4', 'v3', 'v2'],
        )
        entry = response.data['results'][0]
        self.assertEqual(set(entry), {'id', 'user', 'timestamp', 'changes'})
        self.assertEqual(entry['user'], self.owner.pk)

    def test_history_is_paginated(self):
        """Verify page_size is honoured."""
        response = self.client.get(self.url, {'page_size': 2})

        self.assertEqual(len(response.data['results']), 2)
        self.assertIsNotNone(response.data['next'])

    def test_anonymous_gets_401(self):
        """Verify the history requires authentication."""
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_stranger_gets_403_for_public_project(self):
        """Verify only the owner can read the history of a public project."""
        self.client.force_authenticate(self.stranger)

        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_stranger_gets_404_for_non_public_project(self):
        """Verify the history of a private project does not reveal its existence."""
        self.project.visibility = 'private'
        self.project.save()
        self.client.force_authenticate(self.stranger)

        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_history_of_deleted_project_gets_404(self):
        """Verify the history of a deleted project is not available."""
        self.client.delete(self.detail_url(self.project))

        self.assertEqual(self.client.get(self.url).status_code, 404)


class StartupProjectsCountTest(ProjectAPITestCase):
    def test_count_includes_only_public_and_not_deleted(self):
        """Verify projects_count in the startup profile follows the public rule."""
        self.startup.is_verified = True
        self.startup.save()
        create_project(self.startup, 'P1')
        create_project(self.startup, 'P2')
        create_project(self.startup, 'Hidden', visibility='private')
        create_project(self.startup, 'Gone', deleted_at=timezone.now())

        response = self.client.get(
            reverse('startups:startup-detail', kwargs={'id': self.startup.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['projects_count'], 2)


class ProjectFixtureTest(TestCase):
    def test_fixture_loads(self):
        """Verify the sample fixture loads 5 projects with different statuses."""
        call_command('loaddata', 'projects', verbosity=0)

        projects = Project.objects.all()
        self.assertEqual(projects.count(), 5)
        self.assertEqual(
            set(projects.values_list('status', flat=True)),
            {'idea', 'mvp', 'fundraising', 'funded', 'closed'},
        )
        self.assertEqual(Project.objects.public().count(), 4)
