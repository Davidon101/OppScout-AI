from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from ai_engine.providers import FakeProvider, ProviderBusy, ProviderUnavailable
from opportunities.models import AIUsage, Opportunity, OpportunityRequirement
from tests.test_opportunities import make_opportunity

PUBLISHED = Opportunity.Status.PUBLISHED
PROFILE = {"country": "Nigeria", "skills": "Python", "interests": "PRIVATE-INTEREST"}


class GapViewTests(TestCase):
    def setUp(self):
        self.opp = make_opportunity(title="Dev Fellowship", status=PUBLISHED, eligible_regions=["Africa"])
        self.r1 = OpportunityRequirement.objects.create(opportunity=self.opp, text="Ship a team project", requirement_type="mandatory")
        self.url = reverse("opportunities:gaps", args=[self.opp.slug])

    def post(self, data=None, provider=None):
        provider = provider or FakeProvider(result={"gaps": [
            {"requirement_id": self.r1.pk, "gap": "No team project shown.", "action": "Join an open-source project."}],
            "summary": "One thing to do."})
        with patch("opportunities.views.get_provider", return_value=provider):
            return self.client.post(self.url, PROFILE if data is None else data, HTTP_HX_REQUEST="true"), provider

    def test_detail_page_has_both_forms_and_save_button(self):
        r = self.client.get(reverse("opportunities:detail", args=[self.opp.slug]))
        self.assertContains(r, 'id="gap-form"')
        self.assertContains(r, 'data-save="%s"' % self.opp.slug)

    def test_gap_result(self):
        r, provider = self.post()
        self.assertContains(r, "Ship a team project")
        self.assertContains(r, "Join an open-source project.")
        self.assertContains(r, "does not guarantee selection")
        self.assertNotContains(r, "<html")
        self.assertIn("no-store", r["Cache-Control"])
        self.assertNotIn("PRIVATE-INTEREST", provider.calls[0][1])

    def test_no_gaps_message(self):
        r, _ = self.post(provider=FakeProvider(result={"gaps": [], "summary": ""}))
        self.assertContains(r, "No clear gaps were found")

    def test_model_text_is_escaped(self):
        r, _ = self.post(provider=FakeProvider(result={"gaps": [
            {"requirement_id": self.r1.pk, "gap": "<script>x</script>", "action": "<b>y</b>"}]}))
        self.assertNotContains(r, "<script>x</script>")
        self.assertNotContains(r, "<b>y</b>")

    def test_empty_profile_and_region_exclusion_make_no_ai_call(self):
        r, provider = self.post(data={})
        self.assertContains(r, "Add your details")
        r, provider = self.post(data={"country": "France"})
        self.assertContains(r, "do not include your country")
        self.assertEqual(provider.calls, [])
        self.assertEqual(AIUsage.objects.count(), 0)

    def test_education_rule_check_is_shown(self):
        self.opp.education_levels = ["graduate"]
        self.opp.save()
        r, _ = self.post(data={"country": "Nigeria", "education_level": "undergraduate"})
        self.assertContains(r, "It asks for: Bachelor")

    def test_no_requirements(self):
        self.opp.requirements.all().delete()
        r, provider = self.post()
        self.assertContains(r, "No requirements are recorded")
        self.assertEqual(provider.calls, [])

    def test_unavailable_busy_and_capped(self):
        with patch("opportunities.views.get_provider", side_effect=ProviderUnavailable()):
            self.assertContains(self.client.post(self.url, PROFILE, HTTP_HX_REQUEST="true"), "not available right now")
        r, _ = self.post(provider=FakeProvider(error=ProviderBusy()))
        self.assertContains(r, "busy")
        with override_settings(AI_VISITOR_HOURLY_CAP=0):
            r, provider = self.post()
        self.assertContains(r, "this hour")
        self.assertEqual(provider.calls, [])

    def test_shares_the_cap_with_eligibility(self):
        with override_settings(AI_VISITOR_HOURLY_CAP=1):
            self.post()
            with patch("opportunities.views.get_provider", return_value=FakeProvider(result={})):
                r = self.client.post(reverse("opportunities:check", args=[self.opp.slug]), PROFILE, HTTP_HX_REQUEST="true")
        self.assertContains(r, "this hour")

    def test_method_csrf_and_404(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        from django.test import Client
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.url, PROFILE).status_code, 403)
        draft = make_opportunity(title="Hidden")
        self.assertEqual(self.client.post(reverse("opportunities:gaps", args=[draft.slug]), PROFILE).status_code, 404)

    def test_non_htmx_full_page(self):
        with patch("opportunities.views.get_provider", return_value=FakeProvider(result={"gaps": [], "summary": ""})):
            r = self.client.post(self.url, PROFILE)
        self.assertTemplateUsed(r, "gaps/result.html")


class SavedViewTests(TestCase):
    def setUp(self):
        self.a = make_opportunity(title="Alpha Grant", status=PUBLISHED)
        self.b = make_opportunity(title="Beta Grant", status=PUBLISHED)
        self.url = reverse("opportunities:saved_list")

    def post(self, slugs):
        return self.client.post(self.url, {"slugs": slugs}, HTTP_HX_REQUEST="true")

    def test_page_and_nav(self):
        r = self.client.get(reverse("opportunities:saved"))
        self.assertContains(r, "Saved opportunities")
        self.assertContains(r, 'id="saved-form"')
        self.assertContains(self.client.get(reverse("opportunities:home")), ">Saved</a>")

    def test_cards_come_back_in_saved_order(self):
        r = self.post(f"{self.b.slug},{self.a.slug}")
        c = r.content.decode()
        self.assertLess(c.index("Beta Grant"), c.index("Alpha Grant"))
        self.assertIn("no-store", r["Cache-Control"])
        self.assertContains(r, "2 saved")

    def test_drafts_unknown_and_bad_slugs_are_ignored_safely(self):
        draft = make_opportunity(title="Draft One")
        r = self.post(f"{self.a.slug},{draft.slug},nope,<script>,../x")
        self.assertContains(r, "Alpha Grant")
        self.assertNotContains(r, "Draft One")
        self.assertNotContains(r, "<script>")

    def test_empty_and_duplicates(self):
        self.assertContains(self.post(""), "have not saved anything yet")
        r = self.post(f"{self.a.slug},{self.a.slug}")
        self.assertContains(r, "1 saved")

    def test_unavailable_listing_is_counted(self):
        r = self.post(f"{self.a.slug},gone-listing")
        self.assertContains(r, "1 saved listing no longer available")

    def test_cap_and_methods(self):
        slugs = ",".join(f"s{i}" for i in range(500))
        self.assertEqual(self.post(slugs).status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_nothing_is_stored(self):
        before = (Opportunity.objects.count(), AIUsage.objects.count())
        self.post(self.a.slug)
        self.assertEqual(before, (Opportunity.objects.count(), AIUsage.objects.count()))
