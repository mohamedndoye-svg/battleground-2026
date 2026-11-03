"""Assemble data/races.json (national) and data/ga.json (Georgia) from downloaded source pages.

Usage: python3 -I build_data.py <wiki_dir> <gv_dir> <out_dir>
Every number carries a source URL and a fetched_at timestamp (file download time, UTC).
Nothing is estimated: if a value can't be parsed from a source, it is written as null and
the page shows "no data".
"""
import sys, os, re, json, io, warnings
from datetime import datetime, timezone
import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(__file__))
import parse_polls as P

warnings.filterwarnings('ignore')
WIKI, GV, OUT = sys.argv[1:4]
RAW = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw')
WP = 'https://en.wikipedia.org/wiki/'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def fetched(path):
    return datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def wpath(title):
    return os.path.join(WIKI, title + '.html')


ratings = json.load(open(os.path.join(RAW, 'ratings.json')))
h270 = json.load(open(os.path.join(RAW, 'h270.json')))
pres_state = json.load(open(os.path.join(RAW, 'pres2024_state.json')))
RATER = {
    'cook': ('Cook Political Report', {'senate': 'https://www.cookpolitical.com/ratings/senate-race-ratings',
                                       'house': 'https://www.cookpolitical.com/ratings/house-race-ratings'}),
    'ie': ('Inside Elections', {'senate': 'https://insideelections.com/ratings/senate',
                                'house': 'https://insideelections.com/ratings/house'}),
    'sabato': ("Sabato's Crystal Ball", {'senate': 'https://centerforpolitics.org/crystalball/2026-senate/',
                                         'house': 'https://centerforpolitics.org/crystalball/2026-house/'}),
}
GOV_URLS = {'cook': 'https://www.cookpolitical.com/ratings/governor-race-ratings', 'ie': 'https://insideelections.com/ratings/governor',
            'sabato': 'https://centerforpolitics.org/crystalball/2026-governor/'}
for k, u in GOV_URLS.items():
    RATER[k][1]['governor'] = u
RATINGS_PAGE = {'senate': WP + '2026_United_States_Senate_elections#Predictions',
                'house': WP + '2026_United_States_House_of_Representatives_election_ratings',
                'governor': WP + '2026_United_States_gubernatorial_elections#Predictions'}
RATINGS_FILE = {'senate': wpath('2026_United_States_Senate_elections'), 'house': wpath('house_ratings'), 'governor': wpath('gov')}


def score(r):
    """Signed lean: + = D, - = R, 0 = toss-up. Used only for ordering and colour, never displayed as data."""
    if not r or r == 'nan':
        return None
    r = r.replace(' (flip)', '')
    if r.startswith('Toss'):
        return 0
    m = re.match(r'(Tilt|Lean|Likely|Solid|Safe) ([DRI])', r)
    if not m:
        return None
    v = {'Tilt': 1, 'Lean': 2, 'Likely': 3, 'Solid': 4, 'Safe': 4}[m.group(1)]
    return v if m.group(2) in 'DI' else -v


def competitive(r):
    return bool(r) and bool(re.match(r'(Toss|Tilt|Lean)', r))


def rating_block(chamber, row):
    out = {}
    for k, (name, urls) in RATER.items():
        out[k] = {'rating': row.get(k) if row else None, 'as_of': ratings[chamber]['as_of'][k], 'rater': name,
                  'rater_url': urls[chamber], 'via': RATINGS_PAGE[chamber], 'fetched_at': fetched(RATINGS_FILE[chamber])}
    return out


def polling(path, title, dem, rep, extra=()):
    if not os.path.exists(path):
        return {'page': WP + title, 'fetched_at': None, 'averages': [], 'polls': [], 'error': 'page not fetched'}
    p = P.parse(path, WP + title, fetched(path), dem, rep, extra)
    p['rcp_direct'] = 'blocked: realclearpolling.com returns 403 to automated requests'
    return p


