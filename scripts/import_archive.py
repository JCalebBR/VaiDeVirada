#!/usr/bin/env python3
"""Import the attributed third-party archive of observed TSE national totals."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from .update import ROOT
except ImportError:
    from update import ROOT

ARCHIVE_URL = 'https://placar-feed.nicolasqueiroga.workers.dev/history?race=presidente2&minutes=1440'
TZ = timezone(timedelta(hours=-3))
EXPECTED_IDS = {'13': '280002542548', '22': '280002551544'}


def archived_points(raw, first_observed):
    points = []
    seen = set()
    for row in raw['points']:
        if row['race'] != 'presidente2' or row['uf'] != 'BR':
            continue
        at = datetime.fromtimestamp(row['ts'] / 1000, TZ)
        if at.date().isoformat() != '2026-10-25' or at.isoformat() >= first_observed:
            continue
        counted = float(row['sections_pct'])
        if not 0 < counted <= 100:
            continue
        candidates = json.loads(row['candidates'])
        by_id = {str(c['id']): c for c in candidates}
        if not all(id_ in by_id for id_ in EXPECTED_IDS.values()):
            continue
        vote13, vote22 = (int(by_id[EXPECTED_IDS[n]]['votes']) for n in ('13', '22'))
        total = vote13 + vote22
        if total <= 0 or any(abs(float(by_id[EXPECTED_IDS[n]]['pct']) - votes / total * 100) > .02
                                 for n, votes in (('13', vote13), ('22', vote22))):
            continue
        key = (vote13, vote22)
        if key in seen:
            continue
        seen.add(key)
        points.append({
            'id': f'archive-{row["ts"]}', 'at': at.isoformat(timespec='seconds'),
            'counted': counted, 'validVotes': total, 'origin': 'Placar / captura do TSE',
            'candidates': {n: {'name': 'Lula' if n == '13' else 'Flavio Bolsonaro',
                               'votes': by_id[id_]['votes'],
                               'percentage': by_id[id_]['votes'] / total * 100}
                           for n, id_ in EXPECTED_IDS.items()}
        })
    points.sort(key=lambda p: (p['counted'], p['at']))
    cleaned = []
    for point in points:
        if cleaned and point['counted'] <= cleaned[-1]['counted']:
            continue
        cleaned.append(point)
    # Independent raw TSE sample observed at 20:17:34 Brasília, 39.844526167%.
    anchor = next((p for p in cleaned if p['validVotes'] == 49105215), None)
    if not anchor or anchor['candidates']['13']['votes'] != 24444579 or anchor['candidates']['22']['votes'] != 24660636:
        raise ValueError('Archived series lacks the independently checked official TSE sample')
    return cleaned


def main():
    path = ROOT / 'data/results.json'
    data = json.loads(path.read_text())
    original = [p for p in data['history'] if not p['id'].startswith('archive-')]
    points = archived_points(json.loads((ROOT / 'data/archive-2026-10-25.json').read_text()), original[0]['at'])
    if not points or points[-1]['counted'] >= original[0]['counted']:
        raise ValueError('Archive does not precede own observations')
    data['history'] = points + original
    data['archiveUrl'] = ARCHIVE_URL
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(f'Imported {len(points)} attributed archive points; first {points[0]["at"]}')


if __name__ == '__main__':
    main()
