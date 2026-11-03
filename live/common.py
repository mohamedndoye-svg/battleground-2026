"""Shared plumbing for the election-night poller: HTTP with backoff, fetch log, normalized result records.

Every feed parser returns a list of `contest` dicts in one shape, so the rest of the system never
needs to know which state platform a number came from:

    {
      "state": "GA", "key": "GA-GOV", "office": "Governor", "district": None,
      "source": {"name": "GA Secretary of State (Enhanced Voting)", "kind": "official",
                 "url": ..., "fetched_at": ISO, "as_of": ISO or None},
      "reporting": {"units": 2650, "total": 2651, "unit": "precincts"},
      "total_votes": 1234567,
      "candidates": [{"name": ..., "party": "D", "votes": 1, "pct": 50.1,
                      "by_method": {"election_day": 1, "advance": 1, "absentee_mail": 1, "provisional": 1}}],
      "counties": [{"county": "Gwinnett", "reporting": {...}, "total_votes": 1, "candidates": [...]}],
      "official": False,   # True only when the source marks results as certified/official
    }
"""
import gzip, json, os, random, re, time, urllib.request, urllib.error
from datetime import datetime, timezone

UA = 'BattlegroundTracker/1.0 (election-night dashboard; polls public results feeds every few minutes)'
LOG_PATH = os.environ.get('BG_LOG', os.path.join(os.path.dirname(__file__), '..', 'logs', 'fetch.jsonl'))


CLOCK = time.time   # replaced by the mock election night to run on simulated time
TRIES = int(os.environ.get('BG_FETCH_TRIES', '3'))


def now_iso():
    return datetime.fromtimestamp(CLOCK(), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def log(event, **kw):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'ts': now_iso(), 'event': event, **kw}, ensure_ascii=False) + '\n')


class FetchError(Exception):
    pass


def fetch(url, source, timeout=60, tries=None, base_delay=2.0, opener=None):
    """GET with exponential backoff (2s, 4s, 8s + jitter). Logs every attempt. Returns bytes."""
    opener = opener or urllib.request.urlopen
    last = None
    tries = tries or TRIES
    for i in range(tries):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
                                                       'Accept-Encoding': 'gzip'})
            with opener(req, timeout=timeout) as r:
                body = r.read()
                status = getattr(r, 'status', 200)
            if body[:2] == b'\x1f\x8b':  # some servers (Clarity) gzip regardless of what was asked
                body = gzip.decompress(body)
            log('fetch', source=source, url=url, status=status, bytes=len(body), ms=int((time.time() - t0) * 1000), attempt=i + 1)
            if status == 204:
                return b''
            if status == 202 and not body:
                # CloudFront/AWS WAF answers a bot challenge with an empty 202; retrying won't pass it
                log('blocked', source=source, url=url, status=202)
                raise FetchError(f'{source}: blocked by a bot check (HTTP 202 with no content) from this server')
            return body
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            code = getattr(e, 'code', None)
            last = e
            log('fetch_error', source=source, url=url, status=code, error=str(e)[:200], attempt=i + 1)
            if code in (400, 401, 403, 404, 410):
                break  # not transient: retrying won't help
            if code == 429:
                time.sleep(30)
            elif i < tries - 1:
                time.sleep(base_delay * (2 ** i) + random.uniform(0, 1))
    raise FetchError(f'{source}: {url}: {last}')


def fetch_json(url, source, **kw):
    body = fetch(url, source, **kw)
    return json.loads(body) if body else None


def write_json(path, obj):
    """Atomic write so the page never reads a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)


PARTY = {'rep': 'R', 'republican': 'R', 'dem': 'D', 'democratic': 'D', 'democrat': 'D', 'dfl': 'D', 'lib': 'L', 'libertarian': 'L',
         'grn': 'G', 'green': 'G', 'ind': 'I', 'independent': 'I', 'np': 'NP', 'nonpartisan': 'NP'}


def party_code(s):
    if not s:
        return None
    return PARTY.get(s.strip().lower().rstrip('.'), s.strip())


def add_pcts(cands, total=None):
    total = total if total else sum(c['votes'] or 0 for c in cands)
    for c in cands:
        c['pct'] = round(100 * c['votes'] / total, 2) if total else None
    return cands


def lead_margin(cands):
    """(leader, runner_up, margin_pct_points) from candidates sorted by votes."""
    s = sorted(cands, key=lambda c: -(c['votes'] or 0))
    if len(s) < 2 or not s[0]['votes']:
        return (s[0] if s else None), None, None
    return s[0], s[1], round((s[0]['pct'] or 0) - (s[1]['pct'] or 0), 3)


def norm_name(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s.lower())).strip()
