"""Georgia Secretary of State results: Enhanced Voting platform at results.sos.ga.gov.

Endpoints (public JSON, no key; Cache-Control: max-age=60):
  /results/public/api/jurisdictions/Georgia                      list of elections (publicElectionId, electionDate)
  /results/public/api/elections/Georgia/{id}                     small: asOf, publishVersionId, isOfficialResults
  /results/public/api/elections/Georgia/{id}/data                every contest, statewide totals + vote-method split
  /results/public/api/elections/Georgia/{id}/data/ballot-item/{ballotItemId}
                                                                 one contest, broken down by all 159 counties
The election-night poller checks the small endpoint and only re-downloads results when publishVersionId/asOf changes.
"""
import re
from ..common import fetch_json, add_pcts, party_code, now_iso

BASE = 'https://results.sos.ga.gov/results/public/api'
PUBLIC = 'https://results.sos.ga.gov/results/public/Georgia/elections/'
SOURCE = 'GA Secretary of State (Enhanced Voting)'

METHOD = {'election day': 'election_day', 'advance voting': 'advance', 'advanced voting': 'advance',
          'absentee by mail': 'absentee_mail', 'provisional': 'provisional'}


def txt(v):
    if isinstance(v, list):
        return next((x.get('text') for x in v if x.get('languageId') in ('en', None)), v[0].get('text') if v else None)
    return v


def contest_key(name):
    """Map a GA contest name to our race key, or None for contests we don't track."""
    n = name.strip()
    pats = [
        (r'^US Senate$', 'GA-SEN'), (r'^Governor$', 'GA-GOV'), (r'^Lieutenant Governor$', 'GA-LTGOV'),
        (r'^Secretary of State$', 'GA-SOS'), (r'^Attorney General$', 'GA-AG'),
        (r'^Commissioner of Agriculture$', 'GA-AGRI'), (r'^Commissioner of Insurance$', 'GA-INS'),
        (r'^Commissioner of Labor$', 'GA-LABOR'), (r'^State School Superintendent$', 'GA-SCHOOL'),
        (r'^(PSC|Public Service Commission)\s*-?\s*District\s*3$', 'GA-PSC3'),
        (r'^(PSC|Public Service Commission)\s*-?\s*District\s*5$', 'GA-PSC5'),
        (r'^President of the US$', 'GA-PRES'),
    ]
    for p, k in pats:
        if re.match(p, n, re.I):
            return k
    m = re.match(r'^US House of Representatives\s*-\s*District\s*(\d+)$', n, re.I)
    if m:
        return f'GA-{int(m.group(1)):02d}'
    m = re.match(r'^(?:Proposed\s+)?(?:Constitutional\s+)?Amendment\s*(?:No\.?|#)?\s*(\d+)\b', n, re.I)
    if m:
        return f'GA-AMEND{m.group(1)}'
    m = re.match(r'^Statewide Referendum Question\s+([A-Z])\b', n, re.I)
    if m:
        return f'GA-REF{m.group(1).upper()}'
    return None


def split_name(raw):
    """'Fani T. Willis (I) (Dem)' -> ('Fani T. Willis', 'D', True); 'Yes' -> ('Yes', None, False).
    Georgia marks incumbents with '(I)' before the party."""
    raw = raw or ''
    inc = bool(re.search(r'\(I\)', raw))
    raw = re.sub(r'\s*\(I\)', '', raw)
    m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', raw)
    return (m.group(1), party_code(m.group(2)), inc) if m else (raw, None, inc)


def options(opts, total=None):
    out = []
    for o in opts or []:
        name, p, inc = split_name(txt(o['name']))
        party = party_code((o.get('party') or {}).get('abbreviation')) or p
        bym = {}
        for g in o.get('groupResults') or []:
            k = METHOD.get((txt(g['groupName']) or '').strip().lower())
            if k:
                bym[k] = (bym.get(k) or 0) + (g.get('voteCount') or 0)
        out.append({'name': name, 'party': party, 'votes': o.get('voteCount') or 0, 'by_method': bym,
                    'incumbent': inc, 'write_in': bool(o.get('isWriteIn'))})
    return add_pcts(out, total)


