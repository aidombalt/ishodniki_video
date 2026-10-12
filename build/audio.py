"""Sound mix: VO + two music themes with ducking + synthesized SFX -> stereo WAV."""
import sys, os, subprocess, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from timing import *

P = os.environ["PROJ"]
SRC = P + "/src"
SR = 48000
N = int((END + 0.2) * SR)
rng = np.random.default_rng(11)


def load(path, ch=2):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", str(ch), "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, ch).copy()


def db(x):
    return 10 ** (x / 20)


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


mix = np.zeros((N, 2), np.float32)


def place(sig, t, gain=1.0, pan=0.0):
    i = int(round(t * SR))
    if sig.ndim == 1:
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        sig = np.stack([sig * l * 1.414, sig * r * 1.414], 1)
    j = min(N, i + len(sig))
    if j > i:
        mix[i:j] += sig[: j - i] * gain


# ---------------- VO ----------------
vo_cache = {}
speech_levels = []
for b in ["01", "02", "03", "04", "05", "06", "07", "08"]:
    x = load(f"{SRC}/{b}_Eleven_v4.mp3", 1)[:, 0]
    vo_cache[b] = x
    act = x[np.abs(x) > 0.02]
    speech_levels.append(rms_db(act))
target = -19.0
for sid, (b, l0, l1, g0) in VO.items():
    x = vo_cache[b]
    seg = x[int(l0 * SR): int(l1 * SR)].copy()
    lvl = rms_db(x[np.abs(x) > 0.02])
    g = db(target - lvl)
    # 8 ms fades at cut points
    f = int(0.008 * SR)
    seg[:f] *= np.linspace(0, 1, f); seg[-f:] *= np.linspace(1, 0, f)
    place(seg, g0, g)

# ---------------- music ----------------
forecast = load(SRC + "/music_forecast.mp3")
oblivion = load(SRC + "/music_oblivion.mp3")
f_lvl = rms_db(forecast[: SR * 60])
o_lvl = rms_db(oblivion[: SR * 12])

t = np.arange(N) / SR
# speech activity envelope with attack/release
act = np.zeros(N, np.float32)
for (a, b) in SPEECH:
    act[int((a - 0.10) * SR): int((b + 0.25) * SR)] = 1.0


def smooth(env, att=0.10, rel=0.35):
    out = np.empty_like(env)
    ka, kr = 1 - np.exp(-1 / (att * SR)), 1 - np.exp(-1 / (rel * SR))
    v = 0.0
    for i in range(0, len(env), 64):  # block-wise for speed
        tgt = env[i]
        k = ka if tgt > v else kr
        v += (tgt - v) * (1 - (1 - k) ** 64)
        out[i:i + 64] = v
    return out


duck = smooth(act)


def seg_env(t0, t1, fin, fout):
    e = np.clip((t - t0) / max(fin, 1e-3), 0, 1) * np.clip((t1 - t) / max(fout, 1e-3), 0, 1)
    e[(t < t0) | (t > t1)] = 0
    return e


def lay_music(src, src_t0, g0, g1, lvl, gap_db, duck_db, fin, fout, extra=None):
    i0, i1 = int(g0 * SR), int(g1 * SR)
    s0 = int(src_t0 * SR)
    seg = src[s0: s0 + (i1 - i0)]
    n = len(seg)
    env = seg_env(g0, g1, fin, fout)[i0:i0 + n]
    lev = db(gap_db - lvl) * (1 - duck[i0:i0 + n]) + db(duck_db - lvl) * duck[i0:i0 + n]
    if extra is not None:
        lev = lev * extra[i0:i0 + n]
    mix[i0:i0 + n] += seg * (env * lev)[:, None]


# serious block 07: everything a touch quieter
calm = np.ones(N, np.float32)
calm[(t > 68.3) & (t < 78.9)] = db(-3.5)
calm = smooth(calm, 0.4, 0.4)

boost = np.ones(N, np.float32)
for (m0, m1, name) in MEMES:
    boost[(t > m0) & (t < m1)] = db({"kitten": 3.0, "math": 6.5, "vislava": 2.5}.get(name, 0.0))
