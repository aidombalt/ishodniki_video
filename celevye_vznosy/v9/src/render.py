"""Frame renderer: pycairo shapes/compositing, PIL+raqm text, Golos Text. Usage:
   render.py stills t1 t2 ...   -> PNG stills
   render.py video               -> clean MP4 and SRT
   render.py srt                 -> SRT only
   render.py check               -> layout checks at rest moments"""
import sys, json, math, subprocess, re
import numpy as np, cairo
from PIL import Image, ImageFont, ImageDraw
from content import SPOKEN, SUBS, N as NB

import os
ROOT = os.environ.get('PROJECT_ROOT', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK = ROOT + '/build/'; ASSETS = ROOT + '/input/assets/'; FONTD = ROOT + '/input/fonts/'
OUT = ROOT + '/output/'
W, H, FPS = 1920, 1080, 25
FONT = {'R': 'Golos-Text_Regular.ttf', 'M': 'Golos-Text_Medium.ttf', 'D': 'Golos-Text_DemiBold.ttf', 'B': 'Golos-Text_Bold.ttf'}


def hexc(h): return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


NAVY, CYAN, INK, LIGHT, WHITE = hexc('#002A5B'), hexc('#00A0E3'), hexc('#111820'), hexc('#EEF3F7'), (1, 1, 1)
MUTED = hexc('#56606C')       # secondary text (ink, softened)
KICK = MUTED                  # one secondary colour for kickers, captions, notes
RULE = hexc('#C9D5E1')
L, R = 150, 1770
KY = 190          # kicker baseline
TY = 300          # title baseline
SAFE_BOTTOM = 790
AIR = 16          # minimal vertical gap between stacked text blocks

import os
TL = json.load(open(os.environ.get('TLFILE', WORK + 'timeline.json')))
ITEMS = {d['name']: d for d in TL['timeline']}
SEGS = json.load(open(os.environ.get('SEGFILE', WORK + 'segs.json')))
TOTAL = TL['total']


def cut(n): return ITEMS[n]['cut']


def _item_for(f, k):
    for d in TL['timeline']:
        if d.get('vo') == f and d['segs'][0] <= k <= d['segs'][1]:
            return d


def seg_t(f, k, end=False):
    d = _item_for(f, k)
    return d['t0'] + SEGS[f][k][1 if end else 0] - d['a']


VOW = set('аеёиоуыэюяАЕЁИОУЫЭЮЯ')


def nv(s): return sum(c in VOW for c in s)


def word_t(f, k, phrase):
    sp = SPOKEN[f][k]; i = sp.index(phrase)
    r = nv(sp[:i]) / max(nv(sp), 1)
    a, b = SEGS[f][k]
    return seg_t(f, k) + r * (b - a)


# ---------------------------------------------------------------- text
_fonts, _tc = {}, {}


def font(w, s):
    k = (w, s)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(FONTD + FONT[w], s, layout_engine=ImageFont.Layout.RAQM)
    return _fonts[k]


def tw(txt, w, s): return font(w, s).getlength(txt)


def tmask(txt, w, s):
    k = (txt, w, s)
    if k in _tc: return _tc[k]
    f = font(w, s)
    l, t, r, b = f.getbbox(txt, anchor='ls')
    pad = 3; wp, hp = r - l + 2 * pad, b - t + 2 * pad
    im = Image.new('L', (wp, hp), 0)
    ImageDraw.Draw(im).text((pad - l, pad - t), txt, font=f, fill=255, anchor='ls')
    st = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_A8, wp)
    arr = np.zeros((hp, st), np.uint8); arr[:, :wp] = np.asarray(im)
    surf = cairo.ImageSurface.create_for_data(memoryview(arr), cairo.FORMAT_A8, wp, hp, st)
    res = (surf, arr, l - pad, t - pad, (l, t, r, b))
    _tc[k] = res
    return res


PREP = set('в во на и а о об с со по из для к у не за от до без при что как но или же его её их'.split())


def wrap(txt, w, s, maxw):
    """fewest lines that fit, then the most even split; never end a line on a preposition"""
    words = txt.split(' ')
    def ok_break(i): return words[i - 1].lower() not in PREP and words[i] != '—'   # a dash never starts a line
    best = None
    def rec(start, n):
        if n == 1:
            ln = ' '.join(words[start:])
            return [ln] if tw(ln, w, s) <= maxw else None
        res = None
        for i in range(start + 1, len(words)):
            if not ok_break(i): continue
            ln = ' '.join(words[start:i])
            if tw(ln, w, s) > maxw: break
            rest = rec(i, n - 1)
            if rest:
                cand = [ln] + rest
                sc = max(tw(x, w, s) for x in cand) - min(tw(x, w, s) for x in cand) * 0.3
                if res is None or sc < res[0]: res = (sc, cand)
        return res[1] if isinstance(res, tuple) else res
    for n in range(1, 6):
        r = rec(0, n)
        if r: return r
    return [txt]


# ---------------------------------------------------------------- primitives
def ease_out(x): x = min(max(x, 0), 1); return 1 - (1 - x) ** 3
def ease_in(x): x = min(max(x, 0), 1); return x ** 3
def ease_io(x): x = min(max(x, 0), 1); return 3 * x * x - 2 * x ** 3


def lerp(a, b, k): return a + (b - a) * k


def rrect(ctx, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0); ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi); ctx.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    ctx.close_path()


class Text:
    def __init__(s, txt, w, size, x, y, color=INK, align='l'):
        s.txt, s.w, s.size, s.color, s.align = txt, w, size, color, align
        s.width = tw(txt, w, size)
        s.x = x - (s.width if align == 'r' else s.width / 2 if align == 'c' else 0); s.y = y

    def bbox(s):
        l, t, r, b = tmask(s.txt, s.w, s.size)[4]
        return (s.x + l, s.y + t, s.x + r, s.y + b)

    def draw(s, ctx, a, dx=0, dy=0, scale=1.0, ox=None, oy=None):
        surf, _, ox_, oy_, _ = tmask(s.txt, s.w, s.size)
        ctx.save()
        x, y = s.x + dx, s.y + dy
        if scale != 1.0:
            ax = s.x if ox is None else ox; ay = s.y if oy is None else oy
            ctx.translate(ax + dx, ay + dy); ctx.scale(scale, scale); ctx.translate(-ax, -ay); x, y = s.x, s.y
        else:
            x, y = round(x), round(y)
        ctx.set_source_rgba(*s.color, a)
        ctx.mask_surface(surf, x + ox_, y + oy_)
        ctx.restore()


_img = {}


def load_img(name, crop=True):
    if name not in _img:
        im = Image.open(name).convert('RGBA')
        if crop and im.getbbox(): im = im.crop(im.getchannel('A').getbbox())
        _img[name] = im
    return _img[name]


_isurf = {}


