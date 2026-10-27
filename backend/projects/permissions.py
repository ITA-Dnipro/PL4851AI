from rest_framework import permissions


def is_startup_owner(user, startup):
    """True if the user owns the startup profile."""
    return bool(user and user.is_authenticated and startup.user_id == user.pk)


class IsStartupOwnerOrReadOnly(permissions.BasePermission):
    """Anyone can read; only the owner of the project's startup can change it."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True

        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True

        return is_startup_owner(request.user, obj.startup)
