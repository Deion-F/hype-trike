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
        return dict(BOSS_LIVERIES.get(str(key)[5:], LIVERIES["flame"]))
    if str(key).startswith("minion:"):
        return _minion_livery(str(key)[7:])
    bike, _, rider = str(key).partition("+")
    base = dict(LIVERIES.get(bike, LIVERIES["flame"]))
    if rider in LIVERIES:
        r = LIVERIES[rider]
        base.update(suit=r["suit"], helmet=r["helmet"], accent=r["body"])
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
    base = dict(BOSS_LIVERIES.get(biome, LIVERIES["flame"]))
    for k in ("body", "suit", "helmet"):
        base[k] = tuple(int(c * 0.82) for c in base[k])
    return base


def _minion_extras(s, biome, vehicle, frame):
    """One small piece of the boss's look, so minions read as its crew."""
    bob = frame
    lean = RIDER_LEAN.get(vehicle, 0)
    hx, hy = 29 + lean, 7 + bob
    if biome == "lava":                                   # stubby horns
        for side in (-1, 1):
            pygame.draw.polygon(s, (24, 18, 20), [(hx + side * 3, hy - 3), (hx + side * 5, hy - 7),
                                                   (hx + side * 2, hy - 4)])
    elif biome == "valley":                               # bone face guard
        pygame.draw.line(s, (230, 222, 196), (hx + 1, hy + 2), (hx + 5, hy + 2), 2)
    elif biome == "desert":                               # goggles
        pygame.draw.rect(s, (255, 150, 30), (hx, hy - 2, 5, 2))
    elif biome == "night":                                # glowing eyes
        pygame.draw.rect(s, (200, 140, 255), (hx + 1, hy, 1, 1))
        pygame.draw.rect(s, (200, 140, 255), (hx + 3, hy, 1, 1))
    elif biome == "stadium":                              # a star on the tank
        x, y = 26, 21 + bob
        pygame.draw.polygon(s, (255, 215, 60), [(x, y - 2), (x + 2, y + 2), (x - 2, y + 2)])


def draw_minion(vehicle, biome, frame, rider=True):
    out = DRAWERS.get(vehicle, draw_dirt_bike)(_minion_livery(biome), frame, rider)
    if rider:
        _minion_extras(out, biome, vehicle, frame)
    return out


