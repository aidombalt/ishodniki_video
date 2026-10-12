"""v3 montage: dark-humour cut with NPC inserts, YouTube-style graphics."""
import sys, os, subprocess, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from gfx3 import *
from timing3 import *

P = os.environ.get("PROJ")
SRC = P + "/src"
WORK = P + "/work"
FPS = 30
WW, WH = 2400, 1080

class Clip:
    """Sequential CFR video reader. local time -> PIL RGB frame at the clip's native size."""

    def __init__(self, path, src0, speed=1.0, src_end=None, size=None, crop=None):
        self.path, self.src0, self.speed, self.src_end = path, src0, speed, src_end
        self.size = size
        self.crop = crop
        self.proc = None
        self.k = -1
        self.last = None
        if size is None:
            out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                  "stream=width,height", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
            w, h = out.strip().split(",")
            self.size = (int(w), int(h))
        self.osize = (crop[2] - crop[0], crop[3] - crop[1]) if crop else self.size

    def _open(self, start):
        if self.proc:
            self.proc.kill()
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", self.path,
                                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                     stdout=subprocess.PIPE, bufsize=10 ** 8)
        self.base = start
        self.k = -1

    def at(self, local):
        st = self.src0 + max(0.0, local) * self.speed
        if self.src_end is not None:
            st = min(st, self.src_end)
        if self.proc is None:
            self._open(st)
        want = int(round((st - self.base) * FPS))
        if want < self.k or want - self.k > 90:
            self._open(st)
            want = 0
        n = self.size[0] * self.size[1] * 3
        while self.k < want:
            buf = self.proc.stdout.read(n)
            if len(buf) < n:
                break
            self.last = Image.frombytes("RGB", self.size, buf)
            if self.crop:
                self.last = self.last.crop(self.crop)
            self.k += 1
        return self.last

    def close(self):
        if self.proc:
            self.proc.kill()
            self.proc = None


def load_world(path):
    return Image.open(path).convert("RGB").resize((WW, WH), Image.LANCZOS)


S1 = load_world(SRC + "/Battle_1.png")
S2 = load_world(SRC + "/Battle_2.png")
FR = {}


def still(vid, t):
    key = (vid, t)
    if key not in FR:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", f"{WORK}/{vid}_cfr.mp4", "-frames:v", "1",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        FR[key] = Image.frombytes("RGB", (WW, WH), r)
    return FR[key]


# =====================================================================
# Camera
# =====================================================================
FULL = (1200, 540, 1.0)
GRID = (1150, 580, 1.38)
LEFTP = (720, 640, 1.5)
RIGHT2 = (1700, 520, 1.45)
OVERVIEW = (1530, 560, 1.18)


class Cam:
    def __init__(self, start, moves=()):
        self.start = start
        self.moves = sorted(moves)  # (g, dur, pose)

    def pose(self, g):
        p = self.start
        for (t0, d, q) in self.moves:
            if g <= t0:
                break
            k = e_inout((g - t0) / d) if d > 0 else 1
            p = tuple(a + (b - a) * k for a, b in zip(p, q))
            if g < t0 + d:
                break
        return p


def view_rect(pose):
    cx, cy, z = pose
    w, h = W / z, H / z
    cx = min(max(cx, w / 2), WW - w / 2) if w <= WW else WW / 2
    cy = min(max(cy, h / 2), WH - h / 2) if h <= WH else WH / 2
    return cx - w / 2, cy - h / 2, w, h


def apply_cam(world, pose, shake=(0, 0)):
    x0, y0, w, h = view_rect(pose)
    x0 += shake[0]; y0 += shake[1]
    if abs(w - W) < 0.01 and abs(x0 - round(x0)) < 0.01 and abs(y0 - round(y0)) < 0.01:
        return world.crop((int(round(x0)), int(round(y0)), int(round(x0)) + W, int(round(y0)) + H))
    return world.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h))


class Ctx:
    def __init__(self, pose, shake=(0, 0)):
        self.x0, self.y0, self.w, self.h = view_rect(pose)
        self.x0 += shake[0]; self.y0 += shake[1]
        self.z = W / self.w

    def pt(self, x, y):
        return ((x - self.x0) * self.z, (y - self.y0) * self.z)

    def rect(self, r):
        a = self.pt(r[0], r[1]); b = self.pt(r[2], r[3])
        return (a[0], a[1], b[0], b[1])


# =====================================================================
# World coordinates (2400x1080 game UI space)
# =====================================================================
COLX = {1: 862, 2: 1002, 3: 1134, 4: 1266, 5: 1402}
ROWY = {1: 379, 2: 514, 3: 648, 4: 782}


def card(c, r, pad=6):
    x, y = COLX[c], ROWY[r]
    return (x - 54 - pad, y - 47 - pad, x + 54 + pad, y + 47 + pad)


def union(*rs):
    return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))


