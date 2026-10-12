"""Edit decision list for 'Господин объясняет первые два боя' + frame renderer."""
import sys, os, subprocess, math, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from gfx import *

P = os.environ.get("PROJ")
SRC = P + "/src"
WORK = P + "/work"
FPS = 30
WW, WH = 2400, 1080

from timing import *

# =====================================================================
# Sources
# =====================================================================
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
# Element helpers (world-anchored unless stated)
# =====================================================================
class E:
    def __init__(self, t0, t1, fin=0.22, fout=0.18):
        self.t0, self.t1, self.fin, self.fout = t0, t1, fin, fout

    def env(self, g):
        return life(g, self.t0, self.t1, self.fin, self.fout)


class Box(E):
    def __init__(self, rect, color, t0, t1, stroke=5, alpha=1.0, dim_after=None):
        super().__init__(t0, t1, 0.24, 0.2)
        self.rect, self.color, self.stroke, self.alpha, self.dim_after = rect, color, stroke, alpha, dim_after

    def draw(self, cv, g, cx):
        a, p = self.env(g)
        if self.dim_after and g > self.dim_after[0]:
            a *= 1 - (1 - self.dim_after[1]) * e_out((g - self.dim_after[0]) / 0.3)
        draw_box(cv, cx.rect(self.rect), self.color, a * self.alpha, p, self.stroke)


class Spot(E):
    def __init__(self, rects, t0, t1, amount=0.5):
        super().__init__(t0, t1, 0.3, 0.3)
        self.rects, self.amount = rects, amount


class Sprite(E):
    """sprite anchored to world (anchor='w') or screen (anchor='s'); intro: rise / pop / slam."""

    def __init__(self, sp, x, y, t0, t1, anchor="w", intro="rise", rot=0.0, scale=1.0, fin=0.22, fout=0.18,
                 world_scale=False):
        super().__init__(t0, t1, fin, fout)
        self.sp, self.x, self.y, self.anchor, self.intro, self.rot, self.scale = sp, x, y, anchor, intro, rot, scale
        self.world_scale = world_scale

    def draw(self, cv, g, cx):
        a, p = self.env(g)
        if a <= 0.003:
            return
        x, y = (cx.pt(self.x, self.y) if self.anchor == "w" else (self.x, self.y))
        sc = self.scale * (cx.z if self.world_scale else 1.0)
        dy = 0
        if self.intro == "rise":
            dy = 16 * (1 - e_out(p))
        elif self.intro == "pop":
            sc *= 0.55 + 0.45 * e_back(p, 2.2)
        elif self.intro == "slam":
            k = clamp01(p)
            sc *= 1.0 + 0.55 * (1 - e_out(k)) ** 2
            a = min(a, clamp01(p * 3))
        sp = self.sp(g) if callable(self.sp) else self.sp
        paste(cv, sp, x, y + dy, a, sc, self.rot)


class Arrow(E):
    def __init__(self, p0, p1, bend, color, t0, t1):
        super().__init__(t0, t1, 0.4, 0.2)
        self.p0, self.p1, self.bend, self.color = p0, p1, bend, color

    def draw(self, cv, g, cx):
        a, p = self.env(g)
        draw_arrow(cv, cx.pt(*self.p0), cx.pt(*self.p1), self.bend * cx.z, self.color, e_out(p), a)


class Wave(E):
    def __init__(self, origin, t0, t1):
        super().__init__(t0, t1, 0.2, 0.5)
        self.origin = origin

    def draw(self, cv, g, cx):
        a, p = self.env(g)
        draw_wave(cv, cx.pt(*self.origin), 180, g - self.t0, a, BLU, reach=int(330 * cx.z))


class Underline(E):
    def __init__(self, line, color, t0, t1):
        super().__init__(t0, t1, 0.45, 0.2)
        self.line, self.color = line, color

    def draw(self, cv, g, cx):
        a, p = self.env(g)
        if a <= 0.003:
            return
        x0, y0 = cx.pt(self.line[0], self.line[1])
        x1, _ = cx.pt(self.line[2], self.line[3])
        k = e_out(p)
        xe = x0 + (x1 - x0) * k
        lay = ss_round_rect(max(2, int(xe - x0)), 9, 4, fill=rgba(self.color))
        glow = Image.new("RGBA", (lay.width + 40, lay.height + 40), (0, 0, 0, 0))
        glow.alpha_composite(lay, dest=(20, 20))
        glow = glow.filter(ImageFilter.GaussianBlur(6))
        glow.alpha_composite(lay, dest=(20, 20))
        paste(cv, glow, (x0 + xe) / 2, y0 + 4, a)


