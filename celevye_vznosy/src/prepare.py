"""Inputs -> build/: 48 kHz voice takes, speech segments, music, beat grid of the real track."""
import os, glob, json, subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft

ROOT = os.environ.get('PROJECT_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IN, B = ROOT + '/input/', ROOT + '/build/'
os.makedirs(B + 'vo', exist_ok=True)


def ff(*a):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *a], check=True)


# voice: one take per line, 01.mp3 ... ; speech segments by short pauses
segs = {}
for p in sorted(glob.glob(IN + 'voice/*.mp3')):
    k = os.path.basename(p)[:2]
    ff('-i', p, '-ac', '1', '-ar', '48000', '-c:a', 'pcm_f32le', B + 'vo/%s.wav' % k)
    sr, x = wavfile.read(B + 'vo/%s.wav' % k)
    fr = int(sr * 0.01); n = len(x) // fr
    db = 20 * np.log10(np.array([np.sqrt(np.mean(x[j * fr:(j + 1) * fr] ** 2)) for j in range(n)]) + 1e-9)
    sp = db > max(db.max() - 38, -55)
    runs, j = [], 0
    while j < n:
        if sp[j]:
            s = j
            while j < n and sp[j]: j += 1
            runs.append([s, j])
        else:
            j += 1
    m = []
    for r in runs:   # pauses shorter than 0.14 s stay inside a phrase
        if m and r[0] - m[-1][1] < 14: m[-1][1] = r[1]
        else: m.append(r)
    segs[k] = [[a / 100, b / 100] for a, b in m if b - a > 4]
json.dump(segs, open(B + 'segs.json', 'w'))

# music: 48 kHz for the mix, 22.05 kHz for beat tracking
ff('-i', IN + 'music/music.mp3', '-ac', '1', '-ar', '48000', '-c:a', 'pcm_f32le', B + 'music48.wav')
ff('-i', IN + 'music/music.mp3', '-ac', '1', '-ar', '22050', '-f', 'f32le', B + 'music.f32')
sr, hop = 22050, 256; fps = sr / hop
x = np.fromfile(B + 'music.f32', dtype=np.float32)
f, t, Z = stft(x, fs=sr, nperseg=2048, noverlap=2048 - hop, boundary=None)
M = np.log1p(100 * np.abs(Z))
flux = np.maximum(0, np.diff(M, axis=1)).sum(0)
flux = (flux - np.convolve(flux, np.ones(32) / 32, 'same')).clip(0)
# dynamic-programming beat tracker around the measured tempo (~107 BPM)
on = flux / flux.std(); n = len(on); P0 = fps * 60 / 106.9; alpha = 400
score = on.copy(); back = -np.ones(n, int)
lo, hi = int(P0 * 0.9), int(P0 * 1.1) + 1
for i in range(hi, n):
    prev = np.arange(i - hi, i - lo)
    v = score[prev] - alpha * (np.log((i - prev) / P0)) ** 2; j = int(np.argmax(v))
    score[i] = on[i] + v[j]; back[i] = prev[j]
i = int(np.argmax(score[-hi:])) + n - hi
b = []
while i >= 0: b.append(i); i = back[i]
b = np.array(b[::-1]) / fps; b = b[b > 0.3]
bs = b.copy()   # local linear fit removes frame jitter; tempo drift stays
for i in range(len(b)):
    l, h = max(0, i - 6), min(len(b), i + 7)
    idx = np.arange(l, h); bs[i] = np.polyval(np.polyfit(idx, b[l:h], 1), i)
json.dump(bs.tolist(), open(B + 'beats_s.json', 'w'))
print('voice takes', len(segs), 'beats', len(bs))
