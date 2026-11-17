"""Pixel-art toolkit: hue-shifted colour ramps, part shading and outlines,
dithered gradients, pixel-grid sprites and small scenery pieces.

The look follows classic 16-bit sprite work:
  - every colour comes from a ramp of 5 steps; shadows shift toward blue-violet
    and get more saturated, highlights shift toward yellow and get paler
  - the light comes from the top left: a lit band on top / left edges, a
    shadow band on bottom / right edges
  - parts get a 1 px outline in the darkest step of their own ramp (never flat
    black), so they separate from each other and from busy backgrounds
  - gradients are bands joined by a checker dither, not smooth blends

All edge work uses pygame masks (C speed), so it is cheap enough for the web
build; nothing here loops over pixels in Python except the tiny grid sprites.
"""
import colorsys
import math
import random

import pygame

# --- colour ------------------------------------------------------------------------


def clamp(v):
    return max(0, min(255, int(round(v))))


def mix(a, b, k):
    return tuple(clamp(a[i] + (b[i] - a[i]) * k) for i in range(3))


def shift(c, steps):
    """One colour `steps` ramp steps lighter (+) or darker (-), with hue shift:
    darker goes toward blue-violet and more saturated, lighter toward warm
    yellow and less saturated."""
    if not steps:
        return tuple(c[:3])
    h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c[:3]))
    for _ in range(abs(steps)):
        if steps < 0:
            target = 0.70                      # blue-violet
            v *= 0.74
            s = min(1.0, s * 1.10 + 0.04)
        else:
            target = 0.14                      # warm yellow
            v = min(1.0, v * 1.16 + 0.05)
            s *= 0.80
        d = (target - h + 0.5) % 1.0 - 0.5     # shortest way round the hue wheel
        h = (h + d * (0.07 if s > 0.08 else 0.0)) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return clamp(r * 255), clamp(g * 255), clamp(b * 255)


_ramps = {}


def ramp(base):
    """5 steps: [outline, shadow, base, light, shine]."""
    base = tuple(base[:3])
    r = _ramps.get(base)
    if r is None:
        r = [shift(base, -3), shift(base, -1), base, shift(base, 1), shift(base, 2)]
        # outline: deep but still in the colour's hue (cap its brightness)
        o = r[0]
        if max(o) > 90:
            o = tuple(clamp(x * 90 / max(o)) for x in o)
        r[0] = o
        _ramps[base] = r
    return r


def outline_of(c):
    return ramp(c)[0]


# --- masks ---------------------------------------------------------------------------


def mask(s):
    return pygame.mask.from_surface(s, 1)


def edge(m, dx, dy, thick=1):
    """Pixels of m within `thick` px of its border in direction (dx, dy)."""
    inside = m.copy()
    for i in range(1, thick + 1):
        inside = inside.overlap_mask(m, (-dx * i, -dy * i))
    band = m.copy()
    band.erase(inside, (0, 0))
    return band


def dilate(m, diag=False):
    """m grown by one pixel (4-neighbour, or 8 with diag)."""
    out = m.copy()
    offs = ((1, 0), (-1, 0), (0, 1), (0, -1))
    if diag:
        offs += ((1, 1), (-1, 1), (1, -1), (-1, -1))
    for o in offs:
        out.draw(m, o)
    return out


def paint(dst, m, col, pos=(0, 0)):
    if m.count():
        dst.blit(m.to_surface(setcolor=(*col[:3], 255), unsetcolor=(0, 0, 0, 0)), pos)