def img_surface(name, w, h, crop=True):
    k = (name, int(w), int(h))
    if k not in _isurf:
        im = load_img(name, crop).resize((int(w), int(h)), Image.LANCZOS)
        a = np.asarray(im).astype(np.float32)
        al = a[..., 3:4] / 255
        pm = np.concatenate([a[..., 2:3] * al, a[..., 1:2] * al, a[..., 0:1] * al, a[..., 3:4]], 2).astype(np.uint8)
        st = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, int(w))
        buf = np.zeros((int(h), st // 4, 4), np.uint8); buf[:, :int(w)] = pm
        _isurf[k] = (cairo.ImageSurface.create_for_data(memoryview(buf), cairo.FORMAT_ARGB32, int(w), int(h), st), buf)
    return _isurf[k][0]


def fit(name, box, crop=True):
    """contain-fit image in box (x,y,w,h); returns rect"""
    im = load_img(name, crop); x, y, w, h = box
    k = min(w / im.width, h / im.height)
    iw, ih = im.width * k, im.height * k
    return (x + (w - iw) / 2, y + (h - ih) / 2, iw, ih)


def draw_img(ctx, name, rect, a, crop=True, ref=None):
    x, y, w, h = rect
    rw, rh = (ref[2], ref[3]) if ref else (w, h)
    surf = img_surface(name, rw, rh, crop)
    ctx.save(); ctx.translate(x, y); ctx.scale(w / rw, h / rh)
    ctx.set_source_surface(surf, 0, 0); ctx.get_source().set_filter(cairo.FILTER_GOOD)
    ctx.paint_with_alpha(a); ctx.restore()


# ---------------------------------------------------------------- icons (navy line style)
def icon(ctx, kind, x, y, s, color, a):
    ctx.save(); ctx.translate(x, y); ctx.scale(s / 64, s / 64)
    ctx.set_source_rgba(*color, a); ctx.set_line_width(5); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    if kind == 'pin':
        ctx.move_to(32, 60); ctx.curve_to(18, 44, 10, 34, 10, 24); ctx.arc(32, 24, 22, math.pi, 0)
        ctx.curve_to(54, 34, 46, 44, 32, 60); ctx.close_path(); ctx.stroke()
        ctx.arc(32, 24, 8, 0, 2 * math.pi); ctx.stroke()
    elif kind == 'web':
        ctx.arc(32, 32, 26, 0, 2 * math.pi); ctx.stroke()
        ctx.save(); ctx.translate(32, 32); ctx.scale(0.45, 1); ctx.arc(0, 0, 26, 0, 2 * math.pi); ctx.restore(); ctx.stroke()
        ctx.move_to(6, 32); ctx.line_to(58, 32); ctx.stroke()
        ctx.move_to(11, 19); ctx.line_to(53, 19); ctx.move_to(11, 45); ctx.line_to(53, 45); ctx.stroke()
    elif kind == 'clock':
        ctx.arc(32, 32, 26, 0, 2 * math.pi); ctx.stroke()
        ctx.move_to(32, 16); ctx.line_to(32, 32); ctx.line_to(43, 39); ctx.stroke()
    elif kind == 'cal':
        rrect(ctx, 8, 12, 48, 44, 7); ctx.stroke()
        ctx.move_to(8, 26); ctx.line_to(56, 26); ctx.stroke()
        ctx.move_to(21, 6); ctx.line_to(21, 16); ctx.move_to(43, 6); ctx.line_to(43, 16); ctx.stroke()
    elif kind == 'doc':
        ctx.move_to(14, 6); ctx.line_to(40, 6); ctx.line_to(52, 18); ctx.line_to(52, 58); ctx.line_to(14, 58); ctx.close_path(); ctx.stroke()
        for yy in (28, 38, 48): ctx.move_to(22, yy); ctx.line_to(44, yy)
        ctx.stroke()
    elif kind in ('down', 'up'):
        ctx.arc(32, 32, 28, 0, 2 * math.pi); ctx.stroke()
        if kind == 'down':
            ctx.move_to(32, 17); ctx.line_to(32, 46); ctx.move_to(21, 36); ctx.line_to(32, 47); ctx.line_to(43, 36)
        else:
            ctx.move_to(32, 47); ctx.line_to(32, 18); ctx.move_to(21, 28); ctx.line_to(32, 17); ctx.line_to(43, 28)
        ctx.stroke()
    elif kind == 'user':
        ctx.arc(32, 22, 11, 0, 2 * math.pi); ctx.stroke()
        ctx.move_to(10, 58); ctx.curve_to(10, 42, 20, 36, 32, 36); ctx.curve_to(44, 36, 54, 42, 54, 58); ctx.stroke()
    elif kind == 'drop':
        ctx.move_to(32, 6); ctx.curve_to(24, 20, 12, 30, 12, 40); ctx.arc_negative(32, 40, 20, math.pi, 0)
        ctx.curve_to(52, 30, 40, 20, 32, 6); ctx.close_path(); ctx.stroke()
    elif kind == 'valve':
        rrect(ctx, 4, 34, 56, 18, 5); ctx.stroke()
        ctx.move_to(32, 34); ctx.line_to(32, 18); ctx.stroke()
        ctx.move_to(16, 14); ctx.line_to(48, 14); ctx.stroke()
        ctx.move_to(20, 60); ctx.line_to(44, 60); ctx.stroke()
    elif kind == 'flood':
        rrect(ctx, 8, 4, 48, 22, 4); ctx.stroke()
        rrect(ctx, 8, 40, 48, 22, 4); ctx.stroke()
        for xx in (22, 42):
            ctx.move_to(xx, 28); ctx.curve_to(xx - 3, 32, xx - 4, 34, xx, 37); ctx.curve_to(xx + 4, 34, xx + 3, 32, xx, 28); ctx.stroke()
    elif kind == 'box':
        rrect(ctx, 8, 14, 48, 42, 6); ctx.stroke()
        ctx.move_to(18, 28); ctx.line_to(46, 28); ctx.stroke()
        ctx.move_to(24, 42); ctx.line_to(40, 42); ctx.stroke()
    elif kind == 'lock':
        rrect(ctx, 12, 28, 40, 30, 6); ctx.stroke()
        ctx.move_to(20, 28); ctx.line_to(20, 20); ctx.arc(32, 20, 12, math.pi, 0); ctx.line_to(44, 28); ctx.stroke()
    ctx.restore()


# ---------------------------------------------------------------- scene graph
class El:
    """Visible from t_in (fade-in din, rising) to t_out (fade-out dout ending at t_out)."""
    def __init__(s, draw, t_in, t_out, din=0.45, dout=0.2, rise=22, box=None, kind='content', name='', inside=None):
        s.drawf, s.t_in, s.t_out, s.din, s.dout, s.rise = draw, t_in, t_out, din, dout, rise
        s.box, s.kind, s.name, s.inside = box, kind, name, inside
        s.boxes = None

    def box_at(s, t):
        if s.boxes:
            for t0, t1, b in s.boxes:
                if t0 <= t < t1: return b
        return s.box

    def alpha(s, t):
        if t < s.t_in or t >= s.t_out: return 0, 0
        ai = ease_out((t - s.t_in) / s.din) if s.din > 0 else 1
        ao = 1 - ease_in((t - (s.t_out - s.dout)) / s.dout) if s.dout > 0 else 1
        return min(ai, ao), s.rise * (1 - ai) - 8 * (1 - ao)

    def draw(s, ctx, t):
        a, dy = s.alpha(t)
        if a > 0.002: s.drawf(ctx, t, a, dy)


ELS = []


def add_text(txt, w, size, x, y, t_in, t_out, color=INK, align='l', din=0.45, dout=0.2, rise=22, inside=None, name=''):
    o = Text(txt, w, size, x, y, color, align)
    ELS.append(El(lambda ctx, t, a, dy, o=o: o.draw(ctx, a, 0, dy), t_in, t_out, din, dout, rise, box=o.bbox(),
                  name=name or txt[:24], inside=inside))
    return o


def add_lines(lines, w, size, x, y0, lh, t_in, t_out, color=INK, stagger=0.06, **kw):
    out = []
    for i, ln in enumerate(lines):
        out.append(add_text(ln, w, size, x, y0 + i * lh, t_in + i * stagger, t_out, color, **kw))
    return out


def add_card(x, y, w, h, t_in, t_out, fill=LIGHT, r=28, din=0.5, name='card', dashed=False):
    def d(ctx, t, a, dy):
        rrect(ctx, x, y + dy, w, h, r)
        if dashed:
            ctx.set_source_rgba(*NAVY, a * 0.45); ctx.set_line_width(3); ctx.set_dash([14, 10]); ctx.stroke(); ctx.set_dash([])
        else:
            ctx.set_source_rgba(*fill, a); ctx.fill()
    ELS.append(El(d, t_in, t_out, din, 0.3, 22, box=(x, y, x + w, y + h), kind='card', name=name))
    return (x, y, x + w, y + h)


def add_icon(kind, x, y, s, t_in, t_out, color=NAVY):
    ELS.append(El(lambda ctx, t, a, dy: icon(ctx, kind, x, y + dy, s, color, a), t_in, t_out, box=(x, y, x + s, y + s),
                  name='icon-' + kind, kind='deco'))


def kicker(txt, t_in, t_out):
    return add_text(txt, 'D', 56, L, KY, t_in, t_out, KICK, name='kicker')


def title(txt, t_in, t_out, size=88):
    return add_text(txt, 'B', size, L, TY, t_in, t_out, NAVY, name='title')


def bullet_item(txt, x, y, t_in, t_out, w='M', size=60, color=INK):
    def d(ctx, t, a, dy):
        rrect(ctx, x, y - 30 + dy, 14, 14, 3); ctx.set_source_rgba(*NAVY, a); ctx.fill()
    ELS.append(El(d, t_in, t_out, box=(x, y - 30, x + 14, y - 16), name='bullet'))
    return add_text(txt, w, size, x + 40, y, t_in, t_out, color)


def accent_bar(box, t_in, t_out):
    """cyan underline under a computed value (data accent, same as 41 m2 in the example)"""
    x0, y, x1 = box[0], box[3] + 22, box[2]
    def d(ctx, t, a, dy):
        k = ease_out((t - t_in) / 0.6)
        if k <= 0: return
        rrect(ctx, x0, y + dy, (x1 - x0) * k, 10, 5); ctx.set_source_rgba(*CYAN, a); ctx.fill()
    ELS.append(El(d, t_in, t_out, 0.3, 0.3, 0, box=(x0, y, x1, y + 10), name='accent', kind='deco'))


def six_payments(x0, y, x1, h, t_in, t_out):
    """the one sign for 'six equal payments': six cyan segments drawn left to right, then still"""
    gap = 8; w = (x1 - x0 - 5 * gap) / 6
    def d(ctx, t, a, dy):
        for i in range(6):
            k = ease_out((t - t_in - i * 0.08) / 0.3)
            if k <= 0: continue
            rrect(ctx, x0 + i * (w + gap), y + dy, w * k, h, min(10, h / 2)); ctx.set_source_rgba(*CYAN, a); ctx.fill()
    ELS.append(El(d, t_in, t_out, 0.2, 0.2, 0, box=(x0, y, x1, y + h), name='six', kind='deco'))


def caption_ill(x_right, y, t_in, t_out):
    return add_text('Условная иллюстрация', 'R', 56, x_right, y, t_in, t_out, MUTED, align='r', name='caption')


# ---------------------------------------------------------------- photos of the house (why the works are needed)
PH = ROOT + '/input/photos/'


def photo(n, aspect, cx=0.5, cy=0.5, zoom=1.0):
    """cover crop of photo n to aspect w/h around the focus point (fractions of the frame)"""
    key = 'ph:%s:%.3f:%.3f:%.3f:%.2f' % (n, aspect, cx, cy, zoom)
    if key not in _img:
        im = Image.open(PH + '%s.jpg' % n).convert('RGBA')
        W0, H0 = im.size
        w = min(W0, H0 * aspect) / zoom; h = w / aspect
        x0 = min(max(cx * W0 - w / 2, 0), W0 - w); y0 = min(max(cy * H0 - h / 2, 0), H0 - h)
        _img[key] = im.crop((round(x0), round(y0), round(x0 + w), round(y0 + h)))
    return key


def add_photo(key, x, y, w, h, t_in, t_out, name, din=0.55, r=28):
    def d(ctx, t, a, dy):
        ctx.save(); rrect(ctx, x, y + dy, w, h, r); ctx.clip()
        draw_img(ctx, key, (x, y + dy, w, h), a, crop=False); ctx.restore()
    ELS.append(El(d, t_in, t_out, din, 0.3, 26, box=(x, y, x + w, y + h), kind='card', name=name))


# ================================================================ scenes
def sc_logo():
    t0, t1 = cut('logo'), cut('01rad')
    logo = ASSETS + 'petersburg_dom_transparent.png'
    rect = fit(logo, LOGO_BOX)

    def d(ctx, t, a, dy):
        k = ease_out((t - t0) / 1.0); sc = 0.96 + 0.04 * k
        x, y, w, h = rect; cx, cy = x + w / 2, y + h / 2
        draw_img(ctx, logo, (cx - w * sc / 2, cy - h * sc / 2 + dy * 0.3, w * sc, h * sc), a, ref=rect)
    ELS.append(El(d, t0, t1, 0.9, 0.35, 0, box=(rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]), name='logo'))
    add_text('ЖК «Екатерининский»', 'D', 64, 960, 670, t0 + 0.55, t1, NAVY, 'c')
    add_text('Екатерининский проспект, д.' + NB + '2, стр.' + NB + '1', 'R', 56, 960, 750, t0 + 0.7, t1, MUTED, 'c')


LOGO_BOX = (L, 130, R - L, 420)
RAD = ASSETS + 'previous_radiator.png'
TILES = [ASSETS + n for n in ('water.png', 'halls.png', 'kids.png', 'sport.png')]


def kb_photo(key, x, y, w, h, t_in, t_out, name, zoom_to=1.06, focus=(0.5, 0.5), r=28, din=0.55, zoom_t=None):
    """photo card with a slow push-in over its life (zoom_t: optional (t0, t1, z) extra push to a focus)"""
    def d(ctx, t, a, dy):
        k = min(max((t - t_in) / max(t_out - t_in, 1e-3), 0), 1)
        z = 1 + (zoom_to - 1) * k
        fx, fy = focus
        if zoom_t:
            kk = ease_io((t - zoom_t[0]) / (zoom_t[1] - zoom_t[0])); z *= 1 + (zoom_t[2] - 1) * kk
            fx, fy = lerp(fx, zoom_t[3][0], kk), lerp(fy, zoom_t[3][1], kk)
        W2, H2 = w * z, h * z
        ox, oy = x - (W2 - w) * fx, y + dy - (H2 - h) * fy
        ctx.save(); rrect(ctx, x, y + dy, w, h, r); ctx.clip()
        draw_img(ctx, key, (ox, oy, W2, H2), a, crop=False, ref=(0, 0, w, h)); ctx.restore()
    ELS.append(El(d, t_in, t_out, din, 0.3, 26, box=(x, y, x + w, y + h), kind='card', name=name))


def outline_pulse(box, t0, t1, r=28):
    x0, y0, x1, y1 = box
    def d(ctx, t, a, dy):
        k = min(ease_out((t - t0) / 0.3), 1 - ease_in((t - (t1 - 0.4)) / 0.4))
        if k <= 0: return
        rrect(ctx, x0 - 6, y0 - 6 + dy, x1 - x0 + 12, y1 - y0 + 12, r + 6); ctx.set_line_width(5)
        ctx.set_source_rgba(*NAVY, a * k); ctx.stroke()
    ELS.append(El(d, t0, t1, 0.2, 0.2, 0, box=(x0, y0, x1, y1), kind='deco', name='pulse'))


def navy_chip(txt, x, y, t_in, t_out, size=60, h=104, w='D'):
    cw = tw(txt, w, size) + 72
    cd = add_card(x, y, cw, h, t_in, t_out, fill=NAVY, r=26, name='chip-' + txt[:10])
    add_text(txt, w, size, x + 36, y + h / 2 + size * 0.36, t_in + 0.05, t_out, WHITE, inside=cd)
    return cd


def branch_arrow(pts, t_in, t_out, dur=0.5):
    """navy elbow arrow that draws itself along its length, head at the end"""
    segs = list(zip(pts, pts[1:])); lens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs]; tot = sum(lens)
    def d(ctx, t, a, dy):
        k = ease_out((t - t_in) / dur) * tot
        ctx.set_source_rgba(*NAVY, a); ctx.set_line_width(5); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.move_to(pts[0][0], pts[0][1] + dy); left = k; end = pts[0]
        for (p0, p1), ln in zip(segs, lens):
            if left <= 0: break
            f = min(1, left / ln); end = (p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f)
            ctx.line_to(end[0], end[1] + dy); left -= ln
        ctx.stroke()
        if k >= tot - 1:
            ex, ey = pts[-1]; ctx.move_to(ex - 16, ey - 13 + dy); ctx.line_to(ex, ey + dy); ctx.line_to(ex - 16, ey + 13 + dy); ctx.stroke()
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    ELS.append(El(d, t_in, t_out, 0.2, 0.3, 0, box=(min(xs), min(ys) - 13, max(xs), max(ys) + 13), kind='deco', name='branch'))