def list_elections(opener=None):
    j = fetch_json(f'{BASE}/jurisdictions/Georgia', SOURCE, opener=opener)
    return [{'id': e['publicElectionId'], 'date': e['electionDate'], 'name': txt(e['name'])} for e in j.get('elections', [])]


def find_election(date, opener=None):
    """Live-feed detection: returns the election id for `date` (YYYY-MM-DD) once Georgia has published it, else None.
    Prefers a 'general' election over specials held the same day."""
    es = [e for e in list_elections(opener) if e['date'] == date]
    es.sort(key=lambda e: (0 if re.search(r'general', e['name'] or '', re.I) else 1))
    return es[0]['id'] if es else None


def election_meta(eid, opener=None):
    e = fetch_json(f'{BASE}/elections/Georgia/{eid}', SOURCE, opener=opener)
    return {'id': eid, 'as_of': e.get('asOf'), 'version': e.get('publishVersionId') or e.get('asOf'),
            'official': bool(e.get('isOfficialResults')), 'name': txt(e.get('name'))}


def parse_statewide(data, eid, fetched_at=None):
    """Statewide totals for every tracked contest in a /data payload."""
    fetched_at = fetched_at or now_iso()
    el = data['election']
    out = []
    for b in data.get('ballotItems') or []:
        name = txt(b['name'])
        key = contest_key(name)
        if not key:
            continue
        rs = b.get('reportingStatus') or {}
        out.append({
            'state': 'GA', 'key': key, 'office': name, 'ballot_item_id': b['id'],
            'source': {'name': SOURCE, 'kind': 'official', 'url': PUBLIC + eid, 'fetched_at': fetched_at,
                       'as_of': rs.get('asOf') or el.get('asOf')},
            'reporting': {'units': rs.get('reportingUnits'), 'total': rs.get('totalUnits'), 'unit': 'counties fully reported'},
            'total_votes': b.get('voteTotal'),
            'candidates': options((b.get('summaryResults') or {}).get('ballotOptions'), b.get('voteTotal')),
            'official': bool(el.get('isOfficialResults')),
            'contest_type': b.get('contestType'),
        })
    return out


def parse_counties(bi_data):
    """County-level results for one contest from a /data/ballot-item/{id} payload."""
    b = bi_data.get('ballotItemWithBreakdown') or {}
    out = []
    totp = repp = 0
    for r in b.get('breakdownResults') or []:
        loc = r.get('locality') or {}
        cname = re.sub(r'\s+County$', '', txt(loc.get('name')) or '')
        ps = r.get('precinctReportingStatus') or {}
        totp += ps.get('totalUnits') or 0
        repp += ps.get('reportingUnits') or 0
        out.append({'county': cname, 'reporting': {'units': ps.get('reportingUnits'), 'total': ps.get('totalUnits'), 'unit': 'precincts'},
                    'total_votes': r.get('voteTotal'), 'candidates': options(r.get('ballotOptions'), r.get('voteTotal'))})
    return out, {'units': repp, 'total': totp, 'unit': 'precincts'}


def poll(eid, prev_version=None, county_keys=('GA-SEN', 'GA-GOV'), all_counties=False, opener=None):
    """One polling cycle. Returns (contests or None if unchanged, meta)."""
    meta = election_meta(eid, opener)
    if prev_version and meta['version'] == prev_version:
        return None, meta
    fetched_at = now_iso()
    data = fetch_json(f'{BASE}/elections/Georgia/{eid}/data', SOURCE, opener=opener, timeout=120)
    contests = parse_statewide(data, eid, fetched_at)
    for c in contests:
        if all_counties or c['key'] in county_keys:
            bi = fetch_json(f"{BASE}/elections/Georgia/{eid}/data/ballot-item/{c['ballot_item_id']}", SOURCE, opener=opener, timeout=120)
            c['counties'], c['reporting_precincts'] = parse_counties(bi)
    return contests, meta
