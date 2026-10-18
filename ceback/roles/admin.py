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