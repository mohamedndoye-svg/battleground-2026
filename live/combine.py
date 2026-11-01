"""Turn per-source results into the single live.json the page reads.

Rules:
- Official state numbers win. A secondary value (secondary.json, e.g. filled by a person or a future search agent)
  is used only where no official source has the race; if both exist and any candidate differs by more than
  DISCREPANCY_PCT, the official number is shown with a discrepancy flag carrying both values.
- Every race carries its source, fetched_at and the source's last successful check; anything whose source has not
  been checked successfully for STALE_MIN minutes is marked stale.
- Race calls are only ever copied from a named outlet in secondary.json (AP, NBC, CNN, Fox, ABC, CBS, DDHQ).
  Nothing here projects a winner.
"""
from datetime import datetime, timezone
from .rules import STATES, recount_check, majority_check, CLOSINGS_SOURCE
from .sources import RACE_OF, NO_FEED

STALE_MIN = 20
DISCREPANCY_PCT = 0.5   # percent of a candidate's official votes
OUTLETS = {'AP', 'NBC', 'CNN', 'Fox', 'ABC', 'CBS', 'DDHQ'}


def _ts(s):
    try:
        return datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def minutes_since(s, now):
    t = _ts(s)
    return None if t is None else (now - t).total_seconds() / 60


def is_stale(iso, now):
    m = minutes_since(iso, now)
    return m is None or m > STALE_MIN


def health_of(src_state, now, interval):
    """green: checked OK recently; yellow: last attempt failed or feed not live yet; red: no success for STALE_MIN."""
    ok = minutes_since(src_state.get('last_ok'), now)
    if src_state.get('status') == 'not_live':
        return 'yellow'
    if ok is None or ok > STALE_MIN:
        return 'red'
    if src_state.get('consecutive_failures', 0) > 0 or ok > 2 * interval / 60 + 1:
        return 'yellow'
    return 'green'


def summarize(contest):
    cands = [c for c in contest['candidates'] if not c.get('write_in')]
    s = sorted(cands, key=lambda c: -(c['votes'] or 0))
    rep = contest.get('reporting_precincts') or contest.get('reporting') or {}
    share = (rep.get('units') / rep['total']) if rep.get('total') else None
    d = next((c for c in contest['candidates'] if c.get('party') == 'D'), None)
    r = next((c for c in contest['candidates'] if c.get('party') == 'R'), None)
    i = next((c for c in contest['candidates'] if c.get('party') == 'I'), None)
    left = d or i
    margin = round(left['pct'] - r['pct'], 2) if left and r and left.get('pct') is not None and r.get('pct') is not None else None
    return {'leader': s[0]['name'] if s and s[0]['votes'] else None, 'leader_party': s[0].get('party') if s and s[0]['votes'] else None,
            'margin_dr': margin, 'reporting_share': share, 'reporting': rep, 'total_votes': contest.get('total_votes') or 0}


def disagreement(official, secondary):
    out = []
    sec = {c['name'].split()[-1].lower(): c for c in secondary.get('candidates', [])}
    for c in official['candidates']:
        o = sec.get(c['name'].split()[-1].lower())
        if o and c['votes'] and abs(o['votes'] - c['votes']) / c['votes'] * 100 > DISCREPANCY_PCT:
            out.append({'candidate': c['name'], 'official': c['votes'], 'secondary': o['votes'], 'secondary_source': secondary.get('source')})
    return out


