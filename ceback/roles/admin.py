from django.contrib import admin
from .models import Client, Doctor, Manager

# Register your models here.
admin.site.register(Client)

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
  list_display = ('full_name', 'specialization', 'phone', 'is_active', 'user')
  autocomplete_fields = ('user',)
  search_fields = ('full_name', 'phone', 'specialization')
  list_filter = ('is_active', 'specialization')

@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
  list_display = (
      'full_name',
      'phone',
      'department',
      'is_active',
      'created_at',
  )
  search_fields = ('full_name', 'phone')
  list_filter = ('is_active', 'department')

  from django.contrib import admin
from django.db import transaction

from .models import Notification
from .notifications import _push


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
  list_display = ('id', 'user', 'kind', 'short_text', 'is_read', 'created_at')
  list_filter = ('kind', 'is_read', 'created_at')
  search_fields = ('text', 'user__username', 'user__email')
  autocomplete_fields = ('user',)
  raw_id_fields = ('booking', 'slot')
  readonly_fields = ('created_at',)
  actions = ['mark_read', 'mark_unread']

  @admin.display(description='Text')
  def short_text(self, obj):
    return obj.text[:60]

  def save_model(self, request, obj, form, change):
    super().save_model(request, obj, form, change)
    if not change:  # push только для новых уведомлений
      transaction.on_commit(lambda: _push(obj))

  @admin.action(description='Mark as read')
  def mark_read(self, request, queryset):
    queryset.update(is_read=True)

  @admin.action(description='Mark as unread')
  def mark_unread(self, request, queryset):
    queryset.update(is_read=False)