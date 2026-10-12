"""Music edit on bars, speech-driven timeline on real beats, voice/music mix."""
import json, subprocess, re, numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

SR = 48000
W = '/tmp/claude-0/-home-user-ishodniki-video/7fdd3399-3b0b-583b-a74f-2847502fb422/scratchpad/work/'
LEAD = 0.6          # speech starts this long after the cut
REMOVE = [(24, 28), (104, 112)]   # bar ranges removed from the track [a, b)

ITEMS = [('logo', None, 'start'),
 ('01rad', ('01', 0, 0), 'intra'), ('01main', ('01', 1, 3), 'intra'),
 ('02q', ('02', 0, 1), 'scene'), ('02f', ('02', 2, 4), 'intra'),
 ('03a', ('03', 0, 1), 'scene'), ('03b', ('03', 2, 5), 'intra'),
 ('04a', ('04', 0, 4), 'scene'), ('04b', ('04', 5, 7), 'intra'),
 ('05a', ('05', 0, 1), 'scene'), ('05b', ('05', 2, 5), 'intra'),
 ('06a', ('06', 0, 1), 'scene'), ('06b', ('06', 2, 6), 'intra'),
 ('07a', ('07', 0, 1), 'scene'), ('07b', ('07', 2, 3), 'intra'),
 ('08', ('08', 0, 1), 'scene'),
 ('09a', ('09', 0, 0), 'scene'), ('09b', ('09', 1, 2), 'intra'),
 ('10a', ('10', 0, 1), 'scene'), ('10b', ('10', 2, 2), 'intra'), ('10c', ('10', 3, 3), 'intra'),
 ('11', ('11', 0, 1), 'scene'), ('12', ('12', 0, 3), 'scene'),
 ('13a', ('13', 0, 0), 'scene'), ('13b', ('13', 1, 3), 'intra')]
RANGE = {'intra': (1.0, 2.0), 'scene': (2.0, 2.55)}
TARGET = {'intra': 1.4, 'scene': 2.25}


def rd(p):
    sr, x = wavfile.read(p)
    assert sr == SR
    return x.astype(np.float64)


