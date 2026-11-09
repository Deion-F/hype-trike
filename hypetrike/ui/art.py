"""Procedural pixel art: vehicles, rider, themes. Everything is drawn in code,
so there are no external image assets (decision I.5)."""
import math
import random

import pygame

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

TIRE = (34, 30, 40)
RIM = (170, 170, 182)
METAL = (120, 124, 140)
ENGINE = (70, 72, 86)
SEAT = (30, 28, 36)
SKIN = (240, 190, 150)
VISOR = (40, 50, 70)
BOOT = (40, 36, 44)

SPR_W, SPR_H = 52, 44
CONTACT = (26, 38)   # ground contact point (midpoint between wheels) in sprite


def _wheel(s, cx, cy, r, frame, dark=False):
    tire = TIRE if not dark else (20, 18, 24)
    pygame.draw.circle(s, tire, (cx, cy), r)
    pygame.draw.circle(s, RIM if not dark else (110, 110, 120), (cx, cy), max(2, r - 3))
    pygame.draw.circle(s, tire, (cx, cy), max(1, r - 4))
    # spokes alternate per frame (vibration feel)
    if frame == 0:
        pygame.draw.line(s, RIM, (cx - r + 3, cy), (cx + r - 3, cy))
        pygame.draw.line(s, RIM, (cx, cy - r + 3), (cx, cy + r - 3))
    else:
        d = int((r - 3) * 0.7)
        pygame.draw.line(s, RIM, (cx - d, cy - d), (cx + d, cy + d))
        pygame.draw.line(s, RIM, (cx - d, cy + d), (cx + d, cy - d))
    pygame.draw.rect(s, METAL, (cx - 1, cy - 1, 2, 2))


def _rider(s, liv, bob, hip, hand, lean=0):
    """Rider: hip/hand are points; bob shifts body vertically."""
    suit = liv["suit"]
    hx, hy = hip[0], hip[1] + bob
    # leg: hip -> knee -> boot on peg
    knee = (hx + 6, hy + 4)
    boot = (hx + 3, hy + 9)
    pygame.draw.line(s, suit, (hx, hy), knee, 3)
    pygame.draw.line(s, suit, knee, boot, 3)
    pygame.draw.rect(s, BOOT, (boot[0] - 2, boot[1] - 1, 5, 3))
    # torso leaning forward
    sh = (hx + 6 + lean, hy - 10)
    pygame.draw.line(s, suit, (hx, hy), sh, 5)
    pygame.draw.line(s, liv["body"], (hx + 1, hy - 3), (sh[0], sh[1] + 2), 2)  # jersey stripe
    # arm to bars
    pygame.draw.line(s, suit, sh, (hand[0], hand[1] + bob), 3)
    pygame.draw.rect(s, BOOT, (hand[0] - 1, hand[1] + bob - 1, 3, 3))
    # helmet
    hc = (sh[0] + 3, sh[1] - 5)
    pygame.draw.circle(s, liv["helmet"], hc, 5)
    pygame.draw.rect(s, VISOR, (hc[0] + 1, hc[1] - 1, 5, 3))
    pygame.draw.line(s, liv["body"], (hc[0] - 4, hc[1] - 2), (hc[0] + 2, hc[1] - 5), 2)


def _knobs(s, cx, cy, r, frame):
    for i in range(10):
        a = (i + frame * 0.5) * math.pi / 5
        s.fill(TIRE, (int(cx + (r + 1) * math.cos(a)), int(cy + (r + 1) * math.sin(a)), 2, 2))