R_COIN = (1372, 28, 1594, 92)
R_PCT_L = (262, 304, 644, 432)
R_PCT_R = (1756, 304, 2138, 432)
R_MUL_L = (262, 440, 644, 570)
R_MUL_R = (1756, 440, 2138, 570)
R_TIMER = (762, 268, 1648, 318)
R_PUT_L = (246, 842, 668, 930)
B1_CICIN = [card(2, 1), card(3, 2), card(3, 3), card(2, 4)]
B1_SOUP = card(1, 2)
B1_MOLD = [card(4, 1), card(4, 2), card(4, 3), card(4, 4)]
B1_RIGHT = union(card(4, 1), card(5, 4))
B2_LEFT = union(card(1, 2), card(2, 1), card(3, 4), card(3, 1))
B2_LAVA = card(1, 2)
B2_HEAL = card(3, 1)
B2_ARCH = [card(2, 1), card(2, 4)]
B2_SAPHO = card(4, 3)
R_MUL_R2 = (1852, 492, 2034, 568)
# overview (V3 4-8 / 59-65)
OV_B1L = (898, 286, 1392, 432)
OV_B1R = (1392, 286, 1884, 432)
OV_B2L = (898, 664, 1392, 808)
OV_B2R = (1392, 664, 1886, 808)
# entry & dialogue
R_PROMPT = (1416, 546, 1806, 626)
VIS_LINE = (752, 944, 1648, 944)


# =====================================================================
# v3 extras
# =====================================================================
PACK = SRC + "/pack/Genshin_Meme_Pack"
MUL_L_VAL = (392, 498, 514, 562)
MUL_R_VAL = (1890, 498, 1992, 562)
MUL_R2_VAL = (1880, 498, 2006, 562)
PCT_R_VAL = (1876, 360, 2012, 428)
RIGHT_TEAM2 = (1206, 180, 1890, 274)
RULES_UL = (996, 1390, 926)
VIGE_UL = [(1146, 1790, 928), (936, 1466, 974)]
VISL_UL = (754, 1648, 944)
TAG_OPT = (1478, 674, 2040, 758)
OVERVIEW = (1530, 560, 1.18)


class Cam3:
    def __init__(self, start, moves=()):
        self.start = start
        self.moves = sorted(moves, key=lambda m: m[0])  # (t0, dur, pose, ease)

    def pose(self, g):
        p = self.start
        for mv in self.moves:
            t0, d, q = mv[0], mv[1], mv[2]
            ease = mv[3] if len(mv) > 3 else e_inout
            if g <= t0:
                break
            k = ease((g - t0) / d) if d > 0 else 1
            p = tuple(a + (b - a) * k for a, b in zip(p, q))
            if g < t0 + d:
                break
        return p


def shake_fn(events):
    """events: list of (t, amp). Decaying jitter."""
    def fn(g):
        dx = dy = 0.0
        for (t, amp) in events:
            if t <= g < t + 0.35:
                u = g - t
                k = amp * math.exp(-u * 11)
                dx += k * math.sin(u * 83)
                dy += k * math.cos(u * 71)
        return (dx, dy)
    return fn


class E:
    def __init__(self, t0, t1):
        self.t0, self.t1 = t0, t1


class Circle(E):
    def __init__(self, rect, t0, t1, seed=None, dur=0.20, color=RED, width=9):
        super().__init__(t0, t1)
        self.rect, self.dur, self.color, self.width = rect, dur, color, width
        self.seed = seed if seed is not None else int(rect[0] * 7 + rect[1] * 13)

    def draw(self, cv, g, cx):
        marker_ellipse(cv, cx.rect(self.rect), (g - self.t0) / self.dur, self.seed, self.color, self.width)


class Arrow(E):
    def __init__(self, p0, p1, t0, t1, seed=1, dur=0.22):
        super().__init__(t0, t1)
        self.p0, self.p1, self.seed, self.dur = p0, p1, seed, dur

    def draw(self, cv, g, cx):
        marker_arrow(cv, cx.pt(*self.p0), cx.pt(*self.p1), (g - self.t0) / self.dur, self.seed)


class ULine(E):
    def __init__(self, x0, x1, y, t0, t1, seed=3, dur=0.30):
        super().__init__(t0, t1)
        self.x0, self.x1, self.y, self.seed, self.dur = x0, x1, y, seed, dur

    def draw(self, cv, g, cx):
        a = cx.pt(self.x0, self.y); b = cx.pt(self.x1, self.y)
        marker_underline(cv, a[0], b[0], a[1], (g - self.t0) / self.dur, self.seed)


class Txt(E):
    """screen-space text sprite with a snappy pop."""
    def __init__(self, sp, x, y, t0, t1, pop=0.10, rot=0.0):
        super().__init__(t0, t1)
        self.sp, self.x, self.y, self.pop, self.rot = sp, x, y, pop, rot

    def draw(self, cv, g, cx):
        paste(cv, self.sp, self.x, self.y, 1.0, pop_scale((g - self.t0) / self.pop), self.rot)


class WSprite(E):
    """world-anchored sprite that scales with the camera."""
    def __init__(self, sp, x, y, t0, t1, scale=1.0, rot=0.0, pop=0.14, slam=False):
        super().__init__(t0, t1)
        self.sp, self.x, self.y, self.scale, self.rot, self.pop, self.slam = sp, x, y, scale, rot, pop, slam

    def draw(self, cv, g, cx):
        x, y = cx.pt(self.x, self.y)
        p = (g - self.t0) / self.pop
        if self.slam:
            sc = 1.0 + 0.9 * (1 - e_out(p)) ** 2
        else:
            sc = 0.3 + 0.7 * e_out(p) + 0.12 * math.sin(clamp01(p) * math.pi)
        paste(cv, self.sp, x, y, 1.0, self.scale * cx.z * sc, self.rot)


