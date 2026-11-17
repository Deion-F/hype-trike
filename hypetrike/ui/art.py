"""Procedural pixel art: vehicles, rider, themes. Everything is drawn in code,
so there are no external image assets (decision I.5)."""
import math
import random

import pygame

import config as C
from ui import pix

# --- liveries (palette swaps, meta unlockables) ------------------------------
LIVERIES = {
    "flame":  dict(name="Flame",  body=(232, 72, 52),  dark=(150, 36, 40),  suit=(250, 236, 220), helmet=(255, 196, 0)),
    "ocean":  dict(name="Ocean",  body=(40, 140, 230), dark=(26, 76, 150),  suit=(230, 240, 255), helmet=(250, 250, 250)),
    "lime":   dict(name="Lime",   body=(120, 220, 60), dark=(50, 130, 40),  suit=(36, 36, 44),    helmet=(120, 220, 60)),
    "violet": dict(name="Violet", body=(160, 90, 230), dark=(90, 50, 150),  suit=(255, 220, 240), helmet=(255, 120, 200)),
    "gold":   dict(name="Gold",   body=(240, 190, 40), dark=(160, 110, 20), suit=(30, 30, 30),    helmet=(240, 240, 240)),
    "ghost":  dict(name="Ghost",  body=(220, 224, 236), dark=(140, 146, 170), suit=(60, 64, 90),  helmet=(220, 224, 236)),
}
RIVAL_LIVERIES = ["ocean", "lime", "violet", "gold"]


def livery_key(bike, rider=None):
    """Sprite key for a bike paint plus a rider kit (mix and match): "ocean"
    when they match, "ocean+gold" when the rider wears a different scheme."""
    bike = bike if bike in LIVERIES else "flame"
    rider = rider if rider in LIVERIES else bike
    return bike if rider == bike else f"{bike}+{rider}"


def livery(key):
    """Colours for a livery key (see livery_key): the bike's body/dark from the
    bike paint, the rider's suit/helmet/stripe from the rider scheme."""
    if str(key).startswith("boss:"):
        biome = str(key)[5:]
        return dict(BOSS_LIVERIES.get(biome, LIVERIES["flame"]), hair=BOSS_HAIR.get(biome, (60, 40, 30)))
    if str(key).startswith("minion:"):
        return _minion_livery(str(key)[7:])
    bike, _, rider = str(key).partition("+")
    base = dict(LIVERIES.get(bike, LIVERIES["flame"]))
    if rider in LIVERIES:
        r = LIVERIES[rider]
        base.update(suit=r["suit"], helmet=r["helmet"], accent=r["body"])
    base["hair"] = HAIR.get(rider if rider in LIVERIES else bike, HAIR["flame"])
    return base


# --- biome bosses: themed paint + epic extras drawn over the normal bike ----------------
BOSS_LIVERIES = {
    "valley": dict(name="Mud Baron", body=(104, 116, 52), dark=(72, 54, 32), suit=(92, 72, 46),
                   helmet=(66, 74, 40), accent=(214, 196, 130)),
    "desert": dict(name="Dune Raider", body=(222, 182, 112), dark=(150, 90, 40), suit=(204, 164, 104),
                   helmet=(236, 214, 172), accent=(210, 40, 40)),
    "night": dict(name="Phantom", body=(40, 30, 70), dark=(150, 70, 255), suit=(24, 20, 40),
                  helmet=(236, 236, 246), accent=(170, 90, 255)),
    "stadium": dict(name="Showstopper", body=(250, 250, 250), dark=(230, 180, 30), suit=(200, 30, 40),
                    helmet=(255, 215, 60), accent=(255, 215, 60)),
    "lava": dict(name="Inferno", body=(44, 22, 22), dark=(210, 40, 20), suit=(30, 24, 28),
                 helmet=(22, 16, 20), accent=(255, 120, 30)),
}
RIDER_LEAN = {"sprinter": 2, "trike": -1}


def boss_key(biome):
    return f"boss:{biome}"


def minion_key(biome):
    return f"minion:{biome}"


def _minion_livery(biome):
    """A boss's colours, a shade darker: its minions read as its crew."""
    base = dict(BOSS_LIVERIES.get(biome, LIVERIES["flame"]), hair=BOSS_HAIR.get(biome, (60, 40, 30)))
    for k in ("body", "suit", "helmet"):
        base[k] = tuple(int(c * 0.82) for c in base[k])
    return base


livery_colors = livery          # alias used by the sprite cache


def bike_paint(key):
    return str(key).partition("+")[0]


