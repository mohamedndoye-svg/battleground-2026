"""Election-night poller. Polls every official source on its own schedule, with exponential backoff on failure,
and writes site/live/live.json after every cycle. Each source fails on its own; one bad feed never stops the rest.

Usage:
  python3 -m live.poller --out site/live --duration 330        # run ~5.5 hours (GitHub Actions job)
  python3 -m live.poller --out site/live --once                # one cycle
State (versions, health, last good results) persists in <out>/state.json, so a new job picks up where the last left off.
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
from .common import log, write_json, now_iso, FetchError
from .sources import build_sources
from . import combine

MAX_BACKOFF = 30 * 60


def load(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def poll_source(src, st, clock=time.time):
    st['last_attempt'] = now_iso()
    try:
        res, ver = src.poll(st)
        if res == 'not_live':
            st.update(status='not_live', last_ok=now_iso(), consecutive_failures=0, last_error=None)
            log('not_live', source=src.id)
        else:
            st.update(status='ok', last_ok=now_iso(), consecutive_failures=0, last_error=None)
            if res is not None:
                st['contests'], st['version'], st['last_change'] = res, ver, now_iso()
                log('updated', source=src.id, version=ver, contests=len(res))
            else:
                log('unchanged', source=src.id, version=ver)
        delay = src.interval
    except (FetchError, ValueError, KeyError, TypeError, OSError) as e:
        n = st.get('consecutive_failures', 0) + 1
        st.update(status='error', consecutive_failures=n, last_error=f'{type(e).__name__}: {str(e)[:300]}')
        delay = min(src.interval * 2 ** n, MAX_BACKOFF)
        log('source_error', source=src.id, failures=n, retry_in_s=delay, error=st['last_error'])
    st['next_due'] = clock() + delay


def publish(cmd, state):
    """Run the publish hook (e.g. git push to gh-pages). Its failure is logged and never stops polling."""
    import subprocess
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=240)
        log('publish', ok=r.returncode == 0, rc=r.returncode, out=(r.stdout + r.stderr)[-300:])
        if r.returncode == 0:
            state['last_published'] = now_iso()
    except Exception as e:
        log('publish', ok=False, error=str(e)[:300])


def run(out, duration_min=None, once=False, root=None, sleep=time.sleep, clock=time.time, publish_cmd=None, publish_every=360):
    root = root or os.path.join(os.path.dirname(__file__), '..')
    races = load(os.path.join(root, 'data', 'races.json'), {'races': []})
    ga_json = load(os.path.join(root, 'data', 'ga.json'), {})
    state_path = os.path.join(out, 'state.json')
    state = load(state_path, {'sources': {}})
    sources = build_sources()
    end = clock() + duration_min * 60 if duration_min else None
    while True:
        for s in sources:
            st = state['sources'].setdefault(s.id, {})
            if once or clock() >= st.get('next_due', 0):
                poll_source(s, st, clock)
        secondary = load(os.path.join(out, 'secondary.json'), {})
        live = combine.build(races, ga_json, state, sources, secondary, now=datetime.fromtimestamp(clock(), timezone.utc))
        write_json(os.path.join(out, 'live.json'), live)
        write_json(state_path, state)
        if publish_cmd and (once or clock() - state.get('_published_at', 0) >= publish_every):
            state['_published_at'] = clock()
            publish(publish_cmd, state)
        if once or (end and clock() >= end):
            return live
        nxt = min(st.get('next_due', 0) for st in state['sources'].values())
        sleep(max(5, min(60, nxt - clock())))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='site/live')
    ap.add_argument('--duration', type=float, help='minutes to run')
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--publish-cmd', help='shell command run after a cycle to publish site/ (rate-limited)')
    ap.add_argument('--publish-every', type=int, default=360, help='seconds between publishes (GitHub Pages: ~10 builds/hour)')
    a = ap.parse_args(argv)
    live = run(a.out, a.duration, a.once, publish_cmd=a.publish_cmd, publish_every=a.publish_every)
    print(json.dumps({s['id']: s['health'] for s in live['sources']}))


if __name__ == '__main__':
    main()