def cap(lines, t0, t1, accent=None, size=48, y=None):
    sp = caption(lines, size=size, accent=accent)
    yy = y if y is not None else 1040 - sp.height / 2 + 30
    return Sprite(sp, 960, yy, t0, t1, anchor="s", intro="rise", fin=0.24, fout=0.2)


# =====================================================================
# Shots
# =====================================================================
class Shot:
    def __init__(self, t0, t1, cam=None, els=(), spots=(), world=None, screen=None):
        self.t0, self.t1 = t0, t1
        self.cam = cam or Cam(FULL)
        self.els = list(els)
        self.spots = list(spots)
        self.world = world      # fn(g) -> world PIL image
        self.screen = screen    # fn(g) -> screen RGBA (overrides world/cam)
        self.shake = None

    def render(self, g):
        if self.screen is not None:
            base = self.screen(g)
            cx = Ctx(FULL)
        else:
            pose = self.cam.pose(g)
            sh = self.shake(g) if self.shake else (0, 0)
            cx = Ctx(pose, sh)
            base = apply_cam(self.world(g), pose, sh)
        arr = np.asarray(base.convert("RGB"))
        holes, amt = [], 0.0
        for s in self.spots:
            a, _ = s.env(g)
            if a > 0:
                amt = max(amt, s.amount * a)
                holes += [cx.rect(r) for r in s.rects]
        if amt > 0:
            arr = spotlight(arr, holes, amt)
        cv = Image.fromarray(arr).convert("RGBA")
        for e in self.els:
            if e.t0 - 0.01 <= g <= e.t1 + 0.01:
                e.draw(cv, g, cx)
        return cv


SHOTS = []


def add(shot):
    SHOTS.append(shot)
    return shot


