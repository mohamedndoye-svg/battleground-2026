# Battleground 2026

A mobile-first tracker for the 2026 midterms with two views:

- **Georgia** (pinned first): rules (50% + 1, December 1 runoff, 0.5-point recount request), early-vote turnout by county vs. 2022, every statewide race with polls, the three constitutional amendments, and all 14 U.S. House districts (Gwinnett: GA-4, 9, 10, 13).
- **National**: Senate control with the VP tiebreak and tap-to-assign scenarios, a path-to-majority ladder, a House summary by rater, and the competitive governor races with short analyses.

Live page (private to the owner until shared): https://claude.ai/artifact/SrdHWSCjXebv8RzNPy7Jws

## Files

| Path | What it is |
|---|---|
| `index.html` | The whole page. Loads `races.json` and `ga.json` from the same folder. |
| `data/races.json` | Senate and governor races, control math inputs. Hand-editable. |
| `data/ga.json` | Georgia races, House districts, turnout, rules. |
| `data/gov_analysis.json` | Hand-written governor analyses, merged in at build time. |
| `data/raw/` | Intermediate data: ratings, 270toWin House data, 2024 results by state (static). |
| `scripts/` | Fetch and build scripts (below). |

## Refreshing the data

```sh
bash scripts/fetch_sources.sh                       # downloads every source page into cache/ (~3 min, polite pacing)
python3 -I scripts/parse_270_house.py cache/w270/house.html > data/raw/h270.json
python3 -I scripts/extract_ratings.py cache/wiki/2026_United_States_Senate_elections.html \
    cache/wiki/house_ratings.html cache/wiki/gov.html data/raw/ratings.json
python3 -I scripts/build_data.py cache/wiki cache/gv data   # ~2 min
python3 -I scripts/build_ga.py   cache/wiki cache/gv data
```

`data/raw/pres2024_state.json` is a fixed snapshot of 2024 presidential results and does not need refreshing.

### Sources and what blocks automated access

- Used: Wikipedia (ratings tables, race pages and polls, each footnoted to the original), 270toWin, georgiavotes.com (built from GA Secretary of State voter files), georgia.gov.
- Blocked by bot walls, so read via Wikipedia's citations or shown as "no data": Cook Political Report, Inside Elections, Sabato's Crystal Ball, RealClearPolling, sos.ga.gov, Ballotpedia.
- Excluded as paid: Silver Bulletin, NYT, Decision Desk HQ API. FiveThirtyEight shut down in 2025.
- No number is estimated. Anything a source doesn't publish shows "no data".

## Next: Election Night mode (not started)

Requested: automated official results for every tracked race and all GA races/counties, polled every 2–5 minutes, hosted on **GitHub Actions + Pages** (long-running job loop of ~5.5 h started hourly, with a concurrency lock, to avoid Actions' cron delays). The search agent was dropped, so race calls by outlet and states without an official feed will show "not recorded" / "no data".

Blocked until the session has full network access. Order of work:

1. Georgia feed: confirm the platform (appears to be `results.sos.ga.gov`, replacing Clarity) and URL pattern; parse the June 16, 2026 runoff and 2024 general, statewide and county level.
2. Feeds for the other tracked states; table of state / feed found / format / URL pattern / parser tested.
3. Poller with backoff, per-source health, fetch log, 20-minute staleness marking, official-over-other precedence with discrepancy flags.
4. Runoff / recount watch from each state's rules.
5. Mock election night: staggered closings, slow counts, a feed outage, a source disagreement, a recount-margin race, a GA race at 49.6%.
