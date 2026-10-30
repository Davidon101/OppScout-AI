"""Regression checks of the matcher against the real seed data.

Dates are fixed so these never drift as deadlines pass. The relevance labels in
data/eval_profiles.json are the author's judgements: review and extend them.
"""
import unittest
from datetime import date

from ai_engine.evaluation import precision_at_k, recall_at_k, reciprocal_rank
from ai_engine.matching import rank_opportunities
from ai_engine.profile import Profile
from tests.fakes import eval_cases, opps_from_seed

TODAY = date(2026, 10, 28)


def run(profile):
    return rank_opportunities(Profile.from_mapping(profile), opps_from_seed(), today=TODAY)


class SeedEvaluationTests(unittest.TestCase):
    def test_best_result_is_relevant_for_every_profile(self):
        for case in eval_cases():
            ranked = [m.opportunity.slug for m in run(case["profile"]).matches]
            self.assertIn(ranked[0], case["relevant"], case["name"])

    def test_every_relevant_listing_is_in_the_top_five(self):
        for case in eval_cases():
            ranked = [m.opportunity.slug for m in run(case["profile"]).matches]
            self.assertEqual(recall_at_k(ranked, case["relevant"], 5), 1.0, case["name"])

    def test_precision_at_five_is_reasonable_where_labels_allow(self):
        for case in eval_cases():
            if len(case["relevant"]) < 4:
                continue  # precision@5 is capped by the number of labels
            ranked = [m.opportunity.slug for m in run(case["profile"]).matches]
            self.assertGreaterEqual(precision_at_k(ranked, case["relevant"], 5), 0.6, case["name"])

    def test_reciprocal_rank_is_one_for_every_profile(self):
        for case in eval_cases():
            ranked = [m.opportunity.slug for m in run(case["profile"]).matches]
            self.assertEqual(reciprocal_rank(ranked, case["relevant"]), 1.0, case["name"])

    def test_business_idea_profile_separates_the_right_listing(self):
        case = eval_cases()[2]
        matches = run(case["profile"]).matches
        self.assertEqual(matches[0].opportunity.slug, "tef-entrepreneurship-programme")
        self.assertGreater(matches[0].score, matches[1].score + 30)


class SeedRegionTests(unittest.TestCase):
    def test_nigerian_user_loses_nothing_to_region_filters(self):
        result = run({"country": "Nigeria"})
        self.assertEqual(result.hidden_region, 0)

    def test_french_user_is_hidden_from_africa_and_commonwealth_listings(self):
        result = run({"country": "France"})
        shown = {m.opportunity.slug for m in result.matches}
        self.assertNotIn("tef-entrepreneurship-programme", shown)
        self.assertNotIn("commonwealth-masters-scholarship-2027-28", shown)
        self.assertIn("gates-cambridge-scholarship-2027", shown)
        self.assertEqual(result.hidden_region, 2)

    def test_uk_resident_is_hidden_from_gates_cambridge(self):
        shown = {m.opportunity.slug for m in run({"country": "United Kingdom"}).matches}
        self.assertNotIn("gates-cambridge-scholarship-2027", shown)

    def test_russian_user_is_hidden_from_gsoc(self):
        shown = {m.opportunity.slug for m in run({"country": "Russia"}).matches}
        self.assertNotIn("google-summer-of-code", shown)


if __name__ == "__main__":
    unittest.main()