# --- boost colours: the exhaust heat flame, boost sparks and speed streaks ----------------
# Per stage (cold / boost / red window): (outer, mid, core) at the start and end of
# the stage. The red window stays the most intense and flickers in every scheme.
BOOSTS = {
    "flame": dict(name="Flame",
                  cold=(((255, 215, 70), (255, 240, 150), (255, 255, 235)),
                        ((255, 185, 50), (255, 230, 120), (255, 255, 230))),
                  boost=(((255, 130, 25), (255, 205, 70), (255, 250, 210)),
                         ((240, 70, 20), (255, 150, 40), (255, 225, 160))),
                  red=(((200, 15, 15),) * 3, ((200, 15, 15), (255, 60, 30), (255, 170, 120))),
                  sparks=((255, 200, 70), (255, 130, 40)), streak=((255, 70, 35), (255, 150, 50))),
    "plasma": dict(name="Plasma",
                   cold=(((150, 220, 255), (200, 240, 255), (245, 252, 255)),
                         ((110, 200, 255), (180, 230, 255), (240, 250, 255))),
                   boost=(((40, 150, 255), (110, 200, 255), (225, 245, 255)),
                          ((30, 90, 240), (80, 170, 255), (200, 235, 255))),
                   red=(((150, 40, 230),) * 3, ((150, 40, 230), (200, 90, 255), (240, 200, 255))),
                   sparks=((140, 220, 255), (60, 140, 255)), streak=((170, 80, 255), (90, 180, 255))),
    "toxic": dict(name="Toxic",
                  cold=(((200, 245, 120), (225, 255, 170), (245, 255, 225)),
                        ((170, 240, 90), (210, 255, 140), (240, 255, 215))),
                  boost=(((110, 220, 40), (180, 250, 90), (235, 255, 200)),
                         ((60, 190, 30), (140, 235, 70), (220, 255, 170))),
                  red=(((40, 120, 20),) * 3, ((40, 120, 20), (200, 230, 30), (250, 255, 160))),
                  sparks=((190, 255, 90), (90, 210, 40)), streak=((220, 240, 40), (120, 230, 60))),
    "neon": dict(name="Neon",
                 cold=(((255, 170, 230), (255, 205, 240), (255, 240, 250)),
                       ((255, 130, 215), (255, 185, 235), (255, 235, 250))),
                 boost=(((255, 70, 190), (255, 150, 220), (255, 230, 245)),
                        ((230, 30, 160), (255, 100, 200), (255, 210, 240))),
                 red=(((160, 20, 200),) * 3, ((160, 20, 200), (255, 40, 150), (255, 190, 230))),
                 sparks=((255, 150, 230), (230, 60, 190)), streak=((255, 40, 170), (200, 90, 255))),
    "gold": dict(name="Gold",
                 cold=(((255, 240, 150), (255, 248, 200), (255, 255, 240)),
                       ((255, 225, 110), (255, 240, 170), (255, 255, 235))),
                 boost=(((255, 200, 40), (255, 230, 110), (255, 252, 220)),
                        ((240, 170, 20), (255, 215, 70), (255, 245, 190))),
                 red=(((210, 120, 10),) * 3, ((210, 120, 10), (255, 190, 30), (255, 250, 200))),
                 sparks=((255, 230, 110), (255, 190, 40)), streak=((255, 180, 30), (255, 240, 140))),
    "ghost": dict(name="Ghost",
                  cold=(((215, 225, 240), (235, 240, 250), (255, 255, 255)),
                        ((195, 210, 235), (225, 232, 248), (255, 255, 255))),
                  boost=(((170, 190, 230), (215, 225, 250), (255, 255, 255)),
                         ((140, 160, 220), (195, 210, 245), (250, 252, 255))),
                  red=(((90, 100, 150),) * 3, ((90, 100, 150), (190, 200, 240), (255, 255, 255))),
                  sparks=((230, 236, 255), (170, 185, 230)), streak=((200, 210, 255), (255, 255, 255))),
}


def boost_palette(name):
    return BOOSTS.get(name, BOOSTS["flame"])

TIRE = (40, 36, 48)
RIM = (176, 178, 192)
METAL = (128, 132, 150)
ENGINE = (78, 80, 96)
SEAT = (44, 40, 52)
SKIN = (240, 190, 150)
BOOT = (48, 44, 56)
WHITE = (244, 244, 250)
SPRING = (230, 180, 50)
PIPE = (176, 140, 104)

# Hair under each rider kit's helmet (keyed by the rider scheme), and bosses'.
HAIR = {"flame": (120, 60, 34), "ocean": (236, 200, 110), "lime": (40, 32, 36), "violet": (240, 120, 180),
        "gold": (60, 42, 32), "ghost": (200, 204, 220)}
BOSS_HAIR = {"valley": (70, 52, 36), "desert": (30, 26, 30), "night": (230, 230, 240),
             "stadium": (255, 210, 80), "lava": (40, 20, 22)}

SPR_W, SPR_H = 52, 54
CONTACT = (26, 48)   # ground contact point (midpoint between wheels) on the 52x54 design grid
DIRT_PAD = 4         # the bikes are designed on a 52x50 grid that sits this far down
HAND = (35, 17)      # rider's glove on the grip (52x50 grid)
HANDGUARD = (37, 17) # where the coloured hand guard sits

# Sprites are drawn pixel by pixel at their in-race size (config.SPRITE_SCALE of
# the design grid) with an O px margin all round for outlines. The margin is the
# same on every side, so the canvas centre-to-contact offset (blit_rotated) is
# unchanged. Bigger views (garage) scale these up by whole numbers.
K = C.SPRITE_SCALE
O = 2
NW, NH = round(SPR_W * K) + 2 * O, round(SPR_H * K) + 2 * O


class _Pen:
    """Maps design-grid points (52x50, fy-style y) to the native canvas. Sprung
    parts move with `bob`; wheels and the swingarm's axle end don't."""

    def __init__(self, bob):
        self.bob = bob

    def __call__(self, x, y, sprung=True):
        return (round(x * K) + O, round((y + DIRT_PAD) * K) + O + (self.bob if sprung else 0))

    def pts(self, pts, sprung=True):
        return [self(x, y, sprung) for x, y in pts]

    def w(self, width):
        return max(1, round(width * K))


def _canvas():
    return pygame.Surface((NW, NH), pygame.SRCALPHA)