def ribbon(x0, x1, y, h, t_six, t_tail, t_out, tail_w=440, lab_six=None, lab_tail=None, lab_y=None):
    """six cyan payments, then a light grey stretch: no further charges"""
    xs1 = x1 - tail_w - 30 if t_tail else x1
    six_payments(x0, y, xs1, h, t_six, t_out)
    if t_tail:
        def d(ctx, t, a, dy):
            k = ease_out((t - t_tail) / 0.6)
            if k <= 0: return
            rrect(ctx, x1 - tail_w, y + dy, tail_w * k, h, min(10, h / 2)); ctx.set_source_rgba(*RULE, a * 0.8); ctx.fill()
        ELS.append(El(d, t_tail, t_out, 0.2, 0.2, 0, box=(x1 - tail_w, y, x1, y + h), name='tail', kind='deco'))
    ly = lab_y or y + h + 76
    if lab_six: add_text(lab_six, 'R', 56, x0, ly, t_six + 0.2, t_out, MUTED)
    if lab_tail and t_tail: add_text(lab_tail, 'R', 56, x1, ly, t_tail + 0.2, t_out, MUTED, 'r')


# ---------------------------------------------------------------- v5 scenes
def sc_01():
    c1, c2, end = cut('01rad'), cut('01main'), cut('02a')
    kicker('В прошлом видео', c1, c2)
    title('Распределители тепла', c1 + 0.08, c2)
    card0 = (720, 330, 1050, 460)
    tw_, gap = 380, (R - L - 4 * 380) / 3
    TH = 270
    tiles = [(L + i * (tw_ + gap), 520, tw_, TH) for i in range(4)]
    rim = load_img(RAD, crop=False)

    def morph(ctx, t, a, dy):
        k = ease_io((t - (c2 - 0.15)) / 0.75)
        x = lerp(card0[0], tiles[0][0], k); y = lerp(card0[1], tiles[0][1], k) + dy
        w = lerp(card0[2], tiles[0][2], k); h = lerp(card0[3], tiles[0][3], k)
        ctx.save(); rrect(ctx, x, y, w, h, 28); ctx.clip()
        ctx.set_source_rgba(*LIGHT, a); ctx.paint()
        if k < 1:
            s = max(w / rim.width, h / rim.height)
            iw, ih = rim.width * s, rim.height * s
            draw_img(ctx, RAD, (x + w - iw, y + (h - ih) / 2, iw, ih), a * (1 - ease_io(k * 1.4)), crop=False,
                     ref=(0, 0, 1100, 1100 * rim.height / rim.width))
        if k > 0:
            r_ = fit(TILES[0], (x + 18, y + 14, w - 36, h - 28))
            draw_img(ctx, TILES[0], r_, a * ease_io((k - 0.35) / 0.65), ref=fit(TILES[0], (0, 0, tw_ - 36, TH - 28)))
        ctx.restore()
    e = El(morph, c1 + 0.15, end, 0.6, 0.3, 22, box=(card0[0], card0[1], card0[0] + card0[2], card0[1] + card0[3]),
           kind='card', name='radiator')
    e.boxes = [(0, c2 - 0.15, e.box), (c2 - 0.15, 1e9, (tiles[0][0], tiles[0][1], tiles[0][0] + tw_, tiles[0][1] + TH))]
    ELS.append(e)
    for i in (1, 2, 3):
        x, y, w, h = tiles[i]
        def d(ctx, t, a, dy, x=x, y=y, w=w, h=h, i=i):
            rrect(ctx, x, y + dy, w, h, 28); ctx.set_source_rgba(*LIGHT, a); ctx.fill()
            draw_img(ctx, TILES[i], fit(TILES[i], (x + 18, y + 14 + dy, w - 36, h - 28)), a)
        ELS.append(El(d, c2 + 0.35 + 0.1 * i, end, 0.55, 0.3, 26, box=(x, y, x + w, y + h), kind='card', name='tile'))
    # the tiles light up as the topics are named
    box = lambda i: (tiles[i][0], tiles[i][1], tiles[i][0] + tw_, tiles[i][1] + TH)
    for i, wd in ((0, 'холодного'), (1, 'холлов'), (2, 'площадок'), (3, 'площадок')):
        t0 = word_t('v01', 2, wd) - 0.1
        outline_pulse(box(i), t0, t0 + 1.6)
    kicker('Ещё одна часть повестки', c2, end)
    t_title = seg_t('v01', 1) - 0.3
    title('Четыре вопроса на голосовании', t_title, end)
    add_text('Водоснабжение, холлы и лестницы, площадки', 'M', 60, L, TY + 82, seg_t('v01', 2) - 0.25, end, NAVY)


