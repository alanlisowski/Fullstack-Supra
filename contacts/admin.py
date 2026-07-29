from django.contrib import admin

from .models import Contact, ContactStatus


@admin.register(ContactStatus)
class ContactStatusAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "city", "status", "owner", "created_at")
    list_filter = ("status", "city")
    search_fields = ("first_name", "last_name", "email", "phone")
