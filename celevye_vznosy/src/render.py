"""Frame renderer: pycairo shapes/compositing, PIL+raqm text, Golos Text. Usage:
   render.py stills t1 t2 ...   -> PNG stills
   render.py video               -> clean + subtitled MP4, SRT
   render.py check               -> layout checks at rest moments"""
import sys, json, math, subprocess, re
import numpy as np, cairo
from PIL import Image, ImageFont, ImageDraw
from content import SPOKEN, SUBS, N as NB

WD = '/tmp/claude-0/-home-user-ishodniki-video/7fdd3399-3b0b-583b-a74f-2847502fb422/scratchpad/'
WORK = WD + 'work/'; ASSETS = WD + 'in_vis/inner/assets/'; FONTD = WD + 'in_font/'
OUT = WD + 'out/'
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


PREP = set('в во на и а о об с со по из для к у не за от до без при что как но или же — его её их'.split())


def wrap(txt, w, s, maxw):
    """fewest lines that fit, then the most even split; never end a line on a preposition"""
    words = txt.split(' ')
    def ok_break(i): return words[i - 1].lower() not in PREP
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


def caption_ill(x_right, y, t_in, t_out):
    return add_text('Условная иллюстрация', 'R', 56, x_right, y, t_in, t_out, MUTED, align='r', name='caption')


# ================================================================ scenes
def sc_logo():
    t0, t1 = cut('logo'), cut('01rad')
    logo = WD + 'in_vis/inner/assets/petersburg_dom_transparent.png'
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


def sc_01():
    c1, c2, end = cut('01rad'), cut('01main'), cut('02q')
    kicker('В прошлом видео', c1, c2)
    title('Распределители тепла', c1 + 0.08, c2)
    card0 = (720, 330, 1050, 460)
    tw_, gap = 380, (R - L - 4 * 380) / 3
    TH = 270
    tiles = [(L + i * (tw_ + gap), 520, tw_, TH) for i in range(4)]
    rim = load_img(RAD, crop=False)
    # radiator photo in a rounded card, then the card becomes the first work tile
    def morph(ctx, t, a, dy):
        k = ease_io((t - (c2 - 0.15)) / 0.75)
        x = lerp(card0[0], tiles[0][0], k); y = lerp(card0[1], tiles[0][1], k) + dy
        w = lerp(card0[2], tiles[0][2], k); h = lerp(card0[3], tiles[0][3], k)
        ctx.save(); rrect(ctx, x, y, w, h, 28); ctx.clip()
        ctx.set_source_rgba(*LIGHT, a); ctx.paint()
        if k < 1:   # cover-fit photo, anchored on the radiator (right part)
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
        ELS.append(El(d, c2 + 0.25 + 0.1 * i, end, 0.55, 0.3, 26, box=(x, y, x + w, y + h), kind='card', name='tile'))
    kicker('Ещё одна часть повестки', c2, end)
    t_title = seg_t('01', 2) - 1.2
    title('Целевые взносы', t_title, end)
    add_text('на работы в доме и во дворе', 'M', 60, L, TY + 82, t_title + 0.1, end, NAVY)
    add_text('Что предлагается и сколько составит взнос', 'R', 60, L, TY + 162, seg_t('01', 3) - 0.25, end, INK)


