"""Clarity / Scytl ENR, used by several states (self-hosted or on results.enr.clarityelections.com).

For a site base like https://electionresults.iowa.gov/IA :
  {base}/elections.json                                   election list (newer ENR UI): EID, ElectionName, Date
  {base}/{eid}/current_ver.txt                            version number; changes on every publish
  {base}/{eid}/{ver}/json/en/summary.json                 statewide totals per contest
  {base}/{eid}/{ver}/reports/detailxml.zip                every contest by county and vote type (detail.xml)
Contest names differ by state, so each state passes a {our_key: regex} map.
"""
import io, re, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from ..common import fetch, fetch_json, add_pcts, party_code, now_iso


def list_elections(base, source, opener=None):
    d = fetch_json(f'{base}/elections.json', source, opener=opener) or []
    out = []
    for e in d:
        try:
            date = datetime.strptime(e['Date'].split()[0], '%m/%d/%Y').date().isoformat()
        except (ValueError, KeyError):
            date = None
        out.append({'id': e['EID'], 'name': e.get('ElectionName'), 'date': date, 'county': e.get('County') or None})
    return out


def find_election(base, source, date, opener=None):
    """Live-feed detection: the statewide election ID for a date, or None if not posted yet."""
    es = [e for e in list_elections(base, source, opener) if e['date'] == date and not e['county']]
    es.sort(key=lambda e: 0 if re.search(r'general', e['name'] or '', re.I) else 1)
    return es[0]['id'] if es else None


def current_version(base, eid, source, opener=None):
    return fetch(f'{base}/{eid}/current_ver.txt', source, opener=opener).decode().strip()


def clean_choice(name, party):
    """South Carolina prefixes names with the party ('REP Alan Wilson'); drop it when it repeats the party field."""
    if party and name.upper().startswith(party.upper() + ' '):
        return name[len(party) + 1:].strip()
    return name


def match_key(name, keymap):
    for k, pat in keymap.items():
        if re.search(pat, name, re.I):
            return k
    return None


def parse_summary(rows, state, keymap, source, url, fetched_at=None, as_of=None):
    fetched_at = fetched_at or now_iso()
    out = []
    for r in rows:
        key = match_key(re.sub(r'\s+', ' ', r.get('C', '')), keymap)
        if not key:
            continue
        cands = [{'name': clean_choice(n, p), 'party': party_code(p) or None, 'votes': v or 0, 'by_method': {}, 'write_in': n.lower().startswith('write')}
                 for n, p, v in zip(r.get('CH') or [], r.get('P') or [], r.get('V') or [])]
        total = sum(c['votes'] for c in cands)
        out.append({'state': state, 'key': key, 'office': r['C'], 'contest_id': r.get('K'),
                    'source': {'name': source, 'kind': 'official', 'url': url, 'fetched_at': fetched_at, 'as_of': as_of},
                    'reporting': {'units': r.get('PR'), 'total': r.get('TP'), 'unit': 'counties reporting'},
                    'total_votes': total, 'candidates': add_pcts(cands, total), 'official': False})
    return out


METHOD = {'election day': 'election_day', 'absentee': 'absentee_mail', 'absentee by mail': 'absentee_mail', 'mail': 'absentee_mail', 'by mail': 'absentee_mail',
          'early': 'advance', 'early voting': 'advance', 'advance': 'advance', 'advance voting': 'advance', 'provisional': 'provisional'}


def parse_detail(zip_bytes, keymap):
    """{our_key: {'counties': [...], 'reporting_precincts': {...}, 'by_method': {cand: {...}}, 'timestamp': str}}"""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    root = ET.fromstring(z.read('detail.xml'))
    ts = (root.findtext('Timestamp') or '').strip()
    res = {}
    for c in root.findall('Contest'):
        key = match_key(re.sub(r'\s+', ' ', c.get('text', '')), keymap)
        if not key:
            continue
        counties = {}
        for pc in c.find('ParticipatingCounties') or []:
            counties[pc.get('name')] = {'county': pc.get('name'), 'reporting': {'units': int(pc.get('precinctsReported') or 0),
                                        'total': int(pc.get('precinctsParticipating') or 0), 'unit': 'precincts'}, 'candidates': []}
        bym = {}
        for ch in c.findall('Choice'):
            name, party = clean_choice(ch.get('text'), ch.get('party')), party_code(ch.get('party'))
            percounty = {}
            bym[name] = {}
            for vt in ch.findall('VoteType'):
                m = METHOD.get(vt.get('name', '').strip().lower(), re.sub(r'\W+', '_', vt.get('name', '').lower()))
                bym[name][m] = bym[name].get(m, 0) + int(vt.get('votes') or 0)
                for co in vt.findall('County'):
                    percounty[co.get('name')] = percounty.get(co.get('name'), 0) + int(co.get('votes') or 0)
            for cn, v in percounty.items():
                counties.setdefault(cn, {'county': cn, 'reporting': None, 'candidates': []})['candidates'].append(
                    {'name': name, 'party': party, 'votes': v})
        for co in counties.values():
            co['total_votes'] = sum(x['votes'] for x in co['candidates'])
            add_pcts(co['candidates'], co['total_votes'])
        res[key] = {'counties': list(counties.values()), 'by_method': bym, 'timestamp': ts,
                    'reporting_precincts': {'units': int(c.get('precinctsReported') or 0), 'total': int(c.get('precinctsParticipating') or 0),
                                            'unit': 'precincts'}}
    return res


def poll(base, eid, state, keymap, source, public_url, prev_version=None, with_detail=True, opener=None):
    ver = current_version(base, eid, source, opener)
    if prev_version and ver == prev_version:
        return None, {'version': ver}
    fetched_at = now_iso()
    rows = fetch_json(f'{base}/{eid}/{ver}/json/en/summary.json', source, opener=opener)
    contests = parse_summary(rows, state, keymap, source, public_url, fetched_at)
    if with_detail and contests:
        det = parse_detail(fetch(f'{base}/{eid}/{ver}/reports/detailxml.zip', source, opener=opener, timeout=120), keymap)
        for c in contests:
            d = det.get(c['key'])
            if d:
                c['counties'] = d['counties']
                c['reporting_precincts'] = d['reporting_precincts']
                c['source']['as_of'] = d['timestamp']
                for cand in c['candidates']:
                    cand['by_method'] = d['by_method'].get(cand['name'], {})
    return contests, {'version': ver}
