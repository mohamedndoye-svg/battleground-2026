"""Parser tests for every non-Georgia feed, against files saved from the official sites:
2024 general results (where the site still serves them) and the 2026 general files already posted with zero votes.
Run: python3 -m unittest discover live/tests
"""
import gzip, json, os, unittest
from live.feeds import clarity, flatfiles, nebraska
from live import rules

FIX = os.path.join(os.path.dirname(__file__), 'fixtures')


def fx(name, mode='r'):
    p = os.path.join(FIX, name)
    if name.endswith('.gz'):
        return gzip.open(p, 'rt', encoding='utf-8').read()
    with open(p, 'rb' if mode == 'rb' else 'r', **({} if mode == 'rb' else {'encoding': 'utf-8'})) as f:
        return f.read()


def county_sum_ok(test, contest_cands, counties):
    for cand in contest_cands:
        tot = sum(next((x['votes'] for x in co['candidates'] if x['name'] == cand['name']), 0) for co in counties)
        test.assertEqual(tot, cand['votes'], cand['name'])


class TestClarityIowa(unittest.TestCase):
    km = {'IA-PRES': r'^President', 'IA-SEN': r'^United States Senator$', 'IA-GOV': r'^Governor and Lt\.? Governor$'}

    def test_2024_statewide_and_counties(self):
        s = clarity.parse_summary(json.loads(fx('ia_2024_summary.json')), 'IA', self.km, 'IA', 'u')
        pres = next(c for c in s if c['key'] == 'IA-PRES')
        by = {c['party']: c['votes'] for c in pres['candidates']}
        self.assertEqual((by['R'], by['D']), (927019, 707278))
        det = clarity.parse_detail(fx('ia_2024_detailxml.zip', 'rb'), self.km)['IA-PRES']
        self.assertEqual(len(det['counties']), 99)
        county_sum_ok(self, pres['candidates'], det['counties'])
        for c in pres['candidates']:
            self.assertEqual(sum(det['by_method'][c['name']].values()), c['votes'])

    def test_election_list_finds_2026_general(self):
        es = json.loads(fx('ia_elections.json'))
        gen = [e for e in es if e['ElectionName'] == '2026 General Election']
        self.assertEqual(gen[0]['EID'], '127077')


class TestClaritySouthCarolina(unittest.TestCase):
    km = {'SC-PRES': r'^President and Vice President$', 'SC-SEN': r'^U\.S\. Senate$', 'SC-GOV': r'^Governor and Lieutenant Governor$'}

    def test_2024_statewide_and_counties(self):
        s = clarity.parse_summary(json.loads(fx('sc_2024_summary.json')), 'SC', self.km, 'SC', 'u')
        pres = s[0]
        det = clarity.parse_detail(fx('sc_2024_detailxml.zip', 'rb'), self.km)['SC-PRES']
        self.assertEqual(len(det['counties']), 46)
        county_sum_ok(self, pres['candidates'], det['counties'])
        self.assertTrue(all(not c['name'].startswith(('REP ', 'DEM ')) for c in pres['candidates']))

    def test_2026_senate_contest_and_party_prefix(self):
        s = clarity.parse_summary(json.loads(fx('sc_2026_summary.json')), 'SC', self.km, 'SC', 'u')
        sen = next(c for c in s if c['key'] == 'SC-SEN')
        names = {c['name']: c['party'] for c in sen['candidates']}
        self.assertEqual(names['Darline Graham'], 'R')
        self.assertEqual(names['Annie Andrews'], 'D')


class TestMinnesota(unittest.TestCase):
    def test_2024_senate(self):
        c = flatfiles.parse_mn(fx('mn_20241105_ussenate.txt'), 'MN-SEN', 'u')[0]
        kl = next(x for x in c['candidates'] if x['name'] == 'Amy Klobuchar')
        self.assertEqual((kl['party'], kl['votes']), ('D', 1792441))
        self.assertEqual(c['reporting']['units'], c['reporting']['total'])

    def test_2026_file_has_nominees(self):
        c = flatfiles.parse_mn(fx('mn_20261103_ussenate.txt'), 'MN-SEN', 'u')[0]
        self.assertEqual({x['name'] for x in c['candidates'] if x['party'] in 'DR'}, {'Peggy Flanagan', 'Michele Tafoya'})


