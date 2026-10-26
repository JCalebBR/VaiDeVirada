#!/usr/bin/env python3
"""Collect official section logs and BUs; retain only reconciled counts."""
import argparse
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import random
import re
import signal
import sqlite3
import threading
import time
import unicodedata
from http.client import HTTPException, HTTPSConnection, RemoteDisconnected
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://resultados.tse.jus.br/oficial/ele2026'
AREAS = 'ac al am ap ba ce df es go ma mg ms mt pa pb pe pi pr rj rn ro rr rs sc se sp to zz'.split()
DAY = '25/10/2026'
USER_AGENT = 'VaiDeVirada research; bounded collector/1.1'
EVENT = 'O voto do eleitor foi computado'
WEST_AM = {'ATALAIA DO NORTE', 'BENJAMIN CONSTANT', 'BOCA DO ACRE', 'EIRUNEPE',
           'ENVIRA', 'GUAJARA', 'IPIXUNA', 'ITAMARATI', 'JUTAI', 'LABREA',
           'PAUINI', 'SAO PAULO DE OLIVENCA', 'TABATINGA'}


STATUSES = ('ok', 'pending', 'aggregated', 'failed', 'excluded', 'unreconciled')
# Bump when enumeration changes so existing checkpoints re-read the catalogs once.
CATALOG_VERSION = '2'


class Excluded(ValueError):
    pass


def ascii_name(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.upper())
                   if not unicodedata.combining(c))


def utc_offset(uf, name):
    if uf == 'zz':
        raise Excluded('timezone_unknown_exterior')
    if uf == 'ac' or (uf == 'am' and ascii_name(name) in WEST_AM):
        return -5
    if uf in ('am', 'ro', 'rr', 'mt', 'ms'):
        return -4
    if uf == 'pe' and ascii_name(name) == 'FERNANDO DE NORONHA':
        return -2
    return -3


def log_texts(raw, depth=0):
    # Extra .jez members are nested log archives; votes from all of them must still match the BU.
    if len(raw) > 2_000_000:
        raise Excluded('log_size')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        nested = [name for name in names if name != 'logd.dat']
        if ('logd.dat' not in names or depth > 1 or not all(n.endswith('.jez') for n in nested)
                or any(info.file_size > 8_000_000 for info in archive.infolist())):
            raise Excluded('log_archive_layout')
        yield archive.read('logd.dat').decode('latin-1')
        for name in nested:
            yield from log_texts(archive.read(name), depth + 1)


def parse_log(raw, offset):
    result = dict(total=0, pre17=0, at17=0, post17to19=0, after19=0)
    last = None
    for text in log_texts(raw):
        previous, equipment = None, set()
        for line in text.splitlines():
            parts = line.split('\t')
            if not line.startswith(DAY):
                continue
            if re.search(r'(ajust|alter|corrig).*(relógio|horário|data/hora)', line, re.I):
                raise Excluded('clock_adjustment')
            if len(parts) != 6 or parts[3:5] != ['VOTA', EVENT]:
                continue
            equipment.add(parts[2])
            if len(equipment) != 1:
                raise Excluded('multiple_equipment')
            local = datetime.strptime(parts[0], '%d/%m/%Y %H:%M:%S')
            brt = local.replace(tzinfo=timezone(timedelta(hours=offset))).astimezone(
                timezone(timedelta(hours=-3)))
            if previous and brt < previous:
                raise Excluded('clock_regression')
            previous = brt
            clock = (brt.hour, brt.minute, brt.second)
            if not (5 <= brt.hour <= 23):
                raise Excluded('clock_outside_expected_day')
            result['total'] += 1
            result['at17'] += clock == (17, 0, 0)
            if clock <= (17, 0, 0):
                result['pre17'] += 1
            elif clock <= (19, 0, 0):
                result['post17to19'] += 1
            else:
                result['after19'] += 1
        if previous and (last is None or previous > last):
            last = previous
    result['lastVoteHourBRT'] = last.hour if last else None
    return result


