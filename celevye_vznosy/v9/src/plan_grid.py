"""Speech-driven timeline on a steady grid, before the music exists: total length and scene times for the music order."""
import sys, json, numpy as np
sys.path.insert(0, __import__('os').path.dirname(__file__))
import audio as A
bpm = float(sys.argv[1]) if len(sys.argv) > 1 else 107.0
P = 60 / bpm; t0 = 0.5
beats = [(t0 + i * P, i) for i in range(int(400 / P))]
tl, t_end = A.build(beats, {'15': None} and {}, {'15': 0.25})
total = t_end + 6.8
bar = 4 * P
for d in tl:
    if d['kind'] != 'intra':
        print('%-6s cut %7.2f  bar %6.2f  speech %s' % (d['name'], d['cut'], (d['cut'] - t0) / bar + 1, '%.2f-%.2f' % (d['t0'], d['t1']) if 't0' in d else ''))
print('last word %.2f  total %.2f  (%.2f bars of %.3f s)' % (t_end, total, (total - t0) / bar, bar))
json.dump(dict(timeline=tl, total=total, bpm=bpm), open(A.W + 'plan_grid.json', 'w'), indent=1)
