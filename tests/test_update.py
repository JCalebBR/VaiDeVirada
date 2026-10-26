import unittest
import json
from pathlib import Path
from scripts.update import extract, merge


class ElectionDataTest(unittest.TestCase):
    def test_second_round_bulletin_catalog_filter(self):
        from scripts.update_extension import summarize
        sample = [
            {'name': 'AC - Boletim de Urna - Primeiro turno', 'url': 'https://example.com/first.zip'},
            {'name': 'AC - Hash SHA2 - Segundo turno', 'url': 'https://example.com/hash'},
            {'name': 'AC - Boletim de Urna - Segundo turno - 26.10.2026',
             'url': 'https://cdn.tse.jus.br/second.zip'},
        ]
        data = summarize(sample)
        self.assertEqual(data['areasPublished'], 1)
        self.assertEqual(data['round2Bulletins']['AC'], 'https://cdn.tse.jus.br/second.zip')

    def test_first_round_curve_ends_at_official_result(self):
        data_dir = Path(__file__).resolve().parents[1] / 'data'
        data = json.loads((data_dir / 'first-round-history.json').read_text())['history']
        official = json.loads((data_dir / 'results.json').read_text())['firstRound']
        self.assertGreater(len(data), 100)
        self.assertLess(data[0]['counted'], 2)
        self.assertTrue(all(a['counted'] < b['counted'] for a, b in zip(data, data[1:])))
        for n in ('13', '22'):
            self.assertEqual(data[-1]['candidates'][n]['votes'], official['candidates'][n]['votes'])
            self.assertEqual(data[-1]['candidates'][n]['percentage'], official['candidates'][n]['percentage'])

    def test_archive_is_attributed_and_verified(self):
        from scripts.import_archive import archived_points
        raw = json.loads((Path(__file__).resolve().parents[1] / 'data/archive-2026-10-25.json').read_text())
        points = archived_points(raw, '2026-10-25T20:19:04-03:00')
        self.assertGreater(len(points), 30)
        self.assertAlmostEqual(points[0]['counted'], .21252, places=4)
        self.assertTrue(all(p['origin'] == 'Placar / captura do TSE' for p in points))
        self.assertTrue(all(a['counted'] < b['counted'] for a, b in zip(points, points[1:])))

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
