from django import forms

from ai_engine.profile import LOCATION_CHOICES, Profile

from .models import Opportunity


class ProfileForm(forms.Form):
    """Validates the profile the browser sends. Nothing here is stored."""

    country = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "list": "country-options",
                "autocomplete": "country-name",
                "placeholder": "e.g. Nigeria",
            }
        ),
    )
    education_level = forms.ChoiceField(
        required=False,
        choices=[("", "Not sure or prefer not to say")]
        + list(Opportunity.EducationLevel.choices),
    )
    field_of_study = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Computer Science"}),
    )
    current_qualification = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. BSc in progress"}),
    )
    skills = forms.CharField(
        max_length=600,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Python, HTML, CSS"}),
    )
    experience = forms.CharField(
        max_length=600,
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 3, "placeholder": "e.g. Personal software projects"}
        ),
    )
    interests = forms.CharField(
        max_length=600,
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "e.g. AI engineering, software development"}
        ),
    )
    categories = forms.MultipleChoiceField(
        choices=Opportunity.Category.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    location_preferences = forms.MultipleChoiceField(
        choices=LOCATION_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    career_goals = forms.CharField(
        max_length=300,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Become an AI engineer"}),
    )

    def to_profile(self):
        return Profile.from_mapping(self.cleaned_data)