class Squash(E):
    """cicin cards get swatted flat."""
    def __init__(self, cards, empties, src_img, t0, t1):
        super().__init__(t0, t1)
        self.items = []
        for r, e in zip(cards, empties):
            sp = src_img.crop(tuple(int(v) for v in r)).convert("RGBA")
            ep = src_img.crop(tuple(int(v) for v in e)).convert("RGB").resize(sp.size)
            self.items.append((r, sp, ep))

    def draw(self, cv, g, cx):
        k = e_in(clamp01((g - self.t0) / 0.07))
        for i, (r, sp, ep) in enumerate(self.items):
            x0, y0, x1, y1 = cx.rect(r)
            w, h = x1 - x0, y1 - y0
            patch = ep.resize((max(1, int(w)), max(1, int(h))))
            cv.paste(patch, (int(x0), int(y0)))
            sy = 1 - 0.80 * k
            sx = 1 + 0.30 * k
            nw, nh = max(1, int(w * sx)), max(1, int(h * sy))
            s2 = sp.resize((nw, nh), Image.BICUBIC)
            cv.alpha_composite(s2, dest=(int((x0 + x1) / 2 - nw / 2), int(y1 - nh)))


class FlyAway(E):
    def __init__(self, rects, frame, t0, t1):
        super().__init__(t0, t1)
        self.items = []
        for i, r in enumerate(rects):
            ri = tuple(int(v) for v in r)
            sp = frame.crop(ri).convert("RGBA")
            strip = np.asarray(frame.crop((ri[0], ri[1] - 34, ri[2], ri[1] - 12))).reshape(-1, 3).mean(0)
            fill = Image.new("RGB", sp.size, tuple(int(c) for c in strip))
            self.items.append((r, sp, fill, -1 if i == 0 else 1))

    def draw(self, cv, g, cx):
        u = g - self.t0
        for (r, sp, fill, side) in self.items:
            x0, y0, x1, y1 = cx.rect(r)
            w, h = x1 - x0, y1 - y0
            cv.paste(fill.resize((max(1, int(w)), max(1, int(h)))), (int(x0), int(y0)))
            if u < 0.75:
                k = e_in(u / 0.75)
                cxp = (x0 + x1) / 2 + side * 900 * k
                cyp = (y0 + y1) / 2 - 900 * k + 120 * math.sin(k * math.pi)
                spr = sp.resize((max(1, int(w)), max(1, int(h))), Image.BICUBIC)
                paste(cv, spr, cxp, cyp, 1.0, 1 + 0.35 * k, -side * 40 * k)


class Overlay(E):
    """chroma-keyed clip over the shot (screen space)."""
    def __init__(self, clip, x, y, height, t0, t1, key=True):
        super().__init__(t0, t1)
        self.clip, self.x, self.y, self.height, self.key = clip, x, y, height, key

    def draw(self, cv, g, cx):
        fr = self.clip.at(g - self.t0)
        if fr is None:
            return
        im = chroma(fr) if self.key else fr.convert("RGBA")
        k = self.height / im.height
        p = clamp01((g - self.t0) / 0.14)
        sc = 0.4 + 0.6 * e_out(p)
        paste(cv, im.resize((int(im.width * k), int(im.height * k)), Image.BILINEAR), self.x, self.y, 1.0, sc)


class Shot3:
    def __init__(self, t0, t1, cam=None, world=None, screen=None, shake=None):
        self.t0, self.t1 = t0, t1
        self.cam = cam or Cam3(FULL)
        self.world, self.screen, self.shake = world, screen, shake
        self.els = []

    def render(self, g):
        sh = self.shake(g) if self.shake else (0, 0)
        if self.screen is not None:
            base = self.screen(g)
            if sh != (0, 0):
                base = base.transform(base.size, Image.AFFINE, (1, 0, sh[0], 0, 1, sh[1]), resample=Image.BILINEAR)
            cx = Ctx(FULL)
        else:
            pose = self.cam.pose(g)
            cx = Ctx(pose, sh)
            base = apply_cam(self.world(g), pose, sh)
        cv = base.convert("RGBA")
        for e in self.els:
            if e.t0 - 1e-6 <= g < e.t1:
                e.draw(cv, g, cx)
        return cv


SHOTS = []


def add(s):
    SHOTS.append(s)
    return s


def clipfn(clip, t0, fitter):
    return lambda g: fitter(clip.at(g - t0))


# ---------------------------------------------------------------------
# 0. Cold open: Vislava, tragedy, silence
# ---------------------------------------------------------------------
V1c = Clip(f"{WORK}/V1_cfr.mp4", 16.90, speed=0.60, src_end=18.45)
add(Shot3(*S_COLD, cam=Cam3(FULL, [(0.0, S_COLD[1], (1200, 600, 1.07))]), world=lambda g: V1c.at(g - S_COLD[0])))

