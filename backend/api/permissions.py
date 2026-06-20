from rest_framework.permissions import BasePermission


def _get_groups(request) -> list[str]:
    return getattr(request.user, 'claims', {}).get('groups', [])


class HasAnyRole(BasePermission):
    roles: list[str] = []

    def has_permission(self, request, view):
        return any(r in _get_groups(request) for r in self.roles)


class IsManager(HasAnyRole):
    roles = ['manager']


class IsManagerOrCuisinier(HasAnyRole):
    roles = ['manager', 'cuisinier']


class IsManagerOrServeur(HasAnyRole):
    roles = ['manager', 'serveur']


class IsAnyStaff(HasAnyRole):
    roles = ['manager', 'cuisinier', 'serveur']