def sc_02():
    c1, c2, end = cut('02q'), cut('02f'), cut('03a')
    kicker('Предложения к голосованию', c1, c2)
    row_y = 250; cs = 150
    t = add_text('Вопросы', 'B', 88, L, row_y + cs / 2 + 31, seg_t('02', 0) - 0.3, c2, NAVY)
    x = L + t.width + 44
    words = ['восемь', 'десять', 'одиннадцать', 'двенадцать']
    for i, (num, wd) in enumerate(zip(['8', '10', '11', '12'], words)):
        xx = x + i * (cs + 24); ti = word_t('02', 0, wd) - 0.2
        def d(ctx, tt, a, dy, xx=xx):
            rrect(ctx, xx, row_y + dy, cs, cs, 26); ctx.set_source_rgba(*NAVY, a); ctx.fill()
        ELS.append(El(d, ti, c2, 0.45, 0.3, 22, box=(xx, row_y, xx + cs, row_y + cs), kind='card', name='chip'))
        add_text(num, 'B', 84, xx + cs / 2, row_y + cs / 2 + 30, ti, c2, WHITE, 'c', inside=(xx, row_y, xx + cs, row_y + cs))
    add_text('Отдельные разовые взносы', 'D', 72, L, 530, word_t('02', 0, 'предусматривают') - 0.2, c2, NAVY)
    add_text('По каждому вопросу собственники голосуют отдельно', 'R', 56, L, 620, seg_t('02', 1) - 0.25, c2, INK)
    # formula
    kicker('Как рассчитывается взнос', c2, end)
    bw, bh, by = 500, 230, 270
    op = (R - L - 3 * bw) / 2
    bx = [L, L + bw + op, L + 2 * (bw + op)]
    t_f = c2 + 0.05
    b1 = add_card(bx[0], by, bw, bh, t_f, end, name='box1')
    add_lines(['Общая площадь', 'помещения'], 'M', 56, bx[0] + bw / 2, by + 102, 74, t_f + 0.05, end, INK, align='c', inside=b1)
    add_text('×', 'R', 84, bx[0] + bw + op / 2, by + bh / 2 + 28, t_f + 0.15, end, NAVY, 'c')
    add_card(bx[1], by, bw, bh, t_f + 0.2, word_t('02', 3, 'ставку') - 0.1, dashed=True, name='placeholder')
    t2 = word_t('02', 3, 'ставку') - 0.25
    b2 = add_card(bx[1], by, bw, bh, t2, end, name='box2')
    add_lines(['Ставка', 'из бюллетеня'], 'M', 56, bx[1] + bw / 2, by + 102, 74, t2 + 0.05, end, INK, align='c', inside=b2)
    add_text('=', 'R', 84, bx[1] + bw + op / 2, by + bh / 2 + 28, t_f + 0.25, end, NAVY, 'c')
    b3 = add_card(bx[2], by, bw, bh, t_f + 0.3, end, fill=NAVY, name='box3')
    add_text('Взнос', 'D', 72, bx[2] + bw / 2, by + bh / 2 + 25, t_f + 0.35, end, WHITE, 'c', inside=b3)
    t4 = seg_t('02', 4) - 0.25
    add_lines(wrap('Решение о работах и их финансировании принимается на собрании', 'M', 60, R - L), 'M', 60, L, 640, 80, t4, end, NAVY)


def sc_03():
    c1, c2, end = cut('03a'), cut('03b'), cut('04a')
    kicker('Пример расчёта', c1, end)
    add_text('Средняя площадь квартиры в доме', 'M', 60, L, 330, c1 + 0.05, c2, INK)
    tb = seg_t('03', 1) - 0.25
    approx = Text('≈ ', 'B', 210, L, 540, NAVY)
    num = Text('41' + NB + 'м²', 'B', 210, L + approx.width, 540, NAVY)
    ELS.append(El(lambda ctx, t, a, dy: approx.draw(ctx, a, 0, dy), tb, c2, 0.5, 0.3, 26, box=approx.bbox(), name='approx'))
    shift = approx.width

    def dnum(ctx, t, a, dy):
        k = ease_io((t - c2) / 0.6)
        num.draw(ctx, a, -shift * k, dy)
    ELS.append(El(dnum, tb + 0.05, end, 0.5, 0.3, 26, box=num.bbox(), name='41'))
    accent = lambda: None
    nb = num.bbox()

    def dbar(ctx, t, a, dy):
        k = ease_out((t - (c2 + 0.45)) / 0.6)
        if k <= 0: return
        rrect(ctx, nb[0] - shift, nb[3] + 26 + dy, (nb[2] - nb[0]) * k, 10, 5); ctx.set_source_rgba(*CYAN, a); ctx.fill()
    ELS.append(El(dbar, c2, end, 0.3, 0.3, 0, box=(nb[0] - shift, nb[3] + 26, nb[2] - shift, nb[3] + 36), name='bar41'))
    src = 'По электронному паспорту дома: 61' + NB + '641,3' + NB + 'м² ÷ 1' + NB + '510 квартир = 40,82' + NB + 'м²'
    add_lines(wrap(src, 'R', 56, R - L), 'R', 56, L, 680, 74, seg_t('03', 0) - 0.2, c2, MUTED)
    add_text('Эту площадь возьмём для примера', 'M', 60, L, 330, c2, end, INK)
    add_text('Для расчёта подставьте общую площадь своей квартиры', 'M', 56, L, 680, seg_t('03', 3) - 0.25, end, INK)
    add_text('Если она отличается, изменится и сумма', 'R', 56, L, 752, seg_t('03', 5) - 0.25, end, MUTED)