def consensus(avgs):
    vals = [a['margin'] for a in avgs if a.get('margin') is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


# ---------------------------------------------------------------- Senate
SENATE = [
    # id, state, page title, dem-side surname (or I), rep surname, incumbent, inc party, open?, candidates, extra ballot names
    ('AK', 'Alaska', '2026_United_States_Senate_election_in_Alaska', 'sen_Alaska', 'Peltola', 'Dan S. Sullivan', 'Dan Sullivan', 'R', False,
     [('Mary Peltola', 'D'), ('Dan S. Sullivan', 'R', True), ('Dan J. Sullivan', 'R'), ('Gerald Heikes', 'R')], ('Dan J. Sullivan', 'Heikes')),
    ('IA', 'Iowa', '2026_United_States_Senate_election_in_Iowa', 'sen_Iowa', 'Turek', 'Hinson', 'Joni Ernst (retiring)', 'R', True,
     [('Josh Turek', 'D'), ('Ashley Hinson', 'R'), ('Thomas Laehn', 'L')], ()),
    ('KS', 'Kansas', '2026_United_States_Senate_election_in_Kansas', 'sen_Kansas', 'Hamilton', 'Marshall', 'Roger Marshall', 'R', False,
     [('Adam Hamilton', 'D'), ('Roger Marshall', 'R', True), ('David Graham', 'L')], ()),
    ('ME', 'Maine', '2026_United_States_Senate_election_in_Maine', 'sen_Maine', 'Jackson', 'Collins', 'Susan Collins', 'R', False,
     [('Troy Jackson', 'D'), ('Susan Collins', 'R', True)], ()),
    ('MI', 'Michigan', '2026_United_States_Senate_election_in_Michigan', 'sen_Michigan', 'El-Sayed', 'Rogers', 'Gary Peters (retiring)', 'D', True,
     [('Abdul El-Sayed', 'D'), ('Mike Rogers', 'R')], ()),
    ('MN', 'Minnesota', '2026_United_States_Senate_election_in_Minnesota', 'sen_Minnesota', 'Flanagan', 'Tafoya', 'Tina Smith (retiring)', 'D', True,
     [('Peggy Flanagan', 'D'), ('Michele Tafoya', 'R')], ()),
    ('NE', 'Nebraska', '2026_United_States_Senate_election_in_Nebraska', 'sen_Nebraska', 'Osborn', 'Ricketts', 'Pete Ricketts', 'R', False,
     [('Dan Osborn', 'I'), ('Pete Ricketts', 'R', True)], ()),
    ('NH', 'New Hampshire', '2026_United_States_Senate_election_in_New_Hampshire', 'sen_New_Hampshire', 'Pappas', 'Sununu', 'Jeanne Shaheen (retiring)', 'D', True,
     [('Chris Pappas', 'D'), ('John E. Sununu', 'R')], ()),
    ('NC', 'North Carolina', '2026_United_States_Senate_election_in_North_Carolina', 'sen_North_Carolina', 'Cooper', 'Whatley', 'Thom Tillis (retiring)', 'R', True,
     [('Roy Cooper', 'D'), ('Michael Whatley', 'R')], ()),
    ('OH', 'Ohio (special)', '2026_United_States_Senate_special_election_in_Ohio', '2026_United_States_Senate_special_election_in_Ohio', 'Brown', 'Husted', 'Jon Husted (appointed)', 'R', False,
     [('Sherrod Brown', 'D'), ('Jon Husted', 'R', True)], ()),
    ('SC', 'South Carolina', '2026_United_States_Senate_election_in_South_Carolina', 'sen_South_Carolina', 'Andrews', 'Darline Graham', 'Darline Graham (appointed)', 'R', False,
     [('Annie Andrews', 'D'), ('Darline Graham', 'R', True)], ()),
    ('TX', 'Texas', '2026_United_States_Senate_election_in_Texas', 'sen_Texas', 'Talarico', 'Paxton', 'John Cornyn (lost renomination)', 'R', True,
     [('James Talarico', 'D'), ('Ken Paxton', 'R'), ('Ted Brown', 'L')], ()),
    ('GA', 'Georgia', '2026_United_States_Senate_election_in_Georgia', '2026_United_States_Senate_election_in_Georgia', 'Ossoff', 'Collins', 'Jon Ossoff', 'D', False,
     [('Jon Ossoff', 'D', True), ('Mike Collins', 'R')], ()),
]
SEN_KEY = {'Ohio (special)': 'Ohio (special)'}

races = []
srows = ratings['senate']['rows']
for sid, state, title, fname, dem, rep, inc, incp, open_, cands, extra in SENATE:
    row = srows.get(SEN_KEY.get(state, state))
    rb = rating_block('senate', row)
    by_rule = any(competitive(rb[k]['rating']) for k in RATER)
    pol = polling(wpath(fname), title, dem, rep, extra)
    pstate = state.split(' (')[0]
    races.append({
        'id': 'S-' + sid, 'chamber': 'senate', 'state': pstate, 'label': f'{state} Senate',
        'incumbent': {'name': inc, 'party': incp}, 'open': open_,
        'candidates': [{'name': c[0], 'party': c[1], 'incumbent': len(c) > 2} for c in cands],
        'main': {'dem_side': dem, 'rep_side': rep, 'dem_party': 'I' if sid == 'NE' else 'D'},
        'pres2024': {'margin_r': pres_state.get(pstate), 'source': WP + '2024_United_States_presidential_election#Results_by_state',
                     'fetched_at': fetched(wpath('pres2024'))},
        'pvi': row.get('pvi') if row else None,
        'ratings': rb, 'included_by': 'rule' if by_rule else 'manual',
        'included_note': None if by_rule else 'Added by hand: Georgia (rated Likely D by all three, outside the Toss-up/Lean rule).',
        'polling': pol, 'consensus': consensus(pol['averages']),
    })

# Senate seat baseline (seats not in the tracked list), from the Cook column.
sinfo = {'current': {'R': 53, 'D': 45, 'I': 2, 'note': 'Both independents (King, Sanders) caucus with Democrats.'},
         'up': {'R': 22, 'D': 13, 'I': 0}, 'source': WP + '2026_United_States_Senate_elections',
         'fetched_at': fetched(wpath('2026_United_States_Senate_elections'))}
tracked_states = {r['state'] if r['id'] != 'S-OH' else 'Ohio (special)' for r in races}
base = {'D': 0, 'R': 0}
for k, row in srows.items():
    if k.startswith('_') or k in tracked_states:
        continue
    s = score(row['cook'])
    base['D' if s > 0 else 'R'] += 1
holdover = {'D': sinfo['current']['D'] + sinfo['current']['I'] - sinfo['up']['D'], 'R': sinfo['current']['R'] - sinfo['up']['R']}
senate_ctl = {
    **sinfo, 'holdover': holdover, 'safe_up': base,
    'base': {'D': holdover['D'] + base['D'], 'R': holdover['R'] + base['R']},
    'majority': {'D': 51, 'R': 50},
    'vp': {'name': 'JD Vance', 'party': 'R', 'note': 'The Vice President breaks 50–50 ties, so Republicans control the Senate with 50 seats; Democrats need 51. Vance\'s term runs to January 2029, covering the new Congress that starts January 3, 2027.'},
    'baseline_rater': 'cook',
}

# ---------------------------------------------------------------- House: summary only
CATS = ['Solid', 'Likely', 'Lean', 'Tilt']


def house_summary():
    """Per rater: how many of the 435 seats sit in each category for each party.
    The ratings table lists only seats some rater calls competitive; every unlisted seat is Solid/Safe
    for everyone, so Solid = the rater's party total minus that party's listed non-solid seats."""
    rows = {k: v for k, v in ratings['house']['rows'].items() if not k.startswith('_')}
    out = {}
    for k in RATER:
        # final ratings can drop toss-ups entirely (e.g. "D – 239 R – 196"), so the toss-up count is optional
        m = re.search(r'D\D+(\d+)\D+R\D+(\d+)(?:\D+(\d+))?', ratings['house']['rows']['_overall'][k])
        totD, totR, toss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        cnt = {'D': {c: 0 for c in CATS}, 'R': {c: 0 for c in CATS}}
        for row in rows.values():
            r = (row.get(k) or '').replace(' (flip)', '')
            mm = re.match(r'(Tilt|Lean|Likely|Solid|Safe) ([DR])', r)
            if mm and mm.group(1) not in ('Solid', 'Safe'):
                cnt[mm.group(2)][mm.group(1)] += 1
        flips = {'D': sum(1 for row in rows.values() if re.search(r' D \(flip\)', row.get(k) or '')),
                 'R': sum(1 for row in rows.values() if re.search(r' R \(flip\)', row.get(k) or ''))}
        for p_, tot in (('D', totD), ('R', totR)):
            cnt[p_]['Solid'] = tot - sum(v for c, v in cnt[p_].items() if c != 'Solid')
        out[k] = {'rater': RATER[k][0], 'as_of': ratings['house']['as_of'][k], 'D': cnt['D'], 'R': cnt['R'], 'toss': toss,
                  'total': {'D': totD, 'R': totR}, 'flips': flips,
                  'd_needs_from_toss': max(0, 218 - totD), 'r_needs_from_toss': max(0, 218 - totR)}
        assert totD + totR + toss == 435, (k, totD, totR, toss)
    return out


for r in races:
    r['mean_score'] = round(sum(score(r['ratings'][k]['rating']) for k in RATER) / 3, 2)

house_ctl = {
    'current': {'R': 218, 'D': 214, 'I': 1, 'vacant': 2,
                'note': 'Independent Kevin Kiley (CA) caucuses with Republicans. All 435 seats are up in 2026.'},
    'source': WP + '2026_United_States_House_of_Representatives_elections',
    'fetched_at': fetched(wpath('2026_United_States_House_of_Representatives_elections')),
    'majority': 218, 'seats': 435,
    'by_rater': house_summary(),
    'ratings_via': RATINGS_PAGE['house'], 'ratings_fetched_at': fetched(RATINGS_FILE['house']),
}
assert senate_ctl['base']['D'] + senate_ctl['base']['R'] + len(races) == 100, senate_ctl['base']

# ---------------------------------------------------------------- Governors
GOV = [
    # state, D-side surname, R surname, D candidate, R candidate, other candidates on the ballot, extra ballot names allowed in poll tables
    ('Alaska', 'Kreiss-Tomkins', 'Wilson', 'Jonathan Kreiss-Tomkins', 'Bernadette Wilson', [('Dave Bronson', 'R'), ('Treg Taylor', 'R')], ('Bronson', 'Taylor')),
    ('Arizona', 'Hobbs', 'Biggs', 'Katie Hobbs', 'Andy Biggs', [('Teri Hourihan', 'No Labels'), ('Risa Lombardo', 'Green')], ()),
    ('Florida', 'Jolly', 'Donalds', 'David Jolly', 'Byron Donalds', [('Scott Jewett', 'L')], ()),
    ('Georgia', 'Bottoms', 'Jackson', 'Keisha Lance Bottoms', 'Rick Jackson', [], ()),
    ('Iowa', 'Sand', 'Lahn', 'Rob Sand', 'Zach Lahn', [('Sondra Wilson', 'I')], ()),
    ('Kansas', 'Holscher', 'Masterson', 'Cindy Holscher', 'Ty Masterson', [], ()),
    ('Michigan', 'Benson', 'James', 'Jocelyn Benson', 'John James', [('Anthony Hudson', 'L')], ()),
    ('Nebraska', 'Walz', 'Pillen', 'Lynne Walz', 'Jim Pillen', [('Brett Lindstrom', 'America First')], ()),
    ('Nevada', 'Aaron Ford', 'Lombardo', 'Aaron Ford', 'Joe Lombardo', [('Danielle Ford', 'I')], ()),
    ('Ohio', 'Acton', 'Ramaswamy', 'Amy Acton', 'Vivek Ramaswamy', [('Donald Kissick', 'L')], ()),
    ('Oregon', 'Kotek', 'Drazan', 'Tina Kotek', 'Christine Drazan', [('Brett Smith', 'Pacific Green')], ()),
    ('Texas', 'Hinojosa', 'Abbott', 'Gina Hinojosa', 'Greg Abbott', [('Pat Dixon', 'L')], ()),
    ('Vermont', 'Janoo', 'Scott', 'Amanda Janoo', 'Phil Scott', [('Brian Judd', 'I')], ()),
    ('Wisconsin', 'Crowley', 'Tiffany', 'David Crowley', 'Tom Tiffany', [], ()),
]
grows = ratings['governor']['rows']
analysis = json.load(open(os.path.join(os.path.dirname(__file__), '..', 'data', 'gov_analysis.json')))
govs = []
for st, ds, rs, dc, rc, others, extra in GOV:
    row = grows[st]
    rb = rating_block('governor', row)
    title = f'2026_{st}_gubernatorial_election'
    pol = polling(wpath('gov_' + st), title, ds, rs, extra)
    inc = row['incumbent']
    open_ = bool(re.search(r'term-limited|retiring|lost', inc))
    incp = re.search(r'([DR])$', row['last'] or '')
    is_inc = lambda n: (not open_) and n.split()[-1] in inc
    govs.append({
        'id': 'G-' + st, 'chamber': 'governor', 'state': st, 'label': f'{st} Governor',
        'incumbent': {'name': inc, 'party': incp.group(1) if incp else None}, 'open': open_,
        'candidates': [{'name': dc, 'party': 'D', 'incumbent': is_inc(dc)}, {'name': rc, 'party': 'R', 'incumbent': is_inc(rc)}]
                      + [{'name': n, 'party': p_, 'incumbent': False} for n, p_ in others],
        'main': {'dem_side': ds.split()[-1] if st != 'Nevada' else 'A. Ford', 'rep_side': rs, 'dem_party': 'D'},
        'pres2024': {'margin_r': pres_state.get(st), 'source': WP + '2024_United_States_presidential_election#Results_by_state',
                     'fetched_at': fetched(wpath('pres2024'))},
        'pvi': row.get('pvi'), 'ratings': rb, 'included_by': 'rule', 'polling': pol, 'consensus': consensus(pol['averages']),
        'mean_score': round(sum(score(rb[k]['rating']) for k in RATER) / 3, 2),
        'analysis': analysis['races'].get(st),
    })
gtot = {k: ratings['governor']['rows']['_overall'][k] for k in RATER}
_ib = BeautifulSoup(open(wpath('gov'), encoding='utf-8'), 'lxml').select_one('table.infobox').get_text(' ', strip=True)
_sb = re.search(r'Seats before (\d+) (\d+)', _ib)  # infobox order: Republican, Democratic
gov_ctl = {'current': {'R': int(_sb.group(1)), 'D': int(_sb.group(2))} if _sb else None, 'by_rater_totals': gtot, 'as_of': ratings['governor']['as_of'], 'source': RATINGS_PAGE['governor'],
           'fetched_at': fetched(RATINGS_FILE['governor']), 'analysis_as_of': analysis['as_of']}

json.dump({
    'generated_at': NOW,
    'notes': {
        'ratings': 'Cook, Inside Elections and Sabato all block automated access (Cloudflare / bot walls). Ratings are read from Wikipedia\'s rating tables, which cite each rater with the date shown.',
        'polls': 'Polls and averages come from each race\'s Wikipedia page (pollster, dates, sample, LV/RV, MoE, with the pollster\'s own link). RealClearPolling blocks automated access; its average appears only where Wikipedia reports it (labelled RealClearPolitics). Silver Bulletin (paid) is excluded.',
        'margin_sign': 'Poll and average margins: positive = Democratic (or independent) candidate ahead. pres2024.margin_r: positive = Trump ahead.',
        'inside_elections_tilt': 'Inside Elections uses a "Tilt" category; it is treated as Lean for race selection.',
    },
    'control': {'senate': senate_ctl, 'house': house_ctl, 'governor': gov_ctl},
    'races': races + govs,
}, open(os.path.join(OUT, 'races.json'), 'w'), indent=1, ensure_ascii=False)
print('senate', len(races), senate_ctl['base'], 'governors', len(govs))
print('house', {k: (v['total'], v['toss'], v['D'], v['R']) for k, v in house_ctl['by_rater'].items()})