def draw_dirt_bike(liv, frame, rider=True, style="dirt"):
    s = pygame.Surface((SPR_W, SPR_H), pygame.SRCALPHA)
    bob = frame
    rw, fw, wy = (14, 38, 37)
    if style == "sprinter":
        rw, fw = 15, 39
    # swingarm, fork
    pygame.draw.line(s, METAL, (rw, wy), (24, 30), 3)
    pygame.draw.line(s, METAL, (fw, wy), (34, 20 + bob), 3)
    _wheel(s, rw, wy, 7, frame)
    _wheel(s, fw, wy, 7, frame)
    # engine + exhaust
    pygame.draw.rect(s, ENGINE, (21, 27 + bob, 10, 7))
    pygame.draw.line(s, METAL, (22, 33 + bob), (10, 27 + bob), 2)
    # rear fender + seat
    pygame.draw.polygon(s, liv["body"], [(6, 24 + bob), (20, 22 + bob), (22, 26 + bob), (8, 27 + bob)])
    pygame.draw.polygon(s, SEAT, [(12, 22 + bob), (25, 20 + bob), (26, 22 + bob), (13, 24 + bob)])
    # tank / shroud
    pygame.draw.polygon(s, liv["body"], [(24, 21 + bob), (34, 19 + bob), (37, 23 + bob), (31, 28 + bob), (24, 27 + bob)])
    pygame.draw.polygon(s, liv["dark"], [(26, 26 + bob), (31, 28 + bob), (36, 23 + bob), (33, 25 + bob)])
    # number plate + front fender
    pygame.draw.polygon(s, (250, 250, 250), [(34, 18 + bob), (38, 17 + bob), (39, 22 + bob), (36, 23 + bob)])
    pygame.draw.polygon(s, liv["body"], [(35, 28 + bob), (45, 27 + bob), (44, 29 + bob), (36, 30 + bob)])
    # handlebar
    pygame.draw.line(s, METAL, (33, 17 + bob), (36, 15 + bob), 2)
    if style == "scrambler":
        # knobby tyres, high front fender, rear rack, headlight
        _knobs(s, rw, wy, 7, frame)
        _knobs(s, fw, wy, 7, frame)
        pygame.draw.polygon(s, liv["dark"], [(36, 21 + bob), (46, 18 + bob), (46, 20 + bob), (38, 23 + bob)])
        pygame.draw.line(s, METAL, (4, 21 + bob), (13, 20 + bob), 2)
        pygame.draw.rect(s, (255, 240, 170), (38, 19 + bob, 3, 3))
    elif style == "sprinter":
        # tail spoiler, racing stripe, low screen
        pygame.draw.polygon(s, liv["dark"], [(3, 19 + bob), (10, 22 + bob), (6, 24 + bob)])
        pygame.draw.line(s, (250, 250, 250), (24, 23 + bob), (36, 21 + bob), 1)
        pygame.draw.polygon(s, (150, 210, 240), [(36, 16 + bob), (40, 13 + bob), (40, 17 + bob)])
    if rider:
        _rider(s, liv, bob, hip=(21, 19), hand=(35, 15), lean=1 if style == "sprinter" else 0)
    return s


def draw_trike(liv, frame, rider=True):
    s = pygame.Surface((SPR_W, SPR_H), pygame.SRCALPHA)
    bob = frame
    wy = 35
    # far-side rear wheel (darker, offset), then near rear + front balloon tyres
    _wheel(s, 15, wy - 2, 8, frame, dark=True)
    pygame.draw.line(s, METAL, (14, wy), (26, 28), 3)
    pygame.draw.line(s, METAL, (40, wy + 1), (35, 19 + bob), 3)
    _wheel(s, 12, wy, 8, frame)
    _wheel(s, 40, wy + 1, 7, frame)
    pygame.draw.rect(s, ENGINE, (21, 26 + bob, 12, 8))
    # chunky body + rack
    pygame.draw.polygon(s, liv["body"], [(3, 22 + bob), (22, 20 + bob), (24, 25 + bob), (4, 27 + bob)])
    pygame.draw.line(s, METAL, (3, 20 + bob), (14, 19 + bob), 2)
    pygame.draw.polygon(s, SEAT, [(12, 20 + bob), (26, 18 + bob), (27, 21 + bob), (13, 22 + bob)])
    pygame.draw.polygon(s, liv["body"], [(25, 19 + bob), (36, 18 + bob), (41, 24 + bob), (33, 28 + bob), (25, 27 + bob)])
    pygame.draw.polygon(s, liv["dark"], [(27, 26 + bob), (33, 28 + bob), (40, 24 + bob), (36, 25 + bob)])
    pygame.draw.polygon(s, liv["body"], [(36, 27 + bob), (48, 26 + bob), (47, 29 + bob), (38, 30 + bob)])
    pygame.draw.line(s, METAL, (33, 16 + bob), (37, 14 + bob), 2)
    if rider:
        _rider(s, liv, bob, hip=(21, 18), hand=(36, 14), lean=-1)
    return s


DRAWERS = {"dirt": draw_dirt_bike, "trike": draw_trike,
           "scrambler": lambda l, f, rider=True: draw_dirt_bike(l, f, rider, "scrambler"),
           "sprinter": lambda l, f, rider=True: draw_dirt_bike(l, f, rider, "sprinter")}


