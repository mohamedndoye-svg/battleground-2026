"""Extract Cook / Inside Elections / Sabato ratings from Wikipedia's 2026 Senate, House and governor ratings tables.

Usage: extract_ratings.py <senate_html> <house_html> <governor_html> <out_json>
"""
import sys, json, re, warnings
import pandas as pd
warnings.filterwarnings('ignore')
senate_html, house_html, gov_html, out = sys.argv[1:5]

def norm(r):
    r = str(r).strip()
    return 'Toss-up' if r.lower().startswith('toss') else r

def pick(t, prefix):
    col = next(c for c in t.columns if c.startswith(prefix))
    m = re.search(r'([A-Z][a-z]{2})\.? (\d+), (\d{4})', col)
    return col, f'{m.group(1)} {m.group(2)}, {m.group(3)}'

res = {}
for chamber, f, key in [('senate', senate_html, 'State'), ('house', house_html, 'District'), ('governor', gov_html, 'State')]:
    ts = pd.read_html(f, flavor='lxml')
    t = next(x for x in ts if any('Cook' in str(c) for c in x.columns))
    t.columns = [c[1] for c in t.columns]
    cols = {r: pick(t, p) for r, p in [('cook', 'Cook'), ('ie', 'IE'), ('sabato', 'Sabato')]}
    rows = {}
    for _, r in t.iterrows():
        k = str(r[key]).replace('\xa0', ' ')
        if k.startswith('Overall'):
            rows['_overall'] = {n: str(r[c]) for n, (c, _) in cols.items()}
            continue
        rows[k] = {'pvi': str(r[t.columns[1]]), 'incumbent': str(r[t.columns[2]]), 'last': str(r[t.columns[3]]),
                   **{n: norm(r[c]) for n, (c, _) in cols.items()}}
    res[chamber] = {'as_of': {n: d for n, (_, d) in cols.items()}, 'rows': rows}
json.dump(res, open(out, 'w'), indent=1)
print({c: (len(v['rows']), v['as_of'], v['rows']['_overall']) for c, v in res.items()})
