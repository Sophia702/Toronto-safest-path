import unittest

from src.scoring import build_explanation, compute_safety_score


class ScoringTests(unittest.TestCase):
    def test_compute_safety_score_reduces_for_higher_penalties(self):
        score = compute_safety_score(1000.0, 25.0, 10.0, 5.0)
        self.assertAlmostEqual(score, 75.80687499999999)

    def test_higher_crime_penalties_lower_the_score_more_than_distance(self):
        baseline = compute_safety_score(1000.0, 5.0, 5.0, 0.0)
        riskier = compute_safety_score(1000.0, 20.0, 5.0, 0.0)
        self.assertLess(riskier, baseline)

    def test_build_explanation_mentions_dark_streets_when_requested(self):
        explanation = build_explanation(12.0, 6.0, True)
        lowered = explanation.lower()
        self.assertIn("dark streets", lowered)
        self.assertIn("crime", lowered)


if __name__ == "__main__":
    unittest.main()
