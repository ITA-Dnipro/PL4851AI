import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

from startups.models import custom_slugify

MAX_LENGTH_PROJECT_TITLE = 255
MAX_LENGTH_PROJECT_STAGE = 100
MAX_LENGTH_STATUS = 20
MAX_LENGTH_VISIBILITY = 20
MAX_LENGTH_SHORT_DESCRIPTION = 500
MAX_LENGTH_SLUG = 255
MAX_LENGTH_CURRENCY = 3
MAX_LENGTH_TAG = 30
MAX_TAGS = 10
MAX_LENGTH_LOGO = 255
TARGET_AMOUNT_MAX_DIGITS = 12
TARGET_AMOUNT_DECIMAL_PLACES = 2
RAISED_AMOUNT_MAX_DIGITS = 12
RAISED_AMOUNT_DECIMAL_PLACES = 2
DEFAULT_CURRENCY = 'UAH'
CURRENCY_PATTERN = r'^[A-Z]{3}$'


class ProjectQuerySet(models.QuerySet):
    def alive(self):
        """Projects that are not soft-deleted."""
        return self.filter(deleted_at__isnull=True)

    def public(self):
        """Projects visible to everyone."""
        return self.alive().filter(visibility=Project.Visibility.PUBLIC)


class Project(models.Model):
    class ProjectStatus(models.TextChoices):
        IDEA = 'idea', 'Ідея'
        MVP = 'mvp', 'MVP'
        FUNDRAISING = 'fundraising', 'Збір коштів'
        FUNDED = 'funded', 'Профінансований'
        CLOSED = 'closed', 'Закритий'

    class Visibility(models.TextChoices):
        PUBLIC = 'public', 'Публічний'
        PRIVATE = 'private', 'Приватний'
        UNLISTED = 'unlisted', 'Поза списками'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    startup = models.ForeignKey(
        'startups.StartupProfile',
        on_delete=models.RESTRICT,
        related_name='projects',
    )
    title = models.CharField(max_length=MAX_LENGTH_PROJECT_TITLE)
    slug = models.SlugField(max_length=MAX_LENGTH_SLUG, unique=True, blank=True)
    short_description = models.CharField(
        max_length=MAX_LENGTH_SHORT_DESCRIPTION, blank=True, default=''
    )
    description = models.TextField()
    status = models.CharField(
        max_length=MAX_LENGTH_STATUS,
        choices=ProjectStatus.choices,
        default=ProjectStatus.IDEA,
    )
    target_amount = models.DecimalField(
        max_digits=TARGET_AMOUNT_MAX_DIGITS,
        decimal_places=TARGET_AMOUNT_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    raised_amount = models.DecimalField(
        max_digits=RAISED_AMOUNT_MAX_DIGITS,
        decimal_places=RAISED_AMOUNT_DECIMAL_PLACES,
        default=0,
        validators=[MinValueValidator(Decimal('0'))],
    )
    currency = models.CharField(
        max_length=MAX_LENGTH_CURRENCY,
        default=DEFAULT_CURRENCY,
        validators=[
            RegexValidator(
                CURRENCY_PATTERN, 'Currency must be 3 uppercase Latin letters.'
            )
        ],
    )
    tags = ArrayField(
        models.CharField(max_length=MAX_LENGTH_TAG),
        size=MAX_TAGS,
        blank=True,
        default=list,
    )
    visibility = models.CharField(
        max_length=MAX_LENGTH_VISIBILITY,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    project_stage = models.CharField(
        max_length=MAX_LENGTH_PROJECT_STAGE, blank=True, default=''
    )
    logo = models.ImageField(
        upload_to='projects/logos/%Y/%m/',
        blank=True,
        null=True,
        max_length=MAX_LENGTH_LOGO,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)

    objects = ProjectQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=['project_stage'], name='project_stage_idx'),
            models.Index(fields=['status'], name='project_status_idx'),
            models.Index(fields=['visibility'], name='project_visibility_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(target_amount__gt=0),
                name='project_target_amount_gt_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(raised_amount__gte=0),
                name='project_raised_amount_gte_zero',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()

        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        base_slug = custom_slugify(self.title) or 'project'
        base_slug = base_slug[:MAX_LENGTH_SLUG].rstrip('-')
        unique_slug = base_slug
        counter = 1

        while Project.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
            suffix = f'-{counter}'
            allowed_base_len = MAX_LENGTH_SLUG - len(suffix)
            unique_slug = f"{base_slug[:allowed_base_len].rstrip('-')}{suffix}"
            counter += 1

        return unique_slug

    def __str__(self):
        return self.title


class ProjectAudit(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='audits',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='project_audits',
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    changes = models.JSONField(default=dict)

    class Meta:
        ordering = ['-timestamp', '-id']
        indexes = [
            models.Index(fields=['project', '-timestamp'], name='project_audit_idx'),
        ]

    def __str__(self):
        return f'{self.project_id} @ {self.timestamp:%Y-%m-%d %H:%M:%S}'
