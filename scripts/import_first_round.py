#!/usr/bin/env python3
"""Preserve the archived first-round progression in a compact static file."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen

try:
    from .update import ROOT
except ImportError:
    from update import ROOT

ARCHIVE_URL = (
    'https://placar-feed.nicolasqueiroga.workers.dev/history'
    '?race=presidente&from=1791142200000&to=1791216000000'
)
IDS = {'13': '280002542548', '22': '280002551544'}
TZ = timezone(timedelta(hours=-3))


def normalize(raw, official):
    snapshots = []
    seen = set()
    for row in raw['points']:
        if row['race'] != 'presidente' or row['uf'] != 'BR':
            continue
        candidates = json.loads(row['candidates'])
        by_id = {str(c['id']): c for c in candidates if c.get('id')}
        if len(candidates) < 12 or not all(candidate in by_id for candidate in IDS.values()):
            continue
        total = sum(int(c['votes']) for c in candidates)
        counted = float(row['sections_pct'])
        at = datetime.fromtimestamp(row['ts'] / 1000, TZ).isoformat(timespec='seconds')
        if not 0 < counted <= 100 or total <= 0 or not at.startswith(('2026-10-04', '2026-10-05')):
            continue
        if any(abs(int(by_id[id_]['votes']) / total * 100 - float(by_id[id_]['pct'])) > .04
               for id_ in IDS.values()):
            continue
        votes = tuple(int(by_id[id_]['votes']) for id_ in IDS.values())
        if votes in seen:
            continue
        seen.add(votes)
        snapshots.append({
            'at': at, 'counted': counted,
            'candidates': {n: {'votes': int(by_id[id_]['votes']),
                                'percentage': int(by_id[id_]['votes']) / total * 100}
                           for n, id_ in IDS.items()},
        })
    snapshots.sort(key=lambda point: (point['counted'], point['at']))
    points = []
    for point in snapshots:
        if not points or point['counted'] > points[-1]['counted']:
            points.append(point)
    if len(points) < 20 or points[-1]['counted'] != 100:
        raise ValueError('First-round archive is incomplete')
    for n in IDS:
        if points[-1]['candidates'][n]['votes'] != official['candidates'][n]['votes']:
            raise ValueError('Archive final votes disagree with official TSE result')
        points[-1]['candidates'][n]['percentage'] = official['candidates'][n]['percentage']
    return {'source': 'Placar / captura do TSE', 'archiveUrl': ARCHIVE_URL, 'history': points}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, help='Saved response from the public archive')
    args = parser.parse_args()
    if args.input:
        raw = json.loads(args.input.read_text())
    else:
        with urlopen(ARCHIVE_URL, timeout=30) as response:
            raw = json.load(response)
    official = json.loads((ROOT / 'data/results.json').read_text())['firstRound']
    data = normalize(raw, official)
    path = ROOT / 'data/first-round-history.json'
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(f'Preserved {len(data["history"])} first-round points from {data["history"][0]["at"]}')


if __name__ == '__main__':
    main()
