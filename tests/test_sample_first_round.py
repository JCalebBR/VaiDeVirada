from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sample_first_round as baseline


class EstimateTests(unittest.TestCase):
    def test_stratified_estimate_scales_each_uf_and_has_no_error_on_a_census(self):
        self.assertEqual(baseline.estimate([(4, [1, 3, 2, 2])]), (8, 8, 8))
        late, low, high = baseline.estimate([(100, [0, 10]), (10, [1, 1])])
        self.assertEqual(late, 510)
        self.assertLess(low, late)
        self.assertGreater(high, late)

    def test_paper_ballot_and_unreconciled_sections_are_not_counted(self):
        fetch = lambda _: b'{"hashes": []}'
        self.assertEqual(baseline.collect_one(('pb', '20516', '0064', '0427'), 'JOAO PESSOA', fetch),
                         ('excluded', 'multiple_or_missing_sets_contingency'))


if __name__ == '__main__':
    unittest.main()
