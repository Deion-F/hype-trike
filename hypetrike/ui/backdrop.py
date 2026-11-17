"""Parallax backdrops, one per biome, drawn in the 16-bit style of ui/pix.

Two layers: far (sky, sun or moon, clouds, mountains) and mid (hills, trees,
houses, grandstands full of fans, the trackside fence) plus the berm strip
right behind the back lane. Each layer is 2x the view width and repeats every
view width (the renderer wraps it at that period), so everything is drawn
wrap-safe: anything near an edge is drawn again one period over.
"""
import math
import random

import pygame

import config as C
from ui import pix

HORIZON = 200          # sky gradient runs to here
FENCE_Y = 206          # trackside fence top
BERM_TOP = 224         # berm strip (just behind lane 0) top; LANE_BASE_Y is 236


def _seed(theme, salt=0):
    return sum(ord(c) * (i + 7) for i, c in enumerate(theme)) * 131 + salt


class _Layer:
    """A P-wide canvas where every draw is repeated at x - P and x + P, so the
    picture tiles seamlessly; .doubled() gives the 2P layer the renderer wraps.
    .s is the 360 px design band (dy px down the full canvas, see config.ZOOM);
    .full the whole height, for the sky that fills the extra room above."""

    def __init__(self, P, H, alpha, dy=0):
        self.P, self.H, self.dy = P, H, dy
        self.full = pygame.Surface((P, H), pygame.SRCALPHA if alpha else 0)
        self.s = self.full.subsurface((0, dy, P, H - dy))

    def rep(self, fn, x, *a, **kw):
        for dx in (-self.P, 0, self.P):
            fn(self.s, x + dx, *a, **kw)

    def doubled(self):
        out = pygame.Surface((self.P * 2, self.H), self.full.get_flags())
        out.blit(self.full, (0, 0))
        out.blit(self.full, (self.P, 0))
        return out


def _periodic(P, rng, terms):
    """Height function periodic over P: sum of sines with whole-number cycles."""
    ph = [(n, amp, rng.random() * math.tau) for n, amp in terms]
    return lambda x: sum(amp * math.sin(x * math.tau * n / P + p) for n, amp, p in ph)


# --- sky ------------------------------------------------------------------------------------


