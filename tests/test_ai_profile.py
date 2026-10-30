import unittest

from ai_engine.embeddings import cosine_similarity, similarities_for
from ai_engine.evaluation import precision_at_k, recall_at_k
from ai_engine.profile import (
    EDUCATION_LABELS,
    Profile,
    keywords,
    split_list,
)
from tests.fakes import make_opp


class SplitListTests(unittest.TestCase):
    def test_splits_and_dedupes_case_insensitively(self):
        self.assertEqual(
            split_list("Python, python ; HTML\nCSS,, "), ("Python", "HTML", "CSS")
        )

    def test_caps_count_and_length(self):
        many = ",".join(f"skill{i}" for i in range(50))
        self.assertEqual(len(split_list(many, limit=20)), 20)
        self.assertEqual(len(split_list("x" * 500, item_max=60)[0]), 60)

    def test_accepts_lists_none_and_junk(self):
        self.assertEqual(split_list(None), ())
        self.assertEqual(split_list(["a", " b ", 3]), ("a", "b", "3"))


class KeywordTests(unittest.TestCase):
    def test_drops_stopwords_and_short_words(self):
        self.assertEqual(keywords("I want to become an AI engineer"), ("engineer",))
        self.assertEqual(keywords("Start a technology company"), ("technology",))
        self.assertIn("python", keywords("Build Python apps"))


class ProfileTests(unittest.TestCase):
    def test_empty(self):
        self.assertTrue(Profile.from_mapping({}).is_empty())
        self.assertTrue(Profile.from_mapping(None).is_empty())

    def test_invalid_values_are_dropped_not_trusted(self):
        p = Profile.from_mapping(
            {
                "education_level": "wizard",
                "categories": ["job", "nonsense"],
                "location_preferences": ["africa", "mars"],
            }
        )
        self.assertEqual(p.education_level, "")
        self.assertEqual(p.categories, ("job",))
        self.assertEqual(p.location_preferences, ("africa",))
        self.assertFalse(p.is_empty())

    def test_text_fields_are_trimmed(self):
        p = Profile.from_mapping({"country": "N" * 500, "career_goals": "g" * 900})
        self.assertEqual(len(p.country), 100)
        self.assertEqual(len(p.career_goals), 300)

    def test_stated_terms_and_goal_terms_are_kept_apart(self):
        p = Profile.from_mapping(
            {
                "interests": "AI engineering",
                "field_of_study": "Computer Science",
                "career_goals": "Become a data engineer",
            }
        )
        stated = [t.lower() for t in p.interest_terms]
        self.assertEqual(stated, ["ai engineering", "computer science"])
        self.assertEqual(p.goal_terms, ("data", "engineer"))

    def test_goal_terms_skip_words_already_stated(self):
        p = Profile.from_mapping({"interests": "data", "career_goals": "data engineer"})
        self.assertEqual(p.goal_terms, ("engineer",))

    def test_as_text(self):
        p = Profile.from_mapping(
            {"education_level": "undergraduate", "skills": "Python", "interests": "AI"}
        )
        self.assertIn("Skills: Python", p.as_text())
        self.assertIn("Interests: AI", p.as_text())


class EmbeddingTests(unittest.TestCase):
    def test_cosine(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0)
        self.assertAlmostEqual(cosine_similarity([1, 0], [-1, 0]), -1.0)

    def test_zero_vector_and_length_mismatch(self):
        self.assertEqual(cosine_similarity([0, 0], [1, 1]), 0.0)
        with self.assertRaises(ValueError):
            cosine_similarity([1], [1, 2])

    def test_similarities_skip_listings_without_embeddings(self):
        a = make_opp(pk=1)
        a.embedding = [1, 0]
        b = make_opp(pk=2)
        b.embedding = None
        self.assertEqual(list(similarities_for([1, 0], [a, b])), [1])


class MetricTests(unittest.TestCase):
    def test_precision_and_recall(self):
        ranked = ["a", "b", "c", "d", "e", "f"]
        relevant = {"a", "c", "z"}
        self.assertAlmostEqual(precision_at_k(ranked, relevant, 5), 2 / 5)
        self.assertAlmostEqual(recall_at_k(ranked, relevant, 5), 2 / 3)
        self.assertEqual(recall_at_k(ranked, set(), 5), 0.0)

    def test_precision_rejects_bad_k(self):
        with self.assertRaises(ValueError):
            precision_at_k([], [], 0)


class LabelTests(unittest.TestCase):
    def test_every_level_has_a_label(self):
        self.assertEqual(
            set(EDUCATION_LABELS), {"secondary", "undergraduate", "graduate", "postgraduate"}
        )


if __name__ == "__main__":
    unittest.main()
