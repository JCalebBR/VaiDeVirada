#!/usr/bin/env python3
"""Baseline for the 2nd round: votes after 17h in a random sample of 1st-round sections.

The 1st round (04/10/2026) closed at the normal time, so votes logged after 17h there
come from the queue rule alone (voters in line at 17h still vote). The sample is drawn
per UF in proportion to its sections, with a fixed seed, reusing the 2nd-round
collector's log parser, timezone rules and request pacing. Only aggregates are saved.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import re

import collect_urna_logs as c

PLEITO = '3220'
DAY = '04/10/2026'
ROOT = Path(__file__).resolve().parents[1]


def catalog(fetch, uf):
    payload = json.loads(fetch(f'{c.BASE}/arquivo-urna/{PLEITO}/config/{uf}/{uf}-p00{PLEITO}-cs.json', 12_000_000))
    if str(payload.get('cdp')) != PLEITO:
        raise c.Excluded('config_election')
    found = set()
    for area in payload['abr']:
        for mun in area['mu']:
            for zone in mun['zon']:
                for sec in zone['sec']:
                    ids = (mun['cd'].zfill(5), zone['cd'].zfill(4), sec['ns'].zfill(4))
                    # Aggregated sections have no files of their own.
                    if 'nsp' not in sec and all(re.fullmatch(r'\d+', v) for v in ids):
                        found.add((uf, *ids, mun['nm']))
    return sorted(found)


def collect_one(key, name, fetch):
    uf, mun, zone, section = key
    try:
        path = f'{c.BASE}/arquivo-urna/{PLEITO}/dados/{uf}/{mun}/{zone}/{section}'
        aux = json.loads(fetch(f'{path}/p00{PLEITO}-{uf}-m{mun}-z{zone}-s{section}-aux.json'))
        hashes = aux.get('hashes', [])
        if len(hashes) != 1:
            raise c.Excluded('multiple_or_missing_sets_contingency')
        record = hashes[0]
        if not re.fullmatch(r'[A-Za-z0-9=]+', record['hash']):
            raise c.Excluded('invalid_hash')
        files = {}
        for kind in ('log', 'bu'):
            matches = [a['nm'] for a in record['arq'] if a['tp'] == kind]
            if len(matches) != 1 or not re.fullmatch(r'[A-Za-z0-9_.-]+', matches[0]):
                raise c.Excluded(f'missing_or_multiple_{kind}')
            files[kind] = matches[0]
        turnout, _ = c.bu_body(fetch(f"{path}/{record['hash']}/{files['bu']}"), mun, zone, section, '20261004')
        log = c.parse_log(fetch(f"{path}/{record['hash']}/{files['log']}"), c.utc_offset(uf, name), DAY)
        if not log['total'] or log['total'] != turnout:
            raise c.Excluded('unreconciled')
        return 'ok', log
    except c.Excluded as exc:
        return 'excluded', str(exc)
    except c.HTTPError as exc:
        return 'failed', f'http_{exc.code}'
    except (ValueError, KeyError, IndexError, TypeError, c.zipfile.BadZipFile) as exc:
        return 'excluded', f'format_{type(exc).__name__}'
    except (c.URLError, TimeoutError, OSError) as exc:
        return 'failed', type(exc).__name__


def estimate(strata):
    """Stratified estimate of national late votes with a 99.9% interval (z=3.29)."""
    total = variance = 0
    for population, lates in strata:
        n = len(lates)
        if n < 2:
            continue
        mean = sum(lates) / n
        spread = sum((x - mean) ** 2 for x in lates) / (n - 1)
        total += population * mean
        variance += population ** 2 * (1 - n / population) * spread / n
    half = c.Z_999 * variance ** .5
    return round(total), round(max(0, total - half)), round(total + half)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fraction', type=float, default=.01)
    parser.add_argument('--seed', type=int, default=20261004)
    parser.add_argument('--workers', type=int, default=20, choices=range(1, 65))
    parser.add_argument('--interval', type=float, default=.02)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/first-round-baseline.json')
    args = parser.parse_args()
    if args.interval < 1 / 95 or not 0 < args.fraction <= 1:
        parser.error('interval >= 1/95 s (TSE limit: 100 req/s per IP); 0 < fraction <= 1')
    fetch, rng = c.Fetcher(args.interval), random.Random(args.seed)
    population, sample = {}, []
    for uf in c.AREAS:
        if uf == 'zz':
            continue
        sections = catalog(fetch, uf)
        population[uf] = len(sections)
        sample += rng.sample(sections, max(2, round(len(sections) * args.fraction)))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda row: (row[0], collect_one(row[:4], row[4], fetch)), sample))
    status, reasons, lates, hours = {}, {}, {}, {}
    totals = dict(total=0, post17to19=0, after19=0)
    for uf, (state, value) in results:
        status[state] = status.get(state, 0) + 1
        if state != 'ok':
            reasons[value] = reasons.get(value, 0) + 1
            continue
        lates.setdefault(uf, []).append(value['post17to19'] + value['after19'])
        for key in totals:
            totals[key] += value[key]
        hour = value['lastVoteHourBRT']
        if hour is not None:
            hours[str(hour)] = hours.get(str(hour), 0) + 1
    late, lower, upper = estimate((population[uf], lates[uf]) for uf in lates)
    late_sample = totals['post17to19'] + totals['after19']
    c.atomic_json(args.output, {
        'schemaVersion': 1, 'pleito': PLEITO, 'day': DAY, 'seed': args.seed, 'fraction': args.fraction,
        'populationSections': sum(population.values()), 'sampledSections': len(sample),
        'status': status, 'reasons': reasons, **totals, 'late': late_sample,
        'latePerThousand': round(late_sample / totals['total'] * 1000, 3) if totals['total'] else None,
        'lastVoteHourBRT': hours, 'nationalLateEstimate': late, 'nationalLateInterval999': [lower, upper],
        'method': 'Amostra aleatória por UF (proporcional), exterior fora; log reconciliado com o comparecimento do BU; '
                  'relógio convertido para BRT pelas mesmas regras do 2º turno; intervalo de 99,9% estratificado.'})
    print(json.dumps({'status': status, 'late': late_sample, 'total': totals['total'],
                      'estimate': [late, lower, upper]}))


if __name__ == '__main__':
    main()
