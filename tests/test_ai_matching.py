import unittest
from datetime import date, timedelta

from ai_engine import regions
from ai_engine.matching import (
    EXACT,
    SYNONYM,
    WORDS,
    rank_opportunities,
    term_score,
)
from ai_engine.profile import Profile
from tests.fakes import make_opp, make_requirement

TODAY = date(2026, 10, 28)


def rank(profile, opps, **kw):
    return rank_opportunities(Profile.from_mapping(profile), opps, today=TODAY, **kw)


def titles(result):
    return [m.opportunity.title for m in result.matches]


class TermScoreTests(unittest.TestCase):
    def test_exact_synonym_words_and_none(self):
        text = "internship in machine learning and python programming for students"
        self.assertEqual(term_score("python", text), EXACT)
        self.assertEqual(term_score("AI", text), SYNONYM)  # via machine learning
        self.assertEqual(term_score("student internship", text), WORDS)
        self.assertEqual(term_score("fishing", text), 0.0)

    def test_word_boundaries(self):
        self.assertEqual(term_score("java", "we use javascript daily"), 0.0)
        self.assertEqual(term_score("go", "go to the official page"), EXACT)  # a real word match
        self.assertEqual(term_score("ai", "maintain the chain"), 0.0)

    def test_plural_and_symbols(self):
        self.assertEqual(term_score("scholarship", "fully funded scholarships"), EXACT)
        self.assertEqual(term_score("c++", "experience with c++ and rust"), EXACT)

    def test_language_family_synonym(self):
        text = "applicants must be proficient in at least one programming language"
        self.assertEqual(term_score("Python", text), SYNONYM)

    def test_empty_and_tiny_terms(self):
        self.assertEqual(term_score("", "anything"), 0.0)
        self.assertEqual(term_score("a", "a b c"), 0.0)


class ScoringBehaviourTests(unittest.TestCase):
    def test_business_hours_is_not_entrepreneurship(self):
        text = "available during normal business hours"
        self.assertEqual(term_score("entrepreneurship", text), 0.0)
        self.assertEqual(term_score("startup", text), 0.0)

    def test_weak_hits_never_reach_full_score(self):
        opp = make_opp(pk=1, description="python and java and php")
        score = rank({"skills": "python, java, php"}, [opp]).matches[0].score
        self.assertLess(score, 100.0)
        self.assertGreater(score, 80.0)

    def test_strong_matches_beat_a_pile_of_weak_ones(self):
        strong = make_opp(pk=1, title="Strong", description="entrepreneurship programme for entrepreneurs")
        weak = make_opp(pk=2, title="Weak", description="a startup tools course")
        result = rank({"interests": "entrepreneurship"}, [weak, strong])
        self.assertEqual(titles(result), ["Strong", "Weak"])

    def test_goal_words_count_for_less_than_stated_interests(self):
        by_interest = make_opp(pk=1, title="I", description="robotics lab")
        by_goal = make_opp(pk=2, title="G", description="robotics lab")
        stated = rank({"interests": "robotics"}, [by_interest]).matches[0].score
        goal = rank({"career_goals": "robotics"}, [by_goal]).matches[0].score
        self.assertGreater(stated, goal)

    def test_generic_goal_wording_matches_nothing(self):
        opp = make_opp(pk=1, description="the start date is in march at our company")
        match = rank({"career_goals": "Start a company"}, [opp]).matches[0]
        self.assertEqual(match.score, 0.0)