def build(races_json, ga_json, state, sources, secondary=None, now=None):
    now = now or datetime.now(timezone.utc)
    now_s = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    secondary = secondary or {}
    src_info = {}
    for s in sources:
        st = state['sources'].get(s.id, {})
        src_info[s.id] = {'id': s.id, 'state': s.state, 'name': s.name, 'url': s.url, 'kind': 'official',
                          'health': health_of(st, now, s.interval), 'status': st.get('status', 'never_polled'),
                          'last_ok': st.get('last_ok'), 'last_attempt': st.get('last_attempt'), 'last_change': st.get('last_change'),
                          'last_error': st.get('last_error'), 'consecutive_failures': st.get('consecutive_failures', 0),
                          'election_id': st.get('eid'), 'version': st.get('version')}
    for stc, why in NO_FEED.items():
        src_info['none-' + stc] = {'id': 'none-' + stc, 'state': stc, 'name': f'{STATES[stc]["name"]}: no automated source', 'kind': 'none',
                                   'health': 'red', 'status': 'no_feed', 'reason': why}

    by_contest = {}
    for sid, st in state['sources'].items():
        for c in st.get('contests') or []:
            by_contest[c['key']] = (sid, c)

    meta = {r['id']: r for r in races_json['races']}
    out_races = {}
    for rid, r in meta.items():
        stc = next((k for k, v in STATES.items() if v['name'] == r['state'].split(' (')[0]), None)
        ckey = next((k for k, v in RACE_OF.items() if v == rid), None)
        entry = {'id': rid, 'state': stc, 'label': r['label'], 'chamber': r['chamber'],
                 'poll_avg_dr': r.get('consensus'), 'pres2024_margin_r': (r.get('pres2024') or {}).get('margin_r'),
                 'closes': {'first': STATES.get(stc, {}).get('first'), 'last': STATES.get(stc, {}).get('last'), 'source': CLOSINGS_SOURCE},
                 'result': None, 'source': None, 'stale': None, 'flags': {}, 'call': None, 'discrepancy': None, 'notes': []}
        sec = secondary.get('races', {}).get(rid)
        if ckey and ckey in by_contest:
            sid, c = by_contest[ckey]
            entry['result'] = {k: c[k] for k in ('candidates', 'total_votes', 'reporting', 'office') if k in c}
            entry['result']['reporting_precincts'] = c.get('reporting_precincts')
            entry['source'] = {**c['source'], 'last_checked': state['sources'][sid].get('last_ok'), 'feed': sid}
            entry['stale'] = is_stale(state['sources'][sid].get('last_ok'), now)
            if sec and sec.get('candidates'):
                dis = disagreement(c, sec)
                if dis:
                    entry['discrepancy'] = dis
        elif sec and sec.get('candidates'):
            entry['result'] = {'candidates': sec['candidates'], 'total_votes': sum(x['votes'] for x in sec['candidates']), 'reporting': sec.get('reporting')}
            entry['source'] = {'name': sec.get('source'), 'kind': 'secondary', 'url': sec.get('url'), 'fetched_at': sec.get('extracted_at')}
            entry['stale'] = is_stale(sec.get('extracted_at'), now)
        else:
            entry['notes'].append(NO_FEED.get(stc, 'Official feed not live yet') if stc in NO_FEED else 'Official feed not live yet')
        if sec and sec.get('call') and sec['call'].get('outlet') in OUTLETS:
            entry['call'] = sec['call']   # {'winner','party','outlet','called_at','url'}
        if sec and sec.get('outstanding_note'):
            entry['notes'].append(sec['outstanding_note'])
        if entry['result'] and entry['result']['candidates']:
            sm = summarize({'candidates': entry['result']['candidates'], 'total_votes': entry['result']['total_votes'],
                            'reporting': entry['result'].get('reporting'), 'reporting_precincts': entry['result'].get('reporting_precincts')})
            entry.update(sm)
            if sm['margin_dr'] is not None:
                entry['vs_poll'] = round(sm['margin_dr'] - r['consensus'], 2) if r.get('consensus') is not None else None
                pres = entry['pres2024_margin_r']
                entry['vs_pres'] = round(sm['margin_dr'] + pres, 2) if pres is not None else None  # pres stored as R-minus-D
            entry['flags']['recount'] = recount_check(stc, entry['result']['candidates'], entry['result']['total_votes'])
            entry['flags']['majority'] = majority_check(stc, r['chamber'], entry['result']['candidates'], entry['result']['total_votes'], sm['reporting_share'])
        out_races[rid] = entry

    # Georgia: every statewide contest, House district and measure, with counties
    ga_out = []
    ga_src = state['sources'].get('ga', {})
    for c in ga_src.get('contests') or []:
        if c['key'] == 'GA-PRES':
            continue
        sm = summarize(c)
        rt = 'governor' if c['key'] == 'GA-GOV' else 'senate' if c['key'] == 'GA-SEN' else 'other'
        ga_out.append({**{k: c[k] for k in ('key', 'office', 'candidates', 'total_votes', 'reporting', 'source', 'contest_type') if k in c},
                       'reporting_precincts': c.get('reporting_precincts'), 'counties': c.get('counties'),
                       **sm, 'stale': is_stale(ga_src.get('last_ok'), now),
                       'flags': {'recount': recount_check('GA', c['candidates'], c.get('total_votes')),
                                 'majority': majority_check('GA', rt, c['candidates'], c.get('total_votes'), sm['reporting_share'])
                                 if not c['key'].startswith(('GA-AMEND', 'GA-REF')) else None}})
    return {'generated_at': now_s, 'election_date': '2026-11-03', 'stale_after_min': STALE_MIN,
            'sources': list(src_info.values()), 'races': out_races, 'ga': {'contests': ga_out, 'election_id': ga_src.get('eid'),
            'official_updates': secondary.get('ga_updates', [])},
            'calls_note': 'Race calls appear only when a named outlet (AP, NBC, CNN, Fox, ABC, CBS, DDHQ) is recorded in secondary.json. The search agent is not enabled, so no calls are recorded automatically.',
            'expected_vote_note': 'No official source publishes an expected-vote estimate; precincts or counties reporting are shown instead.'}
