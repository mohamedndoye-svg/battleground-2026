"""Mock election night: runs the real poller and combiner on a simulated clock from 6:30 PM to 2:00 AM ET.

Georgia is served by a local HTTP server that imitates the Secretary of State's Enhanced Voting API, so Georgia's
parser, live-feed detection, version checks, backoff and health colours all run for real. The other six feed states
are simulated one level up (their parsers are already tested against real files in test_feeds.py).

Scripted events
  * staggered poll closings (GA/SC 7:00, NC 7:30, FL 8:00, IA/MN/NE 9:00 ET); no votes before a state closes
  * slow counts: Gwinnett and Fulton report much later than the rest of Georgia
  * Georgia feed outage 8:30-9:10 PM (HTTP 503) -> yellow, then red + stale, then recovery
  * source disagreement: a secondary value for North Carolina 3% off the official count
  * recount-margin race: Minnesota Senate finishes 0.2 points apart
  * a Georgia race finishing at 49.6%: Governor leader ends at 49.6% with every precinct in

Usage: python3 -m live.mock [--out /tmp/mock]     -> writes timeline.json, live.json snapshots and a pass/fail report
"""
import argparse, json, os, threading, time, math
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import common, poller, sources as S
from .feeds import ga

ET = timezone(timedelta(hours=-5))
T0 = datetime(2026, 11, 3, 18, 30, tzinfo=ET).timestamp()
T_END = datetime(2026, 11, 4, 2, 0, tzinfo=ET).timestamp()
SIM = {'t': T0}
OUTAGE = (datetime(2026, 11, 3, 20, 30, tzinfo=ET).timestamp(), datetime(2026, 11, 3, 21, 10, tzinfo=ET).timestamp())
HERE = os.path.dirname(__file__)


def clock():
    return SIM['t']


def et_hours(t):
    d = datetime.fromtimestamp(t, ET)
    return d.hour + d.minute / 60 + (24 if d.day == 4 else 0)


def progress(t, close_h, speed=1.0):
    """Share of precincts reported: 0 before close, then an S-curve over ~4 hours (scaled by speed)."""
    h = et_hours(t) - close_h
    if h <= 0:
        return 0.0
    return min(1.0, 1 / (1 + math.exp(-(h * speed - 2.0) * 1.8)) * 1.02)


# ---------------------------------------------------------------- Georgia mock (Enhanced Voting shapes)
GAP = json.load(open(os.path.join(HERE, '..', 'data', 'raw', 'ga_county_pres2024.json')))
COUNTIES = GAP['counties']
SLOW = {'Gwinnett': 0.45, 'Fulton': 0.55}
GA_CONTESTS = [  # name, D, R, D share shift vs 2024 two-party, write-in share at finish
    ('US Senate', 'Jon Ossoff', 'Mike Collins', 0.040, 0.002),
    ('Governor', 'Keisha Lance Bottoms', 'Rick Jackson', -0.0015, 0.009),
    ('Lieutenant Governor', 'Josh McLaurin', 'Greg Dolezal', 0.0, 0.002),
    ('Proposed Constitutional Amendment 1', 'Yes', 'No', None, 0),
]


def calibrate_governor():
    """Find the uniform shift that makes Jackson (R) finish at 49.6% with 0.9% write-ins."""
    lo, hi = -0.2, 0.2
    for _ in range(60):
        mid = (lo + hi) / 2
        rows = ga_counts(T_END, ('Governor', 'D', 'R', mid, 0.009))
        tot = sum(r[2] for r in rows)
        rshare = sum(r[4] for r in rows) / tot
        lo, hi = (mid, hi) if rshare > 0.496 else (lo, mid)
    GA_CONTESTS[1] = ('Governor', 'Keisha Lance Bottoms', 'Rick Jackson', (lo + hi) / 2, 0.009)


def ga_counts(t, contest):
    name, dn, rn, shift, wi = contest
    rows = []
    for cty, info in COUNTIES.items():
        p = progress(t, 19, SLOW.get(cty, 1.0))
        votes = int(info['total_votes'] * 0.72 * p)  # midterm turnout ~72% of 2024
        if shift is None:
            dshare, rshare = 0.58, 0.42
        else:
            d2024 = (1 - info['margin_r'] / 100) / 2
            dshare = max(0.05, min(0.95, d2024 + shift)) * (1 - wi)
            rshare = (1 - wi) - dshare
        rows.append((cty, p, votes, round(votes * dshare), round(votes * rshare), votes - round(votes * dshare) - round(votes * rshare)))
    return rows