class FilterTests(unittest.TestCase):
    def test_category_filter_hides_and_counts(self):
        opps = [
            make_opp(pk=1, title="Grant", category="grant"),
            make_opp(pk=2, title="Job", category="job"),
        ]
        result = rank({"categories": ["job"]}, opps)
        self.assertEqual(titles(result), ["Job"])
        self.assertEqual(result.hidden_category, 1)
        self.assertEqual(result.considered, 2)

    def test_no_category_selected_keeps_all(self):
        opps = [make_opp(pk=1, category="grant"), make_opp(pk=2, category="job")]
        self.assertEqual(len(rank({"country": "Nigeria"}, opps).matches), 2)

    def test_ineligible_region_is_hidden_and_counted(self):
        opps = [
            make_opp(pk=1, title="Africa only", eligible_regions=["Africa"]),
            make_opp(pk=2, title="UK excluded", excluded_regions=["United Kingdom"]),
        ]
        result = rank({"country": "France"}, opps)
        self.assertEqual(titles(result), ["UK excluded"])
        self.assertEqual(result.hidden_region, 1)

    def test_unknown_or_unstated_regions_are_kept(self):
        opps = [
            make_opp(pk=1, title="Not stated"),
            make_opp(pk=2, title="Odd region", eligible_regions=["Southeast Asia"]),
        ]
        self.assertEqual(len(rank({"country": "Nigeria"}, opps).matches), 2)

    def test_misspelled_country_hides_nothing(self):
        opps = [make_opp(pk=1, eligible_regions=["Africa"])]
        self.assertEqual(len(rank({"country": "Nigerai"}, opps).matches), 1)

    def test_no_country_hides_nothing(self):
        opps = [make_opp(pk=1, eligible_regions=["Africa"])]
        self.assertEqual(len(rank({"skills": "python"}, opps).matches), 1)

    def test_nigeria_sees_africa_and_commonwealth_listings(self):
        opps = [
            make_opp(pk=1, title="A", eligible_regions=["Africa"]),
            make_opp(pk=2, title="C", eligible_regions=["Commonwealth"]),
            make_opp(pk=3, title="Asia", eligible_regions=["India"]),
        ]
        result = rank({"country": "Nigeria"}, opps)
        self.assertEqual(sorted(titles(result)), ["A", "C"])


class RankingTests(unittest.TestCase):
    def test_matching_skills_rank_first(self):
        opps = [
            make_opp(pk=1, title="Gardening", description="plants and soil"),
            make_opp(
                pk=2,
                title="Python internship",
                description="Build software with python and machine learning",
                category="internship",
            ),
        ]
        result = rank({"skills": "Python", "interests": "machine learning"}, opps)
        self.assertEqual(titles(result)[0], "Python internship")
        self.assertGreater(result.matches[0].score, result.matches[1].score)
        self.assertTrue(
            any("python" in r.lower() for r in result.matches[0].reasons),
            result.matches[0].reasons,
        )

    def test_requirement_text_is_searched(self):
        opps = [
            make_opp(pk=1, title="Plain"),
            make_opp(
                pk=2,
                title="Reqs",
                requirements=[make_requirement("Experience with Python is an advantage")],
            ),
        ]
        self.assertEqual(titles(rank({"skills": "Python"}, opps))[0], "Reqs")

    def test_missing_user_info_is_not_a_penalty(self):
        # Only a country given: education and skills signals are absent, not zero.
        opp = make_opp(pk=1, education_levels=["graduate"], eligible_regions=["Worldwide"])
        score = rank({"country": "Nigeria"}, [opp]).matches[0].score
        self.assertEqual(score, 100.0)

    def test_education_mismatch_is_flagged_not_hidden(self):
        opp = make_opp(pk=1, education_levels=["graduate"])
        match = rank({"education_level": "undergraduate"}, [opp]).matches[0]
        self.assertEqual(match.score, 0.0)
        self.assertTrue(any("Bachelor's completed" in a for a in match.attention))

    def test_education_match_is_rewarded_and_explained(self):
        opp = make_opp(pk=1, education_levels=["undergraduate"])
        match = rank({"education_level": "undergraduate"}, [opp]).matches[0]
        self.assertEqual(match.score, 100.0)
        self.assertTrue(any("Accepts your education level" in r for r in match.reasons))

    def test_any_level_listing_gives_no_education_signal(self):
        opp = make_opp(pk=1)
        match = rank({"education_level": "undergraduate", "country": "Nigeria"}, [opp]).matches[0]
        self.assertFalse(any("education level" in r for r in match.reasons))

    def test_location_preference(self):
        remote = make_opp(pk=1, title="Remote", work_mode="remote")
        abroad = make_opp(pk=2, title="Abroad", country="Germany")
        local = make_opp(pk=3, title="Local", country="Nigeria")
        result = rank({"location_preferences": ["remote_global"]}, [remote, abroad, local])
        self.assertEqual(titles(result)[0], "Remote")
        result = rank({"location_preferences": ["nigeria"]}, [remote, abroad, local])
        self.assertEqual(titles(result)[0], "Local")
        result = rank({"location_preferences": ["africa"]}, [remote, abroad, local])
        self.assertEqual(titles(result)[0], "Local")

    def test_listing_with_no_stated_location_is_neutral(self):
        opp = make_opp(pk=1)  # physical, no country
        match = rank({"location_preferences": ["nigeria"]}, [opp]).matches[0]
        self.assertFalse(any("location" in r for r in match.reasons))

    def test_embedding_similarity_overrides_ordering(self):
        a = make_opp(pk=1, title="A")
        b = make_opp(pk=2, title="B")
        result = rank({"country": "Nigeria"}, [a, b], similarities={1: 0.1, 2: 0.9})
        self.assertEqual(titles(result), ["B", "A"])
        self.assertTrue(any("similar" in r for r in result.matches[0].reasons))

    def test_similarity_is_clamped(self):
        a = make_opp(pk=1)
        result = rank({"country": "Nigeria"}, [a], similarities={1: 7.0})
        self.assertLessEqual(result.matches[0].score, 100.0)

    def test_ties_break_by_deadline_then_title(self):
        soon = make_opp(pk=1, title="Zed", deadline=TODAY + timedelta(days=5))
        later = make_opp(pk=2, title="Alpha", deadline=TODAY + timedelta(days=50))
        none = make_opp(pk=3, title="Beta")
        self.assertEqual(titles(rank({"country": "Nigeria"}, [none, later, soon])), ["Zed", "Alpha", "Beta"])

    def test_empty_profile_does_not_crash(self):
        result = rank({}, [make_opp(pk=1)])
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.matches[0].score, 0.0)

    def test_no_opportunities(self):
        result = rank({"country": "Nigeria"}, [])
        self.assertEqual(result.matches, [])
        self.assertEqual(result.considered, 0)