def blur_bg(img, dark=0.42, radius=16):
    im = img.resize((W // 2, H // 2), Image.BILINEAR).filter(ImageFilter.GaussianBlur(radius / 2))
    im = im.resize((W, H), Image.BILINEAR)
    a = np.asarray(im).astype(np.float32) * dark
    return Image.fromarray(a.astype(np.uint8))


MEME_BOX = (1760, 900)


def meme_card_screen(bg, clip, g0, label_fn=None, t_in=0.24):
    """Return screen fn: blurred bg + rounded meme window popping in."""
    sw, sh = clip.osize
    k = min(MEME_BOX[0] / sw, MEME_BOX[1] / sh)
    mw, mh = int(sw * k) // 2 * 2, int(sh * k) // 2 * 2
    mask = ss_round_rect(mw, mh, 26, fill=(255, 255, 255, 255)).getchannel("A")
    border = ss_round_rect(mw + 4, mh + 4, 28, outline=(255, 255, 255, 70), width=2)
    shadow = Image.new("RGBA", (mw + 160, mh + 160), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 170), (80, 92, 80 + mw, 92 + mh))
    shadow = shadow.filter(ImageFilter.GaussianBlur(30))

    def fn(g):
        cv = bg.convert("RGBA").copy()
        lt = g - g0
        fr = clip.at(lt).resize((mw, mh), Image.BICUBIC).convert("RGBA")
        fr.putalpha(mask)
        card_ = Image.new("RGBA", shadow.size, (0, 0, 0, 0))
        card_.alpha_composite(shadow)
        card_.alpha_composite(fr, dest=(80, 80))
        card_.alpha_composite(border, dest=(78, 78))
        p = clamp01(lt / t_in)
        sc = 0.93 + 0.07 * e_back(p, 1.6)
        a = clamp01(lt / 0.10)
        paste(cv, card_, W / 2, H / 2, a, sc)
        if label_fn:
            label_fn(cv, lt, (W / 2 - mw / 2, H / 2 - mh / 2, mw, mh))
        return cv
    return fn


# ---------------------------------------------------------------------
# A. Varesa close-up + lower third
# ---------------------------------------------------------------------
V0 = Clip(f"{WORK}/V0_cfr.mp4", 0.0)
sA = add(Shot(0.0, 3.20, Cam((1170, 520, 1.12), [(0.0, 3.2, (1170, 505, 1.17))]),
              world=lambda g: V0.at(g)))
sA.els += [Sprite(lower_third("ГОСПОДИН", "эксперт по вероятным победам"), 480, 860, 0.85, 3.20, anchor="s",
                  intro="rise", fin=0.3, fout=0.01)]

# ---------------------------------------------------------------------
# B. Walk to the event + НАТЛАНБЕТ
# ---------------------------------------------------------------------
V3a = Clip(f"{WORK}/V3_cfr.mp4", 0.30, speed=0.68, src_end=3.12)
sB = add(Shot(3.20, 8.55, Cam((1230, 560, 1.12), [(3.2, 5.35, (1290, 560, 1.20))]),
              world=lambda g: V3a.at(g - 3.20)))
sign_frames = [natlanbet_sign(i) for i in range(3)]
sB.els += [Sprite(lambda g: sign_frames[int((g - T_SIGN) * 5) % 3], 1611, 552, T_SIGN, 8.55, anchor="w",
                  intro="slam", rot=5.0, scale=0.82, fin=0.16, fout=0.01)]
sB.shake = lambda g: ((math.sin((g - T_SIGN) * 70) * 7 * math.exp(-(g - T_SIGN) * 9)) if g > T_SIGN else 0, 0)

# ---------------------------------------------------------------------
# C. What the percentages mean (S1 full)
# ---------------------------------------------------------------------
sC = add(Shot(8.55, 16.05, Cam(FULL, [(15.45, 0.85, GRID)]), world=lambda g: S1))
sC.els += [
    Box(R_COIN, YEL, vo("v2", 0.05), vo("v2", 1.85)),
    Sprite(chip("+100 эмблем в день", accent=YEL, size=38), 1483, 150, vo("v2", 0.35), vo("v2", 1.85)),
    Box(R_PCT_L, RED, vo("v2", 1.90), 15.40),
    Box(R_PCT_R, BLU, vo("v2", 2.05), 15.40),
    cap([[("Проценты — ", MUTED, "Inter-Bold"), ("доля вложенных эмблем", WHITE, "Inter-Bold")]],
        vo("v2", 2.30), 15.40, accent=YEL),
    Sprite(stamp("НЕ ШАНС\nПОБЕДЫ", size=66), 1925, 420, T_HERN, 15.40, anchor="w", intro="slam", rot=8,
           fin=0.14, fout=0.2),
]
sC.spots += [Spot([R_COIN], vo("v2", 0.05), vo("v2", 1.75), 0.45),
             Spot([R_PCT_L, R_PCT_R], vo("v2", 1.95), 15.35, 0.45)]
sC.shake = lambda g: ((math.sin((g - T_HERN) * 60) * 5 * math.exp(-(g - T_HERN) * 10)) if g > T_HERN else 0, 0)

# ---------------------------------------------------------------------
# D. Battle 1 line-up (S1 grid)
# ---------------------------------------------------------------------
HAT = chef_hat(132)
hat_el = lambda t0, t1, intro="pop": Sprite(HAT, COLX[1] - 6, ROWY[2] - 66, t0, t1, anchor="w", intro=intro,
                                            rot=-14, scale=0.86, world_scale=True, fin=0.3, fout=0.15)
sD = add(Shot(16.05, 25.15, Cam(GRID), world=lambda g: S1))
count_txt = ["3", "3 + 3", "3 + 3 + 3", "3 + 3 + 3 + 3 = 12"]
for i, (r, t) in enumerate(zip(B1_CICIN, T_TICKS)):
    sD.els.append(Box(r, RED, t, vo("v3b", 3.0)))
for i, t in enumerate(T_TICKS):
    t1 = T_TICKS[i + 1] if i < 3 else vo("v3a", 2.30)
    txt = count_txt[i]
    parts = [(txt, WHITE, "InterDisplay-Bold")]
    if i == 3:
        parts = [("3 + 3 + 3 + 3 = ", WHITE, "InterDisplay-Bold"), ("12 комаров", RED, "InterDisplay-Black")]
    sD.els.append(cap([parts], t, t1, size=58, accent=RED) if i == 0 else
                  Sprite(caption([parts], size=58, accent=RED), 960, 1040 - caption([parts], size=58, accent=RED).height / 2 + 30,
                         t, t1, anchor="s", intro="none", fin=0.01, fout=0.01 if i < 3 else 0.2))
sD.els += [
    Box(B1_SOUP, YEL, vo("v3a", 2.40), vo("v3b", 3.0)),
    hat_el(T_HAT, 32.75),
    Sprite(chip("суповар", accent=YEL, size=34), COLX[1], ROWY[2] + 92, T_HAT + 0.15, vo("v3b", 3.0)),
    Box(B1_RIGHT, BLU, vo("v3b", 2.95), vo("v3b", 4.65)),
    Box(union(*B1_MOLD), YEL, vo("v3b", 4.70), 25.15),
    Sprite(type_pill("По площади", T_AREA, 36), 1560, 580, vo("v3b", 5.85), 25.15),
]
for r in B1_CICIN:
    sD.els.append(Box(r, RED, vo("v3b", 6.82), 25.15))
sD.els += [Sprite(relation_chip("По площади", T_AREA, "Отряд", T_SQUAD, size=40), 960, 988,
                  vo("v3b", 6.85), 25.15, anchor="s")]
sD.spots += [
    Spot(B1_CICIN, T_TICKS[0], vo("v3a", 2.35), 0.42),
    Spot(B1_CICIN + [B1_SOUP], vo("v3a", 2.35), vo("v3b", 2.90), 0.42),
    Spot([B1_RIGHT], vo("v3b", 2.95), vo("v3b", 4.65), 0.42),
    Spot([union(*B1_MOLD)], vo("v3b", 4.70), vo("v3b", 6.80), 0.5),
    Spot([union(*B1_MOLD)] + B1_CICIN, vo("v3b", 6.80), 25.15, 0.5),
]

# ---------------------------------------------------------------------
# E. Why Gospodin picked the left side (S1 -> V3 live crossfade)
# ---------------------------------------------------------------------
V3e = Clip(f"{WORK}/V3_cfr.mp4", 27.45, speed=0.47, src_end=30.20)
T_XF = vo("v4a", 1.95)


def world_E(g):
    if g < T_XF:
        return S1
    fr = V3e.at(g - T_XF)
    k = e_inout((g - T_XF) / 0.45)
    return Image.blend(S1, fr, k) if k < 1 else fr


T_105 = vo("v4a", 4.14)
T_PUT = vo("v4a", 5.93)
sE = add(Shot(25.15, 32.75, Cam(GRID, [(T_105 - 0.25, 0.75, LEFTP)]), world=world_E))
sE.els += [
    Box(B1_SOUP, YEL, vo("v4a", 0.30), T_105 - 0.1),
    Box(union(*B1_MOLD), BLU, vo("v4a", 3.05), T_105 - 0.1),
    hat_el(25.15, 32.75, intro="none"),
    Sprite(relation_chip("Одиночная цель", T_SINGLE, "По площади", T_AREA, size=36), 700, 1000,
           vo("v4a", 1.05), T_105 - 0.1, anchor="s"),
    Sprite(relation_chip("Дальний бой", T_RANGED, "Полёт", T_FLY, size=36), 1330, 1000,
           vo("v4a", 2.15), T_105 - 0.1, anchor="s"),
    Box(R_MUL_L, RED, T_105 + 0.25, 32.75),
    Box(R_PUT_L, YEL, T_PUT, 32.75),
    Sprite(chip("моя ставка", accent=YEL, size=36), 800, 886, T_PUT + 0.2, 32.75),
]
sE.spots += [
    Spot([B1_SOUP, union(*B1_MOLD)], 25.2, T_105 - 0.15, 0.48),
    Spot([R_MUL_L], T_105 + 0.25, T_PUT, 0.45),
    Spot([R_MUL_L, R_PUT_L], T_PUT, 32.75, 0.45),
]

# ---------------------------------------------------------------------
# F. Homelander: "Прости, семья."
# ---------------------------------------------------------------------
M04 = Clip(SRC + "/M04_homelander.mp4", 1.55)
bgF = blur_bg(apply_cam(still("V3", 30.6), LEFTP))
add(Shot(32.75, 35.95, screen=meme_card_screen(bgF, M04, 32.75)))

# ---------------------------------------------------------------------
# G. Battle 2 line-up (S2 grid)
# ---------------------------------------------------------------------
T_SAP = vo("v5a", 3.14)
sG = add(Shot(35.95, 40.85, Cam(GRID), world=lambda g: S2))
sG.els += [
    Box(B2_LEFT, RED, vo("v5a", 0.70), vo("v5a", 1.10)),
    Box(B2_LAVA, YEL, vo("v5a", 1.05), T_SAP - 0.05),
    Sprite(chip("броня", accent=YEL, size=34), COLX[1], ROWY[2] + 92, vo("v5a", 1.35), T_SAP - 0.05),
    Box(B2_HEAL, YEL, vo("v5a", 2.45), T_SAP - 0.05),
    Sprite(chip("хилер", accent=YEL, size=34), COLX[3] + 150, ROWY[1], vo("v5a", 2.65), T_SAP - 0.05),
    Box(B2_SAPHO, BLU, T_SAP, 40.85),
    Sprite(chip("Сапфо ×1", accent=BLU, size=36), COLX[4], ROWY[3] + 96, T_SAP + 0.25, 40.85),
]
sG.spots += [
    Spot([B2_LEFT], vo("v5a", 0.70), vo("v5a", 1.10), 0.4),
    Spot([B2_LAVA], vo("v5a", 1.05), vo("v5a", 2.45), 0.45),
    Spot([B2_LAVA, B2_HEAL], vo("v5a", 2.45), T_SAP, 0.45),
    Spot([B2_SAPHO], T_SAP, 40.85, 0.55),
]

# ---------------------------------------------------------------------
# H. Kitten knight vs. the crowd
# ---------------------------------------------------------------------
M03 = Clip(SRC + "/M03_cat.mp4", 2.20)
bgH = blur_bg(apply_cam(S2, GRID))
LBL_S = chip("САПФО", accent=BLU, size=44, weight="InterDisplay-Black")
LBL_L = chip("ЛАВАЧУРЛ", accent=RED, size=44, weight="InterDisplay-Black")


def kitten_labels(cv, lt, box):
    x0, y0, mw, mh = box
    src = 2.20 + lt
    a1 = min(clamp01((src - 2.32) / 0.2), clamp01((3.40 - src) / 0.15))
    if a1 > 0:
        paste(cv, LBL_S, x0 + mw * 0.68, y0 + mh * 0.50 + 10 * (1 - e_out(clamp01((src - 2.32) / 0.25))), a1)
    a2 = clamp01((src - 4.78) / 0.2)
    if a2 > 0:
        paste(cv, LBL_L, x0 + mw * 0.30, y0 + mh * 0.10 + 10 * (1 - e_out(a2)), a2)
        paste(cv, LBL_S, x0 + mw * 0.62, y0 + mh * 0.60 + 10 * (1 - e_out(a2)), a2)


add(Shot(40.85, 43.95, screen=meme_card_screen(bgH, M03, 40.85, kitten_labels)))

# ---------------------------------------------------------------------
# I. Archers counter her; her chance (S2 grid)
# ---------------------------------------------------------------------
T_ARCH = vo("v5b", 4.72)
QMARK = chip("?", accent=YEL, size=76, weight="InterDisplay-Black", fg=YEL, pad_x=34)
sI = add(Shot(43.95, 50.90, Cam(GRID), world=lambda g: S2))
sI.els += [
    Box(B2_SAPHO, BLU, 43.95, 50.90, ),
]
for r in B2_ARCH:
    sI.els.append(Box(r, RED, T_ARCH, T_WAVE - 0.05))
sI.els += [
    Arrow((COLX[2] + 60, ROWY[1] + 20), (COLX[4] - 64, ROWY[3] - 30), -40, RED, T_ARCH + 0.2, T_WAVE - 0.05),
    Arrow((COLX[2] + 60, ROWY[4] - 10), (COLX[4] - 64, ROWY[3] + 30), 40, RED, T_ARCH + 0.35, T_WAVE - 0.05),
    Sprite(relation_chip("Отряд", T_SQUAD, "Одиночная цель", T_SINGLE, size=40), 960, 988, T_ARCH + 0.1,
           T_WAVE - 0.05, anchor="s"),
    Wave((COLX[4] - 40, ROWY[3]), T_WAVE, 50.90),
    Sprite(chip("возможный сценарий", accent=BLU, size=36), 960, 988, T_WAVE + 0.15, 50.90, anchor="s"),
    Sprite(QMARK, COLX[2] + 40, ROWY[3] - 30, T_Q, 50.90, intro="pop", fin=0.3),
]
sI.spots += [
    Spot([B2_SAPHO] + B2_ARCH, T_ARCH, T_WAVE, 0.45),
    Spot([union(B2_LEFT, B2_SAPHO)], T_WAVE, 50.90, 0.35),
]

# ---------------------------------------------------------------------
# J. Bet on Sapho (S2 right panel)
# ---------------------------------------------------------------------
sJ = add(Shot(50.90, 53.45, Cam(GRID, [(50.90, 0.7, RIGHT2)]), world=lambda g: S2))
sJ.els += [
    Box(B2_SAPHO, BLU, 50.95, 53.45),
    Box(R_MUL_R2, BLU, vo("v6a", 0.20), 53.45),
    Sprite(chip("моя ставка: 50", accent=BLU, size=38), COLX[4], ROWY[3] + 100, vo("v6a", 1.45), 53.45),
]
sJ.spots += [Spot([R_MUL_R2, B2_SAPHO], 51.0, 53.45, 0.45)]

# ---------------------------------------------------------------------
# K. Hangover math
# ---------------------------------------------------------------------
M01 = Clip(SRC + "/M01_math.mp4", 1.00, crop=(0, 64, 1280, 594))
bgK = blur_bg(apply_cam(S2, RIGHT2))
add(Shot(53.45, 55.75, screen=meme_card_screen(bgK, M01, 53.45)))

# ---------------------------------------------------------------------
# L. The math card
# ---------------------------------------------------------------------
T_WIN = vo("v6b", 2.51)
T_10K = vo("v6b", 3.24)
T_LOSE = vo("v6b", 4.69)
T_500 = vo("v6b", 5.41)
T_KEF = vo("v6b", 6.31)
T_NOEST = vo("v6b", 9.26)
bgL = blur_bg(apply_cam(S2, RIGHT2), dark=0.36)


def fmt(n):
    return f"{n:,}".replace(",", " ")


def math_screen(g):
    cv = bgL.convert("RGBA").copy()
    lt = g - 55.75
    pw, ph = 1300, 640
    a0 = e_out(lt / 0.3)
    panel = ss_round_rect(pw, ph, 30, fill=rgba(INK, 236), outline=(255, 255, 255, 40), width=2)
    d = ImageDraw.Draw(panel)
    fh = font("Inter-Bold", 36)
    d.text((64, 48), "СТАВКА НА САПФО", font=fh, fill=rgba(BLU))
    d.text((64 + fh.getlength("СТАВКА НА САПФО") + 18, 48), "· 50 эмблем", font=fh, fill=rgba(MUTED))
    d.line([(64, 116), (pw - 64, 116)], fill=(255, 255, 255, 34), width=2)
    fl = font("Inter-SemiBold", 40)
    ff = font("InterDisplay-Bold", 78)
    fr = font("InterDisplay-Black", 78)
    rows = [(T_WIN, T_10K, "Победа", GREEN, "50 × 200 = ", 10000, 172),
            (T_LOSE, T_500, "Поражение", LOSS, "50 × 10 = ", 500, 300)]
    for (ta, tb, lab, col, form, res, y) in rows:
        a = e_out((g - ta) / 0.25)
        if a <= 0:
            continue
        row = Image.new("RGBA", (pw, 120), (0, 0, 0, 0))
        rd = ImageDraw.Draw(row)
        rd.text((64, 34), lab, font=fl, fill=rgba(col))
        rd.text((380, 10), form, font=ff, fill=rgba(WHITE))
        if g >= tb:
            k = e_out((g - tb) / 0.55)
            val = int(round(res * k / (10 if res > 1000 else 1))) * (10 if res > 1000 else 1)
            rd.text((380 + ff.getlength(form), 10), fmt(val), font=fr, fill=rgba(col))
        row = with_alpha(row, a)
        panel.alpha_composite(row, dest=(0, int(y + 14 * (1 - a))))
    # verdict
    a = e_out((g - T_KEF) / 0.3)
    if a > 0:
        row = Image.new("RGBA", (pw, 200), (0, 0, 0, 0))
        rd = ImageDraw.Draw(row)
        rd.line([(64, 6), (pw - 64, 6)], fill=(255, 255, 255, 34), width=2)
        f1 = font("Inter-Bold", 46)
        rd.text((64, 40), "Реальный шанс Сапфо:", font=f1, fill=rgba(WHITE))
        x = 64 + f1.getlength("Реальный шанс Сапфо:  ")
        b = e_out((g - T_NOEST) / 0.3)
        if b > 0:
            rd.text((x, 40), "неизвестен", font=f1, fill=rgba(YEL, 255 * b))
        else:
            rd.text((x, 40), "?", font=f1, fill=rgba(YEL))
        f2 = font("Inter-Medium", 32)
        rd.text((64, 118), "14% — это доля эмблем, а не вероятность победы", font=f2, fill=rgba(MUTED))
        row = with_alpha(row, a)
        panel.alpha_composite(row, dest=(0, 430 + int(12 * (1 - a))))
    fn = font("Inter-Regular", 24)
    d.text((pw - 64 - fn.getlength("множители — на момент записи"), ph - 50), "множители — на момент записи",
           font=fn, fill=rgba(MUTED, 170))
    sp = shadowed(panel, blur=26, dy=10, alpha=0.6)
    paste(cv, sp, W / 2, H / 2 + 10 * (1 - a0), a0, 0.97 + 0.03 * a0)
    return cv


add(Shot(55.75, 64.60, screen=math_screen))

# ---------------------------------------------------------------------
# M. Vislava: "о точности модели можно не беспокоиться"
# ---------------------------------------------------------------------
V1 = Clip(f"{WORK}/V1_cfr.mp4", 3.0)
sM = add(Shot(64.60, 67.95, Cam(FULL), world=lambda g: V1.at(g - 64.60)))
sM.els += [Underline(VIS_LINE, YEL, 64.60 + 1.75, 67.95)]

# ---------------------------------------------------------------------
# N. Two forecasts (V3 overview)
# ---------------------------------------------------------------------
V3n = Clip(f"{WORK}/V3_cfr.mp4", 59.1, speed=0.56, src_end=65.2)
T_RISK = vo("v7", 0.05)
T_BOTH = vo("v7", 2.26)
T_CALM = vo("v7", 5.73)
sN = add(Shot(67.95, 78.90, Cam(OVERVIEW), world=lambda g: V3n.at(g - 67.95)))
sN.els += [
    Box(OV_B1L, RED, T_RISK, 78.90, dim_after=(T_CALM, 0.30)),
    Box(OV_B2R, BLU, T_RISK + 0.12, 78.90, dim_after=(T_CALM, 0.30)),
    Sprite(caption([[("МОЙ РИСК:  ", YEL, "InterDisplay-Black"), ("слева ×105  +  Сапфо ×200", WHITE, "Inter-Bold")]],
                   size=46, accent=YEL), 960, 990, T_RISK + 0.1, T_BOTH, anchor="s"),
    Sprite(caption([[("Оба мимо:  ", LOSS, "InterDisplay-Black"), ("500 + 500 = 1 000 очков", WHITE, "Inter-Bold")]],
                   size=46, accent=LOSS), 960, 990, T_BOTH, T_CALM - 0.05, anchor="s"),
    Box(OV_B1R, YEL, T_CALM + 0.1, 78.90),
    Box(OV_B2L, YEL, T_CALM + 0.22, 78.90),
    Sprite(caption([[("ПОСПОКОЙНЕЕ:  ", GREEN, "InterDisplay-Black"), ("грибы ×30  +  лавачурл ×25", WHITE, "Inter-Bold")]],
                   size=46, accent=GREEN), 960, 990, T_CALM, 78.90, anchor="s"),
    Sprite(chip("прогноз, без гарантии", size=30, weight="Inter-Medium", fg=MUTED), 1700, 1000, vo("v7", 7.4),
           78.90, anchor="s"),
]
sN.spots += [Spot([OV_B1L, OV_B2R], T_RISK, T_CALM, 0.42),
             Spot([OV_B1L, OV_B2R, OV_B1R, OV_B2L], T_CALM, 78.90, 0.30)]

# ---------------------------------------------------------------------
# O. Check odds & timer
# ---------------------------------------------------------------------
V3o = Clip(f"{WORK}/V3_cfr.mp4", 41.15, speed=0.62, src_end=43.70)
T_KEFY = vo("v8a", 1.40)
T_TIMER = vo("v8a", 1.85)
T_GOSP = vo("v8a", 2.50)
sO = add(Shot(78.90, 83.30, Cam(FULL), world=lambda g: V3o.at(g - 78.90)))
sO.els += [
    Box(R_MUL_L, YEL, T_KEFY, T_GOSP),
    Box(R_MUL_R, YEL, T_KEFY + 0.1, T_GOSP),
    Box(R_TIMER, YEL, T_TIMER, T_GOSP),
    Sprite(chip("у тебя будет другое время", accent=YEL, size=34), 1205, 368, T_TIMER + 0.2, T_GOSP),
    Sprite(lower_third("ГОСПОДИН", "прогноз выдан  ✓"), 480, 900, T_GOSP, 83.30, anchor="s", intro="rise",
           fin=0.3, fout=0.01),
]
sO.spots += [Spot([R_MUL_L, R_MUL_R], T_KEFY, T_TIMER, 0.45), Spot([R_MUL_L, R_MUL_R, R_TIMER], T_TIMER, T_GOSP, 0.45)]

# ---------------------------------------------------------------------
# P. The pot
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
    # floor shadow under the pot
    sh = np.exp(-(((xx - 960) / 560) ** 2 + ((yy - 1046) / 46) ** 2))
    img *= (1 - 0.65 * sh[..., None])
    rng = np.random.default_rng(1)
    img += rng.normal(0, 1.3, img.shape)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")


POT_BG = make_pot_bg()
# visibility mask for falling cards: outside the pot silhouette OR inside the rim opening
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
    m = ss_round_rect(size[0], size[1], 14, fill=(255, 255, 255, 255)).getchannel("A")
    c.putalpha(m)
    return c


ov = still("V3", 6.0)
gr = still("V3", 10.0)
CARD_SOUP = crop_card(ov, (902, 294, 1039, 426), (170, 164))
hat_small = chef_hat(118)
cs = Image.new("RGBA", (190, 250), (0, 0, 0, 0))
cs.alpha_composite(CARD_SOUP, dest=(10, 76))
cs.alpha_composite(hat_small.rotate(-12, resample=Image.BICUBIC, expand=True), dest=(28, 0))
CARD_SOUP = cs
CARD_CICIN = crop_card(gr, (948, 334, 1056, 426), (176, 150))
CARD_SAPHO = crop_card(ov, (1746, 662, 1884, 798), (166, 164))
DROPS = [(CARD_SOUP, DROP_T[0], -170, -18, 10), (CARD_CICIN, DROP_T[1], 160, 16, -8),
         (CARD_SAPHO, DROP_T[2], -10, -10, 6)]
CARD_SC = 1.25
T_TITLE = vo("v8b", 6.45)


def pot_screen(g):
    cv = POT_BG.copy()
    lt = g - T_POT
    # subtle slow push-in
    cv.alpha_composite(POT, dest=POT_XY)
    for k, (amp, sp_, ph, al) in enumerate([(9, 1.1, 0.0, 0.40), (12, 0.8, 2.0, 0.28)]):
        ph_t = (lt * 0.22 + k * 0.5) % 1.0
        st = with_alpha(STEAM, al * math.sin(math.pi * ph_t))
        cv.alpha_composite(st, dest=(int(POT_XY[0] + amp * math.sin(lt * sp_ + ph)), int(POT_XY[1] - 70 * ph_t)))
    # cards
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
        if tt < 0.35:                      # slide in from above, decelerating
            k = e_out(tt / 0.35)
            x, y, r = hx, -260 + (hang_y + 260) * k, rot0 * (1 - k) + rot0 * 0.4 * k
            a = 1.0
        elif tt < 0.70:                    # hang: readable, tiny wobble
            u = tt - 0.35
            x, y, r = hx, hang_y + 6 * math.sin(u * 18), rot0 * 0.4 * math.cos(u * 12)
            a = 1.0
        elif tt < FALL:                    # drop into the soup
            k = e_in((tt - 0.70) / (FALL - 0.70))
            x = hx + (tx - hx) * k
            y = hang_y + (yt - hang_y) * k
            r = rot0 * 0.4 + (rot1 - rot0 * 0.4) * k
            a = 1.0
        else:                              # sink
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
    # splashes: ripples + droplets
    sl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sl)
    for (sx, sy, s) in splash:
        if s < 0.7:
            k = e_out(s / 0.7)
            rx, ry = 40 + 230 * k, 10 + 46 * k
            sd.ellipse([sx - rx, sy - ry, sx + rx, sy + ry], outline=(255, 214, 150, int(150 * (1 - k))), width=4)
        rng = random.Random(int(sx))
        for i in range(12):
            vx = rng.uniform(-260, 260)
            vy = rng.uniform(-620, -320)
            px, py = sx + vx * s, sy + vy * s + 0.5 * 1800 * s * s
            if s < 0.75 and py < sy + 10:
                rr = rng.uniform(5, 10) * (1 - s)
                sd.ellipse([px - rr, py - rr, px + rr, py + rr], fill=(214, 150, 70, int(230 * (1 - s / 0.75))))
    cv.alpha_composite(sl)
    # final bulk bubble
    if g > T_BULK - 0.35:
        s = g - (T_BULK - 0.35)
        bx, by = RIM_C[0] + 60, SOUP_Y
        if s < 0.35:
            r = 20 + 60 * e_out(s / 0.35)
            bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            bd = ImageDraw.Draw(bl)
            bd.ellipse([bx - r, by - r * 0.75, bx + r, by + r * 0.35], fill=(220, 160, 80, 230),
                       outline=(255, 230, 180, 255), width=3)
            bd.ellipse([bx - r * 0.45, by - r * 0.55, bx - r * 0.1, by - r * 0.3], fill=(255, 245, 220, 200))
            cv.alpha_composite(bl)
        elif s < 0.95:
            k = e_out((s - 0.35) / 0.6)
            bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            bd = ImageDraw.Draw(bl)
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
    # title
    a = e_out((g - T_TITLE) / 0.35)
    if a > 0:
        paste(cv, POT_TITLE, 960, 170 + 12 * (1 - a), a, 0.96 + 0.04 * e_back(clamp01((g - T_TITLE) / 0.35)))
    # vignette fade at the very end
    if g > END - 0.30:
        k = clamp01((g - (END - 0.30)) / 0.05)
        cv = Image.blend(cv, Image.new("RGBA", (W, H), (0, 0, 0, 255)), k)
    return cv


def make_title():
    f1 = font("Inter-SemiBold", 46)
    f2 = font("InterDisplay-Black", 132)
    t1 = "С  У  П"
    t2 = "«СЕМЕЙНЫЙ»"
    w2 = f2.getlength(t2)
    w = int(w2 + 80)
    h = 250
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text(((w - f1.getlength(t1)) / 2, 6), t1, font=f1, fill=rgba(GOLD))
    d.text(((w - w2) / 2, 62), t2, font=f2, fill=(70, 34, 16, 255), stroke_width=4, stroke_fill=(70, 34, 16, 255))
    d.text(((w - w2) / 2, 56), t2, font=f2, fill=(255, 240, 214, 255))
    return shadowed(im, blur=18, dy=8, alpha=0.65)


POT_TITLE = make_title()
add(Shot(T_POT, END, screen=pot_screen))


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
                                "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                                "-pix_fmt", "yuv420p", "-tune", "film", out], stdin=subprocess.PIPE)
        for n in range(n0, n1):
            g = n / FPS
            enc.stdin.write(frame_at(g).tobytes())
            if n % 60 == 0:
                print(f"{out}: {g:.1f}s", flush=True)
        enc.stdin.close()
        enc.wait()
        print("done", out)
