from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from opportunities.models import Opportunity, OpportunityRequirement
from tests.test_opportunities import make_opportunity

PUBLISHED = Opportunity.Status.PUBLISHED


class DirectoryTests(TestCase):
    def setUp(self):
        self.alpha = make_opportunity(
            title="Alpha Scholarship",
            status=PUBLISHED,
            country="Nigeria",
            education_levels=["undergraduate"],
        )
        self.beta = make_opportunity(
            title="Beta Job",
            status=PUBLISHED,
            category=Opportunity.Category.JOB,
            work_mode=Opportunity.WorkMode.REMOTE,
        )
        self.gamma = make_opportunity(
            title="Gamma Grant",
            status=PUBLISHED,
            category=Opportunity.Category.GRANT,
            country="Kenya",
            education_levels=["postgraduate"],
        )
        self.draft = make_opportunity(title="Hidden Draft")
        self.url = reverse("opportunities:list")

    def titles(self, response):
        return [o.title for o in response.context["page"]]

    def test_only_published_listings_appear(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Hidden Draft", self.titles(response))
        self.assertEqual(len(self.titles(response)), 3)

    def test_category_filter(self):
        response = self.client.get(self.url, {"category": "job"})
        self.assertEqual(self.titles(response), ["Beta Job"])

    def test_country_filter_includes_listings_open_to_all(self):
        titles = self.titles(self.client.get(self.url, {"country": "Nigeria"}))
        self.assertIn("Alpha Scholarship", titles)
        self.assertIn("Beta Job", titles)
        self.assertNotIn("Gamma Grant", titles)

    def test_education_filter_includes_any_level(self):
        titles = self.titles(
            self.client.get(self.url, {"education_level": "undergraduate"})
        )
        self.assertIn("Alpha Scholarship", titles)
        self.assertIn("Beta Job", titles)
        self.assertNotIn("Gamma Grant", titles)

    def test_education_filter_matches_listings_with_several_levels(self):
        make_opportunity(
            title="Delta Fellowship",
            status=PUBLISHED,
            education_levels=["undergraduate", "graduate"],
        )
        for level in ("undergraduate", "graduate"):
            titles = self.titles(self.client.get(self.url, {"education_level": level}))
            self.assertIn("Delta Fellowship", titles, level)
        titles = self.titles(self.client.get(self.url, {"education_level": "postgraduate"}))
        self.assertNotIn("Delta Fellowship", titles)

    def test_work_mode_filter(self):
        titles = self.titles(self.client.get(self.url, {"work_mode": "remote"}))
        self.assertEqual(titles, ["Beta Job"])

    def test_search(self):
        titles = self.titles(self.client.get(self.url, {"q": "gamma"}))
        self.assertEqual(titles, ["Gamma Grant"])

    def test_closed_listings_hidden_unless_requested(self):
        make_opportunity(
            title="Old Fellowship",
            status=PUBLISHED,
            deadline=timezone.localdate() - timedelta(days=3),
        )
        self.assertNotIn("Old Fellowship", self.titles(self.client.get(self.url)))
        shown = self.client.get(self.url, {"include_closed": "1"})
        self.assertIn("Old Fellowship", self.titles(shown))

    def test_invalid_filter_values_are_ignored(self):
        response = self.client.get(self.url, {"category": "nonsense", "work_mode": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.titles(response)), 3)

    def test_htmx_request_returns_partial_only(self):
        response = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(response, "opportunities/partials/results.html")
        self.assertTemplateNotUsed(response, "opportunities/list.html")
        self.assertNotContains(response, "<html")

    def test_empty_state(self):
        response = self.client.get(self.url, {"q": "zzzz-no-match"})
        self.assertContains(response, "No opportunities match")


class DetailTests(TestCase):
    def test_published_detail_shows_requirements_and_official_link(self):
        opp = make_opportunity(status=PUBLISHED)
        OpportunityRequirement.objects.create(
            opportunity=opp,
            text="Be enrolled in a degree programme",
            requirement_type=OpportunityRequirement.RequirementType.MANDATORY,
        )
        response = self.client.get(reverse("opportunities:detail", args=[opp.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Be enrolled in a degree programme")
        self.assertContains(response, "https://example.com/apply")

    def test_draft_is_not_public(self):
        opp = make_opportunity()
        response = self.client.get(reverse("opportunities:detail", args=[opp.slug]))
        self.assertEqual(response.status_code, 404)

    def test_expired_listing_still_viewable_with_notice(self):
        opp = make_opportunity(status=Opportunity.Status.EXPIRED)
        response = self.client.get(reverse("opportunities:detail", args=[opp.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "appears to be closed")

    def test_archived_listing_is_hidden_everywhere(self):
        opp = make_opportunity(title="Retired Grant", status=Opportunity.Status.ARCHIVED)
        detail = self.client.get(reverse("opportunities:detail", args=[opp.slug]))
        self.assertEqual(detail.status_code, 404)
        listing = self.client.get(
            reverse("opportunities:list"), {"include_closed": "1"}
        )
        self.assertNotContains(listing, "Retired Grant")