def draw_rider_tumble(liv, t):
    """Thrown rider; t selects a pose (0..3)."""
    s = pygame.Surface((24, 24), pygame.SRCALPHA)
    c = (12, 12)
    a = t * math.pi / 2
    for k, (ln, w, col) in enumerate([(9, 4, liv["suit"]), (7, 3, liv["suit"])]):
        ang = a + k * math.pi
        pygame.draw.line(s, col, c, (c[0] + ln * math.cos(ang), c[1] + ln * math.sin(ang)), w)
    pygame.draw.line(s, liv["suit"], c, (c[0] + 7 * math.cos(a + 1.9), c[1] + 7 * math.sin(a + 1.9)), 3)
    hc = (c[0] + 9 * math.cos(a - 0.4), c[1] + 9 * math.sin(a - 0.4))
    pygame.draw.circle(s, liv["helmet"], hc, 4)
    return s


def draw_rider_run(liv, t):
    """Rider jogging back to the bike (facing left)."""
    s = pygame.Surface((16, 24), pygame.SRCALPHA)
    step = (t // 6) % 2
    pygame.draw.line(s, liv["suit"], (8, 13), (5 if step else 11, 21), 3)
    pygame.draw.line(s, liv["suit"], (8, 13), (11 if step else 5, 21), 3)
    pygame.draw.line(s, liv["suit"], (8, 13), (7, 5), 4)
    pygame.draw.line(s, liv["suit"], (7, 7), (3 if step else 11, 11), 2)
    pygame.draw.circle(s, liv["helmet"], (6, 4), 4)
    pygame.draw.rect(s, VISOR, (2, 3, 3, 3))
    return s


class SpriteCache:
    """Pre-rendered vehicle frames + a rotation cache (rotation is slow-ish)."""

    def __init__(self):
        self._base = {}
        self._rot = {}

    def vehicle(self, vehicle, livery, frame, rider=True):
        key = (vehicle, livery, frame, rider)
        if key not in self._base:
            self._base[key] = DRAWERS.get(vehicle, draw_dirt_bike)(LIVERIES[livery], frame, rider)
        return self._base[key]

    def rotated(self, vehicle, livery, frame, angle, rider=True):
        a = int(round(angle / 3.0)) * 3
        key = (vehicle, livery, frame, rider, a)
        if key not in self._rot:
            if len(self._rot) > 600:
                self._rot.clear()
            self._rot[key] = pygame.transform.rotate(self.vehicle(vehicle, livery, frame, rider), a)
        return self._rot[key], a


def blit_rotated(dst, img_rot, angle_deg, contact_screen):
    """Blit a rotated sprite so that the CONTACT point lands on contact_screen."""
    ox = CONTACT[0] - SPR_W / 2
    oy = CONTACT[1] - SPR_H / 2
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
                   wall=(110, 72, 46), stands=True, stars=False, cactus=False),
    "desert": dict(name="Desert", sky=((250, 170, 100), (255, 226, 170)),
                   far=(214, 140, 100), mid=(226, 180, 120), berm=(190, 130, 80),
                   dirt=(196, 132, 80), grass=(150, 170, 80), sand=(236, 206, 140),
                   wall=(140, 90, 56), stands=False, stars=False, cactus=True),
    "night": dict(name="Night", sky=((14, 16, 44), (54, 50, 110)),
                  far=(40, 44, 84), mid=(30, 60, 60), berm=(90, 64, 54),
                  dirt=(126, 90, 66), grass=(60, 120, 70), sand=(170, 150, 110),
                  wall=(70, 48, 40), stands=True, stars=True, cactus=False),
    "stadium": dict(name="Stadium", sky=((40, 46, 70), (90, 96, 130)),
                    far=(70, 76, 110), mid=(60, 64, 90), berm=(130, 92, 64),
                    dirt=(160, 110, 72), grass=(90, 160, 80), sand=(214, 188, 128),
                    wall=(96, 64, 46), stands=True, stars=False, cactus=False),
}


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def build_backdrop(theme, width, height=360):
    """Two parallax layers: far (sky + mountains) and mid (stands/scenery).
    Each is 2x view width so it can scroll and wrap."""
    th = THEMES[theme]
    rng = random.Random(hash(theme) & 0xFFFF)
    W = width * 2
    far = pygame.Surface((W, height))
    top, bot = th["sky"]
    for y in range(0, 200):
        k = y / 200
        far.fill(tuple(int(top[i] + (bot[i] - top[i]) * k) for i in range(3)), (0, y, W, 1))
    far.fill(bot, (0, 200, W, height - 200))
    if th["stars"]:
        for _ in range(140):
            far.fill((240, 240, 255), (rng.randrange(W), rng.randrange(150), 1, 1))
        pygame.draw.circle(far, (240, 240, 210), (W // 3, 50), 14)
    # mountains: wrap-safe because the profile is periodic over W
    pts = [(0, height)]
    for x in range(0, W + 1, 8):
        y = 150 - 34 * math.sin(x * 2 * math.pi / W * 3) - 18 * math.sin(x * 2 * math.pi / W * 7 + 1)
        pts.append((x, int(y)))
    pts.append((W, height))
    pygame.draw.polygon(far, th["far"], pts)

    mid = pygame.Surface((W, height), pygame.SRCALPHA)
    if th["cactus"]:
        pts = [(0, 230)]
        for x in range(0, W + 1, 8):
            pts.append((x, int(190 - 12 * math.sin(x * 2 * math.pi / W * 5))))
        pts.append((W, 230))
        pygame.draw.polygon(mid, th["mid"], pts)
        for i in range(10):
            cx = i * W // 10 + rng.randrange(30)
            cy = 196
            pygame.draw.rect(mid, (70, 130, 70), (cx, cy - 22, 6, 24))
            pygame.draw.rect(mid, (70, 130, 70), (cx - 6, cy - 14, 6, 4))
            pygame.draw.rect(mid, (70, 130, 70), (cx - 6, cy - 20, 3, 8))
            pygame.draw.rect(mid, (70, 130, 70), (cx + 6, cy - 16, 5, 4))
            pygame.draw.rect(mid, (70, 130, 70), (cx + 8, cy - 24, 3, 10))
    else:
        # rolling hills with trees
        pts = [(0, 232)]
        for x in range(0, W + 1, 8):
            pts.append((x, int(182 - 10 * math.sin(x * 2 * math.pi / W * 4))))
        pts.append((W, 232))
        pygame.draw.polygon(mid, th["mid"], pts)
        for i in range(24):
            tx = i * W // 24 + rng.randrange(20)
            ty = 186 - 10 * math.sin(tx * 2 * math.pi / W * 4)
            pygame.draw.rect(mid, (90, 60, 40), (tx, ty - 6, 3, 8))
            pygame.draw.circle(mid, _shade(th["mid"], 0.75), (tx + 1, int(ty) - 10), 7)
    if th["stands"]:
        # grandstand blocks with a crowd of coloured specks, flags and lights
        for i in range(4):
            bx = i * W // 4 + 40
            bw = W // 4 - 80
            pygame.draw.rect(mid, (70, 74, 96), (bx, 150, bw, 54))
            pygame.draw.rect(mid, (50, 52, 70), (bx, 146, bw, 6))
            for row in range(5):
                for cx in range(bx + 4, bx + bw - 4, 4):
                    if rng.random() < 0.8:
                        col = rng.choice([(240, 80, 80), (250, 220, 90), (90, 160, 250),
                                          (250, 250, 250), (120, 220, 120), (250, 150, 60)])
                        mid.fill(col, (cx + rng.randrange(2), 156 + row * 9, 2, 3))
                        mid.fill(SKIN, (cx + rng.randrange(2), 153 + row * 9, 2, 2))
            pygame.draw.line(mid, METAL, (bx + bw // 2, 146), (bx + bw // 2, 112), 2)
            pygame.draw.rect(mid, (250, 250, 250) if not th["stars"] else (255, 250, 200),
                             (bx + bw // 2 - 8, 106, 16, 6))
    # trackside fence + sponsor-free banners
    fence_y = 206
    pygame.draw.rect(mid, (240, 240, 240), (0, fence_y, W, 2))
    pygame.draw.rect(mid, (240, 240, 240), (0, fence_y + 10, W, 2))
    for x in range(0, W, 16):
        pygame.draw.rect(mid, (200, 200, 210), (x, fence_y, 2, 20))
    banner_cols = [(232, 72, 52), (40, 140, 230), (255, 196, 0), (120, 220, 60)]
    for i, x in enumerate(range(24, W, 160)):
        pygame.draw.rect(mid, banner_cols[i % 4], (x, fence_y + 3, 56, 12))
        pygame.draw.rect(mid, (255, 255, 255), (x + 6, fence_y + 7, 44, 4))
    return far, mid
