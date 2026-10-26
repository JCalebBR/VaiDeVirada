#!/usr/bin/env python3
"""Track availability of official second-round ballot bulletin downloads."""
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATASET = 'https://dadosabertos.tse.jus.br/dataset/resultados-2026-boletim-de-urna'
API = 'https://dadosabertos.tse.jus.br/api/3/action/package_show?id=resultados-2026-boletim-de-urna'


def summarize(resources):
    by_area = {}
    for resource in resources:
        name = resource.get('name', '')
        match = re.match(r'^([A-Z]{2}) - Boletim de Urna - Segundo turno\b', name)
        if match and resource.get('url', '').startswith('https://'):
            by_area[match.group(1)] = resource['url']
    return {
        'datasetUrl': DATASET,
        'round2Bulletins': dict(sorted(by_area.items())),
        'areasPublished': len(by_area),
        'areasExpected': 28,  # 27 unidades federativas e exterior (ZZ).
    }


def main():
    req = Request(API, headers={'Accept': 'application/json', 'User-Agent': 'VaiDeVirada/1.0'})
    with urlopen(req, timeout=25) as response:
        payload = json.load(response)
    if not payload.get('success'):
        raise ValueError('TSE catalog did not return a successful response')
    new = summarize(payload['result']['resources'])
    path = ROOT / 'data/extension.json'
    old = json.loads(path.read_text()) if path.exists() else {}
    if old != new:
        path.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n')
        print(f"Second-round BU files: {new['areasPublished']}/{new['areasExpected']} areas")
    else:
        print('No change in official BU catalog')


if __name__ == '__main__':
    main()
