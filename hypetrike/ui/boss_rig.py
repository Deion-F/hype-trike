"""The bosses' rigs: huge vehicles that fill all four lanes (bosses.BossChase).

Each rig is drawn in code on a local surface (W x H) whose rear sits at PX and
whose y runs from the screen's Y0 down, so lane L's ground line is at
GY0 + 20 L. The still parts are drawn once per boss and cached; wheels, lights
and the weak point (which tells you when and where to hit it) are drawn every
frame on top.
"""
import math
import random

import pygame

import config as C
from ui import pix
from bosses import BOSSES, RIG_LEN, ROOF_MIN

PX = 24                              # local x of the rig's rear
W, H = RIG_LEN + 2 * PX, 200
Y0 = C.lane_y(0) + C.LANE_SPACING // 2 + 2 - 130     # screen y of local y 0
GY0 = 130                            # local ground line of lane 0 (lane 3: GY0 + 60)
FRONT = GY0 + 20 * (C.LANES - 1)    # local ground line of the front lane
HIT = (110, 255, 140)                # every weak point's hit zone is marked in this green


def lane_gy(lane):
    return GY0 + 20 * lane


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


# --- drawing helpers (the sprite pipeline from ui/pix: every part shaded + outlined) -------
WHITE = (255, 255, 255)
OUT = (18, 12, 24)
METAL = (128, 132, 150)


def _R(s, base, rect, r=0, **kw):
    pix.part(s, base, lambda L: pygame.draw.rect(L, WHITE, rect, border_radius=r), **kw)


def _P(s, base, pts, **kw):
    pix.part(s, base, lambda L: pygame.draw.polygon(L, WHITE, pts), **kw)


def _C(s, base, c, rad, **kw):
    pix.part(s, base, lambda L: pygame.draw.circle(L, WHITE, c, rad), **kw)


def _E(s, base, rect, **kw):
    pix.part(s, base, lambda L: pygame.draw.ellipse(L, WHITE, rect), **kw)


def _rivets(s, base, x0, x1, y, step=9):
    r = pix.ramp(base)
    for x in range(x0, x1, step):
        s.set_at((x, y), r[4])
        s.set_at((x + 1, y), r[3])
        s.set_at((x + 1, y + 1), r[0])


def _seams(s, base, x0, x1, y0, y1, step=22):
    """Vertical panel seams: a dark groove with a lit edge beside it."""
    r = pix.ramp(base)
    for x in range(x0 + step, x1 - 2, step):
        s.fill(r[1], (x, y0, 1, y1 - y0))
        s.fill(r[3], (x + 1, y0, 1, y1 - y0))


def _grime(s, rect, col, seed=1, density=0.35):
    """Weathering: dithered dirt flecks getting denser toward the bottom of rect
    (only on pixels already drawn)."""
    x, y, w, h = rect
    r = pix.ramp(col)
    rng = random.Random(seed)
    for yy in range(y, y + h):
        k = (yy - y + 1) / max(1, h)
        for xx in range(x, x + w):
            if (xx + yy) % 2 == 0 and rng.random() < density * k * 2 and s.get_at((xx, yy))[3]:
                s.set_at((xx, yy), r[1] if rng.random() < 0.6 else r[2])