def _wheel(s, c, frame, r=5, knobs=12, chunky=False, far=False, disc=False, slick=False, accent=None):
    """Off-road wheel at native size: a thick knobby tyre (knobs stand proud of
    the outline and turn half a step per frame) with a lit sidewall, a thin
    two-tone rim, dark spokes and a hub with a glint. slick + accent: the
    sprinter's cast wheel with a coloured rim stripe."""
    cx, cy = c
    tr = pix.ramp((24, 22, 30) if far else TIRE)
    rr = pix.ramp((120, 122, 136) if far else RIM)
    pygame.draw.circle(s, tr[0], c, r + 1)
    pygame.draw.circle(s, tr[2], c, r)
    if not slick:
        n = 9 if chunky else knobs
        for i in range(n):
            a = (i + frame * 0.5) * math.tau / n
            px, py = cx + (r + 1) * math.cos(a), cy + (r + 1) * math.sin(a)
            s.fill(tr[2] if not chunky else tr[1], (round(px - 0.5 * chunky), round(py - 0.5 * chunky),
                                                     1 + chunky, 1 + chunky))
    for i in range(20):                                    # lit sidewall, top-left
        a = math.radians(185 + i * 4)
        s.set_at((round(cx + r * math.cos(a)), round(cy + r * math.sin(a))), tr[3])
    rim_r = r - 2
    if slick:
        pygame.draw.circle(s, pix.ramp(ENGINE)[1], c, rim_r)
        pygame.draw.circle(s, accent or rr[2], c, rim_r, 1)
        for i in range(5):
            a = (i + frame * 0.5) * math.tau / 5
            pygame.draw.line(s, rr[3], c, (round(cx + (rim_r - 1) * math.cos(a)), round(cy + (rim_r - 1) * math.sin(a))))
    else:
        pygame.draw.circle(s, tr[1], c, rim_r)
        for i in range(16):                                # rim: lit top-left, shaded bottom-right
            a = math.radians(i * 22.5)
            d = math.cos(a) + math.sin(a)
            s.set_at((round(cx + rim_r * math.cos(a)), round(cy + rim_r * math.sin(a))),
                     rr[3] if d < -0.6 else rr[1] if d > 0.6 else rr[2])
        for i in range(2):
            a = (i + frame * 0.5) * math.pi / 2 + math.pi / 4
            d = rim_r - 1
            pygame.draw.line(s, rr[0], (round(cx - d * math.cos(a)), round(cy - d * math.sin(a))),
                             (round(cx + d * math.cos(a)), round(cy + d * math.sin(a))))
    if disc:
        s.set_at((cx + 1, cy + 1), rr[1])
    s.fill(pix.ramp(METAL)[2], (cx - 1, cy - 1, 2, 2))
    s.set_at((cx - 1, cy - 1), rr[4])


def _line_part(s, base, a, b, width, **kw):
    pix.part(s, base, lambda L: pygame.draw.line(L, (255, 255, 255), a, b, width), **kw)


def _poly_part(s, base, pts, **kw):
    pix.part(s, base, lambda L: pygame.draw.polygon(L, (255, 255, 255), pts), **kw)


# --- rider -----------------------------------------------------------------------------
# Head facing right, 10x10: a motocross helmet (dome, peak, chin bar), goggles with
# a lens glint, the face showing between goggles and chin bar, hair out the back.
#   o outline  1 shell shadow  2 shell  3 shell light  4 shine
#   A peak / stripe (accent)  a accent shadow
#   G goggle frame  L lens  l glint  S skin  s skin shadow  h hair  d hair shadow  m mouth
_HEAD = [
    "...oooo...",
    ".oo3344oo.",
    "o3332AAAAo",
    "o322Aaoaao",
    "o22oGGGGGo",
    "o21GLLlLGo",
    "dh1oGGGGSo",
    "hd1oo2Sso.",
    ".hd1o222o.",
    "..doooooo.",
]
# Thrown / jogging rider's head: same helmet, 9 px, face turned to the viewer.
_HEAD_FRONT = [
    "..oooo...",
    ".o3344o..",
    "o3332AAo.",
    "oGGGGGGo.",
    "oGLlGLLGo",
    "oGGGGGGo.",
    "hoSsmsSoh",
    "d.o222o.d",
    "...ooo...",
]


def _head_pal(liv):
    hr = pix.ramp(liv["helmet"])
    ar = pix.ramp(liv.get("accent", liv["body"]))
    kr = pix.ramp(SKIN)
    hair = pix.ramp(liv.get("hair", (90, 60, 40)))
    lens = pix.ramp(liv.get("lens", (90, 170, 230)))
    return {"o": hr[0], "1": hr[1], "2": hr[2], "3": hr[3], "4": hr[4], "A": ar[2], "a": ar[1],
            "G": (34, 30, 44), "L": lens[2], "l": (250, 252, 255), "S": kr[2], "s": kr[1],
            "h": hair[2], "d": hair[1], "m": (150, 70, 70)}


def head_sprite(liv, front=False):
    return pix.grid(_HEAD_FRONT if front else _HEAD, _head_pal(liv))


def _rider(s, liv, pen, hip, hand, lean=0):
    """Rider in a jersey + pants + boots, design-grid geometry (same pose and
    proportions as ever), drawn natively: shaded limbs, a jersey stripe and
    sleeve cuffs, boot buckles, gloves and the detailed head."""
    suit = liv["suit"]
    acc = liv.get("accent", liv["body"])
    hx, hy = hip
    knee, boot = (hx + 6, hy + 4), (hx + 3, hy + 9)
    sh = (hx + 6 + lean, hy - 10)
    pants = pix.shift(suit, -1) if sum(suit) > 300 else suit
    # leg: thigh along the seat, shin down to the peg, knee pad
    pix.part(s, pants, lambda L: (pygame.draw.line(L, (255, 255, 255), pen(hx, hy), pen(*knee), 2),
                                  pygame.draw.line(L, (255, 255, 255), pen(*knee), pen(*boot), 2)))
    kp = pen(*knee)
    s.fill(pix.ramp(acc)[2], (kp[0] - 1, kp[1] - 1, 2, 1))
    bp = pen(*boot)
    pix.part(s, BOOT, lambda L: L.fill((255, 255, 255), (bp[0] - 1, bp[1] - 1, 4, 2)))
    s.set_at((bp[0], bp[1] - 1), pix.ramp(BOOT)[4])                         # buckle
    # torso + jersey stripe
    pix.part(s, suit, lambda L: pygame.draw.line(L, (255, 255, 255), pen(hx, hy), pen(*sh), 4), hi=1, lo=1)
    a0, a1 = pen(hx + 1, hy - 3), pen(sh[0], sh[1] + 2)
    pygame.draw.line(s, pix.ramp(acc)[2], a0, a1)
    pygame.draw.line(s, pix.ramp(acc)[1], (a0[0] + 1, a0[1]), (a1[0] + 1, a1[1]))
    # arm to the bars, a cuff, the glove
    hp = pen(*hand)
    pix.part(s, suit, lambda L: pygame.draw.line(L, (255, 255, 255), pen(*sh), hp, 2))
    pix.part(s, BOOT, lambda L: L.fill((255, 255, 255), (hp[0] - 1, hp[1] - 1, 2, 2)), hi=0)
    hc = pen(sh[0] + 3, sh[1] - 5)
    s.blit(head_sprite(liv), (hc[0] - 4, hc[1] - 5))


