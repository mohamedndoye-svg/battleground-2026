"""Georgia parser tests against real Secretary of State data saved from results.sos.ga.gov:
the certified 2024 general (statewide + all 159 counties) and the June 16, 2026 primary runoff.
Run: python3 -m unittest live.tests.test_ga   (from the repo root)
"""
import gzip, io, json, os, unittest
from live.feeds import ga

FIX = os.path.join(os.path.dirname(__file__), 'fixtures')


def load(name):
    with gzip.open(os.path.join(FIX, name), 'rt', encoding='utf-8') as f:
        return json.load(f)


class FakeResp(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): self.close()


def opener_for(routes):
    """Fake urlopen: serves fixture JSON by URL suffix."""
    def op(req, timeout=None):
        url = req.full_url
        for suffix, fx in routes.items():
            if url.endswith(suffix):
                return FakeResp(json.dumps(load(fx)).encode())
        raise AssertionError('unexpected URL ' + url)
    return op


class TestGeorgia2024(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = ga.parse_statewide(load('ga_2024NovGen_data.json.gz'), '2024NovGen')
        cls.counties, cls.prec = ga.parse_counties(load('ga_2024NovGen_pres_counties.json.gz'))

    def test_statewide_president_matches_certified_result(self):
        pres = next(c for c in self.state if c['key'] == 'GA-PRES')
        by = {c['name']: c for c in pres['candidates']}
        self.assertEqual(by['Donald J. Trump']['votes'], 2663117)
        self.assertEqual(by['Kamala D. Harris']['votes'], 2548017)
        self.assertEqual(by['Donald J. Trump']['party'], 'R')
        self.assertEqual(by['Kamala D. Harris']['party'], 'D')
        self.assertEqual(pres['reporting'], {'units': 159, 'total': 159, 'unit': 'counties fully reported'})
        self.assertTrue(pres['official'])

    def test_vote_methods_sum_to_total(self):
        pres = next(c for c in self.state if c['key'] == 'GA-PRES')
        for c in pres['candidates']:
            self.assertEqual(sum(c['by_method'].values()), c['votes'], c['name'])
            self.assertEqual(set(c['by_method']), {'election_day', 'advance', 'absentee_mail', 'provisional'})

    def test_all_14_house_districts_and_measures_found(self):
        keys = {c['key'] for c in self.state}
        for d in range(1, 15):
            self.assertIn(f'GA-{d:02d}', keys)
        self.assertTrue({'GA-AMEND1', 'GA-AMEND2', 'GA-REFA'} <= keys)

    def test_ignores_untracked_contests(self):
        self.assertFalse(any('State Senate' in c['office'] or 'District Attorney' in c['office'] for c in self.state))

    def test_counties_complete_and_sum_to_statewide(self):
        self.assertEqual(len(self.counties), 159)
        pres = next(c for c in self.state if c['key'] == 'GA-PRES')
        for cand in pres['candidates']:
            tot = sum(next(x['votes'] for x in co['candidates'] if x['name'] == cand['name']) for co in self.counties)
            self.assertEqual(tot, cand['votes'], cand['name'])
        self.assertEqual(self.prec['units'], self.prec['total'])

    def test_gwinnett_county(self):
        g = next(c for c in self.counties if c['county'] == 'Gwinnett')
        by = {c['name']: c for c in g['candidates']}
        self.assertGreater(by['Kamala D. Harris']['votes'], by['Donald J. Trump']['votes'])
        self.assertEqual(g['reporting']['units'], g['reporting']['total'])
        self.assertAlmostEqual(sum(c['pct'] for c in g['candidates']), 100, delta=0.1)

    def test_incumbent_marker_stripped(self):
        self.assertEqual(ga.split_name('Fani T. Willis (I) (Dem)'), ('Fani T. Willis', 'D', True))
        self.assertEqual(ga.split_name('Yes'), ('Yes', None, False))


class TestGeorgiaRunoff2026(unittest.TestCase):
    def test_primary_runoff_contest_names_do_not_collide(self):
        # Primary contests are named "US Senate - Rep" etc.; they must not be mistaken for the general-election race.
        st = ga.parse_statewide(load('ga_20260616_runoff_data.json.gz'), '06162026GeneralPrimaryRunoff')
        self.assertEqual(st, [])

    def test_runoff_raw_has_senate_primary(self):
        d = load('ga_20260616_runoff_data.json.gz')
        b = next(b for b in d['ballotItems'] if b['name'][0]['text'] == 'US Senate - Rep')
        opts = ga.options(b['summaryResults']['ballotOptions'], b['voteTotal'])
        self.assertEqual({o['name'] for o in opts}, {'Mike Collins', 'Derek Dooley'})
        self.assertAlmostEqual(sum(o['pct'] for o in opts), 100, delta=0.1)


class TestGeorgiaPolling(unittest.TestCase):
    def test_live_feed_detection(self):
        op = opener_for({'/jurisdictions/Georgia': 'ga_jurisdiction.json.gz'})
        self.assertEqual(ga.find_election('2024-11-05', opener=op), '2024NovGen')
        self.assertIsNone(ga.find_election('2026-11-03', opener=op))  # not published yet as of the fixture

    def test_poll_skips_download_when_version_unchanged(self):
        op = opener_for({'/elections/Georgia/2024NovGen': 'ga_2024NovGen_meta.json.gz'})
        meta = ga.election_meta('2024NovGen', opener=op)
        contests, meta2 = ga.poll('2024NovGen', prev_version=meta['version'], opener=op)
        self.assertIsNone(contests)

    def test_full_poll_cycle(self):
        op = opener_for({'/elections/Georgia/2024NovGen': 'ga_2024NovGen_meta.json.gz',
                         '/elections/Georgia/2024NovGen/data': 'ga_2024NovGen_data.json.gz',
                         '/data/ballot-item/01000000-d884-2e72-6367-08dcda4b86b5': 'ga_2024NovGen_pres_counties.json.gz'})
        contests, meta = ga.poll('2024NovGen', county_keys=('GA-PRES',), opener=op)
        pres = next(c for c in contests if c['key'] == 'GA-PRES')
        self.assertEqual(len(pres['counties']), 159)
        self.assertEqual(pres['source']['kind'], 'official')


if __name__ == '__main__':
    unittest.main()
