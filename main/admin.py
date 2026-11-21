# main/admin.py
"""Admin registration for Innovar Service models."""
from django.contrib import admin
from .models import Location, Advisor, Evaluation, QRCode, Badge


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "city")
    search_fields = ("name", "city")


@admin.register(Advisor)
class AdvisorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "identifier", "location", "is_active", "evaluation_count", "average_rating")
    list_filter = ("is_active", "location")
    search_fields = ("full_name", "identifier")
    readonly_fields = ("evaluation_count", "average_rating")


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ("id", "advisor", "location", "overall_star", "created_at", "is_valid")
    list_filter = ("overall_star", "created_at", "advisor")
    search_fields = ("advisor__full_name", "client_name", "client_phone")
    readonly_fields = ("created_at",)


@admin.register(QRCode)
class QRCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "location", "advisor", "created_at")
    list_filter = ("location", "advisor")
    readonly_fields = ("created_at", "evaluation_path")
    fields = ("code", "location", "advisor", "image", "created_at", "evaluation_path")


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "color")
    filter_horizontal = ("advisors",)
    search_fields = ("name",)
