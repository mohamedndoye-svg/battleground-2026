import sys, io, pandas as pd, warnings; warnings.filterwarnings('ignore')
f=sys.argv[1]; kw=sys.argv[2].lower() if len(sys.argv)>2 else ''
ts=pd.read_html(f)
for i,t in enumerate(ts):
    cols=' | '.join(map(str,t.columns))[:300]
    if kw in cols.lower(): print(i, t.shape, cols)