def _bars(s, pen, dark):
    pygame.draw.line(s, pix.ramp(METAL)[3], pen(35, 20), pen(36, 18))
    _line_part(s, dark, pen(33, 19), pen(37, 16), 1, hi=0, lo=0)


def _handguard(s, pen, body):
    gx, gy = HANDGUARD
    _poly_part(s, body, pen.pts([(gx, gy - 3), (gx + 3, gy - 2), (gx + 3, gy + 1), (gx, gy + 2)]), hi=1, lo=0)


def _frame_common(s, pen, frame, rw, fw, wy, wheel_kw_r=None, wheel_kw_f=None):
    """Shock, swingarm, fork and both wheels."""
    sp = pix.ramp(SPRING)
    a, b = pen(19, 27), pen(22, 33, sprung=False)
    for i, (x, y) in enumerate(_pts_on(a, b)):                              # coil spring: bright/dark turns
        s.set_at((x, y), sp[3] if i % 2 else sp[1])
        s.set_at((x + 1, y), sp[2])
    _line_part(s, METAL, pen(rw, wy, False), pen(23, 33, False), 2, lo=1)
    fk = pix.ramp((96, 98, 116))
    _line_part(s, fk[2], pen(fw, wy, False), pen(35, 21), 2, lo=0)
    pygame.draw.line(s, pix.ramp(RIM)[3], pen(fw - 1, wy - 3, False), pen(36, 22))   # stanchion shine
    _wheel(s, pen(rw, wy, False), frame, **(wheel_kw_r or {}))
    _wheel(s, pen(fw, wy, False), frame, disc=True, **(wheel_kw_f or {}))


def _pts_on(a, b):
    n = max(abs(b[0] - a[0]), abs(b[1] - a[1]), 1)
    return [(round(a[0] + (b[0] - a[0]) * i / n), round(a[1] + (b[1] - a[1]) * i / n)) for i in range(n + 1)]


def _engine(s, pen, x0=21, y0=27, w=10, h=8):
    e0, e1 = pen(x0, y0), pen(x0 + w, y0 + h)
    er = pix.ramp(ENGINE)
    pix.part(s, ENGINE, lambda L: pygame.draw.rect(L, (255, 255, 255), (e0[0], e0[1], e1[0] - e0[0], e1[1] - e0[1]),
                                                    border_radius=1), shine=True)
    for i in range(0, e1[1] - e0[1] - 1, 2):                                # cooling fins
        s.fill(er[3], (e1[0] - 4, e0[1] + 1 + i, 3, 1))
    s.fill(er[1], (e0[0] + 1, e1[1] - 2, 2, 1))                             # case bolt
    pygame.draw.line(s, er[0], (e0[0], e1[1]), (e1[0], e1[1]))             # skid plate
    pygame.draw.line(s, pix.ramp(METAL)[3], (e0[0] + 1, e1[1]), (e1[0] - 2, e1[1]))


def draw_dirt_bike(liv, frame, rider=True, style="dirt"):
    """Dirt-bike family at native size. Same layout as ever:
      dirt      - motocross: upswept tail, flat seat into low shrouds, knobbies
      scrambler - retro trail: round tank, bench seat, high pipe, round headlight,
                  fork gaiters, rear rack, chunky block tread
      sprinter  - supermoto: cast wheels on slicks, belly pan, number fairing
                  with a screen, sharp tail spoiler, rider tucked in"""
    s = _canvas()
    pen = _Pen(frame)
    body, dark = liv["body"], liv["dark"]
    rw, fw, wy = 12, 40, 40
    if style == "sprinter":
        _frame_common(s, pen, frame, rw, fw, wy, dict(slick=True, accent=body), dict(slick=True, accent=body))
    elif style == "scrambler":
        _frame_common(s, pen, frame, rw, fw, wy, dict(chunky=True), dict(chunky=True))
        g = pix.ramp((48, 44, 54))
        for k in range(3):                                                    # rubber fork gaiters
            p = pen(fw - 2 - k, wy - 4 - k * 2, False)
            s.fill(g[2] if k % 2 else g[1], (p[0], p[1], 2, 1))
    else:
        _frame_common(s, pen, frame, rw, fw, wy)
    _engine(s, pen)
    {"scrambler": _scrambler_body, "sprinter": _sprinter_body}.get(style, _mx_body)(s, pen, body, dark)
    # front fender hugging the tyre
    fc = pen(fw, wy, False)
    lift = 1 if style == "scrambler" else 0
    pix.part(s, body, lambda L: pygame.draw.arc(L, (255, 255, 255), (fc[0] - 7, fc[1] - 8 - lift, 15, 15),
                                                math.radians(30), math.radians(150), 1), hi=0, lo=0)
    _bars(s, pen, dark)
    if rider:
        _rider(s, liv, pen, (20, 18), HAND, lean=2 if style == "sprinter" else 0)
    _handguard(s, pen, body)
    return s


def _exhaust(s, pen, header, can, tip):
    pr = pix.ramp(PIPE)
    for a, b in zip(header, header[1:]):
        pygame.draw.line(s, pr[0], (a[0], a[1] + 1), (b[0], b[1] + 1))
        pygame.draw.line(s, pr[2], a, b)
    _poly_part(s, METAL, can, shine=True)
    s.fill((30, 28, 38), tip)