def _boss_extras(s, biome, vehicle, frame):
    """Draw a boss's extras on a finished 52x54 sprite (native coordinates)."""
    bob = frame
    lean = RIDER_LEAN.get(vehicle, 0)
    hx, hy = 29 + lean, 7 + bob                    # helmet centre
    sx, sy = 26 + lean, 12 + bob                   # shoulder
    if biome == "lava":                            # INFERNO: horns, red visor, flame decals
        for side in (-1, 1):
            base = (hx + side * 3, hy - 3)
            pygame.draw.polygon(s, (24, 18, 20), [base, (hx + side * 7, hy - 9), (hx + side * 2, hy - 4)])
            pygame.draw.line(s, (255, 90, 30), (hx + side * 6, hy - 8), (hx + side * 7, hy - 10), 1)
        pygame.draw.rect(s, (255, 60, 20), (hx + 1, hy - 1, 5, 2))
        for i, (x, y) in enumerate(((24, 22), (28, 21), (32, 20), (14, 24))):
            col = (255, 200, 60) if (i + frame) % 2 else (255, 110, 30)
            pygame.draw.polygon(s, col, [(x, y + bob + 2), (x + 2, y + bob - 3), (x + 4, y + bob + 2)])
    elif biome == "valley":                        # MUD BARON: spiked pauldron, bone mask, mud splats
        pygame.draw.circle(s, (70, 52, 32), (sx, sy), 4)
        for dx, dy in ((-3, -4), (0, -5), (3, -4)):
            pygame.draw.line(s, (200, 196, 180), (sx + dx // 2, sy - 2), (sx + dx, sy + dy), 1)
        pygame.draw.line(s, (230, 222, 196), (hx + 1, hy + 2), (hx + 5, hy + 2), 2)
        for x, y in ((8, 26), (18, 30), (34, 28), (44, 38), (10, 40)):
            pygame.draw.circle(s, (96, 70, 40), (x, y + bob), 1)
    elif biome == "desert":                        # DUNE RAIDER: trailing scarf, goggles, sun emblem
        wave = 1 if frame else -1
        pts = [(sx - 1, sy + 1), (sx - 7, sy + 2 + wave), (sx - 13, sy + wave * -1), (sx - 18, sy + 2)]
        pygame.draw.lines(s, (210, 40, 40), False, pts, 2)
        pygame.draw.rect(s, (255, 150, 30), (hx, hy - 2, 5, 2))
        pygame.draw.circle(s, (255, 210, 80), (29, 22 + bob), 2)
    elif biome == "night":                         # PHANTOM: hooded cloak, glowing eyes, neon trims
        pygame.draw.polygon(s, (30, 22, 50), [(hx - 5, hy - 4), (hx + 2, hy - 7), (hx + 4, hy - 2),
                                              (sx - 2, sy + 6), (sx - 14, sy + 8 + bob), (sx - 8, sy + 2)])
        pygame.draw.rect(s, (200, 140, 255), (hx + 1, hy, 1, 1))
        pygame.draw.rect(s, (200, 140, 255), (hx + 3, hy, 1, 1))
        pygame.draw.line(s, (170, 90, 255), (8, 22 + bob), (30, 25 + bob), 1)
    elif biome == "stadium":                       # SHOWSTOPPER: crown, cape, star decals
        pygame.draw.polygon(s, (255, 215, 60), [(hx - 4, hy - 4), (hx - 4, hy - 8), (hx - 2, hy - 6),
                                                 (hx, hy - 9), (hx + 2, hy - 6), (hx + 4, hy - 8), (hx + 4, hy - 4)])
        cape = [(sx - 1, sy - 1), (sx - 12, sy + 3 + bob), (sx - 15, sy + 9 - bob), (sx - 3, sy + 6)]
        pygame.draw.polygon(s, (190, 20, 40), cape)
        for x, y in ((26, 21), (12, 24)):
            pygame.draw.polygon(s, (255, 215, 60), [(x, y - 2 + bob), (x + 1, y + bob), (x + 3, y + bob),
                                                     (x + 1, y + 1 + bob), (x + 2, y + 3 + bob),
                                                     (x, y + 2 + bob), (x - 2, y + 3 + bob), (x - 1, y + 1 + bob),
                                                     (x - 3, y + bob), (x - 1, y + bob)])


def draw_boss(vehicle, biome, frame, rider=True):
    out = DRAWERS.get(vehicle, draw_dirt_bike)(livery(boss_key(biome)), frame, rider)
    if rider:
        _boss_extras(out, biome, vehicle, frame)
    return out


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

TIRE = (34, 30, 40)
RIM = (170, 170, 182)
METAL = (120, 124, 140)
ENGINE = (70, 72, 86)
SEAT = (30, 28, 36)
SKIN = (240, 190, 150)
VISOR = (40, 50, 70)
BOOT = (40, 36, 44)

SPR_W, SPR_H = 52, 54
CONTACT = (26, 48)   # ground contact point (midpoint between wheels) in sprite
OLD_PAD = 10         # sprites drawn on the old 52x44 grid sit this far down the new one
DIRT_PAD = 4         # the dirt-bike family is drawn on a 52x50 grid, this far down
HAND = (35, 17)      # dirt-bike family: rider's glove on the grip (52x50 grid)
HANDGUARD = (37, 17) # where the coloured hand guard sits


def _pad(s, pad=OLD_PAD):
    """Place a sprite drawn on a shorter grid onto the full sprite grid, so its
    contact point lands on CONTACT (headroom for the helmet goes on top)."""
    out = pygame.Surface((SPR_W, SPR_H), pygame.SRCALPHA)
    out.blit(s, (0, pad))
    return out


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


def _mx_wheel(s, cx, cy, frame, knobby=True, disc=False, r=8, block=2, n=12, far=False):
    """Big spoked off-road wheel: tall knobby tyre, thin rim, wire spokes and a
    hub. frame 0/1 turns the knobs and spokes half a step (rolling feel).
    block: tread block size in px (3 = the scrambler's chunky blocks).
    far: the far-side wheel of the trike, drawn darker."""
    tire = (18, 16, 22) if far else TIRE
    rim = (110, 110, 122) if far else RIM
    pygame.draw.circle(s, tire, (cx, cy), r)
    if knobby:
        for i in range(n):
            a = (i + frame * 0.5) * 2 * math.pi / n
            kr = r - (block - 2) * 0.5                          # big blocks sit a bit lower
            kx, ky = cx + kr * math.cos(a), cy + kr * math.sin(a)
            s.fill(tire, (int(round(kx - block / 2)), int(round(ky - block / 2)), block, block))
    else:
        pygame.draw.circle(s, (54, 50, 62), (cx, cy), r, 1)        # slick: sidewall sheen
    pygame.draw.circle(s, rim, (cx, cy), r - 3, 1)                 # rim
    spoke = (96, 96, 108) if far else (140, 140, 154)
    for i in range(6):
        a = (i + frame * 0.5) * math.pi / 3
        pygame.draw.line(s, spoke, (cx, cy), (cx + (r - 4) * math.cos(a), cy + (r - 4) * math.sin(a)))
    if disc:
        pygame.draw.circle(s, (150, 150, 162), (cx, cy), 3)
        pygame.draw.circle(s, (96, 96, 110), (cx, cy), 3, 1)
    pygame.draw.circle(s, METAL, (cx, cy), 2)
    s.fill((210, 210, 220), (cx, cy - 1, 1, 1))


def _mag_wheel(s, cx, cy, frame, accent, disc=False):
    """Sprinter (supermoto): slick tyre on a cast five-spoke wheel with a
    coloured rim stripe."""
    r = 8
    pygame.draw.circle(s, TIRE, (cx, cy), r)
    pygame.draw.circle(s, (58, 54, 66), (cx, cy), r, 1)                # slick sidewall
    pygame.draw.circle(s, (60, 62, 74), (cx, cy), r - 2)               # cast wheel
    pygame.draw.circle(s, accent, (cx, cy), r - 2, 1)                  # rim stripe
    for i in range(5):
        a = (i + frame * 0.5) * 2 * math.pi / 5
        pygame.draw.line(s, (170, 172, 186), (cx, cy), (cx + 5 * math.cos(a), cy + 5 * math.sin(a)), 2)
    if disc:
        pygame.draw.circle(s, (150, 150, 162), (cx, cy), 3, 1)
    pygame.draw.circle(s, (40, 40, 50), (cx, cy), 1)


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
    pygame.draw.line(s, liv.get("accent", liv["body"]), (hx + 1, hy - 3), (sh[0], sh[1] + 2), 2)  # jersey stripe
    # arm to bars
    pygame.draw.line(s, suit, sh, (hand[0], hand[1] + bob), 3)
    pygame.draw.rect(s, BOOT, (hand[0] - 1, hand[1] + bob - 1, 3, 3))
    # helmet
    hc = (sh[0] + 3, sh[1] - 5)
    pygame.draw.circle(s, liv["helmet"], hc, 5)
    pygame.draw.rect(s, VISOR, (hc[0] + 1, hc[1] - 1, 5, 3))
    pygame.draw.line(s, liv.get("accent", liv["body"]), (hc[0] - 4, hc[1] - 2), (hc[0] + 2, hc[1] - 5), 2)


def _bars(s, dark, fy):
    """Fork clamp + handlebar in the dark livery colour, ending at the grip."""
    pygame.draw.line(s, METAL, (35, fy(18)), (36, fy(16)), 2)
    pygame.draw.line(s, dark, (33, fy(17)), (37, fy(14)), 2)


def draw_dirt_bike(liv, frame, rider=True, style="dirt"):
    """Dirt-bike family, drawn on the 52x50 grid. All three share the frame,
    engine, big wheels, coloured bars + hand guard and a front fender that hugs
    the tyre (nothing pokes out ahead). Each has its own character:
      dirt      - motocross: upswept tail, flat seat into low shrouds, knobbies
      scrambler - retro trail: round tank, bench seat, high pipe, round headlight,
                  fork gaiters, rear rack, chunky block tread
      sprinter  - supermoto: cast wheels on slicks, belly pan, number fairing
                  with a screen, sharp tail spoiler, rider tucked in"""
    s = pygame.Surface((SPR_W, SPR_H - DIRT_PAD), pygame.SRCALPHA)
    bob = frame
    body, dark = liv["body"], liv["dark"]
    rw, fw, wy = 12, 40, 40
    fy = lambda y: y + bob + 2                      # sprung parts move with the suspension
    # rear shock, swingarm, fork (wheels are unsprung)
    pygame.draw.line(s, (200, 170, 60), (19, fy(25)), (22, 33), 2)            # shock spring
    pygame.draw.line(s, METAL, (rw, wy), (23, 33), 3)                        # swingarm
    pygame.draw.line(s, (90, 92, 106), (fw, wy), (35, fy(19)), 3)            # fork leg
    pygame.draw.line(s, (196, 198, 210), (fw - 1, wy - 3), (36, fy(20)), 1)  # stanchion shine
    if style == "sprinter":
        _mag_wheel(s, rw, wy, frame, body)
        _mag_wheel(s, fw, wy, frame, body, disc=True)
    elif style == "scrambler":
        _mx_wheel(s, rw, wy, frame, block=3, n=10)
        _mx_wheel(s, fw, wy, frame, block=3, n=10, disc=True)
        # rubber fork gaiters
        for k in range(3):
            pygame.draw.line(s, (40, 38, 46), (fw - 2 - k, wy - 4 - k * 2), (fw - k, wy - 4 - k * 2), 2)
    else:
        _mx_wheel(s, rw, wy, frame)
        _mx_wheel(s, fw, wy, frame, disc=True)
    # engine block with fins, skid plate under it
    pygame.draw.rect(s, ENGINE, (21, fy(25), 10, 8), border_radius=2)
    for i in range(3):
        s.fill((96, 98, 114), (27, fy(26 + i * 2), 4, 1))
    pygame.draw.line(s, (40, 40, 50), (21, fy(33)), (31, fy(33)), 2)
    if style == "scrambler":
        _scrambler_body(s, body, dark, fy)
    elif style == "sprinter":
        _sprinter_body(s, body, dark, fy)
    else:
        _mx_body(s, body, dark, fy)
    # front fender hugging the tyre (an arc, nothing sticking out ahead)
    if style == "scrambler":                         # high fender: a little gap above the tyre
        pygame.draw.arc(s, body, (fw - 11, wy - 13, 22, 22), math.radians(40), math.radians(140), 3)
        pygame.draw.line(s, METAL, (fw - 2, wy - 12), (fw - 1, wy - 9), 1)    # fender stay
    else:
        pygame.draw.arc(s, body, (fw - 11, wy - 11, 22, 22), math.radians(25), math.radians(150), 3)
    _bars(s, dark, fy)
    if rider:
        _rider(s, liv, bob, hip=(20, 18), hand=HAND, lean=2 if style == "sprinter" else 0)
    _handguard(s, body, dark, bob)
    return _pad(s, DIRT_PAD)


def _mx_body(s, body, dark, fy):
    # exhaust: header from the cylinder, under the seat, out to a silencer
    pygame.draw.line(s, (150, 120, 90), (30, fy(28)), (22, fy(24)), 2)
    pygame.draw.line(s, (150, 120, 90), (22, fy(24)), (14, fy(23)), 2)
    pygame.draw.polygon(s, METAL, [(5, fy(20)), (15, fy(21)), (15, fy(25)), (6, fy(24))])
    s.fill((40, 40, 50), (4, fy(21), 2, 3))                                  # tail pipe
    # upswept tail / side panel, running forward under the seat
    pygame.draw.polygon(s, body, [(1, fy(15)), (12, fy(18)), (23, fy(20)), (22, fy(24)),
                                  (14, fy(22)), (5, fy(18))])
    pygame.draw.line(s, dark, (5, fy(18)), (14, fy(22)), 1)
    # long flat seat into the tank
    pygame.draw.polygon(s, SEAT, [(8, fy(16)), (27, fy(17)), (28, fy(19)), (12, fy(19))])
    # tank / radiator shroud: a low wedge, no beak
    pygame.draw.polygon(s, body, [(25, fy(18)), (34, fy(16)), (36, fy(19)), (33, fy(25)),
                                  (26, fy(25)), (23, fy(21))])
    pygame.draw.polygon(s, dark, [(27, fy(24)), (33, fy(24)), (35, fy(20)), (31, fy(22))])
    pygame.draw.line(s, (255, 255, 255), (26, fy(19)), (33, fy(17)), 1)      # graphic stripe
    # number plate flush with the fork crown
    pygame.draw.polygon(s, (245, 245, 245), [(35, fy(15)), (38, fy(16)), (37, fy(21)), (35, fy(20))])


def _scrambler_body(s, body, dark, fy):
    # high pipe: up from the cylinder along the side to a short silencer under the seat
    pygame.draw.line(s, (170, 140, 100), (30, fy(27)), (25, fy(21)), 2)
    pygame.draw.line(s, (170, 140, 100), (25, fy(21)), (15, fy(19)), 2)
    pygame.draw.polygon(s, (190, 192, 204), [(4, fy(17)), (15, fy(18)), (15, fy(21)), (5, fy(21))])
    pygame.draw.line(s, (120, 122, 134), (6, fy(19)), (14, fy(19)), 1)      # heat shield slots
    s.fill((40, 40, 50), (3, fy(18), 2, 3))
    # rear rack + short tail
    pygame.draw.polygon(s, dark, [(3, fy(15)), (13, fy(16)), (13, fy(18)), (5, fy(18))])
    pygame.draw.line(s, METAL, (1, fy(13)), (12, fy(14)), 2)
    s.fill(METAL, (2, fy(13), 1, 3))
    # flat bench seat with a stitched seam
    pygame.draw.rect(s, (66, 46, 36), (10, fy(14), 15, 4), border_radius=2)
    pygame.draw.line(s, (110, 82, 60), (11, fy(15)), (23, fy(15)), 1)
    # round teardrop tank with a knee pad
    pygame.draw.ellipse(s, body, (22, fy(14), 14, 9))
    pygame.draw.ellipse(s, dark, (25, fy(19), 7, 4))
    s.fill((255, 255, 255), (27, fy(15), 5, 1))                               # tank shine
    # round headlight on the forks
    pygame.draw.circle(s, METAL, (39, fy(17)), 3)
    pygame.draw.circle(s, (255, 240, 170), (39, fy(17)), 2)


def _sprinter_body(s, body, dark, fy):
    # under-seat silencer
    pygame.draw.line(s, (150, 120, 90), (30, fy(28)), (16, fy(24)), 2)
    pygame.draw.polygon(s, METAL, [(5, fy(20)), (15, fy(21)), (15, fy(24)), (6, fy(23))])
    s.fill((40, 40, 50), (4, fy(21), 2, 2))
    # low tail with a sharp spoiler at the very back
    pygame.draw.polygon(s, body, [(3, fy(16)), (14, fy(18)), (24, fy(20)), (22, fy(23)), (6, fy(19))])
    pygame.draw.polygon(s, dark, [(0, fy(11)), (5, fy(15)), (3, fy(17)), (1, fy(15))])
    # thin seat, low tank with twin racing stripes
    pygame.draw.polygon(s, SEAT, [(10, fy(16)), (26, fy(17)), (27, fy(19)), (12, fy(19))])
    pygame.draw.polygon(s, body, [(25, fy(18)), (34, fy(17)), (36, fy(20)), (32, fy(25)), (24, fy(23))])
    pygame.draw.line(s, (250, 250, 250), (25, fy(20)), (34, fy(18)), 1)
    pygame.draw.line(s, (250, 250, 250), (25, fy(22)), (33, fy(20)), 1)
    # belly pan under the engine
    pygame.draw.polygon(s, dark, [(20, fy(31)), (31, fy(31)), (29, fy(34)), (22, fy(34))])
    # number fairing + low screen, flush with the forks
    pygame.draw.polygon(s, (245, 245, 245), [(35, fy(15)), (38, fy(16)), (37, fy(21)), (35, fy(20))])
    pygame.draw.polygon(s, (150, 210, 240), [(36, fy(13)), (38, fy(11)), (38, fy(15))])


def _handguard(s, body, dark, bob):
    """Coloured MX hand guard + bar end just ahead of the glove."""
    gx, gy = HANDGUARD
    pygame.draw.polygon(s, body, [(gx, gy - 3 + bob), (gx + 3, gy - 2 + bob),
                                  (gx + 3, gy + 1 + bob), (gx, gy + 2 + bob)])
    s.fill(dark, (gx + 3, gy - 2 + bob, 1, 3))


def draw_trike(liv, frame, rider=True):
    """Trike, on the 52x50 grid like the dirt-bike family: a heavy three-wheeler
    on fat balloon knobbies (far rear wheel peeking out behind), a rounded
    body with a rear rack, a fender hugging the front tyre, coloured bars and
    hand guard. The rider sits upright."""
    s = pygame.Surface((SPR_W, SPR_H - DIRT_PAD), pygame.SRCALPHA)
    bob = frame
    body, dark = liv["body"], liv["dark"]
    rw, fw, wy = 12, 41, 40
    fy = lambda y: y + bob + 2
    # far rear wheel, axle and swingarm, fork
    _mx_wheel(s, rw + 10, wy - 3, frame, r=9, block=3, n=10, far=True)
    pygame.draw.arc(s, dark, (rw - 2, wy - 16, 24, 24), math.radians(20), math.radians(110), 3)   # far fender
    pygame.draw.line(s, METAL, (rw, wy), (24, 33), 4)
    pygame.draw.line(s, (90, 92, 106), (fw, wy), (36, fy(19)), 4)
    pygame.draw.line(s, (196, 198, 210), (fw - 1, wy - 4), (37, fy(20)), 1)
    _mx_wheel(s, rw, wy, frame, r=9, block=3, n=10)
    _mx_wheel(s, fw, wy, frame, r=8, block=2, n=12, disc=True)
    # engine, skid plate, short exhaust out the back under the rack
    pygame.draw.rect(s, ENGINE, (20, fy(24), 13, 9), border_radius=2)
    for i in range(3):
        s.fill((96, 98, 114), (28, fy(25 + i * 2), 4, 1))
    pygame.draw.line(s, (40, 40, 50), (20, fy(33)), (32, fy(33)), 2)
    pygame.draw.line(s, (150, 120, 90), (21, fy(29)), (6, fy(26)), 2)
    pygame.draw.rect(s, METAL, (3, fy(24), 7, 4), border_radius=1)
    s.fill((40, 40, 50), (2, fy(25), 2, 2))
    # wide rear fender over the near fat wheel, a slim tail and a rack on top
    pygame.draw.arc(s, body, (rw - 12, wy - 13, 24, 24), math.radians(20), math.radians(170), 4)
    pygame.draw.polygon(s, body, [(4, fy(18)), (22, fy(18)), (24, fy(22)), (8, fy(22))])
    pygame.draw.line(s, dark, (8, fy(22)), (23, fy(22)), 1)
    pygame.draw.line(s, METAL, (1, fy(15)), (12, fy(15)), 2)
    s.fill(METAL, (2, fy(15), 1, 4))
    s.fill(METAL, (11, fy(15), 1, 3))
    # bench seat
    pygame.draw.rect(s, SEAT, (11, fy(15), 16, 4), border_radius=2)
    # rounded front body / tank, no nose point
    pygame.draw.polygon(s, body, [(25, fy(18)), (33, fy(16)), (37, fy(18)), (37, fy(22)),
                                  (33, fy(26)), (25, fy(25))])
    pygame.draw.polygon(s, dark, [(27, fy(24)), (33, fy(24)), (36, fy(21)), (31, fy(22))])
    pygame.draw.line(s, (255, 255, 255), (26, fy(19)), (33, fy(17)), 1)
    pygame.draw.circle(s, (255, 240, 170), (37, fy(20)), 1)                  # small headlight
    # front fender hugging the tyre
    pygame.draw.arc(s, body, (fw - 11, wy - 11, 22, 22), math.radians(25), math.radians(150), 3)
    _bars(s, dark, fy)
    if rider:
        _rider(s, liv, bob, hip=(20, 18), hand=HAND, lean=-1)
    _handguard(s, body, dark, bob)
    return _pad(s, DIRT_PAD)


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


# --- drawing sprites at a smaller size, natively (no resampling blur) --------------------
class _ScaledSurface:
    """A sprite canvas whose coordinates are in the art's native grid; the pixels
    underneath are `k` times the size. Only what the drawers use is supported."""

    def __init__(self, size, flags, k):
        self.k = k
        self.real = _real_pygame.Surface((max(1, round(size[0] * k)), max(1, round(size[1] * k))), flags)

    def fill(self, color, rect=None):
        if rect is None:
            return self.real.fill(color)
        x, y, w, h = rect
        k = self.k
        return self.real.fill(color, (round(x * k), round(y * k), max(1, round(w * k)), max(1, round(h * k))))

    def blit(self, other, pos):
        src = other.real if isinstance(other, _ScaledSurface) else other
        return self.real.blit(src, (round(pos[0] * self.k), round(pos[1] * self.k)))


class _ScaledDraw:
    """pygame.draw with every coordinate, radius and line width scaled by k and
    rounded to whole pixels, so shapes land crisp on the smaller canvas."""

    def __init__(self, k):
        self.k = k

    def _p(self, pt):
        return (round(pt[0] * self.k), round(pt[1] * self.k))

    def _w(self, w):
        return max(1, round(w * self.k)) if w else 0

    def line(self, s, col, a, b, width=1):
        return _real_pygame.draw.line(s.real, col, self._p(a), self._p(b), self._w(width))

    def lines(self, s, col, closed, pts, width=1):
        return _real_pygame.draw.lines(s.real, col, closed, [self._p(p) for p in pts], self._w(width))

    def polygon(self, s, col, pts, width=0):
        return _real_pygame.draw.polygon(s.real, col, [self._p(p) for p in pts], self._w(width))

    def circle(self, s, col, c, r, width=0):
        return _real_pygame.draw.circle(s.real, col, self._p(c), max(1, round(r * self.k)), self._w(width))

    def _rect(self, r):
        x, y, w, h = r
        return (round(x * self.k), round(y * self.k), max(1, round(w * self.k)), max(1, round(h * self.k)))

    def rect(self, s, col, r, width=0, border_radius=0):
        return _real_pygame.draw.rect(s.real, col, self._rect(r), self._w(width),
                                      border_radius=round(border_radius * self.k))

    def ellipse(self, s, col, r, width=0):
        return _real_pygame.draw.ellipse(s.real, col, self._rect(r), self._w(width))

    def arc(self, s, col, r, a0, a1, width=1):
        return _real_pygame.draw.arc(s.real, col, self._rect(r), a0, a1, self._w(width))


class _ScaledPygame:
    """Stands in for the pygame module inside this file while a sprite is drawn."""

    def __init__(self, k):
        self.k = k
        self.draw = _ScaledDraw(k)

    def Surface(self, size, flags=0):        # noqa: N802 (mirrors pygame.Surface)
        return _ScaledSurface(size, flags, self.k)

    def __getattr__(self, name):
        return getattr(_real_pygame, name)


_real_pygame = pygame


def draw_scaled(drawer, k, *args, **kw):
    """Run a sprite drawer with everything scaled by k: crisp, not resampled."""
    global pygame
    if k == 1.0:
        return drawer(*args, **kw)
    pygame = _ScaledPygame(k)
    try:
        out = drawer(*args, **kw)
    finally:
        pygame = _real_pygame
    return out.real if isinstance(out, _ScaledSurface) else out


class SpriteCache:
    """Pre-rendered vehicle frames + a rotation cache (rotation is slow-ish)."""

    def __init__(self, scale=1.0, smooth=True):
        """scale: drawn size (the race renderer uses config.SPRITE_SCALE); the
        sprite's contact point scales with it (see blit_rotated)."""
        self.scale = scale
        self.smooth = smooth
        self._base = {}
        self._rot = {}

    def vehicle(self, vehicle, livery, frame, rider=True):
        key = (vehicle, livery, frame, rider)
        if key not in self._base:
            drawer = DRAWERS.get(vehicle, draw_dirt_bike)
            if str(livery).startswith("boss:"):
                biome = str(livery)[5:]
                drawer = lambda liv, f, r, _v=vehicle, _b=biome: draw_boss(_v, _b, f, r)   # noqa: E731
            elif str(livery).startswith("minion:"):
                biome = str(livery)[7:]
                drawer = lambda liv, f, r, _v=vehicle, _b=biome: draw_minion(_v, _b, f, r)   # noqa: E731
            if self.scale != 1.0 and self.smooth == "native":
                img = draw_scaled(drawer, self.scale, livery_colors(livery), frame, rider)
            else:
                img = drawer(livery_colors(livery), frame, rider)
                if self.scale != 1.0:
                    size = (round(SPR_W * self.scale), round(SPR_H * self.scale))
                    img = (pygame.transform.smoothscale if self.smooth else pygame.transform.scale)(img, size)
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


def blit_rotated(dst, img_rot, angle_deg, contact_screen, scale=1.0):
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
    # "lava" level: hot air (heat rises faster, cools slower), puddles are lava pits
    "lava": dict(name="Volcano", sky=((36, 8, 18), (170, 60, 30)),
                 far=(54, 30, 36), mid=(66, 40, 40), berm=(84, 54, 46),
                 dirt=(104, 74, 62), grass=(96, 90, 76), sand=(150, 116, 92),
                 wall=(58, 38, 36), stands=False, stars=False, cactus=False, lava=True),
}

LAVA = (255, 110, 30)
LAVA_HOT = (255, 210, 80)
LAVA_DARK = (190, 40, 20)


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
    if th.get("lava"):
        # three volcanoes with glowing craters and lava running down
        for i in range(3):
            cx = (i * 2 + 1) * W // 6 + rng.randrange(-30, 30)
            top, base, half = 72 + rng.randrange(20), 170, 110 + rng.randrange(30)
            pygame.draw.polygon(far, _shade(th["far"], 0.8),
                                [(cx - half, base), (cx - 16, top), (cx + 16, top), (cx + half, base)])
            pygame.draw.ellipse(far, LAVA, (cx - 16, top - 4, 32, 8))
            pygame.draw.ellipse(far, LAVA_HOT, (cx - 9, top - 2, 18, 4))
            for k in (-1, 1):
                x, y = cx + k * 8, top + 2
                while y < base - 10:
                    nx, ny = x + k * rng.randrange(2, 6), y + rng.randrange(6, 12)
                    pygame.draw.line(far, LAVA_DARK, (x, y), (nx, ny), 3)
                    pygame.draw.line(far, LAVA, (x, y), (nx, ny), 1)
                    x, y = nx, ny
            for j in range(4):         # smoke plume
                pygame.draw.circle(far, _shade(th["sky"][0], 1.6 + j * 0.2),
                                   (cx + j * 9, top - 14 - j * 14), 9 + j * 3)
        for _ in range(60):            # embers in the sky
            far.fill(rng.choice((LAVA, LAVA_HOT)), (rng.randrange(W), rng.randrange(160), 1, 1))

    mid = pygame.Surface((W, height), pygame.SRCALPHA)
    if th.get("lava"):
        # jagged black rock with glowing cracks
        pts = [(0, 232)]
        for x in range(0, W + 1, 8):
            pts.append((x, int(184 - 10 * math.sin(x * 2 * math.pi / W * 6) - (x // 8 % 3) * 3)))
        pts.append((W, 232))
        pygame.draw.polygon(mid, th["mid"], pts)
        for i in range(18):
            x = i * W // 18 + rng.randrange(30)
            y = 192 + rng.randrange(10)
            pygame.draw.line(mid, LAVA_DARK, (x, y), (x + 6, y + 5), 2)
            pygame.draw.line(mid, LAVA, (x + 6, y + 5), (x + 3, y + 10), 1)
        for i in range(10):            # rocks
            x = i * W // 10 + rng.randrange(40)
            pygame.draw.polygon(mid, _shade(th["mid"], 0.7), [(x, 202), (x + 6, 190), (x + 14, 194), (x + 18, 202)])
    elif th["cactus"]:
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