boost = smooth(boost, 0.12, 0.25)
lay_music(forecast, 0.0, 0.0, 32.75, f_lvl, -27.5, -34.5, 0.20, 0.35)
lay_music(oblivion, 0.40, 32.75, 37.30, o_lvl, -23.5, -28.5, 0.06, 1.30)
lay_music(forecast, 0.0, 36.40, 83.30, f_lvl, -27.5, -34.5, 0.90, 0.35, extra=calm * boost)
lay_music(oblivion, 0.40, T_POT, END - 0.28, o_lvl, -24.0, -29.5, 0.08, 0.10)

# ---------------- SFX ----------------
def band(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x)).astype(np.float32)


def sweep(f0, f1, dur, tau, amp, curve="exp"):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    if curve == "exp":
        f = f0 * (f1 / f0) ** (tt / dur)
    else:
        f = f0 + (f1 - f0) * tt / dur
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * np.exp(-tt / tau) * amp).astype(np.float32)


def noise(dur, lo, hi, tau, amp):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    return band(rng.standard_normal(n).astype(np.float32), lo, hi) * np.exp(-tt / tau) * amp


def fade_in(x, ms=2):
    f = int(ms / 1000 * SR)
    x[:f] *= np.linspace(0, 1, f)
    return x


def mixsig(*parts):
    n = max(len(p) for p, _ in parts)
    out = np.zeros(n, np.float32)
    for p, off in parts:
        i = int(off * SR)
        out[i:i + len(p)] += p[: n - i]
    return out


click = fade_in(mixsig((noise(0.03, 1800, 9000, 0.006, 0.9), 0), (sweep(2600, 1800, 0.03, 0.01, 0.35), 0)))
thud = fade_in(mixsig((sweep(110, 48, 0.32, 0.10, 0.9), 0), (noise(0.08, 200, 2500, 0.02, 0.5), 0)))
tick = fade_in(mixsig((sweep(2300, 2100, 0.04, 0.010, 0.55), 0), (noise(0.01, 3000, 9000, 0.003, 0.2), 0)))
pop = fade_in(sweep(380, 1150, 0.09, 0.05, 0.7))
plop = mixsig((fade_in(sweep(150, 560, 0.12, 0.07, 0.9)), 0), (noise(0.18, 900, 5000, 0.05, 0.22), 0.015))
bulk = mixsig((fade_in(sweep(105, 320, 0.16, 0.10, 1.0)), 0), (fade_in(sweep(210, 700, 0.09, 0.05, 0.55)), 0.11),
              (noise(0.2, 700, 3500, 0.06, 0.12), 0.02))


def whoosh(dur=0.5, lo=400, hi=4500, amp=0.35):
    n = int(dur * SR)
    x = band(rng.standard_normal(n).astype(np.float32), lo, hi)
    e = np.sin(np.linspace(0, np.pi, n)) ** 2
    return x * e * amp


place(click, T_SIGN - 0.01, db(-6))
place(thud, T_SIGN, db(-10))
place(thud, T_HERN, db(-7))
place(click, T_HERN, db(-14))
for tt in T_TICKS:
    place(tick, tt, db(-15))
place(pop, T_HAT + 0.04, db(-10))
place(whoosh(0.45), 40.85 - 0.30, db(-16), pan=-0.3)
place(whoosh(0.45), 53.45 - 0.30, db(-16), pan=0.3)
place(whoosh(0.8, 300, 3000, 0.3), T_WAVE - 0.05, db(-12), pan=-0.4)
place(pop, T_Q + 0.02, db(-14))
for i, dt in enumerate(DROP_T):
    place(whoosh(0.5, 900, 6000, 0.25), dt + 0.25, db(-22), pan=[-0.4, 0.4, 0][i])
    place(plop, dt + FALL - 0.01, db(-7), pan=[-0.15, 0.15, 0][i])
place(bulk, T_BULK - 0.02, db(-5))

# ---------------- master ----------------
# soft limiter
peak = np.max(np.abs(mix))
mix = np.tanh(mix * 1.1) / np.tanh(1.1) if peak > 0.98 else mix
# hard end
e = int((END - 0.25) * SR)
mix[e:e + int(0.05 * SR)] *= np.linspace(1, 0, int(0.05 * SR))[:, None]
mix[e + int(0.05 * SR):] = 0
out = P + "/work/mix_raw.wav"
pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
with wave.open(out, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote", out, "peak", float(np.max(np.abs(mix))), "speech lvls", [round(v, 1) for v in speech_levels],
      "music lvls", round(f_lvl, 1), round(o_lvl, 1))