def der_nodes(raw, depth=0):
    """Read bounded DER TLVs, not signatures or candidate/time associations."""
    if depth > 24:
        raise Excluded('bu_depth')
    nodes, pos = [], 0
    while pos < len(raw):
        if pos + 2 > len(raw):
            raise Excluded('bu_truncated')
        tag, size = raw[pos:pos + 2]
        pos += 2
        if size & 128:
            width = size & 127
            if not 1 <= width <= 4 or pos + width > len(raw):
                raise Excluded('bu_length')
            size = int.from_bytes(raw[pos:pos + width], 'big')
            pos += width
        if pos + size > len(raw):
            raise Excluded('bu_truncated')
        value = raw[pos:pos + size]
        pos += size
        nodes.append((tag, der_nodes(value, depth + 1) if tag & 32 else value))
    return nodes


def integer(node, tag=2):
    if node[0] != tag or not isinstance(node[1], bytes) or not 1 <= len(node[1]) <= 8:
        raise Excluded('bu_integer')
    value = int.from_bytes(node[1], 'big', signed=True)
    if value < 0:
        raise Excluded('bu_negative')
    return value


def children(node, tag=48):
    if node[0] != tag or not isinstance(node[1], list):
        raise Excluded('bu_structure')
    return node[1]


def parse_bu(raw, municipality, zone, section):
    outer = der_nodes(raw)
    if len(outer) != 1:
        raise Excluded('bu_envelope')
    envelope = children(outer[0])
    if len(envelope) != 5 or integer(envelope[1], 10) != 2 or envelope[4][0] != 4:
        raise Excluded('bu_envelope')
    body_nodes = der_nodes(envelope[4][1])
    if len(body_nodes) != 1:
        raise Excluded('bu_body')
    body = children(body_nodes[0])
    if len(body) != 10 or integer(body[1], 10) != 2:
        raise Excluded('bu_version_or_type')
    identity = children(body[3])
    locality = children(identity[0])
    found = (integer(locality[0]), integer(locality[1]), integer(identity[2]))
    if found != (int(municipality), int(zone), int(section)):
        raise Excluded('bu_identity_or_aggregated')
    if body[4][0] != 27 or not body[4][1].startswith(b'20261025T'):
        raise Excluded('bu_date')
    turnout = integer(body[6])
    elections = children(body[8])
    matches = [children(e) for e in elections if integer(children(e)[0]) == 6258]
    if len(matches) != 1:
        raise Excluded('bu_election')
    voting_types = children(matches[0][4])
    if len(voting_types) != 1:
        raise Excluded('bu_multiple_voting_types')
    voting = children(voting_types[0])
    if integer(voting[0], 10) != 1 or integer(voting[1]) != turnout:
        raise Excluded('bu_turnout')
    cargos = children(voting[2])
    if len(cargos) != 1:
        raise Excluded('bu_multiple_cargos')
    cargo = children(cargos[0])
    if integer(cargo[0], 129) != 1:
        raise Excluded('bu_not_president')
    votes = {'13': 0, '22': 0, 'blank': 0, 'null': 0}
    seen = set()
    for item in children(cargo[2]):
        row = children(item)
        kind, count = integer(row[0], 129), integer(row[1], 130)
        if kind == 1:
            candidate = children(row[2], 163)
            number = str(integer(candidate[0]))
            if number not in ('13', '22') or integer(candidate[1]) != int(number):
                raise Excluded('bu_candidate')
            key = number
        elif kind in (2, 3):
            key = {2: 'blank', 3: 'null'}[kind]
        else:
            raise Excluded('bu_vote_kind')
        if key in seen:
            raise Excluded('bu_duplicate_vote_kind')
        seen.add(key)
        votes[key] = count
    if sum(votes.values()) != turnout:
        raise Excluded('bu_vote_sum')
    return {'total': turnout, 'votes': votes}


def reconcile(log, bu):
    if not log['total'] or log['total'] != bu['total']:
        raise Excluded('unreconciled')
    if sum(log[k] for k in ('pre17', 'post17to19', 'after19')) != log['total']:
        raise Excluded('log_partition')
    return {**log, 'votes': bu['votes']}


