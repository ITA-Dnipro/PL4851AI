import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from projects.models import Project
from startups.models import Industry, LocationType, StartupProfile

User = get_user_model()

pytestmark = pytest.mark.models


class ProjectModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='founder2@test.com', role='startup')
        self.startup = StartupProfile.objects.create(
            user=self.user, startup_name='FoodTech', location=LocationType.KYIV_CITY
        )
        self.industry = Industry.objects.get_or_create(
            slug='food', defaults={'industry_name': 'Їжа / Харчова промисловість'}
        )[0]
        self.startup.industries.add(self.industry)
        self.project = Project.objects.create(
            startup=self.startup,
            title='Smart Packaging',
            description='Eco-friendly packaging',
            target_amount=50000.00,
        )

    def create_project(self, **overrides):
        fields = {
            'startup': self.startup,
            'title': 'Another',
            'description': 'D',
            'target_amount': 100,
        }
        fields.update(overrides)

        return Project.objects.create(**fields)

    def test_project_field_presence_and_defaults(self):
        """Verify presence of Project fields and their default values."""
        self.assertEqual(self.project.title, 'Smart Packaging')
        self.assertEqual(self.project.target_amount, 50000.00)
        self.assertEqual(self.project.raised_amount, 0)
        self.assertEqual(self.project.currency, 'UAH')
        self.assertEqual(self.project.status, Project.ProjectStatus.IDEA)
        self.assertEqual(self.project.visibility, Project.Visibility.PUBLIC)
        self.assertEqual(self.project.tags, [])
        self.assertEqual(self.project.project_stage, '')
        self.assertIsNone(self.project.deleted_at)

    def test_primary_key_is_uuid(self):
        """Verify the primary key is a UUID generated automatically."""
        self.assertIsInstance(self.project.pk, uuid.UUID)
        self.assertEqual(self.project.pk, self.project.id)

    def test_foreign_key_relation_with_startup(self):
        """Verify ForeignKey relationship and related_name with StartupProfile."""
        self.assertEqual(self.project.startup, self.startup)
        self.assertIn(self.project, self.startup.projects.all())

    def test_target_amount_must_be_positive(self):
        """Verify CheckConstraint blocks target_amount <= 0."""
        with self.assertRaises(IntegrityError):
            self.create_project(target_amount=0)

    def test_raised_amount_cannot_be_negative(self):
        """Verify CheckConstraint blocks negative raised_amount."""
        with self.assertRaises(IntegrityError):
            self.create_project(raised_amount=-1)

    def test_slug_is_generated_from_title(self):
        """Verify the slug is a transliterated, slugified title."""
        project = self.create_project(title='Крафтові Стільці')

        self.assertEqual(project.slug, 'kraftovi-stiltsi')
        self.assertEqual(self.project.slug, 'smart-packaging')

    def test_slug_is_unique_for_equal_titles(self):
        """Verify equal titles get different slugs."""
        first = self.create_project(title='Same')
        second = self.create_project(title='Same')
        third = self.create_project(title='Same')

        self.assertEqual(
            [first.slug, second.slug, third.slug], ['same', 'same-1', 'same-2']
        )

    def test_slug_fallback_when_title_has_no_letters(self):
        """Verify a title that slugifies to nothing still gets a slug."""
        project = self.create_project(title='!!!')

        self.assertEqual(project.slug, 'project')

    def test_slug_is_kept_on_title_change(self):
        """Verify the slug does not change when the title is edited."""
        self.project.title = 'Renamed'
        self.project.save()

        self.assertEqual(
            Project.objects.get(pk=self.project.pk).slug, 'smart-packaging'
        )

    def test_alive_excludes_soft_deleted(self):
        """Verify alive() hides soft-deleted projects."""
        deleted = self.create_project(title='Gone', deleted_at=timezone.now())

        alive = Project.objects.alive()

        self.assertIn(self.project, alive)
        self.assertNotIn(deleted, alive)

    def test_public_excludes_private_unlisted_and_deleted(self):
        """Verify public() returns only public, not deleted projects."""
        private = self.create_project(title='P', visibility='private')
        unlisted = self.create_project(title='U', visibility='unlisted')
        deleted = self.create_project(title='D', deleted_at=timezone.now())

        public = Project.objects.public()

        self.assertEqual(list(public), [self.project])
        for hidden in (private, unlisted, deleted):
            self.assertNotIn(hidden, public)

    def test_full_clean_rejects_bad_values(self):
        """Verify field validators: currency format, amounts, tags."""
        cases = {
            'currency': {'currency': 'uah'},
            'currency length': {'currency': 'UAHH'},
            'target_amount': {'target_amount': 0},
            'raised_amount': {'raised_amount': -1},
            'tags count': {'tags': ['t'] * 11},
            'tag length': {'tags': ['x' * 31]},
        }
        for name, overrides in cases.items():
            with self.subTest(name):
                project = Project(
                    startup=self.startup,
                    title='V',
                    slug=f'v-{name}'.replace(' ', '-'),
                    description='D',
                    target_amount=100,
                )
                for field, value in overrides.items():
                    setattr(project, field, value)

                with self.assertRaises(ValidationError):
                    project.full_clean()