# ---------------------------------------------------------------------
# 1. Varesa, "Юные лудоманы"
# ---------------------------------------------------------------------
V0 = Clip(f"{WORK}/V0_cfr.mp4", 0.0)
add(Shot3(*S_VARESA, cam=Cam3((1170, 520, 1.12)), world=lambda g: V0.at(g - S_VARESA[0]),
          shake=shake_fn([(S_VARESA[0], 14)])))

# skeleton waiting at the window: "Пока ждём Скирк и Эскофье"
SKEL = Clip(PACK + "/03_bonus/X08_skeleton_window.mp4", 2.0)
add(Shot3(*S_SKEL, screen=clipfn(SKEL, S_SKEL[0], lambda im: fit_blur_fill(im).convert("RGBA"))))

# walk to Lilyuo + НАТЛАНБЕТ
V3w = Clip(f"{WORK}/V3_cfr.mp4", 1.60, speed=0.62, src_end=3.12)
sW = add(Shot3(*S_WALK, cam=Cam3((1250, 560, 1.12), [(S_WALK[0], S_WALK[1] - S_WALK[0], (1300, 570, 1.20))]),
               world=lambda g: V3w.at(g - S_WALK[0]), shake=shake_fn([(T_SIGN, 16)])))
sW.els.append(WSprite(natlanbet_banner(), 1611, 586, T_SIGN, S_WALK[1], scale=0.72, rot=4, pop=0.12, slam=True))

# ---------------------------------------------------------------------
# 2. Percentages (S1)
# ---------------------------------------------------------------------
PCT_L_VAL = (380, 360, 530, 428)
sP = add(Shot3(*S_PCT, cam=Cam3(FULL, [(T_HERN - 0.08, 0.18, (1944, 398, 2.2), e_out)]), world=lambda g: S1))
sP.els += [Circle(R_COIN, vo("v2", 0.85), T_HERN - 0.1, seed=11),
           Circle(PCT_L_VAL, vo("v2", 2.35), T_HERN - 0.1, seed=12),
           Circle(PCT_R_VAL, vo("v2", 2.75), S_PCT[1], seed=13)]

SHEEP = Clip(PACK + "/04_reserve_SD/V3_sheep_b.mp4", 0.5)
add(Shot3(*S_SHEEP, screen=clipfn(SHEEP, S_SHEEP[0], lambda im: fit_blur_fill(im).convert("RGBA"))))

# ---------------------------------------------------------------------
# 3. Battle 1 line-up (S1 grid)
# ---------------------------------------------------------------------
HAT = chef_hat(140)
EMPTY = [card(3, 1), card(2, 2), card(2, 3), card(3, 4)]
sD = add(Shot3(*S_B1, cam=Cam3(GRID), world=lambda g: S1, shake=shake_fn([(T_SLAP, 18)])))
for i, (r, t) in enumerate(zip(B1_CICIN, T_TICKS)):
    sD.els.append(Circle(r, t, vo("v3b", 2.90), seed=20 + i, dur=0.14))
sD.els += [Circle(B1_SOUP, vo("v3a", 2.42), vo("v3b", 2.90), seed=31),
           Circle(B1_RIGHT, vo("v3b", 2.95), vo("v3b", 4.70), seed=32),
           Circle(union(*B1_MOLD), vo("v3b", 4.75), S_B1[1], seed=33),
           Squash(B1_CICIN, EMPTY, S1, T_SLAP, S_WHY[1]),
           WSprite(HAT, COLX[1] - 6, ROWY[2] - 70, T_HAT, S_WHY[1], scale=0.80, rot=-14)]


# ---------------------------------------------------------------------
# 4. Why the left side (S1 -> V3 crossfade), bet, "Прости, семья"
# ---------------------------------------------------------------------
V3e = Clip(f"{WORK}/V3_cfr.mp4", 27.45, speed=0.47, src_end=30.20)


def world_E(g):
    if g < T_XF:
        return S1
    fr = V3e.at(g - T_XF)
    k = e_inout((g - T_XF) / 0.30)
    return Image.blend(S1, fr, k) if k < 1 else fr


T_105 = vo("v4a", 4.14)
sE = add(Shot3(*S_WHY, cam=Cam3(GRID, [(T_105 - 0.20, 0.26, LEFTP, e_out)]), world=world_E))
TYPE1 = stroke_text([("ОДИНОЧНАЯ ЦЕЛЬ", T_SINGLE), ("  >  ", WHITE), ("ПО ПЛОЩАДИ", T_AREA)], 52)
TYPE2 = stroke_text([("ДАЛЬНИЙ БОЙ", T_RANGED), ("  >  ", WHITE), ("ПОЛЁТ", T_FLY)], 52)
sE.els += [Circle(B1_SOUP, vo("v4a", 0.30), T_105 - 0.22, seed=41),
           Circle(union(*B1_MOLD), vo("v4a", 3.05), T_105 - 0.22, seed=42),
           Txt(TYPE1, 960, 958, vo("v4a", 1.05), T_105 - 0.22),
           Txt(TYPE2, 960, 1036, vo("v4a", 2.15), T_105 - 0.22),
           Squash(B1_CICIN, EMPTY, S1, S_WHY[0] - 1, S_WHY[1]),
           WSprite(HAT, COLX[1] - 6, ROWY[2] - 70, S_WHY[0] - 1, S_WHY[1], scale=0.80, rot=-14),
           Circle(MUL_L_VAL, vo("v4a", 5.00), S_WHY[1], seed=43),
           Circle(R_PUT_L, vo("v4a", 6.55), S_WHY[1], seed=44)]

