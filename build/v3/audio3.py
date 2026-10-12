"""v3 mix: VO + Local Forecast (paused/resumed around NPC inserts) + meme audio + meme SFX."""
import sys, os, subprocess, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from timing3 import *

P = os.environ["PROJ"]
SRC = P + "/src"
PACK = SRC + "/pack/Genshin_Meme_Pack"
SFX = SRC + "/sfx"
UP = "/root/.claude/uploads/0120ee38-40d5-55c2-8031-d22adf97ded6"
ORIG = {"V1": UP + "/a246444a-Screenrecording_20261012_121120_com.miHoYo.GenshinImpact.mp4",
        "V2": SRC + "/v2x/Screenrecording_20261012_121225_com.miHoYo.GenshinImpact.mp4"}
SR = 48000
N = int((END + 0.3) * SR)
t = np.arange(N) / SR
mix = np.zeros((N, 2), np.float32)


def load(path, start=0.0, dur=None):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", path, "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def db(x):
    return 10 ** (x / 20)


def lvl(x, gate=0.02):
    m = np.abs(x).max(axis=1) > gate
    s = x[m] if m.sum() > 100 else x
    return 20 * np.log10(np.sqrt(np.mean(s ** 2)) + 1e-12)


def fades(x, fi=0.005, fo=0.02):
    a, b = int(fi * SR), int(fo * SR)
    if a: x[:a] *= np.linspace(0, 1, a)[:, None]
    if b: x[-b:] *= np.linspace(1, 0, b)[:, None]
    return x


def place(sig, at, gain_db=0.0):
    i = int(round(at * SR))
    j = min(N, i + len(sig))
    if j > i:
        mix[i:j] += sig[: j - i] * db(gain_db)


def sound(path, at, target, start=0.0, dur=None, fo=0.03):
    """place a clip normalised so its active part sits at `target` dB RMS."""
    x = load(path, start, dur)
    x = fades(x, 0.004, fo)
    place(x, at, target - lvl(x))


# ---------------- VO ----------------
vo_raw = {b: load(f"{SRC}/{b}_Eleven_v4.mp3") for b in sorted({v[0] for v in VO.values()})}
for sid, (b, l0, l1, g0) in VO.items():
    x = vo_raw[b]
    seg = fades(x[int(l0 * SR): int(l1 * SR)].copy(), 0.008, 0.008)
    place(seg, g0, -19.0 - lvl(x))

# ---------------- ducking envelope ----------------
act = np.zeros(N, np.float32)
for (a, b) in SPEECH:
    act[int((a - 0.10) * SR): int((b + 0.25) * SR)] = 1.0


def smooth(env, att=0.10, rel=0.35):
    out = np.empty_like(env)
    ka, kr = 1 - np.exp(-1 / (att * SR)), 1 - np.exp(-1 / (rel * SR))
    v = float(env[0])
    for i in range(0, len(env), 64):
        tgt = env[i]
        k = ka if tgt > v else kr
        v += (tgt - v) * (1 - (1 - k) ** 64)
        out[i:i + 64] = v
    return out


duck = smooth(act)

# ---------------- music: Local Forecast, paused around inserts ----------------
forecast = load(SRC + "/music_forecast.mp3")
f_lvl = lvl(forecast[: SR * 60])
GAP, DUCK = -27.0, -34.0
# (global start, global end, fade in, fade out, extra gain dB)
RUNS = [(S_VARESA[0], S_HOME[0], 0.0, 0.05, 0.0),
        (S_B2[0], S_JACK[0], 0.35, 0.06, 0.0),
        (S_RULES[0], S_VIGE[0] - 0.05, 0.05, 0.05, 0.0),
        (S_RISK[0], S_VISL[0] - 0.05, 0.25, 0.05, 0.0),
        (S_POT[0], S_TAG[0], 0.30, 0.05, -2.0)]
pos = 0.0
for (g0, g1, fi, fo, extra) in RUNS:
    n = int((g1 - g0) * SR)
    seg = forecast[int(pos * SR): int(pos * SR) + n].copy()
    i0 = int(g0 * SR)
    lev = (db(GAP - f_lvl) * (1 - duck[i0:i0 + n]) + db(DUCK - f_lvl) * duck[i0:i0 + n]) * db(extra)
    seg *= lev[:, None]
    seg = fades(seg, fi, fo)
    place(seg, g0)
    pos += g1 - g0
