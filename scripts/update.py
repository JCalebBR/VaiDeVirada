#!/usr/bin/env python3
"""Collect official national presidential totals for the static Pages dashboard."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://resultados.tse.jus.br/oficial/ele2026'
URLS = {1: f'{BASE}/6257/dados/br/br-c0001-e006257-u.json',
        2: f'{BASE}/6258/dados/br/br-c0001-e006258-u.json'}


def number(value):
    return float(str(value).replace(',', '.'))


def candidates(payload):
    cargo = next(c for c in payload['carg'] if c['cd'] == '1')
    return {
        cand['n']: {'name': cand['nmu'].title(), 'votes': int(cand['vap']),
                    'percentage': number(cand['pvapn'])}
        for group in cargo['agr'] for party in group.get('par', [])
        for cand in party.get('cand', []) if cand.get('dvt') == 'Válido'
    }


def extract(payload):
    if payload.get('tpabr') != 'br' or payload.get('cdabr') != 'br':
        raise ValueError('Expected national (BR) totals')
    if payload.get('t') not in ('1', '2'):
        raise ValueError('Unexpected election round')
    if str(payload.get('ele')) != ('6257' if payload['t'] == '1' else '6258'):
        raise ValueError('Unexpected election ID')
    rows = candidates(payload)
    if '13' not in rows or '22' not in rows:
        raise ValueError('Missing presidential finalists')
    timestamp = datetime.strptime(payload['dt'] + ' ' + payload['ht'], '%d/%m/%Y %H:%M:%S')
    # TSE timestamps are local Brasília time; include the explicit offset in serialized data.
    from datetime import timedelta
    timestamp = timestamp.replace(tzinfo=timezone(timedelta(hours=-3)))
    return {
        'id': str(payload['idg']), 'at': timestamp.isoformat(),
        'counted': number(payload['s']['pstn']),
        'validVotes': int(payload['v']['vvc']),
        'candidates': {n: rows[n] for n in ('22', '13')},
    }


def fetch(url):
    req = Request(url, headers={'User-Agent': 'VaiDeVirada/1.0 (GitHub Pages election dashboard)',
                                'Accept': 'application/json'})
    with urlopen(req, timeout=25) as response:
        return json.load(response)


def merge(existing, first, second):
    if first['counted'] < 99.99:
        raise ValueError('First round is not fully counted')
    history = existing.get('history', [])
    if history:
        previous = history[-1]
        if second['counted'] < previous['counted'] - 0.0001:
            raise ValueError('Counted percentage went backwards; keep previous data')
        if second['at'] < previous['at']:
            raise ValueError('Source timestamp went backwards; keep previous data')
        if second['id'] == previous['id']:
            return {**existing, 'firstRound': first}
        if second['counted'] == previous['counted']:
            history = history[:-1]
    if not history or second['id'] != history[-1]['id']:
        history = [*history, second]
    return {'source': 'Tribunal Superior Eleitoral', 'firstRound': first,
            'history': history, 'round2Url': URLS[2], 'round1Url': URLS[1]}


def main():
    path = ROOT / 'data' / 'results.json'
    old = json.loads(path.read_text()) if path.exists() else {}
    first = extract(fetch(URLS[1]))
    second = extract(fetch(URLS[2]))
    new = merge(old, first, second)
    if new != old:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n')
        print(f"Updated {second['counted']:.2f}% at {second['at']}")
    else:
        print('No new TSE data')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as exc:
        print(f'Collection failed: {exc}', file=sys.stderr)
        sys.exit(1)