M04 = Clip(SRC + "/M04_homelander.mp4", 1.55)
add(Shot3(*S_HOME, screen=clipfn(M04, S_HOME[0], lambda im: cover(im, focus=(0.42, 0.5)).convert("RGBA"))))

# ---------------------------------------------------------------------
# 5. Battle 2 (S2 grid), kitten, archers, Gosling
# ---------------------------------------------------------------------
sG = add(Shot3(*S_B2, cam=Cam3(GRID), world=lambda g: S2))
sG.els += [Circle(B2_LEFT, vo("v5a", 0.75), vo("v5a", 1.55), seed=51),
           Circle(B2_LAVA, vo("v5a", 1.60), S_B2[1], seed=52),
           Circle(B2_HEAL, vo("v5a", 2.60), S_B2[1], seed=53),
           Circle(B2_SAPHO, vo("v5a", 3.45), S_B2[1], seed=54)]

M03 = Clip(SRC + "/M03_cat.mp4", 2.30)
LBL_S = stroke_text("САПФО", 92, OSW)
LBL_S2 = stroke_text("САПФО", 64, OSW)
LBL_L = stroke_text("ЛАВАЧУРЛ", 92, OSW)
KCROP = (0.5, 0.5)


def kitten_screen(g):
    lt = g - S_KITTEN[0]
    cv = fit_blur_fill(M03.at(lt)).convert("RGBA")
    src = 2.30 + lt
    if 2.38 <= src < 3.42:
        paste(cv, LBL_S, 1230, 560, 1.0, pop_scale((src - 2.38) / 0.1))
    if src >= 4.78:
        paste(cv, LBL_L, 653, 340, 1.0, pop_scale((src - 4.78) / 0.1))
        paste(cv, LBL_S2, 1143, 650, 1.0, pop_scale((src - 4.86) / 0.1))
    return cv


add(Shot3(*S_KITTEN, screen=kitten_screen))

sI = add(Shot3(*S_ARCH, cam=Cam3(GRID), world=lambda g: S2))
SAP = (COLX[4], ROWY[3])
sI.els += [Circle(B2_SAPHO, S_ARCH[0], S_ARCH[1], seed=54, dur=0.01),
           Arrow((COLX[2] + 40, ROWY[1] + 30), (COLX[4] - 70, ROWY[3] - 40), vo("v5b", 4.90), vo("v5b", 6.40), seed=61),
           Arrow((COLX[2] + 40, ROWY[4] - 30), (COLX[4] - 70, ROWY[3] + 40), vo("v5b", 5.10), vo("v5b", 6.40), seed=62),
           Arrow((COLX[4] - 70, ROWY[3] - 10), (COLX[1] + 60, ROWY[2] + 20), vo("v5b", 6.60), S_ARCH[1], seed=63),
           Arrow((COLX[4] - 70, ROWY[3] + 5), (COLX[3] + 40, ROWY[1] + 40), vo("v5b", 6.80), S_ARCH[1], seed=64),
           Arrow((COLX[4] - 70, ROWY[3] + 25), (COLX[3] + 30, ROWY[4] - 10), vo("v5b", 7.00), S_ARCH[1], seed=65)]

GOSL = Clip(PACK + "/03_bonus/X15_gosling_confused.mp4", 3.50, crop=(0, 352, 720, 928))
add(Shot3(*S_GOSL, screen=clipfn(GOSL, S_GOSL[0], lambda im: fit_blur_fill(im).convert("RGBA"))))

# ---------------------------------------------------------------------
# 6. The bet on Sapho, jackpot, rules, aw dang it, kef
# ---------------------------------------------------------------------
sJ = add(Shot3(*S_BET, cam=Cam3(GRID, [(S_BET[0] + 0.05, 0.26, RIGHT2, e_out)]), world=lambda g: S2))
sJ.els += [Circle(B2_SAPHO, vo("v6a", 0.30), S_BET[1], seed=71),
           Circle(MUL_R2_VAL, vo("v6a", 2.55), S_BET[1], seed=72)]

JACK = Clip(PACK + "/03_bonus/X20_jackpot_original.mp4", 1.00)
BG_J = apply_cam(S2, RIGHT2).convert("RGBA")


def jack_screen(g):
    cv = BG_J.copy()
    fr = JACK.at(g - S_JACK[0])
    guy = chroma(fr).resize((1080, 1080), Image.BILINEAR)
    cv.alpha_composite(guy, dest=(1300 - 540, 0))
    return cv


add(Shot3(*S_JACK, screen=jack_screen, shake=shake_fn([(S_JACK[0] + 0.9, 10), (S_JACK[0] + 1.4, 8)])))

