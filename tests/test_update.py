import unittest
from scripts.update import extract, merge


class ElectionDataTest(unittest.TestCase):
    def test_parse_national_candidate_totals(self):
        payload = {
            'tpabr': 'br', 'cdabr': 'br', 't': '1', 'ele': '6257',
            'idg': '42', 'dt': '05/10/2026', 'ht': '12:00:00',
            's': {'pstn': '100'}, 'v': {'vvc': '1000'},
            'carg': [{'cd': '1', 'agr': [
                {'par': [{'cand': [{'n': '22', 'nmu': 'FLAVIO BOLSONARO',
                                     'dvt': 'Válido', 'vap': '470',
                                     'pvapn': '47,03'}]}]},
                {'par': [{'cand': [{'n': '13', 'nmu': 'LULA',
                                     'dvt': 'Válido', 'vap': '450',
                                     'pvapn': '45,16'}]}]},
            ]}],
        }
        first = extract(payload)
        self.assertEqual(first['candidates']['13']['name'], 'Lula')
        self.assertEqual(first['candidates']['22']['percentage'], 47.03)
        self.assertEqual(first['at'], '2026-10-05T12:00:00-03:00')
        with self.assertRaises(ValueError):
            extract({**payload, 'cdabr': 'sp'})

    def test_merge_deduplicates_and_rejects_regression(self):
        first = {'counted': 100}
        snapshot = {'id': '1', 'at': '2026-10-25T17:00:00-03:00', 'counted': 2}
        result = merge({}, first, snapshot)
        self.assertEqual(len(merge(result, first, snapshot)['history']), 1)
        with self.assertRaises(ValueError):
            merge(result, first, {**snapshot, 'id': '2', 'counted': 1})
        next_result = merge(result, first, {**snapshot, 'id': '2', 'counted': 2})
        self.assertEqual(len(next_result['history']), 1)
        self.assertEqual(next_result['history'][0]['id'], '2')


if __name__ == '__main__':
    unittest.main()