def money_scene(f, a, b, nxt, q, ttl, t_ttl, label, items, qual, img, rate, total):
    c1, c2, end = cut(a), cut(b), cut(nxt)
    kicker('Вопрос ' + q + ' · разовый взнос', c1, end)
    title(ttl, c1 + 0.08, end)
    boxA = fit(img, (1060, 340, 710, 360)); boxB = fit(img, (1150, 350, 620, 280))

    def dimg(ctx, t, a_, dy):
        k = ease_io((t - (c2 - 0.2)) / 0.7)
        r = tuple(lerp(boxA[i], boxB[i], k) for i in range(4))
        draw_img(ctx, img, (r[0], r[1] + dy, r[2], r[3]), a_, ref=boxA)
    e = El(dimg, c1 + 0.1, end, 0.6, 0.3, 26, box=(boxA[0], boxA[1], boxA[0] + boxA[2], boxA[1] + boxA[3]), name='ill', kind='card')
    e.boxes = [(0, c2 - 0.2, e.box), (c2 - 0.2, 1e9, (boxB[0], boxB[1], boxB[0] + boxB[2], boxB[1] + boxB[3]))]; ELS.append(e)
    CAP = 32   # disclaimer under illustrations: small, unobtrusive
    cw_ = tw('Условная иллюстрация', 'R', CAP)
    cxA = min(boxA[0] + boxA[2] / 2, R - cw_ / 2); cxB = min(boxB[0] + boxB[2] / 2, R - cw_ / 2)
    capA = Text('Условная иллюстрация', 'R', CAP, cxA, boxA[1] + boxA[3] + 40, MUTED, 'c')
    capB_y = boxB[1] + boxB[3] + 40

    def dcap(ctx, t, a_, dy):
        k = ease_io((t - (c2 - 0.2)) / 0.7)
        capA.draw(ctx, a_, (cxB - cxA) * k, dy + (capB_y - capA.y) * k)
    e = El(dcap, c1 + 0.3, end, 0.5, 0.3, 22, box=capA.bbox(), name='caption')
    bA = capA.bbox(); dxB, dyB = cxB - cxA, capB_y - capA.y
    e.boxes = [(0, c2 - 0.2, bA), (c2 - 0.2, 1e9, (bA[0] + dxB, bA[1] + dyB, bA[2] + dxB, bA[3] + dyB))]
    ELS.append(e)
    # state A: what is replaced
    y = 410
    if label:
        add_text(label[0], 'R', 56, L, y, label[1] - 0.2, c2, MUTED); y += 80
    for txt, ti in items:
        bullet_item(txt, L, y, ti - 0.2, c2); y += 76
    if qual:
        lines = wrap(qual[0], 'R', 56, 840)
        add_lines(lines, 'R', 56, L, y + 22, 72, qual[1] - 0.2, c2, MUTED)
    # state B: calculation card
    cx0, cy0, cw, ch = L, 340, 920, 440
    card = add_card(cx0, cy0, cw, ch, c2, end, name='calc')
    add_text('Ставка', 'R', 56, cx0 + 52, cy0 + 95, c2 + 0.08, end, MUTED, inside=card)
    add_text(rate + NB + '₽ за' + NB + 'м²', 'D', 72, cx0 + cw - 52, cy0 + 95, c2 + 0.12, end, NAVY, 'r', inside=card)

    def drule(ctx, t, a_, dy):
        rrect(ctx, cx0 + 52, cy0 + 140 + dy, cw - 104, 3, 1.5); ctx.set_source_rgba(*RULE, a_); ctx.fill()
    ELS.append(El(drule, c2 + 0.15, end, 0.5, 0.3, 10, box=(cx0 + 52, cy0 + 140, cx0 + cw - 52, cy0 + 143), name='rule', kind='deco'))
    t_sum = seg_t(f, max(k for k in SUBS[f] if SUBS[f][k][0][0].startswith('Для квартиры'))) - 0.25
    lab = add_text('Взнос для квартиры 41' + NB + 'м²', 'R', 56, cx0 + 52, cy0 + 228, t_sum, end, MUTED, inside=card)
    big = add_text(total + NB + '₽', 'B', 150, cx0 + 52, cy0 + 362, t_sum + 0.1, end, NAVY, inside=card)
    bb = big.bbox()
    accent_bar(bb, t_sum + 0.35, end)


