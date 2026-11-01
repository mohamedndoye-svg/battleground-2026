"""Registry of official results sources, what races each covers, and how each one is polled.

Base URLs can be overridden with environment variables (BG_GA_BASE, BG_IA_BASE, ...) so the mock election-night
server can stand in for the real feeds during tests.
"""
import os
from .feeds import ga, clarity, flatfiles, nebraska

ELECTION_DATE = os.environ.get('BG_ELECTION_DATE', '2026-11-03')


def env(name, default):
    return os.environ.get(name, default)


# Which of our race IDs (from data/races.json) each contest key feeds.
RACE_OF = {
    'GA-SEN': 'S-GA', 'GA-GOV': 'G-Georgia',
    'IA-SEN': 'S-IA', 'IA-GOV': 'G-Iowa',
    'SC-SEN': 'S-SC',
    'MN-SEN': 'S-MN',
    'NC-SEN': 'S-NC',
    'FL-GOV': 'G-Florida',
    'NE-SEN': 'S-NE', 'NE-GOV': 'G-Nebraska',
}

CLARITY = {
    'IA': {'base': lambda: env('BG_IA_BASE', 'https://electionresults.iowa.gov/IA'), 'source': 'Iowa Secretary of State (Clarity ENR)',
           'public': 'https://electionresults.iowa.gov/IA/', 'list': True,
           'keys': {'IA-SEN': r'^United States Senator$', 'IA-GOV': r'^Governor and Lt\.? Governor$'}},
    'SC': {'base': lambda: env('BG_SC_BASE', 'https://www.enr-scvotes.org/SC'), 'source': 'SC Election Commission (Clarity ENR)',
           'public': 'https://www.enr-scvotes.org/SC/127300/', 'list': False, 'eid': env('BG_SC_EID', '127300'),
           'keys': {'SC-SEN': r'^U\.S\. Senate$', 'SC-GOV': r'^Governor and Lieutenant Governor$'}},
}

NE_PARTIES = {'ricketts': 'R', 'osborn': 'I', 'pillen': 'R', 'walz': 'D', 'lindstrom': 'America First'}


class Source:
    """One feed. `poll(state)` returns (contests or None if unchanged, version)."""
    interval = 180

    def __init__(self, sid, state, name, url, interval=None):
        self.id, self.state, self.name, self.url = sid, state, name, url
        if interval:
            self.interval = interval


class GASource(Source):
    def poll(self, st):
        ga.BASE = env('BG_GA_BASE', 'https://results.sos.ga.gov/results/public/api')
        eid = st.get('eid') or ga.find_election(ELECTION_DATE)
        if not eid:
            return 'not_live', None
        st['eid'] = eid
        # county breakdowns for every tracked GA contest; the per-contest endpoint is only hit when the version changes
        contests, meta = ga.poll(eid, prev_version=st.get('version'), all_counties=True)
        return contests, meta['version']


class ClaritySource(Source):
    def poll(self, st):
        cfg = CLARITY[self.state]
        base = cfg['base']()
        eid = st.get('eid') or (clarity.find_election(base, cfg['source'], ELECTION_DATE) if cfg['list'] else cfg['eid'])
        if not eid:
            return 'not_live', None
        st['eid'] = eid
        contests, meta = clarity.poll(base, eid, self.state, cfg['keys'], cfg['source'], cfg['public'] + str(eid) + '/' if cfg['list'] else cfg['public'],
                                      prev_version=st.get('version'))
        return contests, meta['version']


class FileSource(Source):
    """MN / NC / FL publish one file per election; there is no version number, so we compare a content hash."""
    def __init__(self, sid, state, name, url, fn, interval=None):
        super().__init__(sid, state, name, url, interval)
        self.fn = fn

    def poll(self, st):
        import hashlib, json
        contests = self.fn(ELECTION_DATE)
        ver = hashlib.sha1(json.dumps([[c['key'], [x['votes'] for x in c['candidates']], c.get('reporting')] for c in contests]).encode()).hexdigest()[:12]
        if st.get('version') == ver:
            return None, ver
        return contests, ver


class NESource(Source):
    def poll(self, st):
        import hashlib, json
        contests = nebraska.poll(NE_PARTIES)
        ver = hashlib.sha1(json.dumps([[c['key'], [x['votes'] for x in c['candidates']]] for c in contests]).encode()).hexdigest()[:12]
        return (None if st.get('version') == ver else contests), ver


def _date_compact():
    return ELECTION_DATE.replace('-', '')


def build_sources():
    flatfiles_mn = lambda d: flatfiles.poll_mn(d)
    return [
        GASource('ga', 'GA', 'GA Secretary of State', 'https://results.sos.ga.gov/results/public/Georgia', interval=120),
        ClaritySource('ia', 'IA', CLARITY['IA']['source'], 'https://electionresults.iowa.gov/IA/'),
        ClaritySource('sc', 'SC', CLARITY['SC']['source'], 'https://www.enr-scvotes.org/SC/127300/'),
        FileSource('mn', 'MN', flatfiles.MN_SOURCE, flatfiles.mn_url(ELECTION_DATE, 'ussenate'), flatfiles_mn),
        FileSource('nc', 'NC', flatfiles.NC_SOURCE, flatfiles.nc_url(ELECTION_DATE), flatfiles.poll_nc),
        FileSource('fl', 'FL', flatfiles.FL_SOURCE, flatfiles.fl_url(ELECTION_DATE), flatfiles.poll_fl),
        NESource('ne', 'NE', nebraska.SOURCE, nebraska.URL),
    ]


# Tracked states with no automated official source, and why (shown on the page).
NO_FEED = {
    'AK': 'elections.alaska.gov did not respond to automated requests',
    'AZ': 'results.arizona.vote is behind a Cloudflare bot check',
    'KS': 'Kansas posts results files only after the canvass; no live machine-readable feed found',
    'ME': 'maine.gov blocks automated requests (AWS); Maine publishes official tabulations after election night',
    'MI': 'mielections.us closes automated connections',
    'NH': 'sos.nh.gov blocks automated requests (Akamai)',
    'NV': 'silverstateelection.nv.gov is behind an Incapsula bot check',
    'OH': 'liveresults.ohiosos.gov returns 403 to automated requests',
    'OR': 'results.oregonvotes.gov has no machine-readable results file',
    'TX': 'results.texas-election.com is behind a Cloudflare bot check',
    'VT': 'Vermont\'s results site did not respond',
    'WI': 'Wisconsin has no statewide live results feed (counties report); elections.wi.gov is behind Cloudflare',
}