def _mx_body(s, pen, body, dark):
    _exhaust(s, pen, [pen(30, 30), pen(22, 26), pen(14, 25)],
             pen.pts([(5, 22), (15, 23), (15, 27), (6, 26)]), (*pen(4, 23), 2, 2))
    # upswept tail / side panel
    _poly_part(s, body, pen.pts([(1, 17), (12, 20), (23, 22), (22, 26), (14, 24), (5, 20)]), shine=True)
    pygame.draw.line(s, pix.ramp(dark)[2], pen(6, 20), pen(14, 24))
    # long flat seat with a lit top
    _poly_part(s, SEAT, pen.pts([(8, 18), (27, 19), (28, 21), (12, 21)]), hi=1, lo=0)
    # tank / radiator shroud, its dark lower panel, the graphic stripe
    _poly_part(s, body, pen.pts([(25, 20), (34, 18), (36, 21), (33, 27), (26, 27), (23, 23)]), shine=True)
    _poly_part(s, dark, pen.pts([(27, 26), (33, 26), (35, 22), (31, 24)]), outline=False, hi=0)
    pygame.draw.line(s, WHITE, pen(26, 21), pen(33, 19))
    # number plate on the fork crown
    _poly_part(s, WHITE, pen.pts([(35, 17), (38, 18), (37, 23), (35, 22)]), hi=0)
    p = pen(36, 20)
    s.set_at(p, (40, 36, 50))


def _scrambler_body(s, pen, body, dark):
    _exhaust(s, pen, [pen(30, 29), pen(25, 23), pen(15, 21)],
             pen.pts([(4, 19), (15, 20), (15, 23), (5, 23)]), (*pen(3, 20), 2, 2))
    hs = pix.ramp(METAL)
    pygame.draw.line(s, hs[1], pen(6, 21), pen(14, 21))                      # heat shield slots
    _poly_part(s, dark, pen.pts([(3, 17), (13, 18), (13, 20), (5, 20)]))    # short tail
    _line_part(s, METAL, pen(1, 15), pen(12, 16), 1, hi=0, lo=0)            # rear rack
    s.fill(hs[2], (*pen(2, 15), 1, 2))
    a, b = pen(10, 16), pen(25, 20)                                          # bench seat + stitching
    seat = (86, 60, 46)
    pix.part(s, seat, lambda L: pygame.draw.rect(L, (255, 255, 255), (a[0], a[1], b[0] - a[0], b[1] - a[1]),
                                                 border_radius=1))
    pygame.draw.line(s, pix.ramp(seat)[3], (a[0] + 1, a[1] + 1), (b[0] - 2, a[1] + 1))
    t0, t1 = pen(22, 16), pen(36, 25)                                        # round tank + knee pad
    pix.part(s, body, lambda L: pygame.draw.ellipse(L, (255, 255, 255), (t0[0], t0[1], t1[0] - t0[0], t1[1] - t0[1])),
             shine=True, lo=1)
    k0 = pen(25, 21)
    s.fill(pix.ramp(dark)[2], (k0[0], k0[1] + 1, 4, 2))
    s.fill(WHITE, (*pen(27, 17), 3, 1))
    hl = pen(39, 19)                                                         # round headlight
    pygame.draw.circle(s, pix.ramp(METAL)[0], hl, 3)
    pygame.draw.circle(s, (255, 236, 160), hl, 2)
    s.set_at((hl[0] - 1, hl[1] - 1), (255, 255, 255))


def _sprinter_body(s, pen, body, dark):
    _exhaust(s, pen, [pen(30, 30), pen(16, 26)],
             pen.pts([(5, 22), (15, 23), (15, 26), (6, 25)]), (*pen(4, 23), 2, 1))
    _poly_part(s, body, pen.pts([(3, 18), (14, 20), (24, 22), (22, 25), (6, 21)]), shine=True)
    _poly_part(s, dark, pen.pts([(0, 13), (5, 17), (3, 19), (1, 17)]))      # tail spoiler
    _poly_part(s, SEAT, pen.pts([(10, 18), (26, 19), (27, 21), (12, 21)]), lo=0)
    _poly_part(s, body, pen.pts([(25, 20), (34, 19), (36, 22), (32, 27), (24, 25)]), shine=True)
    pygame.draw.line(s, WHITE, pen(25, 22), pen(34, 20))                     # twin racing stripes
    pygame.draw.line(s, pix.ramp(dark)[1], pen(25, 24), pen(33, 22))
    _poly_part(s, dark, pen.pts([(20, 33), (31, 33), (29, 36), (22, 36)]))  # belly pan
    _poly_part(s, WHITE, pen.pts([(35, 17), (38, 18), (37, 23), (35, 22)]), hi=0)
    sc = pen.pts([(36, 15), (38, 12), (38, 17)])                             # screen
    pygame.draw.polygon(s, (150, 210, 240), sc)
    s.set_at(sc[1], (240, 250, 255))