def sc_04():
    f = '04'
    money_scene(f, '04a', '04b', '05a', '8', 'Холодное водоснабжение', seg_t(f, 1) - 0.25,
                ('Замена элементов системы:', seg_t(f, 1) + 1.2),
                [('стояки', seg_t(f, 2)), ('трубы в подвале', seg_t(f, 3)),
                 ('подпитка в тепловом пункте', word_t(f, 3, 'элементов подпитки'))],
                None, ASSETS + 'water.png', '84,94', '3' + NB + '482,54')


def sc_05():
    f = '05'
    money_scene(f, '05a', '05b', '06a', '10', 'Косметический ремонт', seg_t(f, 1) - 0.25, None,
                [('приквартирные холлы', word_t(f, 1, 'приквартирных')), ('лифтовые холлы', word_t(f, 1, 'лифтовых')),
                 ('чёрные лестницы', word_t(f, 1, 'а также'))],
                ('В местах, где нужен ремонт', word_t(f, 1, 'в местах')), ASSETS + 'halls.png', '109,96', '4' + NB + '508,36')


def sc_06():
    f = '06'
    money_scene(f, '06a', '06b', '07a', '11', 'Детские площадки', seg_t(f, 1) - 0.25, None,
                [('замена оборудования', seg_t(f, 1)), ('замена покрытия', word_t(f, 1, 'покрытия'))],
                None, ASSETS + 'kids.png', '207,14', '8' + NB + '492,74')


def sc_07():
    f = '07'
    money_scene(f, '07a', '07b', '08', '12', 'Спортивная площадка', seg_t(f, 1) - 0.25, None,
                [('замена оборудования', seg_t(f, 1)), ('замена покрытия', word_t(f, 1, 'покрытия'))],
                None, ASSETS + 'sport.png', '37,52', '1' + NB + '538,32')


