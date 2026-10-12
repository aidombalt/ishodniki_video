"""Graphics primitives for the Gospodin montage: one consistent visual language."""
import math, random
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1920, 1080
FONT_DIR = "/usr/share/fonts/opentype/inter/"

# ---------- palette ----------
YEL = (255, 208, 64)
RED = (255, 86, 86)
BLU = (70, 192, 255)
INK = (13, 15, 26)
WHITE = (248, 248, 250)
MUTED = (182, 189, 206)
GREEN = (98, 226, 150)
LOSS = (255, 128, 112)
GOLD = (255, 214, 102)

# suppression type colours (match the in-game corner icons)
T_SQUAD = (96, 206, 120)
T_AREA = (245, 176, 52)
T_SINGLE = (178, 120, 240)
T_FLY = (64, 206, 160)
T_RANGED = (84, 150, 240)


@lru_cache(maxsize=64)
def font(name, size):
    return ImageFont.truetype(FONT_DIR + name + ".otf", size)


# ---------- easing ----------
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


def e_back(t, s=1.55):
    t = clamp01(t)
    c3 = s + 1
    return 1 + c3 * (t - 1) ** 3 + s * (t - 1) ** 2


def life(g, t0, t1, fin=0.22, fout=0.18):
    """alpha envelope + intro progress for an element living in [t0, t1]."""
    if g < t0 or g > t1:
        return 0.0, 0.0
    a_in = clamp01((g - t0) / fin) if fin > 0 else 1.0
    a_out = clamp01((t1 - g) / fout) if fout > 0 else 1.0
    return min(e_out(a_in), e_out(a_out)), a_in


# ---------- low level ----------
def rgba(c, a=255):
    return (c[0], c[1], c[2], int(a))


def with_alpha(img, a):
    if a >= 0.999:
        return img
    im = img.copy()
    al = im.getchannel("A").point(lambda v: int(v * a))
    im.putalpha(al)
    return im


def paste(canvas, sprite, cx, cy, alpha=1.0, scale=1.0, rot=0.0):
    """Composite sprite centred at (cx, cy) on an RGBA canvas."""
    if alpha <= 0.003 or sprite is None:
        return
    sp = sprite
    if abs(scale - 1) > 1e-3:
        w = max(1, int(round(sp.width * scale)))
        h = max(1, int(round(sp.height * scale)))
        sp = sp.resize((w, h), Image.BICUBIC)
    if abs(rot) > 1e-3:
        sp = sp.rotate(rot, resample=Image.BICUBIC, expand=True)
    sp = with_alpha(sp, alpha)
    x = int(round(cx - sp.width / 2))
    y = int(round(cy - sp.height / 2))
    if x >= canvas.width or y >= canvas.height or x + sp.width <= 0 or y + sp.height <= 0:
        return
    canvas.alpha_composite(sp, dest=(max(0, x), max(0, y)),
                           source=(max(0, -x), max(0, -y)))


def ss_round_rect(w, h, r, fill=None, outline=None, width=0, ss=3):
    """Anti-aliased rounded rectangle via supersampling."""
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([0, 0, w * ss - 1, h * ss - 1], radius=r * ss,
                        fill=fill, outline=outline, width=width * ss)
    return big.resize((w, h), Image.LANCZOS)


def shadowed(sprite, blur=14, dy=6, alpha=0.55, pad=None):
    pad = pad if pad is not None else blur * 2 + abs(dy)
    w, h = sprite.size
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    al = sprite.getchannel("A").point(lambda v: int(v * alpha))
    blk = Image.new("RGBA", sprite.size, (0, 0, 0, 255))
    blk.putalpha(al)
    sh.alpha_composite(blk, dest=(pad, pad + dy))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(sh)
    out.alpha_composite(sprite, dest=(pad, pad))
    return out


def text_size(txt, f):
    b = f.getbbox(txt)
    return b[2] - b[0], b[3] - b[1], b


# ---------- highlight box (attached to UI) ----------
_box_cache = {}