V3r = Clip(f"{WORK}/V3_cfr.mp4", 35.60, speed=0.80)
sR = add(Shot3(*S_RULES, cam=Cam3((1150, 820, 1.35)), world=lambda g: V3r.at(g - S_RULES[0])))
sR.els += [ULine(RULES_UL[0], RULES_UL[1], RULES_UL[2], vo("v6b", 5.30), S_RULES[1], seed=81)]

AW = Clip(PACK + "/01_main/V1_aw_dang_it_ready.mp4", 0.0)
add(Shot3(*S_AW, screen=clipfn(AW, S_AW[0], lambda im: fit_blur_fill(im, fill=(255, 255, 255)).convert("RGBA"))))

sK = add(Shot3(*S_KEF, cam=Cam3(RIGHT2, [(vo("v6c", 9.20), 1.9, (1880, 430, 1.75))]), world=lambda g: S2))
sK.els += [Circle(MUL_R2_VAL, vo("v6c", 6.35), S_KEF[1], seed=91),
           Circle(PCT_R_VAL, vo("v6c", 7.55), S_KEF[1], seed=92)]

# ---------------------------------------------------------------------
# 7. Vige roast
# ---------------------------------------------------------------------
V2v = Clip(f"{WORK}/V2_cfr.mp4", 19.0, speed=0.89, src_end=21.35)
sV = add(Shot3(*S_VIGE, cam=Cam3(FULL), world=lambda g: V2v.at(g - S_VIGE[0])))
sV.els += [ULine(VIGE_UL[0][0], VIGE_UL[0][1], VIGE_UL[0][2], S_VIGE[0] + 1.75, S_VIGE[1], seed=101),
           ULine(VIGE_UL[1][0], VIGE_UL[1][1], VIGE_UL[1][2], S_VIGE[0] + 2.05, S_VIGE[1], seed=102)]

# ---------------------------------------------------------------------
# 8. Risky bet -> penguin -> bets fly away -> calm option
# ---------------------------------------------------------------------
V3k = Clip(f"{WORK}/V3_cfr.mp4", 59.1, speed=0.56, src_end=65.2)
sRk = add(Shot3(*S_RISK, cam=Cam3(OVERVIEW), world=lambda g: V3k.at(g - S_RISK[0])))
sRk.els += [Circle(OV_B1L, vo("v7a", 0.45), S_RISK[1], seed=111),
            Circle(OV_B2R, vo("v7a", 0.70), S_RISK[1], seed=112)]

PENG = Clip(PACK + "/01_main/V2_penguin_b.mp4", 15.30)
PENG_FOCUS = (790, 845)


def peng_screen(g):
    lt = g - S_PENG[0]
    fr = PENG.at(lt)
    z = 1.0 + 0.75 * e_inout(lt / (S_PENG[1] - S_PENG[0]))
    sw, sh = fr.size
    w, h = sw / z, sw / z * 9 / 16
    cxp = sw / 2 + (PENG_FOCUS[0] - sw / 2) * (1 - 1 / z) * 1.6
    cyp = sh / 2 + (PENG_FOCUS[1] - sh / 2) * (1 - 1 / z) * 1.6
    x0 = min(max(cxp - w / 2, 0), sw - w); y0 = min(max(cyp - h / 2, 0), sh - h)
    return fr.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h)).convert("RGBA")


add(Shot3(*S_PENG, screen=peng_screen))

V3f = Clip(f"{WORK}/V3_cfr.mp4", 60.35, speed=0.56, src_end=65.2)
sF = add(Shot3(*S_FLY, cam=Cam3(OVERVIEW), world=lambda g: V3f.at(g - S_FLY[0]),
               shake=shake_fn([(T_FLYAWAY, 12)])))
fly_frame = still("V3", round(60.35 + (T_FLYAWAY - S_FLY[0]) * 0.56, 2))
sF.els += [Circle(OV_B1L, S_FLY[0], T_FLYAWAY, seed=111, dur=0.01),
           Circle(OV_B2R, S_FLY[0], T_FLYAWAY, seed=112, dur=0.01),
           FlyAway([OV_B1L, OV_B2R], fly_frame, T_FLYAWAY, S_FLY[1]),
           Circle(OV_B1R, vo("v7c", 7.95), S_FLY[1], seed=113),
           Circle(OV_B2L, vo("v7c", 8.55), S_FLY[1], seed=114)]

# ---------------------------------------------------------------------
# 9. Check odds & timer (+ hamster), Vislava irony
# ---------------------------------------------------------------------
V3o = Clip(f"{WORK}/V3_cfr.mp4", 41.15, speed=0.62, src_end=43.70)
sO = add(Shot3(*S_CHECK, cam=Cam3(FULL), world=lambda g: V3o.at(g - S_CHECK[0])))
HAM = Clip(PACK + "/03_bonus/X13_hamster_phone.mp4", 4.0)
sO.els += [Circle(MUL_L_VAL, vo("v8a", 1.40), vo("v8a", 2.50), seed=121),
           Circle(MUL_R_VAL, vo("v8a", 1.52), vo("v8a", 2.50), seed=122),
           Circle(R_TIMER, vo("v8a", 1.92), vo("v8a", 2.50), seed=123),
           Overlay(HAM, 1690, 760, 560, vo("v8a", 0.15), vo("v8a", 2.45))]