def sc_08():
    c1, end = cut('08'), cut('09a')
    kicker('Вопросы 11 и 12 · площадки', c1, end)
    title('Отдельное условие', c1 + 0.1, end)
    t1 = seg_t('08', 1) - 0.3
    card = add_card(L, 350, R - L, 430, t1 - 0.1, end, name='cond')
    add_lines(['Если решение о финансировании', 'не будет принято,'], 'D', 64, L + 60, 440, 80, t1, end, NAVY, inside=card)

    def dr(ctx, t, a, dy):
        k = ease_out((t - (word_t('08', 1, 'аварийное') - 0.3)) / 0.6)
        rrect(ctx, L + 62, 562 + dy, 6, 180 * k, 3); ctx.set_source_rgba(*NAVY, a * 0.35); ctx.fill()
    ELS.append(El(dr, word_t('08', 1, 'аварийное') - 0.3, end, 0.3, 0.3, 0, box=(L + 62, 562, L + 68, 742), name='rule', kind='deco'))
    add_text('аварийное оборудование, подлежащее демонтажу,', 'R', 56, L + 110, 622, word_t('08', 1, 'аварийное') - 0.2, end,
             INK, inside=card)
    add_text('демонтируют без установки нового взамен', 'D', 64, L + 110, 714, word_t('08', 1, 'демонтируют') - 0.2, end,
             NAVY, inside=card)


