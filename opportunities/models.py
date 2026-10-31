import hashlib
import secrets

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify


class Organization(models.Model):
    """Who is offering opportunities. There are no logins: an organization holds
    a secret management key, and only a hash of it is stored."""

    class OrgType(models.TextChoices):
        EMPLOYER = "employer", "Employer or company"
        UNIVERSITY = "university", "University or school"
        SCHOLARSHIP = "scholarship_provider", "Scholarship or grant provider"
        NGO = "ngo", "NGO or foundation"
        GOVERNMENT = "government", "Government agency"
        OTHER = "other", "Other"

    name = models.CharField(max_length=200)
    org_type = models.CharField(max_length=24, choices=OrgType.choices)
    contact_email = models.EmailField()
    website = models.URLField(max_length=300)
    location = models.CharField(max_length=150, help_text="City and country.")
    phone = models.CharField(max_length=40, blank=True)
    about = models.TextField(blank=True, max_length=1000)
    verified = models.BooleanField(
        default=False,
        help_text="Tick only after you have checked the organization is real (website, email domain).",
    )
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @staticmethod
    def hash_key(raw):
        return hashlib.sha256((raw or "").strip().encode()).hexdigest()

    def issue_key(self):
        """Create a new key, store its hash, and return the raw key once.
        The raw key is never stored. Any older key stops working."""
        raw = "ops_" + secrets.token_urlsafe(24)
        self.key_hash = self.hash_key(raw)
        self.save(update_fields=["key_hash"])
        return raw

    @classmethod
    def for_key(cls, raw):
        raw = (raw or "").strip()
        if not raw or len(raw) > 100:
            return None
        return cls.objects.filter(key_hash=cls.hash_key(raw)).first()


class OpportunityQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Opportunity.Status.PUBLISHED)

    def visible(self):
        """Statuses the public may see: live listings and ones that have ended."""
        S = Opportunity.Status
        return self.filter(status__in=[S.PUBLISHED, S.EXPIRED, S.CLOSED, S.FILLED])

    def open(self):
        """Not past its deadline. A blank deadline means rolling/open."""
        today = timezone.localdate()
        return self.filter(Q(deadline__isnull=True) | Q(deadline__gte=today))


