from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from opportunities.models import Opportunity


def load_seed():
    call_command("load_opportunities", stdout=StringIO())


class SeedDataTests(TestCase):
    def test_seed_loads_and_is_idempotent(self):
        load_seed()
        count = Opportunity.objects.count()
        self.assertGreater(count, 0)
        load_seed()
        self.assertEqual(Opportunity.objects.count(), count)

    def test_public_listings_are_verified_and_linked(self):
        load_seed()
        public = Opportunity.objects.filter(
            status__in=[Opportunity.Status.PUBLISHED, Opportunity.Status.EXPIRED]
        )
        self.assertTrue(public.exists())
        for opp in public:
            self.assertIsNotNone(opp.last_verified, opp.title)
            self.assertTrue(opp.official_url.startswith("https://"), opp.title)
            self.assertTrue(opp.requirements.exists(), opp.title)
