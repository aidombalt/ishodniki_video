"""Music edit on bars, speech-driven timeline on real beats, voice/music mix."""
import json, subprocess, re, numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

SR = 48000
W = '/tmp/claude-0/-home-user-ishodniki-video/7fdd3399-3b0b-583b-a74f-2847502fb422/scratchpad/work/'
LEAD = 0.6          # speech starts this long after the cut
import os
HAS14 = os.path.exists(W + 'vo/14.wav')   # reassurance line after the total
HAS15 = os.path.exists(W + 'vo/15.wav')   # closing call to vote on the brand card


def plan(c_end=102, sparse_extra=2):
    """original bar ranges played in order. Groove C runs to bar c_end, the quiet section is stretched or
    shortened by sparse_extra bars (looping bars 116-117), then dip, final groove and the final chord."""
    k = [(0, 27), (31, 82 if HAS14 else c_end)]
    if HAS14:   # 5 bars of the kick-less breakdown under the block after the total; groove returns on 09b
        k += [(36, 39), (38, 40), (82, c_end)]
    if sparse_extra >= 0:   # bars may come in halves (2 beats)
        whole = int(sparse_extra // 2); rest = sparse_extra - 2 * whole
        k += [(112, 118)] + [(116, 118)] * whole + ([(118 - rest, 118)] if rest else []) + [(118, None)]
    else:
        k += [(112, 118 + sparse_extra), (118, None)]
    return k
BEAT_OFFSET = 0.062   # tracked grid sat between 16ths; kick/snare land 62 ms later

ITEMS = [('logo', None, 'start'),
 ('01rad', ('01', 0, 0), 'intra'), ('01main', ('01', 1, 3), 'intra'),
 ('02q', ('02', 0, 1), 'scene'), ('02f', ('02', 2, 4), 'intra'),
 ('03a', ('03', 0, 1), 'scene'), ('03b', ('03', 2, 5), 'intra'),
 ('04a', ('04', 0, 4), 'scene'), ('04b', ('04', 5, 7), 'intra'),
 ('05a', ('05', 0, 1), 'scene'), ('05b', ('05', 2, 5), 'intra'),
 ('06a', ('06', 0, 1), 'scene'), ('06b', ('06', 2, 6), 'intra'),
 ('07a', ('07', 0, 1), 'scene'), ('07b', ('07', 2, 3), 'intra'),
 ('08', ('08', 0, 1), 'scene'),
 ('09a', ('09', 0, 0), 'scene'), ('09n', ('14', 0, -1), 'intra'), ('09b', ('09', 1, 2), 'intra'),
 ('10a', ('10', 0, 1), 'scene'), ('10b', ('10', 2, 2), 'intra'), ('10c', ('10', 3, 3), 'intra'),
 ('11', ('11', 0, -1), 'scene'), ('12', ('12', 0, 3), 'scene'),
 ('13a', ('13', 0, 0), 'scene'), ('13b', ('13', 1, 3), 'intra'), ('15', ('15', 0, -1), 'scene')]
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


def kweight(x):
    from scipy.signal import lfilter
    y = lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285], [1, -1.69065929318241, 0.73248077421585], x)
    return lfilter([1.0, -2.0, 1.0], [1, -1.99004745483398, 0.99007225036621], y)