def lufs(x):
    wavfile.write(W + '_m.wav', SR, np.stack([x, x], 1).astype(np.float32))   # measured as delivered: dual-mono stereo
    o = subprocess.run(['ffmpeg', '-nostats', '-i', W + '_m.wav', '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                       capture_output=True, text=True).stderr
    i = float(re.findall(r'I:\s+(-?[\d.]+) LUFS', o)[-1])
    return i


def true_peak_db(x):
    y = resample_poly(x, 4, 1)
    return 20 * np.log10(np.abs(y).max() + 1e-12)


def onset(x, t):
    w = int(0.0025 * SR); i0 = int((t - 0.05) * SR); i1 = int((t + 0.05) * SR)
    e = np.convolve(x[i0:i1] ** 2, np.ones(w) / w, 'same')
    d = np.convolve(np.diff(np.log(e + 1e-10)), np.ones(w), 'same')
    return (i0 + np.argmax(d)) / SR


def edit_music():
    x = rd(W + 'music48.wav')
    beats = np.array(json.load(open(W + 'beats_s.json')))
    db = beats[0::4]
    keep, prev = [], 0.0
    for a, b in REMOVE:
        keep.append((prev, onset(x, db[a])))
        prev = onset(x, db[b])
    keep.append((prev, len(x) / SR))
    xf = int(0.02 * SR); pre = int(0.003 * SR)
    out = np.zeros(0); bmap = []
    for k, (s, e) in enumerate(keep):
        i0 = int(s * SR) - pre - (xf if k else 0)
        i1 = int(e * SR) - pre if k < len(keep) - 1 else len(x)
        seg = x[max(i0, 0):i1].copy()
        offset = (len(out) - (xf if k else 0)) / SR - max(i0, 0) / SR
        if k:
            r = np.linspace(0, np.pi / 2, xf)
            seg[:xf] *= np.sin(r)
            out[-xf:] *= np.cos(r)
            out[-xf:] += seg[:xf]
            out = np.concatenate([out, seg[xf:]])
        else:
            out = seg
        for bi, bt in enumerate(beats):
            if s - 0.01 <= bt < e - 0.01:
                bmap.append((bt + offset, bi))
    return out, bmap


def build(beats, force=None, extra=None):
    """beats: list of (time, orig_index). Cuts land on beats; speech starts LEAD after a cut."""
    force = force or {}; extra = extra or {}
    segs = json.load(open(W + 'segs.json'))
    tl, t_end = [], None
    for name, clip, kind in ITEMS:
        if kind == 'start':
            tl.append(dict(name=name, cut=beats[0][0], kind=kind)); continue
        if t_end is None:
            cut = beats[6][0]
        elif name in force:
            cut = min(beats, key=lambda b: abs(b[0] - force[name]))[0]
        else:
            lo, hi = RANGE[kind]
            cand = [b for b in beats if lo <= b[0] + LEAD - t_end <= hi]
            if kind == 'scene' and [c for c in cand if c[1] % 2 == 0]:
                cand = [c for c in cand if c[1] % 2 == 0]
            tgt = TARGET[kind] + extra.get(name, 0)
            cut = min(cand, key=lambda c: abs(c[0] + LEAD - t_end - tgt))[0]
        f, s0, s1 = clip
        a, b = segs[f][s0][0], segs[f][s1][1]
        t0 = cut + LEAD
        d = dict(name=name, kind=kind, cut=float(cut), vo=f, segs=[s0, s1], a=a, b=b, t0=t0, t1=t0 + b - a,
                 pause=None if t_end is None else t0 - t_end)
        if d['pause'] is not None and not (RANGE[kind][0] - 0.05 <= d['pause'] <= RANGE[kind][1] + 0.05):
            print('WARN pause', name, round(d['pause'], 2))
        tl.append(d); t_end = d['t1']
    return tl, t_end


def voice_stem(tl, total):
    segs = json.load(open(W + 'segs.json'))
    files = {}
    for k in range(1, 14):
        f = '%02d' % k
        x = rd(W + 'vo/%s.wav' % f)
        files[f] = x * 10 ** ((-18.6 - lufs(x)) / 20)   # equalise takes
    v = np.zeros(int(total * SR) + SR)
    for d in tl:
        if d['kind'] == 'start':
            continue
        x = files[d['vo']]; sg = segs[d['vo']]
        pre, post = 0.06, 0.14
        nxt = sg[d['segs'][1] + 1][0] if d['segs'][1] + 1 < len(sg) else len(x) / SR
        a = max(0, d['a'] - pre); b = min(len(x) / SR, d['b'] + post, nxt - 0.04)
        c = x[int(a * SR):int(b * SR)].copy()
        fi, fo = int(0.01 * SR), int(0.05 * SR)
        c[:fi] *= np.linspace(0, 1, fi); c[-fo:] *= np.linspace(1, 0, fo)
        i = int((d['t0'] - (d['a'] - a)) * SR)
        v[i:i + len(c)] += c
    return v


def main():
    m, bmap = edit_music()
    wavfile.write(W + 'music_edit.wav', SR, m.astype(np.float32))
    # musical landmarks after the edit
    lm = {ob: t for t, ob in bmap}
    db = lambda bar: lm[bar * 4]
    force = {'07b': None, '08': db(71), '09a': db(77)}
    # 07b: one beat later than greedy so that 08 lands on the breakdown downbeat
    tl, _ = build(bmap, {'08': db(71), '09a': db(77)})
    c07 = [d for d in tl if d['name'] == '07b'][0]['cut']
    later = [t for t, _ in bmap if t > c07 + 0.3][0]
    force = {'07b': later, '08': db(71), '09a': db(77)}
    tail = db(125)
    extra = {}
    for it in range(12):
        tl, t_end = build(bmap, force, extra)
        gap = tail - t_end
        if gap < 0.3:
            break
        for n in ['10a', '11', '12', '13a', '10b', '10c', '13b', '09b']:
            extra[n] = extra.get(n, 0) + 0.12
    total = round((t_end + 6.8) * 25) / 25
    print('tail start %.2f, last word %.2f, end %.2f, music len %.2f' % (tail, t_end, total, len(m) / SR))
    for d in tl:
        print('%-7s cut %7.2f  speech %7.2f-%7.2f  pause %s' % (d['name'], d['cut'], d.get('t0', 0), d.get('t1', 0),
              '' if d.get('pause') is None else '%.2f' % d['pause']))
    v = voice_stem(tl, total)
    n = int(total * SR)
    v = v[:n]; m = np.concatenate([m, np.zeros(max(0, n - len(m)))])[:n]
    # loudness: voice -15.5, music under speech 12.5 LU below
    v *= 10 ** ((-15.5 - lufs(v)) / 20)
    speech = np.zeros(n, bool)
    for d in tl:
        if d['kind'] != 'start':
            speech[int(d['t0'] * SR):int(d['t1'] * SR)] = True
    mu = m[speech]
    g_under = 10 ** ((-15.5 - 12.5 - lufs(mu)) / 20)
    # duck envelope: +3 dB in pauses longer than 1 s, smooth ramps
    lift = np.zeros(n)
    t = np.arange(n) / SR
    spans = [(d['t0'], d['t1']) for d in tl if d['kind'] != 'start']
    pauses = [(0, spans[0][0])] + [(spans[i][1], spans[i + 1][0]) for i in range(len(spans) - 1)] + [(spans[-1][1], total)]
    for a, b in pauses:
        if b - a < 1.0:
            continue
        up0, up1 = a + 0.25, a + 0.75
        dn0, dn1 = b - 0.55, b - 0.1
        if a == 0:
            up0 = up1 = 0
        if b >= total - 0.01:
            dn0 = dn1 = total + 1
        env = np.clip(np.minimum((t - up0) / max(up1 - up0, 1e-3), (dn1 - t) / max(dn1 - dn0, 1e-3)), 0, 1)
        env[(t < up0) | (t > dn1)] = 0
        lift = np.maximum(lift, 0.5 - 0.5 * np.cos(np.pi * env))
    gm = g_under * 10 ** (3.0 * lift / 20)
    # gentle fade at the very end
    fo = int(1.6 * SR); gm[-fo:] *= np.linspace(1, 0, fo) ** 1.5
    mus = m * gm
    mix = v + mus
    g = 10 ** ((-16.0 - lufs(mix)) / 20)
    mix *= g; v *= g; mus *= g
    tp = true_peak_db(mix)
    if tp > -1.2:
        # soft peak limiting on oversampled envelope
        lim = 10 ** (-1.3 / 20)
        y = resample_poly(mix, 4, 1)
        env = np.abs(y)
        gr = np.minimum(1, lim / np.maximum(env, 1e-9))
        from scipy.ndimage import minimum_filter1d, uniform_filter1d
        gr = uniform_filter1d(minimum_filter1d(gr, 4 * 96), 4 * 48)
        mix = resample_poly(y * gr, 1, 4)[:n]
    print('mix I=%.2f  TP=%.2f  voice I=%.2f  music-under=%.2f  music-pause-lift=3dB' %
          (lufs(mix), true_peak_db(mix), lufs(v), lufs(mus[speech])))
    st = np.stack([mix, mix], 1).astype(np.float32)
    wavfile.write(W + 'mix.wav', SR, st)
    json.dump(dict(timeline=tl, total=total, beats=[t for t, _ in bmap if t < total],
                   downbeats=[t for t, ob in bmap if ob % 4 == 0 and t < total], tail=tail), open(W + 'timeline.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
