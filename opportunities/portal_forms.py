import re
from datetime import date

from django import forms
from django.utils import timezone

from .categories import EMPLOYMENT_TYPES, all_extra_keys, clean_details, extra_fields_for
from .models import Opportunity, Organization

MAX_LINES = 15
LINE_MAX = 300


def _http_url(value):
    if value and not re.match(r"^https?://", value, re.I):
        raise forms.ValidationError("The link must start with http:// or https://")
    return value


class HoneypotMixin(forms.Form):
    """A field real visitors never see. Bots that fill it are rejected."""

    nickname = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}),
        label="Leave this empty",
    )

    def clean_nickname(self):
        if self.cleaned_data.get("nickname"):
            raise forms.ValidationError("Rejected.")
        return ""


class OrganizationForm(HoneypotMixin, forms.ModelForm):
    class Meta:
        model = Organization
        fields = ["name", "org_type", "contact_email", "website", "location", "phone", "about"]
        labels = {
            "name": "Organization name",
            "org_type": "Type of organization",
            "contact_email": "Official contact email",
            "website": "Official website",
            "location": "Location (city and country)",
            "phone": "Phone (optional)",
            "about": "About the organization (optional)",
        }
        widgets = {"about": forms.Textarea(attrs={"rows": 3})}

    def clean_website(self):
        return _http_url(self.cleaned_data["website"])

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())


def parse_lines(text):
    out, seen = [], set()
    for raw in (text or "").splitlines():
        line = " ".join(raw.strip().lstrip("-*• ").split())[:LINE_MAX]
        if line and line.casefold() not in seen:
            seen.add(line.casefold())
            out.append(line)
    return out[:MAX_LINES]


class OpportunityForm(HoneypotMixin, forms.Form):
    title = forms.CharField(max_length=200)
    category = forms.ChoiceField(choices=Opportunity.Category.choices)
    description = forms.CharField(
        max_length=4000, widget=forms.Textarea(attrs={"rows": 6}),
        help_text="What the opportunity involves.",
    )
    benefits = forms.CharField(
        max_length=2000, required=False, widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Salary, funding, training, or other benefits.",
    )
    country = forms.CharField(
        max_length=100, required=False, label="Location",
        help_text="Country or city. Leave blank if it is open to all countries.",
    )
    work_mode = forms.ChoiceField(choices=Opportunity.WorkMode.choices)
    education_levels = forms.MultipleChoiceField(
        choices=Opportunity.EducationLevel.choices, required=False,
        widget=forms.CheckboxSelectMultiple, label="Education level required",
        help_text="Tick none if any level can apply.",
    )
    eligible_regions = forms.CharField(
        max_length=300, required=False, label="Who can apply (countries or regions)",
        help_text="Comma-separated, e.g. Nigeria, Africa. Write Worldwide if open to all. Leave blank if you do not restrict it.",
    )
    excluded_regions = forms.CharField(
        max_length=300, required=False, label="Who cannot apply",
        help_text="Comma-separated countries or regions, if any.",
    )
    mandatory_requirements = forms.CharField(
        max_length=3000, required=False, widget=forms.Textarea(attrs={"rows": 5}),
        label="Mandatory requirements", help_text="One per line. Applicants must meet these.",
    )
    preferred_requirements = forms.CharField(
        max_length=3000, required=False, widget=forms.Textarea(attrs={"rows": 3}),
        label="Preferred requirements", help_text="One per line. Nice to have.",
    )
    deadline = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}),
        label="Application deadline", help_text="Leave blank if applications are rolling.",
    )
    official_url = forms.URLField(max_length=500, label="Official application link")
    how_to_apply = forms.CharField(
        max_length=1500, required=False, widget=forms.Textarea(attrs={"rows": 3}),
        label="How to apply (optional)", help_text="Extra instructions, if the link is not enough.",
    )
    contact_info = forms.CharField(max_length=200, required=False, label="Contact for applicants (optional)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_keys = []
        for key, (label, kind) in all_extra_keys().items():
            name = f"x_{key}"
            if kind == "choice:employment":
                field = forms.ChoiceField(
                    required=False, label=label,
                    choices=[("", "Not specified")] + [(v, v) for v in EMPLOYMENT_TYPES],
                )
            else:
                field = forms.CharField(required=False, max_length=200, label=label)
            field.is_extra = True
            self.fields[name] = field
            self.extra_keys.append(name)

    def category_for_extras(self):
        return self.data.get("category") or self.initial.get("category") or ""

    def clean_official_url(self):
        return _http_url(self.cleaned_data["official_url"])

    def clean_deadline(self):
        value = self.cleaned_data.get("deadline")
        if value and value < timezone.localdate():
            raise forms.ValidationError("The deadline is in the past.")
        return value

    def clean_eligible_regions(self):
        return _split(self.cleaned_data.get("eligible_regions"))

    def clean_excluded_regions(self):
        return _split(self.cleaned_data.get("excluded_regions"))

    def clean(self):
        data = super().clean()
        mandatory = parse_lines(data.get("mandatory_requirements"))
        preferred = parse_lines(data.get("preferred_requirements"))
        if not mandatory and not preferred:
            self.add_error(
                "mandatory_requirements",
                "List at least one requirement. Applicants and the eligibility checker rely on them.",
            )
        data["mandatory_list"], data["preferred_list"] = mandatory, preferred
        category = data.get("category")
        raw = {k[2:]: data.get(k) for k in self.extra_keys}
        data["details"] = clean_details(category, raw) if category else {}
        return data

    @classmethod
    def from_opportunity(cls, opp):
        reqs = list(opp.requirements.all())
        initial = {
            "title": opp.title, "category": opp.category, "description": opp.description,
            "benefits": opp.benefits, "country": opp.country, "work_mode": opp.work_mode,
            "education_levels": opp.education_levels,
            "eligible_regions": ", ".join(opp.eligible_regions),
            "excluded_regions": ", ".join(opp.excluded_regions),
            "deadline": opp.deadline, "official_url": opp.official_url,
            "how_to_apply": opp.how_to_apply, "contact_info": opp.contact_info,
            "mandatory_requirements": "\n".join(r.text for r in reqs if r.requirement_type == "mandatory"),
            "preferred_requirements": "\n".join(r.text for r in reqs if r.requirement_type == "preferred"),
        }
        for key, value in (opp.details or {}).items():
            initial[f"x_{key}"] = value
        return cls(initial=initial)


def _split(value):
    out, seen = [], set()
    for part in re.split(r"[,;\n]+", value or ""):
        item = " ".join(part.split())[:80]
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            out.append(item)
    return out[:20]
