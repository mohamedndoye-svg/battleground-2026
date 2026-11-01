"""Assemble data/ga.json: Georgia statewide races, 14 House districts, early-vote turnout, rules.

Usage: python3 -I build_ga.py <wiki_dir> <gv_dir> <out_dir>
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
GVU = 'https://georgiavotes.com/'
NOW = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def fetched(path):
    return datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def wpath(t):
    return os.path.join(WIKI, t + '.html')


def predictions(title):
    """Cook / Inside Elections / Sabato rows from the page's 'Predictions' table (Source | Ranking | As of)."""
    out = {}
    try:
        tables = pd.read_html(wpath(title), flavor='lxml')
    except ValueError:
        return out
    for t in tables:
        cols = [str(c) for c in t.columns]
        if cols[:3] != ['Source', 'Ranking', 'As of']:
            continue
        for _, r in t.iterrows():
            src = re.sub(r'\[.*?\]', '', str(r['Source'])).strip()
            key = 'cook' if src.startswith('The Cook') or src.startswith('Cook') else 'ie' if src.startswith('Inside') else \
                'sabato' if src.startswith('Sabato') else None
            if key and key not in out:
                rating = re.sub(r'\[.*?\]', '', str(r['Ranking'])).strip()
                out[key] = {'rating': 'Toss-up' if rating.lower().startswith('toss') else rating,
                            'as_of': re.sub(r'\[.*?\]', '', str(r['As of'])).strip(),
                            'via': WP + title + '#Predictions', 'fetched_at': fetched(wpath(title))}
        if out:
            break
    return out


STATEWIDE = [
    # office, page title, D candidate, R candidate, D surname, R surname, incumbent note
    ('U.S. Senate', '2026_United_States_Senate_election_in_Georgia', 'Jon Ossoff', 'Mike Collins', 'Ossoff', 'Collins', 'Jon Ossoff (D) is running for re-election'),
    ('Governor', '2026_Georgia_gubernatorial_election', 'Keisha Lance Bottoms', 'Rick Jackson', 'Bottoms', 'Jackson', 'Open: Brian Kemp (R) is term-limited. Libertarian Chase Oliver withdrew.'),
    ('Lieutenant Governor', '2026_Georgia_lieutenant_gubernatorial_election', 'Josh McLaurin', 'Greg Dolezal', 'McLaurin', 'Dolezal', 'Open seat'),
    ('Secretary of State', '2026_Georgia_Secretary_of_State_election', 'Penny Brown Reynolds', 'Tim Fleming', 'Reynolds', 'Fleming', 'Open: Brad Raffensperger (R) ran for governor'),
    ('Attorney General', '2026_Georgia_Attorney_General_election', 'Tanya Miller', 'Brian Strickland', 'Miller', 'Strickland', 'Open: Chris Carr (R) ran for governor'),
    ('Agriculture Commissioner', '2026_Georgia_Agriculture_Commissioner_election', 'Katherine Juhan-Arnold', 'Tyler Harper', 'Juhan-Arnold', 'Harper', 'Tyler Harper (R) is running for re-election'),
    ('Insurance Commissioner', '2026_Georgia_Insurance_Commissioner_election', 'Keisha Sean Waites', 'John King', 'Waites', 'King', 'John King (R) is running for re-election'),
    ('Labor Commissioner', '2026_Georgia_Labor_Commissioner_election', 'Nikki Porcher', 'Bárbara Rivera Holmes', 'Porcher', 'Holmes', 'Bárbara Rivera Holmes (R) is running for a first full term'),
    ('State School Superintendent', '2026_Georgia_State_Superintendent_of_Schools_election', 'Lydia Catalina Powell', 'Richard Woods', 'Powell', 'Woods', 'Richard Woods (R) is running for re-election'),
    ('Public Service Commission, District 3', '2026_Georgia_Public_Service_Commission_election', 'Peter Hubbard', 'Fitz Johnson', 'Hubbard', 'Johnson', 'Peter Hubbard (D) is running for re-election; rematch of 2025'),
    ('Public Service Commission, District 5', '2026_Georgia_Public_Service_Commission_election', 'Shelia Edwards', 'Josh Tolbert', 'Edwards', 'Tolbert', 'Open: Tricia Pridemore (R) ran for U.S. House'),
]
INC = {'Jon Ossoff', 'Tyler Harper', 'John King', 'Bárbara Rivera Holmes', 'Richard Woods', 'Peter Hubbard'}