def draw_trike(liv, frame, rider=True):
    """Trike at native size: fat balloon knobbies (the far rear wheel peeking out
    behind), a rounded body with a rear rack, a fender hugging the front tyre.
    The rider sits upright."""
    s = _canvas()
    pen = _Pen(frame)
    body, dark = liv["body"], liv["dark"]
    rw, fw, wy = 12, 41, 40
    _wheel(s, pen(rw + 10, wy - 3, False), frame, r=6, chunky=True, far=True)
    fc = pen(rw, wy, False)
    pix.part(s, pix.shift(dark, -1), lambda L: pygame.draw.arc(L, (255, 255, 255), (fc[0] - 1, fc[1] - 11, 16, 16),
                                                               math.radians(30), math.radians(110), 1), hi=0, lo=0)
    _line_part(s, METAL, pen(rw, wy, False), pen(24, 33, False), 3)
    _line_part(s, (96, 98, 116), pen(fw, wy, False), pen(36, 21), 3, lo=0)
    pygame.draw.line(s, pix.ramp(RIM)[3], pen(fw - 1, wy - 4, False), pen(37, 22))
    _wheel(s, pen(rw, wy, False), frame, r=6, chunky=True)
    _wheel(s, pen(fw, wy, False), frame, disc=True)
    _engine(s, pen, 20, 26, 13, 9)
    _exhaust(s, pen, [pen(21, 31), pen(6, 28)], pen.pts([(3, 26), (10, 26), (10, 30), (3, 30)]), (*pen(2, 27), 2, 2))
    rc = pen(rw, wy, False)                                                  # wide rear fender
    pix.part(s, body, lambda L: pygame.draw.arc(L, (255, 255, 255), (rc[0] - 9, rc[1] - 9, 18, 18),
                                                math.radians(25), math.radians(165), 2), hi=1, lo=0)
    _poly_part(s, body, pen.pts([(4, 20), (22, 20), (24, 24), (8, 24)]), shine=True)
    _line_part(s, METAL, pen(1, 17), pen(12, 17), 1, hi=0, lo=0)            # rack
    for x in (2, 11):
        s.fill(pix.ramp(METAL)[2], (*pen(x, 17), 1, 3))
    a, b = pen(11, 17), pen(27, 21)
    pix.part(s, SEAT, lambda L: pygame.draw.rect(L, (255, 255, 255), (a[0], a[1], b[0] - a[0], b[1] - a[1]),
                                                 border_radius=1), lo=0)
    _poly_part(s, body, pen.pts([(25, 20), (33, 18), (37, 20), (37, 24), (33, 28), (25, 27)]), shine=True)
    _poly_part(s, dark, pen.pts([(27, 26), (33, 26), (36, 23), (31, 24)]), outline=False, hi=0)
    pygame.draw.line(s, WHITE, pen(26, 21), pen(33, 19))
    hl = pen(37, 22)
    s.set_at(hl, (255, 240, 170))
    fc = pen(fw, wy, False)
    pix.part(s, body, lambda L: pygame.draw.arc(L, (255, 255, 255), (fc[0] - 7, fc[1] - 8, 15, 15),
                                                math.radians(30), math.radians(150), 1), hi=0, lo=0)
    _bars(s, pen, dark)
    if rider:
        _rider(s, liv, pen, (20, 18), HAND, lean=-1)
    _handguard(s, pen, body)
    return s


DRAWERS = {"dirt": draw_dirt_bike, "trike": draw_trike,
           "scrambler": lambda l, f, rider=True: draw_dirt_bike(l, f, rider, "scrambler"),
           "sprinter": lambda l, f, rider=True: draw_dirt_bike(l, f, rider, "sprinter")}


# --- bosses and minions: extras drawn over the finished native sprite -------------------------


