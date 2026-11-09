from rest_framework.permissions import BasePermission


def is_manager(user):
  if not user or not user.is_authenticated:
    return False
  if user.is_superuser:
    return True
  m = getattr(user, 'manager', None)
  return bool(m and m.is_active)


def is_doctor(user):
  if not user or not user.is_authenticated:
    return False
  d = getattr(user, 'doctor', None)
  return bool(d and d.is_active)


def is_client(user):
  if not user or not user.is_authenticated:
    return False
  return getattr(user, 'client', None) is not None


class IsManager(BasePermission):
  def has_permission(self, request, view):
    return is_manager(request.user)


class IsDoctor(BasePermission):
  def has_permission(self, request, view):
    return is_doctor(request.user)


class IsClient(BasePermission):
  def has_permission(self, request, view):
    return is_client(request.user)