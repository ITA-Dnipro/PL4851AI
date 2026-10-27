import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from projects.models import Project, ProjectAudit
from startups.models import StartupProfile

User = get_user_model()

pytestmark = pytest.mark.api


class ProjectAdminActionsTest(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='admin@test.com',
            password='password123',
            first_name='Admin',
            last_name='User',
            role='startup',
        )
        owner = User.objects.create_user(
            email='owner@test.com', first_name='O', last_name='W', role='startup'
        )
        startup = StartupProfile.objects.create(
            user=owner, startup_name='Admin Startup', startup_phone='380990000000'
        )
        self.first = Project.objects.create(
            startup=startup, title='First', description='D', target_amount=100
        )
        self.second = Project.objects.create(
            startup=startup, title='Second', description='D', target_amount=100
        )
        self.url = reverse('admin:projects_project_changelist')
        self.client.force_login(self.admin_user)

    def run_action(self, action, *projects):
        return self.client.post(
            self.url,
            {
                'action': action,
                '_selected_action': [str(project.pk) for project in projects],
            },
            follow=True,
        )

    def test_changelist_opens(self):
        """Verify the admin list works with the new schema and filters."""
        response = self.client.get(self.url, {'visibility': 'public'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'First')

    def test_change_visibility(self):
        """Verify the visibility actions change the selected projects only."""
        for action, expected in (
            ('make_private', 'private'),
            ('make_unlisted', 'unlisted'),
            ('make_public', 'public'),
        ):
            with self.subTest(action=action):
                self.run_action(action, self.first)

                self.first.refresh_from_db()
                self.second.refresh_from_db()
                self.assertEqual(self.first.visibility, expected)
                self.assertEqual(self.second.visibility, 'public')

    def test_soft_delete_and_restore(self):
        """Verify an admin can soft delete a project and restore it."""
        response = self.run_action('soft_delete', self.first)

        self.first.refresh_from_db()
        self.assertIsNotNone(self.first.deleted_at)
        self.assertContains(response, 'Deleted: 1.')
        self.assertFalse(Project.objects.alive().filter(pk=self.first.pk).exists())

        response = self.run_action('restore', self.first)

        self.first.refresh_from_db()
        self.assertIsNone(self.first.deleted_at)
        self.assertContains(response, 'Restored: 1.')

    def test_actions_are_audited_with_the_admin_as_author(self):
        """Verify every action writes a history entry."""
        self.run_action('make_private', self.first, self.second)

        audits = ProjectAudit.objects.all()
        self.assertEqual(audits.count(), 2)
        for audit in audits:
            self.assertEqual(audit.user, self.admin_user)
            self.assertEqual(
                audit.changes, {'visibility': {'before': 'public', 'after': 'private'}}
            )

    def test_soft_delete_skips_already_deleted(self):
        """Verify an already deleted project keeps its original deletion time."""
        deleted_at = timezone.now() - timezone.timedelta(days=1)
        self.first.deleted_at = deleted_at
        self.first.save()

        self.run_action('soft_delete', self.first)

        self.first.refresh_from_db()
        self.assertEqual(self.first.deleted_at, deleted_at)
        self.assertFalse(ProjectAudit.objects.exists())

    def test_non_staff_cannot_use_the_admin(self):
        """Verify the actions are not available without staff rights."""
        self.client.logout()
        self.client.force_login(
            User.objects.create_user(
                email='plain@test.com', first_name='P', last_name='L', role='startup'
            )
        )

        response = self.run_action('make_private', self.first)

        self.first.refresh_from_db()
        self.assertEqual(self.first.visibility, 'public')
        self.assertNotContains(response, 'Made private')