def sc_v02():
    c1, c2, c3, end = cut('02a'), cut('02b'), cut('02c'), cut('03a')
    kicker('В доме', c1, end)
    title('Холодное водоснабжение', c1 + 0.08, end)
    add_text('Стояки и трубы в подвале изнашиваются', 'M', 60, L, TY + 90, seg_t('v02', 1) - 0.25, c3, INK)
    py, ph = 450, 330
    lw = 440; rx = L + 560; rh, rg = 150, 30
    t_c = word_t('v02', 2, 'прорвёт') - 0.3
    cd = add_card(L, py, lw, ph, t_c, c3, name='cause')
    add_icon('drop', L + lw / 2 - 48, py + 44, 96, t_c + 0.1, c3)
    add_lines(['Прорыв', 'на стояке'], 'M', 56, L + lw / 2, py + 214, 70, t_c + 0.1, c3, INK, align='c', inside=cd)
    for i, (ic, txt, wd) in enumerate([('valve', 'Воду отключают по стояку', 'отключить'), ('flood', 'Может залить соседей снизу', 'залить')]):
        y = py + i * (rh + rg); ti = word_t('v02', 2, wd) - 0.3
        cdi = add_card(rx, y, R - rx, rh, ti, c3, name='effect')
        add_icon(ic, rx + 36, y + rh / 2 - 36, 72, ti + 0.1, c3)
        add_text(txt, 'M', 56, rx + 140, y + rh / 2 + 20, ti + 0.1, c3, INK, inside=cdi)
        branch_arrow([(L + lw + 14, py + ph / 2), (L + lw + 50, py + ph / 2), (L + lw + 50, y + rh / 2), (rx - 14, y + rh / 2)],
                     ti - 0.2, c3)
    t3 = seg_t('v02', 3) - 0.3
    cd = add_card(L, 450, R - L, 200, c3 + 0.05, end, fill=NAVY, name='plan')
    add_text('Менять планово, не дожидаясь аварии', 'D', 68, 960, 572, t3 + 0.05, end, WHITE, 'c', inside=cd)


def sc_v03():
    c1, c2, end = cut('03a'), cut('03b'), cut('04a')
    kicker('В доме', c1, end)
    title('Холлы и чёрные лестницы', c1 + 0.08, end)
    t1 = seg_t('v03', 0) - 0.3
    kb_photo(photo(1, 650 / 420, *FOCUS[1]), L, 360, 650, 420, t1, end, 'ph-stairs', focus=(0.5, 0.7))
    LX = L + 650 + 64
    add_text('Потёртости и сколы краски', 'M', 60, LX, 440, t1 + 0.15, end, INK)
    t2 = seg_t('v03', 2) - 0.25
    add_lines(['Общее имущество', 'всех собственников'], 'R', 56, LX, 540, 72, t2, end, MUTED)
    add_text('Привести в порядок', 'D', 64, LX, 730, seg_t('v03', 3) - 0.25, end, NAVY)


def sc_v04():
    c1, c2, end = cut('04a'), cut('04b'), cut('05a')
    kicker('Во дворе', c1, end)
    title('Детская и спортивная площадки', c1 + 0.08, end)
    CW, CH, CY = 786, 350, 360; X2 = R - CW; CAPY = CY + CH + 60
    t0 = seg_t('v04', 0) - 0.3
    t_sw = word_t('v04', 1, 'а на детских') + 0.2
    kb_photo(photo(20, CW / CH, *FOCUS[20]), L, CY, CW, CH, t0, t_sw + 0.5, 'ph-kids')
    add_text('Детская площадка', 'M', 56, L, CAPY, t0 + 0.1, t_sw + 0.5, INK)
    t_sp = word_t('v04', 1, 'На спортивной') - 0.1
    kb_photo(photo(26, CW / CH, *FOCUS[26]), X2, CY, CW, CH, t_sp, end, 'ph-sport')
    add_text('Спортивная площадка', 'M', 56, X2, CAPY, t_sp + 0.1, end, INK)
    t_kz = seg_t('v04', 3) - 0.2
    kb_photo(photo(10, CW / CH, *FOCUS[10]), L, CY, CW, CH, t_sw, end, 'ph-repair', din=0.5,
             zoom_t=(t_kz, t_kz + 2.0, 1.25, (0.45, 0.65)))
    add_text('Следы ремонта покрытия', 'M', 56, L, CAPY, t_sw + 0.3, end, INK)
    t_eq = word_t('v04', 4, 'оборудование') - 0.2
    outline_pulse((L, CY, L + CW, CY + CH), t_eq, t_eq + 1.8); outline_pulse((X2, CY, R, CY + CH), t_eq, t_eq + 1.8)


TR_ACCR, TR_DONE, TR_COLD = 5567245.63, 6335850.53, 2029742.63   # 2025 report, current repair


