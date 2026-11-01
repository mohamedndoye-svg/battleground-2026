"""Nebraska Secretary of State: electionresults.nebraska.gov (ASP.NET).

The statewide page has an "Export" link that posts the form back and returns an .xlsx with one sheet per
statewide contest: a 'Precincts N of M Reporting' line, then rows of County | votes per candidate, then Total.
The sheet has no party column, so parties come from our race list (`parties` maps surname -> party).
"""
import io, re, urllib.parse, urllib.request, http.cookiejar
import openpyxl
from ..common import UA, log, add_pcts, now_iso, FetchError

URL = 'https://electionresults.nebraska.gov/resultsSW.aspx?type=SW&map=CTY'
SOURCE = 'Nebraska Secretary of State'
KEYS = {'NE-SEN': r'^For United States Senator', 'NE-GOV': r'^For Governor'}


def download():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try:
        h = op.open(urllib.request.Request(URL, headers={'User-Agent': UA}), timeout=60).read().decode('utf-8', 'replace')
        form = {m.group(1): m.group(2) for m in re.finditer(r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', h)}
        form.update({'__EVENTTARGET': 'ctl00$NavLinks$lnkbtnSWExport', '__EVENTARGUMENT': ''})
        r = op.open(urllib.request.Request(URL, data=urllib.parse.urlencode(form).encode(),
                    headers={'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded'}), timeout=90)
        body = r.read()
        log('fetch', source=SOURCE, url=URL + ' (export)', status=r.status, bytes=len(body))
        if not body.startswith(b'PK'):
            raise FetchError('Nebraska export did not return a spreadsheet')
        return body
    except FetchError:
        raise
    except Exception as e:  # network errors, form changes
        log('fetch_error', source=SOURCE, url=URL, error=str(e)[:200])
        raise FetchError(f'{SOURCE}: {e}')


def surname(n):
    return re.sub(r'\s+', ' ', n).strip().split(' and ')[0].split()[-1].lower()


def parse(xlsx_bytes, parties, fetched_at=None):
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True)
    out = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        hdr_i = next((i for i, r in enumerate(rows) if r and r[1] == 'County'), None)
        if hdr_i is None:
            continue
        title = re.sub(r'\s+', ' ', str(rows[hdr_i][0] or '')).strip()
        key = next((k for k, p in KEYS.items() if re.search(p, title)), None)
        if not key:
            continue
        rep = next((re.search(r'Precincts (\d+) of (\d+) Reporting', str(r[0] or '')) for r in rows[:hdr_i] if r and r[0] and 'Precincts' in str(r[0])), None)
        stamp = next((str(r[0]).replace('Downloaded at ', '') for r in rows[:hdr_i] if r and r[0] and 'Downloaded' in str(r[0])), None)
        names = [re.sub(r'\s+', ' ', str(n)).strip() for n in rows[hdr_i][2:] if n]
        counties, totals = [], None
        for r in rows[hdr_i + 1:]:
            if not r or not r[1]:
                continue
            vals = [int(v or 0) for v in r[2:2 + len(names)]]
            if str(r[1]).strip().lower() in ('total', 'totals'):
                totals = vals
                continue
            cands = add_pcts([{'name': n, 'party': parties.get(surname(n)), 'votes': v} for n, v in zip(names, vals)])
            counties.append({'county': str(r[1]).strip(), 'reporting': None, 'total_votes': sum(vals), 'candidates': cands})
        if totals is None:
            totals = [sum(next(c['votes'] for c in co['candidates'] if c['name'] == n) for co in counties) for n in names]
        cands = add_pcts([{'name': n, 'party': parties.get(surname(n)), 'votes': v, 'by_method': {}} for n, v in zip(names, totals)])
        out.append({'state': 'NE', 'key': key, 'office': title, 'candidates': cands, 'total_votes': sum(totals), 'counties': counties,
                    'reporting': {'units': int(rep.group(1)), 'total': int(rep.group(2)), 'unit': 'precincts'} if rep else None,
                    'official': False,
                    'source': {'name': SOURCE, 'kind': 'official', 'url': URL, 'fetched_at': fetched_at or now_iso(), 'as_of': stamp}})
    return out


def poll(parties):
    return parse(download(), parties)
