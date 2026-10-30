import unittest

from ai_engine import regions
from ai_engine.regions import ELIGIBLE, INELIGIBLE, UNKNOWN, region_status


class CanonicalTests(unittest.TestCase):
    def test_aliases_and_accents(self):
        self.assertEqual(regions.canonical("UK"), "united kingdom")
        self.assertEqual(regions.canonical("U.K."), "united kingdom")
        self.assertEqual(regions.canonical("Côte d'Ivoire"), "cote d'ivoire")
        self.assertEqual(regions.canonical("Cote d’Ivoire"), "cote d'ivoire")
        self.assertEqual(regions.canonical("Ivory Coast"), "cote d'ivoire")
        self.assertEqual(regions.canonical("  nigeria "), "nigeria")
        self.assertEqual(regions.canonical("Global"), "worldwide")
        self.assertEqual(regions.canonical(None), "")

    def test_group_sizes(self):
        self.assertEqual(len(regions.AFRICA_SET), 54)
        self.assertEqual(len(regions.COMMONWEALTH_SET), 56)

    def test_nigeria_groups(self):
        self.assertEqual(regions.groups_for("Nigeria"), {"africa", "commonwealth"})
        self.assertEqual(regions.groups_for("Egypt"), {"africa"})
        self.assertEqual(regions.groups_for("India"), {"commonwealth"})
        self.assertEqual(regions.groups_for("France"), frozenset())

    def test_in_group(self):
        self.assertTrue(regions.in_group("Ghana", "Africa"))
        self.assertFalse(regions.in_group("India", "Africa"))

    def test_country_names_are_all_known(self):
        for name in regions.COUNTRY_NAMES:
            self.assertTrue(regions.is_known_country(name), name)


class RegionStatusTests(unittest.TestCase):
    def test_worldwide_is_eligible(self):
        self.assertEqual(region_status(["Worldwide"], [], "Nigeria"), ELIGIBLE)

    def test_group_membership(self):
        self.assertEqual(region_status(["Africa"], [], "Nigeria"), ELIGIBLE)
        self.assertEqual(region_status(["Commonwealth"], [], "Nigeria"), ELIGIBLE)
        self.assertEqual(region_status(["Africa"], [], "France"), INELIGIBLE)
        self.assertEqual(region_status(["Commonwealth"], [], "France"), INELIGIBLE)

    def test_exact_country(self):
        self.assertEqual(region_status(["Nigeria"], [], "nigeria"), ELIGIBLE)
        self.assertEqual(region_status(["Kenya"], [], "Nigeria"), INELIGIBLE)

    def test_exclusions_win(self):
        self.assertEqual(
            region_status(["Worldwide"], ["United Kingdom"], "UK"), INELIGIBLE
        )
        self.assertEqual(
            region_status(["Worldwide"], ["United Kingdom"], "Nigeria"), ELIGIBLE
        )
        self.assertEqual(region_status([], ["Russia", "Belarus"], "Russia"), INELIGIBLE)
        self.assertEqual(region_status([], ["Commonwealth"], "Nigeria"), INELIGIBLE)

    def test_not_stated_is_unknown_never_ineligible(self):
        self.assertEqual(region_status([], [], "Nigeria"), UNKNOWN)
        self.assertEqual(region_status(None, None, "Nigeria"), UNKNOWN)

    def test_missing_country_is_unknown(self):
        self.assertEqual(region_status(["Africa"], ["United Kingdom"], ""), UNKNOWN)

    def test_misspelled_country_is_never_disqualified(self):
        self.assertEqual(region_status(["Africa"], [], "Nigerai"), UNKNOWN)

    def test_unresolvable_region_is_unknown(self):
        self.assertEqual(region_status(["Southeast Asia"], [], "Nigeria"), UNKNOWN)

    def test_known_region_mixed_with_unresolvable_stays_unknown(self):
        self.assertEqual(region_status(["Kenya", "Southeast Asia"], [], "Nigeria"), UNKNOWN)


if __name__ == "__main__":
    unittest.main()