def sc_v05():
    c1, c2, c3, c4, end = cut('05a'), cut('05b'), cut('05c'), cut('05d'), cut('06a')
    # 1. the tariff is old
    kicker('Как оплатить работы', c1, c2)
    title('Тариф на текущий ремонт', c1 + 0.08, c2)
    ty = word_t('v05', 3, 'в две тысячи') - 0.2
    yr = Text('2017', 'B', 150, L, 520, NAVY)

    def dyr(ctx, t, a, dy):
        k = ease_out((t - ty) / 0.8); yr.draw(ctx, a, 0, dy, scale=0.9 + 0.1 * k, ox=L, oy=520)
    ELS.append(El(dyr, ty, c2, 0.5, 0.3, 26, box=yr.bbox(), name='2017'))
    tx = L + yr.width + 60
    add_text('утверждён собственниками', 'M', 60, tx, 450, ty + 0.3, c2, INK)
    add_text('больше 9' + NB + 'лет назад', 'D', 60, tx, 525, seg_t('v05', 4) - 0.2, c2, NAVY)
    t_p = word_t('v05', 5, 'цены выросли') - 0.2; t_w = word_t('v05', 5, 'продолжает') - 0.2
    add_icon('up', L, 600, 72, t_p, c2)
    add_text('Рост цен', 'D', 64, L + 100, 658, t_p + 0.05, c2, NAVY)
    add_icon('clock', L + 520, 600, 72, t_w, c2)
    add_text('Износ дома', 'D', 64, L + 620, 658, t_w + 0.05, c2, NAVY)
    add_text('Средств по тарифу не хватает на ремонт', 'M', 60, L, 768, seg_t('v05', 6) - 0.2, c2, INK)
    # 2. the 2025 report: accrued vs done, the cold-water share of the works
    kicker('Отчёт УК за 2025' + NB + 'год', c2, c3)
    title('Текущий ремонт', c2 + 0.08, c3)
    full = R - L - 360; w1, w2 = full * TR_ACCR / TR_DONE, full
    LIGHTCYAN = tuple(0.55 * c + 0.45 for c in CYAN)
    rows = [('Начислено', '≈ 5,6' + NB + 'млн' + NB + '₽', 440, w1, LIGHTCYAN, word_t('v05', 7, 'начислено') - 0.3),
            ('Выполнено работ', '≈ 6,3' + NB + 'млн' + NB + '₽', 610, w2, CYAN, word_t('v05', 7, 'а работ') - 0.2)]
    t_cold = word_t('v05', 8, 'труб') - 0.2
    for lab, val, yb, wb, col, ti in rows:
        add_text(lab, 'M', 56, L, yb, ti, c3, INK)
        by = yb + 22; bh = 64

        def dbar(ctx, t, a, dy, by=by, wb=wb, col=col, ti=ti, cold=(lab == 'Выполнено работ')):
            k = ease_out((t - ti - 0.15) / 0.9)
            if k <= 0: return
            rrect(ctx, L, by + dy, wb * k, bh, 12); ctx.set_source_rgba(*col, a); ctx.fill()
            if cold:
                kc = ease_out((t - t_cold) / 0.6)
                if kc > 0:
                    ctx.save(); rrect(ctx, L, by + dy, wb * k, bh, 12); ctx.clip()
                    ctx.rectangle(L, by + dy, wb * TR_COLD / TR_DONE * kc, bh); ctx.set_source_rgba(*NAVY, a); ctx.fill()
                    ctx.restore()
        ELS.append(El(dbar, ti, c3, 0.2, 0.3, 0, box=(L, by, L + wb, by + bh), kind='deco', name='bar'))
        add_text(val, 'D', 60, L + wb + 30, by + bh / 2 + 22, ti + 0.9, c3, NAVY)
    add_text('2,03' + NB + 'млн' + NB + '₽ — холодное водоснабжение', 'M', 56, L, 776, t_cold + 0.4, c3, NAVY)
    # 3. two meetings without a quorum
    kicker('Прошлые собрания', c3, c4)
    title('Изменение тарифа', c3 + 0.08, c4)
    rh3 = 180; t_q = word_t('v05', 10, 'не набрался') - 0.2
    for i, (dates, pct) in enumerate([('Декабрь 2025 — март 2026', '24,41'), ('Май — июль 2026', '41,03')]):
        y = 370 + i * (rh3 + 24); ti = seg_t('v05', 9) - 0.2 + 0.5 * i
        cd = add_card(L, y, R - L, rh3, ti, c4, name='meeting')
        add_text(dates, 'M', 56, L + 48, y + 74, ti + 0.05, c4, INK, inside=cd)
        add_text('кворума нет', 'D', 60, L + 48, y + 148, t_q + 0.2 * i, c4, NAVY, inside=cd)
        g = add_text('голосов', 'M', 56, R - 48, y + 128, ti + 0.2, c4, MUTED, 'r', inside=cd)
        add_text(pct + NB + '%', 'B', 110, g.x - 24, y + 128, ti + 0.15, c4, NAVY, 'r', inside=cd)
    # 4. this ballot: question 7 is the tariff, questions 8, 10, 11, 12 are the one-off contributions
    kicker('Текущее собрание', c4, end)
    title('В этом бюллетене', c4 + 0.08, end)
    t7 = seg_t('v05', 13) - 0.2; t8 = word_t('v05', 16, 'оплатить отдельно') - 0.2
    cs = 104; ry1, rh = 380, 170
    cd7 = add_card(L, ry1, R - L, rh, t7, end, name='q7')

    def chip7(ctx, t, a, dy):
        x, y = L + 33, ry1 + (rh - cs) / 2 + dy
        rrect(ctx, x, y, cs, cs, 22); ctx.set_source_rgba(*NAVY, a * 0.55); ctx.set_line_width(4); ctx.stroke()
    ELS.append(El(chip7, t7 + 0.05, end, 0.45, 0.3, 22, box=(L + 33, ry1 + (rh - cs) / 2, L + 33 + cs, ry1 + (rh + cs) / 2),
                  kind='deco', name='chip7'))
    add_text('7', 'B', 64, L + 33 + cs / 2, ry1 + rh / 2 + 23, t7 + 0.05, end, NAVY, 'c', inside=cd7)
    add_text('Новый договор управления и тариф', 'D', 60, L + 33 + cs + 44, ry1 + rh / 2 + 22, t7 + 0.1, end, INK, inside=cd7)
    ry2 = ry1 + rh + 40
    cd8 = add_card(L, ry2, R - L, rh, t8, end, fill=NAVY, name='q8-12')
    for i, n in enumerate(QS):
        x = L + 33 + i * (cs + 16)

        def chipw(ctx, t, a, dy, x=x):
            rrect(ctx, x, ry2 + (rh - cs) / 2 + dy, cs, cs, 22); ctx.set_source_rgba(*WHITE, a); ctx.fill()
        ELS.append(El(chipw, t8 + 0.1 + 0.08 * i, end, 0.4, 0.3, 22, box=(x, ry2 + (rh - cs) / 2, x + cs, ry2 + (rh + cs) / 2),
                      kind='deco', name='chipw'))
        add_text(n, 'B', 56, x + cs / 2, ry2 + rh / 2 + 20, t8 + 0.1 + 0.08 * i, end, NAVY, 'c', inside=cd8)
    add_text('Единовременные целевые взносы', 'D', 60, L + 33 + 4 * cs + 3 * 16 + 44, ry2 + rh / 2 + 22, t8 + 0.4, end, WHITE,
             inside=cd8)


def sc_v06():
    c1, c2, end = cut('06a'), cut('06b'), cut('07a')
    kicker('Предложения к голосованию', c1, end)
    row_y = 250; cs = 150
    t = add_text('Вопросы', 'B', 88, L, row_y + cs / 2 + 31, seg_t('v06', 0) - 0.3, end, NAVY)
    x = L + t.width + 44
    for i, (num, wd) in enumerate(zip(['8', '10', '11', '12'], ['восемь', 'десять', 'одиннадцать', 'двенадцать'])):
        xx = x + i * (cs + 24); ti = word_t('v06', 0, wd) - 0.2
        def d(ctx, tt, a, dy, xx=xx):
            rrect(ctx, xx, row_y + dy, cs, cs, 26); ctx.set_source_rgba(*NAVY, a); ctx.fill()
        ELS.append(El(d, ti, end, 0.45, 0.3, 22, box=(xx, row_y, xx + cs, row_y + cs), kind='card', name='chip'))
        add_text(num, 'B', 84, xx + cs / 2, row_y + cs / 2 + 30, ti, end, WHITE, 'c', inside=(xx, row_y, xx + cs, row_y + cs))
    add_text('Голосование по каждому вопросу отдельно', 'D', 72, L, 530, seg_t('v06', 1) - 0.25, c2, NAVY)
    add_text('У каждого — смета или коммерческое предложение', 'R', 56, L, 620, seg_t('v06', 2) - 0.25, c2, INK)
    t1 = c2 + 0.05
    add_icon('user', L, 470, 64, t1, end)
    add_text('Личный кабинет ELSA', 'M', 60, L + 100, 522, t1 + 0.05, end, INK)
    add_text('приложение или сайт dom.myelsa.ru', 'R', 56, L + 100, 594, t1 + 0.12, end, MUTED)
    t2 = word_t('v06', 3, 'или в офисе') - 0.25
    add_icon('pin', L, 646, 64, t2, end)
    add_text('Офис управляющей компании', 'M', 60, L + 100, 698, t2 + 0.05, end, INK)
    add_text('в рабочие часы: пн–пт, 9:00–18:00', 'R', 56, L + 100, 770, t2 + 0.12, end, MUTED)


def sc_v07():
    c1, c2, c3, end = cut('07a'), cut('07b'), cut('07c'), cut('08')
    kicker('Как устроен взнос', c1, end)
    title('Единовременный взнос', c1 + 0.08, end)
    add_text('Сумма определяется один раз', 'M', 60, L, 384, seg_t('v07', 1) - 0.25, end, NAVY)
    by, bh = 420, 180; ws = [500, 380, 560]; op = (R - L - sum(ws)) / 2
    bx = [L, L + ws[0] + op, L + ws[0] + ws[1] + 2 * op]
    tf = seg_t('v07', 2) - 0.2
    b1 = add_card(bx[0], by, ws[0], bh, tf, end, name='box1')
    add_lines(['Общая площадь', 'помещения'], 'M', 56, bx[0] + ws[0] / 2, by + 84, 70, tf + 0.05, end, INK, align='c', inside=b1)
    add_text('×', 'R', 84, bx[0] + ws[0] + op / 2, by + bh / 2 + 28, tf + 0.15, end, NAVY, 'c')
    t2 = word_t('v07', 3, 'на размер') - 0.25
    add_card(bx[1], by, ws[1], bh, tf + 0.2, t2 + 0.15, dashed=True, name='placeholder')
    b2 = add_card(bx[1], by, ws[1], bh, t2, end, name='box2')
    add_lines(['Взнос', 'за 1' + NB + 'м²'], 'M', 56, bx[1] + ws[1] / 2, by + 84, 70, t2 + 0.05, end, INK, align='c', inside=b2)
    add_text('=', 'R', 84, bx[1] + ws[1] + op / 2, by + bh / 2 + 28, tf + 0.25, end, NAVY, 'c')
    b3 = add_card(bx[2], by, ws[2], bh, tf + 0.3, end, fill=NAVY, name='box3')
    add_lines(['Единовременный', 'взнос'], 'D', 56, bx[2] + ws[2] / 2, by + 84, 70, tf + 0.35, end, WHITE, align='c', inside=b3)
    ribbon(L, R, 650, 44, c2 + 0.6, c3 + 0.7, end, tail_w=723, lab_six='6 платежей, по одному в месяц',
           lab_tail='без начислений по взносу', lab_y=764)


