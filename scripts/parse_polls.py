"""Parse a Wikipedia race page into polling averages + most recent general-election polls.

Usage (module): parse(html_path, page_url, fetched_at, dem, rep) -> dict
`dem` / `rep` are surnames of the two main nominees (dem may be an independent).
Every number keeps the citation URL Wikipedia attaches to it.
"""
import re, io, warnings
from datetime import datetime
import pandas as pd
from bs4 import BeautifulSoup

warnings.filterwarnings('ignore')
PAID = ('Silver Bulletin', 'Decision Desk HQ')  # aggregators the user asked to exclude as paid; DDHQ kept below if free
EXCLUDE_AGG = ('Silver Bulletin',)
MONTHS = {m: i for i, m in enumerate(['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                                      'September', 'October', 'November', 'December'], 1)}


def ref_map(soup):
    """Map displayed footnote number ('377') -> first external URL in that reference."""
    out = {}
    for sup in soup.select('sup.reference a[href^="#cite_note"]'):
        num = sup.get_text(strip=True).strip('[]')
        if num in out or not num.isdigit():
            continue
        note = soup.find(id=sup['href'][1:])
        if note:
            a = next((x['href'] for x in note.select('a[href^=http]') if 'wikipedia.org' not in x['href']
                      and 'archive.org' not in x['href']), None)
            out[num] = {'url': a, 'text': note.get_text(' ', strip=True)[:240]}
    return out


def end_date(s):
    s = str(s).replace('–', '-').replace('—', '-')
    years = re.findall(r'\d{4}', s)
    tail = s.split('-')[-1].strip()
    m = re.search(r'([A-Z][a-z]+)?\s*(\d{1,2}),?\s*(\d{4})?', tail)
    if not m or not years:
        return None
    mon = m.group(1)
    if not mon:
        mons = re.findall(r'([A-Z][a-z]+)\s+\d', s)
        mon = mons[-1] if mons else None
    if mon not in MONTHS:
        return None
    return datetime(int(years[-1]), MONTHS[mon], int(m.group(2))).date().isoformat()


def clean(v):
    v = str(v)
    return None if v in ('nan', 'NaN') else re.sub(r'\[[^\]]*\]', '', v).strip()


def refs_in(v):
    return re.findall(r'\[(\d+)\]', str(v))


def pct(v):
    m = re.search(r'(\d+(?:\.\d+)?)\s*%', str(v))
    return float(m.group(1)) if m else None


def find_cols(cols, dem, rep):
    # general-election tables tag each candidate with a party, e.g. "Rick Jackson (R)"; primary tables don't
    tagged = [c for c in cols if re.search(r'\((D|R|I|DFL)\)', c)]
    dc = next((c for c in tagged if dem.lower() in c.lower()), None)
    rc = next((c for c in tagged if rep.lower() in c.lower()), None)
    if dc and rc:
        return dc, rc
    # untagged head-to-head: accept only if the two nominees are the table's only candidate columns
    std = ('Source', 'Poll source', 'Date', 'Sample', 'Margin', 'Other', 'Undecided', 'Unnamed', 'Lead')
    names = [c for c in cols if not c.startswith(std)]
    dc = next((c for c in names if dem.lower() in c.lower()), None)
    rc = next((c for c in names if rep.lower() in c.lower()), None)
    return (dc, rc) if dc and rc and len(names) == 2 else (None, None)


def flat(t):
    t.columns = [' '.join(dict.fromkeys(map(str, c))) if isinstance(c, tuple) else str(c) for c in t.columns]
    return t


_CACHE = {}


def load(path):
    # state House pages hold many districts; parse each file once
    if path not in _CACHE:
        html = open(path, encoding='utf-8').read()
        # some pages carry malformed spans like rowspan="2&quot;" that crash the table parser
        html = re.sub(r'''(rowspan|colspan)=(["'])(\d+)[^>]*?\2''', r'\1="\3"', html)
        try:
            tables = [flat(t) for t in pd.read_html(io.StringIO(html), flavor='lxml')]
        except ValueError:
            tables = []
        _CACHE[path] = (ref_map(BeautifulSoup(html, 'lxml')), tables)
    return _CACHE[path]


def parse(path, page_url, fetched_at, dem, rep, extra_cols=()):
    refs, tables = load(path)
    agg_t, poll_t = None, None
    for t in tables:
        cols = list(t.columns)
        dc, rc = find_cols(cols, dem, rep)
        if not (dc and rc):
            continue
        # skip hypotheticals: another D/R/I name in the header that isn't a real ballot candidate
        others = [c for c in cols if re.search(r'\((D|R|I|DFL)\)', c) and c not in (dc, rc)
                  and not any(x.lower() in c.lower() for x in extra_cols)]
        if others or any(c.startswith('RCV round') for c in cols):
            continue
        head = ' '.join(cols)
        if 'Source of poll aggregation' in head and agg_t is None:
            agg_t = (t, dc, rc)
        elif 'Poll source' in head and 'Sample' in head and poll_t is None:
            poll_t = (t, dc, rc)

    def cite(nums):
        for n in nums:
            r = refs.get(n)
            if r and r['url']:
                return r['url']
        return None

    out = {'page': page_url, 'fetched_at': fetched_at, 'averages': [], 'polls': []}
    if agg_t:
        t, dc, rc = agg_t
        for _, r in t.iterrows():
            src_raw = str(r['Source of poll aggregation'])
            src = clean(src_raw)
            if src == 'Average' or any(src.startswith(x) for x in EXCLUDE_AGG):
                continue
            d, rp = pct(r[dc]), pct(r[rc])
            out['averages'].append({
                'source': src, 'dates': clean(r['Dates administered']), 'updated': clean(r['Dates updated']),
                'dem': d, 'rep': rp, 'margin': round(d - rp, 1) if d is not None and rp is not None else None,
                'cite': cite(refs_in(src_raw)),
            })
    if poll_t:
        t, dc, rc = poll_t
        datec = next(c for c in t.columns if c.startswith('Date'))
        samp = next(c for c in t.columns if c.startswith('Sample'))
        moe = next((c for c in t.columns if c.startswith('Margin of error')), None)
        seen = set()
        rows = []
        for _, r in t.iterrows():
            src_raw = str(r[next(c for c in t.columns if c.startswith('Poll source'))])
            src = clean(src_raw)
            d, rp = pct(r[dc]), pct(r[rc])
            if not src or d is None or rp is None or src.lower().startswith('poll source'):
                continue
            key = (src, clean(r[datec]))
            if key in seen:
                continue  # alternate versions of the same poll (e.g. leaners pushed) – keep the first listed
            seen.add(key)
            s = clean(r[samp]) or ''
            pop = re.search(r'\((LV|RV|A|V)\)', s)
            n = re.search(r'([\d,]+)', s)
            rows.append({
                'pollster': re.sub(r'\s*\((R|D)\)\s*$', '', src), 'partisan': (re.search(r'\((R|D)\)\s*$', src) or [None, None])[1],
                'dates': clean(r[datec]), 'end': end_date(clean(r[datec])),
                'n': int(n.group(1).replace(',', '')) if n else None, 'pop': pop.group(1) if pop else None,
                'moe': pct(r[moe]) if moe else None,
                'dem': d, 'rep': rp, 'margin': round(d - rp, 1), 'cite': cite(refs_in(src_raw)),
            })
        rows.sort(key=lambda x: x['end'] or '', reverse=True)
        out['polls'] = rows[:5]
        out['poll_count'] = len(rows)
        # always surface the latest New York Times/Siena poll, even when it isn't among the five most recent
        ts = next((r for r in rows if re.search(r'New York Times|Siena', r['pollster'])), None)
        if ts:
            out['times_siena'] = {**ts, 'in_recent': ts in out['polls']}
    return out


if __name__ == '__main__':
    import sys, json
    print(json.dumps(parse(sys.argv[1], 'x', 'x', sys.argv[2], sys.argv[3]), indent=1))