def finish(layer, base, outline=True, hi=1, lo=1, shine=False, rim=False, flat=True):
    """Shade a part drawn flat on `layer` (any colour, alpha = shape) with its
    ramp: lit top/left band, shadow bottom/right band, an outline round it.
    Returns a new surface the same size (the outline may reach the canvas edge).
    flat: recolour the whole shape to `base` first (False keeps drawn detail).
    shine: a 1-2 px specular glint near the top-left corner.
    rim: a thin reflected-light line inside the bottom shadow (round things)."""
    r = ramp(base)
    m = mask(layer)
    out = pygame.Surface(layer.get_size(), pygame.SRCALPHA)
    if outline:
        paint(out, dilate(m), r[0])
    if flat:
        paint(out, m, r[2])
    else:
        out.blit(layer, (0, 0))
    if lo:
        sh = edge(m, 0, 1, lo)
        sh.draw(edge(m, 1, 0, 1), (0, 0))
        paint(out, sh, r[1])
        if rim and lo >= 2:
            paint(out, edge(m, 0, 1, 1), r[2])
    if hi:
        lt = edge(m, 0, -1, hi)
        lt.draw(edge(m, -1, 0, 1), (0, 0))
        lt.erase(edge(m, 0, 1, 1), (0, 0))      # thin shapes: keep a shadow pixel
        paint(out, lt, r[3])
    if shine:
        tl = edge(m, 0, -1, 1).overlap_mask(edge(m, -1, 0, 2), (0, 0))
        tl = edge(m, 0, -1, 2)
        tl.erase(edge(m, -1, 0, 1), (0, 0))
        tl = tl.overlap_mask(edge(m, -1, 0, 3), (0, 0))
        paint(out, tl, r[4])
    return out


def part(dst, base, draw, outline=True, hi=1, lo=1, shine=False, rim=False, pos=(0, 0), size=None):
    """Draw a shaded, outlined part: draw(layer) paints its flat shape."""
    layer = pygame.Surface(size or dst.get_size(), pygame.SRCALPHA)
    draw(layer)
    dst.blit(finish(layer, base, outline, hi, lo, shine, rim), pos)


def silhouette(img, col, diag=False):
    """img with a 1 px outline of `col` round its whole shape (same size)."""
    m = mask(img)
    ring = dilate(m, diag)
    ring.erase(m, (0, 0))
    out = img.copy()
    paint(out, ring, col)
    return out


def inner_line(img, col, alpha_edge=True):
    """Darken the outermost pixels of a shape (an outline that doesn't add size)."""
    m = mask(img)
    ring = m.copy()
    ring.erase(m.overlap_mask(m, (1, 0)).overlap_mask(m, (-1, 0))
               .overlap_mask(m, (0, 1)).overlap_mask(m, (0, -1)), (0, 0))
    out = img.copy()
    paint(out, ring, col)
    return out


# --- dither ---------------------------------------------------------------------------

_checks = {}


def checker(w, h, col, phase=0, density=2):
    """A surface with every other pixel (density 2) or 1 in 4 (density 4) set."""
    key = (w, h, tuple(col[:3]), phase, density)
    s = _checks.get(key)
    if s is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            for x in range((y + phase) % 2 if density == 2 else (y % 2) * 2 + phase % 2, w,
                           2 if density == 2 else 4):
                if density == 4 and y % 2 and phase % 2:
                    pass
                s.set_at((x, y), (*col[:3], 255))
        if len(_checks) > 300:
            _checks.clear()
        _checks[key] = s
    return s


def dither_rows(dst, x, y, w, rows, col_a, col_b):
    """Blend from a into b over `rows` rows: 25%, 50%, 75% checker steps."""
    for i in range(rows):
        k = (i + 1) / (rows + 1)
        dst.fill(col_a, (x, y + i, w, 1))
        if k < 0.34:
            dst.blit(checker(w, 1, col_b, i, 4), (x, y + i))
        elif k < 0.67:
            dst.blit(checker(w, 1, col_b, i), (x, y + i))
        else:
            dst.fill(col_b, (x, y + i, w, 1))
            dst.blit(checker(w, 1, col_a, i, 4), (x, y + i))


def band_gradient(dst, rect, top, bottom, bands=7, dither=3):
    """Vertical gradient as flat colour bands joined by checker dither."""
    x, y, w, h = rect
    cols = [mix(top, bottom, i / (bands - 1)) for i in range(bands)]
    bh = h / bands
    for i, c in enumerate(cols):
        y0 = y + int(i * bh)
        y1 = y + int((i + 1) * bh)
        dst.fill(c, (x, y0, w, y1 - y0))
        if i + 1 < bands and dither:
            nxt = cols[i + 1]
            d = min(dither, y1 - y0)
            for j in range(d):
                yy = y1 - d + j
                pat = checker(w, 1, nxt, j, 4 if j < d / 2 else 2)
                dst.blit(pat, (x, yy))


def dither_shade(dst, m, col, density=2, pos=(0, 0)):
    """Lay a checker of `col` over the pixels in mask m (a soft shadow)."""
    w, h = m.get_size()
    pat = checker(w, h, col, 0, density)
    pm = pygame.mask.from_surface(pat, 1).overlap_mask(m, (0, 0))
    paint(dst, pm, col, pos)