statewide = []
for office, title, dc, rc, ds, rs, note in STATEWIDE:
    path = wpath(title)
    pol = P.parse(path, WP + title, fetched(path), ds, rs) if os.path.exists(path) else {'averages': [], 'polls': []}
    pol['rcp_direct'] = 'blocked: realclearpolling.com returns 403 to automated requests'
    vals = [a['margin'] for a in pol['averages'] if a['margin'] is not None]
    statewide.append({
        'id': 'GA-' + re.sub(r'\W+', '-', office).strip('-'), 'office': office,
        'candidates': [{'name': dc, 'party': 'D', 'incumbent': dc in INC}, {'name': rc, 'party': 'R', 'incumbent': rc in INC}],
        'main': {'dem_side': ds, 'rep_side': rs, 'dem_party': 'D'},
        'note': note, 'source': WP + title, 'fetched_at': fetched(path),
        'ratings': predictions(title), 'polling': pol, 'consensus': round(sum(vals) / len(vals), 1) if vals else None,
    })

measures = {
    'items': [
        {'name': 'Amendment 1', 'summary': 'Raise the cap on land a single owner can enroll in the Conservation Use Valuation Assessment (CUVA) program from 2,000 to 4,000 acres.'},
        {'name': 'Amendment 2', 'summary': 'Require all probate court judges to be elected in nonpartisan elections.'},
        {'name': 'Amendment 3', 'summary': 'Allow the General Assembly to create and dedicate revenue to a Georgia Next Generation 9-1-1 Fund.'},
    ],
    'count_note': 'Three constitutional amendments; no other statewide referendum questions were reported.',
    'numbering_note': 'News outlets number these differently. Numbering here follows the Secretary of State summary booklet as described in search results; the booklet itself (sos.ga.gov) blocks automated access, so confirm the order on your sample ballot.',
    'sources': [
        {'label': 'WTOC (Oct 21, 2026): Georgia voters will decide 3 constitutional amendments', 'url': 'https://www.wtoc.com/2026/10/21/georgia-voters-will-decide-3-constitutional-amendments-during-midterms/'},
        {'label': 'Ballotpedia News (Apr 2, 2026)', 'url': 'https://news.ballotpedia.org/2026/04/02/georgia-general-assembly-places-constitutional-amendments-on-the-2026-ballot-to-fund-emergency-response-systems-and-require-nonpartisan-elections-for-probate-judges/'},
        {'label': 'GA Secretary of State: 2026 Constitutional Summaries booklet (PDF; not machine-readable from here)', 'url': 'https://sos.ga.gov/sites/default/files/2026-09/2026%20Constitutional%20Summaries%20booklet%20FINAL.pdf'},
    ],
    'retrieved': '2026-10-30 via web search; pages not directly fetched',
}

# ---------------------------------------------------------------- House districts
ratings = json.load(open(os.path.join(RAW, 'ratings.json')))['house']
h270 = json.load(open(os.path.join(RAW, 'h270.json')))
rows = {k.replace('\xa0', ' '): v for k, v in ratings['rows'].items()}
GWINNETT = {'GA-4', 'GA-9', 'GA-10', 'GA-13'}
houses = []
for i in range(1, 15):
    key = f'GA-{i}'
    d = h270[key]
    row = rows.get(f'Georgia {i}')
    rb = {}
    for k in ('cook', 'ie', 'sabato'):
        if row:
            rb[k] = {'rating': row[k], 'as_of': ratings['as_of'][k]}
        else:
            rb[k] = {'rating': 'Solid', 'as_of': ratings['as_of'][k],
                     'note': 'Not listed in the competitive-seat table, i.e. rated Solid/Safe by every rater'}
    cands = [{'name': c['name'].rstrip('*'), 'party': {'DD': 'D', 'RR': 'R'}.get(c['fill'], c['fill']), 'incumbent': c['name'].endswith('*')}
             for c in d['candidates']]
    pm = d['pres2024']
    houses.append({
        'id': key, 'incumbent': d['incumbent'], 'note': d.get('note') or '',
        'candidates': cands, 'ratings': rb,
        'competitive': any(re.match(r'(Toss|Tilt|Lean)', (rb[k]['rating'] or '')) for k in rb),
        'gwinnett': key in GWINNETT,
        'pres2024': {'party': pm['party'], 'pts': pm['pts']} if pm else None,
        'house2024': d['house2024'],
    })