def opt(name, party, votes, groups):
    return {'id': name, 'name': [{'languageId': 'en', 'text': f'{name} ({party})' if party else name}],
            'voteCount': votes, 'party': {'abbreviation': party} if party else None, 'isWriteIn': party is None and name.startswith('Write'),
            'groupResults': [{'groupName': [{'languageId': 'en', 'text': g}], 'voteCount': v} for g, v in groups]}


def split(v):
    ed = int(v * 0.42); adv = int(v * 0.50); ab = int(v * 0.07)
    return [('Election Day', ed), ('Advance Voting', adv), ('Absentee by Mail', ab), ('Provisional', v - ed - adv - ab)]


def ga_payload(path, t):
    published = t >= datetime(2026, 11, 3, 18, 55, tzinfo=ET).timestamp()
    if path.endswith('/jurisdictions/Georgia'):
        es = [{'publicElectionId': '2024NovGen', 'electionDate': '2024-11-05', 'name': [{'languageId': 'en', 'text': 'November General Election'}]}]
        if published:
            es.insert(0, {'publicElectionId': '11032026GeneralElection', 'electionDate': '2026-11-03', 'name': [{'languageId': 'en', 'text': 'November 3rd, 2026 General Election'}]})
        return {'elections': es}
    version = str(int((t - T0) // 600))  # results republished every 10 simulated minutes
    if path.endswith('/elections/Georgia/11032026GeneralElection'):
        return {'asOf': datetime.fromtimestamp(t, timezone.utc).isoformat(), 'publishVersionId': version, 'isOfficialResults': False,
                'name': [{'languageId': 'en', 'text': 'November 3rd, 2026 General Election'}]}
    items, breakdowns = [], {}
    for i, c in enumerate(GA_CONTESTS):
        rows = ga_counts(t, c)
        D, R, W = sum(r[3] for r in rows), sum(r[4] for r in rows), sum(r[5] for r in rows)
        dp, rp = ('Dem', 'Rep') if c[3] is not None else (None, None)
        opts = [opt(c[1], dp, D, split(D)), opt(c[2], rp, R, split(R))] + ([opt('Write-in', None, W, split(W))] if W else [])
        fully = sum(1 for r in rows if r[1] >= 1)
        items.append({'id': f'bi{i}', 'name': [{'languageId': 'en', 'text': c[0]}], 'contestType': 'Candidate', 'voteTotal': D + R + W,
                      'reportingStatus': {'reportingUnits': fully, 'totalUnits': 159, 'asOf': datetime.fromtimestamp(t, timezone.utc).isoformat()},
                      'summaryResults': {'ballotOptions': opts}})
        breakdowns[f'bi{i}'] = [{'locality': {'name': [{'languageId': 'en', 'text': f'{cty} County'}]}, 'voteTotal': v,
                                 'precinctReportingStatus': {'reportingUnits': round(20 * p), 'totalUnits': 20},
                                 'ballotOptions': [opt(c[1], dp, d, split(d)), opt(c[2], rp, r, split(r))] + ([opt('Write-in', None, w, split(w))] if w else [])}
                                for cty, p, v, d, r, w in rows]
    if '/data/ballot-item/' in path:
        bid = path.rsplit('/', 1)[1]
        return {'ballotItemWithBreakdown': {'breakdownResults': breakdowns[bid]}}
    if path.endswith('/data'):
        return {'election': {'asOf': datetime.fromtimestamp(t, timezone.utc).isoformat(), 'isOfficialResults': False}, 'ballotItems': items}
    return None


class GAHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        t = clock()
        if OUTAGE[0] <= t < OUTAGE[1]:
            self.send_response(503); self.end_headers(); return
        body = ga_payload(self.path.split('?')[0], t)
        if body is None:
            self.send_response(404); self.end_headers(); return
        b = json.dumps(body).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(b)


# ---------------------------------------------------------------- other states, simulated at the source level
def contest(state, key, office, close_h, cands, t, units_total, final_margin=None):
    p = progress(t, close_h)
    total = int(sum(v for _, _, v in cands) * p)
    base = sum(v for _, _, v in cands)
    out = [{'name': n, 'party': pt, 'votes': int(v / base * total), 'by_method': {}} for n, pt, v in cands]
    common.add_pcts(out, sum(c['votes'] for c in out))
    return {'state': state, 'key': key, 'office': office, 'candidates': out, 'total_votes': sum(c['votes'] for c in out), 'official': False,
            'reporting': {'units': round(units_total * min(p, 1)), 'total': units_total, 'unit': 'precincts'},
            'source': {'name': f'{state} official (simulated)', 'kind': 'official', 'url': 'mock://' + state, 'fetched_at': common.now_iso(), 'as_of': None}}


SIMULATED = {
    'sc': lambda t: [contest('SC', 'SC-SEN', 'U.S. Senate', 19, [('Darline Graham', 'R', 760000), ('Annie Andrews', 'D', 735000)], t, 2300)],
    'nc': lambda t: [contest('NC', 'NC-SEN', 'US SENATE', 19.5, [('Roy Cooper', 'D', 1_950_000), ('Michael Whatley', 'R', 1_760_000)], t, 2626)],
    'fl': lambda t: [contest('FL', 'FL-GOV', 'Governor', 20, [('Byron Donalds', 'R', 3_900_000), ('David Jolly', 'D', 3_500_000)], t, 5626)],
    'ia': lambda t: [contest('IA', 'IA-SEN', 'United States Senator', 21, [('Ashley Hinson', 'R', 640_000), ('Josh Turek', 'D', 630_000)], t, 1666),
                     contest('IA', 'IA-GOV', 'Governor', 21, [('Rob Sand', 'D', 680_000), ('Zach Lahn', 'R', 600_000)], t, 1666)],
    # recount-margin race: Flanagan 50.1 / Tafoya 49.9 -> 0.2-point margin, inside Minnesota's 0.25% request threshold
    'mn': lambda t: [contest('MN', 'MN-SEN', 'U.S. Senator', 21, [('Peggy Flanagan', 'D', 1_402_800), ('Michele Tafoya', 'R', 1_397_200)], t, 4105)],
    'ne': lambda t: [contest('NE', 'NE-SEN', 'For United States Senator', 21, [('Pete Ricketts', 'R', 400_000), ('Dan Osborn', 'I', 380_000)], t, 1322)],
}


def patch_sources():
    for cls in (S.ClaritySource, S.FileSource, S.NESource):
        def p(self, st, _c=cls):
            res = SIMULATED[self.id](clock())
            ver = str([c['total_votes'] for c in res])
            return (None if st.get('version') == ver else res), ver
        cls.poll = p


def run(out):
    os.makedirs(out, exist_ok=True)
    for f in ('state.json', 'live.json', 'secondary.json'):
        try:
            os.remove(os.path.join(out, f))
        except OSError:
            pass
    srv = ThreadingHTTPServer(('127.0.0.1', 0), GAHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ['BG_GA_BASE'] = f'http://127.0.0.1:{srv.server_address[1]}/results/public/api'
    os.environ['BG_LOG'] = os.path.join(out, 'fetch.jsonl')
    common.LOG_PATH = os.environ['BG_LOG']
    common.CLOCK = clock
    os.environ['BG_NO_CALLS'] = '1'  # the mock checks that nothing is called; keep tonight's real calls out of it
    common.TRIES = 1
    patch_sources()
    calibrate_governor()
    # secondary source for the disagreement scenario: NC count 3% higher than official for Cooper
    timeline = []

    def step_sleep(sec):
        SIM['t'] += 600  # every loop iteration advances 10 simulated minutes
        live = json.load(open(os.path.join(out, 'live.json')))
        if et_hours(SIM['t']) >= 21.5 and not os.path.exists(os.path.join(out, 'secondary.json')):
            nc = live['races']['S-NC']['result']
            if nc:
                sec = {'races': {'S-NC': {'source': 'Example outlet (mock)', 'url': 'mock://outlet', 'extracted_at': common.now_iso(),
                                          'candidates': [{'name': c['name'], 'votes': int(c['votes'] * (1.03 if 'Cooper' in c['name'] else 1))} for c in nc['candidates']]}}}
                json.dump(sec, open(os.path.join(out, 'secondary.json'), 'w'))
        snap(live)

    def snap(live):
        g = live['races'].get('G-Georgia', {})
        gsen = next((c for c in live['ga']['contests'] if c['key'] == 'GA-SEN'), None)
        share = lambda co: co['reporting']['units'] / co['reporting']['total'] if co and co.get('reporting') and co['reporting']['total'] else 0
        gw = next((co for co in (gsen or {}).get('counties') or [] if co['county'] == 'Gwinnett'), None)
        cos = sorted(share(co) for co in (gsen or {}).get('counties') or [])
        timeline.append({'et': datetime.fromtimestamp(SIM['t'] - 600, ET).strftime('%H:%M'), 'h': round(et_hours(SIM['t'] - 600), 2),
                         'ia_votes': (live['races']['S-IA'].get('total_votes') or 0),
                         'any_votes': sum((r.get('total_votes') or 0) for r in live['races'].values()),
                         'gw_share': share(gw), 'ga_median_share': cos[len(cos) // 2] if cos else 0,
                         'health': {s['id']: s['health'] for s in live['sources'] if s['kind'] == 'official'},
                         'ga_status': next(s['status'] for s in live['sources'] if s['id'] == 'ga'),
                         'ga_stale': live['races']['S-GA']['stale'],
                         'ga_sen': (live['races']['S-GA'].get('reporting'), live['races']['S-GA'].get('margin_dr')),
                         'ga_gov_leader_pct': (g.get('flags') or {}).get('majority', {}) and g['flags']['majority'].get('leader_pct'),
                         'nc_discrepancy': bool(live['races']['S-NC'].get('discrepancy'))})

    sources = S.build_sources()
    for s in sources:
        s.interval = 600 if s.id != 'ga' else 300
    poller.run(out, duration_min=(T_END - T0) / 60, sleep=step_sleep, clock=clock)
    srv.shutdown()
    live = json.load(open(os.path.join(out, 'live.json')))
    json.dump(timeline, open(os.path.join(out, 'timeline.json'), 'w'), indent=1)
    return live, timeline


def checks(live, timeline):
    R = live['races']
    gov = R['G-Georgia']
    ga_gov = next(c for c in live['ga']['contests'] if c['key'] == 'GA-GOV')
    hs = [t['health']['ga'] for t in timeline]
    before = [t for t in timeline if t['h'] < 19]
    mid = next(t for t in timeline if t['h'] >= 22)
    return [
        ('Staggered closings: no votes anywhere before 7 PM', all(t['any_votes'] == 0 for t in before)),
        ('Staggered closings: Georgia feed detected only after it was published', any(t['ga_status'] == 'not_live' for t in before) and timeline[-1]['ga_status'] == 'ok'),
        ('Staggered closings: Iowa has no votes until its 9 PM close', all(t['ia_votes'] == 0 for t in timeline if t['h'] < 21) and timeline[-1]['ia_votes'] > 0),
        ('Slow counts: at 10 PM Gwinnett is well behind the median county', mid['gw_share'] < mid['ga_median_share'] - 0.25),
        ('Feed outage: Georgia goes yellow then red during the outage', 'yellow' in hs and 'red' in hs),
        ('Feed outage: Georgia data marked stale during the outage', any(t['ga_stale'] for t in timeline if 20.8 <= t['h'] <= 21.1)),
        ('Freshness: Georgia data not marked stale when the feed is healthy', not any(t['ga_stale'] for t in timeline if t['h'] >= 21.5)),
        ('Feed outage: other sources stay green during Georgia outage', all(t['health']['nc'] == 'green' for t in timeline if 20.6 <= t['h'] <= 21.0)),
        ('Feed outage: Georgia recovers to green after the outage', hs[-1] == 'green'),
        ('Source disagreement: NC shows official number with discrepancy flag', bool(R['S-NC'].get('discrepancy')) and R['S-NC']['source']['kind'] == 'official'),
        ('Recount margin: Minnesota Senate flagged (0.2 pts, 0.25% rule)', bool(R['S-MN']['flags'].get('recount', {}).get('within'))),
        ('GA 49.6%: Governor leader finishes at 49.6%', abs((gov['flags']['majority'] or {}).get('leader_pct', 0) - 49.6) < 0.06),
        ('GA 49.6%: flagged as likely runoff on Dec 1', bool(gov['flags']['majority'].get('likely')) and gov['flags']['majority']['rule']['date'] == '2026-12-01'),
        ('GA 49.6%: Senate race above 50%, not flagged', R['S-GA']['flags']['majority']['above'] is True),
        ('No race is marked called (no call source configured)', all(r['call'] is None for r in R.values())),
        ('States without a feed show no data, not estimates', R['S-TX']['result'] is None and R['S-OH']['result'] is None),
        ('Every result carries a source and timestamp', all(r['source'] and r['source'].get('fetched_at') for r in R.values() if r['result'])),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='/tmp/bg-mock')
    a = ap.parse_args()
    t0 = time.time()
    live, tl = run(a.out)
    res = checks(live, tl)
    for name, ok in res:
        print(('PASS ' if ok else 'FAIL ') + name)
    json.dump([{'check': n, 'pass': bool(o)} for n, o in res], open(os.path.join(a.out, 'report.json'), 'w'), indent=1)
    print(f'{sum(1 for _, o in res if o)}/{len(res)} passed in {time.time() - t0:.0f}s real time; timeline in {a.out}/timeline.json')


if __name__ == '__main__':
    main()