def ride_gain(m, target, tl, total):
    """slow gain so the music's short-term loudness (3 s, dual-mono stereo) sits at target; frozen in the final pause"""
    y = kweight(m) ** 2
    hop = SR // 10; win = 3 * SR
    c = np.concatenate([[0], np.cumsum(y)])
    centers = np.arange(0, len(m), hop)
    ms = np.array([(c[min(len(m), i + win // 2)] - c[max(0, i - win // 2)]) / win for i in centers])
    st = -0.691 + 10 * np.log10(2 * ms + 1e-12)
    g = target - st
    base = np.median(g[len(g) // 10: -len(g) // 10])
    g = base + np.clip(g - base, -6, 6)   # ride at most +-6 dB around the overall trim
    k = 21; g = np.convolve(np.pad(g, k // 2, mode='edge'), np.ones(k) / k, 'valid')
    last = [d for d in tl if d['kind'] != 'start'][-1]['t1']
    g[centers / SR > last] = g[np.searchsorted(centers / SR, last) - 1]
    gs = np.interp(np.arange(len(m)), centers, g)
    return 10 ** (gs / 20)


def edit_music(KEEP):
    x = rd(W + 'music48.wav')
    beats = np.array(json.load(open(W + 'beats_s.json'))) + BEAT_OFFSET
    db = beats[0::4]
    keep = []
    at = lambda bar: beats[int(round(bar * 4))]   # bars may be fractional (half bars)
    for a, b in KEEP:
        s0 = 0.0 if a == 0 else onset(x, at(a))
        s1 = len(x) / SR if b is None else onset(x, at(b))
        keep.append((s0, s1))
    xf = int(0.02 * SR); pre = int(0.003 * SR)
    out = np.zeros(0); bmap = []; seen = set(); starts = []
    for k, (s, e) in enumerate(keep):
        i0 = int(s * SR) - pre - (xf if k else 0)
        i1 = int(e * SR) - pre if k < len(keep) - 1 else len(x)
        seg = x[max(i0, 0):i1].copy()
        offset = (len(out) - (xf if k else 0)) / SR - max(i0, 0) / SR
        starts.append(s + offset)
        if k:
            r = np.linspace(0, np.pi / 2, xf)
            seg[:xf] *= np.sin(r)
            out[-xf:] *= np.cos(r)
            out[-xf:] += seg[:xf]
            out = np.concatenate([out, seg[xf:]])
        else:
            out = seg
        for bi, bt in enumerate(beats):
            if s - 0.08 <= bt < e - 0.08:
                bmap.append((bt + offset, bi if bi not in seen else -1)); seen.add(bi)
    return out, bmap, starts


def build(beats, force=None, extra=None):
    """beats: list of (time, orig_index). Cuts land on beats; speech starts LEAD after a cut."""
    force = force or {}; extra = extra or {}
    segs = json.load(open(W + 'segs.json'))
    tl, t_end = [], None
    for name, clip, kind in ITEMS:
        if clip and clip[0] not in segs:
            continue
        if kind == 'start':
            tl.append(dict(name=name, cut=beats[0][0], kind=kind)); continue
        if t_end is None:
            cut = beats[6][0]
        elif name in force:
            cut = min(beats, key=lambda b: abs(b[0] - force[name]))[0]
        else:
            lo, hi = RANGE[kind]
            cand = [b for b in beats if lo <= b[0] + LEAD - t_end <= hi]
            if not cand:   # window narrower than a beat: take the nearest beat
                cand = sorted(beats, key=lambda b: abs(b[0] + LEAD - t_end - TARGET[kind]))[:1]
            if kind == 'scene' and [c for c in cand if c[1] % 2 == 0]:
                cand = [c for c in cand if c[1] % 2 == 0]
            tgt = TARGET[kind] + extra.get(name, 0)
            cut = min(cand, key=lambda c: abs(c[0] + LEAD - t_end - tgt))[0]
        f, s0, s1 = clip
        if s1 < 0: s1 = len(segs[f]) - 1   # whole take, however many phrases it has
        a, b = segs[f][s0][0], segs[f][s1][1]
        t0 = cut + LEAD
        d = dict(name=name, kind=kind, cut=float(cut), vo=f, segs=[s0, s1], a=a, b=b, t0=t0, t1=t0 + b - a,
                 pause=None if t_end is None else t0 - t_end)
        if d['pause'] is not None and not (RANGE[kind][0] - 0.05 <= d['pause'] <= RANGE[kind][1] + 0.05):
            print('WARN pause', name, round(d['pause'], 2))
        tl.append(d); t_end = d['t1']
    return tl, t_end


def high_shelf(x, f0, gain_db, q=0.707):
    from scipy.signal import lfilter
    A = 10 ** (gain_db / 40); w0 = 2 * np.pi * f0 / SR; al = np.sin(w0) / (2 * q); c = np.cos(w0)
    b = [A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al)]
    a = [(A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al]
    return lfilter(np.array(b) / a[0], np.array(a) / a[0], x)


def voice_stem(tl, total):
    segs = json.load(open(W + 'segs.json'))
    files = {}
    for k in range(1, 16):
        if not os.path.exists(W + 'vo/%02d.wav' % k):
            continue
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
    def landmarks(bmap, starts, keep):
        lm = {}
        for t, ob in bmap:
            lm.setdefault(ob, t)
        db = lambda bar: lm[bar * 4]
        idx = {r: i for i, r in enumerate(keep)}
        base = {'04a': db(31), '08': db(71), '09a': db(77)}
        if HAS14:
            base.update({'09n': starts[idx[(36, 39)]], '09b': starts[idx[(82, keep[idx[(36, 39)] + 2][1])]]})
        return db, base
    # pass 1: natural speech timing after 09b decides how much groove and quiet music is needed
    keep = plan()
    m, bmap, starts = edit_music(keep)
    db, base = landmarks(bmap, starts, keep)
    tl, _ = build(bmap, base)
    c07 = [d for d in tl if d['name'] == '07b'][0]['cut']
    base['07b'] = [t for t, _ in bmap if t > c07 + 0.3][0]
    tl, t_end = build(bmap, base)
    cut = {d['name']: d['cut'] for d in tl}
    t_from = cut['09b'] if HAS14 else cut['09a']
    bar_c = 2.257; bar_s = 2.29
    half = lambda x: round(2 * x) / 2
    c_end = min(82 + half((cut['12'] - t_from) / bar_c), 112) if HAS14 else min(80 + half((cut['12'] - db(80)) / bar_c), 112)
    quiet_bars = half((t_end + 0.4 - cut['12']) / bar_s)    # bars from the quiet section to the final chord
    keep = plan(c_end, quiet_bars - 13)
    m, bmap, starts = edit_music(keep)
    wavfile.write(W + 'music_edit.wav', SR, m.astype(np.float32))
    db, base = landmarks(bmap, starts, keep)
    base['07b'] = [t for t, _ in bmap if t > c07 + 0.3][0]
    base['12'] = db(112)
    tail = db(125)
    print('music plan', keep)
    # pass 2: spread the small residuals over the neighbouring pauses so the anchored cuts stay in range
    extra = {'15': 0.25} if HAS15 else {}
    pre12, post12 = ['10a', '10b', '10c', '11'], ['13a', '13b'] + (['15'] if HAS15 else [])
    for it in range(30):
        tl, t_end = build(bmap, base, extra)
        d = {x['name']: x for x in tl}
        p12 = d['12']['pause']
        r1 = 0 if 2.0 <= p12 <= 2.5 else (2.25 - p12)
        r2 = (tail - 0.4) - t_end
        if abs(r1) < 0.05 and abs(r2) < 0.3:
            break
        for n in pre12: extra[n] = extra.get(n, 0) - r1 / len(pre12) * 0.5
        for n in post12: extra[n] = extra.get(n, 0) + r2 / len(post12) * 0.5
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
    g_under = ride_gain(m, -15.5 - 12.5, tl, total)
    # duck envelope: +3 dB in pauses longer than 1 s, smooth ramps
    lift = np.zeros(n)
    t = np.arange(n) / SR
    spans = [(d['t0'], d['t1']) for d in tl if d['kind'] != 'start']
    pauses = [(0, spans[0][0])] + [(spans[i][1], spans[i + 1][0]) for i in range(len(spans) - 1)] + [(spans[-1][1], total)]
    for a, b in pauses:
        if b - a < 1.5:
            continue
        up0, up1 = a + 0.25, a + 0.75
        dn0, dn1 = b - 0.55, b - 0.1
        if a == 0:
            up0 = up1 = 0
        if b >= total - 0.01:
            dn0 = dn1 = total + 1
        env = np.clip(np.minimum((t - up0) / max(up1 - up0, 1e-3), (dn1 - t) / max(dn1 - dn0, 1e-3)), 0, 1)
        env[(t < up0) | (t > dn1)] = 0
        # rise amount per pause: music level in the pause vs the 3 s under the preceding speech stays <= 3 dB
        km = kweight(m * g_under) ** 2
        Lk = lambda i0, i1: 10 * np.log10(km[max(i0, 0):max(i1, i0 + 1)].mean() + 1e-12)
        if a > 0 and b < total - 0.01:
            r0 = Lk(int((a + 0.8) * SR), int((b - 0.6) * SR)) - Lk(int((a - 3) * SR), int(a * SR))
        else:
            r0 = 0.0
        amt = float(np.clip(2.8 - r0, 0, 2.8))
        lift = np.maximum(lift, amt * (0.5 - 0.5 * np.cos(np.pi * env)))
    gm = g_under * 10 ** (lift / 20)
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
    np.save(W + 'stem_v.npy', v.astype(np.float32)); np.save(W + 'stem_m.npy', mus.astype(np.float32))
    st = np.stack([mix, mix], 1).astype(np.float32)
    wavfile.write(W + 'mix.wav', SR, st)
    json.dump(dict(timeline=tl, total=total, beats=[t for t, _ in bmap if t < total],
                   downbeats=[t for t, ob in bmap if ob % 4 == 0 and t < total], tail=tail), open(W + 'timeline.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
