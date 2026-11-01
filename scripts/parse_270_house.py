"""Parse 270toWin's 2026 House page: incumbent, 2024 House margin, 2024 presidential margin, candidates per district."""
import re, json, sys
from bs4 import BeautifulSoup
h = open(sys.argv[1]).read()
s = BeautifulSoup(h, 'lxml')
out = {}
for tr in s.select('tr[district_id_combo]'):
    sd = tr.select_one('td.state_district')
    combo = tr['district_id_combo']
    if sd:
        code = re.sub(r'\s+', '', sd.get_text())
        st, num = code.split('-')
        num = 'AL' if num in ('', 'AL', '0') else num
        m = tr.select('td.margin_victory')
        def mg(td):
            t = td.get_text(strip=True)
            if not re.search(r'\d', t): return None
            v = float(re.sub(r'[^\d.]', '', t))
            side = 'R' if 'red' in td.get('style', '') else 'D' if 'blue' in td.get('style', '') else '?'
            return {'party': side, 'pts': v, 'raw': t}
        party = 'R' if '#D22532' in str(tr.select_one('td.rep_party')) else 'D' if tr.select_one('td.rep_party') and '#' in str(tr.select_one('td.rep_party')) else None
        out[combo] = {'id': f'{st}-{num}', 'incumbent': tr.select_one('td.rep_name').get_text(strip=True),
                      'house2024': mg(m[0]) if len(m) > 0 else None, 'pres2024': mg(m[1]) if len(m) > 1 else None,
                      'competitive_270': tr.get('is_competitive') == '1', 'candidates': []}
    else:
        cl = tr.select('div.candidate-list div')
        if combo in out and cl:
            for d in cl:
                cls = ' '.join(d.get('class', []))
                p = re.search(r'fill-(\w+)', cls)
                out[combo]['candidates'].append({'name': d.get_text(strip=True), 'fill': p.group(1) if p else None})
            fn = tr.select_one('div.footnote')
            out[combo]['note'] = fn.get_text(' ', strip=True) if fn else ''
print(json.dumps({v['id']: v for v in out.values()}, indent=0))
