from django import forms
from django.contrib import admin
from django.utils import timezone

from .models import Opportunity, OpportunityRequirement, Organization


class CommaListField(forms.CharField):
    """Edits a JSON list of strings as comma-separated text."""

    def prepare_value(self, value):
        if isinstance(value, list):
            return ", ".join(value)
        return value

    def to_python(self, value):
        value = super().to_python(value)
        if not value:
            return []
        return [part.strip() for part in value.split(",") if part.strip()]


class OpportunityAdminForm(forms.ModelForm):
    education_levels = forms.MultipleChoiceField(
        choices=Opportunity.EducationLevel.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Tick the levels the applicant must be at. Tick none if any level is accepted.",
    )
    eligible_regions = CommaListField(
        required=False,
        help_text="Comma-separated, e.g. Africa, Nigeria. Use Worldwide if open to all. Leave blank if not stated.",
    )
    excluded_regions = CommaListField(
        required=False,
        help_text="Comma-separated, e.g. United Kingdom.",
    )

    class Meta:
        model = Opportunity
        fields = "__all__"


class RequirementInline(admin.TabularInline):
    model = OpportunityRequirement
    extra = 3


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    form = OpportunityAdminForm
    list_display = (
        "title",
        "provider",
        "organization",
        "category",
        "deadline",
        "status",
        "last_verified",
    )
    list_filter = ("status", "category", "work_mode", "organization__verified")
    search_fields = ("title", "provider", "description")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at", "details_text")
    inlines = [RequirementInline]
    actions = ["mark_verified_today", "mark_published", "mark_expired", "mark_archived"]

    @admin.display(description="Category details (set by the organization)")
    def details_text(self, obj):
        return "; ".join(f"{k}: {v}" for k, v in (obj.details or {}).items()) or "None"

    @admin.action(description="Mark selected as verified today")
    def mark_verified_today(self, request, queryset):
        updated = queryset.update(last_verified=timezone.localdate())
        self.message_user(request, f"{updated} opportunity(ies) marked verified.")

    @admin.action(description="Publish selected")
    def mark_published(self, request, queryset):
        updated = queryset.update(status=Opportunity.Status.PUBLISHED)
        self.message_user(request, f"{updated} opportunity(ies) published.")

    @admin.action(description="Archive selected (hide from the public site)")
    def mark_archived(self, request, queryset):
        updated = queryset.update(status=Opportunity.Status.ARCHIVED)
        self.message_user(request, f"{updated} opportunity(ies) archived.")

    @admin.action(description="Mark selected as expired")
    def mark_expired(self, request, queryset):
        updated = queryset.update(status=Opportunity.Status.EXPIRED)
        self.message_user(request, f"{updated} opportunity(ies) marked expired.")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "org_type", "contact_email", "website", "verified", "created_at")
    list_filter = ("verified", "org_type")
    search_fields = ("name", "contact_email", "website")
    readonly_fields = ("created_at",)
    actions = ["issue_new_key"]

    @admin.action(description="Issue a new management key (the old key stops working)")
    def issue_new_key(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one organization.", level="error")
            return
        org = queryset.get()
        raw = org.issue_key()
        self.message_user(
            request,
            f"New key for {org.name}: {raw}  Send it to them privately. It will not be shown again.",
        )