def _boss_extras(s, biome, vehicle, frame):
    """A boss's look on top of its bike (native coordinates via the pen)."""
    pen = _Pen(frame)
    lean = RIDER_LEAN.get(vehicle, 0)
    hc = pen(29 + lean, 3)                       # helmet centre
    shd = pen(26 + lean, 8)                      # shoulder
    if biome == "lava":                          # INFERNO: horns, red visor, flame decals
        for side in (-1, 1):
            b0 = (hc[0] + side * 2, hc[1] - 3)
            _poly_part(s, (40, 30, 34), [b0, (hc[0] + side * 5, hc[1] - 8), (hc[0] + side, hc[1] - 4)], hi=1, lo=0)
            s.set_at((hc[0] + side * 5, hc[1] - 8), (255, 120, 40))
        s.fill((255, 70, 30), (hc[0], hc[1], 4, 1))
        for i, (x, y) in enumerate(((24, 20), (28, 19), (32, 18), (14, 22))):
            p = pen(x, y)
            col = (255, 200, 60) if (i + frame) % 2 else (255, 110, 30)
            pygame.draw.polygon(s, col, [(p[0], p[1] + 1), (p[0] + 1, p[1] - 2), (p[0] + 3, p[1] + 1)])
    elif biome == "valley":                      # MUD BARON: spiked pauldron, bone mask, mud splats
        pix.part(s, (86, 64, 40), lambda L: pygame.draw.circle(L, (255, 255, 255), shd, 3), shine=True)
        for dx, dy in ((-2, -3), (0, -4), (2, -3)):
            pygame.draw.line(s, (220, 214, 196), (shd[0] + dx // 2, shd[1] - 2), (shd[0] + dx, shd[1] + dy))
        s.fill((236, 228, 204), (hc[0] + 1, hc[1] + 2, 4, 1))
        s.fill((150, 140, 120), (hc[0] + 1, hc[1] + 3, 4, 1))
        for x, y in ((8, 22), (18, 26), (34, 24), (44, 34), (10, 36)):
            p = pen(x, y)
            s.fill((96, 70, 40), (p[0], p[1], 2, 1))
            s.set_at((p[0], p[1] - 1), (130, 96, 60))
    elif biome == "desert":                      # DUNE RAIDER: trailing scarf, goggles, sun emblem
        wave = 1 if frame else -1
        pts = [(shd[0] - 1, shd[1] + 1), (shd[0] - 5, shd[1] + 2 + wave), (shd[0] - 9, shd[1] - wave),
               (shd[0] - 13, shd[1] + 2)]
        pix.part(s, (210, 40, 40), lambda L: pygame.draw.lines(L, (255, 255, 255), False, pts, 1), lo=0)
        s.fill((255, 160, 40), (hc[0], hc[1] - 1, 4, 1))
        p = pen(29, 21)
        pix.part(s, (255, 210, 80), lambda L: pygame.draw.circle(L, (255, 255, 255), p, 1), hi=0, lo=0)
    elif biome == "night":                       # PHANTOM: hooded cloak, glowing eyes, neon trims
        cloak = [(hc[0] - 4, hc[1] - 3), (hc[0] + 1, hc[1] - 5), (hc[0] + 3, hc[1] - 1),
                 (shd[0] - 1, shd[1] + 4), (shd[0] - 10, shd[1] + 6 + frame), (shd[0] - 6, shd[1] + 1)]
        _poly_part(s, (42, 32, 70), cloak, shine=True)
        for dx in (1, 3):
            s.set_at((hc[0] + dx, hc[1]), (220, 170, 255))
        pygame.draw.line(s, (170, 90, 255), pen(8, 21), pen(30, 24))
    elif biome == "stadium":                     # SHOWSTOPPER: crown, cape, star decals
        crown = [(hc[0] - 3, hc[1] - 3), (hc[0] - 3, hc[1] - 6), (hc[0] - 1, hc[1] - 4), (hc[0], hc[1] - 7),
                 (hc[0] + 1, hc[1] - 4), (hc[0] + 3, hc[1] - 6), (hc[0] + 3, hc[1] - 3)]
        _poly_part(s, (255, 205, 50), crown, shine=True, lo=0)
        s.set_at((hc[0], hc[1] - 4), (230, 40, 60))
        cape = [(shd[0] - 1, shd[1] - 1), (shd[0] - 8, shd[1] + 2 + frame), (shd[0] - 10, shd[1] + 6 - frame),
                (shd[0] - 2, shd[1] + 4)]
        _poly_part(s, (200, 26, 46), cape)
        for x, y in ((26, 19), (12, 22)):
            p = pen(x, y)
            _star(s, p, (255, 215, 60))


def _star(s, p, col):
    x, y = p
    for dx, dy in ((0, -1), (-1, 0), (0, 0), (1, 0), (0, 1)):
        s.set_at((x + dx, y + dy), col)
    s.set_at((x, y), (255, 250, 210))


def _minion_extras(s, biome, vehicle, frame):
    """One small piece of the boss's look, so minions read as its crew."""
    pen = _Pen(frame)
    lean = RIDER_LEAN.get(vehicle, 0)
    hc = pen(29 + lean, 3)
    if biome == "lava":
        for side in (-1, 1):
            pygame.draw.polygon(s, (30, 22, 26), [(hc[0] + side * 2, hc[1] - 3), (hc[0] + side * 4, hc[1] - 6),
                                                  (hc[0] + side, hc[1] - 4)])
    elif biome == "valley":
        s.fill((236, 228, 204), (hc[0] + 1, hc[1] + 2, 4, 1))
    elif biome == "desert":
        s.fill((255, 160, 40), (hc[0], hc[1] - 1, 4, 1))
    elif biome == "night":
        for dx in (1, 3):
            s.set_at((hc[0] + dx, hc[1]), (220, 170, 255))
    elif biome == "stadium":
        _star(s, pen(26, 19), (255, 215, 60))


def draw_minion(vehicle, biome, frame, rider=True):
    out = DRAWERS.get(vehicle, draw_dirt_bike)(_minion_livery(biome), frame, rider)
    if rider:
        _minion_extras(out, biome, vehicle, frame)
    return out


def draw_boss(vehicle, biome, frame, rider=True):
    out = DRAWERS.get(vehicle, draw_dirt_bike)(livery(boss_key(biome)), frame, rider)
    if rider:
        _boss_extras(out, biome, vehicle, frame)
    return out


# --- the rider off the bike (crash) --------------------------------------------------------
# Drawn at the size the rider is on the bike, with the same head.


def _limb(L, a, b, w=2):
    pygame.draw.line(L, (255, 255, 255), a, b, w)


def draw_rider_tumble(liv, t):
    """Thrown rider; t selects a pose (0..3): the body cartwheels round its middle."""
    s = pygame.Surface((24, 24), pygame.SRCALPHA)
    c = (12, 12)
    a = t * math.pi / 2
    end = lambda ang, ln: (round(c[0] + ln * math.cos(ang)), round(c[1] + ln * math.sin(ang)))   # noqa: E731
    suit = liv["suit"]
    legs = end(a + math.pi, 7)
    pix.part(s, pix.shift(suit, -1) if sum(suit) > 300 else suit,
             lambda L: (_limb(L, c, legs, 3), _limb(L, legs, end(a + math.pi + 0.5, 9), 2)))
    pix.part(s, BOOT, lambda L: L.fill((255, 255, 255), (*end(a + math.pi + 0.5, 9), 2, 2)), hi=0)
    pix.part(s, suit, lambda L: (_limb(L, c, end(a, 5), 4), _limb(L, c, end(a + 1.9, 6), 2),
                                 _limb(L, c, end(a - 1.6, 6), 2)))
    pygame.draw.line(s, pix.ramp(liv.get("accent", liv["body"]))[2], c, end(a, 4))
    for ang in (a + 1.9, a - 1.6):
        g = end(ang, 6)
        s.fill(pix.ramp(BOOT)[2], (g[0] - 1, g[1] - 1, 2, 2))
    hd = pygame.transform.rotate(head_sprite(liv, front=True), -math.degrees(a) - 90 if t % 2 else 0)
    hc = end(a - 0.3, 8)
    s.blit(hd, (hc[0] - hd.get_width() // 2, hc[1] - hd.get_height() // 2))
    return s


def draw_rider_run(liv, t):
    """Rider jogging back to the bike (facing left): swinging arms and legs,
    boots, the helmet with goggles pushed into view and hair."""
    s = pygame.Surface((16, 24), pygame.SRCALPHA)
    step = (t // 6) % 2
    suit = liv["suit"]
    pants = pix.shift(suit, -1) if sum(suit) > 300 else suit
    far, near = ((5, 21), (11, 21)) if step else ((11, 21), (5, 21))
    pix.part(s, pix.shift(pants, -1), lambda L: _limb(L, (8, 13), far, 2), hi=0)
    pix.part(s, pants, lambda L: _limb(L, (8, 13), near, 3))
    for p in (far, near):
        pix.part(s, BOOT, lambda L, p=p: L.fill((255, 255, 255), (p[0] - 2, p[1] - 1, 4, 2)), hi=0)
    pix.part(s, suit, lambda L: (_limb(L, (8, 14), (7, 6), 4), _limb(L, (7, 8), (3 if step else 11, 12), 2)))
    pygame.draw.line(s, pix.ramp(liv.get("accent", liv["body"]))[2], (8, 12), (7, 8))
    hd = head_sprite(liv)
    s.blit(pygame.transform.flip(hd, True, False), (1, 0))
    return s


class SpriteCache:
    """Pre-rendered vehicle frames + a rotation cache (rotation is slow-ish)."""

    def __init__(self, scale=K, smooth=None):
        """scale: drawn size relative to the design grid. Sprites are drawn at
        SPRITE_SCALE; other scales are whole-number (nearest) enlargements of
        that, so pixels stay crisp. The contact point scales with it."""
        self.scale = scale
        self._base = {}
        self._rot = {}

    def vehicle(self, vehicle, livery, frame, rider=True):
        key = (vehicle, livery, frame, rider)
        if key not in self._base:
            drawer = DRAWERS.get(vehicle, draw_dirt_bike)
            if str(livery).startswith("boss:"):
                img = draw_boss(vehicle, str(livery)[5:], frame, rider)
            elif str(livery).startswith("minion:"):
                img = draw_minion(vehicle, str(livery)[7:], frame, rider)
            else:
                img = drawer(livery_colors(livery), frame, rider)
            if abs(self.scale - K) > 1e-6:
                k = self.scale / K
                img = pygame.transform.scale(img, (round(NW * k), round(NH * k)))
            self._base[key] = img
        return self._base[key]

    def rotated(self, vehicle, livery, frame, angle, rider=True):
        a = int(round(angle / 3.0)) * 3
        key = (vehicle, livery, frame, rider, a)
        if key not in self._rot:
            if len(self._rot) > 600:
                self._rot.clear()
            self._rot[key] = pygame.transform.rotate(self.vehicle(vehicle, livery, frame, rider), a)
        return self._rot[key], a

    def rotated_outlined(self, vehicle, livery, frame, angle, color, width=1):
        """Rotated frame with an outline (player marker, perfect-landing glow)."""
        img, a = self.rotated(vehicle, livery, frame, angle)
        key = (vehicle, livery, frame, True, a, color, width)
        out = self._rot.get(key)
        if out is None:
            out = outlined(img, color, width)
            self._rot[key] = out
        return out, a


def contact_px(scale=K):
    """Where the ground contact point sits on a sprite drawn at `scale`."""
    k = scale / K
    return ((CONTACT[0] * K + O) * k, ((CONTACT[1]) * K + O) * k)


def outlined(img, color, width=1):
    """A copy of img with a solid outline of `width` px around its silhouette.
    The result is 2*width larger, padded evenly, so its centre stays put."""
    w, h = img.get_size()
    out = pygame.Surface((w + 2 * width, h + 2 * width), pygame.SRCALPHA)
    sil = pygame.mask.from_surface(img).to_surface(setcolor=(*color, 255), unsetcolor=(0, 0, 0, 0))
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if (dx or dy) and abs(dx) + abs(dy) <= width + 1:
                out.blit(sil, (width + dx, width + dy))
    out.blit(img, (width, width))
    return out


def blit_rotated(dst, img_rot, angle_deg, contact_screen, scale=K):
    """Blit a rotated sprite so that the CONTACT point lands on contact_screen.
    scale: the size the sprite was drawn at (SpriteCache.scale)."""
    ox = (CONTACT[0] - SPR_W / 2) * scale
    oy = (CONTACT[1] - SPR_H / 2) * scale
    a = math.radians(angle_deg)
    rx = ox * math.cos(a) + oy * math.sin(a)
    ry = -ox * math.sin(a) + oy * math.cos(a)
    r = img_rot.get_rect()
    dst.blit(img_rot, (contact_screen[0] - rx - r.w / 2, contact_screen[1] - ry - r.h / 2))

# --- themes --------------------------------------------------------------------
THEMES = {
    "valley": dict(name="Valley", sky=((120, 190, 250), (200, 230, 255)),
                   far=(110, 150, 190), mid=(80, 150, 90), berm=(150, 104, 66),
                   dirt=(172, 118, 70), grass=(96, 170, 70), sand=(222, 196, 130),
                   wall=(110, 72, 46), stands=True, stars=False, cactus=False,
                   fg=(92, 170, 70), flowers=[(255, 110, 140), (255, 236, 110), (250, 250, 250)]),
    "desert": dict(name="Desert", sky=((250, 170, 100), (255, 226, 170)),
                   far=(214, 140, 100), mid=(226, 180, 120), berm=(190, 130, 80),
                   dirt=(196, 132, 80), grass=(150, 170, 80), sand=(236, 206, 140),
                   wall=(140, 90, 56), stands=False, stars=False, cactus=True, fg=(226, 182, 118)),
    "night": dict(name="Night", sky=((14, 16, 44), (54, 50, 110)),
                  far=(40, 44, 84), mid=(30, 60, 60), berm=(90, 64, 54),
                  dirt=(126, 90, 66), grass=(60, 120, 70), sand=(170, 150, 110),
                  wall=(70, 48, 40), stands=True, stars=True, cactus=False, fg=(40, 86, 70)),
    "stadium": dict(name="Stadium", sky=((40, 46, 70), (90, 96, 130)),
                    far=(70, 76, 110), mid=(60, 64, 90), berm=(130, 92, 64),
                    dirt=(160, 110, 72), grass=(90, 160, 80), sand=(214, 188, 128),
                    wall=(96, 64, 46), stands=True, stars=False, cactus=False, fg=(70, 72, 92)),
    # "lava" level: hot air (heat rises faster, cools slower), puddles are lava pits
    "lava": dict(name="Volcano", sky=((36, 8, 18), (170, 60, 30)),
                 far=(54, 30, 36), mid=(66, 40, 40), berm=(84, 54, 46),
                 dirt=(104, 74, 62), grass=(96, 90, 76), sand=(150, 116, 92),
                 wall=(58, 38, 36), stands=False, stars=False, cactus=False, lava=True, fg=(52, 40, 46)),
}

LAVA = (255, 110, 30)
LAVA_HOT = (255, 210, 80)
LAVA_DARK = (190, 40, 20)


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def build_backdrop(theme, width, height=None):
    """Two parallax layers: far (sky + mountains) and mid (scenery, stands,
    fence), each 2x view width, repeating every view width (ui/backdrop.py)."""
    from ui import backdrop
    return backdrop.build(theme, THEMES[theme], width, height)


def build_berm(theme, width):
    from ui import backdrop
    return backdrop.build_berm(THEMES[theme], width, theme)