def sc_09():
    c1, c2, end = cut('09a'), cut('09b'), cut('10a')
    has_n = '09n' in ITEMS          # optional reassurance block right after the total
    cm = cut('09n') if has_n else c2
    kicker('Если собрание примет все четыре вопроса', c1, end)
    title('Для квартиры 41' + NB + 'м²', c1 + 0.55, end)
    vals = [('8', '3' + NB + '482,54'), ('10', '4' + NB + '508,36'), ('11', '8' + NB + '492,74'), ('12', '1' + NB + '538,32')]
    gw = (R - L - 30) / 2
    for i, (q, v) in enumerate(vals):
        x = L + (i % 2) * (gw + 30); y = 370 + (i // 2) * 150
        ti = c1 + 0.8 + 0.12 * i
        cd = add_card(x, y, gw, 130, ti, cm, name='sum-tile')
        add_text('Вопрос ' + q, 'R', 56, x + 44, y + 85, ti + 0.05, cm, MUTED, inside=cd)
        add_text(v + NB + '₽', 'D', 64, x + gw - 44, y + 87, ti + 0.08, cm, NAVY, 'r', inside=cd)
    ts = word_t('09', 0, 'общая сумма') - 0.3

    def drule(ctx, t, a, dy):
        k = ease_out((t - ts) / 0.7)
        rrect(ctx, L, 668, (R - L) * k, 4, 2); ctx.set_source_rgba(*NAVY, a); ctx.fill()
    ELS.append(El(drule, ts, cm, 0.2, 0.3, 0, box=(L, 668, R, 672), name='sumrule'))
    lab = Text('Общая сумма', 'R', 56, L, 766, MUTED)
    LAB_B = 420 if has_n else 434
    big = Text('18' + NB + '021,96' + NB + '₽', 'B', 170, L, 0, NAVY)
    sA = 100 / 170
    yA, yB = 770, (578 if has_n else 594)
    xA = R - (big.bbox()[2] - L) * sA   # align the ink edge to the right margin

    def dlab(ctx, t, a, dy):
        k = ease_io((t - (cm - 0.2)) / 0.7)
        lab.draw(ctx, a, 0, dy + lerp(0, LAB_B - 766, k))
    e = El(dlab, ts + 0.1, end, 0.5, 0.3, 18, box=lab.bbox(), name='sumlabel'); lb = lab.bbox()
    e.boxes = [(0, cm - 0.2, lb), (cm - 0.2, 1e9, (lb[0], lb[1] + LAB_B - 766, lb[2], lb[3] + LAB_B - 766))]; ELS.append(e)

    def dbig(ctx, t, a, dy):
        k = ease_io((t - (cm - 0.2)) / 0.7)
        s = lerp(sA, 1, k); x = lerp(xA, L, k); y = lerp(yA, yB, k)
        ctx.save(); ctx.translate(x, y + dy); ctx.scale(s, s)
        surf, _, ox, oy, _ = tmask(big.txt, 'B', 170)
        ctx.set_source_rgba(*NAVY, a); ctx.mask_surface(surf, ox, oy); ctx.restore()
    bb = big.bbox()
    e = El(dbig, ts + 0.2, end, 0.5, 0.3, 18, box=(L, yB + bb[1], L + big.width, yB + bb[3]), name='total')
    e.boxes = [(0, cm - 0.2, (xA + (bb[0] - L) * sA, yA + bb[1] * sA, xA + (bb[2] - L) * sA, yA + bb[3] * sA)), (cm - 0.2, 1e9, e.box)]
    ELS.append(e)
    accent_bar((L, yB + bb[1], L + big.width, yB + bb[3]), cm + 0.5, end)
    ny = 700 if has_n else 732
    if has_n:
        add_text('Это не ежемесячная плата, а разовые взносы', 'M', 60, L, ny, seg_t('14', 0) - 0.25, c2, NAVY)
        add_text('Сумма зависит от того, какие вопросы примет собрание', 'R', 56, L, ny + 74,
                 seg_t('14', len(SEGS['14']) - 1) - 0.25, c2, MUTED)
    add_text('Взнос на распределители в этот расчёт не входит', 'M', 60, L, ny, seg_t('09', 1) - 0.25, end, NAVY)


def sc_10():
    c1, c2, c3, end = cut('10a'), cut('10b'), cut('10c'), cut('11')
    kicker('В указанные ставки включены', c1, c2)
    title('Материалы и работы', c1 + 0.1, c2)
    t1 = seg_t('10', 1) - 0.3
    card = add_card(L, 400, R - L, 220, t1, c2, name='fixed')
    add_icon('lock', L + 56, 468, 80, t1 + 0.05, c2)
    add_text('По проекту решения', 'R', 56, L + 180, 488, t1 + 0.1, c2, MUTED, inside=card)
    add_text('стоимость работ фиксирована', 'D', 64, L + 180, 570, t1 + 0.16, c2, NAVY, inside=card)
    kicker('По проекту решения: если стоимость материалов', c2, end)
    for ic, head, body, ti, to in [
            ('down', 'Обоснованно снизится',
             'Разница между начисленным взносом и фактическими затратами подлежит возврату собственникам', c2, c3),
            ('up', 'Обоснованно вырастет', 'Разницу предусмотрено покрыть из средств текущего ремонта', c3, end)]:
        title(head, ti + 0.05, to)
        lines = wrap(body, 'M', 60, R - L - 260)
        ch = 120 + 80 * len(lines)
        cd = add_card(L, 380, R - L, ch, ti + 0.15, to, name='case')
        add_icon(ic, L + 60, 380 + ch / 2 - 48, 96, ti + 0.2, to)
        add_lines(lines, 'M', 60, L + 204, 380 + 60 + 52, 80, ti + 0.25, to, INK, inside=cd)


def sc_11():
    c1, end = cut('11'), cut('12')
    kicker('Материалы собрания', c1, end)
    title('Сметы и предложения', c1 + 0.1, end)
    t1 = seg_t('11', 1) - 0.25
    add_icon('pin', L, 418, 64, t1, end)
    add_text('Офис управляющей компании', 'M', 60, L + 100, 470, t1 + 0.05, end, INK)
    add_text('с торца 3-й парадной', 'R', 56, L + 100, 548, t1 + 0.12, end, MUTED)
    t2 = word_t('11', 1, 'и на её сайте') - 0.25
    add_icon('web', L, 628, 64, t2, end)
    add_text('dombalt.ru', 'D', 64, L + 100, 682, t2 + 0.05, end, NAVY)


def sc_12():
    c1, end = cut('12'), cut('13a')
    kicker('Очная часть собрания', c1, end)
    t0 = word_t('12', 0, 'двадцатого') - 0.3
    add_icon('cal', L, 300, 96, t0, end)
    add_text('20' + NB + 'октября, 15:00', 'B', 150, L + 136, 400, t0 + 0.05, end, NAVY)
    t1 = seg_t('12', 1) - 0.25
    add_icon('pin', L + 16, 512, 64, t1, end)
    add_text('Помещение паспортной службы', 'M', 60, L + 136, 566, t1 + 0.05, end, INK)
    add_text('с торца 1-й парадной', 'R', 56, L + 136, 642, t1 + 0.12, end, MUTED)
    t3 = seg_t('12', 3) - 0.25
    add_text('Екатерининский проспект, д.' + NB + '2, стр.' + NB + '1', 'R', 56, L + 136, 742, t3, end, MUTED)


def sc_13():
    c1, c2 = cut('13a'), cut('13b')
    last = ITEMS['13b']['t1']
    endcard = min(b for b in TL['beats'] if b >= last + 3.0)   # info holds >3 s after the last word, then the brand card
    end = endcard
    kicker('Голосование', c1, end)
    ly = 262
    nodes = [L + 14, 760, R - 14]
    labs = [Text('16' + NB + 'октября', 'D', 56, L, ly + 76, MUTED),
            Text('20' + NB + 'октября · очная часть', 'D', 56, 746, ly + 76, MUTED),
            Text('31' + NB + 'января', 'D', 56, R, ly + 76, MUTED, 'r')]

    def act(i, t):
        if i == 0: return 1 - ease_io((t - c2) / 0.5)
        if i == 2: return ease_io((t - c2 - 0.9) / 0.4)
        return 0

    def dline(ctx, t, a, dy):
        rrect(ctx, L, ly - 2 + dy, R - L, 4, 2); ctx.set_source_rgba(*RULE, a); ctx.fill()
        k = ease_io((t - (c2 + 0.1)) / 1.0)
        if k > 0:
            rrect(ctx, L, ly - 3 + dy, (R - L) * k, 6, 3); ctx.set_source_rgba(*NAVY, a); ctx.fill()
        for i, x in enumerate(nodes):
            ac = act(i, t)
            ctx.arc(x, ly + dy, 13, 0, 2 * math.pi); ctx.set_source_rgba(*WHITE, a); ctx.fill_preserve()
            ctx.set_source_rgba(*(NAVY if ac > 0 or i == 2 and k > 0.95 else MUTED), a); ctx.set_line_width(4); ctx.stroke()
            if ac > 0:
                ctx.arc(x, ly + dy, 9 * ac, 0, 2 * math.pi); ctx.set_source_rgba(*NAVY, a); ctx.fill()
    ELS.append(El(dline, c1 + 0.1, end, 0.5, 0.2, 0, box=(L, ly - 13, R, ly + 13), name='timeline', kind='group'))

    def dlabs(ctx, t, a, dy):
        for i, o in enumerate(labs):
            o.color = NAVY if act(i, t) > 0.5 else MUTED
            o.draw(ctx, a, 0, dy)
    ELS.append(El(dlabs, c1 + 0.2, end, 0.5, 0.2, 14, box=(L, labs[0].bbox()[1], R, labs[0].bbox()[3]), name='tl-labels', kind='group'))
    for o in labs:
        ELS.append(El(lambda *a: None, c1 + 0.2, end, box=o.bbox(), name='tl-' + o.txt[:6]))
    t0 = seg_t('13', 0) - 0.3
    add_text('Голосование начинается', 'M', 60, L, 450, t0, c2, MUTED)
    add_text('16' + NB + 'октября', 'B', 150, L, 610, t0 + 0.1, c2, NAVY)
    t1 = seg_t('13', 1) - 0.25
    add_text('Приём решений завершается', 'M', 60, L, 450, t1, end, MUTED)
    add_text('31' + NB + 'января 2027, 18:00', 'B', 112, L, 565, t1 + 0.1, end, NAVY)
    t2 = seg_t('13', 2) - 0.25
    add_icon('clock', L, 614, 56, t2, end)
    add_text('В офис — заранее, в часы работы: пн–пт, 09:00–18:00', 'M', 56, L + 84, 661, t2 + 0.05, end, INK)
    t3 = seg_t('13', 3) - 0.25
    add_icon('cal', L, 700, 56, t3, end)
    add_text('Последний день голосования — воскресенье', 'R', 56, L + 84, 747, t3 + 0.05, end, MUTED)
    # brand card at the finale, same lockup as the opening
    logo = ASSETS + 'petersburg_dom_transparent.png'
    rect = fit(logo, LOGO_BOX)

    def dlogo(ctx, t, a, dy):
        k = ease_out((t - endcard) / 1.0); sc = 0.97 + 0.03 * k
        x, y, w, h = rect; cx, cy = x + w / 2, y + h / 2
        draw_img(ctx, logo, (cx - w * sc / 2, cy - h * sc / 2, w * sc, h * sc), a, ref=rect)
    ELS.append(El(dlogo, endcard, TOTAL + 1, 0.8, 0.2, 0, box=(rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]), name='logo-end'))
    add_text('dombalt.ru', 'D', 64, 960, 670, endcard + 0.35, TOTAL + 1, NAVY, 'c')


