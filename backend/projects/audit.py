from datetime import datetime
from decimal import Decimal

from projects.models import ProjectAudit

AUDITED_FIELDS = (
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
    'deleted_at',
)
EMPTY_SNAPSHOT = dict.fromkeys(AUDITED_FIELDS)
MONEY_QUANTUM = Decimal('0.01')


def _serialize(value):
    """Turns a field value into something a JSONField can store."""
    if isinstance(value, Decimal):
        return str(value.quantize(MONEY_QUANTUM))

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, (list, tuple)):
        return list(value)

    return value


def snapshot(project):
    """Audited field values of a project as a JSON-friendly dict."""
    return {field: _serialize(getattr(project, field)) for field in AUDITED_FIELDS}


def record_audit(project, user, before):
    """Stores the difference between `before` and the current state of the project.

    Returns the created ProjectAudit, or None if nothing changed.
    """
    after = snapshot(project)
    changes = {
        field: {'before': before[field], 'after': after[field]}
        for field in AUDITED_FIELDS
        if before[field] != after[field]
    }
    if not changes:
        return None

    audit_user = user if user is not None and user.is_authenticated else None

    return ProjectAudit.objects.create(
        project=project, user=audit_user, changes=changes
    )
