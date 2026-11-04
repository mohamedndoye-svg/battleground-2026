"""States that publish plain results files.

Minnesota  https://electionresultsfiles.sos.mn.gov/{YYYYMMDD}/{file}.txt   semicolon-delimited, statewide rows
           fields: state;county;precinct;office_id;office;district;cand_id;name;suffix;incumbent;party;
                   precincts_reporting;precincts_total;votes;pct;contest_total
North Carolina  https://er.ncsbe.gov/enr/{YYYYMMDD}/data/results_0.txt  JSON list, one row per candidate, statewide,
           with vote-method splits: evc (Election Day), ovc (one-stop early), avc (absentee by mail), pvc (provisional)
Florida    https://flelectionfiles.floridados.gov/enightfilespublic/{YYYYMMDD}_ElecResultsFL.txt
           tab-delimited, one row per candidate per county, with precincts reporting per county
All three post the file for an upcoming election ahead of time (with zero votes), so "feed is live" means
"file exists and has nonzero votes".
"""
import csv, io, json, re
from ..common import fetch, add_pcts, party_code, now_iso

# ---------------------------------------------------------------- Minnesota
MN_SOURCE = 'Minnesota Secretary of State'
MN_FILES = {'MN-SEN': 'ussenate'}


def mn_url(date, file):
    return f'https://electionresultsfiles.sos.mn.gov/{date.replace("-", "")}/{file}.txt'


def parse_mn(text, key, url, fetched_at=None):
    cands, rep = [], None
    for row in csv.reader(io.StringIO(text), delimiter=';'):
        if len(row) < 16:
            continue
        cands.append({'name': row[7], 'party': party_code(row[10]) or None, 'votes': int(row[13] or 0), 'by_method': {},
                      'incumbent': bool(row[9].strip()), 'write_in': 'write' in row[7].lower()})
        rep = {'units': int(row[11] or 0), 'total': int(row[12] or 0), 'unit': 'precincts'}
        office = row[4]
    if not cands:
        return []
    total = sum(c['votes'] for c in cands)
    return [{'state': 'MN', 'key': key, 'office': office, 'reporting': rep, 'total_votes': total,
             'candidates': add_pcts(cands, total), 'official': False,
             'source': {'name': MN_SOURCE, 'kind': 'official', 'url': url, 'fetched_at': fetched_at or now_iso(), 'as_of': None}}]


def poll_mn(date, opener=None):
    out = []
    for key, f in MN_FILES.items():
        url = mn_url(date, f)
        out += parse_mn(fetch(url, MN_SOURCE, opener=opener).decode('utf-8', 'replace'), key, url)
    return out


# ---------------------------------------------------------------- North Carolina
NC_SOURCE = 'NC State Board of Elections'
NC_KEYS = {'NC-SEN': r'^US SENATE\b', 'NC-PRES': r'^US PRESIDENT\b', 'NC-GOV': r'^NC GOVERNOR\b'}
NC_METHOD = {'evc': 'election_day', 'ovc': 'advance', 'avc': 'absentee_mail', 'pvc': 'provisional'}


def nc_url(date):
    return f'https://er.ncsbe.gov/enr/{date.replace("-", "")}/data/results_0.txt'


def parse_nc(rows, url, fetched_at=None):
    by = {}
    for r in rows:
        key = next((k for k, p in NC_KEYS.items() if re.search(p, r.get('cnm', ''))), None)
        if not key:
            continue
        c = by.setdefault(key, {'state': 'NC', 'key': key, 'office': r['cnm'], 'candidates': [], 'official': False,
                                'reporting': {'units': int(r.get('prt') or 0), 'total': int(r.get('ptl') or 0), 'unit': 'precincts'},
                                'source': {'name': NC_SOURCE, 'kind': 'official', 'url': 'https://er.ncsbe.gov/', 'fetched_at': fetched_at or now_iso(), 'as_of': None}})
        c['candidates'].append({'name': r['bnm'], 'party': party_code(r.get('pty')) or None, 'votes': int(r.get('vct') or 0),
                                'by_method': {m: int(r.get(f) or 0) for f, m in NC_METHOD.items()}, 'write_in': 'write' in r['bnm'].lower()})
    for c in by.values():
        c['total_votes'] = sum(x['votes'] for x in c['candidates'])
        add_pcts(c['candidates'], c['total_votes'])
    return list(by.values())


def poll_nc(date, opener=None):
    url = nc_url(date)
    return parse_nc(json.loads(fetch(url, NC_SOURCE, opener=opener)), url)


