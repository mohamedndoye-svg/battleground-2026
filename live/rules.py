"""State rules used on election night: poll closings, majority/runoff rules, recount margins.

Poll closings: 270toWin "2026 Poll Closing Times" (Eastern; Nov 3 is on standard time).
    https://www.270towin.com/poll-closing-times  (retrieved 2026-11-01)
    `first` = first polls close in the state, `last` = all polls closed. Times are 24h Eastern on 2026-11-03;
    times >= 24 are after midnight.
Recounts: Verified Voting recount law database, https://verifiedvoting.org/recountlaw/{state}/ (retrieved 2026-11-01),
    which quotes each statute. `basis` says what the percentage is measured against.
These are rule look-ups applied to official counts, never projections.
"""

VV = 'https://verifiedvoting.org/recountlaw/'
CLOSINGS_SOURCE = 'https://www.270towin.com/poll-closing-times'

STATES = {
    # state: name, first/last poll close (ET hours), recount rule, majority rule
    'GA': {'name': 'Georgia', 'first': 19, 'last': 19,
           'recount': {'type': 'request', 'pct': 0.5, 'basis': 'total', 'text': 'A losing candidate may request a recount if the margin is 0.5% or less.', 'cite': 'O.C.G.A. § 21-2-495', 'url': VV + 'georgia/'},
           'majority': {'type': 'runoff', 'threshold': 50.0, 'date': '2026-12-01',
                        'text': 'A candidate needs a majority (50% + 1). Otherwise the top two meet in a runoff on December 1, 2026.',
                        'url': 'https://georgia.gov/georgia-election-guide'}},
    'SC': {'name': 'South Carolina', 'first': 19, 'last': 19,
           'recount': {'type': 'automatic', 'pct': 1.0, 'basis': 'total', 'text': 'Automatic recount when the margin is under 1% of votes cast.', 'url': VV + 'south-carolina/'}},
    'VT': {'name': 'Vermont', 'first': 19, 'last': 19,
           'recount': {'type': 'request', 'pct': 2.0, 'basis': 'total', 'text': 'A losing statewide candidate may request a recount if the margin is 2% or less.', 'cite': 'Vt. Stat. Ann. tit. 17, § 2601', 'url': VV + 'vermont/'},
           'majority': {'type': 'legislature', 'threshold': 50.0, 'races': ['governor'],
                        'text': 'If no candidate for governor wins a majority, the Vermont General Assembly chooses the governor.',
                        'url': 'https://en.wikipedia.org/wiki/Governor_of_Vermont'}},
    'FL': {'name': 'Florida', 'first': 19, 'last': 20,
           'recount': {'type': 'automatic', 'pct': 0.5, 'basis': 'total', 'text': 'Automatic recount when the margin is 0.5% or less.', 'url': VV + 'florida/'}},
    'NC': {'name': 'North Carolina', 'first': 19.5, 'last': 19.5,
           'recount': {'type': 'request', 'pct': 0.5, 'votes_cap': 10000, 'basis': 'total', 'text': 'A candidate may demand a recount if the margin is 0.5% or 10,000 votes, whichever is less.', 'cite': 'N.C. Gen. Stat. § 163-182.7(c)', 'url': VV + 'north-carolina/'}},
    'OH': {'name': 'Ohio', 'first': 19.5, 'last': 19.5,
           'recount': {'type': 'automatic', 'pct': 0.25, 'basis': 'total', 'text': 'Automatic recount in a statewide race when the margin is 0.25% or less.', 'url': VV + 'ohio/'}},
    'ME': {'name': 'Maine', 'first': 20, 'last': 20,
           'recount': {'type': 'request', 'pct': 1.0, 'votes_cap': 1000, 'basis': 'total', 'text': 'Taxpayer-funded recount on request if the margin is 1% or less and not more than 1,000 votes.', 'url': VV + 'maine/'},
           'majority': {'type': 'rcv', 'threshold': 50.0, 'races': ['senate'],
                        'text': 'Maine uses ranked-choice voting for U.S. Senate. If no candidate has a majority of first choices, ballots are retabulated centrally, usually a week or more after Election Day.',
                        'url': 'https://en.wikipedia.org/wiki/Ranked-choice_voting_in_Maine'}},
    'MI': {'name': 'Michigan', 'first': 20, 'last': 21,
           'recount': {'type': 'automatic', 'pct': 0.1, 'basis': 'total', 'text': 'Automatic recount in a statewide race when the margin is 0.1% or less.', 'url': VV + 'michigan/'}},
    'NH': {'name': 'New Hampshire', 'first': 19, 'last': 20,
           'recount': {'type': 'request', 'pct': 20.0, 'basis': 'total', 'text': 'Any losing candidate within 20% may apply for a recount (fees apply outside narrow margins).', 'cite': 'N.H. Rev. Stat. Ann. § 660:1', 'url': VV + 'new-hampshire/'}},
    'KS': {'name': 'Kansas', 'first': 20, 'last': 21,
           'recount': {'type': 'request', 'pct': 0.5, 'basis': 'total', 'text': 'A candidate may petition for a taxpayer-funded recount if the margin is 0.5% or less.', 'url': VV + 'kansas/'}},
    'TX': {'name': 'Texas', 'first': 20, 'last': 21,
           'recount': {'type': 'request', 'pct': None, 'basis': None, 'text': 'Automatic only for a tie. Candidates may request a recount after the canvass; see source for the margin rules.', 'url': VV + 'texas/'}},
    'IA': {'name': 'Iowa', 'first': 21, 'last': 21,
           'recount': {'type': 'request', 'pct': 0.15, 'basis': 'total', 'text': 'Statewide and federal candidates may request a taxpayer-funded recount if the margin is under 0.15%.', 'url': VV + 'iowa/'}},
    'AZ': {'name': 'Arizona', 'first': 21, 'last': 21,
           'recount': {'type': 'automatic', 'pct': 0.5, 'basis': 'top_two', 'text': 'Automatic recount when the margin between the top two is 0.5% or less.', 'url': VV + 'arizona/'}},
    'MN': {'name': 'Minnesota', 'first': 21, 'last': 21,
           'recount': {'type': 'request', 'pct': 0.25, 'basis': 'total', 'text': 'A losing candidate may request a recount if the margin is 0.25% or less.', 'url': VV + 'minnesota/'}},
    'NE': {'name': 'Nebraska', 'first': 21, 'last': 21,
           'recount': {'type': 'automatic', 'pct': 1.0, 'basis': 'winner', 'text': 'Automatic recount when the margin is 1% or less of the winner\'s votes.', 'url': VV + 'nebraska/'}},
    'WI': {'name': 'Wisconsin', 'first': 21, 'last': 21,
           'recount': {'type': 'request', 'pct': 0.25, 'basis': 'total', 'text': 'Taxpayer-funded recount on petition if the margin is 0.25% or less (paid by the candidate up to 1%).', 'url': VV + 'wisconsin/'}},
    'NV': {'name': 'Nevada', 'first': 22, 'last': 22,
           'recount': {'type': 'request', 'pct': None, 'basis': None, 'text': 'No automatic recount; any candidate may request one with no margin requirement.', 'url': VV + 'nevada/'}},
    'OR': {'name': 'Oregon', 'first': 22, 'last': 23,
           'recount': {'type': 'automatic', 'pct': 0.2, 'basis': 'top_two', 'text': 'Automatic recount when the margin is 0.2% or less of the votes for the top two.', 'url': VV + 'oregon/'}},
    'AK': {'name': 'Alaska', 'first': 24, 'last': 25,
           'recount': {'type': 'request', 'pct': None, 'basis': None, 'text': 'Automatic only for a tie; a defeated candidate may request a recount.', 'url': VV + 'alaska/'},
           'majority': {'type': 'rcv', 'threshold': 50.0, 'races': ['senate', 'governor'],
                        'text': 'Alaska uses ranked-choice voting in general elections. If no candidate has a majority of first choices, the ranked-choice count is run after all ballots arrive, about two weeks after Election Day.',
                        'url': 'https://en.wikipedia.org/wiki/2020_Alaska_Measure_2'}},
}


