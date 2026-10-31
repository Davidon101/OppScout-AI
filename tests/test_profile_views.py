from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ai_engine.profile import EDUCATION_LABELS
from opportunities.models import Opportunity
from tests.test_opportunities import make_opportunity

PUBLISHED = Opportunity.Status.PUBLISHED


class ProfilePageTests(TestCase):
    def test_profile_page_loads_with_form_and_country_suggestions(self):
        response = self.client.get(reverse("opportunities:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Find my opportunities")
        self.assertContains(response, 'list="country-options"')
        self.assertContains(response, '<option value="Nigeria">')
        self.assertContains(response, "Clear saved profile")

    def test_profile_page_does_not_leak_anything_server_side(self):
        response = self.client.get(reverse("opportunities:profile"))
        self.assertNotContains(response, "oppscout.profile")  # storage key lives in app.js only

    def test_education_labels_match_the_model(self):
        self.assertEqual(
            EDUCATION_LABELS, dict(Opportunity.EducationLevel.choices)
        )


class MatchResultsTests(TestCase):
    def setUp(self):
        self.url = reverse("opportunities:matches")
        self.python_job = make_opportunity(
            title="Python Internship",
            category=Opportunity.Category.INTERNSHIP,
            description="Build software with python and machine learning.",
            status=PUBLISHED,
            eligible_regions=["Africa"],
        )

    def post(self, data, **extra):
        return self.client.post(self.url, data, **extra)

    def test_returns_ranked_results_with_reasons(self):
        response = self.post({"country": "Nigeria", "skills": "Python"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Python Internship")
        self.assertContains(response, "Why it matched")
        self.assertContains(response, "Mentions your skills: Python")
        self.assertContains(response, "not an eligibility decision")
        self.assertTemplateUsed(response, "matching/results.html")

    def test_htmx_request_returns_only_the_partial(self):
        response = self.post({"country": "Nigeria"}, HTTP_HX_REQUEST="true")
        self.assertTemplateUsed(response, "matching/partials/match_list.html")
        self.assertTemplateNotUsed(response, "matching/results.html")
        self.assertNotContains(response, "<html")

    def test_response_is_not_cached(self):
        response = self.post({"country": "Nigeria"})
        self.assertIn("no-store", response["Cache-Control"])

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_empty_profile_is_rejected_with_a_message(self):
        response = self.post({})
        self.assertContains(response, "Add at least one detail")
        self.assertNotContains(response, "Python Internship")

    def test_overlong_field_is_rejected(self):
        response = self.post({"country": "N" * 101})
        self.assertContains(response, "at most 100 characters")

    def test_invalid_choice_is_rejected(self):
        response = self.post({"country": "Nigeria", "education_level": "wizard"})
        self.assertContains(response, "Education level")
        self.assertNotContains(response, "Python Internship")

    def test_region_that_excludes_the_country_is_hidden_and_counted(self):
        response = self.post({"country": "France"})
        self.assertNotContains(response, "Python Internship")
        self.assertContains(response, "1 listing hidden because the stated eligible regions")

    def test_unknown_country_hides_nothing(self):
        response = self.post({"country": "Nigerai"})
        self.assertContains(response, "Python Internship")

    def test_category_filter_hides_other_types(self):
        make_opportunity(title="A Grant", category=Opportunity.Category.GRANT, status=PUBLISHED)
        response = self.post({"country": "Nigeria", "categories": ["grant"]})
        self.assertContains(response, "A Grant")
        self.assertNotContains(response, "Python Internship")
        self.assertContains(response, "outside your chosen types")

    def test_drafts_closed_and_expired_listings_never_appear(self):
        make_opportunity(title="Draft Listing")
        make_opportunity(
            title="Closed Listing",
            status=PUBLISHED,
            deadline=timezone.localdate() - timedelta(days=1),
        )
        make_opportunity(title="Expired Listing", status=Opportunity.Status.EXPIRED)
        make_opportunity(title="Archived Listing", status=Opportunity.Status.ARCHIVED)
        response = self.post({"country": "Nigeria"})
        for title in ("Draft Listing", "Closed Listing", "Expired Listing", "Archived Listing"):
            self.assertNotContains(response, title)

    def test_no_open_listings_shows_a_sensible_empty_state(self):
        Opportunity.objects.all().delete()
        response = self.post({"country": "Nigeria"})
        self.assertContains(response, "No open listings match")

    def test_missing_country_shows_a_hint(self):
        response = self.post({"skills": "Python"})
        self.assertContains(response, "Add your country")

    def test_attention_notes_are_shown(self):
        make_opportunity(
            title="Soon Closing",
            status=PUBLISHED,
            deadline=timezone.localdate() + timedelta(days=3),
        )
        response = self.post({"country": "Nigeria"})
        self.assertContains(response, "Check before applying")
        self.assertContains(response, "Closes in 3 days.")

    def test_profile_details_are_not_echoed_unescaped(self):
        response = self.post({"country": "Nigeria", "skills": "<script>alert(1)</script>"})
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_csrf_is_enforced_for_real_browsers(self):
        from django.test import Client

        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(self.url, {"country": "Nigeria"}).status_code, 403)

    def test_many_listings_do_not_cause_per_listing_queries(self):
        for i in range(15):
            make_opportunity(title=f"Listing {i}", status=PUBLISHED)
        with self.assertNumQueries(2):  # listings + prefetched requirements
            self.post({"country": "Nigeria"})


class AccountPageTests(TestCase):
    def test_login_and_register_collect_nothing_and_point_to_guest_use(self):
        for name in ("login", "register"):
            response = self.client.get(reverse(f"opportunities:{name}"))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Continue as guest")
            self.assertNotContains(response, "<form")
            self.assertNotContains(response, 'name="password"')
            self.assertNotContains(response, "demo")


class HomePageTests(TestCase):
    def test_home_has_search_categories_and_how_it_works(self):
        response = self.client.get(reverse("opportunities:home"))
        self.assertContains(response, 'role="search"')
        self.assertContains(response, "?category=scholarship")
        self.assertContains(response, "How it works")
        self.assertNotContains(response, "demo")

    def test_featured_shows_open_published_listings_soonest_first(self):
        today = timezone.localdate()
        make_opportunity(title="Later One", status=PUBLISHED, deadline=today + timedelta(days=60))
        make_opportunity(title="Sooner One", status=PUBLISHED, deadline=today + timedelta(days=5))
        make_opportunity(title="Closed One", status=PUBLISHED, deadline=today - timedelta(days=1))
        make_opportunity(title="Draft One")
        response = self.client.get(reverse("opportunities:home"))
        content = response.content.decode()
        self.assertLess(content.index("Sooner One"), content.index("Later One"))
        self.assertNotIn("Closed One", content)
        self.assertNotIn("Draft One", content)


class ErrorPageTests(TestCase):
    def test_404_uses_the_site_template(self):
        with self.settings(DEBUG=False):
            response = self.client.get("/definitely-not-here/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)
        self.assertContains(response, "Browse opportunities", status_code=404)

    def test_unpublished_listing_is_a_404(self):
        draft = make_opportunity(title="Secret Draft")
        response = self.client.get(reverse("opportunities:detail", args=[draft.slug]))
        self.assertEqual(response.status_code, 404)
