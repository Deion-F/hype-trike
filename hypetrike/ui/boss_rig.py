"""The bosses' rigs: huge vehicles that fill all four lanes (bosses.BossChase).

Each rig is drawn in code on a local surface (W x H) whose rear sits at PX and
whose y runs from the screen's Y0 down, so lane L's ground line is at
GY0 + 20 L. The still parts are drawn once per boss and cached; wheels, lights
and the weak point (which tells you when and where to hit it) are drawn every
frame on top.
"""
import math

import pygame

import config as C
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


def _wheel(surf, x, y, r, spin, tyre=(28, 24, 30), hub=(150, 146, 160), spokes=4):
    pygame.draw.circle(surf, tyre, (x, y), r)
    pygame.draw.circle(surf, _shade(tyre, 1.6), (x, y), r, 2)
    pygame.draw.circle(surf, hub, (x, y), max(3, r // 2))
    for k in range(spokes):
        a = spin + k * math.pi / spokes
        dx, dy = math.cos(a) * (r // 2), math.sin(a) * (r // 2)
        pygame.draw.line(surf, _shade(hub, 0.6), (x - dx, y - dy), (x + dx, y + dy), 2)
    for k in range(10):                                  # tread knobs
        a = spin * 0.5 + k * math.pi / 5
        pygame.draw.circle(surf, _shade(tyre, 0.6), (int(x + math.cos(a) * (r - 1)), int(y + math.sin(a) * (r - 1))), 2)


# --- the still body, per boss -----------------------------------------------------------
def _body_valley(s, info):
    body, dark, trim = info["body"], info["dark"], info["trim"]
    for x in (PX + 30, PX + 104, PX + 180):                       # far-side wheels
        pygame.draw.circle(s, (20, 18, 22), (x, GY0 - 4), 15)
    pygame.draw.rect(s, dark, (PX, FRONT - 40, RIG_LEN, 22))      # chassis
    bed = [(PX - 2, 66), (PX + 144, 66), (PX + 140, FRONT - 22), (PX + 4, FRONT - 22)]
    pygame.draw.polygon(s, body, bed)
    pygame.draw.polygon(s, _shade(body, 0.6), bed, 3)
    for x in range(PX + 20, PX + 140, 24):                         # bed ribs
        pygame.draw.line(s, _shade(body, 0.75), (x, 70), (x, FRONT - 24), 3)
    for i, (x, r) in enumerate(((PX + 30, 20), (PX + 64, 26), (PX + 100, 22), (PX + 128, 14))):
        pygame.draw.circle(s, (88, 64, 40), (x, 68), r)           # a heap of mud
        pygame.draw.circle(s, (118, 88, 56), (x - 4, 62), r // 2)
    pygame.draw.ellipse(s, (88, 64, 40), (PX - 4, 60, 150, 18))
    for x in (PX + 20, PX + 70, PX + 118):                          # drips down the side
        pygame.draw.rect(s, (88, 64, 40), (x, 76, 6, 18 + x % 13), border_radius=3)
    cab = pygame.Rect(PX + 148, 84, 58, FRONT - 22 - 84)
    pygame.draw.rect(s, _shade(body, 1.1), cab, border_radius=6)
    pygame.draw.rect(s, _shade(body, 0.6), cab, 3, border_radius=6)
    pygame.draw.rect(s, (150, 190, 200), (cab.x + 22, cab.y + 8, 30, 24), border_radius=3)
    pygame.draw.line(s, (220, 240, 245), (cab.x + 26, cab.y + 28), (cab.x + 40, cab.y + 11), 2)
    sx, sy = cab.x + 18, cab.y + 50                                 # bone mask on the door
    pygame.draw.ellipse(s, (232, 226, 206), (sx - 11, sy - 12, 22, 22))
    pygame.draw.rect(s, (232, 226, 206), (sx - 7, sy + 6, 14, 8))
    for ex in (-5, 5):
        pygame.draw.circle(s, (30, 24, 20), (sx + ex, sy - 2), 4)
    pygame.draw.rect(s, (60, 56, 60), (cab.x + 4, cab.y - 26, 8, 30))   # exhaust stack
    pygame.draw.rect(s, (60, 56, 60), (PX - 12, 70, 16, FRONT - 70))   # tailgate: a hatch per lane
    for y in range(74, GY0 - 30, 12):
        pygame.draw.line(s, (240, 200, 40), (PX - 12, y), (PX + 3, y + 8), 3)


def _body_desert(s, info):
    body, dark = info["body"], info["dark"]
    pygame.draw.rect(s, (40, 34, 30), (PX + 50, GY0 - 18, RIG_LEN - 54, 18), border_radius=9)   # far track
    hull = [(PX, 64), (PX + 168, 64), (PX + RIG_LEN, 108), (PX + RIG_LEN, 148), (PX, 148)]
    pygame.draw.polygon(s, body, hull)
    pygame.draw.polygon(s, _shade(body, 0.6), hull, 3)
    for x in range(PX + 12, PX + 170, 22):                          # armour seams
        pygame.draw.line(s, _shade(body, 0.82), (x, 68), (x, 132), 2)
    pygame.draw.polygon(s, _shade(body, 0.75), [(PX + 60, 64), (PX + 96, 18), (PX + 112, 64)])   # sail fin
    pygame.draw.polygon(s, (200, 70, 50), [(PX + 96, 20), (PX + 60, 30), (PX + 92, 36)])      # scarf flag
    for i in range(3):                                              # goggle lamps
        pygame.draw.circle(s, (30, 24, 20), (PX + 176 + i * 9, 100 + i * 7), 6)
        pygame.draw.circle(s, (255, 230, 150), (PX + 176 + i * 9, 100 + i * 7), 3)
    pygame.draw.rect(s, dark, (PX - 4, 40, 34, 26), border_radius=4)          # the vent housing up top
    pygame.draw.rect(s, _shade(dark, 0.6), (PX - 4, 40, 34, 26), 2, border_radius=4)


def _body_night(s, info):
    body, trim = info["body"], info["trim"]
    for x in range(PX + 20, PX + RIG_LEN, 32):                       # far-side wheels
        pygame.draw.circle(s, (12, 10, 18), (x, GY0 - 3), 11)
    coach = pygame.Rect(PX, 70, RIG_LEN - 18, FRONT - 22 - 70)
    pygame.draw.rect(s, body, coach, border_radius=10)
    pygame.draw.ellipse(s, _shade(body, 1.2), (PX - 4, 56, RIG_LEN - 10, 34))   # arched roof
    pygame.draw.rect(s, trim, (PX, 100, RIG_LEN - 18, 3))
    pygame.draw.rect(s, trim, (PX, FRONT - 34, RIG_LEN - 18, 3))
    for i, x in enumerate(range(PX + 22, PX + RIG_LEN - 30, 36)):   # arched windows
        r = pygame.Rect(x, 108, 24, 36)
        pygame.draw.rect(s, (70, 50, 110), r, border_radius=10)
        pygame.draw.rect(s, (190, 160, 255), r.inflate(-6, -6), border_radius=8)
        pygame.draw.ellipse(s, (60, 40, 90), (x + 7, 116 + (i % 2) * 4, 10, 14))    # a ghost inside
    nose = [(PX + RIG_LEN - 18, 78), (PX + RIG_LEN + 4, 120), (PX + RIG_LEN + 4, FRONT - 22),
            (PX + RIG_LEN - 18, FRONT - 22)]
    pygame.draw.polygon(s, _shade(body, 0.8), nose)
    pygame.draw.rect(s, (30, 26, 40), (PX + RIG_LEN - 60, 30, 16, 40))     # smokestack
    pygame.draw.rect(s, trim, (PX + RIG_LEN - 64, 28, 24, 6))
    pygame.draw.polygon(s, (90, 86, 100), [(PX + RIG_LEN + 4, FRONT - 22), (PX + RIG_LEN + 16, FRONT - 2),
                                           (PX + RIG_LEN - 10, FRONT - 2)])   # cowcatcher
    pygame.draw.rect(s, (16, 14, 24), (PX - 10, 76, 12, FRONT - 22 - 76))   # lantern rack on its tail


def _body_stadium(s, info):
    body, dark, trim = info["body"], info["dark"], info["trim"]
    skirt = pygame.Rect(PX, 128, RIG_LEN, FRONT - 12 - 128)
    pygame.draw.rect(s, body, skirt)
    for x in range(PX, PX + RIG_LEN, 12):                            # gold fringe
        pygame.draw.circle(s, trim, (x + 6, FRONT - 12), 6)
    pygame.draw.rect(s, trim, (PX, 126, RIG_LEN, 5))
    stage = pygame.Rect(PX + 8, 84, RIG_LEN - 16, 44)
    pygame.draw.rect(s, dark, stage)
    for x in (PX + 30, PX + RIG_LEN - 50):                           # speaker stacks
        pygame.draw.rect(s, (30, 26, 34), (x, 52, 30, 76))
        for y in (64, 94):
            pygame.draw.circle(s, (70, 66, 80), (x + 15, y), 11)
            pygame.draw.circle(s, (20, 18, 24), (x + 15, y), 5)
    cx = PX + RIG_LEN // 2 + 4                                      # the giant crown
    crown = [(cx - 34, 84), (cx - 34, 40), (cx - 18, 58), (cx, 26), (cx + 18, 58), (cx + 34, 40), (cx + 34, 84)]
    pygame.draw.polygon(s, trim, crown)
    pygame.draw.polygon(s, _shade(trim, 0.6), crown, 3)
    for gx, col in ((cx - 18, (230, 60, 80)), (cx, (90, 160, 255)), (cx + 18, (90, 220, 120))):
        pygame.draw.circle(s, col, (gx, 72), 5)
    for x in (PX + 12, PX + RIG_LEN - 12):                           # light poles
        pygame.draw.rect(s, (70, 66, 80), (x - 2, 20, 4, 66))


def _body_lava(s, info):
    body, dark, trim = info["body"], info["dark"], info["trim"]
    for x in (PX + 36, PX + 110, PX + 182):
        pygame.draw.circle(s, (16, 10, 10), (x, GY0 - 4), 15)
    pygame.draw.rect(s, dark, (PX, FRONT - 40, RIG_LEN, 22))
    tank = pygame.Rect(PX + 6, 70, 148, FRONT - 36 - 70)
    pygame.draw.rect(s, body, tank, border_radius=30)
    pygame.draw.rect(s, _shade(body, 0.55), tank, 3, border_radius=30)
    for pts in (((PX + 30, 82), (PX + 46, 104), (PX + 40, 124), (PX + 58, 146)),
                ((PX + 90, 76), (PX + 82, 100), (PX + 98, 120)),
                ((PX + 120, 96), (PX + 138, 118), (PX + 128, 140))):       # glowing cracks
        pygame.draw.lines(s, (255, 110, 30), False, pts, 3)
        pygame.draw.lines(s, (255, 210, 80), False, pts, 1)
    for x in (PX + 40, PX + 100):                                      # flame decals
        pygame.draw.polygon(s, trim, [(x, 150), (x + 10, 120), (x + 18, 138), (x + 26, 112), (x + 34, 150)])
    cab = pygame.Rect(PX + 158, 92, 48, FRONT - 22 - 92)
    pygame.draw.rect(s, _shade(body, 1.2), cab, border_radius=6)
    pygame.draw.rect(s, (255, 150, 40), (cab.x + 18, cab.y + 10, 24, 14), border_radius=3)   # glowing visor
    for hx, d in ((cab.x + 8, -1), (cab.x + 40, 1)):                  # horns
        pygame.draw.polygon(s, (230, 220, 200), [(hx - 5, cab.y + 2), (hx + 5, cab.y + 2), (hx + 12 * d, cab.y - 22)])
    pygame.draw.rect(s, (40, 36, 40), (PX - 6, 92, 18, FRONT - 36 - 92))   # the armoured core hatch


BODIES = {"valley": _body_valley, "desert": _body_desert, "night": _body_night,
          "stadium": _body_stadium, "lava": _body_lava}
_cache = {}


def body(biome):
    if biome not in _cache:
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        BODIES[biome](s, BOSSES[biome])
        _cache[biome] = s
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
        for x in range(PX + 62, PX + RIG_LEN, 26):
            _wheel(s, x, FRONT - 12, 11, spin, tyre=(50, 42, 34), spokes=3)
        pygame.draw.rect(s, (50, 42, 34), (PX + 50, FRONT - 24, RIG_LEN - 52, 24), 3, border_radius=12)
        for x in range(PX + 6, PX + 50, 22):
            _wheel(s, x, FRONT - 12, 11, spin, tyre=(50, 42, 34), spokes=3)
        _roof_zone(s, t, look, glow, pulse)
    elif biome == "night":
        for x in range(PX + 20, PX + RIG_LEN - 20, 32):
            _wheel(s, x, FRONT - 12, 11, spin, tyre=(24, 20, 30), hub=(120, 100, 150))
        pygame.draw.line(s, (120, 100, 150), (PX + 20 + math.cos(spin) * 5, FRONT - 12 + math.sin(spin) * 5),
                         (PX + 180 + math.cos(spin) * 5, FRONT - 12 + math.sin(spin) * 5), 3)    # coupling rod
        for lane in range(C.LANES):                                     # a lantern per lane on its tail
            y = lane_gy(lane) - 18
            lit = lane == look.lantern
            nxt = lane == look.lantern_next and (t // 6) % 2 == 0
            if lit:
                pygame.draw.circle(s, (*glow, 70), (PX - 6, y), 16)
            col = (240, 225, 255) if lit else ((190, 140, 255) if nxt else (60, 50, 80))
            pygame.draw.rect(s, (30, 26, 40), (PX - 12, y - 7, 12, 14), border_radius=2)
            pygame.draw.rect(s, col, (PX - 10, y - 5, 8, 10), border_radius=2)
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
