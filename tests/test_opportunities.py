from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from opportunities.models import Opportunity, OpportunityRequirement


def make_opportunity(**overrides):
    data = {
        "title": "Test Scholarship",
        "provider": "Acme Foundation",
        "category": Opportunity.Category.SCHOLARSHIP,
        "description": "A test listing.",
        "official_url": "https://example.com/apply",
    }
    data.update(overrides)
    return Opportunity.objects.create(**data)


class OpportunityModelTests(TestCase):
    def test_slug_is_generated_and_unique(self):
        first = make_opportunity()
        second = make_opportunity()
        self.assertEqual(first.slug, "test-scholarship")
        self.assertEqual(second.slug, "test-scholarship-2")

    def test_deadline_helpers(self):
        today = timezone.localdate()
        past = make_opportunity(title="Past", deadline=today - timedelta(days=1))
        future = make_opportunity(title="Future", deadline=today + timedelta(days=5))
        rolling = make_opportunity(title="Rolling")
        self.assertTrue(past.is_expired)
        self.assertFalse(future.is_expired)
        self.assertEqual(future.days_left, 5)
        self.assertFalse(rolling.is_expired)
        self.assertIsNone(rolling.days_left)

    def test_expired_status_overrides_deadline(self):
        opp = make_opportunity(status=Opportunity.Status.EXPIRED)
        self.assertTrue(opp.is_expired)

    def test_published_and_open_querysets(self):
        today = timezone.localdate()
        make_opportunity(title="Live", status=Opportunity.Status.PUBLISHED)
        make_opportunity(title="Draft")
        make_opportunity(
            title="Closed",
            status=Opportunity.Status.PUBLISHED,
            deadline=today - timedelta(days=1),
        )
        titles = set(Opportunity.objects.published().open().values_list("title", flat=True))
        self.assertEqual(titles, {"Live"})

    def test_requirement_defaults_to_unclear(self):
        opp = make_opportunity()
        req = OpportunityRequirement.objects.create(opportunity=opp, text="Be enrolled")
        self.assertEqual(req.requirement_type, OpportunityRequirement.RequirementType.UNCLEAR)


class PageTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get(reverse("opportunities:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Find What Fits")

    def test_healthz(self):
        response = self.client.get(reverse("opportunities:healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