def sc_v08():
    c1, end = cut('08'), cut('09a')
    c2 = seg_t('v08', 1) - 0.3
    kicker('Пример расчёта', c1, end)
    add_text('Средняя площадь квартиры в доме', 'M', 60, L, 330, c1 + 0.05, c2, INK)
    tb = word_t('v08', 0, 'около') - 0.25
    approx = Text('≈ ', 'B', 210, L, 540, NAVY)
    num = Text('41' + NB + 'м²', 'B', 210, L + approx.width, 540, NAVY)
    ELS.append(El(lambda ctx, t, a, dy: approx.draw(ctx, a, 0, dy), tb, c2, 0.5, 0.3, 26, box=approx.bbox(), name='approx'))
    shift = approx.width

    def dnum(ctx, t, a, dy):
        k = ease_io((t - c2) / 0.6)
        num.draw(ctx, a, -shift * k, dy)
    ELS.append(El(dnum, tb + 0.05, end, 0.5, 0.3, 26, box=num.bbox(), name='41'))
    nb = num.bbox()

    def dbar(ctx, t, a, dy):
        k = ease_out((t - (c2 + 0.45)) / 0.6)
        if k <= 0: return
        rrect(ctx, nb[0] - shift, nb[3] + 26 + dy, (nb[2] - nb[0]) * k, 10, 5); ctx.set_source_rgba(*CYAN, a); ctx.fill()
    ELS.append(El(dbar, c2, end, 0.3, 0.3, 0, box=(nb[0] - shift, nb[3] + 26, nb[2] - shift, nb[3] + 36), name='bar41'))
    src = 'По электронному паспорту дома: 61' + NB + '641,3' + NB + 'м² ÷ 1' + NB + '510 квартир = 40,82' + NB + 'м²'
    add_lines(wrap(src, 'R', 56, R - L), 'R', 56, L, 680, 74, tb + 0.4, end, MUTED)
    add_text('Эту площадь возьмём для примера', 'M', 60, L, 330, c2, end, INK)


QS = ['8', '10', '11', '12']


def nav_chips(cur, t_in, t_out):
    cs, gap = 96, 16; x0 = R - 4 * cs - 3 * gap; y = KY - 70
    for i, n in enumerate(QS):
        x = x0 + i * (cs + gap); on = n == cur
        def d(ctx, t, a, dy, x=x, on=on):
            rrect(ctx, x, y + dy, cs, cs, 20)
            if on: ctx.set_source_rgba(*NAVY, a); ctx.fill()
            else: ctx.set_source_rgba(*NAVY, a * 0.45); ctx.set_line_width(3); ctx.stroke()
        ELS.append(El(d, t_in, t_out, 0.4, 0.3, 0, box=(x, y, x + cs, y + cs), kind='card', name='nav'))
        add_text(n, 'B', 40, x + cs / 2, y + cs / 2 + 14, t_in, t_out, WHITE if on else NAVY, 'c', rise=0,
                 inside=(x, y, x + cs, y + cs))
    return x0, y, cs, gap


def q_card(a, b, nxt, f, q, ttl, scope, monthly, rate, total, t_month, t_six):
    c1, c2, end = cut(a), cut(b), cut(nxt)
    kicker('Вопрос ' + q + ' · квартира 41' + NB + 'м²', c1, end)
    nav_chips(q, c1, end)
    bx, by, bs = L, 250, 180

    def dchip(ctx, t, a_, dy):   # the big chip settles in place; the nav row marks the same question
        k = ease_out((t - c1 - 0.15) / 0.5); s_ = bs * (0.8 + 0.2 * k)
        x, y = bx + (bs - s_) / 2, by + (bs - s_) / 2 + dy
        rrect(ctx, x, y, s_, s_, 32 * s_ / bs); ctx.set_source_rgba(*NAVY, a_); ctx.fill()
        Text(q, 'B', 104, bx + bs / 2, by + bs / 2 + 37, WHITE, 'c').draw(ctx, a_, 0, dy, scale=s_ / bs, ox=bx + bs / 2, oy=by + bs / 2)
    ELS.append(El(dchip, c1 + 0.15, end, 0.4, 0.3, 0, box=(bx, by, bx + bs, by + bs), kind='card', name='bigchip'))
    tx = bx + bs + 48
    add_text(ttl, 'B', 88, tx, 330, c1 + 0.3, end, NAVY, name='qtitle')
    add_text(scope, 'R', 56, tx, 410, c1 + 0.6, end, MUTED)
    cx0, cy0, cw, ch = L, 470, R - L, 320
    card = add_card(cx0, cy0, cw, ch, c2, end, name='price')
    p0 = cx0 + 56
    big = add_text(monthly + NB + '₽', 'B', 140, p0, cy0 + 150, t_month, end, NAVY, inside=card)
    six_payments(p0, cy0 + 186, p0 + 760, 40, t_six, end)
    add_text('в месяц · 6 платежей', 'R', 56, p0, cy0 + 290, t_six + 0.2, end, MUTED, inside=card)
    rx = cx0 + 900
    tr = t_month + 0.7
    add_text('Взнос за 1' + NB + 'м²', 'R', 56, rx, cy0 + 66, tr, end, MUTED, inside=card)
    add_text(rate + NB + '₽', 'D', 56, rx, cy0 + 132, tr + 0.06, end, NAVY, inside=card)
    add_text('Единовременный взнос', 'R', 56, rx, cy0 + 206, tr + 0.25, end, MUTED, inside=card)
    add_text(total + NB + '₽', 'D', 56, rx, cy0 + 276, tr + 0.31, end, NAVY, inside=card)


def sc_cards():
    q_card('09a', '09b', '10a', 'v09', '8', 'Холодное водоснабжение', 'Стояки, трубы в подвале, элементы подпитки',
           '580,42', '84,94', '3' + NB + '482,54', word_t('v09', 5, 'пятьсот') - 0.25, word_t('v09', 5, 'в течение') - 0.2)
    q_card('10a', '10b', '11a', 'v10', '10', 'Холлы и чёрные лестницы', 'Косметический ремонт там, где он необходим',
           '751,39', '109,96', '4' + NB + '508,36', word_t('v10', 2, 'семьсот') - 0.25, word_t('v10', 2, 'на полгода') - 0.2)
    q_card('11a', '11b', '12a', 'v11', '11', 'Детские площадки', 'Замена оборудования и покрытия',
           '1' + NB + '415,46', '207,14', '8' + NB + '492,74', word_t('v11', 1, 'тысячу') - 0.25, word_t('v11', 1, 'в течение') - 0.2)
    q_card('12a', '12b', '13', 'v12', '12', 'Спортивная площадка', 'Замена оборудования и покрытия',
           '256,39', '37,52', '1' + NB + '538,32', seg_t('v12', 3) + 1.0, seg_t('v12', 4) - 0.2)


def sc_v13():
    c1, end = cut('13'), cut('14')
    kicker('Если собрание утвердит все четыре взноса', c1, end)
    title('Платёж для квартиры 41' + NB + 'м²', c1 + 0.08, end)
    gap = 48; w = (R - L - 3 * gap) / 4; y, h = 350, 160
    vals = ['580,42', '751,39', '1' + NB + '415,46', '256,39']
    for i, (qq, v) in enumerate(zip(QS, vals)):
        x = L + i * (w + gap); ti = c1 + 0.5 + 0.3 * i
        cd = add_card(x, y, w, h, ti, end, name='sum-tile')
        add_text('Вопрос ' + qq, 'R', 56, x + 28, y + 62, ti + 0.05, end, MUTED, inside=cd)
        add_text(v + NB + '₽', 'D', 60, x + 28, y + 136, ti + 0.08, end, NAVY, inside=cd)
        if i: add_text('+', 'D', 64, x - gap / 2, y + 104, ti, end, NAVY, 'c')
    tt = seg_t('v13', 1) - 0.25
    big = add_text('= 3' + NB + '003,66' + NB + '₽', 'B', 140, L, 648, tt, end, NAVY)
    add_text('в месяц', 'D', 64, big.x + big.width + 28, 648, tt + 0.1, end, NAVY)
    ribbon(L, R, 682, 32, tt + 0.6, tt + 1.4, end, tail_w=600, lab_six='6 платежей', lab_tail='дальше начислений по взносам нет',
           lab_y=774)