# meme moments without VO: lift the bed a little
for (a, b, gdb) in [(S_KITTEN[0], S_KITTEN[1], 3.0), (S_GOSL[0], S_GOSL[1], 2.0)]:
    pass  # bed already at gap level there (no speech) — nothing to do

# ---------------- NPC inserts: original game audio (near-silence + UI blips) ----------------
for (vid, src0, src1, g0) in [("V1", 16.90, 18.45, S_COLD[0]), ("V2", 19.00, 21.30, S_VIGE[0]),
                              ("V1", 3.10, 6.10, S_VISL[0]), ("V1", 36.95, 37.95, S_TAG[0])]:
    x = fades(load(ORIG[vid], src0, src1 - src0), 0.02, 0.15)
    place(x, g0, 12.0)

# ---------------- meme audio ----------------
sound(SFX + "/moye_moye.wav", S_HOME[0], -24.5, 0.0, S_HOME[1] - S_HOME[0] + 0.25, fo=0.25)
sound(PACK + "/03_bonus/X20_jackpot_original.mp4", S_JACK[0], -16.5, 1.00, S_JACK[1] - S_JACK[0], fo=0.06)
sound(PACK + "/01_main/V1_aw_dang_it_ready.mp4", S_AW[0], -15.0, 0.0, S_AW[1] - S_AW[0], fo=0.05)
sound(SFX + "/moye_moye.wav", S_TAG[0] + 0.05, -21.0, 0.0, END - S_TAG[0] - 0.3, fo=0.02)

# ---------------- SFX ----------------
sound(PACK + "/02_sounds/S1_vine_boom_a.mp3", S_VARESA[0] - 0.02, -13.0)
sound(PACK + "/02_sounds/S3_cha_ching_b.mp3", T_SIGN - 0.03, -20.0, 0.0, 1.4, fo=0.3)
sound(SFX + "/bruh.mp3", T_BRUH, -17.0)
sound(PACK + "/02_sounds/S5_slap_a.mp3", T_SLAP - 0.01, -15.0)
for T in T_SCRATCH:
    sound(PACK + "/02_sounds/S2_record_scratch_a.mp3", T, -17.0)
sound(SFX + "/faah.wav", T_FLYAWAY, -16.0)


# small synthetic UI bits (ticks, hat pop, plops, final bubble)
def band(x, lo, hi):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, len(x)).astype(np.float32)


rng = np.random.default_rng(3)


def sweep(f0, f1, dur, tau, amp):
    n = int(dur * SR); tt = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (tt / dur)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt / tau) * amp).astype(np.float32)


def noise(dur, lo, hi, tau, amp):
    n = int(dur * SR); tt = np.arange(n) / SR
    return band(rng.standard_normal(n).astype(np.float32), lo, hi) * np.exp(-tt / tau) * amp


def mono(*parts):
    n = max(len(p) + int(o * SR) for p, o in parts)
    out = np.zeros(n, np.float32)
    for p, o in parts:
        i = int(o * SR); out[i:i + len(p)] += p
    out[:96] *= np.linspace(0, 1, 96)
    return np.stack([out, out], 1)


tick = mono((sweep(2300, 2100, 0.04, 0.010, 0.55), 0), (noise(0.01, 3000, 9000, 0.003, 0.2), 0))
pop = mono((sweep(380, 1150, 0.09, 0.05, 0.7), 0))
plop = mono((sweep(150, 560, 0.12, 0.07, 0.9), 0), (noise(0.18, 900, 5000, 0.05, 0.22), 0.015))
bulk = mono((sweep(105, 320, 0.16, 0.10, 1.0), 0), (sweep(210, 700, 0.09, 0.05, 0.55), 0.11), (noise(0.2, 700, 3500, 0.06, 0.12), 0.02))
for T in T_TICKS:
    place(tick, T, -16)
place(pop, T_HAT + 0.04, -11)
for dt in DROP_T:
    place(plop, dt + FALL - 0.01, -7)
place(bulk, T_BULK - 0.02, -5)

# ---------------- master ----------------
e = int((END - 0.04) * SR)
mix[e:] = 0
out = P + "/work/mix3_raw.wav"
with wave.open(out, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
print("wrote", out, "peak", round(float(np.abs(mix).max()), 3), "music used", round(pos, 1), "s")