V1v = Clip(f"{WORK}/V1_cfr.mp4", 3.10, src_end=6.15)
sVl = add(Shot3(*S_VISL, cam=Cam3(FULL), world=lambda g: V1v.at(g - S_VISL[0])))
sVl.els += [ULine(VISL_UL[0], VISL_UL[1], VISL_UL[2], S_VISL[0] + 1.62, S_VISL[1], seed=131)]

# ---------------------------------------------------------------------
# 10. The pot (no titles) + eulogy tag
# ---------------------------------------------------------------------
POT_S = 0.80
POT = Image.open(SRC + "/pot.webp").convert("RGBA")
POT = POT.resize((int(POT.width * POT_S), int(POT.height * POT_S)), Image.LANCZOS)
POT_XY = (960 - int(768 * POT_S), 1052 - int(980 * POT_S))
_pa = np.asarray(POT).astype(np.float32).copy()
_yy = np.arange(_pa.shape[0])[:, None]
_ramp = np.clip((int(250 * POT_S) - _yy) / (90 * POT_S), 0, 1)
_st = _pa.copy(); _st[..., 3] *= _ramp
STEAM = Image.fromarray(_st.astype(np.uint8), "RGBA")
RIM_C = (POT_XY[0] + 770 * POT_S, POT_XY[1] + 360 * POT_S)
RIM_A = (522 * POT_S, 126 * POT_S)
SOUP_Y = POT_XY[1] + 418 * POT_S


def make_pot_bg():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - 960) / 1150) ** 2 + ((yy - 640) / 820) ** 2)
    k = np.clip(d, 0, 1) ** 1.3
    inner = np.array([66, 46, 34], np.float32)
    outer = np.array([10, 8, 10], np.float32)
    img = inner * (1 - k[..., None]) + outer * k[..., None]
    sh = np.exp(-(((xx - 960) / 560) ** 2 + ((yy - 1046) / 46) ** 2))
    img *= (1 - 0.65 * sh[..., None])
    img += np.random.default_rng(1).normal(0, 1.3, img.shape)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")


POT_BG = make_pot_bg()
_sil = Image.new("L", (W, H), 0)
_sil.paste(POT.getchannel("A").point(lambda v: 255 if v > 150 else 0), POT_XY)
_op = Image.new("L", (W, H), 0)
ImageDraw.Draw(_op).ellipse([RIM_C[0] - RIM_A[0] + 18, RIM_C[1] - RIM_A[1] + 8, RIM_C[0] + RIM_A[0] - 18,
                             RIM_C[1] + RIM_A[1] - 6], fill=255)
_op.paste(0, (0, int(SOUP_Y - 2), W, H))
VISMASK = Image.fromarray(np.maximum(255 - np.asarray(_sil), np.asarray(_op)).astype(np.uint8)).filter(
    ImageFilter.GaussianBlur(1.2))


def crop_card(img, r, size):
    c = img.crop(r).resize(size, Image.LANCZOS).convert("RGBA")
    m = Image.new("L", (size[0] * 3, size[1] * 3), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] * 3 - 1, size[1] * 3 - 1], radius=40, fill=255)
    c.putalpha(m.resize(size, Image.LANCZOS))
    return c


ov = still("V3", 6.0)
gr = still("V3", 10.0)
_cs = crop_card(ov, (902, 294, 1039, 426), (170, 164))
CARD_SOUP = Image.new("RGBA", (190, 252), (0, 0, 0, 0))
CARD_SOUP.alpha_composite(_cs, dest=(10, 78))
CARD_SOUP.alpha_composite(chef_hat(120).rotate(-12, resample=Image.BICUBIC, expand=True), dest=(22, 0))
CARD_CICIN = crop_card(gr, (948, 334, 1056, 426), (176, 150))
CARD_SAPHO = crop_card(ov, (1746, 662, 1884, 798), (166, 164))
DROPS = [(CARD_SOUP, DROP_T[0], -170, -18, 10), (CARD_CICIN, DROP_T[1], 160, 16, -8), (CARD_SAPHO, DROP_T[2], -10, -10, 6)]
CARD_SC = 1.25


