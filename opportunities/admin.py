from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from ai_engine.fetching import Fetcher
from ai_engine.providers import ProviderError

from . import scouting
from .models import Opportunity, OpportunityRequirement, Organization, Report, ScoutLog, Source
from .services import get_provider


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
        "needs_review",
    )
    list_filter = ("status", "scouted", "category", "work_mode", "organization__verified")
    search_fields = ("title", "provider", "description")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at", "details_text", "proposed_changes", "changes_noted_at", "scout_source")
    exclude = ("pending_changes",)
    inlines = [RequirementInline]
    actions = ["mark_verified_today", "mark_published", "mark_expired", "mark_archived",
               "apply_proposed_changes", "dismiss_proposed_changes"]

    @admin.display(boolean=True, description="Changes to review")
    def needs_review(self, obj):
        return bool(obj.pending_changes)

    @admin.display(description="Changes the scouting job saw on the source page")
    def proposed_changes(self, obj):
        changes = obj.pending_changes or {}
        if not changes:
            return "None"
        rows = []
        for key, value in changes.items():
            if isinstance(value, dict):
                rows.append(format_html("<li><b>{}</b>: {} &rarr; {}</li>", key, value.get("old"), value.get("new")))
            else:
                rows.append(format_html("<li><b>{}</b>: {}</li>", key, "; ".join(value)))
        return format_html("<ul>{}</ul><p>Use the actions on the list page to apply or dismiss.</p>", format_html("".join(rows)))

    @admin.action(description="Apply the proposed changes from the source page")
    def apply_proposed_changes(self, request, queryset):
        n = 0
        for opp in queryset.exclude(pending_changes={}):
            scouting.apply_changes(opp)
            n += 1
        self.message_user(request, f"Applied changes to {n} listing(s) and marked them verified today.")

    @admin.action(description="Dismiss the proposed changes (keep the listing as it is)")
    def dismiss_proposed_changes(self, request, queryset):
        n = 0
        for opp in queryset.exclude(pending_changes={}):
            scouting.dismiss_changes(opp)
            n += 1
        self.message_user(request, f"Dismissed changes on {n} listing(s).")

    @admin.display(description="Category details (set by the organization)")
    def details_text(self, obj):
        return "; ".join(f"{k}: {v}" for k, v in (obj.details or {}).items()) or "None"

    @admin.action(description="Mark selected as verified today")
    def mark_verified_today(self, request, queryset):
        updated = queryset.update(last_verified=timezone.localdate())
        self.message_user(request, f"{updated} opportunity(ies) marked verified.")

    @admin.action(description="Publish selected")
    def mark_published(self, request, queryset):
        # Publishing a scouted draft means you reviewed it against the page.
        queryset.filter(scouted=True, last_verified__isnull=True).update(last_verified=timezone.localdate())
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


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("display_name", "status", "found_by", "last_checked", "fail_count", "last_error")
    list_filter = ("status", "found_by")
    search_fields = ("url", "name", "note")
    readonly_fields = ("found_by", "last_checked", "last_error", "fail_count", "created_at")
    actions = ["approve", "reject", "check_now"]
    change_list_template = "admin/opportunities/source/change_list.html"

    @admin.display(description="Source")
    def display_name(self, obj):
        return obj.name or obj.url

    @admin.action(description="Approve selected (they will be checked automatically)")
    def approve(self, request, queryset):
        n = queryset.update(status=Source.Status.APPROVED, fail_count=0)
        self.message_user(request, f"{n} source(s) approved.")

    @admin.action(description="Reject selected")
    def reject(self, request, queryset):
        n = queryset.update(status=Source.Status.REJECTED)
        self.message_user(request, f"{n} source(s) rejected.")

    @admin.action(description="Check selected now (up to 2 at a time)")
    def check_now(self, request, queryset):
        try:
            provider = get_provider()
        except ProviderError:
            self.message_user(request, "GEMINI_API_KEY is not set.", level=messages.ERROR)
            return
        fetcher = Fetcher()
        for source in queryset.exclude(status=Source.Status.REJECTED)[:2]:
            outcome, _ = scouting.scout_source(source, provider, fetcher, force=True)
            self.message_user(request, f"{source}: {outcome}")

    def get_urls(self):
        custom = [path("discover/", self.admin_site.admin_view(self.discover_view), name="opportunities_source_discover")]
        return custom + super().get_urls()

    def discover_view(self, request):
        context = {**self.admin_site.each_context(request), "title": "Find sources with AI", "opts": self.model._meta}
        if request.method == "POST":
            topic = request.POST.get("topic", "").strip()
            if not topic:
                messages.error(request, "Type what to look for.")
            else:
                try:
                    added, checked, notes = scouting.discover(topic, get_provider(), Fetcher(), max_new=4)
                except ProviderError as exc:
                    messages.error(request, getattr(exc, "public_message", "The AI service had a problem."))
                else:
                    messages.success(request, f"Checked {checked} page(s) and proposed {len(added)} source(s).")
                    for note in notes[:5]:
                        messages.info(request, note)
                    return redirect(reverse("admin:opportunities_source_changelist") + "?status__exact=proposed")
        return render(request, "admin/opportunities/source/discover.html", context)


@admin.register(ScoutLog)
class ScoutLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "source", "outcome", "detail")
    list_filter = ("outcome",)
    readonly_fields = ("source", "outcome", "detail", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("created_at", "opportunity", "message", "contact", "resolved")
    list_filter = ("resolved",)
    readonly_fields = ("opportunity", "message", "contact", "created_at")
    actions = ["mark_resolved"]

    @admin.action(description="Mark selected as resolved")
    def mark_resolved(self, request, queryset):
        self.message_user(request, f"{queryset.update(resolved=True)} report(s) resolved.")
