import io
import unittest
import zipfile

from scripts.audit_urna import count_votes


def archive(lines, name='logd.dat'):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as writer:
        writer.writestr(name, '\n'.join(lines).encode('latin-1'))
    return stream.getvalue()


def event(time, text='O voto do eleitor foi computado', module='VOTA', date='25/10/2026'):
    return f'{date} {time}\tINFO\t01798584\t{module}\t{text}\tABCDEF'


class UrnAuditTest(unittest.TestCase):
    def test_counts_only_completed_votes_on_election_day(self):
        raw = archive([
            event('16:59:59'),
            event('17:00:00'),
            event('17:00:01'),
            event('18:45:00'),
            event('19:00:01'),
            event('18:00:00', 'Eleitor foi habilitado'),
            event('18:00:00', module='SCUE'),
            event('18:00:00', date='04/10/2026'),
        ])
        self.assertEqual(count_votes(raw), {'total': 5, 'after17': 3, 'after19': 1})

    def test_rejects_invalid_archive_and_clock(self):
        with self.assertRaises(ValueError):
            count_votes(archive([event('17:01:00')], '../logd.dat'))
        with self.assertRaises(ValueError):
            count_votes(archive([event('25:01:00')]))


if __name__ == '__main__':
    unittest.main()