def build():
    ELS.clear()
    for f in (sc_logo, sc_01, sc_02, sc_03, sc_04, sc_05, sc_06, sc_07, sc_08, sc_09, sc_10, sc_11, sc_12, sc_13):
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
        if words[i - 1].lower() in PREP: continue
        wa, wb = tw(a, 'M', 56), tw(b, 'M', 56)
        if max(wa, wb) > maxw: continue
        adj = words[i - 1].lower().endswith(ADJ)   # keep adjective + noun together
        sc = abs(wa - wb) - (420 if a.endswith((',', ':', '—', '.')) else 0) + (500 if adj else 0) + (0 if min(wa, wb) >= max(wa, wb) * 0.35 else 600)
        if best is None or sc < best[0]: best = (sc, [a, b])
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
            t = float(tt); s = frame(t, subs=True); save_png(s, WORK + 'st_%07.2f.png' % t)
    elif mode == 'video':
        n = int(round(TOTAL * FPS))
        enc = lambda p: subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', '%dx%d' % (W, H),
            '-r', str(FPS), '-i', '-', '-i', WORK + 'mix.wav', '-map', '0:v', '-map', '1:a',
            '-vf', 'scale=out_color_matrix=bt709:out_range=tv,format=yuv420p', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
            '-tune', 'animation', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
            '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', '-t', '%.3f' % (n / FPS), p], stdin=subprocess.PIPE)
        p1, p2 = enc(OUT + 'clean.mp4'), enc(OUT + 'subs.mp4')
        stats = []
        s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        prev = None
        for i in range(n):
            t = i / FPS
            frame(t, False, s); s.flush(); p1.stdin.write(bytes(s.get_data()))
            a = np.ndarray((H, W, 4), np.uint8, s.get_data())[::8, ::8, :3].astype(np.int16)
            stats.append((t, float(a.mean()), float(np.abs(a - prev).mean()) if prev is not None else 0.0)); prev = a
            ctx = cairo.Context(s); draw_subs(ctx, t); s.flush(); p2.stdin.write(bytes(s.get_data()))
            if i % 500 == 0: print('frame', i, '/', n, flush=True)
        p1.stdin.close(); p2.stdin.close(); p1.wait(); p2.wait()
        json.dump(stats, open(WORK + 'framestats.json', 'w'))
        open(OUT + 'subs.srt', 'w', encoding='utf-8').write(srt())
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
    print('\n'.join(sorted(set(probs))) or 'layout OK')
    for s, e, txt in CUES:
        if len(sub_lines(txt)) > 2: print('sub >2 lines', txt)
    print('cues', len(CUES))


if __name__ == '__main__':
    main()
