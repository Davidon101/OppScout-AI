from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ai_engine.providers import FakeProvider, ProviderBadResponse, ProviderBusy, ProviderUnavailable
from opportunities import limits
from opportunities.models import AIUsage, Opportunity, OpportunityRequirement
from tests.test_opportunities import make_opportunity

PUBLISHED = Opportunity.Status.PUBLISHED
PROFILE = {"country": "Nigeria", "education_level": "undergraduate",
           "skills": "Python", "interests": "PRIVATE-INTEREST"}


def provider_for(opp, statuses):
    reqs = list(opp.requirements.all())
    return FakeProvider(result={
        "criteria": [
            {"requirement_id": r.pk, "status": s, "evidence": "Skills: Python", "note": ""}
            for r, s in zip(reqs, statuses)
        ],
        "summary": "Looks fine.",
    })


class EligibilityViewTests(TestCase):
    def setUp(self):
        self.opp = make_opportunity(title="Dev Fellowship", status=PUBLISHED,
                                    eligible_regions=["Africa"])
        self.r1 = OpportunityRequirement.objects.create(
            opportunity=self.opp, text="Know Python", requirement_type="mandatory")
        self.r2 = OpportunityRequirement.objects.create(
            opportunity=self.opp, text="Know Django", requirement_type="preferred")
        self.url = reverse("opportunities:check", args=[self.opp.slug])

    def post(self, data=None, provider=None, **extra):
        provider = provider or provider_for(self.opp, ["met", "unclear"])
        with patch("opportunities.views.get_provider", return_value=provider):
            response = self.client.post(self.url, PROFILE if data is None else data,
                                        HTTP_HX_REQUEST="true", **extra)
        return response, provider

    def test_detail_page_has_the_check_form(self):
        response = self.client.get(reverse("opportunities:detail", args=[self.opp.slug]))
        self.assertContains(response, "Check my eligibility")
        self.assertContains(response, 'id="eligibility-form"')

    def test_successful_check(self):
        response, provider = self.post()
        self.assertContains(response, "Appears to meet the stated requirements")
        self.assertContains(response, "Know Python")
        self.assertContains(response, "Looks met")
        self.assertContains(response, "not an official decision")
        self.assertNotContains(response, "<html")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(len(provider.calls), 1)

    def test_only_needed_fields_reach_the_provider(self):
        _, provider = self.post()
        user = provider.calls[0][1]
        self.assertIn("Python", user)
        self.assertNotIn("PRIVATE-INTEREST", user)

    def test_profile_is_not_stored_anywhere(self):
        self.post()
        self.assertNotIn("Nigeria", "".join(AIUsage.objects.values_list("key", flat=True)))
        self.assertNotIn("127.0.0.1", "".join(AIUsage.objects.values_list("key", flat=True)))

    def test_mandatory_not_met(self):
        response, _ = self.post(provider=provider_for(self.opp, ["not_met", "met"]))
        self.assertContains(response, "Does not appear to meet a mandatory requirement")

    def test_empty_profile_makes_no_ai_call(self):
        response, provider = self.post(data={})
        self.assertContains(response, "Add your details on the profile page first")
        self.assertEqual(provider.calls, [])

    def test_region_exclusion_is_decided_without_ai(self):
        response, provider = self.post(data={"country": "France"})
        self.assertContains(response, "do not include France")
        self.assertEqual(provider.calls, [])
        self.assertEqual(AIUsage.objects.count(), 0)

    def test_no_requirements_makes_no_ai_call(self):
        self.opp.requirements.all().delete()
        response, provider = self.post()
        self.assertContains(response, "No requirements are recorded")
        self.assertEqual(provider.calls, [])

    def test_missing_api_key_degrades_politely(self):
        with patch("opportunities.views.get_provider", side_effect=ProviderUnavailable()):
            response = self.client.post(self.url, PROFILE, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI checks are not available right now")

    def test_unconfigured_site_has_no_key(self):
        with override_settings(GEMINI_API_KEY=""):
            response = self.client.post(self.url, PROFILE, HTTP_HX_REQUEST="true")
        self.assertContains(response, "AI checks are not available right now")

    def test_provider_errors_show_a_safe_message(self):
        for error, text in ((ProviderBusy(), "busy"), (ProviderBadResponse("raw detail"), "could not use")):
            response, _ = self.post(provider=FakeProvider(error=error))
            self.assertContains(response, text)
            self.assertNotContains(response, "raw detail")

    def test_garbage_model_output_yields_unclear_not_a_verdict(self):
        response, _ = self.post(provider=FakeProvider(result={"criteria": [{"requirement_id": 999, "status": "met", "evidence": "x"}]}))
        self.assertContains(response, "Cannot tell from what you shared")

    def test_model_text_is_escaped(self):
        provider = FakeProvider(result={"criteria": [
            {"requirement_id": self.r1.pk, "status": "met", "evidence": "<script>x</script>", "note": ""}],
            "summary": "<b>hi</b>"})
        response, _ = self.post(provider=provider)
        self.assertNotContains(response, "<script>x</script>")
        self.assertNotContains(response, "<b>hi</b>")

    def test_get_not_allowed_and_csrf_enforced(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        from django.test import Client
        self.assertEqual(Client(enforce_csrf_checks=True).post(self.url, PROFILE).status_code, 403)

    def test_drafts_and_unknown_slugs_404(self):
        draft = make_opportunity(title="Hidden")
        self.assertEqual(self.client.post(reverse("opportunities:check", args=[draft.slug]), PROFILE).status_code, 404)

    def test_non_htmx_gets_a_full_page(self):
        with patch("opportunities.views.get_provider", return_value=provider_for(self.opp, ["met", "met"])):
            response = self.client.post(self.url, PROFILE)
        self.assertTemplateUsed(response, "eligibility/result.html")
        self.assertContains(response, "<html")

    def test_invalid_profile_values(self):
        response, provider = self.post(data={"country": "N" * 101})
        self.assertContains(response, "not valid")
        self.assertEqual(provider.calls, [])


@override_settings(AI_VISITOR_HOURLY_CAP=2, AI_MINUTE_CAP=50, AI_DAILY_CAP=50)
class LimitTests(TestCase):
    def setUp(self):
        self.opp = make_opportunity(status=PUBLISHED, eligible_regions=["Africa"])
        OpportunityRequirement.objects.create(opportunity=self.opp, text="Know Python",
                                              requirement_type="mandatory")
        self.url = reverse("opportunities:check", args=[self.opp.slug])

    def call(self, ip="1.1.1.1"):
        provider = provider_for(self.opp, ["met"])
        with patch("opportunities.views.get_provider", return_value=provider):
            return self.client.post(self.url, PROFILE, HTTP_HX_REQUEST="true",
                                    REMOTE_ADDR=ip), provider

    def test_visitor_cap_blocks_then_other_visitors_still_work(self):
        self.call(); self.call()
        response, provider = self.call()
        self.assertContains(response, "used your AI checks for this hour")
        self.assertEqual(provider.calls, [])
        response, _ = self.call(ip="2.2.2.2")
        self.assertContains(response, "Appears to meet")

    def test_refused_requests_are_not_counted(self):
        self.call(); self.call(); self.call(); self.call()
        self.assertEqual(AIUsage.objects.get(key__startswith="d:").count, 2)

    @override_settings(AI_DAILY_CAP=1)
    def test_daily_cap_protects_the_provider_quota(self):
        self.call(ip="1.1.1.1")
        response, provider = self.call(ip="3.3.3.3")
        self.assertContains(response, "reached today")
        self.assertEqual(provider.calls, [])

    @override_settings(AI_MINUTE_CAP=1)
    def test_minute_cap(self):
        self.call(ip="1.1.1.1")
        response, _ = self.call(ip="4.4.4.4")
        self.assertContains(response, "try again in a minute")

    def test_directory_and_matching_work_when_ai_is_capped(self):
        self.call(); self.call(); self.call()
        self.assertEqual(self.client.get(reverse("opportunities:list")).status_code, 200)
        self.assertEqual(self.client.post(reverse("opportunities:matches"), {"country": "Nigeria"}).status_code, 200)

    def test_ip_is_hashed_and_old_rows_purged(self):
        self.call()
        keys = list(AIUsage.objects.values_list("key", flat=True))
        self.assertTrue(all("1.1.1.1" not in k for k in keys))
        AIUsage.objects.update(created=timezone.now() - timedelta(days=3))
        self.call(ip="9.9.9.9")
        self.assertFalse(AIUsage.objects.filter(key__startswith="v:").exclude(key__contains=limits._visitor_token("9.9.9.9")).exists())

    def test_forwarded_header_uses_last_entry(self):
        class R:
            META = {"HTTP_X_FORWARDED_FOR": "6.6.6.6, 7.7.7.7", "REMOTE_ADDR": "10.0.0.1"}
        self.assertEqual(limits.client_ip(R), "7.7.7.7")