def enumerate_sections(payload, uf):
    if str(payload.get('cdp')) != '3221' or payload.get('dg') != DAY:
        raise Excluded('config_election_or_date')
    found = {}
    for area in payload['abr']:
        if area['cd'] != uf:
            raise Excluded('config_area')
        for mun in area['mu']:
            for zone in mun['zon']:
                for sec in zone['sec']:
                    ids = (mun['cd'].zfill(5), zone['cd'].zfill(4), sec['ns'].zfill(4))
                    principal = sec.get('nsp')
                    if not all(re.fullmatch(r'\d+', value) for value in ids) or (
                            principal is not None and not re.fullmatch(r'\d+', principal)):
                        raise Excluded('config_identifiers')
                    # An aggregated section ("nsp") has no files; its votes are in the principal's BU.
                    found[(uf, *ids)] = (mun['nm'], principal and principal.zfill(4))
    return [(key, name, principal) for key, (name, principal) in sorted(found.items())]


class Blocked(RuntimeError):
    """The server signalled a block; stop instead of renewing it."""


_connections = threading.local()


def http_get(url, limit):
    # One persistent HTTPS connection per thread and host saves a TLS handshake per file.
    parts = urlsplit(url)
    pool = _connections.__dict__.setdefault('pool', {})
    for retry_stale in (True, False):
        conn = pool.get(parts.netloc)
        if conn is None:
            conn = pool[parts.netloc] = HTTPSConnection(parts.netloc, timeout=30)
        try:
            conn.request('GET', parts.path + (f'?{parts.query}' if parts.query else ''),
                         headers={'User-Agent': USER_AGENT})
            response = conn.getresponse()
            data = response.read(limit + 1)
        except (RemoteDisconnected, BrokenPipeError, ConnectionResetError):
            conn.close()
            pool.pop(parts.netloc, None)
            if retry_stale:
                continue
            raise
        except (OSError, HTTPException):
            conn.close()
            pool.pop(parts.netloc, None)
            raise
        if len(data) > limit or response.will_close:
            conn.close()
            pool.pop(parts.netloc, None)
        if response.status != 200:
            raise HTTPError(url, response.status, response.reason, response.headers, None)
        if len(data) > limit:
            raise Excluded('download_size')
        return data


class Fetcher:
    # TSE: over 100 req/s per IP blocks for 10 min, and retrying during the block renews it.
    BLOCK_PAUSE = 660
    MAX_PAUSES = 3
    MAX_CONSECUTIVE_404 = 25

    def __init__(self, interval=.5, attempts=4, stop=None):
        self.interval, self.attempts = interval, attempts
        self.gap = interval
        self.stop = stop or threading.Event()
        self.lock, self.next_request = threading.Lock(), 0
        self.paused_until, self.pauses, self.not_found = 0, 0, 0

    def _turn(self):
        while True:
            with self.lock:
                now = time.monotonic()
                if now >= self.paused_until:
                    wait = max(0, self.next_request - now)
                    self.next_request = max(now, self.next_request) + self.gap
                    break
                pause = self.paused_until - now
            if self.stop.wait(pause):
                raise Blocked('stopped during block pause')
        time.sleep(wait)

    def _block(self, code):
        with self.lock:
            now = time.monotonic()
            if now >= self.paused_until:
                self.pauses += 1
                if self.pauses > self.MAX_PAUSES:
                    raise Blocked(f'HTTP {code} after {self.MAX_PAUSES} pauses')
                self.paused_until = now + self.BLOCK_PAUSE
                self.gap = max(self.gap * 2, self.interval)
                print(f'HTTP {code}: pausing {self.BLOCK_PAUSE}s, then {1 / self.gap:.0f} req/s', flush=True)

    def __call__(self, url, limit=2_000_000):
        attempt = 0
        while True:
            self._turn()
            try:
                data = http_get(url, limit)
                with self.lock:
                    self.gap = max(self.interval, self.gap * .98)
                    self.pauses = self.not_found = 0
                return data
            except HTTPError as exc:
                if exc.code in (403, 429):
                    self._block(exc.code)
                    continue
                if exc.code == 404:
                    with self.lock:
                        self.not_found += 1
                        if self.not_found >= self.MAX_CONSECUTIVE_404:
                            raise Blocked(f'{self.not_found} consecutive HTTP 404')
                    raise
                if exc.code not in (408, 500, 502, 503, 504) or attempt + 1 >= self.attempts:
                    raise
            except (OSError, HTTPException):
                if attempt + 1 >= self.attempts:
                    raise
            # Transient server errors slow every worker, not only the one that failed.
            with self.lock:
                self.gap = min(10, max(1, self.gap * 2))
            attempt += 1
            if self.stop.wait(min(60, 2 ** attempt + random.random())):
                raise Blocked('stopped during retry')


