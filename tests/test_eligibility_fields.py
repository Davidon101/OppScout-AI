from django.core.exceptions import ValidationError
from django.test import TestCase

from opportunities.admin import OpportunityAdminForm
from opportunities.models import Opportunity
from tests.test_opportunities import make_opportunity


class EducationLevelTests(TestCase):
    def test_empty_levels_accept_everyone(self):
        opp = make_opportunity()
        self.assertTrue(opp.accepts_education("undergraduate"))
        self.assertEqual(opp.education_levels_display, "Any level")

    def test_multiple_levels(self):
        opp = make_opportunity(education_levels=["graduate", "postgraduate"])
        self.assertTrue(opp.accepts_education("graduate"))
        self.assertTrue(opp.accepts_education("postgraduate"))
        self.assertFalse(opp.accepts_education("undergraduate"))
        self.assertEqual(
            opp.education_levels_display, "Bachelor's completed, Master's completed"
        )

    def test_unknown_level_is_rejected(self):
        opp = Opportunity(
            title="X",
            provider="Y",
            category="grant",
            description="d",
            official_url="https://example.com",
            education_levels=["wizard"],
        )
        with self.assertRaises(ValidationError) as ctx:
            opp.full_clean()
        self.assertIn("education_levels", ctx.exception.message_dict)


class RegionTests(TestCase):
    def test_unspecified_regions(self):
        opp = make_opportunity()
        self.assertIn("Not specified", opp.eligibility_summary)

    def test_summary_lists_open_and_excluded(self):
        opp = make_opportunity(
            eligible_regions=["Worldwide"], excluded_regions=["United Kingdom"]
        )
        self.assertEqual(
            opp.eligibility_summary, "Open to: Worldwide. Not open to: United Kingdom"
        )

    def test_blank_region_entry_is_rejected(self):
        opp = Opportunity(
            title="X",
            provider="Y",
            category="grant",
            description="d",
            official_url="https://example.com",
            eligible_regions=["Africa", " "],
        )
        with self.assertRaises(ValidationError) as ctx:
            opp.full_clean()
        self.assertIn("eligible_regions", ctx.exception.message_dict)


class AdminFormTests(TestCase):
    def form_data(self, **overrides):
        data = {
            "title": "Admin Test",
            "provider": "Acme",
            "category": "grant",
            "description": "d",
            "work_mode": "remote",
            "status": "draft",
            "official_url": "https://example.com/apply",
            "education_levels": ["graduate", "postgraduate"],
            "eligible_regions": "Africa, Nigeria",
            "excluded_regions": "",
        }
        data.update(overrides)
        return data

    def test_form_saves_lists(self):
        form = OpportunityAdminForm(data=self.form_data())
        self.assertTrue(form.is_valid(), form.errors)
        opp = form.save()
        self.assertEqual(opp.education_levels, ["graduate", "postgraduate"])
        self.assertEqual(opp.eligible_regions, ["Africa", "Nigeria"])
        self.assertEqual(opp.excluded_regions, [])

    def test_form_shows_existing_lists_as_text(self):
        opp = make_opportunity(eligible_regions=["Africa", "Nigeria"])
        form = OpportunityAdminForm(instance=opp)
        self.assertIn("Africa, Nigeria", str(form["eligible_regions"]))