# --- grid sprites -------------------------------------------------------------------------


def grid(rows, pal, flip=False):
    """A sprite from text rows: each char maps to a colour in pal ('.' / ' ' clear)."""
    h = len(rows)
    w = max(len(r) for r in rows)
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            c = pal.get(ch)
            if c is not None:
                s.set_at((w - 1 - x if flip else x, y), (*c[:3], 255) if len(c) == 3 else c)
    return s


# --- scenery pieces ---------------------------------------------------------------------


def blob(dst, cx, cy, r, col):
    pygame.draw.circle(dst, col, (int(cx), int(cy)), max(1, int(r)))


def canopy(dst, cx, cy, w, h, base, rng, outline=True, clumps=None):
    """A leafy crown: overlapping round clumps, each with a lit top-left,
    shadowed underside, dark outline and a few leaf-tip pixels."""
    r = ramp(base)
    pad = 3
    W, H = int(w) + pad * 2, int(h) + pad * 2
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    n = clumps or max(3, int(w * h / 60))
    pts = []
    for i in range(n):
        a = rng.random() * math.tau
        rr = rng.random() ** 0.6
        px = W / 2 + math.cos(a) * rr * (w / 2 - w / 5)
        py = H / 2 + math.sin(a) * rr * (h / 2 - h / 5)
        pts.append((px, py, max(2, min(w, h) / 3.2 + rng.random() * 1.5)))
    pts.sort(key=lambda p: p[1])
    shape = pygame.Surface((W, H), pygame.SRCALPHA)
    for px, py, pr in pts:
        blob(shape, px, py, pr, (255, 255, 255))
    m = mask(shape)
    if outline:
        paint(layer, dilate(m), r[0])
    paint(layer, m, r[1])
    # each clump: lit cap in base, then a light crescent top-left (back to front)
    for px, py, pr in pts:
        c = pygame.Surface((W, H), pygame.SRCALPHA)
        blob(c, px, py, pr, (255, 255, 255))
        cm = mask(c).overlap_mask(m, (0, 0))
        top = cm.copy()
        top.erase(mask(c), (0, int(max(1, pr * 0.55))))
        paint(layer, top, r[2])
        lit = cm.copy()
        lit.erase(mask(c), (1, 2))
        paint(layer, lit, r[3])
        # a separating dark arc under the clump
        und = edge(cm, 0, 1, 1).overlap_mask(m, (0, 0))
        paint(layer, und, r[1])
    # deepest shade across the bottom, dithered upward
    bot = edge(m, 0, 1, max(1, int(h / 5)))
    dither_shade(layer, bot, r[1], 2)
    paint(layer, edge(m, 0, 1, 1), shift(r[1], -1))
    # leaf-tip sparkle pixels on the lit side
    for _ in range(int(w * h / 40)):
        x = rng.randrange(W)
        y = rng.randrange(H)
        if m.get_at((x, y)) and y < H * 0.6 and x < W * 0.7:
            layer.set_at((x, y), (*r[4], 255))
    dst.blit(layer, (int(cx - W / 2), int(cy - H / 2)))
    return layer