def collect_one(key, name, fetch):
    uf, mun, zone, section = key
    try:
        offset = utc_offset(uf, name)
        path = f'{BASE}/arquivo-urna/3221/dados/{uf}/{mun}/{zone}/{section}'
        aux = json.loads(fetch(f'{path}/p003221-{uf}-m{mun}-z{zone}-s{section}-aux.json'))
        hashes = aux.get('hashes', [])
        if len(hashes) != 1:
            raise Excluded('multiple_or_missing_sets_contingency')
        record = hashes[0]
        if not re.fullmatch(r'[A-Za-z0-9=]+', record['hash']):
            raise Excluded('invalid_hash')
        files = {}
        for kind in ('log', 'bu'):
            matches = [a['nm'] for a in record['arq'] if a['tp'] == kind]
            if len(matches) != 1 or not re.fullmatch(r'[A-Za-z0-9_.-]+', matches[0]):
                raise Excluded(f'missing_or_multiple_{kind}')
            files[kind] = matches[0]
        bu = parse_bu(fetch(f"{path}/{record['hash']}/{files['bu']}"), mun, zone, section)
        log = parse_log(fetch(f"{path}/{record['hash']}/{files['log']}"), offset)
        return 'ok', reconcile(log, bu)
    except Excluded as exc:
        reason = str(exc)
        return ('unreconciled' if reason == 'unreconciled' else 'excluded'), {'reason': reason}
    except HTTPError as exc:
        return 'failed', {'reason': f'http_{exc.code}'}
    except (ValueError, KeyError, IndexError, TypeError, zipfile.BadZipFile) as exc:
        return 'excluded', {'reason': f'format_{type(exc).__name__}'}
    except (URLError, TimeoutError, OSError) as exc:
        return 'failed', {'reason': type(exc).__name__}


def empty_group():
    return dict(sections=0, total=0, pre17=0, at17=0, post17to19=0, after19=0, lateSquares=0,
                votes={'13': 0, '22': 0, 'blank': 0, 'null': 0},
                estimatedWindow={'13': 0., '22': 0., 'blank': 0., 'null': 0.},
                estimatedRemoved={'13': 0., '22': 0., 'blank': 0., 'null': 0.},
                marginBounds=[0, 0], lastVoteHourBRT={}, lastVoteHourKnownSections=0)


def add_group(group, row):
    group['sections'] += 1
    for field in ('total', 'pre17', 'at17', 'post17to19', 'after19'):
        group[field] += row[field]
    removed = row['post17to19'] + row['after19']
    group['lateSquares'] += removed ** 2
    hour = row.get('lastVoteHourBRT')
    if hour is not None:
        hour = str(hour)
        group['lastVoteHourBRT'][hour] = group['lastVoteHourBRT'].get(hour, 0) + 1
        group['lastVoteHourKnownSections'] += 1
    for candidate, votes in row['votes'].items():
        group['votes'][candidate] += votes
        group['estimatedWindow'][candidate] += row['post17to19'] * votes / row['total']
        group['estimatedRemoved'][candidate] += removed * votes / row['total']
    # Exact feasible bounds on the retained 13-minus-22 margin, not a confidence interval.
    a, b = row['votes']['13'], row['votes']['22']
    other = row['total'] - a - b
    group['marginBounds'][0] += a - b - min(a, removed) + max(0, removed - a - other)
    group['marginBounds'][1] += a - b + min(b, removed) - max(0, removed - b - other)