house_src = {
    'ratings_via': WP + '2026_United_States_House_of_Representatives_election_ratings',
    'ratings_fetched_at': fetched(wpath('house_ratings')),
    'candidates_and_margins': 'https://www.270towin.com/2026-house-election/',
    'candidates_fetched_at': fetched(os.path.join(os.path.dirname(GV), 'w270', 'house.html')),
    'gwinnett_source': WP + 'Gwinnett_County,_Georgia', 'gwinnett_fetched_at': fetched(wpath('gwinnett')),
    'gwinnett_note': 'Gwinnett County is split among the 4th, 9th, 10th and 13th districts (2023 map).',
    'ga13_note': 'David Scott (D) died April 22, 2026; Everton Blair won the special election, then lost the Democratic primary to Jasmine Clark.',
    'ga14_note': 'Marjorie Taylor Greene (R) resigned January 5, 2026; Clay Fuller won the special election.',
}

# ---------------------------------------------------------------- Turnout (georgiavotes.com, built from SOS absentee files)
home = open(os.path.join(GV, 'gv_home.html'), encoding='utf-8').read()
upd = re.search(r'Last updated\s*(?:<!-- -->)?\s*([\d-]+ [\d:]+)', home)
payload = home.replace('\\"', '"')
mrows = re.search(r'"maxVoteDay":"([\d-]+)","rows":(\[.*?\]),"series"', payload)
max_day, daily = mrows.group(1), json.loads(mrows.group(2))
cnty = json.loads(re.search(r'"counties":(\[\{"change".*?\}\])', payload).group(1))
cmp22 = {c['label']: c for c in cnty}
ct = pd.read_html(os.path.join(GV, 'gv_county.html'), flavor='lxml')[0]
ust = pd.read_html(os.path.join(GV, 'gv_ushouse.html'), flavor='lxml')[0]
shares = pd.read_html(os.path.join(GV, 'gv_home.html'), flavor='lxml')[0]
gw = open(os.path.join(GV, 'gv_c67.html'), encoding='utf-8').read()
gw_text = BeautifulSoup(gw, 'lxml').get_text(' ', strip=True)
gw_margin = re.search(r"two-party margin was (D|R)\+([\d.]+)", gw_text)

counties = []
for _, r in ct.iterrows():
    name = str(r['County'])
    c = cmp22.get(name, {})
    counties.append({'county': name, 'rv': int(r['RVs']), 'votes': int(r['Votes']), 'mail_accepted': int(r['Mail (V)']),
                     'early_in_person': int(r['Early (V)']), 'pct_of_rv': round(100 * int(r['Votes']) / int(r['RVs']), 1),
                     'same_point_2022': c.get('cmp'), 'change_vs_2022_pct': c.get('change'),
                     'pct_of_2022_total': str(r["% of '22"])})
