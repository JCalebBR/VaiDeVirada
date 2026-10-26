#!/usr/bin/env python3
"""Audit one official second-round urn log without storing individual events."""
import argparse
import io
import json
import re
import urllib.request
import zipfile

BASE = 'https://resultados.tse.jus.br/oficial/ele2026/arquivo-urna/3221/dados'
DAY = '25/10/2026'
EVENT = 'O voto do eleitor foi computado'
MAX_ZIP_BYTES = 2_000_000
MAX_LOG_BYTES = 8_000_000


def count_votes(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != ['logd.dat'] or archive.getinfo('logd.dat').file_size > MAX_LOG_BYTES:
            raise ValueError('Unexpected log archive')
        lines = archive.read('logd.dat').decode('latin-1').splitlines()
    result = {'total': 0, 'after17': 0, 'after19': 0}
    for line in lines:
        if EVENT not in line:
            continue
        parts = line.split('\t')
        if len(parts) != 6 or parts[3] != 'VOTA' or parts[4] != EVENT:
            continue
        match = re.fullmatch(r'(\d{2}/\d{2}/\d{4}) (\d{2}):(\d{2}):(\d{2})', parts[0])
        if not match or match[1] != DAY:
            continue
        hour, minute, second = map(int, match.groups()[1:])
        if hour > 23 or minute > 59 or second > 59:
            raise ValueError('Invalid urn clock')
        result['total'] += 1
        if (hour, minute, second) > (17, 0, 0):
            result['after17'] += 1
        if (hour, minute, second) > (19, 0, 0):
            result['after19'] += 1
    return result


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'VaiDeVirada/1.0'})
    with urllib.request.urlopen(req, timeout=30) as response:
        limit = MAX_ZIP_BYTES if url.endswith('.jez') else 200_000
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Official file larger than safety limit')
        return data


def audit(uf, municipality, zone, section):
    if not re.fullmatch(r'[a-z]{2}', uf):
        raise ValueError('Invalid UF')
    values = (municipality, zone, section)
    if not all(re.fullmatch(r'\d+', x) for x in values):
        raise ValueError('Invalid section identifiers')
    municipality, zone, section = (municipality.zfill(5), zone.zfill(4), section.zfill(4))
    path = f'{BASE}/{uf}/{municipality}/{zone}/{section}'
    aux = json.loads(fetch(f'{path}/p003221-{uf}-m{municipality}-z{zone}-s{section}-aux.json'))
    hashes = aux.get('hashes', [])
    if len(hashes) != 1:
        raise ValueError(f'Expected one urn file set, found {len(hashes)}; inspect aggregation/contingency')
    record = hashes[0]
    if not re.fullmatch(r'[A-Za-z0-9=]+', record['hash']):
        raise ValueError('Invalid urn hash')
    logs = [a['nm'] for a in record['arq'] if a['tp'] in ('log', 'logsa')]
    if len(logs) != 1 or not re.fullmatch(r'[a-zA-Z0-9_.-]+\.jez', logs[0]):
        raise ValueError('Expected exactly one .jez log')
    summary = count_votes(fetch(f"{path}/{record['hash']}/{logs[0]}"))
    return {'section': f'{uf.upper()} / {municipality} / {zone} / {section}',
            'auxUrl': f'{path}/p003221-{uf}-m{municipality}-z{zone}-s{section}-aux.json',
            'urnClock': 'local da urna; verificar fuso e relógio antes de agregar',
            **summary}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('uf')
    parser.add_argument('municipality')
    parser.add_argument('zone')
    parser.add_argument('section')
    args = parser.parse_args()
    print(json.dumps(audit(args.uf.lower(), args.municipality, args.zone, args.section),
                     ensure_ascii=False, indent=2))