class ExplanationTests(unittest.TestCase):
    def test_fallback_reason_when_nothing_specific_matched(self):
        match = rank({"country": ""}, [make_opp(pk=1)]).matches[0]
        self.assertEqual(len(match.reasons), 1)
        self.assertIn("nothing in its published details rules you out", match.reasons[0])

    def test_region_reasons(self):
        worldwide = make_opp(pk=1, eligible_regions=["Worldwide"])
        africa = make_opp(pk=2, eligible_regions=["Africa"])
        result = rank({"country": "Nigeria"}, [worldwide, africa])
        by_pk = {m.opportunity.pk: m for m in result.matches}
        self.assertIn("worldwide", by_pk[1].reasons[0].lower())
        self.assertIn("Nigeria", by_pk[2].reasons[0])
        self.assertEqual(by_pk[1].region_status, regions.ELIGIBLE)

    def test_unstated_regions_flagged_when_country_given(self):
        match = rank({"country": "Nigeria"}, [make_opp(pk=1)]).matches[0]
        self.assertTrue(any("does not state who can apply" in a for a in match.attention))
        silent = rank({"skills": "python"}, [make_opp(pk=1)]).matches[0]
        self.assertFalse(any("who can apply" in a for a in silent.attention))

    def test_deadline_attention(self):
        soon = make_opp(pk=1, deadline=TODAY + timedelta(days=3))
        today = make_opp(pk=2, deadline=TODAY)
        past = make_opp(pk=3, deadline=TODAY - timedelta(days=1))
        far = make_opp(pk=4, deadline=TODAY + timedelta(days=90))
        by_pk = {m.opportunity.pk: m for m in rank({}, [soon, today, past, far]).matches}
        self.assertIn("Closes in 3 days.", by_pk[1].attention)
        self.assertIn("Closes today.", by_pk[2].attention)
        self.assertIn("The deadline has passed.", by_pk[3].attention)
        self.assertFalse(any("Closes" in a for a in by_pk[4].attention))

    def test_verification_attention(self):
        fresh = make_opp(pk=1, last_verified=TODAY - timedelta(days=5))
        stale = make_opp(pk=2, last_verified=TODAY - timedelta(days=120))
        never = make_opp(pk=3, last_verified=None)
        by_pk = {m.opportunity.pk: m for m in rank({}, [fresh, stale, never]).matches}
        self.assertFalse(by_pk[1].attention)
        self.assertTrue(any("Last verified" in a for a in by_pk[2].attention))
        self.assertTrue(any("not been verified" in a for a in by_pk[3].attention))

    def test_requirement_counts(self):
        opp = make_opp(
            pk=1,
            requirements=[
                make_requirement("a", "mandatory"),
                make_requirement("b", "mandatory"),
                make_requirement("c", "preferred"),
                make_requirement("d", "unclear"),
            ],
        )
        match = rank({}, [opp]).matches[0]
        self.assertEqual((match.mandatory_count, match.unclear_count), (2, 1))


if __name__ == "__main__":
    unittest.main()