def recount_check(state, cands, total=None):
    """Return a recount flag for the top two candidates, or None. Uses the state's own basis for the percentage."""
    rule = STATES.get(state, {}).get('recount')
    s = sorted([c for c in cands if not c.get('write_in')], key=lambda c: -(c['votes'] or 0))
    if not rule or len(s) < 2 or not s[0]['votes']:
        return None
    diff = s[0]['votes'] - s[1]['votes']
    if rule['pct'] is None:
        return {'within': diff == 0, 'diff_votes': diff, 'rule': rule, 'note': 'tie' if diff == 0 else None}
    base = {'total': total or sum(c['votes'] for c in cands), 'top_two': s[0]['votes'] + s[1]['votes'],
            'winner': s[0]['votes']}[rule['basis']]
    pct = 100 * diff / base if base else None
    within = pct is not None and pct <= rule['pct'] and (rule.get('votes_cap') is None or diff <= rule['votes_cap'])
    return {'within': within, 'diff_votes': diff, 'diff_pct': round(pct, 3) if pct is not None else None, 'rule': rule}


def majority_check(state, race_type, cands, total=None, reporting_share=None):
    """Runoff / RCV / legislature watch. 'likely' is a fixed, published rule: leader under the threshold with at least
    95% of reporting units in. It is a flag, not a projection."""
    m = STATES.get(state, {}).get('majority')
    if not m or (m.get('races') and race_type not in m['races']):
        return None
    total = total or sum(c['votes'] for c in cands)
    s = sorted(cands, key=lambda c: -(c['votes'] or 0))
    if not s or not total:
        return {'type': m['type'], 'rule': m, 'leader_pct': None, 'above': None, 'likely': False}
    lp = 100 * s[0]['votes'] / total
    above = lp > m['threshold']
    return {'type': m['type'], 'rule': m, 'leader': s[0]['name'], 'leader_pct': round(lp, 2), 'above': above,
            'likely': (not above) and reporting_share is not None and reporting_share >= 0.95}