counties.sort(key=lambda x: -x['rv'])
statewide_now = next(d for d in daily if d['dt'] == max_day)
turnout = {
    'source': GVU, 'source_note': 'georgiavotes.com is an independent site built from the GA Secretary of State absentee voter files (sos.ga.gov blocks automated access from here). Counts only accepted ballots with a return date.',
    'site_last_updated': upd.group(1) if upd else None, 'site_tz_note': 'timezone not stated by the site',
    'fetched_at': fetched(os.path.join(GV, 'gv_home.html')), 'through_vote_day': max_day,
    'statewide': {'votes': statewide_now['cur'], 'same_point_2022': statewide_now['cmp'],
                  'change_vs_2022_pct': round(100 * (statewide_now['cur'] / statewide_now['cmp'] - 1), 1),
                  'final_2022_early_total_note': 'The 2022 series keeps rising after this point; the 2022 value at election eve is shown in the daily series.',
                  'same_point_2024': None,
                  'same_point_2024_note': 'no data: georgiavotes.com compares midterm to midterm only, and the SOS 2024 absentee file is behind sos.ga.gov\'s bot wall.'},
    'daily': [{'date': d['dt'], 'y2026': d['cur'] if d['dt'] <= max_day else None, 'y2022': d['cmp']} for d in daily],
    'daily_note': '2022 is aligned to the same number of days before Election Day.',
    'electorate_by_race': [{'group': str(r['Race']), 'y2026': str(r['2026']), 'y2024': str(r['2024']), 'y2022': str(r['2022'])} for _, r in shares.iterrows()],
    'electorate_note': 'Share of early voters so far, compared with the same point in 2024 and 2022.',
    'counties': counties,
    'focus_counties': ['Gwinnett', 'Fulton', 'Cobb', 'DeKalb'],
    'by_district': [{'district': str(r['District']), 'rv': int(r['RVs']), 'votes': int(r['Votes']), 'pct_of_2022_total': str(r["% of '22"])} for _, r in ust.iterrows()],
    'gwinnett_extra': {'pres2024': f'{gw_margin.group(1)}+{gw_margin.group(2)}' if gw_margin else None,
                       'source': GVU + 'county?c=67', 'fetched_at': fetched(os.path.join(GV, 'gv_c67.html'))},
    'sos_turnout_page': 'https://sos.ga.gov/page/election-data-hub-turnout',
}

rules = {
    'runoff': {
        'rule': 'In a general election, a candidate needs a majority (50% + 1) of votes cast. If nobody gets it, the top two finishers go to a runoff.',
        'date': '2026-12-01', 'date_label': 'Tuesday, December 1, 2026',
        'details': 'Polls open 7 a.m.–7 p.m. Early voting for the runoff is shortened by Thanksgiving; counties set exact dates.',
        'statute': 'O.C.G.A. § 21-2-501',
        'sources': [{'label': 'georgia.gov: Georgia Election Guide', 'url': 'https://georgia.gov/georgia-election-guide'},
                    {'label': 'Wikipedia: 2026 Georgia state elections (cites GA SOS Elections Division)', 'url': WP + '2026_Georgia_state_elections'},
                    {'label': 'Rockdale County 2026 election schedule (from SOS calendar)', 'url': 'https://www.rockdalecountyga.gov/board-of-elections-voter-registration/georgia-2026-election-schedule-v1-2/'}],
    },
    'recount': {
        'rule': 'No automatic recount. A losing candidate may request one if the margin is 0.5 percentage points or less, in writing, within two business days after certification. Election superintendents may also order a recount before certification if they find a discrepancy.',
        'threshold_pct': 0.5, 'statute': 'O.C.G.A. § 21-2-495',
        'sources': [{'label': 'georgia.gov: Election Recount Rules in Georgia', 'url': 'https://georgia.gov/election-recount-rules-georgia'},
                    {'label': 'Verified Voting: Georgia recount law', 'url': 'https://verifiedvoting.org/recountlaw/georgia/'}],
    },
    'verified': '2026-10-30 via web search of official georgia.gov pages; sos.ga.gov and legis.ga.gov could not be fetched directly',
    'other_dates': {'election_day': '2026-11-03', 'early_voting_ends': '2026-10-30'},
    'not_on_ballot': 'Georgia Supreme Court and Court of Appeals seats were decided in the May 19 nonpartisan election, not in November.',
}

json.dump({'generated_at': NOW, 'statewide': statewide, 'measures': measures, 'house': houses, 'house_sources': house_src,
           'turnout': turnout, 'rules': rules}, open(os.path.join(OUT, 'ga.json'), 'w'), indent=1, ensure_ascii=False)
print('statewide', [(s['office'], s['consensus'], len(s['polling']['polls']), list(s['ratings'])) for s in statewide])
print('turnout', turnout['statewide'], turnout['site_last_updated'], 'gw', turnout['gwinnett_extra'])