def _window(s, rect, glass=(120, 180, 220), frame=(60, 60, 72), r=3):
    """Outlined frame, glass in a vertical ramp, a lit top edge."""
    x, y, w, h = rect
    gr = pix.ramp(glass)
    pygame.draw.rect(s, OUT, (x - 2, y - 2, w + 4, h + 4), border_radius=r + 1)
    pygame.draw.rect(s, frame, (x - 1, y - 1, w + 2, h + 2), border_radius=r)
    pygame.draw.rect(s, gr[1], (x, y, w, h), border_radius=r)
    pygame.draw.rect(s, gr[2], (x, y, w, h * 2 // 3), border_radius=r)
    s.fill(gr[3], (x + 2, y + 1, w - 4, 1))


def _glints(s, rect, glass):
    """Two diagonal reflections across a window (drawn over whoever is inside)."""
    x, y, w, h = rect
    gr = pix.ramp(glass)
    pygame.draw.line(s, gr[4], (x + 2, y + h - 3), (x + 2 + h // 2, y + 2))
    pygame.draw.line(s, gr[3], (x + 6, y + h - 3), (x + 6 + h // 2, y + 2))


def _driver(s, x, y, liv, extra=None):
    """A boss at the wheel, seen through its window: shoulders in its suit and
    the rider head (helmet, goggles, face, hair) from the bikes."""
    from ui import art
    sr = pix.ramp(liv["suit"])
    s.fill(OUT, (x - 2, y + 8, 14, 9))
    s.fill(sr[2], (x - 1, y + 9, 12, 8))
    s.fill(sr[3], (x - 1, y + 9, 6, 1))
    s.fill(sr[1], (x + 8, y + 10, 2, 7))
    s.blit(art.head_sprite(liv), (x, y))
    if extra:
        extra(s, x, y)


def _wheel(surf, x, y, r, spin, tyre=(36, 30, 36), hub=(160, 156, 170), spokes=4):
    """A rig wheel: outlined tyre with chunky tread blocks that turn with it, a
    lit sidewall, a stepped rim, spokes, a bolt ring and a capped hub."""
    tr, hr = pix.ramp(tyre), pix.ramp(hub)
    pygame.draw.circle(surf, OUT, (x, y), r + 2)
    for k in range(12):                                  # tread blocks proud of the tyre
        a = spin * 0.5 + k * math.pi / 6
        pygame.draw.circle(surf, tr[2], (round(x + math.cos(a) * (r + 0.5)), round(y + math.sin(a) * (r + 0.5))), 2)
    pygame.draw.circle(surf, tr[2], (x, y), r)
    for k in range(18):                                  # lit sidewall arc, top-left
        a = math.radians(190 + k * 4)
        surf.set_at((round(x + (r - 1) * math.cos(a)), round(y + (r - 1) * math.sin(a))), tr[3])
    pygame.draw.circle(surf, tr[1], (x, y), r - 2, 1)
    rim = max(3, r // 2 + 1)
    pygame.draw.circle(surf, tr[0], (x, y), rim + 1)
    pygame.draw.circle(surf, hr[1], (x, y), rim)
    pygame.draw.circle(surf, hr[2], (x - 1, y - 1), rim - 1)
    for k in range(spokes):
        a = spin + k * math.pi / spokes
        dx, dy = math.cos(a) * (rim - 1), math.sin(a) * (rim - 1)
        pygame.draw.line(surf, hr[0], (x - dx, y - dy), (x + dx, y + dy), 2 if r > 9 else 1)
    if r > 9:
        for k in range(5):                               # bolt ring
            a = spin + k * math.tau / 5
            surf.set_at((round(x + math.cos(a) * 3), round(y + math.sin(a) * 3)), hr[4])
    pygame.draw.circle(surf, hr[3], (x, y), 2)
    surf.set_at((x - 1, y - 1), hr[4])


def _far_wheel(s, x, y, r):
    pygame.draw.circle(s, OUT, (x, y), r + 1)
    pygame.draw.circle(s, (30, 26, 32), (x, y), r)
    pygame.draw.circle(s, (46, 42, 52), (x, y), r // 2)
    pygame.draw.arc(s, (56, 52, 64), (x - r + 1, y - r + 1, 2 * r - 2, 2 * r - 2), math.radians(100),
                    math.radians(170), 1)


def _hazard(s, rect, step=8):
    """Yellow / black hazard stripes clipped to rect, outlined."""
    x, y, w, h = rect
    layer = pygame.Surface((w, h), pygame.SRCALPHA)
    layer.fill((34, 30, 38))
    for k in range(-h, w, step):
        pygame.draw.polygon(layer, (246, 200, 40), [(k, h), (k + h, 0), (k + h + step // 2, 0), (k + step // 2, h)])
    layer.fill((255, 236, 140), (0, 0, w, 1))
    s.blit(layer, (x, y))
    pygame.draw.rect(s, OUT, (x - 1, y - 1, w + 2, h + 2), 1)


GHOST = ["..oooo..", ".oWWwwo.", "oWWwwwwo", "owewwewo", "owwwwwwo", "owwmmwwo", "owwwwwwo", "ow.ww.wo",
         ".o.oo.o."]


# --- the still body, per boss -----------------------------------------------------------
def _body_valley(s, info):
    """MUD HAULER: a battered dump truck heaped with glossy mud, the Mud Baron in
    its cab, a hazard-striped tailgate with a hatch per lane."""
    from ui import art
    body, dark = info["body"], info["dark"]
    for x in (PX + 30, PX + 104, PX + 180):                       # far-side wheels
        _far_wheel(s, x, GY0 - 4, 15)
    _R(s, dark, (PX, FRONT - 40, RIG_LEN, 22), 2, shine=True)     # chassis rail
    _rivets(s, dark, PX + 4, PX + RIG_LEN - 4, FRONT - 36)
    _rivets(s, dark, PX + 4, PX + RIG_LEN - 4, FRONT - 24)
    bed = [(PX - 2, 66), (PX + 144, 66), (PX + 140, FRONT - 22), (PX + 4, FRONT - 22)]
    _P(s, body, bed, hi=2, lo=3)
    br = pix.ramp(body)
    for x in range(PX + 20, PX + 140, 24):                         # raised ribs
        s.fill(br[0], (x - 1, 70, 6, FRONT - 94))
        s.fill(br[2], (x, 70, 4, FRONT - 94))
        s.fill(br[3], (x, 70, 1, FRONT - 94))
        s.fill(br[1], (x + 3, 70, 1, FRONT - 94))
        _rivets(s, body, x + 1, x + 3, 76, 9)
    s.fill(br[3], (PX, 67, 142, 1))
    pygame.draw.line(s, br[0], (PX + 6, 104), (PX + 30, 106))       # dents
    pygame.draw.line(s, br[3], (PX + 6, 105), (PX + 30, 107))
    _grime(s, (PX + 2, FRONT - 52, 140, 30), (90, 66, 42), 3, 0.5)
    mud = (100, 74, 46)
    pix.canopy(s, PX + 70, 60, 156, 34, mud, random.Random(7), clumps=14)   # a heap of glossy mud
    mr = pix.ramp(mud)
    for x in (PX + 20, PX + 70, PX + 118):                          # drips down the side
        n = 18 + x % 13
        _R(s, mud, (x, 74, 6, n), 3, shine=True)
        _C(s, mud, (x + 3, 74 + n), 3)
        s.set_at((x + 2, 78), mr[4])
    for x, y in ((PX + 40, 50), (PX + 96, 46), (PX + 120, 56)):    # wet glints on the heap
        s.fill(mr[4], (x, y, 2, 1))
        s.set_at((x + 3, y + 1), mr[4])
    # cab: rounded box, the Mud Baron at the wheel, a door with a skull, a grille, a lamp
    cab = pygame.Rect(PX + 148, 84, 58, FRONT - 22 - 84)
    cb = _shade(body, 1.1)
    _R(s, cb, cab, 6, hi=2, lo=2, shine=True)
    win = (cab.x + 22, cab.y + 8, 30, 24)
    _window(s, win, (150, 190, 200))
    liv = art.livery(art.boss_key("valley"))

    def mask(s, x, y):                                              # bone face guard
        s.fill((236, 228, 206), (x + 5, y + 7, 5, 2))
        s.fill((150, 140, 120), (x + 5, y + 9, 5, 1))
    _driver(s, cab.x + 33, cab.y + 13, liv, mask)
    _glints(s, win, (150, 190, 200))
    door = pygame.Rect(cab.x + 4, cab.y + 36, 30, cab.h - 42)
    pygame.draw.rect(s, pix.ramp(cb)[0], door, 1, border_radius=2)
    s.fill(pix.ramp(METAL)[3], (door.right - 7, door.y + 4, 4, 2))
    sx, sy = cab.x + 18, cab.y + 50                                 # bone skull on the door
    _E(s, (232, 226, 206), (sx - 9, sy - 10, 18, 17), shine=True)
    _R(s, (232, 226, 206), (sx - 6, sy + 5, 12, 6), 1, hi=0)
    for ex in (-4, 4):
        pygame.draw.circle(s, (34, 24, 20), (sx + ex, sy - 2), 3)
        s.set_at((sx + ex - 1, sy - 3), (90, 70, 60))
    for k in range(3):
        s.fill((120, 110, 96), (sx - 4 + k * 4, sy + 6, 1, 4))
    _R(s, (70, 70, 80), (cab.right - 6, cab.bottom - 26, 8, 20), 1)  # grille
    for y in range(cab.bottom - 24, cab.bottom - 7, 3):
        s.fill((30, 30, 36), (cab.right - 5, y, 6, 1))
    _C(s, (255, 236, 150), (cab.right + 1, cab.y + 40), 3, shine=True)  # headlamp
    _R(s, (70, 66, 74), (cab.x + 4, cab.y - 26, 8, 30), 1, shine=True)  # exhaust stack
    _R(s, (52, 48, 56), (cab.x + 2, cab.y - 29, 12, 4), 1)
    s.fill((20, 16, 20), (cab.x + 5, cab.y - 29, 6, 2))
    # tailgate: hazard stripes round a hatch per lane
    _R(s, (64, 60, 66), (PX - 13, 69, 17, FRONT - 69), 1)
    _hazard(s, (PX - 11, 70, 13, 26))
    _hazard(s, (PX - 11, FRONT - 26, 13, 20))


def _body_desert(s, info):
    """SAND CRAWLER: an armoured half-track with a bone-ribbed sail fin, three
    goggle lamps, plates weathered by sand and the Dune Raider up front."""
    from ui import art
    body, dark = info["body"], info["dark"]
    _R(s, (46, 40, 36), (PX + 50, GY0 - 18, RIG_LEN - 54, 18), 9)     # far track
    _R(s, dark, (PX + 2, 140, RIG_LEN - 4, 26), 2, shine=True)        # side skirt over the tracks
    _rivets(s, dark, PX + 6, PX + RIG_LEN - 6, 158, 10)
    hull = [(PX, 64), (PX + 168, 64), (PX + RIG_LEN, 108), (PX + RIG_LEN, 148), (PX, 148)]
    _P(s, body, hull, hi=2, lo=3, shine=True)
    br = pix.ramp(body)
    for y in (88, 116):                                             # armour plate rows
        s.fill(br[1], (PX + 2, y, 166, 1))
        s.fill(br[3], (PX + 2, y + 1, 166, 1))
        _rivets(s, body, PX + 5, PX + 160, y + 4, 11)
    _seams(s, body, PX, PX + 170, 68, 146)
    _rivets(s, body, PX + 5, PX + 166, 69, 11)
    _grime(s, (PX + 2, 122, RIG_LEN - 2, 26), (196, 160, 104), 5, 0.6)
    for x, y in ((PX + 44, 98), (PX + 130, 128), (PX + 90, 76)):   # scrapes
        pygame.draw.line(s, br[3], (x, y), (x + 9, y - 2))
        pygame.draw.line(s, br[1], (x, y + 1), (x + 9, y - 1))
    # sail fin with bone ribs, a scarf flag on top
    _P(s, _shade(body, 0.78), [(PX + 60, 64), (PX + 96, 18), (PX + 112, 64)], hi=1, lo=1)
    for k in range(4):
        x0 = PX + 66 + k * 11
        pygame.draw.line(s, (236, 226, 200), (x0, 63), (PX + 90 + k * 3, 30 + k * 7), 2)
        pygame.draw.line(s, (170, 150, 120), (x0 + 1, 63), (PX + 91 + k * 3, 31 + k * 7), 1)
    _P(s, (210, 64, 50), [(PX + 96, 20), (PX + 58, 28), (PX + 70, 32), (PX + 60, 38), (PX + 92, 36)], shine=True)
    # cockpit with the Dune Raider (orange goggles, a red scarf)
    win = (PX + 150, 70, 26, 20)
    _window(s, win, (220, 170, 110), (90, 70, 50))
    liv = art.livery(art.boss_key("desert"))

    def goggles(s, x, y):
        s.fill((255, 160, 40), (x + 4, y + 4, 6, 2))
        s.set_at((x + 7, y + 4), (255, 240, 200))
        s.fill((210, 40, 40), (x - 1, y + 9, 9, 2))
    _driver(s, PX + 160, 73, liv, goggles)
    _glints(s, win, (220, 170, 110))
    for i in range(3):                                              # goggle lamps
        c = (PX + 180 + i * 8, 106 + i * 7)
        pygame.draw.circle(s, OUT, c, 7)
        pygame.draw.circle(s, (70, 60, 50), c, 6)
        pygame.draw.circle(s, (255, 216, 120), c, 4)
        pygame.draw.circle(s, (255, 244, 200), (c[0] - 1, c[1] - 1), 2)
        s.set_at((c[0] - 2, c[1] - 2), (255, 255, 255))
    # the vent housing up top (louvres; the hit zone glows over it live)
    _R(s, dark, (PX - 4, 40, 34, 26), 4, shine=True)
    dr = pix.ramp(dark)
    for y in range(46, 62, 4):
        s.fill(dr[0], (PX + 18, y, 9, 2))
        s.fill(dr[3], (PX + 18, y + 2, 9, 1))


def _body_night(s, info):
    """GHOST TRAIN: a midnight coach with an arched roof, neon trim, arched
    windows with ghosts peering out, a smokestack, a cowcatcher and the hooded
    Phantom at the controls."""
    from ui import art
    body, trim = info["body"], info["trim"]
    for x in range(PX + 20, PX + RIG_LEN, 32):                       # far-side wheels
        _far_wheel(s, x, GY0 - 3, 11)
    coach = pygame.Rect(PX, 70, RIG_LEN - 18, FRONT - 22 - 70)
    _R(s, body, coach, 10, hi=2, lo=3)
    roof = _shade(body, 1.4)
    _E(s, roof, (PX - 4, 56, RIG_LEN - 10, 34), hi=2, lo=1, shine=True)   # arched roof
    rr = pix.ramp(roof)
    for x in range(PX + 14, PX + RIG_LEN - 20, 14):                 # roof ribs
        top = 58 + int(((x - PX - 100) / 100) ** 2 * 12)
        s.fill(rr[1], (x, top + 2, 1, 86 - top))
    tr = pix.ramp(trim)
    for y in (100, FRONT - 34):                                     # neon trim lines
        s.fill(tr[0], (PX, y - 1, RIG_LEN - 18, 5))
        s.fill(tr[2], (PX, y, RIG_LEN - 18, 3))
        s.fill(tr[4], (PX, y, RIG_LEN - 18, 1))
    ghost = pix.grid(GHOST, {"o": (70, 50, 110), "w": (226, 218, 255), "W": (255, 255, 255),
                             "e": (50, 26, 80), "m": (120, 60, 140)})
    for i, x in enumerate(range(PX + 22, PX + RIG_LEN - 30, 36)):   # arched windows, a ghost in each
        r = pygame.Rect(x, 108, 24, 36)
        pygame.draw.rect(s, OUT, r.inflate(4, 4), border_radius=12)
        pygame.draw.rect(s, (70, 50, 110), r.inflate(2, 2), border_radius=11)
        pygame.draw.rect(s, (120, 90, 190), r, border_radius=10)
        pygame.draw.rect(s, (190, 160, 255), r.inflate(-6, -6), border_radius=8)
        pix.dither_shade(s, pygame.mask.Mask((18, 8), fill=True), (150, 120, 230), 2, (x + 3, 133))
        g = ghost if i % 2 == 0 else pygame.transform.flip(ghost, True, False)
        s.blit(g, (x + 8, 116 + (i % 2) * 4))
        s.fill((250, 246, 255), (x + 5, 112, 1, 6))                 # glass glint
    nose = [(PX + RIG_LEN - 18, 78), (PX + RIG_LEN + 4, 120), (PX + RIG_LEN + 4, FRONT - 22),
            (PX + RIG_LEN - 18, FRONT - 22)]
    _P(s, _shade(body, 0.85), nose, shine=True)
    win = (PX + RIG_LEN - 42, 74, 20, 20)                           # the Phantom's cab window
    _window(s, win, (120, 90, 180), (40, 30, 60), 2)
    liv = art.livery(art.boss_key("night"))

    def hood(s, x, y):
        pygame.draw.polygon(s, (36, 28, 58), [(x - 1, y + 9), (x + 1, y - 2), (x + 7, y - 3), (x + 10, y + 1),
                                              (x + 6, y + 2), (x + 3, y + 9)])
        pygame.draw.line(s, (80, 60, 120), (x + 1, y - 1), (x + 7, y - 2))
        s.set_at((x + 7, y + 5), (230, 180, 255))
        s.set_at((x + 9, y + 5), (230, 180, 255))
    _driver(s, PX + RIG_LEN - 37, 78, liv, hood)
    _glints(s, win, (120, 90, 180))
    _C(s, (255, 236, 170), (PX + RIG_LEN + 1, 132), 4, shine=True)  # head lamp
    _R(s, (36, 32, 48), (PX + RIG_LEN - 60, 30, 16, 40), 2, shine=True)     # smokestack
    _R(s, trim, (PX + RIG_LEN - 64, 26, 24, 7), 2, shine=True)
    cc = [(PX + RIG_LEN + 4, FRONT - 22), (PX + RIG_LEN + 16, FRONT - 2), (PX + RIG_LEN - 10, FRONT - 2)]
    _P(s, (110, 104, 122), cc, shine=True)                          # cowcatcher with slats
    for k in range(4):
        pygame.draw.line(s, (60, 56, 70), (PX + RIG_LEN - 6 + k * 5, FRONT - 3),
                         (PX + RIG_LEN + 2 + k * 2, FRONT - 20))
    _R(s, (22, 18, 32), (PX - 10, 76, 12, FRONT - 22 - 76), 2)      # lantern rack on its tail


def _figure(s, x, ground, head, suit, cape=None):
    """A performer standing on the float, arms up: legs, a body in its suit,
    a head sprite (face, hair) on top. About 10 px wide from x."""
    sr = pix.ramp(suit)
    if cape:
        cr = pix.ramp(cape)
        pygame.draw.polygon(s, cr[0], [(x + 2, ground - 17), (x - 5, ground - 1), (x + 5, ground - 3)])
        pygame.draw.polygon(s, cr[2], [(x + 2, ground - 15), (x - 3, ground - 2), (x + 4, ground - 4)])
    s.fill(OUT, (x + 2, ground - 8, 6, 8))
    s.fill(sr[1], (x + 3, ground - 8, 1, 7))
    s.fill(sr[2], (x + 5, ground - 8, 2, 7))
    s.fill(OUT, (x + 1, ground - 17, 8, 10))
    s.fill(sr[2], (x + 2, ground - 16, 6, 8))
    s.fill(sr[3], (x + 2, ground - 16, 3, 1))
    for ax in (x, x + 8):                                    # arms up
        s.fill(OUT, (ax - 1, ground - 26, 3, 11))
        s.fill(sr[2], (ax, ground - 22, 1, 6))
        s.fill(pix.ramp(pix.SKINS[1])[2], (ax, ground - 25, 1, 3))
    s.blit(head, (x + 5 - head.get_width() // 2, ground - 16 - head.get_height() + 1))


def _body_stadium(s, info):
    """PARADE FLOAT: a velvet skirt with a gold fringe, a stage with speaker
    stacks, a giant jewelled crown and the Showstopper performing with two
    backup dancers."""
    from ui import art
    body, dark, trim = info["body"], info["dark"], info["trim"]
    skirt = pygame.Rect(PX, 128, RIG_LEN, FRONT - 12 - 128)
    _R(s, body, skirt, 0, hi=1, lo=2)
    br = pix.ramp(body)
    for x in range(PX + 6, PX + RIG_LEN, 12):                       # velvet folds
        s.fill(br[1], (x, 132, 2, FRONT - 146))
        s.fill(br[3], (x + 5, 132, 1, FRONT - 146))
    for x in range(PX, PX + RIG_LEN, 12):                            # gold fringe balls
        _C(s, trim, (x + 6, FRONT - 12), 5, shine=True, lo=1)
    _R(s, trim, (PX, 125, RIG_LEN, 6), 0, shine=True)
    for x in range(PX + 8, PX + RIG_LEN - 8, 16):                    # studs on the trim
        s.set_at((x, 127), (255, 255, 230))
    stage = pygame.Rect(PX + 8, 84, RIG_LEN - 16, 44)
    _R(s, dark, stage, 0, hi=1, lo=1)
    dr = pix.ramp(dark)
    for x in range(stage.x + 8, stage.right, 8):                    # back-wall boards
        s.fill(dr[1], (x, stage.y + 2, 1, 30))
    _R(s, (220, 200, 160), (stage.x, stage.y + 34, stage.w, 8), 0, hi=1, lo=1)   # stage deck
    for x in (PX + 30, PX + RIG_LEN - 50):                           # speaker stacks
        _R(s, (34, 30, 40), (x, 52, 30, 76), 2, shine=True)
        for y in (64, 94):
            pygame.draw.circle(s, OUT, (x + 15, y), 12)
            pygame.draw.circle(s, (80, 76, 92), (x + 15, y), 11)
            pygame.draw.circle(s, (54, 50, 62), (x + 15, y), 8)
            pygame.draw.circle(s, (22, 20, 26), (x + 15, y), 4)
            s.set_at((x + 11, y - 7), (150, 146, 170))
        for k in range(4):
            s.fill((60, 56, 70), (x + 4 + k * 6, 112, 3, 8))         # grille
    cx = PX + RIG_LEN // 2 + 4                                      # the giant crown
    crown = [(cx - 34, 84), (cx - 34, 40), (cx - 18, 58), (cx, 26), (cx + 18, 58), (cx + 34, 40), (cx + 34, 84)]
    _P(s, trim, crown, hi=2, lo=2, shine=True)
    tr = pix.ramp(trim)
    s.fill(tr[1], (cx - 33, 74, 67, 2))
    s.fill(tr[3], (cx - 33, 76, 67, 1))
    for px, py in ((cx - 34, 40), (cx, 26), (cx + 34, 40)):
        _C(s, (250, 250, 240), (px, py), 3, shine=True)
    for gx, col in ((cx - 18, (230, 60, 80)), (cx, (90, 160, 255)), (cx + 18, (90, 220, 120))):
        _C(s, col, (gx, 66), 5, shine=True)
    for x in (PX + 12, PX + RIG_LEN - 12):                           # light poles
        _R(s, (90, 86, 100), (x - 2, 20, 4, 66), 0, lo=0)
    # performers on the stage deck: the Showstopper (crowned helmet, cape) and two dancers
    liv = art.livery(art.boss_key("stadium"))
    king = art.head_sprite(liv).copy()
    for dx in (2, 4, 6):
        king.set_at((dx, 0), (255, 215, 60))
    _figure(s, cx - 5, 118, king, liv["suit"], cape=(200, 26, 46))
    rng = random.Random(11)
    for fx in (PX + 66, PX + RIG_LEN - 80):
        _figure(s, fx, 118, pix.face(rng.choice(["long", "bun", "bob"]), rng.choice(pix.SKINS),
                                     rng.choice(pix.HAIRS)), rng.choice([(250, 120, 170), (60, 200, 220)]))


def _body_lava(s, info):
    """MAGMA TANKER: a riveted tank banded with steel straps, glowing cracks
    and flame decals, a horned cab with the Inferno's eyes behind its glowing
    visor, an armoured core hatch on its tail."""
    body, dark, trim = info["body"], info["dark"], info["trim"]
    for x in (PX + 36, PX + 110, PX + 182):
        _far_wheel(s, x, GY0 - 4, 15)
    _R(s, dark, (PX, FRONT - 40, RIG_LEN, 22), 2, shine=True)
    _rivets(s, dark, PX + 4, PX + RIG_LEN - 4, FRONT - 36)
    tank = pygame.Rect(PX + 6, 70, 148, FRONT - 36 - 70)
    _R(s, body, tank, 30, hi=3, lo=4, shine=True)
    glow = pix.ramp((255, 110, 30))
    for pts in (((PX + 40, 82), (PX + 50, 104), (PX + 44, 124), (PX + 58, 146)),
                ((PX + 92, 76), (PX + 86, 100), (PX + 100, 120)),
                ((PX + 112, 96), (PX + 124, 118), (PX + 118, 140))):       # glowing cracks with a halo
        for p in pts:
            g = pygame.Surface((16, 16), pygame.SRCALPHA)
            pygame.draw.circle(g, WHITE, (8, 8), 7)
            pix.dither_shade(s, pix.mask(g).overlap_mask(pix.mask(s), (p[0] - 8, p[1] - 8)), glow[1], 4,
                             (p[0] - 8, p[1] - 8))
        pygame.draw.lines(s, (90, 20, 10), False, pts, 5)
        pygame.draw.lines(s, glow[2], False, pts, 3)
        pygame.draw.lines(s, (255, 230, 120), False, pts, 1)
    for x in (PX + 28, PX + 78, PX + 128):                          # steel straps
        _R(s, (96, 90, 96), (x, 71, 7, tank.h - 2), 1, shine=True)
        for y in range(76, tank.bottom - 4, 10):
            s.set_at((x + 3, y), (200, 196, 210))
    for x in (PX + 40, PX + 100):                                      # flame decals
        _P(s, trim, [(x, 150), (x + 10, 122), (x + 14, 134), (x + 18, 116), (x + 24, 134), (x + 27, 126),
                     (x + 34, 150)], shine=True)
        pygame.draw.polygon(s, (255, 220, 90), [(x + 10, 150), (x + 17, 134), (x + 24, 150)])
    _grime(s, (PX + 8, tank.bottom - 18, 146, 16), (40, 20, 18), 9, 0.5)
    cab = pygame.Rect(PX + 158, 92, 48, FRONT - 22 - 92)
    cb = _shade(body, 1.3)
    _R(s, cb, cab, 6, hi=2, lo=2, shine=True)
    _seams(s, cb, cab.x, cab.right, cab.y + 30, cab.bottom - 4, 16)
    vis = pygame.Rect(cab.x + 16, cab.y + 9, 26, 15)                   # glowing visor, the Inferno's eyes
    pygame.draw.rect(s, OUT, vis.inflate(4, 4), border_radius=4)
    pygame.draw.rect(s, (200, 70, 20), vis, border_radius=3)
    pygame.draw.rect(s, (255, 150, 40), vis.inflate(-2, -4), border_radius=3)
    s.fill((255, 230, 140), (vis.x + 3, vis.y + 2, vis.w - 6, 1))
    for ex in (vis.x + 9, vis.x + 16):
        s.fill((60, 10, 10), (ex, vis.y + 6, 3, 2))
        s.set_at((ex + 1, vis.y + 6), (255, 255, 200))
    for hx, d in ((cab.x + 8, -1), (cab.x + 40, 1)):                  # horns
        _P(s, (230, 220, 200), [(hx - 5, cab.y + 2), (hx + 5, cab.y + 2), (hx + 12 * d, cab.y - 22)], shine=True)
        pygame.draw.line(s, (170, 150, 130), (hx, cab.y - 2), (hx + 7 * d, cab.y - 12))
    _C(s, (255, 200, 90), (cab.right, cab.y + 44), 3, shine=True)     # headlamp
    _R(s, (46, 42, 48), (PX - 6, 92, 18, FRONT - 36 - 92), 2, shine=True)   # the armoured core hatch


BODIES = {"valley": _body_valley, "desert": _body_desert, "night": _body_night,
          "stadium": _body_stadium, "lava": _body_lava}
_cache = {}


def body(biome):
    if biome not in _cache:
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        BODIES[biome](s, BOSSES[biome])
        _cache[biome] = pix.silhouette(s, OUT)
    return _cache[biome]


# --- the live parts ------------------------------------------------------------------------
class Look:
    """What the rig shows right now (a BossChase, or a still for the intro portrait)."""

    def __init__(self, chase=None, now=0, bike=None):
        self.weak = chase.weak if chase else None
        self.shield = chase.shield(now) if chase else "closed"
        self.lantern = chase.lantern if chase else 1
        self.lantern_next = chase.lantern_next if chase else None
        self.spot = chase.spotlit(now) if chase else False
        self.brake = chase.in_window(now) if chase else False
        self.flash = max(0, 12 - (now - chase.flash_at)) if chase else 0
        self.wrecked = chase.outcome == "won" if chase else False
        self.wreck_t = (now - chase.wrecked_at) if chase and chase.wrecked_at is not None else 0
        self.speed = chase.speed if chase else 0.0
        self.x = chase.x if chase else 0.0
        self.hot = bool(bike and chase and chase.weak == "core" and chase.weak_open(bike, now))
        self.open = bool(bike and chase and chase.outcome is None and chase.weak_open(bike, now))
        self.lane = bike.lane_index if bike else 1


def draw(surf, biome, sx_rear, t, look):
    """Draw the rig with its rear at screen x sx_rear."""
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (0, 0, 0, 70), (PX - 10, GY0 - 6, RIG_LEN + 30, FRONT - GY0 + 20))   # shadow
    s.blit(body(biome), (0, 0))
    spin = -look.x / 18.0
    _live(s, biome, t, look, spin)
    if look.brake:                                                     # brake lights: it's slowing for you
        for y in (FRONT - 12, 46):                                       # clear of the lanterns
            pygame.draw.rect(s, (255, 40, 40), (PX - 2, y, 7, 8))
            pygame.draw.circle(s, (255, 90, 90, 90), (PX + 1, y + 4), 10)
    if look.open and not look.wrecked:                                 # ram it now and it counts
        k = 120 + int(100 * abs(((t % 20) - 10) / 10))
        pygame.draw.rect(s, (120, 255, 120, k), (PX - 14, 24, 8, FRONT - 22), border_radius=3)
    if look.flash and look.flash % 4 < 2:                           # a quick double flash
        s.fill((min(150, 13 * look.flash),) * 3, special_flags=pygame.BLEND_RGB_ADD)
    bob = int(math.sin(t * 0.35) * 1.2) if look.speed > 1 else 0
    if look.wrecked:
        s.fill((60, 60, 60), special_flags=pygame.BLEND_RGB_SUB)
        k = min(1.0, look.wreck_t / 40)
        s = pygame.transform.rotate(s, -7 * k)
        bob = int(10 * k)
    surf.blit(s, (int(sx_rear - PX), Y0 + bob))


def _live(s, biome, t, look, spin):
    info = BOSSES[biome]
    glow = info["glow"]
    pulse = 0.6 + 0.4 * (1 + math.sin(t * 0.2)) / 2
    if biome == "valley":
        for x in (PX + 30, PX + 104, PX + 180):
            _wheel(s, x, FRONT - 16, 18, spin, tyre=(40, 32, 26))
        _hatches(s, t, look, glow, pulse)
    elif biome == "desert":
        _track(s, PX + 50, PX + RIG_LEN + 2, FRONT - 26, FRONT, spin)
        _track(s, PX - 2, PX + 48, FRONT - 26, FRONT, spin)
        _roof_zone(s, t, look, glow, pulse)
    elif biome == "night":
        for x in range(PX + 20, PX + RIG_LEN - 20, 32):
            _wheel(s, x, FRONT - 12, 11, spin, tyre=(24, 20, 30), hub=(120, 100, 150))
        pygame.draw.line(s, (120, 100, 150), (PX + 20 + math.cos(spin) * 5, FRONT - 12 + math.sin(spin) * 5),
                         (PX + 180 + math.cos(spin) * 5, FRONT - 12 + math.sin(spin) * 5), 3)    # coupling rod
        _lanterns(s, t, look, glow)
    elif biome == "stadium":
        for x in range(PX + 20, PX + RIG_LEN, 44):
            _wheel(s, x, FRONT - 6, 8, spin, spokes=2)
        for i, x in enumerate((PX + 12, PX + RIG_LEN - 12)):          # blinking bulbs on the poles
            for k in range(4):
                on = (t // 8 + k + i) % 2
                pygame.draw.circle(s, (255, 240, 160) if on else (120, 100, 60), (x, 24 + k * 14), 4)
        cx, cy = PX + 2, 104                                           # the spotlight lens on its tail
        lit = look.spot
        pygame.draw.circle(s, (40, 36, 48), (cx, cy), 18)
        pygame.draw.circle(s, (255, 250, 210) if lit else (110, 100, 70), (cx, cy), 13)
        if lit:
            pygame.draw.circle(s, (*glow, 90), (cx, cy), 24, 4)
        for k in range(5):                                             # a star on the lens
            a = t * 0.05 + k * 1.2566
            pygame.draw.line(s, (200, 150, 40), (cx, cy), (cx + math.cos(a) * 11, cy + math.sin(a) * 11), 2)
    else:                                                              # lava
        for x in (PX + 36, PX + 110, PX + 182):
            _wheel(s, x, FRONT - 16, 17, spin, tyre=(30, 20, 18), hub=(120, 70, 50))
        hot = look.hot
        for k, y in enumerate(range(96, FRONT - 40, 14)):              # armour plates over the core
            col = (255, 240, 200) if hot and (t // 3 + k) % 2 else ((200, 80, 40) if hot else (90, 84, 90))
            pygame.draw.rect(s, col, (PX - 4, y, 14, 11), border_radius=2)
        pygame.draw.circle(s, _shade((255, 120, 30), pulse), (PX + 3, (96 + FRONT - 40) // 2), 6)


def _track(s, x0, x1, y0, y1, spin):
    """A crawler track: road wheels inside a tread band whose cleats run round
    with the wheels' spin, a lit top run, an outline."""
    h = y1 - y0
    tr = pix.ramp((58, 50, 44))
    pygame.draw.rect(s, OUT, (x0 - 1, y0 - 1, x1 - x0 + 2, h + 2), border_radius=h // 2 + 1)
    pygame.draw.rect(s, tr[2], (x0, y0, x1 - x0, h), border_radius=h // 2)
    pygame.draw.rect(s, tr[1], (x0 + 3, y0 + 3, x1 - x0 - 6, h - 6), border_radius=h // 2 - 3)
    off = int(-spin * 6) % 6
    for x in range(x0 + h // 2 + off, x1 - h // 2, 6):          # cleats, top and bottom runs
        s.fill(tr[3], (x, y0, 3, 2))
        s.fill(tr[0], (x, y1 - 2, 3, 2))
    for x in range(x0 + 11, x1 - 8, 22):
        _wheel(s, x, y0 + h // 2, 8, spin, tyre=(40, 34, 30), spokes=3)


def _hatches(s, t, look, glow, pulse):
    """Mud Hauler: a hatch per lane on its tailgate. The lit one is the target; its
    shield drops over it and only lifts while the rig brakes."""
    for lane in range(C.LANES):
        gy = lane_gy(lane)
        slot = pygame.Rect(PX - 14, gy - 21, 18, 18)
        target = lane == look.lantern
        pygame.draw.rect(s, (30, 28, 32), slot, border_radius=2)
        if not target:
            continue
        open_ = look.shield == "open"
        pygame.draw.circle(s, (*HIT, int(60 + 60 * pulse)), slot.center, 22)              # halo
        core = (255, 255, 210) if open_ else _shade(HIT, pulse)
        pygame.draw.rect(s, core, slot.inflate(-4, -4), border_radius=2)
        ring = 2 + int(3 * pulse)
        pygame.draw.rect(s, HIT, slot.inflate(8 + ring, 8 + ring), 3, border_radius=4)
        if open_:
            pygame.draw.rect(s, (160, 160, 170), (slot.x - 2, slot.y - 22, slot.w + 4, 8), border_radius=2)  # lifted
            pygame.draw.circle(s, (*HIT, 140), slot.center, 26, 4)
        else:
            warn = look.shield == "warn"
            col = (240, 200, 40) if warn and (t // 4) % 2 else (150, 150, 160)
            lift = 4 if warn and (t // 4) % 2 else 0
            pygame.draw.rect(s, col, (slot.x - 2, slot.y - 2 - lift, slot.w + 4, slot.h + 4), border_radius=2)
            pygame.draw.line(s, (90, 90, 100), (slot.x, slot.centery - lift), (slot.right, slot.centery - lift), 2)
            pygame.draw.circle(s, (60, 60, 70), (slot.centerx, slot.centery - lift), 3)       # the lock


def _lanterns(s, t, look, glow):
    """Ghost Train: a lantern per lane on its tail, all burning alike (decoys) in the
    light. While its lights flicker they all gutter; once it's dark only the soul
    lantern is still lit (its glow is drawn again over the dark: soul_glow)."""
    dark = look.weak == "soul" and look.shield == "open"
    flicker = look.weak == "soul" and look.shield == "warn"
    for lane in range(C.LANES):
        y = lane_gy(lane) - 18
        if dark:
            lit = False                                             # soul_glow draws the one left burning
        elif flicker:
            lit = (t // 4 + lane * 3) % 5 != 0
        else:
            lit = True
        if lit:
            pygame.draw.circle(s, (*glow, 60), (PX - 6, y), 15)
        _lantern(s, PX - 6, y, lit, t + lane * 5)


def _lantern(s, cx, cy, lit, t, col=None):
    """An iron lantern: a bail on top, a cap and base, bars over the glass and
    (when lit) a flickering flame inside."""
    s.fill(OUT, (cx - 7, cy - 8, 14, 17))
    pygame.draw.arc(s, (90, 84, 104), (cx - 4, cy - 13, 8, 8), 0, math.pi, 1)    # bail
    s.fill((70, 64, 84), (cx - 6, cy - 7, 12, 3))                 # cap
    s.fill((110, 104, 124), (cx - 6, cy - 7, 12, 1))
    s.fill((70, 64, 84), (cx - 6, cy + 5, 12, 3))                 # base
    glass = col or ((240, 225, 255) if lit else (40, 34, 56))
    gr = pix.ramp(glass)
    s.fill(gr[2], (cx - 5, cy - 4, 10, 9))
    if lit:
        s.fill(gr[3], (cx - 5, cy - 4, 10, 2))
        fl = 2 + (t // 4) % 2
        pygame.draw.polygon(s, (255, 255, 255), [(cx - 2, cy + 4), (cx, cy + 1 - fl), (cx + 2, cy + 4)])
        s.set_at((cx, cy + 3), (255, 230, 150))
    for bx in (cx - 2, cx + 2):                                   # bars
        s.fill((70, 64, 84), (bx, cy - 4, 1, 9))


def soul_glow(surf, sx_rear, t, look):
    """Drawn over the Phantom's darkness: the soul lantern still burning (with the
    green hit ring), and its next lane blinking before it hops."""
    if look.weak != "soul" or look.shield != "open" or look.wrecked:
        return
    pulse = 0.6 + 0.4 * (1 + math.sin(t * 0.25)) / 2
    for lane, main in ((look.lantern, True), (look.lantern_next, False)):
        if lane is None or (not main and (t // 5) % 2):
            continue
        x, y = int(sx_rear - 6), int(Y0 + lane_gy(lane) - 18)
        halo = pygame.Surface((80, 80), pygame.SRCALPHA)
        pygame.draw.circle(halo, (200, 170, 255, int(70 * pulse) if main else 40), (40, 40), 34)
        pygame.draw.circle(halo, (235, 220, 255, int(110 * pulse) if main else 60), (40, 40), 18)
        surf.blit(halo, (x - 40, y - 40))
        _lantern(surf, x, y, True, t, None if main else (190, 140, 255))
        if main:
            ring = 12 + int(3 * pulse)
            pygame.draw.rect(surf, HIT, (x - ring, y - ring, 2 * ring, 2 * ring), 3, border_radius=4)


def _roof_zone(s, t, look, glow, pulse):
    """Sand Crawler: its vent sits up top; anything above the dashed line (for your
    lane, ROOF_MIN up) on its tail counts. The whole zone glows."""
    floor = lane_gy(look.lane) - ROOF_MIN                       # wheels above this line hit
    zone = pygame.Surface((26, max(1, floor - 30)), pygame.SRCALPHA)
    zone.fill((*HIT, int(70 + 70 * pulse)))
    s.blit(zone, (PX - 18, 30))
    pygame.draw.rect(s, HIT, (PX - 18, 30, 26, floor - 30), 3)
    for x in range(PX - 18, PX + 8, 6):                         # the "above this" line
        pygame.draw.line(s, (255, 255, 255), (x, floor), (x + 3, floor), 2)
    for k in range(3):                                          # chevrons pointing up
        y = floor - 12 - k * 12 - (t // 4) % 6
        pygame.draw.lines(s, (255, 255, 255), False, [(PX - 11, y + 4), (PX - 5, y), (PX + 1, y + 4)], 2)
    cx, cy = PX + 13, 52                                        # the vent itself
    pygame.draw.circle(s, _shade(HIT, pulse), (cx, cy), 10)
    for k in range(4):
        a = t * 0.15 + k * 1.57
        pygame.draw.line(s, (80, 60, 30), (cx, cy), (cx + math.cos(a) * 9, cy + math.sin(a) * 9), 2)


def portrait(biome, t, scale=0.6):
    """The rig still, scaled, for the boss intro."""
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    s.blit(body(biome), (0, 0))
    _live(s, biome, t, Look(), t * 0.1)
    return pygame.transform.smoothscale(s, (int(W * scale), int(H * scale)))


def on_screen(sx_rear, width):
    return sx_rear - PX < width and sx_rear + RIG_LEN + PX > 0