# ---------------------------------------------------------------- Florida
FL_SOURCE = 'Florida Division of Elections'
FL_KEYS = {'FL-GOV': r'^Governor\b', 'FL-PRES': r'^President and Vice President$'}


def fl_url(date):
    return f'https://flelectionfiles.floridados.gov/enightfilespublic/{date.replace("-", "")}_ElecResultsFL.txt'


def parse_fl(text, url, fetched_at=None):
    rd = csv.DictReader(io.StringIO(text), delimiter='\t')
    by = {}
    for r in rd:
        key = next((k for k, p in FL_KEYS.items() if re.search(p, (r.get('RaceName') or '').strip())), None)
        if not key:
            continue
        c = by.setdefault(key, {'state': 'FL', 'key': key, 'office': r['RaceName'].strip(), 'official': False, '_c': {}, '_k': {},
                                'source': {'name': FL_SOURCE, 'kind': 'official', 'url': url, 'fetched_at': fetched_at or now_iso(), 'as_of': None}})
        last, first = (r.get('CanNameLast') or '').strip(), (r.get('CanNameFirst') or '').strip()
        # ticket races (President/VP, Governor/Lt. Governor) mark the middle-name field with "/" and store
        # the top of the ticket's surname in CanNameFirst and the running mate's in CanNameLast
        ticket = '/' in (r.get('CanNameMiddle') or '')
        name = first if ticket else f'{first} {last}'.strip()
        party = party_code(r.get('PartyCode'))
        v = int((r.get('CanVotes') or '0').strip() or 0)
        cand = c['_c'].setdefault(name, {'name': name, 'party': party, 'votes': 0, 'by_method': {}})
        cand['votes'] += v
        co = c['_k'].setdefault(r['CountyName'].strip(), {'county': r['CountyName'].strip(), 'candidates': [],
                                'reporting': {'units': int(r.get('PrecinctsReporting') or 0), 'total': int(r.get('Precincts') or 0), 'unit': 'precincts'}})
        co['candidates'].append({'name': name, 'party': party, 'votes': v})
    out = []
    for c in by.values():
        c['candidates'] = list(c.pop('_c').values())
        c['counties'] = list(c.pop('_k').values())
        c['total_votes'] = sum(x['votes'] for x in c['candidates'])
        add_pcts(c['candidates'], c['total_votes'])
        for co in c['counties']:
            co['total_votes'] = sum(x['votes'] for x in co['candidates'])
            add_pcts(co['candidates'], co['total_votes'])
        u = sum(co['reporting']['units'] for co in c['counties']); t = sum(co['reporting']['total'] for co in c['counties'])
        c['reporting'] = {'units': u, 'total': t, 'unit': 'precincts'}
        out.append(c)
    return out


FL_WATCH = 'https://floridaelectionwatch.gov/StateOffices/Governor'


def parse_fl_watch(html, url, fetched_at=None):
    """Florida Election Watch contest page: a table of Candidate | Party | Votes | %. It gives no precinct counts."""
    from bs4 import BeautifulSoup
    rows = BeautifulSoup(html, 'lxml').select('tr.grid-row')
    cands = []
    for tr in rows:
        td = [x.get_text(' ', strip=True) for x in tr.find_all('td')]
        if len(td) < 3 or not re.sub(r'\D', '', td[2]):
            continue
        name = td[0].split(' and ')[0].strip()  # ticket: keep the top of the ticket
        cands.append({'name': name, 'party': party_code(td[1]) or None, 'votes': int(re.sub(r'\D', '', td[2])), 'by_method': {},
                      'write_in': td[1].strip().upper() == 'WRI'})
    if not cands:
        return []
    total = sum(c['votes'] for c in cands)
    return [{'state': 'FL', 'key': 'FL-GOV', 'office': 'Governor and Lieutenant Governor', 'candidates': add_pcts(cands, total),
             'total_votes': total, 'reporting': None, 'official': False,
             'source': {'name': 'Florida Election Watch (Florida Dept. of State)', 'kind': 'official', 'url': url,
                        'fetched_at': fetched_at or now_iso(), 'as_of': None}}]


def poll_fl(date, opener=None):
    """The election-night file is the primary source; in 2026 the state stopped updating it on election night,
    so fall back to the Election Watch page whenever the file still shows no votes."""
    url = fl_url(date)
    res = parse_fl(fetch(url, FL_SOURCE, opener=opener, timeout=120).decode('utf-8', 'replace'), url)
    if not any(c['total_votes'] for c in res):
        watch = parse_fl_watch(fetch(FL_WATCH, FL_SOURCE, opener=opener).decode('utf-8', 'replace'), FL_WATCH)
        if watch and watch[0]['total_votes']:
            return watch
    return res