class TestNorthCarolina(unittest.TestCase):
    def test_2024_president_with_vote_methods(self):
        cs = flatfiles.parse_nc(json.loads(fx('nc_20241105_results_0.json.gz')), 'u')
        pres = next(c for c in cs if c['key'] == 'NC-PRES')
        t = next(c for c in pres['candidates'] if c['name'] == 'Donald J. Trump')
        self.assertEqual(t['votes'], 2898423)
        self.assertEqual(sum(t['by_method'].values()), t['votes'])

    def test_2026_senate_present(self):
        cs = flatfiles.parse_nc(json.loads(fx('nc_20261103_results_0.json.gz')), 'u')
        sen = next(c for c in cs if c['key'] == 'NC-SEN')
        self.assertIn('Roy Cooper', {c['name'] for c in sen['candidates']})


class TestFlorida(unittest.TestCase):
    def test_2024_president_counties(self):
        c = next(x for x in flatfiles.parse_fl(fx('fl_20241105.txt.gz'), 'u') if x['key'] == 'FL-PRES')
        self.assertEqual(len(c['counties']), 67)
        by = {x['name']: x['votes'] for x in c['candidates']}
        self.assertEqual(by['Trump'], 6110125)
        county_sum_ok(self, c['candidates'], c['counties'])

    def test_2026_governor_ticket_names(self):
        c = next(x for x in flatfiles.parse_fl(fx('fl_20261103.txt.gz'), 'u') if x['key'] == 'FL-GOV')
        by = {x['name']: x['party'] for x in c['candidates']}
        self.assertEqual((by['Donalds'], by['Jolly']), ('R', 'D'))


class TestNebraska(unittest.TestCase):
    def test_2026_export_structure(self):
        cs = nebraska.parse(fx('ne_2026_pre.xlsx', 'rb'), {'ricketts': 'R', 'osborn': 'I', 'pillen': 'R', 'walz': 'D'})
        sen = next(c for c in cs if c['key'] == 'NE-SEN')
        self.assertEqual(len(sen['counties']), 93)
        self.assertEqual(sen['reporting']['total'], 1322)
        self.assertEqual({c['name']: c['party'] for c in sen['candidates'] if c['party']}, {'Pete Ricketts': 'R', 'Dan Osborn': 'I'})


class TestRules(unittest.TestCase):
    def cands(self, a, b, other=0):
        return [{'name': 'A', 'party': 'D', 'votes': a}, {'name': 'B', 'party': 'R', 'votes': b}, {'name': 'C', 'party': 'L', 'votes': other}]

    def test_ga_runoff_at_49_6(self):
        m = rules.majority_check('GA', 'governor', self.cands(496, 494, 10), reporting_share=0.99)
        self.assertFalse(m['above'])
        self.assertTrue(m['likely'])
        self.assertEqual(m['rule']['date'], '2026-12-01')

    def test_ga_exactly_50_is_not_a_majority(self):
        self.assertFalse(rules.majority_check('GA', 'senate', self.cands(500, 490, 10))['above'])

    def test_recount_margins(self):
        self.assertTrue(rules.recount_check('GA', self.cands(1002, 998))['within'])     # 0.2%
        self.assertFalse(rules.recount_check('GA', self.cands(1100, 900))['within'])    # 10%
        self.assertTrue(rules.recount_check('SC', self.cands(1005, 995))['within'])     # 0.5% < 1%
        nc = rules.recount_check('NC', self.cands(2_510_000, 2_495_000))                # 0.3% but 15,000 votes
        self.assertFalse(nc['within'])

    def test_maine_rcv_only_for_senate(self):
        self.assertEqual(rules.majority_check('ME', 'senate', self.cands(48, 47, 5))['type'], 'rcv')
        self.assertIsNone(rules.majority_check('ME', 'governor', self.cands(48, 47, 5)))


if __name__ == '__main__':
    unittest.main()