class Opportunity(models.Model):
    class Category(models.TextChoices):
        SCHOLARSHIP = "scholarship", "Scholarship"
        INTERNSHIP = "internship", "Internship"
        FELLOWSHIP = "fellowship", "Fellowship"
        GRANT = "grant", "Grant"
        JOB = "job", "Job"
        TRAINING = "training", "Training programme"

    class WorkMode(models.TextChoices):
        REMOTE = "remote", "Remote"
        PHYSICAL = "physical", "Physical"
        HYBRID = "hybrid", "Hybrid"

    class EducationLevel(models.TextChoices):
        SECONDARY = "secondary", "Secondary school"
        UNDERGRADUATE = "undergraduate", "Undergraduate (in progress)"
        GRADUATE = "graduate", "Bachelor's completed"
        POSTGRADUATE = "postgraduate", "Master's completed"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending review"
        PUBLISHED = "published", "Published"
        PAUSED = "paused", "Paused"
        CLOSED = "closed", "Closed"
        FILLED = "filled", "Filled"
        EXPIRED = "expired", "Expired"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    provider = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.TextField()
    benefits = models.TextField(blank=True)
    country = models.CharField(
        max_length=100,
        blank=True,
        help_text="Country or location. Leave blank if open to all countries.",
    )
    work_mode = models.CharField(
        max_length=10, choices=WorkMode.choices, default=WorkMode.PHYSICAL
    )
    education_levels = models.JSONField(
        default=list,
        blank=True,
        help_text="Levels the applicant must be at. Leave empty if any level is accepted.",
    )
    eligible_regions = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Who may apply: country names or groups such as Africa, Commonwealth, "
            "Worldwide. Leave empty if the provider does not say."
        ),
    )
    excluded_regions = models.JSONField(
        default=list,
        blank=True,
        help_text="Countries or groups that may not apply, e.g. United Kingdom.",
    )
    deadline = models.DateField(
        null=True, blank=True, help_text="Leave blank if there is no fixed deadline."
    )
    official_url = models.URLField(max_length=500)
    source_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    organization = models.ForeignKey(
        Organization,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="opportunities",
        help_text="Empty for listings researched by OppScout.",
    )
    how_to_apply = models.TextField(
        blank=True, help_text="Steps or instructions, if different from the official link."
    )
    contact_info = models.CharField(max_length=200, blank=True)
    details = models.JSONField(default=dict, blank=True, editable=False)
    last_verified = models.DateField(null=True, blank=True)
    # Precomputed offline; filled by a management command later.
    embedding = models.JSONField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OpportunityQuerySet.as_manager()

    class Meta:
        ordering = ["title"]
        verbose_name_plural = "opportunities"
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["deadline"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.provider})"

    def clean(self):
        super().clean()
        errors = {}
        levels = self.education_levels
        if not isinstance(levels, list) or any(
            v not in self.EducationLevel.values for v in levels
        ):
            errors["education_levels"] = "Must be a list of valid education levels."
        for name in ("eligible_regions", "excluded_regions"):
            value = getattr(self, name)
            if not isinstance(value, list) or any(
                not isinstance(i, str) or not i.strip() for i in value
            ):
                errors[name] = "Must be a list of non-empty text values."
        if errors:
            raise ValidationError(errors)

    def accepts_education(self, level):
        """Empty means the provider names no level, so no one is excluded."""
        return not self.education_levels or level in self.education_levels

    @property
    def education_levels_display(self):
        if not self.education_levels:
            return "Any level"
        return ", ".join(
            self.EducationLevel(v).label
            for v in self.education_levels
            if v in self.EducationLevel.values
        )

    @property
    def posted_by_organization(self):
        return self.organization_id is not None

    @property
    def closed_notice(self):
        """Shown on the public page for listings that are no longer taking applications."""
        if self.status == self.Status.FILLED:
            return "This opportunity has been filled."
        if self.status == self.Status.CLOSED:
            return "The organization has closed applications."
        if self.is_expired:
            return "This opportunity appears to be closed. Check the official page for its current status."
        return ""

    @property
    def detail_items(self):
        from .categories import details_for_display

        return details_for_display(self.category, self.details)

    @property
    def eligibility_summary(self):
        parts = []
        if self.eligible_regions:
            parts.append("Open to: " + ", ".join(self.eligible_regions))
        if self.excluded_regions:
            parts.append("Not open to: " + ", ".join(self.excluded_regions))
        return ". ".join(parts) if parts else "Not specified. Check the official page."

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        base = slugify(self.title)[:200] or "opportunity"
        candidate = base
        n = 2
        while Opportunity.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            candidate = f"{base}-{n}"
            n += 1
        return candidate

    @property
    def days_left(self):
        if self.deadline is None:
            return None
        return (self.deadline - timezone.localdate()).days

    @property
    def is_expired(self):
        """Not accepting applications: expired, closed, filled, or past its deadline."""
        if self.status in (self.Status.EXPIRED, self.Status.CLOSED, self.Status.FILLED):
            return True
        return self.deadline is not None and self.deadline < timezone.localdate()

    @property
    def deadline_tone(self):
        """closed, urgent (a week or less), soon (a month or less), open or none."""
        if self.is_expired:
            return "closed"
        if self.deadline is None:
            return "none"
        days = self.days_left
        if days <= 7:
            return "urgent"
        if days <= 30:
            return "soon"
        return "open"

    @property
    def deadline_label(self):
        if self.status == self.Status.FILLED:
            return "Filled"
        if self.is_expired:
            return "Closed"
        if self.deadline is None:
            return "No fixed deadline"
        days = self.days_left
        if days == 0:
            return "Closes today"
        if days == 1:
            return "Closes tomorrow"
        return f"Closes in {days} days"


class OpportunityRequirement(models.Model):
    class RequirementType(models.TextChoices):
        MANDATORY = "mandatory", "Mandatory"
        PREFERRED = "preferred", "Preferred"
        UNCLEAR = "unclear", "Unclear (review)"

    class Category(models.TextChoices):
        EDUCATION = "education", "Education"
        LOCATION = "location", "Location"
        EXPERIENCE = "experience", "Experience"
        SKILL = "skill", "Skill"
        AGE = "age", "Age"
        OTHER = "other", "Other"

    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.CASCADE, related_name="requirements"
    )
    text = models.CharField(max_length=500)
    requirement_type = models.CharField(
        max_length=10,
        choices=RequirementType.choices,
        default=RequirementType.UNCLEAR,
    )
    category = models.CharField(max_length=12, choices=Category.choices, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    source_reference = models.CharField(
        max_length=500,
        blank=True,
        help_text="Where this requirement was published (URL or document name).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"[{self.requirement_type}] {self.text[:60]}"


class AIUsage(models.Model):
    """Counters that cap AI calls (per visitor per hour, per minute, per day).

    Visitors are stored only as a salted hash inside `key`, never as an IP.
    """

    key = models.CharField(max_length=100, unique=True)
    count = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.key}: {self.count}"
