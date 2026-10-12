"""v3 graphics: the plain YouTube-edit look.
Red marker circles/arrows/underlines, Montserrat Black / Oswald text with a hard black stroke,
full-screen meme cuts, chroma key, blurred fill for vertical clips. No glows, no rounded dark panels."""
import math, random, os
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1920, 1080
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts", "ttf")
RED = (232, 22, 22)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
YELLOW = (255, 221, 0)
T_SINGLE = (196, 132, 255)
T_AREA = (255, 196, 40)
T_RANGED = (110, 180, 255)
T_FLY = (90, 235, 160)


@lru_cache(maxsize=32)
def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name + ".ttf"), size)


MONT = "Montserrat_900Black"
MONT_I = "Montserrat_900Black_Italic"
OSW = "Oswald_700Bold"


def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def e_out(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3


def e_in(t):
    t = clamp01(t)
    return t ** 3


def e_inout(t):
    t = clamp01(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def with_alpha(img, a):
    if a >= 0.999:
        return img
    im = img.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    return im


def paste(canvas, sprite, cx, cy, alpha=1.0, scale=1.0, rot=0.0):
    if alpha <= 0.003 or sprite is None:
        return
    sp = sprite
    if abs(scale - 1) > 1e-3:
        sp = sp.resize((max(1, int(round(sp.width * scale))), max(1, int(round(sp.height * scale)))), Image.BICUBIC)
    if abs(rot) > 1e-3:
        sp = sp.rotate(rot, resample=Image.BICUBIC, expand=True)
    sp = with_alpha(sp, alpha)
    x = int(round(cx - sp.width / 2)); y = int(round(cy - sp.height / 2))
    if x >= canvas.width or y >= canvas.height or x + sp.width <= 0 or y + sp.height <= 0:
        return
    canvas.alpha_composite(sp, dest=(max(0, x), max(0, y)), source=(max(0, -x), max(0, -y)))


# ---------------- text: white + fat black stroke + hard shadow ----------------
_tcache = {}


def stroke_text(parts, size, fname=MONT, stroke=None, shadow=True, upper=False):
    """parts: str or list of (text, colour). Returns RGBA sprite."""
    if isinstance(parts, str):
        parts = [(parts, WHITE)]
    if upper:
        parts = [(t.upper(), c) for t, c in parts]
    key = (tuple(parts), size, fname, stroke, shadow)
    if key in _tcache:
        return _tcache[key]
    f = font(fname, size)
    sw = stroke if stroke is not None else max(3, int(size * 0.13))
    widths = [f.getlength(t) for t, _ in parts]
    tw = sum(widths)
    asc, desc = f.getmetrics()
    pad = sw + int(size * 0.12)
    w, h = int(tw + 2 * pad), int(asc + desc + 2 * pad)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        x = pad
        off = max(2, int(size * 0.06))
        for (t, c), wd in zip(parts, widths):
            sd.text((x + off, pad + off), t, font=f, fill=(0, 0, 0, 150), stroke_width=sw, stroke_fill=(0, 0, 0, 150))
            x += wd
        im.alpha_composite(sh)
    x = pad
    for (t, c), wd in zip(parts, widths):
        d.text((x, pad), t, font=f, fill=c + (255,), stroke_width=sw, stroke_fill=BLACK + (255,))
        x += wd
    _tcache[key] = im
    return im


def pop_scale(p):
    """snappy text pop: 1.28 -> 1.0 in ~0.1 s (p is 0..1 over that window)."""
    p = clamp01(p)
    return 1.0 + 0.28 * (1 - e_out(p))


# ---------------- red marker shapes ----------------
def _marker_draw(canvas, pts, color, width, alpha=1.0):
    if len(pts) < 2 or alpha <= 0.003:
        return
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    pad = width * 2 + 6
    bx0, by0 = int(min(xs) - pad), int(min(ys) - pad)
    bw, bh = int(max(xs) - min(xs) + 2 * pad), int(max(ys) - min(ys) + 2 * pad)
    ss = 3
    big = Image.new("RGBA", (bw * ss, bh * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    sp = [((x - bx0) * ss, (y - by0) * ss) for x, y in pts]
    # soft dark edge so red reads on red UI
    d.line([(x + 2 * ss, y + 2 * ss) for x, y in sp], fill=(0, 0, 0, 90), width=width * ss, joint="curve")
    d.line(sp, fill=color + (255,), width=width * ss, joint="curve")
    r = width * ss / 2
    for (x, y) in (sp[0], sp[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=color + (255,))
    big = big.resize((bw, bh), Image.LANCZOS)
    if alpha < 1:
        big = with_alpha(big, alpha)
    canvas.alpha_composite(big, dest=(max(0, bx0), max(0, by0)), source=(max(0, -bx0), max(0, -by0)))


def marker_ellipse(canvas, rect, prog, seed, color=RED, width=9, pad=14, alpha=1.0):
    """Hand-drawn circle around rect (screen coords), drawn on with prog 0..1."""
    if prog <= 0:
        return
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2 * 1.10 + pad, (y1 - y0) / 2 * 1.16 + pad
    rnd = random.Random(seed)
    start = rnd.uniform(-2.4, -1.6)
    total = 2 * math.pi + rnd.uniform(0.45, 0.75)
    tilt = rnd.uniform(-0.07, 0.07)
    ph1, ph2 = rnd.uniform(0, 6.28), rnd.uniform(0, 6.28)
    n = 110
    pts = []
    m = max(2, int(n * clamp01(prog)))
    for i in range(m + 1):
        t = i / n
        a = start + total * t
        r = 1 + 0.035 * math.sin(2 * a + ph1) + 0.02 * math.sin(3 * a + ph2) + 0.05 * t
        ex, ey = rx * r * math.cos(a), ry * r * math.sin(a)
        pts.append((cx + ex * math.cos(tilt) - ey * math.sin(tilt), cy + ex * math.sin(tilt) + ey * math.cos(tilt)))
    _marker_draw(canvas, pts, color, width, alpha)


def marker_arrow(canvas, p0, p1, prog, seed, color=RED, width=9, bend=0.12, alpha=1.0):
    if prog <= 0:
        return
    rnd = random.Random(seed)
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    b = bend * L * (1 if rnd.random() > 0.5 else -1)
    n = 40
    k_line = clamp01(prog / 0.75)
    pts = []
    for i in range(int(n * k_line) + 1):
        t = i / n
        wob = math.sin(t * math.pi) * b + math.sin(t * 9 + seed) * 2.0
        pts.append((x0 + dx * t + nx * wob, y0 + dy * t + ny * wob))
    _marker_draw(canvas, pts, color, width, alpha)
    if prog > 0.75 and len(pts) > 3:
        k = clamp01((prog - 0.75) / 0.25)
        ex, ey = pts[-1]
        px, py = pts[-4]
        ang = math.atan2(ey - py, ex - px)
        hl = 34 * k
        for s in (-1, 1):
            a2 = ang + math.pi + s * 0.55
            _marker_draw(canvas, [(ex, ey), (ex + math.cos(a2) * hl, ey + math.sin(a2) * hl)], color, width, alpha)


def marker_underline(canvas, x0, x1, y, prog, seed, color=RED, width=8, alpha=1.0):
    if prog <= 0:
        return
    rnd = random.Random(seed)
    n = 30
    pts = []
    xe = x0 + (x1 - x0) * clamp01(prog)
    for i in range(n + 1):
        t = i / n
        x = x0 + (xe - x0) * t
        pts.append((x, y + math.sin(t * 3.1 + rnd.uniform(0, 1)) * 3 + (x - x0) * 0.008))
    _marker_draw(canvas, pts, color, width, alpha)


# ---------------- bookmaker banner ----------------
def natlanbet_banner():
    f = font(MONT_I, 118)
    t = "НАТЛАНБЕТ"
    tw = f.getlength(t)
    w, h = int(tw + 150), 190
    im = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    sk = 38
    poly = [(20 + sk, 20), (20 + w, 20), (20 + w - sk, 20 + h), (20, 20 + h)]
    d.polygon([(x + 8, y + 9) for x, y in poly], fill=(0, 0, 0, 140))
    d.polygon(poly, fill=(214, 18, 32, 255))
    d.polygon([(20 + sk * 0.16, 20 + h - 22), (20 + w - sk * 0.86, 20 + h - 22), (20 + w - sk, 20 + h), (20, 20 + h)],
              fill=YELLOW + (255,))
    d.text((20 + (w - tw) / 2 + 6, 22), t, font=f, fill=WHITE + (255,), stroke_width=7, stroke_fill=BLACK + (255,))
    return im


# ---------------- chef hat sticker ----------------
def chef_hat(width=150):
    ss = 3
    w, h = width, int(width * 0.92)
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    S = lambda v: int(v * ss)
    puff = [(0.30, 0.36, 0.22), (0.52, 0.27, 0.25), (0.73, 0.37, 0.21), (0.42, 0.48, 0.22), (0.62, 0.49, 0.22)]
    for o, col in ((7, (0, 0, 0, 255)), (0, (255, 255, 255, 255))):
        for (px, py, pr) in puff:
            d.ellipse([S(w * (px - pr)) - S(o), S(h * py - w * pr) - S(o), S(w * (px + pr)) + S(o), S(h * py + w * pr) + S(o)], fill=col)
        d.rounded_rectangle([S(w * 0.18) - S(o), S(h * 0.58) - S(o), S(w * 0.82) + S(o), S(h * 0.92) + S(o)], radius=S(8 + o), fill=col)
    for k in range(3):
        x = w * (0.33 + 0.17 * k)
        d.line([S(x), S(h * 0.62), S(x), S(h * 0.88)], fill=(170, 170, 180, 255), width=S(3))
    return big.resize((w, h), Image.LANCZOS)


# ---------------- clip helpers ----------------
def cover(img, size=(W, H), focus=(0.5, 0.5)):
    sw, sh = img.size
    k = max(size[0] / sw, size[1] / sh)
    nw, nh = int(math.ceil(sw * k)), int(math.ceil(sh * k))
    im = img.resize((nw, nh), Image.LANCZOS)
    x = int(min(max(focus[0] * nw - size[0] / 2, 0), nw - size[0]))
    y = int(min(max(focus[1] * nh - size[1] / 2, 0), nh - size[1]))
    return im.crop((x, y, x + size[0], y + size[1]))


def fit_blur_fill(img, size=(W, H), dark=0.55, fill=None):
    """Vertical/odd clip: blurred cover background + fitted foreground (CapCut-style)."""
    if fill is not None:
        bg = Image.new("RGB", size, fill)
    else:
        bg = cover(img.convert("RGB"), (size[0] // 4, size[1] // 4)).filter(ImageFilter.GaussianBlur(6))
        bg = bg.resize(size, Image.BILINEAR)
        bg = Image.fromarray((np.asarray(bg).astype(np.float32) * dark).astype(np.uint8))
    sw, sh = img.size
    k = min(size[0] / sw, size[1] / sh)
    fg = img.resize((int(sw * k), int(sh * k)), Image.LANCZOS)
    bg.paste(fg, ((size[0] - fg.width) // 2, (size[1] - fg.height) // 2))
    return bg


def chroma(img, lo=40, hi=95):
    """Key out green. Returns RGBA."""
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    gr = g - np.maximum(r, b)
    alpha = 1 - np.clip((gr - lo) / (hi - lo), 0, 1)
    g2 = np.minimum(g, np.maximum(r, b) + 8)  # despill
    out = np.dstack([r, np.where(gr > lo * 0.5, g2, g), b, (alpha * 255)]).clip(0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")