def summarize(rows):
    national, areas, municipalities = empty_group(), {}, {}
    for uf, mun, payload in rows:
        row = json.loads(payload) if isinstance(payload, str) else payload
        for group in (national, areas.setdefault(uf.upper(), empty_group()),
                      municipalities.setdefault(f'{uf.upper()}/{mun}', empty_group())):
            add_group(group, row)
    for group in [national, *areas.values(), *municipalities.values()]:
        group['estimatedUntil17'] = {
            n: group['votes'][n] - group['estimatedRemoved'][n] for n in ('13', '22')}
        diff = group['estimatedUntil17']['13'] - group['estimatedUntil17']['22']
        group['estimatedWinner'] = ('13' if diff > 0 else '22') if diff else None
        group['estimatedMargin'] = abs(diff)
    # Municipal rows keep only fields needed to audit geographic coverage and allocation.
    municipal_fields = ('sections', 'total', 'pre17', 'post17to19', 'after19', 'estimatedWindow')
    municipalities = {key: {field: group[field] for field in municipal_fields}
                      for key, group in municipalities.items()}
    return {'national': national, 'byUF': areas, 'byMunicipality': municipalities}


Z_999 = 3.29


def confidence(byUF, denominators, official, rate_per_minute=None, now=None):
    """Can removing every vote after 17h flip the final margin? Answer at 99.9% or say when."""
    if not official:
        return None
    a, b = (official['candidates'][n]['votes'] for n in ('13', '22'))
    margin = abs(a - b)
    sampled = sum(group['sections'] for group in byUF.values())
    mean_votes = sum(group['total'] for group in byUF.values()) / sampled if sampled else 0
    estimate = variance = worst = 0
    for uf, counts in denominators.items():
        group = byUF.get(uf) or empty_group()
        n = group['sections']
        unsampled = sum(counts.get(s, 0) for s in ('failed', 'excluded', 'unreconciled'))
        if uf == 'ZZ' or n < 2:
            # No usable sample: count every section as if all of its votes were late.
            worst += (counts.get('pending', 0) + unsampled) * mean_votes
            estimate += group['post17to19'] + group['after19']
            continue
        population = n + counts.get('pending', 0)
        late = group['post17to19'] + group['after19']
        mean = late / n
        spread = max(0, (group['lateSquares'] - n * mean ** 2) / (n - 1))
        estimate += population * mean
        variance += population ** 2 * (1 - n / population) * spread / n
        worst += unsampled * group['total'] / n
    upper = estimate + Z_999 * variance ** .5 + worst
    result = dict(level=.999, margin=margin, lateEstimate=round(estimate), lateUpper=round(upper),
                  worstCaseNonRandom=round(worst), sampleSections=sampled, answered=upper < margin,
                  marginFinal=float(str(official.get('counted', 0)).replace(',', '.')) >= 100,
                  sectionsNeeded=None, etaAnsweredAt=None)
    if result['answered']:
        result['sectionsNeeded'] = sampled
    elif estimate + worst < margin and variance > 0:
        # Sampling error shrinks with 1/sqrt(n); find the n where the bound clears the margin.
        needed = sampled * (Z_999 * variance ** .5 / (margin - estimate - worst)) ** 2
        result['sectionsNeeded'] = round(needed)
        if rate_per_minute:
            eta = (now or datetime.now(timezone.utc)) + timedelta(minutes=(needed - sampled) / rate_per_minute)
            result['etaAnsweredAt'] = eta.isoformat()
    return result


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript("""
      CREATE TABLE IF NOT EXISTS sections (
        uf TEXT, mun TEXT, zone TEXT, section TEXT, name TEXT,
        status TEXT NOT NULL DEFAULT 'pending', payload TEXT,
        PRIMARY KEY (uf, mun, zone, section));
      CREATE TABLE IF NOT EXISTS configs (uf TEXT PRIMARY KEY, status TEXT, detail TEXT);
      CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    return db


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
    tmp.replace(path)


def export(db, output, report, progress=None):
    coverage = dict(db.execute('SELECT status, COUNT(*) FROM sections GROUP BY status'))
    stored = db.execute("SELECT value FROM meta WHERE key='progress'").fetchone()
    if progress is None:
        progress = json.loads(stored[0]) if stored else {'state': 'stopped'}
        if progress.get('state') == 'running':
            progress = {**progress, 'state': 'stopped', 'etaCompleteAt': None}
    if not coverage.get('pending'):
        progress = {**progress, 'state': 'complete', 'etaCompleteAt': None}
    db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', ('progress', json.dumps(progress)))
    db.commit()
    config = {uf: {'status': status, 'detail': detail}
              for uf, status, detail in db.execute('SELECT * FROM configs ORDER BY uf')}
    denominators = {}
    for uf, status, count in db.execute('SELECT uf,status,COUNT(*) FROM sections GROUP BY uf,status'):
        denominators.setdefault(uf.upper(), {})[status] = count
    municipal_coverage = {}
    for uf, mun, total, ok in db.execute(
            "SELECT uf,mun,COUNT(*),SUM(status='ok') FROM sections GROUP BY uf,mun"):
        municipal_coverage[f'{uf.upper()}/{mun}'] = {'total': total, 'ok': ok}
    data = summarize(db.execute("SELECT uf,mun,payload FROM sections WHERE status='ok'"))
    metadata = dict(db.execute("SELECT key,value FROM meta"))
    official = metadata.get('official')
    official = json.loads(official) if official else None
    data.update(schemaVersion=1, generatedAt=datetime.now(timezone.utc).isoformat(),
                election='6258', pleito='3221', coverage={
                    'enumeratedSections': sum(coverage.values()),
                    **{s: coverage.get(s, 0) for s in STATUSES},
                    'areasExpected': 28, 'areasEnumerated': sum(c['status'] == 'ok' for c in config.values()),
                    'denominatorScope': 'published_section_catalog_not_all_installed_sections',
                    'byUF': denominators, 'byMunicipality': municipal_coverage, 'configs': config},
                official=official, nationalCounterfactualWinner=None,
                collectionSource='individual_official_section_files',
                progress=progress,
                sampling={'catalogOrderSections': int(metadata.get('catalogOrderSections', 0))},
                confidence=confidence(data['byUF'], denominators, official,
                                      progress.get('sectionsPerMinute') if progress.get('state') == 'running' else None),
                method={
                    'window': '17:00:00 < conclusão <= 19:00:00 BRT; corte até 17h inclui igualdade',
                    'removed': 'Todos os eventos >17h, inclusive >19h, no contrafactual até 17h',
                    'allocation': 'Hipótese: mesma proporção do BU entre horários, incluindo brancos/nulos; não são escolhas observadas.',
                    'clock': 'Relógio local convertido para UTC-03; fusos por UF e exceções municipais; ZZ excluído.',
                    'scope': 'Somas somente das seções reconciliadas; a projeção nacional fica em confidence.',
                    'sampling': 'Ordem sorteada dentro de cada UF, todas no mesmo percentual; as primeiras sampling.catalogOrderSections seções seguiram a ordem do catálogo.',
                    'confidence': 'Estimativa estratificada por UF dos votos após 17h, limite de 99,9% (z=3,29), mais pior caso para exterior e seções excluídas, com falha ou não reconciliadas.',
                    'bounds': 'Limites combinatórios por seção; não intervalo estatístico.',
                    'legal': 'Janela analítica; não comprova extensão legal geral do horário.'},
                sources={'config': f'{BASE}/arquivo-urna/3221/config/',
                         'official': f'{BASE}/6258/dados/br/br-c0001-e006258-u.json'})
    # A catalog can omit unreceived sections; it cannot certify full national coverage.
    atomic_json(output, data)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open('w') as stream:
        for uf, mun, zone, section, status, payload in db.execute(
                "SELECT uf,mun,zone,section,status,payload FROM sections "
                "WHERE status NOT IN ('ok','pending','aggregated')"):
            stream.write(json.dumps({'section': [uf, mun, zone, section], 'status': status,
                                     'detail': json.loads(payload or '{}')}) + '\n')
    print(json.dumps({'ok': coverage.get('ok', 0), 'pending': coverage.get('pending', 0),
                      'progress': progress, 'confidence': data['confidence']}, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, default=ROOT / '.cache/urna-logs/checkpoint.sqlite')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/extension-analysis.json')
    parser.add_argument('--report', type=Path, default=ROOT / '.cache/urna-logs/absences.jsonl')
    parser.add_argument('--workers', type=int, default=8, choices=range(1, 65))
    parser.add_argument('--interval', type=float, default=.1,
                        help='Minimum gap between requests across all workers; grows on 5xx and blocks')
    parser.add_argument('--refresh-catalog', action='store_true',
                        help='Re-read the 28 section catalogs even when the checkpoint has them')
    parser.add_argument('--retry-failed', action='store_true')
    parser.add_argument('--export-only', action='store_true')
    parser.add_argument('--retry-excluded', action='store_true',
                        help='Recheck conservative exclusions after parser changes')
    parser.add_argument('--seconds', type=int, default=0, help='Stop cleanly after this budget; 0 runs to completion')
    args = parser.parse_args()
    # The TSE allows 100 requests per second per IP; stay below it even with timer jitter.
    if args.interval < 1 / 95 or args.seconds < 0:
        parser.error('interval >= 1/95 s (TSE limit: 100 req/s per IP); seconds >= 0')
    stop = threading.Event()
    db, fetch = connect(args.checkpoint), Fetcher(args.interval, stop=stop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    blocked = None
    if not args.export_only:
        try:
            if args.refresh_catalog or catalog_stale(db):
                load_catalogs(db, fetch)
        except Blocked as exc:
            export(db, args.output, args.report)
            raise SystemExit(f'Stopped: {exc}')
        try:
            raw = json.loads(fetch(f'{BASE}/6258/dados/br/br-c0001-e006258-u.json'))
            votes = {}
            for cargo in raw['carg']:
                if cargo['cd'] == '1':
                    for group in cargo['agr']:
                        for party in group.get('par', []):
                            for cand in party.get('cand', []):
                                if cand['n'] in ('13', '22'):
                                    votes[cand['n']] = {'name': cand['nmu'], 'votes': int(cand['vap'])}
            if raw['ele'] != '6258' or raw['t'] != '2' or set(votes) != {'13', '22'}:
                raise ValueError('Unexpected totalization')
            official = {'candidates': votes, 'counted': raw['s']['pstn'], 'date': raw['dt'], 'time': raw['ht'],
                        'winner': max(votes, key=lambda n: votes[n]['votes'])}
            db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', ('official', json.dumps(official)))
            db.commit()
        except Blocked as exc:
            export(db, args.output, args.report)
            raise SystemExit(f'Stopped: {exc}')
        except Exception as exc:
            print(f'Official totalization unavailable: {type(exc).__name__}', flush=True)
        if args.retry_failed:
            db.execute("UPDATE sections SET status='pending',payload=NULL WHERE status='failed'")
            db.commit()
        if args.retry_excluded:
            db.execute("UPDATE sections SET status='pending',payload=NULL WHERE status='excluded'")
            db.commit()
        export(db, args.output, args.report)
        blocked = collect_pending(db, fetch, args, stop)
    export(db, args.output, args.report)
    db.close()
    if blocked:
        raise SystemExit(f'Stopped: {blocked}')


def catalog_failed(db):
    configs = dict(db.execute('SELECT uf,status FROM configs'))
    return any(configs.get(uf) != 'ok' for uf in AREAS)


def catalog_stale(db):
    version = db.execute("SELECT value FROM meta WHERE key='catalogVersion'").fetchone()
    return catalog_failed(db) or not version or version[0] != CATALOG_VERSION


def load_catalogs(db, fetch):
    for uf in AREAS:
        try:
            payload = json.loads(fetch(f'{BASE}/arquivo-urna/3221/config/{uf}/{uf}-p003221-cs.json', 12_000_000))
            rows = enumerate_sections(payload, uf)
            db.executemany('INSERT OR IGNORE INTO sections(uf,mun,zone,section,name) VALUES(?,?,?,?,?)',
                           [(*key, name) for key, name, _ in rows])
            db.executemany(
                "UPDATE sections SET status='aggregated',payload=? "
                "WHERE uf=? AND mun=? AND zone=? AND section=? AND status!='ok'",
                [(json.dumps({'principal': principal}), *key) for key, _, principal in rows if principal])
            db.execute('INSERT OR REPLACE INTO configs VALUES(?,?,?)', (uf, 'ok', str(len(rows))))
        except Blocked:
            raise
        except Exception as exc:
            db.execute('INSERT OR REPLACE INTO configs VALUES(?,?,?)', (uf, 'failed', type(exc).__name__))
        db.commit()
    if not catalog_failed(db):
        db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', ('catalogVersion', CATALOG_VERSION))
        db.commit()


def progress_snapshot(db, args, finished, state, message=None):
    window = [t for t in finished if t >= time.monotonic() - 600]
    span = (time.monotonic() - window[0]) / 60 if len(window) > 1 else 0
    rate = len(window) / span if span else None
    pending = db.execute("SELECT COUNT(*) FROM sections WHERE status='pending'").fetchone()[0]
    now = datetime.now(timezone.utc)
    eta = now + timedelta(minutes=pending / rate) if rate and pending else None
    return dict(state=state, updatedAt=now.isoformat(), sectionsPerMinute=rate and round(rate, 1),
                targetRequestsPerSecond=round(1 / args.interval, 1) if getattr(args, 'interval', None) else None,
                etaCompleteAt=eta and eta.isoformat(), message=message)


def collect_pending(db, fetch, args, stop, export_every=300):
    """Collect pending sections; return the block reason if the server stopped us."""
    started = last_export = time.monotonic()
    out_of_time = lambda: args.seconds and time.monotonic() - started >= args.seconds
    finished, blocked = deque(maxlen=200_000), None
    # Sections done before random ordering existed followed catalog order; record how many.
    db.execute("""INSERT OR IGNORE INTO meta SELECT 'catalogOrderSections', COUNT(*) FROM sections
                  WHERE status NOT IN ('pending','aggregated')""")
    db.commit()
    export(db, args.output, args.report, progress_snapshot(db, args, finished, 'running'))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        while not stop.is_set() and not out_of_time():
            # Random order inside each UF, every UF at the same fraction done: the processed
            # sections stay a stratified random sample that supports a national estimate.
            chunk = db.execute("""SELECT uf,mun,zone,section,name FROM (
              SELECT *, ROW_NUMBER() OVER (PARTITION BY uf ORDER BY random()) * 1.0
                        / COUNT(*) OVER (PARTITION BY uf) AS position
              FROM sections WHERE status='pending') ORDER BY position LIMIT 2000""").fetchall()
            if not chunk:
                break
            queue, running = iter(chunk), {}
            while True:
                while len(running) < args.workers * 2 and not stop.is_set() and not out_of_time():
                    row = next(queue, None)
                    if row is None:
                        break
                    running[pool.submit(collect_one, row[:4], row[4], fetch)] = row
                if not running:
                    break
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for future in done:
                    row = running.pop(future)
                    try:
                        status, result = future.result()
                    except Blocked as exc:
                        blocked = blocked or str(exc)
                        stop.set()
                        continue
                    db.execute('UPDATE sections SET status=?,payload=? WHERE uf=? AND mun=? AND zone=? AND section=?',
                               (status, json.dumps(result), *row[:4]))
                    finished.append(time.monotonic())
                db.commit()
                if time.monotonic() - last_export >= export_every:
                    export(db, args.output, args.report, progress_snapshot(db, args, finished, 'running'))
                    last_export = time.monotonic()
    state = 'blocked' if blocked else 'stopped'
    export(db, args.output, args.report, progress_snapshot(db, args, finished, state, blocked))
    return blocked


if __name__ == '__main__':
    main()