def box_sprite(w, h, color, stroke=5, r=14, glow=True):
    key = (int(w) // 2 * 2, int(h) // 2 * 2, color, stroke, r, glow)
    if key in _box_cache:
        return _box_cache[key]
    w, h = key[0], key[1]
    pad = 26
    big = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ring = ss_round_rect(w, h, r, outline=rgba(color), width=stroke)
    if glow:
        g = Image.new("RGBA", big.size, (0, 0, 0, 0))
        gl = ss_round_rect(w, h, r, outline=rgba(color, 255), width=stroke + 4)
        g.alpha_composite(gl, dest=(pad, pad))
        g = g.filter(ImageFilter.GaussianBlur(9))
        g = with_alpha(g, 0.85)
        big.alpha_composite(g)
    # thin dark outer line for contrast on bright UI
    dark = ss_round_rect(w + 4, h + 4, r + 2, outline=(0, 0, 0, 110), width=2)
    big.alpha_composite(dark, dest=(pad - 2, pad - 2))
    big.alpha_composite(ring, dest=(pad, pad))
    if len(_box_cache) > 400:
        _box_cache.clear()
    _box_cache[key] = big
    return big


def draw_box(canvas, rect, color, alpha, prog, stroke=5, r=14):
    x0, y0, x1, y1 = rect
    if alpha <= 0.003:
        return
    sc = 1.0 + 0.10 * (1 - e_back(prog)) if prog < 1 else 1.0
    sp = box_sprite(x1 - x0, y1 - y0, color, stroke, r)
    paste(canvas, sp, (x0 + x1) / 2, (y0 + y1) / 2, alpha, sc)


# ---------- spotlight dim ----------
def spotlight(frame_rgb, holes, amount, feather=18):
    """Darken everything except rounded holes (screen rects). frame: HxWx3 uint8 ndarray."""
    if amount <= 0.003:
        return frame_rgb
    q = 4
    m = Image.new("L", (W // q, H // q), 255)
    d = ImageDraw.Draw(m)
    for (x0, y0, x1, y1) in holes:
        d.rounded_rectangle([x0 / q - 3, y0 / q - 3, x1 / q + 3, y1 / q + 3], radius=6, fill=0)
    m = m.filter(ImageFilter.GaussianBlur(feather / q))
    m = m.resize((W, H), Image.BILINEAR)
    mk = np.asarray(m, dtype=np.float32) * (amount / 255.0)
    out = frame_rgb.astype(np.float32) * (1 - mk[..., None])
    return out.astype(np.uint8)


# ---------- chips / captions ----------
_chip_cache = {}


def chip(text, accent=None, size=36, weight="Inter-SemiBold", fg=WHITE, dot=None,
         bg_alpha=0.9, pad_x=24, h=None, border=True):
    key = ("chip", text, accent, size, weight, fg, dot, bg_alpha, pad_x, h, border)
    if key in _chip_cache:
        return _chip_cache[key]
    f = font(weight, size)
    tw, th, bb = text_size(text, f)
    hh = h or int(size * 1.62)
    dot_w = int(size * 0.62) if dot else 0
    w = tw + 2 * pad_x + dot_w
    base = ss_round_rect(w, hh, hh // 2, fill=rgba(INK, 255 * bg_alpha),
                         outline=rgba(accent, 235) if (accent and border) else (255, 255, 255, 40),
                         width=2)
    d = ImageDraw.Draw(base)
    x = pad_x
    if dot:
        r = size * 0.22
        cy = hh / 2
        dd = ss_round_rect(int(2 * r), int(2 * r), int(r), fill=rgba(dot))
        base.alpha_composite(dd, dest=(int(x), int(cy - r)))
        x += dot_w
    ty = (hh - (bb[3] + bb[1])) / 2
    d.text((x - bb[0], ty), text, font=f, fill=rgba(fg))
    out = shadowed(base, blur=10, dy=4, alpha=0.5)
    _chip_cache[key] = out
    return out


def rich_chip(parts, size=36, pad_x=26, h=None, accent=None):
    """parts: list of (text, colour, fontname) drawn inline."""
    key = ("rich", tuple(parts), size, pad_x, h, accent)
    if key in _chip_cache:
        return _chip_cache[key]
    widths = []
    for txt, col, fn in parts:
        f = font(fn, size)
        widths.append(f.getlength(txt))
    hh = h or int(size * 1.66)
    w = int(sum(widths) + 2 * pad_x)
    base = ss_round_rect(w, hh, hh // 2, fill=rgba(INK, 232),
                         outline=rgba(accent, 235) if accent else (255, 255, 255, 46), width=2)
    d = ImageDraw.Draw(base)
    x = pad_x
    ref = font("Inter-Bold", size)
    bb = ref.getbbox("АБВЁЙgy")
    ty = (hh - (bb[3] + bb[1])) / 2
    for (txt, col, fn), wd in zip(parts, widths):
        d.text((x, ty), txt, font=font(fn, size), fill=rgba(col))
        x += wd
    out = shadowed(base, blur=10, dy=4, alpha=0.5)
    _chip_cache[key] = out
    return out


def type_pill(text, col, size=34):
    """A suppression-type pill styled like the in-game tags."""
    return chip(text, accent=col, size=size, weight="Inter-Bold", dot=col)


def relation_chip(a_txt, a_col, b_txt, b_col, size=36, lead=None):
    key = ("rel", a_txt, a_col, b_txt, b_col, size, lead)
    if key in _chip_cache:
        return _chip_cache[key]
    f = font("Inter-Bold", size)
    hh = int(size * 1.8)
    pad = 24
    dot = int(size * 0.44)
    gap = 16
    arrow = "  сильнее  "
    fa = font("Inter-Medium", int(size * 0.72))
    parts_w = (dot + 12 + f.getlength(a_txt)) + gap + fa.getlength("▶") + 2 * 18 + gap + (dot + 12 + f.getlength(b_txt))
    lead_w = 0
    if lead:
        fl = font("Inter-SemiBold", size)
        lead_w = fl.getlength(lead) + 22
    w = int(parts_w + 2 * pad + lead_w)
    base = ss_round_rect(w, hh, hh // 2, fill=rgba(INK, 236), outline=(255, 255, 255, 50), width=2)
    d = ImageDraw.Draw(base)
    bb = f.getbbox("АБВgy")
    ty = (hh - (bb[3] + bb[1])) / 2
    x = pad
    if lead:
        d.text((x, ty), lead, font=fl, fill=rgba(MUTED))
        x += lead_w
    for i, (txt, col) in enumerate([(a_txt, a_col), (b_txt, b_col)]):
        dd = ss_round_rect(dot, dot, dot // 2, fill=rgba(col))
        base.alpha_composite(dd, dest=(int(x), int(hh / 2 - dot / 2)))
        x += dot + 12
        d.text((x, ty), txt, font=f, fill=rgba(col if col != WHITE else WHITE))
        x += f.getlength(txt) + gap
        if i == 0:
            ab = fa.getbbox("▶")
            d.text((x + 18, (hh - (ab[3] + ab[1])) / 2), "▶", font=fa, fill=rgba(WHITE, 230))
            x += fa.getlength("▶") + 2 * 18 + gap
    out = shadowed(base, blur=10, dy=4, alpha=0.5)
    _chip_cache[key] = out
    return out


def caption(lines, size=50, accent=None, width=None):
    """Main statement panel (bottom centre). lines: list of str or list of parts lists."""
    key = ("cap", repr(lines), size, accent, width)
    if key in _chip_cache:
        return _chip_cache[key]
    rows = []
    for ln in lines:
        if isinstance(ln, str):
            ln = [(ln, WHITE, "Inter-Bold")]
        rows.append(ln)
    lh = int(size * 1.32)
    fsz = []
    widths = []
    for row in rows:
        wsum = 0
        for txt, col, fn in row:
            s = size if not fn.endswith("@s") else int(size * 0.72)
            wsum += font(fn.replace("@s", ""), s).getlength(txt)
        widths.append(wsum)
    padx, pady = (58 if accent else 40), 22
    w = int(width or (max(widths) + 2 * padx))
    h = int(len(rows) * lh + 2 * pady - (lh - size * 1.12))
    base = ss_round_rect(w, h, 24, fill=rgba(INK, 228), outline=(255, 255, 255, 40), width=2)
    if accent:
        bar = ss_round_rect(10, h - 28, 5, fill=rgba(accent))
        base.alpha_composite(bar, dest=(16, 14))
    d = ImageDraw.Draw(base)
    ref = font("Inter-Bold", size).getbbox("АБВЁЙ")
    for i, row in enumerate(rows):
        x = (w - widths[i]) / 2 + (8 if accent else 0)
        y = pady + i * lh - ref[1] + 2
        for txt, col, fn in row:
            s = size if not fn.endswith("@s") else int(size * 0.72)
            fo = font(fn.replace("@s", ""), s)
            yy = y + (size - s) * 0.78 if s != size else y
            d.text((x, yy), txt, font=fo, fill=rgba(col))
            x += fo.getlength(txt)
    out = shadowed(base, blur=16, dy=6, alpha=0.55)
    _chip_cache[key] = out
    return out


def chapter_tag(text):
    key = ("chap", text)
    if key in _chip_cache:
        return _chip_cache[key]
    f = font("InterDisplay-Black", 38)
    tw, th, bb = text_size(text, f)
    w, h = tw + 44, 62
    base = ss_round_rect(w, h, 14, fill=rgba(YEL))
    d = ImageDraw.Draw(base)
    d.text(((w - tw) / 2 - bb[0], (h - (bb[3] + bb[1])) / 2), text, font=f, fill=rgba(INK))
    out = shadowed(base, blur=10, dy=4, alpha=0.45)
    _chip_cache[key] = out
    return out


# ---------- lower third ----------
def lower_third(title, sub, accent=YEL):
    key = ("lt", title, sub, accent)
    if key in _chip_cache:
        return _chip_cache[key]
    ft = font("InterDisplay-Black", 66)
    fs = font("Inter-SemiBold", 32)
    tw, th, tb = text_size(title, ft)
    sw = fs.getlength(sub)
    w = int(max(tw, sw) + 92)
    h = 156
    base = ss_round_rect(w, h, 20, fill=rgba(INK, 225), outline=(255, 255, 255, 36), width=2)
    bar = ss_round_rect(12, h - 32, 6, fill=rgba(accent))
    base.alpha_composite(bar, dest=(22, 16))
    d = ImageDraw.Draw(base)
    d.text((58 - tb[0], 22 - tb[1] + 6), title, font=ft, fill=rgba(WHITE))
    d.text((60, 104), sub, font=fs, fill=rgba(MUTED))
    out = shadowed(base, blur=16, dy=6, alpha=0.55)
    _chip_cache[key] = out
    return out


# ---------- НАТЛАНБЕТ sign ----------
def natlanbet_sign(bulb_phase=0):
    rnd = random.Random(7)
    text = "НАТЛАНБЕТ"
    f = font("InterDisplay-Black", 112)
    ss = 2
    letters = []
    total = 0
    for ch in text:
        w = f.getlength(ch)
        letters.append((ch, w))
        total += w + 4
    W0 = int(total + 120)
    H0 = 214
    base = Image.new("RGBA", (W0 * ss, H0 * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle([0, 0, W0 * ss - 1, H0 * ss - 1], radius=26 * ss, fill=(122, 18, 30, 255),
                        outline=(255, 200, 90, 255), width=7 * ss)
    d.rounded_rectangle([16 * ss, 16 * ss, (W0 - 16) * ss, (H0 - 16) * ss], radius=16 * ss,
                        outline=(255, 226, 150, 150), width=2 * ss)
    base = base.resize((W0, H0), Image.LANCZOS)
    # bulbs
    bl = Image.new("RGBA", base.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(bl)
    pts = []
    step = 38
    for x in range(30, W0 - 20, step):
        pts.append((x, 9)); pts.append((x, H0 - 9))
    for y in range(9 + step, H0 - 20, step):
        pts.append((9, y)); pts.append((W0 - 9, y))
    for i, (x, y) in enumerate(pts):
        on = ((i + bulb_phase) % 3) != 0
        c = (255, 244, 190, 255) if on else (150, 110, 60, 255)
        bd.ellipse([x - 6, y - 6, x + 6, y + 6], fill=c)
    glow = bl.filter(ImageFilter.GaussianBlur(6))
    base.alpha_composite(glow)
    base.alpha_composite(bl)
    # crooked letters
    x = 60
    for ch, w in letters:
        lw = int(w + 30)
        lim = Image.new("RGBA", (lw, 170), (0, 0, 0, 0))
        ld = ImageDraw.Draw(lim)
        bb = f.getbbox(ch)
        # gradient-ish: draw dark outline then gold fill
        ld.text((15 - bb[0], 18), ch, font=f, fill=(70, 10, 10, 255), stroke_width=5, stroke_fill=(70, 10, 10, 255))
        ld.text((15 - bb[0], 12), ch, font=f, fill=(255, 222, 110, 255))
        hi = Image.new("RGBA", lim.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(hi)
        hd.text((15 - bb[0], 12), ch, font=f, fill=(255, 250, 220, 255))
        mask = Image.new("L", lim.size, 0)
        ImageDraw.Draw(mask).rectangle([0, 0, lw, 70], fill=150)
        lim.paste(hi, (0, 0), Image.composite(hi.getchannel("A"), Image.new("L", lim.size, 0), mask))
        rot = rnd.uniform(-7, 7)
        dy = rnd.uniform(-9, 9)
        lim = lim.rotate(rot, resample=Image.BICUBIC, expand=False)
        base.alpha_composite(lim, dest=(int(x - 15), int(14 + dy)))
        x += w + 4
    return shadowed(base, blur=18, dy=10, alpha=0.6)


# ---------- stamp ----------
def stamp(text, color=(232, 52, 52), size=58):
    lines = text.split("\n")
    ss = 2
    fb = font("InterDisplay-Black", size * ss)
    lw = [fb.getlength(l) / ss for l in lines]
    lh = size * 1.08
    tw = max(lw)
    th = lh * len(lines)
    w, h = int(tw + 64), int(th + 44)
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([4 * ss, 4 * ss, (w - 4) * ss, (h - 4) * ss], radius=14 * ss,
                        outline=rgba(color), width=7 * ss)
    ref = fb.getbbox("НШ")
    for i, l in enumerate(lines):
        x = (w - lw[i]) / 2 * ss
        y = (22 + i * lh) * ss - ref[1] + (lh - size * 0.74) / 2 * ss
        d.text((x, y), l, font=fb, fill=rgba(color))
    big = big.resize((w, h), Image.LANCZOS)
    # ink texture
    rng = np.random.default_rng(3)
    a = np.asarray(big.getchannel("A")).astype(np.float32)
    noise = rng.random(a.shape)
    blot = np.asarray(Image.fromarray((rng.random((h // 6 + 1, w // 6 + 1)) * 255).astype(np.uint8))
                      .resize((w, h), Image.BILINEAR)).astype(np.float32) / 255
    a = a * np.clip(0.86 + 0.2 * blot, 0, 1) * (noise > 0.025)
    big.putalpha(Image.fromarray(a.astype(np.uint8)))
    # light backing so it reads on busy UI
    back = ss_round_rect(w - 8, h - 8, 12, fill=(255, 246, 238, 200))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(back, dest=(4, 4))
    out.alpha_composite(big)
    return shadowed(out, blur=8, dy=3, alpha=0.35)


# ---------- chef hat ----------
def chef_hat(width=150):
    ss = 3
    w, h = width, int(width * 0.92)
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    S = lambda v: int(v * ss)
    outline = (150, 150, 160, 255)
    puff = [(0.30, 0.36, 0.22), (0.52, 0.27, 0.25), (0.73, 0.37, 0.21), (0.42, 0.48, 0.22), (0.62, 0.49, 0.22)]
    for (px, py, pr) in puff:
        d.ellipse([S(w * (px - pr)) - S(3), S(h * py - w * pr) - S(3), S(w * (px + pr)) + S(3), S(h * py + w * pr) + S(3)], fill=outline)
    for (px, py, pr) in puff:
        d.ellipse([S(w * (px - pr)), S(h * py - w * pr), S(w * (px + pr)), S(h * py + w * pr)], fill=(252, 252, 255, 255))
    # band
    d.rounded_rectangle([S(w * 0.18) - S(3), S(h * 0.58) - S(3), S(w * 0.82) + S(3), S(h * 0.92) + S(3)], radius=S(10), fill=outline)
    d.rounded_rectangle([S(w * 0.18), S(h * 0.58), S(w * 0.82), S(h * 0.92)], radius=S(8), fill=(244, 244, 248, 255))
    for k in range(3):
        x = w * (0.33 + 0.17 * k)
        d.line([S(x), S(h * 0.61), S(x), S(h * 0.89)], fill=(205, 205, 215, 255), width=S(2))
    big = big.resize((w, h), Image.LANCZOS)
    # soft shading
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    sd.ellipse([int(w * 0.45), int(h * 0.05), int(w * 0.98), int(h * 0.62)], fill=(120, 130, 160, 60))
    sh = sh.filter(ImageFilter.GaussianBlur(8))
    al = big.getchannel("A")
    shm = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shm.paste(sh, (0, 0), Image.composite(sh.getchannel("A"), Image.new("L", (w, h), 0), al))
    big.alpha_composite(shm)
    return shadowed(big, blur=6, dy=4, alpha=0.45)


# ---------- arrow ----------
def draw_arrow(canvas, p0, p1, bend, color, prog, alpha, width=8):
    """Quadratic bezier arrow drawn progressively (screen coords)."""
    if alpha <= 0.003 or prog <= 0:
        return
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    nx, ny = -(y1 - y0), (x1 - x0)
    nl = math.hypot(nx, ny) or 1
    cx, cy = mx + nx / nl * bend, my + ny / nl * bend
    n = 48
    pts = []
    for i in range(int(n * clamp01(prog)) + 1):
        t = i / n
        pts.append(((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1,
                    (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1))
    if len(pts) < 2:
        return
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    pad = 40
    bx0, by0 = int(min(xs) - pad), int(min(ys) - pad)
    bw, bh = int(max(xs) - min(xs) + 2 * pad), int(max(ys) - min(ys) + 2 * pad)
    ss = 3
    big = Image.new("RGBA", (bw * ss, bh * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    sp = [((x - bx0) * ss, (y - by0) * ss) for x, y in pts]
    d.line(sp, fill=(0, 0, 0, 120), width=(width + 4) * ss, joint="curve")
    d.line(sp, fill=rgba(color), width=width * ss, joint="curve")
    # head
    ex, ey = pts[-1]
    px, py = pts[-4] if len(pts) > 4 else pts[0]
    ang = math.atan2(ey - py, ex - px)
    L = 30
    hp = [(ex + math.cos(ang) * 8, ey + math.sin(ang) * 8),
          (ex - math.cos(ang - 0.5) * L, ey - math.sin(ang - 0.5) * L),
          (ex - math.cos(ang + 0.5) * L, ey - math.sin(ang + 0.5) * L)]
    d.polygon([((x - bx0) * ss, (y - by0) * ss) for x, y in hp], fill=rgba(color))
    big = big.resize((bw, bh), Image.LANCZOS)
    big = with_alpha(big, alpha)
    canvas.alpha_composite(big, dest=(max(0, bx0), max(0, by0)), source=(max(0, -bx0), max(0, -by0)))


# ---------- wave from Sapho ----------
def draw_wave(canvas, origin, direction_deg, t, alpha, color=BLU, reach=520):
    """Directional ripples; t = seconds since start."""
    if alpha <= 0.003:
        return
    ox, oy = origin
    pad = reach + 40
    bw, bh = 2 * pad, 2 * pad
    lay = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    period = 1.1
    for k in range(4):
        ph = (t - k * period / 2.2)
        if ph < 0:
            continue
        ph = (ph % period) / period
        r = 60 + ph * reach
        a = (1 - ph) ** 1.4
        if a < 0.02:
            continue
        span = 46
        bb = [pad - r, pad - r, pad + r, pad + r]
        d.arc(bb, direction_deg - span, direction_deg + span, fill=rgba(color, 255 * a), width=22)
        d.arc(bb, direction_deg - span + 3, direction_deg + span - 3, fill=rgba(WHITE, 230 * a), width=7)
    lay = lay.filter(ImageFilter.GaussianBlur(1.6))
    glow = lay.filter(ImageFilter.GaussianBlur(10))
    out = Image.new("RGBA", lay.size, (0, 0, 0, 0))
    out.alpha_composite(glow); out.alpha_composite(lay)
    out = with_alpha(out, alpha * 0.9)
    x, y = int(ox - pad), int(oy - pad)
    canvas.alpha_composite(out, dest=(max(0, x), max(0, y)), source=(max(0, -x), max(0, -y)))
