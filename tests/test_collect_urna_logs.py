import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collect_urna_logs as collector


def archive(times, extra='', member='logd.dat'):
    text = '\n'.join(f'{day} {clock}\tINFO\t123\tVOTA\t{collector.EVENT}\tx'
                     for day, clock in times)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zipped:
        zipped.writestr(member, (text + '\n' + extra).encode('latin-1'))
    return buffer.getvalue()


def tlv(tag, value):
    if len(value) < 128:
        size = bytes([len(value)])
    else:
        size_bytes = len(value).to_bytes((len(value).bit_length() + 7) // 8, 'big')
        size = bytes([128 + len(size_bytes)]) + size_bytes
    return bytes([tag]) + size + value


def number(value, tag=2):
    return tlv(tag, value.to_bytes(max(1, (value.bit_length() + 8) // 8), 'big'))


def seq(*values, tag=48):
    return tlv(tag, b''.join(values))


def synthetic_bu(election=6258, mun=20516, zone=64, section=427, total=10, votes=(6, 2, 1, 1), exterior=False):
    rows = []
    for code, count in zip(('13', '22', 'blank', 'null'), votes):
        kind = 1 if code.isdigit() else {'blank': 2, 'null': 3}[code]
        candidate = seq(number(int(code)), number(int(code)), tag=163) if kind == 1 else b''
        rows.append(seq(number(kind, 129), number(count, 130), candidate, number(1), tlv(4, b'x')))
    cargo = seq(number(1, 129), number(1), seq(*rows))
    voting = seq(number(1, 10), number(total), seq(cargo))
    result = seq(number(election), number(10), number(10), number(1), seq(voting))
    body = seq(seq(), number(2, 10), seq(),
               seq(seq(number(mun), number(zone)), number(1), number(section)),
               tlv(27, b'20261025T170000'), seq(tag=160), number(total),
               *(() if exterior else (seq(tag=161),)), seq(result), seq())
    return seq(seq(), number(2, 10), seq(tag=160), number(1, 10), tlv(4, body))


class LogTests(unittest.TestCase):
    def test_boundary_partition_and_day(self):
        raw = archive([(collector.DAY, t) for t in ('16:59:59', '17:00:00', '17:00:01',
                                                   '19:00:00', '19:00:01')]
                      + [('04/10/2026', '18:00:00')])
        counts = collector.parse_log(raw, -3)
        self.assertEqual((counts['total'], counts['pre17'], counts['post17to19'],
                          counts['after19'], counts['at17']), (5, 2, 2, 1, 1))
        self.assertEqual(counts['lastVoteHourBRT'], 19)

    def test_timezone_conversion_not_local_17(self):
        raw = archive([(collector.DAY, '15:00:00'), (collector.DAY, '15:00:01')])
        self.assertEqual(collector.parse_log(raw, -5)['post17to19'], 1)
        self.assertEqual(collector.utc_offset('ac', 'RIO BRANCO'), -5)
        self.assertEqual(collector.utc_offset('am', 'EIRUNEP\u00c9'), -5)
        self.assertEqual(collector.utc_offset('am', 'MANAUS'), -4)
        self.assertEqual(collector.utc_offset('ms', 'CAMPO GRANDE'), -4)
        self.assertEqual(collector.utc_offset('pe', 'FERNANDO DE NORONHA'), -2)
        self.assertEqual(collector.utc_offset('pb', 'JOAO PESSOA'), -3)
        self.assertIsNone(collector.utc_offset('zz', 'LISBOA'))

    def test_exterior_keeps_local_clock(self):
        counts = collector.parse_log(archive([(collector.DAY, '16:59:00'), (collector.DAY, '17:20:00')]), None)
        self.assertEqual((counts['pre17'], counts['post17to19'], counts['lastVoteHourBRT']), (1, 1, 17))

    def test_strict_module_and_message(self):
        extra = f'{collector.DAY} 18:01:00\tINFO\t123\tOTHER\t{collector.EVENT}\tx'
        self.assertEqual(collector.parse_log(archive([], extra), -3)['total'], 0)

    def test_rejects_unexpected_archive_clock_changes_and_regression(self):
        with self.assertRaises(collector.Excluded):
            collector.parse_log(archive([], member='other.dat'), -3)
        with self.assertRaisesRegex(collector.Excluded, 'regression'):
            collector.parse_log(archive([(collector.DAY, '17:01:00'),
                                        (collector.DAY, '17:00:00')]), -3)
        with self.assertRaisesRegex(collector.Excluded, 'adjustment'):
            collector.parse_log(archive([(collector.DAY, '15:00:00')],
                                        collector.DAY + ' 16:00:00\tAjuste de hor\u00e1rio'), -3)
        # Daylight saving applied at boot, before any vote, does not move vote times.
        boot = '\n'.join([f'{collector.DAY} 06:00:00\tINFO\t123\tGAP\tHor\u00e1rio da urna alterado devido a hor\u00e1rio de ver\u00e3o\tx',
                          f'{collector.DAY} 09:00:00\tINFO\t123\tVOTA\t{collector.EVENT}\tx'])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zipped:
            zipped.writestr('logd.dat', boot.encode('latin-1'))
        self.assertEqual(collector.parse_log(buffer.getvalue(), None)['total'], 1)
        with self.assertRaises(ValueError):
            collector.parse_log(archive([(collector.DAY, '25:00:00')]), -3)

    def test_nested_log_archive_votes_are_summed(self):
        inner = archive([(collector.DAY, '17:30:00')])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zipped:
            zipped.writestr('logd.dat', zipfile.ZipFile(io.BytesIO(
                archive([(collector.DAY, '09:00:00')]))).read('logd.dat'))
            zipped.writestr('0204771ME.jez', inner)
        counts = collector.parse_log(buffer.getvalue(), -3)
        self.assertEqual((counts['total'], counts['pre17'], counts['post17to19']), (2, 1, 1))
        self.assertEqual(counts['lastVoteHourBRT'], 17)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zipped:
            zipped.writestr('logd.dat', b'')
            zipped.writestr('notes.txt', b'')
        with self.assertRaisesRegex(collector.Excluded, 'layout'):
            collector.parse_log(buffer.getvalue(), -3)


class BulletinTests(unittest.TestCase):
    def test_der_votes_turnout_and_identity(self):
        result = collector.parse_bu(synthetic_bu(), '20516', '0064', '0427')
        self.assertEqual(result, {'total': 10, 'votes': {'13': 6, '22': 2, 'blank': 1, 'null': 1}})
        for raw in (synthetic_bu(section=428), synthetic_bu(election=6257),
                    synthetic_bu(total=11), synthetic_bu()[:-1], b'\x30\x80'):
            with self.assertRaises((collector.Excluded, IndexError)):
                collector.parse_bu(raw, '20516', '0064', '0427')

    def test_reconciliation_and_nonzero_total(self):
        log = dict(total=10, pre17=6, at17=0, post17to19=3, after19=1)
        bu = collector.parse_bu(synthetic_bu(), '20516', '0064', '0427')
        self.assertEqual(collector.reconcile(log, bu)['total'], 10)
        with self.assertRaisesRegex(collector.Excluded, 'unreconciled'):
            collector.reconcile({**log, 'total': 11}, bu)
        with self.assertRaisesRegex(collector.Excluded, 'partition'):
            collector.reconcile({**log, 'pre17': 7}, bu)

    def test_exterior_bu_without_optional_field(self):
        # Exterior BUs lack the empty [1] node Brazilian BUs carry between turnout and the elections.
        self.assertEqual(collector.parse_bu(synthetic_bu(exterior=True), '20516', '0064', '0427')['total'], 10)

    def test_paper_ballot_sections_are_excluded(self):
        aux = {'hashes': [{'hash': 'abc', 'arq': [{'nm': 'x-busa.dat', 'tp': 'busa'},
                                                   {'nm': 'x-logsa.jez', 'tp': 'logsa'}]}]}
        status, detail = collector.collect_one(('zz', '29173', '0001', '0494'), 'KATMANDU',
                                               lambda _: json.dumps(aux).encode())
        self.assertEqual((status, detail['reason']), ('excluded', 'paper_ballot_sa'))

    def test_multiple_urn_sets_excluded_not_chosen(self):
        fetch = lambda _: json.dumps({'hashes': [{}, {}]}).encode()
        status, detail = collector.collect_one(('pb', '20516', '0064', '0427'), 'JOAO PESSOA', fetch)
        self.assertEqual(status, 'excluded')
        self.assertIn('contingency', detail['reason'])

    def test_network_failure_is_reported(self):
        def fetch(_):
            raise collector.HTTPError('https://example.test', 404, 'missing', {}, None)
        self.assertEqual(collector.collect_one(('pb', '20516', '0064', '0427'),
                                              'JOAO PESSOA', fetch),
                         ('failed', {'reason': 'http_404'}))


class AggregationTests(unittest.TestCase):
    def test_allocation_includes_invalid_votes_and_removes_after19(self):
        row = dict(total=10, pre17=6, at17=0, post17to19=3, after19=1,
                   votes={'13': 6, '22': 2, 'blank': 1, 'null': 1}, lastVoteHourBRT=19)
        output = collector.summarize([('pb', '20516', row), ('ac', '01392', row)])
        national = output['national']
        self.assertAlmostEqual(national['estimatedWindow']['13'], 3.6)
        self.assertAlmostEqual(sum(national['estimatedWindow'].values()), 6)
        self.assertAlmostEqual(national['estimatedUntil17']['13'], 7.2)
        self.assertEqual(national['marginBounds'], [0, 12])
        self.assertEqual(national['lastVoteHourBRT'], {'19': 2})
        self.assertEqual(national['lastVoteHourKnownSections'], 2)
        self.assertEqual(output['byUF']['PB']['sections'], 1)
        self.assertEqual(output['byMunicipality']['PB/20516']['post17to19'], 3)
        self.assertIsNone(collector.summarize([])['national']['estimatedWinner'])

    def test_exterior_stays_out_of_brasilia_sums(self):
        row = dict(total=10, pre17=9, at17=0, post17to19=1, after19=0,
                   votes={'13': 6, '22': 2, 'blank': 1, 'null': 1}, lastVoteHourBRT=17)
        output = collector.summarize([('pb', '20516', row), ('zz', '29955', row)])
        self.assertEqual(output['national']['sections'], 1)
        self.assertNotIn('ZZ', output['byUF'])
        self.assertEqual(output['exterior']['sections'], 1)
        self.assertEqual(output['exterior']['lastVoteHourLocal'], {'17': 1})

    def test_exterior_bound_uses_arrival_time_not_offsets(self):
        sections = [('ok', f'{collector.DAY} 14:31:04', 300), ('excluded', f'{collector.DAY} 06:00:00', None),
                    ('ok', f'{collector.DAY} 21:12:49', 250), ('excluded', None, None)]
        self.assertEqual(collector.exterior_bound(sections, 500),
                         {'sections': 4, 'receivedBefore17BRT': 2, 'lateBoundBRT': 750})
        self.assertFalse(collector.received_before_17('04/10/2026 10:00:00'))

    def test_margin_bounds_against_all_feasible_assignments(self):
        for a in range(4):
            for b in range(4):
                for other in range(3):
                    total = a + b + other
                    if not total:
                        continue
                    for removed in range(total + 1):
                        row = dict(total=total, pre17=total - removed, at17=0,
                                   post17to19=removed, after19=0,
                                   votes={'13': a, '22': b, 'blank': other, 'null': 0})
                        possible = [a - x - b + y for x in range(a + 1) for y in range(b + 1)
                                    if 0 <= removed - x - y <= other]
                        group = collector.empty_group()
                        collector.add_group(group, row)
                        self.assertEqual(group['marginBounds'], [min(possible), max(possible)])

    def test_enumeration_deduplicates_and_validates_pleito(self):
        payload = {'cdp': '3221', 'dg': collector.DAY, 'abr': [{'cd': 'pb', 'mu': [
            {'cd': '20516', 'nm': 'JOAO PESSOA', 'zon': [
                {'cd': '64', 'sec': [{'ns': '427', 'nsa': ['428']}, {'ns': '427'},
                                     {'ns': '428', 'nsp': '427'}]}]}]}]}
        self.assertEqual(collector.enumerate_sections(payload, 'pb'),
                         [(('pb', '20516', '0064', '0427'), 'JOAO PESSOA', None, None),
                          (('pb', '20516', '0064', '0428'), 'JOAO PESSOA', '0427', None)])
        payload['abr'][0]['mu'][0]['zon'][0]['sec'] = [{'ns': '427', 'da': collector.DAY, 'ha': '14:31:04'}]
        self.assertEqual(collector.enumerate_sections(payload, 'pb')[0][3], f'{collector.DAY} 14:31:04')
        with self.assertRaises(collector.Excluded):
            collector.enumerate_sections({**payload, 'cdp': '6258'}, 'pb')

    def test_aggregated_sections_are_marked_not_fetched(self):
        payload = {'cdp': '3221', 'dg': collector.DAY, 'abr': [{'cd': 'pb', 'mu': [
            {'cd': '20516', 'nm': 'JOAO PESSOA', 'zon': [
                {'cd': '64', 'sec': [{'ns': '427'}, {'ns': '428', 'nsp': '427'}]}]}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            db = collector.connect(Path(tmp) / 'state.sqlite')
            with patch.object(collector, 'AREAS', ['pb']):
                self.assertTrue(collector.catalog_stale(db))
                collector.load_catalogs(db, lambda *_: json.dumps(payload).encode())
                self.assertFalse(collector.catalog_stale(db))
            self.assertEqual(dict(db.execute('SELECT section,status FROM sections')),
                             {'0427': 'pending', '0428': 'aggregated'})
            db.close()

    def test_checkpoint_resume_export_does_not_make_national_winner(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            db = collector.connect(path / 'state.sqlite')
            db.execute("INSERT INTO sections(uf,mun,zone,section,name) VALUES('pb','20516','0064','0427','TEST')")
            db.execute("INSERT INTO configs VALUES('pb','ok','1')")
            db.commit()
            db.close()
            db = collector.connect(path / 'state.sqlite')
            collector.export(db, path / 'analysis.json', path / 'absences.jsonl')
            result = json.loads((path / 'analysis.json').read_text())
            self.assertEqual(result['coverage']['pending'], 1)
            self.assertEqual(result['coverage']['areasEnumerated'], 1)
            self.assertIsNone(result['nationalCounterfactualWinner'])
            self.assertEqual(result['national']['sections'], 0)
            db.close()

    def error(self, code):
        return collector.HTTPError('https://example.test', code, 'x', {}, None)

    def test_block_pauses_every_worker_then_resumes_slower(self):
        fetch = collector.Fetcher(interval=.01, attempts=2)
        fetch.BLOCK_PAUSE = .05
        started = collector.time.monotonic()
        with patch.object(collector, 'http_get', side_effect=[self.error(403), b'ok']):
            self.assertEqual(fetch('https://example.test'), b'ok')
        self.assertGreaterEqual(collector.time.monotonic() - started, .05)
        self.assertEqual(fetch.pauses, 0)
        self.assertGreater(fetch.gap, .01)

    def test_repeated_blocks_stop_instead_of_renewing(self):
        fetch = collector.Fetcher(interval=.01)
        fetch.BLOCK_PAUSE = 0
        with patch.object(collector, 'http_get', side_effect=self.error(429)), \
                patch.object(collector.time, 'sleep'):
            with self.assertRaisesRegex(collector.Blocked, '429'):
                fetch('https://example.test')

    def test_consecutive_404_trip_the_breaker(self):
        fetch = collector.Fetcher(interval=.01)
        with patch.object(collector, 'http_get', side_effect=self.error(404)), \
                patch.object(collector.time, 'sleep'):
            for _ in range(fetch.MAX_CONSECUTIVE_404 - 1):
                with self.assertRaises(collector.HTTPError):
                    fetch('https://example.test')
            with self.assertRaisesRegex(collector.Blocked, '404'):
                fetch('https://example.test')
        self.assertIsInstance(collector.Blocked('x'), Exception)
        self.assertNotIsInstance(collector.Blocked('x'), (ValueError, OSError))

    def test_server_errors_back_off_and_slow_everyone(self):
        fetch = collector.Fetcher(interval=.01, attempts=2)
        fetch.stop.wait = lambda seconds: False
        with patch.object(collector, 'http_get', side_effect=[self.error(503), self.error(503)]), \
                patch.object(collector.time, 'sleep'):
            with self.assertRaises(collector.HTTPError):
                fetch('https://example.test')
        self.assertGreaterEqual(fetch.gap, 1)

    def test_confidence_answers_only_when_bound_clears_margin(self):
        def uf_group(sections, late_each):
            group = collector.empty_group()
            row = dict(total=300, pre17=300 - late_each, at17=0, post17to19=late_each, after19=0,
                       votes={'13': 150, '22': 150 - 0, 'blank': 0, 'null': 0})
            row['votes']['22'] = 300 - 150
            for i in range(sections):
                collector.add_group(group, {**row, 'post17to19': late_each + i % 2,
                                            'pre17': 300 - late_each - i % 2})
            return group
        byUF = {'PB': uf_group(100, 1)}
        denominators = {'PB': {'ok': 100, 'pending': 900}, 'ZZ': {'excluded': 10}}
        official = {'candidates': {'13': {'votes': 1_000_000}, '22': {'votes': 900_000}},
                    'counted': '100,00'}
        result = collector.confidence(byUF, denominators, official, rate_per_minute=100)
        self.assertEqual((result['kind'], result['level']), ('sample', .999))
        self.assertTrue(result['answered'])
        self.assertTrue(result['marginFinal'])
        self.assertEqual(result['lateEstimate'], 1500)
        self.assertEqual(result['worstCaseNonRandom'], 3000)
        close = {'candidates': {'13': {'votes': 1000}, '22': {'votes': 900}}, 'counted': '99,50'}
        result = collector.confidence(byUF, denominators, close)
        self.assertFalse(result['answered'])
        self.assertFalse(result['marginFinal'])
        self.assertIsNone(collector.confidence(byUF, denominators, None))
        census = collector.confidence(byUF, {'PB': {'ok': 100, 'excluded': 1}}, official,
                                      exterior=[('ok', f'{collector.DAY} 21:00:00', 200)])
        self.assertEqual((census['kind'], census['level']), ('census', None))
        self.assertEqual(census['lateEstimate'], 150)
        self.assertEqual(census['worstCaseNonRandom'], 300 + 200)
        self.assertEqual(census['lateUpper'], 150 + 500)

    def test_pool_processes_every_pending_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            db = collector.connect(path / 'state.sqlite')
            db.executemany("INSERT INTO sections(uf,mun,zone,section,name) VALUES(?,?,?,?,'X')",
                           [(uf, '00001', '0001', f'{n:04d}') for uf in ('pb', 'sp') for n in range(5)])
            db.commit()
            args = collector.argparse.Namespace(workers=3, seconds=0, output=path / 'a.json',
                                                report=path / 'r.jsonl')
            with patch.object(collector, 'collect_one', return_value=('excluded', {'reason': 'test'})):
                collector.collect_pending(db, None, args, collector.threading.Event())
            self.assertEqual(dict(db.execute('SELECT status,COUNT(*) FROM sections GROUP BY status')),
                             {'excluded': 10})
            db.close()


if __name__ == '__main__':
    unittest.main()