def _sky(L, top, bottom, bands=9):
    h = HORIZON + L.dy
    pix.band_gradient(L.full, (0, 0, L.P, h), top, bottom, bands + L.dy // 30, 3)
    L.full.fill(bottom, (0, h, L.P, L.H - h))


def _sun(L, x, y, r, col, glow):
    s = L.s
    for i, k in enumerate((2.4, 1.8, 1.35)):
        g = pygame.Surface((int(r * k * 2 + 2),) * 2, pygame.SRCALPHA)
        pygame.draw.circle(g, (255, 255, 255), (g.get_width() // 2,) * 2, int(r * k))
        pix.dither_shade(s, pix.mask(g), pix.mix(glow, col, i * 0.3), 4 if i == 0 else 2,
                         (x - g.get_width() // 2, y - g.get_width() // 2))
    pygame.draw.circle(s, pix.shift(col, -1), (x, y), r)
    pygame.draw.circle(s, col, (x - 1, y - 1), r - 1)
    pygame.draw.circle(s, pix.shift(col, 2), (x - r // 3, y - r // 3), max(1, r // 3))


def _moon(L, x, y, r):
    s = L.s
    for i, k in enumerate((2.6, 1.7)):
        g = pygame.Surface((int(r * k * 2 + 2),) * 2, pygame.SRCALPHA)
        pygame.draw.circle(g, (255, 255, 255), (g.get_width() // 2,) * 2, int(r * k))
        pix.dither_shade(s, pix.mask(g), (60, 70, 130) if i == 0 else (90, 100, 160), 4 if i == 0 else 2,
                         (x - g.get_width() // 2, y - g.get_width() // 2))
    pygame.draw.circle(s, (200, 200, 170), (x, y), r)
    pygame.draw.circle(s, (246, 244, 214), (x - 1, y - 1), r - 1)
    for cx, cy, cr in ((-4, -3, 3), (3, 2, 2), (-1, 5, 2), (5, -5, 1)):
        pygame.draw.circle(s, (214, 210, 180), (x + cx, y + cy), cr)
        s.set_at((x + cx - 1, y + cy - 1), (255, 255, 236))


def _stars(L, rng, n, top=0, bottom=150):
    s = L.full
    bottom += L.dy
    for _ in range(n):
        x, y = rng.randrange(L.P), rng.randrange(top, bottom)
        b = rng.random()
        if b > 0.95:                                        # a twinkle cross
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                s.set_at(((x + dx) % L.P, y + dy), (255, 255, 230) if not (dx or dy) else (150, 160, 220))
        else:
            s.set_at((x, y), (255, 255, 255) if b > 0.6 else (150, 160, 210))


def _clouds(L, rng, n, ys, col, shade, line, wmin=34, wmax=96):
    for i in range(n):
        x = int((i + rng.random() * 0.6) * L.P / n)
        y = rng.randint(ys[0] - L.dy * 3 // 4, ys[1])
        w = rng.randint(wmin, wmax)
        seed = rng.random()
        L.rep(lambda s, xx, w=w, y=y, seed=seed: pix.cloud(L.full, xx, y + L.dy, w, random.Random(seed), col, shade, line), x)


def _birds(L, rng, n, col):
    for _ in range(n):
        x, y = rng.randrange(L.P), rng.randrange(30, 110)
        L.s.set_at((x - 1, y - 1), col)
        L.s.set_at((x, y), col)
        L.s.set_at((x + 1, y - 1), col)


# --- terrain ranges --------------------------------------------------------------------------


def _range(L, base_y, h_fn, col, lit=True, snow=None, haze=None, outline=True, ridge_light=None):
    """A mountain/hill range: per column, lit colour on faces turned to the
    light (rising to the right), shadow on the others, a light ridge line,
    optional snow above `snow` px, a dithered haze toward `haze` at its foot."""
    r = pix.ramp(col)
    s = L.s
    ys = [base_y - h_fn(x) for x in range(L.P + 1)]
    rising = True
    for x in range(L.P):
        y = int(ys[x])
        d = ys[(x + 3) % L.P] - ys[x]                 # a few px ahead: no flicker on flats
        if d < -0.4:
            rising = True
        elif d > 0.4:
            rising = False
        c = r[2] if (rising or not lit) else r[1]
        s.fill(c, (x, y, 1, L.H - y))
        if outline:
            s.set_at((x, y - 1), r[0] if not ridge_light else r[1])
        if lit:
            s.set_at((x, y), (ridge_light or r[3]) if rising else r[2])
        if snow is not None and y < snow:
            depth = int((snow - y) * 0.8) + (x * 7 % 3)
            sc = (250, 250, 255) if rising else (196, 210, 240)
            s.fill(sc, (x, y, 1, depth))
            s.set_at((x, y + depth), pix.shift(sc, -1))
    if haze is not None:
        hm = pygame.mask.Mask((L.P, L.H))
        for x in range(L.P):
            y = int(ys[x])
            top = max(y, base_y - 22)
            if top < L.H:
                hm.draw(pygame.mask.Mask((1, max(1, base_y + 30 - top)), fill=True), (x, top))
        pix.dither_shade(s, hm, haze, 4)
        hm2 = pygame.mask.Mask((L.P, L.H))
        for x in range(L.P):
            top = max(int(ys[x]), base_y - 8)
            hm2.draw(pygame.mask.Mask((1, max(1, base_y + 30 - top)), fill=True), (x, top))
        pix.dither_shade(s, hm2, haze, 2)
    return ys


def _texture(L, ys, col, rng, n, kind="tuft", y_max=None):
    s = L.s
    for _ in range(n):
        x = rng.randrange(L.P)
        y = int(ys[x]) + rng.randint(3, 26)
        if y_max and y > y_max:
            continue
        if kind == "tuft":
            pix.tuft(s, x, y, col, rng, rng.randint(2, 3))
        elif kind == "speck":
            s.set_at((x, y), col)


# --- props -------------------------------------------------------------------------------------


def _house(s, x, ground, rng, wall=(246, 236, 214), roof=(214, 76, 60), w=None):
    """A small cottage: walls with a shaded side, a pitched roof with tile rows
    and an eave shadow, a door, lit windows, a chimney."""
    w = w or rng.choice((16, 18, 22))
    h = w * 2 // 3
    wr, rr = pix.ramp(wall), pix.ramp(roof)
    top = ground - h
    s.fill(wr[0], (x - 1, top - 1, w + 2, h + 1))
    s.fill(wr[2], (x, top, w, h))
    s.fill(wr[1], (x + w - 3, top, 3, h))
    s.fill(wr[3], (x, top, 1, h))
    ry = top - w // 3 - 2
    if rng.random() < 0.5:                                       # chimney
        cx = x + w * 2 // 3
        s.fill(pix.ramp((150, 90, 70))[0], (cx - 1, ry - 2, 5, 8))
        s.fill((150, 90, 70), (cx, ry - 1, 3, 7))
    pts = [(x - 3, top + 1), (x + w // 2, ry), (x + w + 2, top + 1)]
    pygame.draw.polygon(s, rr[0], [(pts[0][0] - 1, pts[0][1] + 1), (pts[1][0], pts[1][1] - 1), (pts[2][0] + 1, pts[2][1] + 1)])
    pygame.draw.polygon(s, rr[2], pts)
    pygame.draw.polygon(s, rr[1], [pts[1], pts[2], (x + w // 2, top + 1)])
    for k in range(1, 4):                                        # tile rows
        yy = ry + (top + 1 - ry) * k // 4
        half = (w // 2 + 3) * k // 4
        pygame.draw.line(s, rr[1] if k % 2 else rr[3], (x + w // 2 - half + 1, yy), (x + w // 2 + half - 1, yy))
    pygame.draw.line(s, rr[3], pts[0], pts[1])
    s.fill(wr[1], (x, top, w, 1))                                # eave shadow
    dx = x + 2 if w < 18 else x + w // 2 - 2
    s.fill(pix.ramp((120, 76, 50))[1], (dx, ground - 6, 4, 6))
    s.fill(pix.ramp((120, 76, 50))[3], (dx, ground - 6, 1, 6))
    s.set_at((dx + 3, ground - 3), (240, 200, 90))
    for wx in ((x + w - 8,) if w < 18 else (x + 2, x + w - 7)):
        s.fill(wr[0], (wx - 1, top + 2, 6, 5))
        s.fill((120, 180, 230), (wx, top + 3, 4, 3))
        s.fill((230, 246, 255), (wx, top + 3, 1, 1))
        s.fill(wr[0], (wx + 2, top + 3, 1, 3))


def _barn(s, x, ground, rng):
    w, h = 22, 14
    r = pix.ramp((190, 50, 44))
    s.fill(r[0], (x - 1, ground - h - 1, w + 2, h + 1))
    s.fill(r[2], (x, ground - h, w, h))
    for k in range(2, w, 3):
        s.fill(r[1], (x + k, ground - h, 1, h))
    pts = [(x - 2, ground - h), (x + 4, ground - h - 7), (x + w - 4, ground - h - 7), (x + w + 2, ground - h)]
    pygame.draw.polygon(s, (60, 54, 64), [(px, py - 1) for px, py in pts])
    pygame.draw.polygon(s, (120, 110, 120), pts)
    pygame.draw.line(s, (160, 152, 160), pts[1], pts[2])
    s.fill((246, 236, 214), (x + 7, ground - 9, 8, 9))
    s.fill(r[1], (x + 8, ground - 8, 6, 8))
    pygame.draw.line(s, (246, 236, 214), (x + 8, ground - 8), (x + 13, ground - 1))
    pygame.draw.line(s, (246, 236, 214), (x + 13, ground - 8), (x + 8, ground - 1))


def _windmill(s, x, ground, rng, t=0):
    tr = pix.ramp((236, 230, 220))
    pygame.draw.polygon(s, tr[0], [(x - 5, ground), (x - 3, ground - 26), (x + 3, ground - 26), (x + 5, ground)])
    pygame.draw.polygon(s, tr[2], [(x - 4, ground), (x - 2, ground - 25), (x + 2, ground - 25), (x + 4, ground)])
    s.fill(tr[1], (x + 1, ground - 25, 3, 25))
    hub = (x, ground - 27)
    for k in range(4):
        a = k * math.pi / 2 + 0.4
        e = (hub[0] + 13 * math.cos(a), hub[1] + 13 * math.sin(a))
        pygame.draw.line(s, (90, 70, 60), hub, e, 1)
        p = (hub[0] + 9 * math.cos(a + 0.18), hub[1] + 9 * math.sin(a + 0.18))
        pygame.draw.line(s, (250, 250, 250), (hub[0] + 4 * math.cos(a + 0.2), hub[1] + 4 * math.sin(a + 0.2)), p, 2)
    s.fill((60, 50, 50), (hub[0] - 1, hub[1] - 1, 3, 3))


def _floodlight(s, x, top, ground, lit=False):
    """A lattice mast with a lamp bank (glowing at night)."""
    m = pix.ramp((150, 156, 170))
    s.fill(m[0], (x - 2, top, 5, ground - top))
    s.fill(m[2], (x - 1, top, 3, ground - top))
    for y in range(top + 2, ground, 4):
        s.set_at((x - 1, y), m[3])
        s.set_at((x + 1, y + 2), m[1])
    s.fill(m[0], (x - 9, top - 9, 19, 10))
    s.fill(m[1], (x - 8, top - 8, 17, 8))
    for i in range(4):
        for j in range(2):
            c = (255, 252, 220) if lit else (230, 236, 246)
            s.fill(c, (x - 7 + i * 4, top - 7 + j * 4, 3, 3))
            s.set_at((x - 7 + i * 4, top - 7 + j * 4), (255, 255, 255) if lit else (255, 255, 255))


def _light_cone(s, x, y, length, spread, col, density=4):
    g = pygame.Surface((spread * 2 + 2, length), pygame.SRCALPHA)
    pygame.draw.polygon(g, (255, 255, 255), [(spread - 3, 0), (spread + 4, 0), (spread * 2, length), (0, length)])
    pix.dither_shade(s, pix.mask(g), col, density, (x - spread, y))


def _grandstand(L, x, w, rng, night=False, roof_col=(196, 60, 52)):
    """A covered grandstand: a striped roof on posts, tiered benches packed with
    fans (faces, hair, shirts; some cheering, a few waving flags), a fascia
    with coloured panels and a floodlight mast."""
    seed = rng.random()

    def draw(s, x0):
        r = random.Random(seed)
        top, base = 128, 204
        st = pix.ramp((84, 88, 112) if not night else (54, 56, 80))
        rr = pix.ramp(roof_col)
        # back wall and tiers
        s.fill(st[0], (x0 - 1, top + 10, w + 2, base - top - 10))
        s.fill(st[1], (x0, top + 11, w, base - top - 11))
        flags = [(232, 72, 52), (40, 140, 230), (255, 196, 0), (120, 220, 60), (250, 250, 250)]
        seat_col = (54, 92, 200) if not night else (60, 64, 150)
        tiers = 4
        th = 13
        for i in range(tiers):
            ty = top + 20 + i * th                                # seat-back top of this row
            s.fill(st[2], (x0, ty + 6, w, 2))                     # the step under the row
            s.fill(st[3], (x0, ty + 6, w, 1))
            for fx in range(x0 + 2 + (i % 2) * 4, x0 + w - 8, 8):
                pix.seat(s, fx, ty, seat_col)
                if r.random() < 0.72:
                    cheer = r.choice((0, 0, 0, 1, 2)) if not night else r.choice((0, 0, 1, 2))
                    pix.fan(s, fx, ty - 1, r, cheer)
                    if r.random() < 0.04:                         # a flag on a stick
                        fc = r.choice(flags)
                        s.fill((90, 80, 70), (fx + 7, ty - 14, 1, 12))
                        s.fill(fc, (fx + 8, ty - 14, 6, 4))
                        s.fill(pix.shift(fc, 1), (fx + 8, ty - 14, 6, 1))
        # roof: overhang with stripes, a shadow under it, posts
        s.fill(rr[0], (x0 - 5, top - 1, w + 10, 12))
        s.fill(rr[2], (x0 - 4, top, w + 8, 10))
        for k in range(x0 - 4, x0 + w + 4, 6):
            s.fill(rr[3] if night is False else rr[1], (k, top, 3, 10))
        s.fill(rr[4], (x0 - 4, top, w + 8, 1))
        s.fill(rr[1], (x0 - 4, top + 8, w + 8, 2))
        pix.dither_shade(s, pygame.mask.Mask((w, 5), fill=True), st[0], 2, (x0, top + 11))
        for px in (x0 + 2, x0 + w // 2, x0 + w - 4):
            s.fill(st[0], (px - 1, top + 10, 4, base - top - 10))
            s.fill(pix.ramp((170, 174, 190))[2], (px, top + 10, 2, base - top - 10))
        # fascia with panels
        s.fill(st[0], (x0 - 1, base - 9, w + 2, 10))
        for i, k in enumerate(range(x0, x0 + w, 24)):
            c = pix.ramp(flags[i % 4])
            s.fill(c[2], (k + 1, base - 8, 22, 7))
            s.fill(c[3], (k + 1, base - 8, 22, 1))
            s.fill(c[1], (k + 1, base - 2, 22, 1))
            s.fill((250, 250, 250), (k + 5, base - 6, 13, 1))
            s.fill((250, 250, 250), (k + 5, base - 4, 9, 1))
        _floodlight(s, x0 + w // 2, top - 30, top, lit=night)
        if night:
            _light_cone(s, x0 + w // 2, top - 26, 60, 40, (255, 250, 200), 4)

    L.rep(draw, x)


def _fence(L, rng, style="rail", banner_cols=None):
    """Trackside fence along FENCE_Y with banners and tyre stacks."""
    s, P = L.s, L.P
    y = FENCE_Y
    if style == "rail":
        post, rail = pix.ramp((220, 222, 232)), pix.ramp((246, 246, 250))
        for x in range(0, P, 16):
            s.fill(post[0], (x - 1, y - 1, 4, 20))
            s.fill(post[2], (x, y, 2, 18))
            s.set_at((x, y), post[4])
        for ry in (y, y + 9):
            s.fill(rail[0], (0, ry - 1, P, 4))
            s.fill(rail[2], (0, ry, P, 2))
            s.fill(rail[4], (0, ry, P, 1))
    elif style == "wood":
        w = pix.ramp((150, 104, 66))
        for x in range(0, P, 20):
            s.fill(w[0], (x - 1, y - 2, 5, 21))
            s.fill(w[2], (x, y - 1, 3, 19))
            s.fill(w[3], (x, y - 1, 1, 19))
        for ry in (y + 1, y + 9):
            s.fill(w[0], (0, ry - 1, P, 5))
            s.fill(w[2], (0, ry, P, 3))
            s.fill(w[3], (0, ry, P, 1))
            for x in range(0, P, 7):
                s.set_at((x, ry + 1), w[1])
    elif style == "steel":
        m = pix.ramp((110, 100, 104))
        for x in range(0, P, 24):
            s.fill(m[0], (x - 1, y - 2, 4, 21))
            s.fill(m[2], (x, y - 1, 2, 19))
        for ry in (y + 2, y + 10):
            s.fill(m[0], (0, ry - 1, P, 4))
            s.fill(m[2], (0, ry, P, 2))
            s.fill((255, 120, 40), (0, ry, P, 1)) if ry == y + 2 else None
    banner_cols = banner_cols or [(232, 72, 52), (40, 140, 230), (255, 196, 0), (120, 220, 60)]
    n = max(1, P // 160)
    for i in range(n):
        x = int(24 + i * P / n)
        c = pix.ramp(banner_cols[i % len(banner_cols)])
        kind = i % 3

        def banner(s, xx, c=c, kind=kind):
            s.fill(c[0], (xx - 1, y + 2, 58, 14))
            s.fill(c[2], (xx, y + 3, 56, 12))
            s.fill(c[3], (xx, y + 3, 56, 1))
            s.fill(c[1], (xx, y + 13, 56, 2))
            if kind == 0:                                     # chevrons
                for k in range(6):
                    px = xx + 6 + k * 8
                    pygame.draw.lines(s, (250, 250, 250), False, [(px, y + 5), (px + 3, y + 8), (px, y + 11)], 2)
            elif kind == 1:                                   # a star and stripes
                pygame.draw.polygon(s, (255, 240, 120), [(xx + 9, y + 4), (xx + 11, y + 8), (xx + 15, y + 8),
                                                         (xx + 12, y + 11), (xx + 13, y + 14), (xx + 9, y + 12),
                                                         (xx + 5, y + 14), (xx + 6, y + 11), (xx + 3, y + 8),
                                                         (xx + 7, y + 8)])
                for k in range(3):
                    s.fill((250, 250, 250), (xx + 20, y + 5 + k * 3, 32 - k * 8, 2))
            else:                                             # checkered flag panel
                for k in range(10):
                    for j in range(2):
                        if (k + j) % 2:
                            s.fill((30, 28, 36), (xx + 4 + k * 5, y + 5 + j * 4, 5, 4))
                        else:
                            s.fill((250, 250, 250), (xx + 4 + k * 5, y + 5 + j * 4, 5, 4))
        L.rep(banner, x)
    # marshals with flags and boards at the fence
    for i in range(max(2, P // 260)):
        x = int((i + 0.35) * P / max(2, P // 260))
        seed = rng.random()
        kind = "flag" if i % 2 == 0 else "board"
        L.rep(lambda s, xx, seed=seed, kind=kind: pix.marshal(s, xx, y + 18, random.Random(seed), kind,
                                                              (255, 214, 40) if kind == "flag" else (40, 160, 70)), x)
    # tyre stacks between banners
    for i in range(n):
        x = int(24 + (i + 0.5) * P / n) + 20

        def tyres(s, xx):
            t = pix.ramp((44, 40, 50))
            for k in range(3):
                ty = y + 14 - k * 5
                s.fill(t[0], (xx - 1, ty - 1, 14, 7))
                s.fill(t[2], (xx, ty, 12, 5))
                s.fill(t[3], (xx + 1, ty, 10, 1))
                s.fill(t[0], (xx + 4, ty + 1, 4, 3))
                s.fill((240, 240, 240) if k == 1 else t[1], (xx, ty + 4, 12, 1))
        L.rep(tyres, x)


# --- biomes ------------------------------------------------------------------------------------


def _valley(far, mid, rng, th):
    _sky(far, (74, 146, 236), (196, 230, 255))
    _sun(far, int(far.P * 0.78), 46, 13, (255, 246, 200), (220, 240, 255))
    _clouds(far, rng, 6, (24, 112), (255, 255, 255), (206, 222, 246), (166, 196, 236))
    _birds(far, rng, 5, (70, 90, 130))
    P = far.P
    h1 = _periodic(P, rng, [(2, 22), (5, 12), (9, 6)])
    _range(far, 168, lambda x: 40 + h1(x), (150, 178, 222), snow=None, haze=(186, 218, 250), outline=False,
           ridge_light=(214, 228, 250))
    h2 = _periodic(P, rng, [(3, 26), (7, 10), (13, 4)])
    _range(far, 188, lambda x: 46 + h2(x), (98, 140, 196), snow=146, haze=(170, 206, 246))
    # mid: two rows of hills, trees, a village
    h3 = _periodic(P, rng, [(2, 8), (5, 5)])
    ys = _range(mid, 214, lambda x: 32 + h3(x), (128, 196, 104), haze=None)
    _texture(mid, ys, (128, 196, 104), rng, P // 6)
    for i in range(P // 26):                                   # far tree line
        x = rng.randrange(P)
        seed = rng.random()
        kind = "pine" if rng.random() < 0.35 else "round"
        hh = rng.randint(12, 18)
        mid.rep(lambda s, xx, gy=int(ys[x]) + 3, hh=hh, kind=kind, seed=seed:
                pix.tree(s, xx, gy, hh, (70, 150, 80) if kind == "round" else (52, 120, 84), (110, 74, 50),
                         random.Random(seed), kind), x)
    for i in range(3):                                         # houses, a barn, a windmill
        x = int((i + 0.3 + rng.random() * 0.3) * P / 3)
        seed = rng.random()
        gy = int(ys[x]) + 6
        roof = rng.choice([(214, 76, 60), (60, 120, 200), (230, 150, 50)])
        mid.rep(lambda s, xx, gy=gy, seed=seed, roof=roof: _house(s, xx, gy, random.Random(seed), roof=roof), x)
        if i == 1:
            mid.rep(lambda s, xx, gy=gy: _barn(s, xx, gy, rng), x + 30)
        if i == 2:
            mid.rep(lambda s, xx, gy=gy: _windmill(s, xx, gy, rng), x - 26)
    h4 = _periodic(P, rng, [(3, 4), (8, 2)])
    ys2 = _range(mid, 226, lambda x: 18 + h4(x), (96, 172, 82))
    _texture(mid, ys2, (96, 172, 82), rng, P // 4)
    for i in range(P // 30):                                   # near trees and bushes
        x = rng.randrange(P)
        seed = rng.random()
        hh = rng.randint(20, 30)
        mid.rep(lambda s, xx, gy=int(ys2[x]) + 4, hh=hh, seed=seed:
                pix.tree(s, xx, gy, hh, (62, 156, 70), (120, 78, 50), random.Random(seed)), x)
    for i in range(P // 22):
        x = rng.randrange(P)
        seed = rng.random()
        mid.rep(lambda s, xx, gy=int(ys2[x]) + 8, seed=seed:
                pix.bush(s, xx, gy, 12, (80, 168, 70), random.Random(seed),
                         flowers=[(255, 120, 150), (255, 240, 120), (250, 250, 250)]), x)
    _stands_and_fence(mid, rng, th, roof=(204, 64, 56))


def _stands_and_fence(mid, rng, th, roof=(204, 64, 56), night=False, fence="rail"):
    if th["stands"]:
        P = mid.P
        n = 2
        for i in range(n):
            w = rng.choice((150, 174, 198))
            _grandstand(mid, int(i * P / n + 20 + rng.randint(0, P // n - w - 40)), w, rng, night=night,
                        roof_col=roof)
    _fence(mid, rng, fence)


def _desert(far, mid, rng, th):
    _sky(far, (238, 132, 92), (255, 228, 168))
    _sun(far, int(far.P * 0.3), 120, 22, (255, 236, 150), (255, 206, 140))
    for i in range(5):                                         # long thin clouds
        x, y, w = rng.randrange(far.P), rng.randint(20, 90), rng.randint(40, 110)
        seed = rng.random()
        far.rep(lambda s, xx, y=y, w=w, seed=seed: pix.cloud(s, xx, y, w, random.Random(seed), (255, 214, 190),
                                                              (240, 170, 150), None), x)
    P = far.P
    # buttes and mesas: flat tops, strata bands, shadowed right faces
    hz = _periodic(P, rng, [(2, 6), (5, 3)])
    _range(far, 186, lambda x: 22 + hz(x), (230, 168, 120), outline=False, haze=(250, 206, 150))
    for i in range(5):
        x = int((i + rng.random() * 0.5) * P / 5)
        w = rng.randint(40, 90)
        h = rng.randint(30, 62)
        seed = rng.random()
        far.rep(lambda s, xx, w=w, h=h, seed=seed: _mesa(s, xx, 186, w, h, random.Random(seed)), x)
    # mid: dunes with ripples, cacti, rocks, an adobe hut
    h3 = _periodic(P, rng, [(3, 8), (7, 4)])
    ys = _range(mid, 218, lambda x: 26 + h3(x), (236, 190, 124))
    for _ in range(P // 5):                                    # ripples
        x = rng.randrange(P)
        y = int(ys[x]) + rng.randint(4, 30)
        r = pix.ramp((236, 190, 124))
        mid.s.fill(r[1], (x, y, rng.randint(3, 7), 1))
        mid.s.fill(r[3], (x + 1, y - 1, rng.randint(2, 4), 1))
    for i in range(P // 40):
        x = rng.randrange(P)
        seed = rng.random()
        mid.rep(lambda s, xx, gy=int(ys[x]) + 10, seed=seed: _cactus(s, xx, gy, random.Random(seed)), x)
    for i in range(P // 50):
        x = rng.randrange(P)
        mid.rep(lambda s, xx, gy=int(ys[x]) + 14: pix.rock(s, xx, gy, 10, 6, (176, 120, 86)), x)
    x = rng.randrange(P)
    mid.rep(lambda s, xx: _adobe(s, xx, int(ys[x]) + 12), x)
    _fence(mid, rng, "wood", [(214, 60, 50), (40, 150, 170), (250, 180, 40)])


def _mesa(s, x, base, w, h, rng):
    r = pix.ramp((206, 120, 82))
    top = base - h
    inset = rng.randint(6, 12)
    pts = [(x - w // 2, base), (x - w // 2 + inset, top), (x + w // 2 - inset, top), (x + w // 2, base)]
    pygame.draw.polygon(s, r[0], [(px + (1 if px > x else -1), py - (1 if py == top else 0)) for px, py in pts])
    pygame.draw.polygon(s, r[2], pts)
    sh = [(x + w // 6, top), (x + w // 2 - inset, top), (x + w // 2, base), (x + w // 8, base)]
    pygame.draw.polygon(s, r[1], sh)
    for k in range(1, 5):                                      # strata
        yy = top + h * k // 5
        c = r[3] if k % 2 else pix.shift(r[1], 0)
        x0 = x - w // 2 + inset - inset * k // 5
        pygame.draw.line(s, c, (x0 + 1, yy), (x + w // 6, yy))
        pygame.draw.line(s, r[0] if k % 2 else r[1], (x + w // 6, yy), (x + w // 2 - inset + inset * k // 5 - 1, yy))
    pygame.draw.line(s, r[4], (x - w // 2 + inset, top), (x + w // 6, top))


def _cactus(s, x, ground, rng):
    g = pix.ramp((84, 156, 84))
    h = rng.randint(16, 24)

    def stem(x0, y0, w, hh):
        s.fill(g[0], (x0 - 1, y0 - 1, w + 2, hh + 2))
        s.fill(g[2], (x0, y0, w, hh))
        s.fill(g[3], (x0 + 1, y0, 1, hh))
        s.fill(g[1], (x0 + w - 1, y0 + 1, 1, hh - 1))
        s.set_at((x0 + 1, y0), g[4])
    stem(x - 3, ground - h, 6, h)
    for side in (-1, 1):
        if rng.random() < 0.85:
            ay = ground - h + rng.randint(5, 9)
            ax = x - 3 - 5 if side < 0 else x + 3 + 1
            s.fill(g[0], (min(ax, ax + 4) - 1, ay + 3, 6, 5))
            stem(ax, ay, 4, 7)
            s.fill(g[2], (ax if side < 0 else ax - 1, ay + 5, 5, 3))
    for k in range(ground - h + 3, ground, 3):                 # spines
        s.set_at((x - 4, k), (250, 240, 200))
        s.set_at((x + 3, k + 1), (250, 240, 200))
    if rng.random() < 0.5:
        s.fill((255, 110, 150), (x - 1, ground - h - 2, 3, 2))
        s.set_at((x, ground - h - 3), (255, 200, 220))


def _adobe(s, x, ground):
    r = pix.ramp((222, 168, 116))
    s.fill(r[0], (x - 1, ground - 15, 28, 16))
    s.fill(r[2], (x, ground - 14, 26, 14))
    s.fill(r[1], (x + 20, ground - 14, 6, 14))
    s.fill(r[3], (x, ground - 14, 26, 1))
    for k in range(4):
        s.fill((120, 80, 50), (x + 2 + k * 6, ground - 13, 2, 2))
    s.fill(r[0], (x + 10, ground - 8, 6, 8))
    s.fill((70, 44, 36), (x + 11, ground - 7, 4, 7))
    s.fill(r[0], (x + 3, ground - 9, 4, 4))
    s.fill((90, 60, 50), (x + 4, ground - 8, 2, 2))


def _night(far, mid, rng, th):
    _sky(far, (10, 12, 38), (58, 52, 116), 10)
    _stars(far, rng, far.P // 4)
    _moon(far, int(far.P * 0.33), 52, 12)
    _clouds(far, rng, 3, (60, 100), (70, 74, 130), (44, 46, 96), None, 40, 80)
    P = far.P
    h1 = _periodic(P, rng, [(2, 20), (6, 9)])
    _range(far, 176, lambda x: 40 + h1(x), (50, 54, 100), outline=False, ridge_light=(110, 120, 190),
           haze=(70, 64, 130))
    h2 = _periodic(P, rng, [(3, 22), (8, 7)])
    ys = _range(far, 196, lambda x: 36 + h2(x), (36, 42, 78), ridge_light=(90, 100, 170))
    for _ in range(P // 20):                                   # lit windows on the hills
        x = rng.randrange(P)
        y = int(ys[x]) + rng.randint(6, 24)
        far.s.fill((255, 220, 120), (x, y, 2, 1))
    h3 = _periodic(P, rng, [(2, 8), (5, 4)])
    ys = _range(mid, 220, lambda x: 26 + h3(x), (34, 70, 70), ridge_light=(70, 120, 130))
    for i in range(P // 24):
        x = rng.randrange(P)
        seed = rng.random()
        hh = rng.randint(16, 26)
        kind = "pine" if rng.random() < 0.6 else "round"
        mid.rep(lambda s, xx, gy=int(ys[x]) + 5, hh=hh, seed=seed, kind=kind:
                pix.tree(s, xx, gy, hh, (36, 84, 84), (60, 44, 44), random.Random(seed), kind), x)
    for _ in range(P // 12):                                   # fireflies
        x, y = rng.randrange(P), rng.randint(170, 214)
        mid.s.set_at((x, y), (220, 255, 140))
    _stands_and_fence(mid, rng, th, roof=(70, 70, 150), night=True)


def _stadium(far, mid, rng, th):
    """Indoor arena: a dark roof with trusses and hanging lights, an upper deck
    of fans, a big screen, spotlight beams."""
    _sky(far, (22, 22, 40), (70, 74, 110), 8)
    s, P = far.s, far.P
    tr = pix.ramp((90, 94, 120))
    for y in range(16 - far.dy, 47, 30):                       # roof trusses, up into the extra room
        s = far.full
        y += far.dy
        s.fill(tr[0], (0, y - 1, P, 8))
        s.fill(tr[2], (0, y, P, 2))
        s.fill(tr[2], (0, y + 5, P, 2))
        for x in range(0, P, 12):
            pygame.draw.line(s, tr[1], (x, y + 1), (x + 6, y + 5))
            pygame.draw.line(s, tr[1], (x + 6, y + 5), (x + 12, y + 1))
    s = far.s
    for i in range(P // 80):                                   # hanging lamps with beams
        x = int((i + 0.5) * P / (P // 80))
        far.rep(lambda s, xx: (s.fill((40, 40, 54), (xx - 4, 53, 9, 5)), s.fill((255, 250, 210), (xx - 3, 57, 7, 2))), x)
        far.rep(lambda s, xx, i=i: _light_cone(s, xx, 59, 120, 26 + (i % 3) * 6, (200, 210, 255), 4), x)
    # upper deck: rows of tiny fans
    deck = pix.ramp((60, 62, 92))
    s.fill(deck[0], (0, 92, P, 70))
    s.fill(deck[1], (0, 94, P, 66))
    for row in range(5):                                       # seated fans, darker (further away)
        ty = 100 + row * 13
        s.fill(deck[2], (0, ty + 6, P, 2))
        for x in range((row % 2) * 4, P - 8, 8):
            pix.seat(s, x, ty, (44, 60, 140))
            if rng.random() < 0.8:
                pix.fan(s, x, ty - 1, rng, rng.choice((0, 0, 0, 1, 2)))
    pix.dither_shade(s, pygame.mask.Mask((P, 70), fill=True), deck[0], 4, (0, 92))
    # the big screen
    x = P // 2
    far.rep(lambda s, xx: _big_screen(s, xx - 40, 66), x)
    _range(mid, 214, lambda x: 0, (60, 64, 90), lit=False, outline=False)
    _stands_and_fence(mid, rng, th, roof=(150, 40, 60), fence="rail")


def _big_screen(s, x, y):
    s.fill((20, 18, 28), (x - 2, y - 2, 84, 46))
    s.fill((60, 62, 80), (x - 1, y - 1, 82, 44))
    s.fill((16, 30, 60), (x, y, 80, 42))
    for k in range(0, 42, 2):
        s.fill((22, 40, 80), (x, y + k, 80, 1))
    # a pixel bike + "HYPE!" blocks
    for i, col in enumerate(((255, 196, 0), (232, 72, 52), (40, 140, 230), (120, 220, 60))):
        s.fill(col, (x + 8 + i * 17, y + 8, 13, 6))
        s.fill(pix.shift(col, 1), (x + 8 + i * 17, y + 8, 13, 1))
    pygame.draw.circle(s, (240, 240, 250), (x + 26, y + 32), 5, 2)
    pygame.draw.circle(s, (240, 240, 250), (x + 52, y + 32), 5, 2)
    pygame.draw.polygon(s, (232, 72, 52), [(x + 28, y + 26), (x + 46, y + 22), (x + 50, y + 30), (x + 32, y + 30)])
    s.fill((255, 196, 0), (x + 38, y + 18, 6, 5))
    s.fill((20, 18, 28), (x + 38, y + 44, 4, 10))


def _volcano_peaks(far, rng, th):
    from ui.art import LAVA, LAVA_HOT, LAVA_DARK
    P = far.P
    for i in range(3):
        cx = int((i * 2 + 1) * P / 6) + rng.randrange(-30, 30)
        top = 72 + rng.randrange(20)
        half = 110 + rng.randrange(30)
        seed = rng.random()

        def volcano(s, x, top=top, half=half, seed=seed):
            r = random.Random(seed)
            rr = pix.ramp((70, 40, 46))
            base = 172
            pts = [(x - half, base), (x - 16, top), (x + 16, top), (x + half, base)]
            pygame.draw.polygon(s, rr[0], [(px + (1 if px > x else -1), py - 1) for px, py in pts])
            pygame.draw.polygon(s, rr[2], pts)
            pygame.draw.polygon(s, rr[1], [(x + 4, top), (x + 16, top), (x + half, base), (x + half // 4, base)])
            pygame.draw.line(s, rr[3], (x - half + 2, base - 1), (x - 15, top + 1))
            for k in range(5):                                 # gullies, inside the cone
                f = (k + 1) / 6
                gx = x - 16 + (32 * f)
                bx = x - half + 2 * half * f
                pygame.draw.line(s, rr[1] if bx < x else rr[0], (int(gx + (bx - gx) * 0.3), top + 18 + (k % 2) * 6),
                                 (int(bx * 0.8 + gx * 0.2), base - 4))
            pygame.draw.ellipse(s, LAVA_DARK, (x - 17, top - 4, 34, 9))
            pygame.draw.ellipse(s, LAVA, (x - 15, top - 3, 30, 6))
            pygame.draw.ellipse(s, LAVA_HOT, (x - 8, top - 2, 16, 3))
            for k in (-1, 1):
                xx, yy = x + k * 8, top + 2
                while yy < base - 10:
                    nx, ny = xx + k * r.randrange(2, 6), yy + r.randrange(6, 12)
                    pygame.draw.line(s, LAVA_DARK, (xx, yy), (nx, ny), 3)
                    pygame.draw.line(s, LAVA, (xx, yy), (nx, ny), 1)
                    s.set_at((xx, yy), LAVA_HOT)
                    xx, yy = nx, ny
            for j in range(4):                                 # smoke plume
                pix.cloud(s, x + j * 10, top - 16 - j * 16, 26 + j * 10, r, (100, 70, 80), (64, 40, 52), (40, 24, 34))
        far.rep(volcano, cx)


def _lava(far, mid, rng, th):
    from ui.art import LAVA, LAVA_HOT, LAVA_DARK
    _sky(far, (30, 6, 20), (176, 64, 34), 10)
    for _ in range(far.P // 10):                               # ash and embers
        far.s.set_at((rng.randrange(far.P), rng.randrange(170)), rng.choice((LAVA, LAVA_HOT, (90, 60, 60))))
    P = far.P
    h1 = _periodic(P, rng, [(3, 16), (7, 6)])
    _range(far, 180, lambda x: 34 + h1(x), (80, 40, 44), outline=False, ridge_light=(200, 80, 50), haze=(130, 50, 34))
    _volcano_peaks(far, rng, th)
    h3 = _periodic(P, rng, [(6, 6), (13, 3)])
    ys = _range(mid, 222, lambda x: 30 + h3(x) + ((x // 6) % 3) * 2, (60, 40, 44), ridge_light=(160, 70, 50))
    for i in range(P // 30):                                   # glowing cracks
        x = rng.randrange(P)
        y = int(ys[x]) + rng.randint(6, 26)
        pygame.draw.line(mid.s, LAVA_DARK, (x, y), (x + 6, y + 5), 2)
        pygame.draw.line(mid.s, LAVA, (x + 6, y + 5), (x + 3, y + 10), 1)
        mid.s.set_at((x + 6, y + 5), LAVA_HOT)
    for i in range(P // 40):                                   # obsidian spires
        x = rng.randrange(P)
        h = rng.randint(14, 30)
        mid.rep(lambda s, xx, gy=int(ys[x]) + 6, h=h: _spire(s, xx, gy, h), x)
    for i in range(P // 30):
        x = rng.randrange(P)
        mid.rep(lambda s, xx, gy=int(ys[x]) + 14: pix.rock(s, xx, gy, 12, 7, (70, 50, 54)), x)
    _fence(mid, rng, "steel", [(200, 60, 30), (255, 160, 40), (90, 80, 90)])


def _spire(s, x, ground, h):
    r = pix.ramp((44, 36, 52))
    pts = [(x - 5, ground), (x - 1, ground - h), (x + 1, ground - h), (x + 6, ground)]
    pygame.draw.polygon(s, r[0], [(x - 6, ground + 1), (x, ground - h - 1), (x + 7, ground + 1)])
    pygame.draw.polygon(s, r[2], pts)
    pygame.draw.polygon(s, r[1], [(x + 1, ground - h), (x + 6, ground), (x + 1, ground)])
    pygame.draw.line(s, (150, 120, 200), (x - 4, ground - 1), (x - 1, ground - h + 1))


BIOMES = {"valley": _valley, "desert": _desert, "night": _night, "stadium": _stadium, "lava": _lava}


def build(theme, th, width, height=None):
    """(far, mid) layers, each 2 x width, repeating every `width` px, the
    360 px design band drawn config.WORLD_DY px down."""
    height = height or C.VIEW_H
    rng = random.Random(_seed(theme))
    dy = C.WORLD_DY
    far = _Layer(width, height, alpha=False, dy=dy)
    mid = _Layer(width, height, alpha=True, dy=dy)
    BIOMES.get(theme, _valley)(far, mid, rng, th)
    return far.doubled(), mid.doubled()


def build_berm(th, width, theme="valley"):
    """The bank right behind the back lane (BERM_TOP..236): a packed-dirt
    slope with a lit lip, stones, grass tufts (not in the volcano or arena),
    repeating every `width` px. The renderer scrolls it with the track."""
    rng = random.Random(_seed(theme, 5))
    h = 12
    L = _Layer(width, h, alpha=False)
    base = th["berm"]
    r = pix.ramp(base)
    s = L.s
    s.fill(r[1], (0, 0, width, h))
    pix.dither_rows(s, 0, 3, width, 4, r[2], r[1])
    s.fill(r[2], (0, 0, width, 3))
    s.fill(r[3], (0, 0, width, 1))
    s.fill(r[0], (0, h - 1, width, 1))
    grassy = theme in ("valley", "night")
    for _ in range(width // 6):
        x = rng.randrange(width)
        y = rng.randint(2, h - 3)
        if rng.random() < 0.5:
            pix.pebble(s, x, y, base, big=rng.random() < 0.3)
        elif grassy:
            pix.tuft(s, x, min(3, y), th["grass"], rng, 3)
    if grassy:
        g = pix.ramp(th["grass"])
        for x in range(width):                                 # a ragged grass lip
            d = 1 + (x * 7 + x // 3) % 3
            s.fill(g[2], (x, 0, 1, d))
            if d == 3:
                s.set_at((x, 0), g[3])
    return L.doubled()