def pot_screen(g):
    cv = POT_BG.copy()
    lt = g - T_POT
    cv.alpha_composite(POT, dest=POT_XY)
    for k, (amp, sp_, ph, al) in enumerate([(9, 1.1, 0.0, 0.40), (12, 0.8, 2.0, 0.28)]):
        ph_t = (lt * 0.22 + k * 0.5) % 1.0
        st = with_alpha(STEAM, al * math.sin(math.pi * ph_t))
        cv.alpha_composite(st, dest=(int(POT_XY[0] + amp * math.sin(lt * sp_ + ph)), int(POT_XY[1] - 70 * ph_t)))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    splash = []
    for (sp, t0, dx, rot0, rot1) in DROPS:
        tt = g - t0
        if tt < 0:
            continue
        tx = RIM_C[0] + dx * 0.55
        hang_y = 318
        ch = sp.height * CARD_SC
        yt = SOUP_Y - ch / 2 + 26
        hx = tx + dx * 0.25
        if tt < 0.35:
            k = e_out(tt / 0.35)
            x, y, r = hx, -260 + (hang_y + 260) * k, rot0 * (1 - k) + rot0 * 0.4 * k
            a = 1.0
        elif tt < 0.70:
            u = tt - 0.35
            x, y, r = hx, hang_y + 6 * math.sin(u * 18), rot0 * 0.4 * math.cos(u * 12)
            a = 1.0
        elif tt < FALL:
            k = e_in((tt - 0.70) / (FALL - 0.70))
            x = hx + (tx - hx) * k
            y = hang_y + (yt - hang_y) * k
            r = rot0 * 0.4 + (rot1 - rot0 * 0.4) * k
            a = 1.0
        else:
            s = tt - FALL
            x, y, r = tx, yt + (ch + 10) * e_out(s / 0.7), rot1
            a = 1 - clamp01((s - 0.45) / 0.3)
            splash.append((tx, SOUP_Y + 6, s))
        if a > 0:
            paste(lay, sp, x, y, a, CARD_SC, r)
    if lay.getbbox():
        lay.putalpha(Image.fromarray((np.asarray(lay.getchannel("A")).astype(np.float32) *
                                      np.asarray(VISMASK).astype(np.float32) / 255).astype(np.uint8)))
        cv.alpha_composite(lay)
    sl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sl)
    for (sx, sy, s) in splash:
        if s < 0.7:
            k = e_out(s / 0.7)
            rx, ry = 40 + 230 * k, 10 + 46 * k
            sd.ellipse([sx - rx, sy - ry, sx + rx, sy + ry], outline=(255, 214, 150, int(150 * (1 - k))), width=4)
        rng = random.Random(int(sx))
        for i in range(12):
            vx = rng.uniform(-260, 260); vy = rng.uniform(-620, -320)
            px, py = sx + vx * s, sy + vy * s + 0.5 * 1800 * s * s
            if s < 0.75 and py < sy + 10:
                rr = rng.uniform(5, 10) * (1 - s)
                sd.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(214, 150, 70, int(230 * (1 - s / 0.75))))
    cv.alpha_composite(sl)
    if g > T_BULK - 0.35:
        s = g - (T_BULK - 0.35)
        bx, by = RIM_C[0] + 60, SOUP_Y
        bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bl)
        if s < 0.35:
            r = 20 + 60 * e_out(s / 0.35)
            bd.ellipse([bx - r, by - r * 0.75, bx + r, by + r * 0.35], fill=(220, 160, 80, 230), outline=(255, 230, 180, 255), width=3)
            bd.ellipse([bx - r * 0.45, by - r * 0.55, bx - r * 0.1, by - r * 0.3], fill=(255, 245, 220, 200))
        elif s < 0.95:
            k = e_out((s - 0.35) / 0.6)
            rr = 90 + 160 * k
            bd.ellipse([bx - rr, by - rr * 0.22, bx + rr, by + rr * 0.22], outline=(255, 220, 160, int(170 * (1 - k))), width=4)
            rng = random.Random(5)
            for i in range(10):
                ang = rng.uniform(math.pi * 1.05, math.pi * 1.95)
                dist = 40 + 180 * k
                px, py = bx + math.cos(ang) * dist, by + math.sin(ang) * dist * 0.9 + 260 * (s - 0.35) ** 2
                ra = 7 * (1 - k)
                bd.ellipse([px - ra, py - ra, px + ra, py + ra], fill=(220, 160, 80, int(220 * (1 - k))))
        cv.alpha_composite(bl)
    return cv


add(Shot3(*S_POT, screen=pot_screen))

V1t = Clip(f"{WORK}/V1_cfr.mp4", 36.95, speed=0.65, src_end=38.05)
sT = add(Shot3(*S_TAG, cam=Cam3(FULL, [(S_TAG[0], END - S_TAG[0], (1500, 620, 1.12))]), world=lambda g: V1t.at(g - S_TAG[0])))
sT.els += [Circle(TAG_OPT, S_TAG[0] + 0.45, END + 1, seed=141, dur=0.24)]


# =====================================================================
def frame_at(g):
    for s in SHOTS:
        if s.t0 - 1e-6 <= g < s.t1 - 1e-6:
            return s.render(g).convert("RGB")
    return Image.new("RGB", (W, H), (0, 0, 0))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "stills":
        out = sys.argv[2]
        os.makedirs(out, exist_ok=True)
        for t in [float(x) for x in sys.argv[3:]]:
            frame_at(t).save(f"{out}/f_{t:06.2f}.jpg", quality=90)
            print("saved", t, flush=True)
    elif mode == "video":
        t0, t1, out = float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
        n0, n1 = int(round(t0 * FPS)), int(round(t1 * FPS))
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                                "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
        for n in range(n0, n1):
            enc.stdin.write(frame_at(n / FPS).tobytes())
            if n % 60 == 0:
                print(f"{out}: {n / FPS:.1f}s", flush=True)
        enc.stdin.close()
        enc.wait()
        print("done", out)