def tree(dst, x, ground, h, base, trunk, rng, kind="round"):
    """A tree standing on (x, ground) about h px tall: trunk, root flare, crown."""
    tr = ramp(trunk)
    tw = max(2, h // 9)
    th = int(h * 0.42)
    pygame.draw.rect(dst, tr[0], (x - tw // 2 - 1, ground - th - 1, tw + 2, th + 1))
    pygame.draw.rect(dst, tr[2], (x - tw // 2, ground - th, tw, th))
    if tw >= 3:
        dst.fill(tr[1], (x + tw // 2 - 1, ground - th, 1, th))
        dst.fill(tr[3], (x - tw // 2, ground - th, 1, th))
    dst.fill(tr[1], (x - tw // 2 - 1, ground - 1, tw + 2, 1))
    if kind == "pine":
        r = ramp(base)
        tiers = max(3, h // 7)
        for i in range(tiers):
            ty = ground - th // 2 - i * (h - th // 2) // tiers - 4
            hw = int((tiers - i) * h / tiers / 2.6) + 1
            pts = [(x - hw, ty), (x, ty - (h - th // 2) // tiers - 4), (x + hw, ty)]
            pygame.draw.polygon(dst, r[0], [(pts[0][0] - 1, ty + 1), (x, pts[1][1] - 1), (pts[2][0] + 1, ty + 1)])
            pygame.draw.polygon(dst, r[2], pts)
            pygame.draw.polygon(dst, r[1], [(x, pts[1][1]), (pts[2][0], ty), (x + 1, ty)])
            pygame.draw.line(dst, r[3], (pts[0][0] + 1, ty - 1), (x, pts[1][1] + 1))
        return
    cw = int(h * 0.8)
    ch = int(h * 0.68)
    canopy(dst, x, ground - th - ch // 2 + ch // 6, cw, ch, base, rng)


def bush(dst, x, ground, w, base, rng, flowers=None):
    h = max(4, int(w * 0.6))
    layer = canopy(dst, x, ground - h / 2, w, h, base, rng, clumps=max(3, w // 4))
    if flowers:
        for _ in range(max(1, w // 5)):
            fx = x + rng.randrange(-w // 2 + 1, w // 2)
            fy = ground - rng.randrange(2, h)
            dst.fill(rng.choice(flowers), (fx, fy, 1, 1))
    return layer


def cloud(dst, cx, cy, w, rng, col=(255, 255, 255), shade=(200, 214, 240), line=None):
    """A puffy cloud: round bumps rising to a big middle one over a flat base,
    lit tops, a shaded underside joined by a dither band, an outline in the
    sky's own hue, and a crease under each bump."""
    h = max(8, int(w * 0.4))
    W, H = w + 6, int(h * 1.45) + 6
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    shape = pygame.Surface((W, H), pygame.SRCALPHA)
    n = max(3, w // 12)
    bumps = []
    for i in range(n):
        k = math.sin(math.pi * (i + 0.5) / n)
        br = h * (0.32 + 0.42 * k) + rng.random() * 1.5
        bx = 3 + w * (i + 0.5) / n + rng.randint(-1, 1)
        by = H - 3 - br * 0.75
        bumps.append((bx, by, br))
        blob(shape, bx, by, br, (255, 255, 255))
    shape.fill((255, 255, 255), (4, H - 3 - int(h * 0.35), w - 2, int(h * 0.35)))
    m = mask(shape)
    keep = pygame.mask.Mask((W, H))
    keep.draw(pygame.mask.Mask((W, H - 3), fill=True), (0, 0))
    m = m.overlap_mask(keep, (0, 0))
    if line:
        paint(s, dilate(m), line)
    paint(s, m, shade)
    k = max(2, h // 4)
    lit = m.overlap_mask(m, (0, -k))
    paint(s, lit, col)
    band = m.overlap_mask(m, (0, -(k - 2))) if k > 2 else m.copy()
    band.erase(lit, (0, 0))
    dither_shade(s, band, col, 2)
    for bx, by, br in bumps[1:]:                       # creases where bumps overlap
        c = pygame.Surface((W, H), pygame.SRCALPHA)
        blob(c, bx, by, br, (255, 255, 255))
        cm = edge(mask(c), -1, 0, 1).overlap_mask(lit, (0, 0))
        cm.erase(edge(m, 0, -1, 2), (0, 0))
        paint(s, cm, mix(col, shade, 0.5))
    dst.blit(s, (int(cx - W / 2), int(cy - H / 2)))


def rock(dst, x, y, w, h, base, rng=None):
    """A chunky rock sitting on (x..x+w, y): faceted top light, dark base, outline."""
    rng = rng or random.Random(x * 7 + y)
    r = ramp(base)
    pts = [(x, y), (x + rng.randint(0, 1), y - h + 2), (x + w * 0.35, y - h),
           (x + w * 0.75, y - h + rng.randint(0, 2)), (x + w, y - h * 0.4), (x + w, y)]
    pygame.draw.polygon(dst, r[0], [(px + (1 if px > x + w / 2 else -1), py - (1 if py < y else 0))
                                    for px, py in pts])
    pygame.draw.polygon(dst, r[2], pts)
    pygame.draw.polygon(dst, r[1], [(x + w * 0.55, y - h * 0.5), (x + w, y - h * 0.4), (x + w, y), (x + w * 0.4, y)])
    pygame.draw.line(dst, r[3], (x + 1, y - h + 2), (x + w * 0.35, y - h + 1))
    if w >= 5:
        dst.fill(r[4], (int(x + w * 0.3), int(y - h + 1), 1, 1))
    dst.fill(r[0], (int(x), int(y), int(w) + 1, 1))


def pebble(dst, x, y, base, big=False):
    r = ramp(base)
    if big:
        dst.fill(r[0], (x, y + 1, 4, 2))
        dst.fill(r[2], (x, y, 3, 2))
        dst.fill(r[3], (x, y, 1, 1))
        dst.fill(r[1], (x + 2, y + 1, 1, 1))
    else:
        dst.fill(r[3], (x, y, 1, 1))
        dst.fill(r[0], (x + 1, y, 1, 1))
        dst.fill(r[1], (x, y + 1, 2, 1))


def tuft(dst, x, y, base, rng, h=3):
    """A grass tuft: 3-5 blades in two greens with a lit tip."""
    r = ramp(base)
    n = rng.randint(3, 5)
    for i in range(n):
        bx = x + i - n // 2
        bh = h - abs(i - n // 2) + rng.randint(0, 1)
        if bh <= 0:
            continue
        dst.fill(r[1] if i % 2 else r[2], (bx, y - bh + 1, 1, bh))
        dst.fill(r[3], (bx, y - bh + 1, 1, 1))
    dst.fill(r[0], (x - n // 2, y + 1, n, 1))


def flower(dst, x, y, col, rng):
    stem = (60, 140, 60)
    dst.fill(stem, (x, y - 1, 1, 2))
    dst.fill(col, (x - 1, y - 2, 3, 1))
    dst.fill(col, (x, y - 3, 1, 3))
    dst.fill((255, 240, 150), (x, y - 2, 1, 1))


# --- people (spectators) -----------------------------------------------------------------

SKINS = [(255, 214, 178), (240, 188, 146), (206, 150, 108), (156, 104, 70), (112, 74, 52)]
HAIRS = [(50, 34, 30), (96, 56, 32), (232, 196, 96), (196, 80, 40), (30, 28, 40),
         (150, 150, 160), (240, 120, 170), (70, 120, 220)]
SHIRTS = [(232, 72, 52), (40, 140, 230), (255, 196, 0), (120, 220, 60), (160, 90, 230),
          (250, 250, 250), (250, 140, 40), (40, 190, 180), (240, 110, 170)]

# Head sprites 5 px wide, 5 tall (o outline, h hair, H hair light, s skin,
# k skin shade, e eye, c cheek). Each is a different hairstyle.
_HEADS = [
    [".ooo.", "ohHho", "ohsso", "osese", ".okko"],      # short
    [".ooo.", "oHHho", "hssso", "hesec", "hokko"],      # long, sides down
    ["oo.oo", "oHHho", "ohsso", "osese", ".okko"],      # spiky / bunches
    [".ooo.", "oHHHo", "ossso", "osese", ".okko"],      # cap of hair (bowl)
    [".ooo.", "ohhho", "ohhho", "ohhho", ".ooo."],      # seen from behind
]


def spectator(dst, x, y, rng, cheer=0, flag=None, back=False):
    """A 5 px wide, 10 px tall fan in the stands, feet at (x+2, y). Shirt,
    arms (raised when cheering), a face with eyes and cheeks, a hairstyle.
    cheer: 0 arms down, 1 one arm up, 2 both up."""
    skin = rng.choice(SKINS)
    hair = rng.choice(HAIRS)
    shirt = rng.choice(SHIRTS)
    sr = ramp(shirt)
    hr = ramp(hair)
    kr = ramp(skin)
    o = mix(hr[0], (20, 14, 30), 0.5)
    # body (shoulders 5 px)
    top = y - 10
    dst.fill(o, (x - 1, top + 5, 7, 6))
    dst.fill(sr[2], (x, top + 6, 5, 4))
    dst.fill(sr[3], (x, top + 6, 2, 1))
    dst.fill(sr[1], (x + 4, top + 7, 1, 3))
    # arms
    if cheer:
        for side in ((1, 2) if cheer == 2 else (rng.choice((1, 2)),)):
            ax = x - 1 if side == 1 else x + 5
            dst.fill(o, (ax - 1 + (side - 1), top + 1, 2, 6))
            dst.fill(sr[2], (ax, top + 3, 1, 3))
            dst.fill(kr[2], (ax, top + 1, 1, 2))
    pal = {"o": o, "h": hr[2], "H": hr[3], "s": kr[2], "k": kr[1], "e": (40, 24, 30),
           "c": mix(kr[2], (240, 110, 110), 0.5)}
    rows = _HEADS[4] if back else rng.choice(_HEADS[:4])
    head = grid(rows, pal)
    dst.blit(head, (x, top + 1))
    if flag:
        fx = x + 5
        dst.fill((90, 80, 70), (fx, top - 6, 1, 10))
        dst.fill(flag, (fx + 1, top - 6, 5, 3))
        dst.fill(shift(flag, 1), (fx + 1, top - 6, 5, 1))


def relight(img, top=1, bottom=3, outline=True, line_col=None, rivets=True):
    """Finish a big multi-colour piece drawn flat (a boss rig): every pixel on
    its top / left edge one ramp step lighter, a checker-dithered band along its
    bottom one step darker (solid on the last row), and a 1 px outline.
    Per-pixel, so use it once on cached art, not every frame."""
    out = img.copy()
    m = mask(img)
    lit = edge(m, 0, -1, top)
    lit.draw(edge(m, -1, 0, 1), (0, 0))
    dark = edge(m, 0, 1, bottom)
    last = edge(m, 0, 1, 1)
    for (x0, y0, bw, bh) in m.get_bounding_rects():
        for y in range(y0, y0 + bh):
            for x in range(x0, x0 + bw):
                if lit.get_at((x, y)):
                    step = 1
                elif last.get_at((x, y)) or (dark.get_at((x, y)) and (x + y) % 2 == 0):
                    step = -1
                else:
                    continue
                c = out.get_at((x, y))
                out.set_at((x, y), (*shift(c[:3], step), c[3]))
    if rivets:                                          # rivets / panel seams on big flat parts
        inner = m.copy()
        for _ in range(4):
            inner = inner.overlap_mask(m.overlap_mask(inner, (1, 0)).overlap_mask(inner, (-1, 0))
                                       .overlap_mask(inner, (0, 1)).overlap_mask(inner, (0, -1)), (0, 0))
        band = edge(m, 0, -1, 4)
        band.erase(edge(m, 0, -1, 2), (0, 0))
        w, h = m.get_size()
        for y in range(h):
            for x in range(0, w, 9):
                if band.get_at((x, y)) and inner.get_at((x, y)):
                    c = out.get_at((x, y))
                    out.set_at((x, y), (*shift(c[:3], 2), c[3]))
                    if y + 1 < h:
                        out.set_at((x, y + 1), (*shift(c[:3], -2), c[3]))
    if outline:
        ring = dilate(m)
        ring.erase(m, (0, 0))
        paint(out, ring, line_col or (20, 14, 26))
    return out


# --- seated fans and trackside marshals (7 px heads) ------------------------------------
# o outline  h hair  H hair light  s skin  k skin shade  e eye  c blush  m mouth
# C cap  V cap peak  l scalp shine
FACES = {
    "short": [".ooooo.", "oHHhhho", "ohsssho", "oseseso", "ocsmsco", ".okkko."],
    "long":  [".ooooo.", "oHHHhho", "hhssshh", "hsesesh", "hcsmsch", "hhkkkhh", "h.....h"],
    "bun":   ["..oHo..", ".ooHoo.", "oHhhhho", "ohsssho", "oseseso", "ocsmsco", ".okkko."],
    "spiky": ["h.H.h.h", "hHhHhHh", "ohhhhho", "ohsssho", "oseseso", "ocsmsco", ".okkko."],
    "cap":   [".ooooo.", "oCCCCCo", "oVVVVVV", "oseseso", "ocsmsco", ".okkko."],
    "bald":  [".ooooo.", "oslssso", "hsssssh", "hsesesh", "ocsmsco", ".okkko."],
    "bob":   [".ooooo.", "oHHHHho", "ohhhhho", "hsesesh", "hcsmsch", ".hkkkh."],
}
_face_cache = {}


def face(style, skin, hair, cap=None):
    key = (style, skin, hair, cap)
    img = _face_cache.get(key)
    if img is None:
        hr, kr = ramp(hair), ramp(skin)
        cr = ramp(cap or (220, 60, 60))
        pal = {"o": mix(hr[0], (24, 14, 30), 0.5), "h": hr[2], "H": hr[3], "s": kr[2], "k": kr[1],
               "e": (34, 22, 30), "c": mix(kr[2], (250, 110, 120), 0.55), "m": (170, 70, 70),
               "C": cr[2], "V": cr[1], "l": kr[4]}
        img = grid(FACES[style], pal)
        if len(_face_cache) > 600:
            _face_cache.clear()
        _face_cache[key] = img
    return img


def seat(dst, x, y, col):
    """A stadium seat back, 7 x 6, its top at y."""
    r = ramp(col)
    dst.fill(r[0], (x, y, 7, 6))
    dst.fill(r[2], (x + 1, y, 5, 5))
    dst.fill(r[3], (x + 1, y, 5, 1))
    dst.fill(r[1], (x + 5, y + 1, 1, 4))


def fan(dst, x, y, rng, cheer=0):
    """A seated fan whose seat back's top is at y: head over shoulders in a
    shirt, arms up when cheering (1 or 2)."""
    skin = rng.choice(SKINS)
    style = rng.choice(list(FACES))
    hair = rng.choice(HAIRS)
    shirt = rng.choice(SHIRTS)
    sr = ramp(shirt)
    o = mix(sr[0], (20, 14, 30), 0.4)
    # shoulders over the seat back
    dst.fill(o, (x, y + 1, 7, 5))
    dst.fill(sr[2], (x + 1, y + 2, 5, 4))
    dst.fill(sr[3], (x + 1, y + 2, 2, 1))
    dst.fill(sr[1], (x + 5, y + 3, 1, 3))
    hd = face(style, skin, hair, rng.choice(SHIRTS) if style == "cap" else None)
    dst.blit(hd, (x, y - hd.get_height() + 2))
    if cheer:
        kr = ramp(skin)
        for side in ((0, 1) if cheer == 2 else (rng.randint(0, 1),)):
            ax = x - 1 if side == 0 else x + 7
            dst.fill(o, (ax - (1 if side == 0 else 0), y - 7, 2, 9))
            dst.fill(sr[2], (ax, y - 3, 1, 4))
            dst.fill(kr[2], (ax, y - 6, 1, 3))


def marshal(dst, x, ground, rng, kind="flag", flag=(255, 214, 40)):
    """A track marshal standing by the fence: hi-vis vest over a white suit,
    a cap, and a flag or a pit board. Feet at (x+3, ground)."""
    skin = rng.choice(SKINS)
    vest = ramp((255, 130, 30))
    suit = ramp((236, 236, 244))
    o = (30, 22, 36)
    top = ground - 18
    dst.fill(o, (x + 1, ground - 6, 5, 6))                  # legs
    dst.fill(suit[1], (x + 2, ground - 6, 1, 5))
    dst.fill(suit[2], (x + 4, ground - 6, 1, 5))
    dst.fill(o, (x + 1, ground - 1, 2, 1))
    dst.fill(o, (x + 4, ground - 1, 2, 1))
    dst.fill(o, (x, top + 6, 7, 7))                         # body
    dst.fill(vest[2], (x + 1, top + 7, 5, 5))
    dst.fill(vest[3], (x + 1, top + 7, 2, 1))
    dst.fill((250, 250, 250), (x + 1, top + 9, 5, 1))       # reflective band
    dst.fill(vest[1], (x + 5, top + 8, 1, 4))
    dst.blit(face("cap", skin, (60, 40, 30), (240, 240, 250)), (x, top))
    if kind == "flag":
        dst.fill((90, 80, 70), (x + 7, top - 2, 1, 12))
        wave = rng.randint(0, 1)
        fr = ramp(flag)
        dst.fill(ramp(flag)[0], (x + 8, top - 3, 8, 6))
        dst.fill(fr[2], (x + 8, top - 2 + wave, 7, 4))
        dst.fill(fr[3], (x + 8, top - 2 + wave, 7, 1))
        dst.fill(skin, (x + 7, top + 6, 1, 2))
    else:                                                   # a pit board held up
        dst.fill(o, (x + 6, top + 1, 10, 8))
        dst.fill((250, 250, 250), (x + 7, top + 2, 8, 6))
        dst.fill((40, 40, 50), (x + 8, top + 3, 2, 4))
        dst.fill((220, 50, 50), (x + 11, top + 3, 3, 4))
        dst.fill(skin, (x + 6, top + 8, 2, 1))