def sc_v14():
    c1, end = cut('14'), cut('17a')
    kicker('Свой расчёт', c1, end)
    title('Свой платёж в месяц', c1 + 0.08, end)
    tf = word_t('v14', 0, 'умножьте') - 0.25
    add_text('Общая площадь × 73,26' + NB + '₽', 'B', 110, L, 490, tf, end, NAVY)
    add_text('= платёж в месяц по всем четырём вопросам', 'M', 60, L, 580, tf + 0.4, end, INK)
    add_text('Без учёта распределителей тепла (вопросы 3 и 4)', 'R', 56, L, 700, tf + 1.2, end, MUTED)
    add_text('В квитанции возможна разница в копейках', 'R', 56, L, 772, tf + 1.4, end, MUTED)


def sc_v16():
    c1, c2, c3, end = cut('16a'), cut('16b'), cut('16c'), cut('18a')
    kicker('Почему важен каждый голос', c1, end)
    title('Нужно больше половины голосов', c1 + 0.08, end)
    bx0, bx1, by, bh = L, R, 440, 56; mid = (bx0 + bx1) / 2

    def dbar(ctx, t, a, dy):   # no running fill: the scale must not look like a live count
        rrect(ctx, bx0, by + dy, bx1 - bx0, bh, 14); ctx.set_source_rgba(*LIGHT, a); ctx.fill()
        rrect(ctx, mid, by + dy, bx1 - mid, bh, 14); ctx.set_source_rgba(*RULE, a * 0.55); ctx.fill()
        rrect(ctx, mid - 3, by - 22 + dy, 6, bh + 44, 3); ctx.set_source_rgba(*NAVY, a); ctx.fill()
    ELS.append(El(dbar, c1 + 0.2, end, 0.5, 0.3, 0, box=(bx0, by - 22, bx1, by + bh + 22), kind='deco', name='quorum'))
    add_text('50' + NB + '%', 'D', 56, mid, 400, c1 + 0.3, end, NAVY, 'c')
    t_m = word_t('v16', 0, 'больше половины') + 0.6
    for i, (v, lab) in enumerate([(0.2441, '24,41'), (0.4103, '41,03')]):
        x = bx0 + (bx1 - bx0) * v; ti = t_m + 0.35 * i

        def dm(ctx, t, a, dy, x=x):
            rrect(ctx, x - 6, by - 14 + dy, 12, bh + 28, 6); ctx.set_source_rgba(*CYAN, a); ctx.fill()
        ELS.append(El(dm, ti, end, 0.4, 0.3, 0, box=(x - 6, by - 14, x + 6, by + bh + 14), kind='deco', name='mark'))
        add_text(lab + NB + '%', 'D', 56, x, by + bh + 82, ti + 0.05, end, NAVY, 'c')
    add_text('Прошлые собрания: кворума не было', 'M', 56, L, 652, t_m + 0.5, end, NAVY)
    add_text('Голоса считаются по площади помещений', 'R', 56, L, 750, seg_t('v16', 1) - 0.25, c2, MUTED)
    add_text('Без кворума взносы не утвердить', 'D', 64, L, 752, c2 + 0.6, c3, NAVY)
    add_text('Важен бюллетень каждого собственника', 'D', 64, L, 752, c3 + 0.6, end, NAVY)


def sc_v17():
    c1, c2, c3, end = cut('17a'), cut('17b'), cut('17c'), cut('16a')   # the deadlines come before the quorum
    kicker('Голосование закончится', c1, end)
    title('31' + NB + 'января 2027, 18:00', word_t('v17', 0, 'тридцать первого') - 0.25, end)
    t1 = word_t('v17', 1, 'в ящик') - 0.25
    add_icon('box', L, 378, 64, t1, end)
    add_text('Ящик для показаний счётчиков', 'M', 60, L + 100, 430, t1 + 0.05, end, INK)
    add_text('на 1-м этаже каждой парадной', 'R', 56, L + 100, 500, t1 + 0.12, end, MUTED)
    t2 = word_t('v17', 1, 'или сдать') - 0.25
    add_icon('pin', L, 548, 64, t2, end)
    add_text('Офис УК — с торца 3-й парадной', 'M', 60, L + 100, 600, t2 + 0.05, end, INK)
    add_text('по будням, 9:00–18:00', 'R', 56, L + 100, 670, seg_t('v17', 2) - 0.25, end, MUTED)
    navy_chip('В офис — до 18:00 пятницы, 29' + NB + 'января', L, 698, word_t('v17', 4, 'поэтому') - 0.2, end, size=56, h=88)


def sc_v18():
    c1, c2, c4 = cut('18a'), cut('18b'), cut('18d')
    kicker('Если решения будут приняты', c1, c4)
    title('Работы в доме и во дворе', c1 + 0.08, c4)
    tw_, gap, TH, y = 380, (R - L - 4 * 380) / 3, 250, 360
    for i, wd in ((0, ('v18', 0, 'стояки')), (1, ('v18', 1, 'холлы')), (2, ('v18', 1, 'новое покрытие')), (3, ('v18', 1, 'на площадках'))):
        x = L + i * (tw_ + gap); ti = word_t(*wd) - 0.25
        def d(ctx, t, a, dy, x=x, i=i):
            rrect(ctx, x, y + dy, tw_, TH, 28); ctx.set_source_rgba(*LIGHT, a); ctx.fill()
            draw_img(ctx, TILES[i], fit(TILES[i], (x + 18, y + 14 + dy, tw_ - 36, TH - 28)), a)
        ELS.append(El(d, ti, c4, 0.55, 0.3, 26, box=(x, y, x + tw_, y + TH), kind='card', name='tile18'))
    ribbon(L, R, 660, 40, c2 + 0.5, word_t('v18', 2, 'после чего') - 0.1, c4, tail_w=600, lab_six='6 платежей',
           lab_tail='дальше начислений по взносам нет', lab_y=770)
    logo = ASSETS + 'petersburg_dom_transparent.png'
    rect = fit(logo, (L, 120, R - L, 330))

    def dlogo(ctx, t, a, dy):
        k = ease_out((t - c4) / 1.0); sc = 0.97 + 0.03 * k
        x, y_, w, h = rect; cx, cy = x + w / 2, y_ + h / 2
        draw_img(ctx, logo, (cx - w * sc / 2, cy - h * sc / 2, w * sc, h * sc), a, ref=rect)
    ELS.append(El(dlogo, c4 + 0.1, TOTAL + 1, 0.8, 0.2, 0, box=(rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]), name='logo-end'))
    add_text('Примите разумное решение — проголосуйте', 'D', 68, 960, 610, seg_t('v18', 5) - 0.1, TOTAL + 1, NAVY, 'c')
    add_text('Голосование до 31' + NB + 'января 2027, 18:00', 'M', 60, 960, 710, seg_t('v18', 6) + 0.2, TOTAL + 1, MUTED, 'c')


FOCUS = {1: (0.5, 0.6), 20: (0.5, 0.55, 1.2), 26: (0.5, 0.42), 10: (0.5, 0.62)}
THUMB = {1: (0.5, 0.6), 20: (0.42, 0.5), 26: (0.5, 0.45), 10: (0.5, 0.6)}


def build():
    ELS.clear()
    for f in (sc_logo, sc_01, sc_v02, sc_v03, sc_v04, sc_v05, sc_v06, sc_v07, sc_v08, sc_cards, sc_v13, sc_v14, sc_v17,
              sc_v16, sc_v18):
        f()


# ---------------------------------------------------------------- subtitles
def cues():
    out = []
    for f in sorted(SUBS):
        for k in sorted(SUBS[f]):
            if f not in SEGS or k >= len(SEGS[f]) or not _item_for(f, k):
                continue   # line not in the current cut (e.g. the optional block before its voice is recorded)
            pieces = SUBS[f][k]; a, b = SEGS[f][k]; sp = SPOKEN[f][k]
            pos = 0
            for txt, spk in pieces:
                if spk is None:
                    s0, s1 = 0, 1
                else:
                    i = sp.index(spk, pos); pos = i + len(spk)
                    s0, s1 = nv(sp[:i]) / nv(sp), nv(sp[:i + len(spk)]) / nv(sp)
                t0 = seg_t(f, k) + s0 * (b - a); t1 = seg_t(f, k) + s1 * (b - a)
                out.append([t0, t1, txt, ITEMS[_item_for(f, k)['name']]['name']])
    out.sort(key=lambda c: c[0])   # lines recorded later (e.g. 14) must sit in time order
    def split(c):   # long lines: split at the punctuation (or space) nearest the middle, time by length
        txt = c[2]
        if len(txt) <= 84: return [c]
        cuts = [m.end() for m in re.finditer(r'[,:—] ', txt)]
        if not cuts or min(abs(i - len(txt) / 2) for i in cuts) > len(txt) / 4:
            cuts += [m.end() for m in re.finditer(r' ', txt)]
        k = min(cuts, key=lambda i: abs(i - len(txt) / 2))
        a, b = txt[:k].strip(), txt[k:].strip()
        tm = c[0] + (c[1] - c[0]) * len(a) / (len(a) + len(b))
        return split([c[0], tm, a, c[3]]) + split([tm, c[1], b, c[3]])
    out = [p for c in out for p in split(c)]
    # merge short neighbours within one screen state
    m = []
    for c in out:
        if m and c[3] == m[-1][3] and not m[-1][2].endswith('.') and c[0] - m[-1][1] < 0.45 and len(m[-1][2]) + len(c[2]) <= 84 and c[1] - m[-1][0] <= 7.5:
            m[-1] = [m[-1][0], c[1], m[-1][2] + ' ' + c[2], c[3]]
        else:
            m.append(list(c))
    res = []
    for i, c in enumerate(m):
        s = c[0] - 0.1; e = c[1] + 0.3
        if i + 1 < len(m):
            nxt = m[i + 1][0] - 0.1
            e = nxt - 0.04 if nxt - e < 0.5 else min(e, nxt - 0.04)
        res.append((s, max(e, s + 1.0), c[2]))
    return res


ADJ = ('ая', 'яя', 'ую', 'юю', 'ой', 'ей', 'ых', 'их', 'ым', 'им', 'ое', 'ее', 'ий', 'ый', 'ого', 'его', 'ому', 'ему', 'ыми', 'ими')


def sub_lines(txt, maxw=1480):
    if tw(txt, 'M', 56) <= maxw: return [txt]
    words = txt.split(' '); best = None
    for i in range(1, len(words)):
        a, b = ' '.join(words[:i]), ' '.join(words[i:])
        if words[i - 1].lower() in PREP or words[i] == '—': continue
        wa, wb = tw(a, 'M', 56), tw(b, 'M', 56)
        if max(wa, wb) > maxw: continue
        adj = words[i - 1].lower().endswith(ADJ)   # keep adjective + noun together
        sc = abs(wa - wb) - (420 if a.endswith((',', ':', '—', '.')) else 0) + (500 if adj else 0) + (0 if min(wa, wb) >= max(wa, wb) * 0.35 else 600)
        if best is None or sc < best[0]: best = (sc, [a, b])
    if best is None:   # no balanced split: greedy
        out, cur = [], ''
        for w_ in words:
            if cur and tw(cur + ' ' + w_, 'M', 56) > maxw: out.append(cur); cur = w_
            else: cur = (cur + ' ' + w_).strip()
        return out + [cur]
    return best[1]


CUES = None


def draw_subs(ctx, t):
    for s, e, txt in CUES:
        if s <= t < e:
            a = min(1, (t - s) / 0.12, (e - t) / 0.12)
            lines = sub_lines(txt)
            lh = 70; w = max(tw(x, 'M', 56) for x in lines) + 64; h = lh * len(lines) + 30
            x = (W - w) / 2; y = 1036 - h
            rrect(ctx, x, y, w, h, 16); ctx.set_source_rgba(*NAVY, 0.9 * a); ctx.fill()
            for i, ln in enumerate(lines):
                Text(ln, 'M', 56, W / 2, y + 15 + 52 + i * lh, WHITE, 'c').draw(ctx, a)


def srt():
    def ts(x):
        ms = int(round(x * 1000)); return '%02d:%02d:%02d,%03d' % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)
    o = []
    for i, (s, e, txt) in enumerate(CUES, 1):
        o.append('%d\n%s --> %s\n%s\n' % (i, ts(s), ts(e), '\n'.join(sub_lines(txt)).replace(NB, ' ')))
    return '\n'.join(o)


# ---------------------------------------------------------------- frame
def frame(t, subs=False, surf=None):
    surf = surf or cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    ctx.set_source_rgb(1, 1, 1); ctx.paint()
    for e in ELS:
        dim = getattr(e, 'dim', None)
        if dim:
            k = ease_io((t - dim[0]) / 0.5)
            ctx.push_group(); e.draw(ctx, t); ctx.pop_group_to_source(); ctx.paint_with_alpha(1 - (1 - dim[1]) * k)
        else:
            e.draw(ctx, t)
    if subs: draw_subs(ctx, t)
    return surf


def save_png(surf, path):
    a = np.ndarray((H, W, 4), np.uint8, surf.get_data())
    Image.fromarray(a[..., [2, 1, 0]].copy()).save(path)


def main():
    global CUES
    build(); CUES = cues()
    mode = sys.argv[1]
    import os; os.makedirs(OUT, exist_ok=True)
    if mode == 'stills':
        for tt in sys.argv[2:]:
            t = float(tt); s = frame(t, subs=False); save_png(s, WORK + 'st_%07.2f.png' % t)
    elif mode == 'video':
        n = int(round(TOTAL * FPS))
        enc = lambda p: subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', '%dx%d' % (W, H),
            '-r', str(FPS), '-i', '-', '-i', WORK + 'mix.wav', '-map', '0:v', '-map', '1:a',
            '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
            '-tune', 'animation', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
            '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', '-t', '%.3f' % (n / FPS), p], stdin=subprocess.PIPE)
        p1 = enc(OUT + 'celevye_vznosy_v9.mp4'); p2 = None
        stats = []
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        prev = None
        for i in range(n):
            t = i / FPS
            frame(t, False, s); s.flush(); p1.stdin.write(bytes(s.get_data()))
            a = np.ndarray((H, W, 4), np.uint8, s.get_data())[::8, ::8, :3].astype(np.int16)
            stats.append((t, float(a.mean()), float(np.abs(a - prev).mean()) if prev is not None else 0.0)); prev = a
            if i % 500 == 0: print('frame', i, '/', n, flush=True)
        p1.stdin.close(); p1.wait()
        json.dump(stats, open(WORK + 'framestats.json', 'w'))
        open(OUT + 'celevye_vznosy_v9.srt', 'w', encoding='utf-8').write(srt())
    elif mode == 'srt':   # subtitles only (they are not burned into the video)
        open(OUT + 'celevye_vznosy_v9.srt', 'w', encoding='utf-8').write(srt())
    elif mode == 'check':
        check()


def check():
    """overlaps, margins, subtitle band, text inside cards, at every rest moment"""
    probs = []
    cuts = sorted(set([d['cut'] for d in TL['timeline']] + [TOTAL]))
    moments = []
    for i in range(len(cuts) - 1):
        moments += [cuts[i + 1] - 0.35]
    for d in TL['timeline']:
        if 't1' in d: moments.append(d['t1'])
    for t in sorted(moments):
        vis = [e for e in ELS if e.t_in + e.din <= t < e.t_out - e.dout]
        for e in vis:
            x0, y0, x1, y1 = e.box_at(t)
            if x0 < L - 40 or x1 > R + 1 or y1 > SAFE_BOTTOM or y0 < 60:
                probs.append('%.2f margin %s %s' % (t, e.name, [round(v) for v in e.box]))
            if e.inside:
                cx0, cy0, cx1, cy1 = e.inside
                if x0 < cx0 + 20 or x1 > cx1 - 20 or y0 < cy0 + 12 or y1 > cy1 - 12:
                    probs.append('%.2f outside-card %s' % (t, e.name))
        cards = [e for e in vis if e.kind == 'card']
        for e in vis:
            if e.kind != 'content': continue
            for c in cards:
                a, b = e.box_at(t), c.box_at(t)
                ins = e.inside and abs(e.inside[0] - b[0]) < 1 and abs(e.inside[1] - b[1]) < 1
                if not ins and a[0] < b[2] - 2 and b[0] < a[2] - 2 and a[1] < b[3] - 2 and b[1] < a[3] - 2:
                    probs.append('%.2f text-over-card %s | %s' % (t, e.name, c.name))
        tx = [e for e in vis if e.kind == 'content']
        for i in range(len(tx)):
            for j in range(i + 1, len(tx)):
                a, b = tx[i].box_at(t), tx[j].box_at(t)
                if a[0] < b[2] - 2 and b[0] < a[2] - 2 and a[1] < b[3] - 2 and b[1] < a[3] - 2:
                    probs.append('%.2f overlap %s | %s' % (t, tx[i].name, tx[j].name))
                elif a[0] < b[2] and b[0] < a[2] and min(abs(a[1] - b[3]), abs(b[1] - a[3])) < AIR:
                    probs.append('%.2f tight %s | %s' % (t, tx[i].name, tx[j].name))   # elements almost touching
    print('\n'.join(sorted(set(probs))) or 'layout OK')
    for s, e, txt in CUES:
        if len(sub_lines(txt)) > 2: print('sub >2 lines', txt)
    print('cues', len(CUES))


if __name__ == '__main__':
    main()
