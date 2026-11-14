"""World rendering: backdrop, track, surface tiles, vehicles, particles."""
import math
import random

import pygame

import config as C
from track.tiles import (PROFILES, GAP, START, COOLANT, MUD, DEBRIS, WATER, PAD_BARS,
                         DIRT, GRASS, SAND, PIT_DEPTH, DECKS, DECK_UP, DECK, DECK_DOWN,
                         DECK_KICK, DECK_GAP, DRAW, DECK_H, draw_lift, SPLITS, SPLIT_DRAW,
                         SKY_UP, SKY_DOWN, SKY_H, HIGH_LANES, _sample)
from ui import art

BACK_LANES = tuple(range(HIGH_LANES))           # split bridge: the skyway lanes
FRONT_LANES = tuple(range(HIGH_LANES, C.LANES))  # ... and the deck lanes below

FRONT_BOTTOM = 342


def _heat_colour(stops, v):
    """Colour at heat v along (heat, colour) stops."""
    for (v0, c0), (v1, c1) in zip(stops, stops[1:]):
        if v <= v1:
            k = (v - v0) / max(1e-6, v1 - v0)
            return tuple(int(a + (b - a) * max(0.0, min(1.0, k))) for a, b in zip(c0, c1))
    return stops[-1][1]


def _shade(c, k):
    return (max(0, min(255, int(c[0] * k))), max(0, min(255, int(c[1] * k))),
            max(0, min(255, int(c[2] * k))))


class Particles:
    MAX = 360

    def __init__(self):
        # [x, y, vx, vy, life, max_life, color, size, gravity, grow, alpha]
        # in world coords (x = track px)
        self.items = []
        self._puffs = {}          # (diameter, colour, alpha step) -> round soft puff surface

    def emit(self, x, y, vx, vy, life, color, size=2, gravity=0.05, grow=0.0, alpha=0):
        """grow > 0: a puff that swells by that many px over its life (smoke).
        alpha > 0: a round, see-through puff that fades out as it dies (dust)."""
        if len(self.items) < self.MAX:
            self.items.append([x, y, vx, vy, life, life, color, size, gravity, grow, alpha])

    def update(self):
        keep = []
        for p in self.items:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += p[8]
            p[4] -= 1
            if p[4] > 0:
                keep.append(p)
        self.items = keep

    def _puff(self, d, col, a):
        key = (d, col, a)
        img = self._puffs.get(key)
        if img is None:
            if len(self._puffs) > 400:
                self._puffs.clear()
            img = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(img, (*col, a), (d / 2, d / 2), d / 2)
            self._puffs[key] = img
        return img

    def draw(self, surf, cam_x):
        for x, y, _, _, life, ml, col, size, _, grow, alpha in self.items:
            sx = C.BIKE_SCREEN_X + (x - cam_x)
            if alpha:
                k = life / ml                                   # 1 -> 0 over its life
                d = max(2, int(size + grow * (1 - k)))
                a = int(alpha * min(1.0, k * 1.6)) // 16 * 16   # fade in steps (cache-friendly)
                if a > 0:
                    surf.blit(self._puff(d, col, a), (int(sx - d / 2), int(y - d / 2)))
                continue
            if grow:
                s = int(size + grow * (1 - life / ml))
                surf.fill(col, (int(sx - s / 2), int(y - s / 2), s, s))
                continue
            s = size if life > ml * 0.4 else max(1, size - 1)
            surf.fill(col, (int(sx), int(y), s, s))


class WorldRenderer:
    def __init__(self, width, theme="valley"):
        self.sprites = art.SpriteCache(C.SPRITE_SCALE, C.SPRITE_SMOOTH)
        self.width = width
        self.particles = Particles()
        self.set_theme(theme, width)
        self._rng = random.Random(1)

    def set_theme(self, theme, width=None):
        if width:
            self.width = width
        self.theme_name = theme if theme in art.THEMES else "valley"
        self.theme = art.THEMES[self.theme_name]
        self.far, self.mid = art.build_backdrop(self.theme_name, self.width)
        th = self.theme
        self.mat_col = {DIRT: th["dirt"], GRASS: th["grass"], SAND: th["sand"]}

    # ------------------------------------------------------------------------
    def draw_backdrop(self, surf, cam_x, scroll=None):
        """scroll: parallax position for the far/mid layers (defaults to cam_x).
        The race scene runs it faster than the camera while boosting."""
        W = self.far.get_width()
        scroll = cam_x if scroll is None else scroll
        for layer, k in ((self.far, 0.08), (self.mid, 0.4)):
            off = int(scroll * k) % (W // 2)          # forward = layers slide left
            surf.blit(layer, (-off, 0))
            if W - off < self.width:
                surf.blit(layer, (W - off, 0))
        th = self.theme
        # berm behind lane 0
        surf.fill(_shade(th["berm"], 0.85), (0, C.LANE_BASE_Y - 12, self.width, 12))
        surf.fill(_shade(th["berm"], 1.05), (0, C.LANE_BASE_Y - 12, self.width, 2))

    COL_TOP = C.LANE_BASE_Y - 100  # tallest structure (deck kicker, 71 px) + art above it

    def draw_track(self, surf, track, cam_x, editor_cursor=None, ticks=0):
        """Blit pre-rendered columns (each column is rendered once per track).
        ticks: race tick, for the moving parts (drawbridge leaves)."""
        key = (self.theme_name, getattr(self, "heat_pads", False))
        if getattr(self, "_cache_track", None) is not track or self._cache_theme != key:
            self._cache_track = track
            self._cache_theme = key
            self._col_cache = {}
        left = cam_x - C.BIKE_SCREEN_X
        first = int(math.floor(left / C.TILE_W))
        last = int(math.floor((left + self.width) / C.TILE_W)) + 1
        for ci in range(first, last + 1):
            col = ci % track.ncols
            img = self._col_cache.get(col)
            if img is None:
                img = self._render_column(track, col)
                self._col_cache[col] = img
            sx0 = int(round(C.BIKE_SCREEN_X + ci * C.TILE_W - cam_x))
            surf.blit(img, (sx0, self.COL_TOP))
            if track.terrain[col] == DRAW:
                self._draw_leaf(surf, sx0, draw_lift(ticks, col), ticks)
            elif track.terrain[col] == SPLIT_DRAW:
                self._draw_leaf(surf, sx0, draw_lift(ticks, col), ticks, lanes=FRONT_LANES)

    def _render_column(self, track, col):
        tmp = pygame.Surface((C.TILE_W + 2, FRONT_BOTTOM + 2), pygame.SRCALPHA)
        self._draw_column(tmp, track, col, 0)
        return tmp.subsurface((0, self.COL_TOP, C.TILE_W + 2, FRONT_BOTTOM + 2 - self.COL_TOP)).copy()

    def _draw_column(self, surf, track, col, sx0):
        th = self.theme
        t = track.terrain[col]
        base = self.mat_col.get(track.material[col], th["dirt"])
        if t in SPLITS:
            self._draw_split_column(surf, track, col, sx0, base)
            return
        if t in DECKS:
            self._draw_deck_column(surf, track, col, sx0, base)
            return
        if t == GAP:
            self._draw_pit(surf, sx0,
                           track.terrain[(col - 1) % track.ncols] == GAP,
                           track.terrain[(col + 1) % track.ncols] == GAP)
            return
        prof = PROFILES[t]
        for (x0, h0), (x1, h1) in zip(prof, prof[1:]):
            if x1 <= x0:
                continue
            a = sx0 + x0
            b = sx0 + x1
            slope = (h1 - h0) / (x1 - x0)
            k = 1.0 + max(-0.35, min(0.25, slope * 0.35))
            for lane in range(C.LANES):
                ya = C.lane_y(lane)
                yb = C.lane_y(lane + 1)
                lk = k * (0.97 if lane % 2 else 1.0)
                pygame.draw.polygon(surf, _shade(base, lk),
                                    [(a, ya - h0), (b, ya - h1), (b + 1, yb - h1), (a, yb - h0)])
                pygame.draw.line(surf, _shade(base, lk * 1.18), (a, ya - h0), (b, ya - h1))
            yf = C.lane_y(C.LANES)
            pygame.draw.polygon(surf, _shade(th["wall"], 0.8 + 0.2 * k),
                                [(a, yf - h0), (b, yf - h1), (b + 1, FRONT_BOTTOM), (a, FRONT_BOTTOM)])
        r = random.Random(col * 977 + 13)
        for _ in range(10):
            lx = r.randrange(C.TILE_W)
            lane = r.randrange(C.LANES)
            h = track._h[col * C.TILE_W + lx]
            y = C.lane_y(lane) + r.randrange(3, C.LANE_SPACING - 2) - h
            surf.fill(_shade(base, 0.72), (int(sx0 + lx), int(y), 2, 1))
        if track.material[col] == GRASS:
            for _ in range(14):
                lx = r.randrange(C.TILE_W)
                lane = r.randrange(C.LANES)
                h = track._h[col * C.TILE_W + lx]
                y = C.lane_y(lane) + r.randrange(2, C.LANE_SPACING - 3) - h
                surf.fill(_shade(base, 1.25), (int(sx0 + lx), int(y), 1, 2))
        elif track.material[col] == SAND:
            for _ in range(10):
                lx = r.randrange(C.TILE_W - 6)
                lane = r.randrange(C.LANES)
                h = track._h[col * C.TILE_W + lx]
                y = C.lane_y(lane) + r.randrange(4, C.LANE_SPACING - 3) - h
                pygame.draw.line(surf, _shade(base, 0.86), (sx0 + lx, y), (sx0 + lx + 5, y - 1))
        if t == START:
            self._draw_start(surf, sx0)
        self._draw_surfaces(surf, track, col, sx0)

    # -- raised decks: a timber trestle bridge -------------------------------------------
    PLANK = (196, 150, 96)
    BEAM = (92, 62, 40)
    RAIL = (52, 44, 52)

    def _ground_strip(self, surf, sx0, base, x0=0, x1=C.TILE_W, shade=1.0):
        """Flat ground lanes + front wall (what you see under the deck)."""
        th = self.theme
        base = _shade(base, shade)
        a, b = sx0 + x0, sx0 + x1
        for lane in range(C.LANES):
            ya, yb = C.lane_y(lane), C.lane_y(lane + 1)
            lk = 0.97 if lane % 2 else 1.0
            surf.fill(_shade(base, lk), (a, ya, b - a + 1, yb - ya))
            pygame.draw.line(surf, _shade(base, lk * 1.18), (a, ya), (b, ya))
        yf = C.lane_y(C.LANES)
        surf.fill(_shade(th["wall"], 1.0), (a, yf, b - a + 1, FRONT_BOTTOM - yf))

    def _deck_surface(self, surf, sx0, prof, x_from=0, x_to=C.TILE_W, lanes=None):
        """Plank lanes following `prof` between x_from and x_to; returns nothing.
        lanes: which lanes the deck spans (default all; split bridges use halves)."""
        lanes = lanes or range(C.LANES)
        back, front = lanes[0], lanes[-1] + 1
        plank = self.PLANK
        for (x0, h0), (x1, h1) in zip(prof, prof[1:]):
            x0c, x1c = max(x0, x_from), min(x1, x_to)
            if x1c <= x0c:
                continue
            f0 = (x0c - x0) / (x1 - x0)
            f1 = (x1c - x0) / (x1 - x0)
            ha, hb = h0 + (h1 - h0) * f0, h0 + (h1 - h0) * f1
            a, b = sx0 + x0c, sx0 + x1c
            slope = (h1 - h0) / (x1 - x0)
            k = 1.0 + max(-0.3, min(0.25, slope * 0.35))
            for lane in lanes:
                ya, yb = C.lane_y(lane), C.lane_y(lane + 1)
                lk = k * (0.95 if lane % 2 else 1.0)
                pygame.draw.polygon(surf, _shade(plank, lk),
                                    [(a, ya - ha), (b, ya - hb), (b + 1, yb - hb), (a, yb - ha)])
            # plank seams across the deck (every 8 px)
            for px in range((x0c + 7) // 8 * 8, x1c, 8):
                hp = h0 + (h1 - h0) * (px - x0) / (x1 - x0)
                pygame.draw.line(surf, _shade(plank, 0.78), (sx0 + px, C.lane_y(back) - hp),
                                 (sx0 + px, C.lane_y(front) - hp))
            # back rail and front deck edge (a dark beam)
            pygame.draw.line(surf, self.RAIL, (a, C.lane_y(back) - ha - 1), (b, C.lane_y(back) - hb - 1), 2)
            yf = C.lane_y(front)
            pygame.draw.polygon(surf, self.BEAM, [(a, yf - ha), (b, yf - hb), (b, yf - hb + 6), (a, yf - ha + 6)])
            pygame.draw.line(surf, _shade(self.BEAM, 1.4), (a, yf - ha), (b, yf - hb))

    def _trestle(self, surf, x, top_h):
        """A timber leg pair with cross-bracing, from the deck's front edge down."""
        yf = C.lane_y(C.LANES)
        y_top = yf - top_h + 6
        if y_top >= yf:
            return
        beam = self.BEAM
        dark = _shade(beam, 0.7)
        # back leg (behind, under the far edge of the deck) peeks out higher up
        yb = C.lane_y(0)
        if yb - top_h + 6 < yb:
            surf.fill(dark, (x + 4, yb - top_h + 6, 3, top_h - 6))
        surf.fill(beam, (x, y_top, 4, yf - y_top))
        surf.fill(_shade(beam, 1.35), (x, y_top, 1, yf - y_top))
        surf.fill(dark, (x - 1, yf - 2, 6, 3))           # footing

    def _bracing(self, surf, xa, xb, top_h):
        yf = C.lane_y(C.LANES)
        y_top = yf - top_h + 7
        if yf - y_top < 10:
            return
        col = _shade(self.BEAM, 0.85)
        pygame.draw.line(surf, col, (xa + 3, y_top), (xb, yf - 3), 2)
        pygame.draw.line(surf, col, (xa + 3, yf - 3), (xb, y_top), 2)

    def _draw_deck_column(self, surf, track, col, sx0, base):
        t = track.terrain[col]
        prof = PROFILES[t]
        nxt = track.terrain[(col + 1) % track.ncols]
        prv = track.terrain[(col - 1) % track.ncols]
        # the deck's shadow darkens the ground under it, so the space reads as open
        self._ground_strip(surf, sx0, base, shade=1.0 if t in (DECK_GAP, DRAW) else 0.58)
        if t == DECK_UP:
            # a solid timber ramp: wedge front face, planks on top
            yf = C.lane_y(C.LANES)
            pts = [(sx0 + x, yf - h) for x, h in prof] + [(sx0 + C.TILE_W, yf), (sx0, yf)]
            pygame.draw.polygon(surf, _shade(self.BEAM, 1.1), pts)
            for i in range(1, 6):        # horizontal boards on the face
                y = yf - i * DECK_H / 6
                xr = sx0 + 72 * (i * DECK_H / 6) / DECK_H
                pygame.draw.line(surf, _shade(self.BEAM, 0.8), (xr, y), (sx0 + C.TILE_W, y))
            self._deck_surface(surf, sx0, prof)
            self._trestle(surf, sx0 + C.TILE_W - 6, DECK_H)
            return
        if t == DECK_GAP:
            # the span is gone: a hole in the ground under it, splintered ends
            self._draw_pit(surf, sx0, False, False)
            for side, x in ((0, sx0), (1, sx0 + C.TILE_W - 8)):
                for lane in range(C.LANES):
                    ya = C.lane_y(lane) - DECK_H
                    jag = 3 + (lane * 5 + side * 3) % 5
                    xx = x + (0 if side == 0 else 8 - jag)
                    surf.fill(_shade(self.PLANK, 0.9), (xx, ya, jag, C.LANE_SPACING))
            return
        if t == DRAW:
            # piers both ends; the leaf itself is drawn live (_draw_leaf)
            self._draw_pit(surf, sx0, False, False)
            self._trestle(surf, sx0 + 2, DECK_H + 4)
            self._trestle(surf, sx0 + C.TILE_W - 6, DECK_H + 4)
            return
        if t == DECK_DOWN:
            self._deck_surface(surf, sx0, prof, 0, 16)
            yf = C.lane_y(C.LANES)
            pts = [(sx0 + 16, yf - DECK_H), (sx0 + C.TILE_W, yf), (sx0 + 16, yf)]
            pygame.draw.polygon(surf, _shade(self.BEAM, 1.1), pts)
            self._deck_surface(surf, sx0, prof, 16, C.TILE_W)
            self._trestle(surf, sx0 + 12, DECK_H)
            return
        # deck / deck kicker: open underneath, legs every half column with bracing
        self._bracing(surf, sx0 + 2, sx0 + 38, DECK_H)
        self._bracing(surf, sx0 + 42, sx0 + 78, DECK_H)
        for lx in (2, 40):
            self._trestle(surf, sx0 + lx, DECK_H)
        flat = [(0, DECK_H), (C.TILE_W, DECK_H)]
        self._deck_surface(surf, sx0, flat)
        if t == DECK_KICK:
            self._deck_surface(surf, sx0, prof, 0, 62)
            for lane in range(C.LANES + 1):     # warning chevrons on the kicker lip
                y = C.lane_y(lane) - DECK_H - 15
                surf.fill((250, 210, 40) if lane % 2 else (30, 30, 30), (sx0 + 52, y - 1, 5, 3))
        if nxt in (DECK_GAP, DRAW):
            # warning stripes on the edge before a hole
            for lane in range(C.LANES + 1):
                y = C.lane_y(lane) - DECK_H
                surf.fill((250, 210, 40) if lane % 2 else (30, 30, 30), (sx0 + C.TILE_W - 3, y - 2, 3, 4))
        self._draw_surfaces(surf, track, col, sx0)

    def _draw_split_column(self, surf, track, col, sx0, base):
        """Split bridge: the back lanes ride a narrow skyway on tall legs, the
        front lanes the deck (or the drawbridge) below it. Back to front: the
        ground or pit, the skyway's legs and strip, then the lower deck."""
        t = track.terrain[col]
        lower, upper = SPLITS[t]
        yf_up = C.lane_y(HIGH_LANES)              # skyway front edge (ground line)
        if lower == DRAW:
            self._draw_pit(surf, sx0, False, False)
        else:
            self._ground_strip(surf, sx0, base, shade=0.5)
        uprof = PROFILES[upper]
        # skyway legs: tall timber posts from the strip's front edge to the ground
        for lx in (6, 46):
            h = _sample(uprof, lx)
            y_top = yf_up - h + 6
            surf.fill(_shade(self.BEAM, 0.75), (sx0 + lx, y_top, 3, yf_up - y_top))
        if upper == SKY_UP:
            # a timber wedge from deck height up to the strip
            pts = [(sx0 + x, yf_up - h) for x, h in uprof] + [(sx0 + C.TILE_W, yf_up - DECK_H),
                                                              (sx0, yf_up - DECK_H)]
            pygame.draw.polygon(surf, _shade(self.BEAM, 1.1), pts)
        elif upper == SKY_DOWN:
            pts = [(sx0 + 16, yf_up - SKY_H), (sx0 + C.TILE_W, yf_up - DECK_H), (sx0 + 16, yf_up - DECK_H)]
            pygame.draw.polygon(surf, _shade(self.BEAM, 1.1), pts)
        self._deck_surface(surf, sx0, uprof, lanes=BACK_LANES)
        # yellow edge markers along the strip's open front edge
        for x in range(4, C.TILE_W, 16):
            h = _sample(uprof, x)
            surf.fill((250, 210, 40), (sx0 + x, yf_up - h - 2, 6, 2))
        # the lower deck (front lanes)
        if lower == DRAW:
            self._trestle(surf, sx0 + 2, DECK_H + 4)
            self._trestle(surf, sx0 + C.TILE_W - 6, DECK_H + 4)
        else:
            self._bracing(surf, sx0 + 2, sx0 + 38, DECK_H)
            self._bracing(surf, sx0 + 42, sx0 + 78, DECK_H)
            for lx in (2, 40):
                self._trestle(surf, sx0 + lx, DECK_H)
            self._deck_surface(surf, sx0, PROFILES[DECK], lanes=FRONT_LANES)
            nxt = track.tile((col + 1) % track.ncols, C.LANES - 1)
            if nxt in (DECK_GAP, DRAW):
                for lane in FRONT_LANES + (C.LANES,):
                    y = C.lane_y(lane) - DECK_H
                    surf.fill((250, 210, 40) if lane % 2 else (30, 30, 30), (sx0 + C.TILE_W - 3, y - 2, 3, 4))
        self._draw_surfaces(surf, track, col, sx0)

    def _draw_leaf(self, surf, sx0, lift, ticks, lanes=None):
        """Drawbridge leaf hinged at its far end; `lift` 0 (down) .. 1 (up, ~70 deg).
        lanes: the lanes it spans (default all)."""
        lanes = lanes or range(C.LANES)
        back, front = lanes[0], lanes[-1] + 1
        ang = math.radians(70 * lift)
        L = C.TILE_W - 4
        hx = sx0 + C.TILE_W - 2                  # hinge x
        dx, dh = L * math.cos(ang), L * math.sin(ang)
        plank = self.PLANK
        for lane in lanes:
            ya, yb = C.lane_y(lane) - DECK_H, C.lane_y(lane + 1) - DECK_H
            lk = (0.95 if lane % 2 else 1.0) * (1.0 - 0.25 * lift)
            pygame.draw.polygon(surf, _shade(plank, lk),
                                [(hx - dx, ya - dh), (hx, ya), (hx, yb), (hx - dx, yb - dh)])
        yf = C.lane_y(front) - DECK_H
        pygame.draw.polygon(surf, self.BEAM, [(hx - dx, yf - dh), (hx, yf), (hx, yf + 6), (hx - dx, yf - dh + 6)])
        pygame.draw.line(surf, self.RAIL, (hx - dx, C.lane_y(back) - DECK_H - dh - 1),
                         (hx, C.lane_y(back) - DECK_H - 1), 2)
        # signal post on the near pier: red while lifting/up (blinks), green when down
        px, py = sx0 + 1, C.lane_y(back) - DECK_H - 26
        surf.fill(self.RAIL, (px, py, 3, 26))
        if lift > 0.02:
            on = (ticks // 8) % 2 == 0 or lift >= 1.0
            colr = (255, 60, 40) if on else (120, 30, 30)
        else:
            colr = (80, 230, 90)
        pygame.draw.circle(surf, (24, 20, 30), (px + 1, py - 2), 4)
        pygame.draw.circle(surf, colr, (px + 1, py - 2), 3)

    def _draw_pit(self, surf, sx0, open_left=False, open_right=False):
        th = self.theme
        top = C.lane_y(0) - 2
        x0 = sx0 if open_left else sx0 + 2
        x1 = sx0 + C.TILE_W if open_right else sx0 + C.TILE_W - 2
        pygame.draw.rect(surf, (20, 16, 24), (x0, top, x1 - x0 + 1, FRONT_BOTTOM - top))
        for i in range(6):
            pygame.draw.rect(surf, (34, 28, 40), (sx0 + 6 + i * 12, top + 8 + (i % 2) * 6, 6, 3))
        lava = self.theme.get("lava")
        pygame.draw.rect(surf, art.LAVA_DARK if lava else (60, 120, 170), (x0, FRONT_BOTTOM - 14, x1 - x0 + 1, 14))
        pygame.draw.rect(surf, art.LAVA_HOT if lava else (120, 180, 220), (x0, FRONT_BOTTOM - 14, x1 - x0 + 1, 2))
        for edge, is_open in ((sx0, open_left), (sx0 + C.TILE_W - 3, open_right)):
            if is_open:
                continue
            pygame.draw.rect(surf, _shade(th["wall"], 0.7), (edge, top, 3, FRONT_BOTTOM - top))
            for lane in range(C.LANES + 1):   # hazard stripes on the lips
                y = C.lane_y(lane)
                surf.fill((250, 210, 40) if lane % 2 else (30, 30, 30), (edge - 1, y - 2, 4, 4))

    def _draw_start(self, surf, sx0):
        # Checkered line just ahead of where the bikes line up, so every front
        # tyre sits on it at the start (bike x is the midpoint between wheels).
        lx = int(sx0 + C.START_X + C.START_LINE_DX)
        for lane in range(C.LANES):
            y0 = C.lane_y(lane)
            for j in range(5):
                for i in range(2):
                    col = (250, 250, 250) if (i + j) % 2 == 0 else (24, 24, 30)
                    surf.fill(col, (lx + i * 4, int(y0 + j * 4), 4, 4))
        # gate behind lane 0, its right post on the line (kept inside the column)
        gx = lx + 4
        pygame.draw.rect(surf, (230, 230, 240), (gx - 48, C.LANE_BASE_Y - 70, 3, 58))
        pygame.draw.rect(surf, (230, 230, 240), (gx + 4, C.LANE_BASE_Y - 70, 3, 58))
        pygame.draw.rect(surf, (232, 72, 52), (gx - 50, C.LANE_BASE_Y - 78, 59, 12))
        for i in range(7):
            surf.fill((250, 250, 250) if i % 2 else (24, 24, 30), (gx - 46 + i * 8, C.LANE_BASE_Y - 75, 8, 6))

    def _draw_surfaces(self, surf, track, col, sx0):
        for lane in range(C.LANES):
            s = track.surface[lane][col]
            if s < 0:
                continue
            y0 = C.lane_y(lane)
            h = track.ground(col * C.TILE_W + 40, lane)
            cy = y0 + C.LANE_SPACING // 2 - h
            if s == MUD:
                pygame.draw.ellipse(surf, (88, 58, 40), (sx0 + 8, cy - 6, 64, 13))
                pygame.draw.ellipse(surf, (110, 76, 52), (sx0 + 16, cy - 4, 40, 7))
                surf.fill((70, 46, 30), (int(sx0 + 30), int(cy - 1), 6, 2))
            elif s in PAD_BARS:
                self._draw_pad(surf, sx0, cy, PAD_BARS[s], getattr(self, "heat_pads", False))
            elif s == WATER and self.theme.get("lava"):
                # lava pit: glowing crust rim, molten middle, a couple of bubbles
                pygame.draw.ellipse(surf, (50, 30, 30), (sx0 + 6, cy - 7, 68, 15))
                pygame.draw.ellipse(surf, art.LAVA_DARK, (sx0 + 9, cy - 5, 62, 11))
                pygame.draw.ellipse(surf, art.LAVA, (sx0 + 14, cy - 4, 50, 8))
                pygame.draw.ellipse(surf, art.LAVA_HOT, (sx0 + 24, cy - 2, 26, 4))
                pygame.draw.circle(surf, art.LAVA_HOT, (int(sx0 + 20), int(cy + 1)), 2)
                pygame.draw.circle(surf, (255, 240, 180), (int(sx0 + 56), int(cy - 1)), 1)
            elif s == WATER:
                # puddle: dark rim, blue water, sky reflection streaks
                pygame.draw.ellipse(surf, _shade(self.theme["dirt"], 0.7), (sx0 + 6, cy - 7, 68, 15))
                pygame.draw.ellipse(surf, (52, 110, 170), (sx0 + 9, cy - 5, 62, 11))
                pygame.draw.ellipse(surf, (80, 150, 210), (sx0 + 14, cy - 4, 46, 7))
                pygame.draw.line(surf, (200, 230, 255), (sx0 + 22, cy - 2), (sx0 + 36, cy - 2))
                pygame.draw.line(surf, (170, 215, 250), (sx0 + 44, cy + 1), (sx0 + 52, cy + 1))
            elif s == DEBRIS:
                # striped barrier (crash window is local x 28..52)
                bx = sx0 + 30
                pygame.draw.rect(surf, (60, 50, 50), (bx + 1, cy - 1, 20, 4))
                pygame.draw.rect(surf, (240, 240, 240), (bx, cy - 15, 20, 12))
                for i in range(0, 20, 6):
                    pygame.draw.polygon(surf, (232, 59, 59), [(bx + i, cy - 3), (bx + i + 3, cy - 15),
                                                              (bx + min(20, i + 6), cy - 15), (bx + min(20, i + 3), cy - 3)])
                pygame.draw.rect(surf, (40, 30, 30), (bx, cy - 15, 20, 12), 1)

    # pad plate (base, rim, chevron) colours by size, small -> large
    HEAT_PAD_COLS = (((170, 70, 24), (255, 150, 60), (255, 215, 90)),
                     ((150, 46, 20), (255, 120, 40), (255, 200, 60)),
                     ((130, 24, 16), (255, 70, 30), (255, 245, 150)))
    COOL_PAD_COLS = ((40, 104, 150), (30, 90, 140), (22, 74, 128))

    def _draw_pad(self, surf, sx0, cy, bars, heat):
        """Coolant / heat pad, sized by the bars it gives: the plate grows and
        carries one chevron per bar (1 small, 2 medium, 3 large)."""
        w = 12 + 15 * bars + (6 if bars == 3 else 0)
        x0 = sx0 + 40 - w // 2
        if heat:
            base, rim, chev = self.HEAT_PAD_COLS[bars - 1]
        else:
            base, rim, chev = self.COOL_PAD_COLS[bars - 1], None, (90, 220, 255)
        pygame.draw.rect(surf, base, (x0, cy - 6, w, 13), border_radius=3)
        if rim:
            pygame.draw.rect(surf, rim, (x0, cy - 6, w, 13), 1, border_radius=3)
            if bars == 3:                                  # large: a hot glow line under it
                pygame.draw.line(surf, rim, (x0 + 3, cy + 8), (x0 + w - 4, cy + 8))
        for i in range(bars):
            x = x0 + 8 + i * 15
            pygame.draw.polygon(surf, chev, [(x, cy - 4), (x + 8, cy), (x, cy + 4), (x + 3, cy)])

    # ------------------------------------------------------------------------
    def bike_screen_pos(self, bike, cam_x):
        sx = C.BIKE_SCREEN_X + (bike.x - cam_x)
        sy = C.lane_y(bike.lane_pos) + C.LANE_SPACING // 2 + 2 - bike.h
        return sx, sy

    def draw_bike(self, surf, bike, cam_x, livery="flame", frame=0, is_player=True, outline=None):
        """outline: (colour, width) for a solid outline round the rider and bike."""
        vehicle = bike.stats.vehicle
        sx, sy = self.bike_screen_pos(bike, cam_x)
        if sx < -60 or sx > self.width + 60:
            return
        ground_y = C.lane_y(bike.lane_pos) + C.LANE_SPACING // 2 + 2 - bike.track.ground(bike.x, bike.lane_index)
        if bike.airborne:
            w = max(8, 30 - int((sy - ground_y) * -0.2))
            pygame.draw.ellipse(surf, (0, 0, 0, 0) if False else _shade(self.mat_col[DIRT], 0.55),
                                (sx - w // 2, ground_y - 3, w, 5))
        if bike.state == "crash":
            self._draw_crash(surf, bike, sx, sy, livery, vehicle)
            return
        angle = bike.angle
        if bike.wobble:
            angle += math.sin(bike.wobble * 0.9) * 6
        if outline:
            img, a = self.sprites.rotated_outlined(vehicle, livery, frame, angle, *outline)
        else:
            img, a = self.sprites.rotated(vehicle, livery, frame, angle)
        art.blit_rotated(surf, img, a, (sx, sy), self.sprites.scale)
        if bike.state == "overheat" and (bike.ticks // 8) % 2 == 0:
            for i in range(3):
                pygame.draw.circle(surf, (235, 235, 240), (int(sx + 6 + i * 5), int(sy - 20 - i * 5)), 3 + i)

    def draw_boss_trail(self, surf, race, cam_x, t):
        """Boss + minion trails and the boss's hazards on the track (under the bikes)."""
        if race.brain is None:
            return
        now = race.time_ticks
        for trail in race.trails:
            self._draw_trail(surf, race, trail, cam_x, t, now)
        for hz in race.brain.hazards:
            self._draw_hazard(surf, race, hz, cam_x, t, now)

    def _trail_y(self, race, x, lane):
        return C.lane_y(lane) + C.LANE_SPACING // 2 - race.track.ground(x, lane)

    def _draw_trail(self, surf, race, trail, cam_x, t, now):
        small = trail.k < 1.0                                   # a minion's: smaller and fainter
        sz = 0.65 if small else 1.0
        for i, (x, lane, born) in enumerate(trail.points):
            sx = C.BIKE_SCREEN_X + (x - cam_x)
            if sx < -20 or sx > self.width + 20:
                continue
            k = max(0.0, 1.0 - (now - born) / trail.life)       # 1 fresh .. 0 gone
            y = self._trail_y(race, x, lane)
            j = (i * 7919) % 5 - 2
            kind = trail.kind
            if kind == "mud":
                pygame.draw.ellipse(surf, (90, 62, 38), (sx - 6 * sz, y - 3 + j * 0.4, 12 * sz, 5 * sz))
                pygame.draw.ellipse(surf, (120, 86, 52), (sx - 3 * sz, y - 2, 5 * sz, 2))
            elif kind == "sand":
                r = max(1, int((3 + 5 * (1 - k)) * sz))
                pygame.draw.circle(surf, (226, 196, 140), (int(sx), int(y - 4 - (1 - k) * 8 + j)), r)
            elif kind == "oil":
                pygame.draw.ellipse(surf, (18, 14, 26), (sx - 7 * sz, y - 3, 14 * sz, 5 * sz))
                pygame.draw.line(surf, (150, 90, 230) if i % 2 else (60, 180, 200), (sx - 3, y - 2), (sx + 2, y - 2))
            elif kind == "smoke":
                g = int(150 + 60 * (1 - k))
                pygame.draw.circle(surf, (g, g, g + 8), (int(sx), int(y - 6 - (1 - k) * 14 + j)),
                                   max(1, int((3 + 6 * (1 - k)) * sz)))
            elif kind == "fire":
                h = (4 + 9 * k) * sz * (1.0 + 0.3 * (((t + i * 3) % 4) / 3))
                pygame.draw.polygon(surf, (230, 60, 20), [(sx - 5 * sz, y), (sx, y - h), (sx + 5 * sz, y)])
                pygame.draw.polygon(surf, (255, 190, 50), [(sx - 2, y), (sx, y - h * 0.55), (sx + 2, y)])

    HAZARD_COL = {"mud": (150, 110, 60), "devil": (236, 206, 140), "pyro": (255, 120, 40), "lava": (255, 80, 20)}

    def _draw_hazard(self, surf, race, hz, cam_x, t, now):
        sx = C.BIKE_SCREEN_X + (hz.x - cam_x)
        if sx < -60 or sx > self.width + 60:
            return
        y = self._trail_y(race, hz.x, hz.lane)
        col = self.HAZARD_COL[hz.kind]
        if not hz.live(now):
            # warning: a blinking marker on the lane (and a shadow / crack where it lands)
            if (now - hz.start) // 6 % 2 == 0:
                pygame.draw.polygon(surf, col, [(sx - 10, y - 2), (sx, y - 9), (sx + 10, y - 2), (sx, y + 4)], 2)
            if hz.kind == "mud":
                r = 4 + 10 * (now - hz.start) / max(1, hz.warn)
                pygame.draw.ellipse(surf, (40, 30, 24), (sx - r, y - r / 3, 2 * r, 2 * r / 3))
            elif hz.kind == "lava":
                pygame.draw.line(surf, (255, 120, 30), (sx - 12, y), (sx + 12, y - 1), 2)
            return
        if hz.kind == "mud":
            pygame.draw.ellipse(surf, (88, 60, 36), (sx - 38, y - 6, 76, 12))
            pygame.draw.ellipse(surf, (118, 84, 52), (sx - 24, y - 4, 40, 6))
        elif hz.kind == "devil":
            for k in range(5):                                       # a spinning funnel of sand
                a = t * 0.5 + k * 1.3
                w = 4 + k * 3
                pygame.draw.ellipse(surf, (226, 196, 140) if k % 2 else (190, 160, 110),
                                    (sx - w + math.sin(a) * 3, y - 6 - k * 6, 2 * w, 5), 2)
        elif hz.kind == "pyro" and not hz.used:
            h = 30 + 10 * ((t * 7) % 3)
            pygame.draw.polygon(surf, (240, 60, 20), [(sx - 8, y), (sx, y - h), (sx + 8, y)])
            pygame.draw.polygon(surf, (255, 210, 80), [(sx - 4, y), (sx, y - h * 0.6), (sx + 4, y)])
        elif hz.kind == "lava" and not hz.used:
            pygame.draw.ellipse(surf, art.LAVA_DARK, (sx - 34, y - 6, 68, 12))
            pygame.draw.ellipse(surf, art.LAVA, (sx - 26, y - 4, 52, 8))
            bub = (t // 5) % 3
            pygame.draw.circle(surf, art.LAVA_HOT, (int(sx - 10 + bub * 10), int(y - 6 - bub * 2)), 3)

    def draw_hoops(self, surf, track, cam_x, t, front=False):
        """Flaming hoops (track.hoops), seen side-on as a tall thin ring of fire.
        The back half is drawn before the bikes, the front half after, so a bike
        flies through it."""
        if not track.hoops:
            return
        L = track.length
        k = self.sprites.scale
        for hx, hh, lane in track.hoops:
            wx = hx + round((cam_x - hx) / L) * L                 # nearest lap copy to the camera
            sx = C.BIKE_SCREEN_X + (wx - cam_x)
            if sx < -40 or sx > self.width + 40:
                continue
            cy = C.lane_y(lane) + C.LANE_SPACING // 2 + 2 - hh - 14 * k   # around the rider's middle
            ry, rx = 24, 9
            rect = pygame.Rect(int(sx - rx), int(cy - ry), 2 * rx, 2 * ry)
            a0, a1 = (math.pi / 2, 3 * math.pi / 2) if not front else (-math.pi / 2, math.pi / 2)
            pygame.draw.arc(surf, (120, 40, 20), rect.inflate(4, 4), a0, a1, 5)
            pygame.draw.arc(surf, (255, 110, 30), rect, a0, a1, 4)
            pygame.draw.arc(surf, (255, 220, 90), rect.inflate(-3, -3), a0, a1, 1)
            # flickering flame tongues round the ring
            for i in range(8):
                ang = a0 + (a1 - a0) * (i + 0.5) / 8
                px, py = sx + rx * math.cos(ang), cy - ry * math.sin(ang)
                fl = 3 + ((t + i * 5) % 6)
                col = (255, 190, 60) if (t // 3 + i) % 2 else (255, 100, 30)
                pygame.draw.polygon(surf, col, [(px - 2, py), (px + 2, py), (px, py - fl)])

    @staticmethod
    def fire_level(bike):
        """0 (no flames) .. 1 (about to blow): the bike catches fire once its heat
        is more than half way into the red window."""
        red_at = C.ONE_SUPER_AT if bike.one_button else C.RED_AT
        start = red_at + (C.TEMP_OVERHEAT - red_at) * C.FIRE_FROM
        if bike.state != "ride" or bike.temp <= start:
            return 0.0
        return min(1.0, (bike.temp - start) / max(0.01, C.TEMP_OVERHEAT - start))

    # flame roots along the bike (sprite px from the ground contact, before scaling)
    FIRE_ROOTS = ((-17, -14), (-9, -17), (-1, -20), (7, -18), (14, -13), (-5, -9))

    def draw_bike_fire(self, surf, bike, cam_x, t):
        """Flames licking up off the bike in the hot end of the red window: they
        grow and flicker harder the closer the engine is to blowing up."""
        f = self.fire_level(bike)
        if f <= 0:
            return
        sx, sy = self.bike_screen_pos(bike, cam_x)
        k = self.sprites.scale
        a = math.radians(bike.angle)
        ca, sa = math.cos(a), math.sin(a)
        for i, (dx, dy) in enumerate(self.FIRE_ROOTS):
            dx, dy = dx * k, dy * k
            px = sx + dx * ca + dy * sa
            py = sy - dx * sa + dy * ca
            flick = ((t * 3 + i * 7) % 5) / 4.0
            h = (6 + 10 * f) * (0.7 + 0.5 * flick)
            w = 2.5 + 2.5 * f
            sway = math.sin(t * 0.5 + i) * 2
            tip = (px + sway - bike.vx * 0.4, py - h)              # flames trail back as you ride
            pygame.draw.polygon(surf, (220, 40, 20), [(px - w, py), tip, (px + w, py)])
            pygame.draw.polygon(surf, (255, 150, 30), [(px - w * 0.6, py), (px + sway * 0.6 - bike.vx * 0.25,
                                                                          py - h * 0.65), (px + w * 0.6, py)])
            pygame.draw.polygon(surf, (255, 235, 140), [(px - w * 0.25, py), (px, py - h * 0.35),
                                                         (px + w * 0.25, py)])

    def emit_fire_embers(self, bike, cam_x):
        f = self.fire_level(bike)
        if f <= 0:
            return
        sx, sy = self.bike_screen_pos(bike, cam_x)
        wx = bike.x - (sx - (C.BIKE_SCREEN_X + bike.x - cam_x))
        for _ in range(1 + int(2 * f)):
            self.particles.emit(wx + self._rng.uniform(-10, 8), sy - 12 + self._rng.uniform(-4, 4),
                                -bike.vx * 0.4 + self._rng.uniform(-0.4, 0.4), self._rng.uniform(-1.6, -0.6),
                                self._rng.randint(10, 22), (255, 160, 40) if self._rng.random() < 0.6
                                else (255, 230, 120), size=2, gravity=-0.02)

    def draw_boss_aura(self, surf, race, cam_x, t):
        """A ring round the boss while the player is inside its aura (Hex, Heat Wave,
        Sandblast), drawn over the bikes."""
        brain = race.brain
        if brain is None or not brain.aura_on:
            return
        from bosses import BOSSES
        boss = race.rivals[race.boss_i]
        sx, sy = self.bike_screen_pos(boss, cam_x)
        g = BOSSES[race.boss]["glow"]
        r = 26 + 3 * math.sin(t * 0.2)
        pygame.draw.ellipse(surf, g, (sx - r * 1.4, sy - r * 0.5 - 8, r * 2.8, r), 2)

    def _draw_explosion(self, surf, bike, sx, sy, livery, vehicle):
        """Fireball, rider launched sky-high, then a new bike parachutes in."""
        T = bike.crash_total
        e = T - bike.timer
        liv = art.livery(livery)
        # fireball (first ~0.5 s), then a smouldering scorch mark
        if e < 30:
            k = e / 30
            for r, col in ((26, (255, 90, 30)), (18, (255, 180, 50)), (9, (255, 245, 200))):
                rad = max(1, int(r * (0.4 + 0.9 * k) * (1.1 - 0.5 * k)))
                pygame.draw.circle(surf, col, (int(sx), int(sy - 10)), rad)
        scorch_x = sx
        if e < T * C.EXPLODE_DROP_AT:
            pygame.draw.ellipse(surf, (40, 34, 30), (scorch_x - 16, sy - 3, 32, 6))
        # rider: big arc up and forward, a dazed pause, then jog back
        p1, p2 = 0.30 * T, 0.45 * T
        dist = 80
        if e < p1:
            k = e / p1
            rx, ry = sx + dist * k, sy - 18 - 110 * math.sin(math.pi * k)
            surf.blit(art.draw_rider_tumble(liv, int(e / 3) % 4), (rx - 12, ry - 12))
        elif e < p2:
            surf.blit(art.draw_rider_tumble(liv, 1), (sx + dist - 12, sy - 18))
        else:
            k = min(1.0, (e - p2) / (T * C.EXPLODE_DROP_AT - p2))
            rx = sx + dist * (1 - k) + 14 * (k >= 1)       # waits beside the landing spot
            surf.blit(art.draw_rider_run(liv, e), (rx - 8, sy - 22))
        # replacement bike floats down on a parachute, lands, then bounces once
        d0, d1 = 0.45 * T, T * C.EXPLODE_DROP_AT
        if e >= d0:
            img, a = self.sprites.rotated(vehicle, livery, 0, 0, rider=False)
            if e < d1:
                k = (e - d0) / (d1 - d0)
                y = sy - 230 * (1 - k)
                sway = math.sin(e * 0.15) * 5
                art.blit_rotated(surf, img, 0, (sx + sway, y), self.sprites.scale)
                cx, cy = sx + sway, y - 46
                pygame.draw.line(surf, (230, 230, 240), (cx - 14, cy + 2), (sx + sway - 12, y - 18), 1)
                pygame.draw.line(surf, (230, 230, 240), (cx + 14, cy + 2), (sx + sway + 12, y - 18), 1)
                dome = [(cx + 18 * math.cos(t), cy + 2 - 14 * math.sin(t))
                        for t in (math.pi * i / 10 for i in range(11))]
                pygame.draw.polygon(surf, (240, 70, 60), dome)
                pygame.draw.polygon(surf, (250, 250, 250), [(cx, cy + 2)] + dome[4:7])
                pygame.draw.line(surf, (150, 40, 40), (cx - 18, cy + 2), (cx + 18, cy + 2), 2)
            else:
                bounce = max(0.0, 6 * math.sin(min(math.pi, (e - d1) * 0.35)))
                art.blit_rotated(surf, img, 0, (sx, sy - bounce), self.sprites.scale)

    def _draw_crash(self, surf, bike, sx, sy, livery, vehicle):
        if bike.crash_reason == "explode":
            self._draw_explosion(surf, bike, sx, sy, livery, vehicle)
            return
        T = bike.crash_total
        e = T - bike.timer
        liv = art.livery(livery)
        if bike.crash_reason == "pit":
            # bike vanished into the pit; rider climbs out and runs back
            img, a = self.sprites.rotated(vehicle, livery, 0, 0, rider=False)
            if e > T * 0.5:
                art.blit_rotated(surf, img, 0, (sx, sy - 4), self.sprites.scale)
        else:
            tumble = min(e, 18)
            ang = -tumble * 22 if e < 18 else 160
            img, a = self.sprites.rotated(vehicle, livery, 0, ang, rider=False)
            art.blit_rotated(surf, img, a, (sx, sy - (6 if e >= 18 else 3)), self.sprites.scale)
        p1, p2 = 0.35 * T, 0.55 * T
        dist = 30 + min(70, bike.crash_speed * 1.6) if hasattr(bike, "crash_speed") else 60
        if e < p1:
            k = e / p1
            rx = sx + dist * k
            ry = sy - 18 - 40 * math.sin(math.pi * k)
            img = art.draw_rider_tumble(liv, int(e / 4) % 4)
            surf.blit(img, (rx - 12, ry - 12))
        elif e < p2:
            img = art.draw_rider_tumble(liv, 1)
            surf.blit(img, (sx + dist - 12, sy - 18))
        else:
            k = (e - p2) / (T - p2)
            rx = sx + dist * (1 - k)
            surf.blit(art.draw_rider_run(liv, e), (rx - 8, sy - 22))

    # -- turbo -----------------------------------------------------------------------
    # Flame origin in sprite coords: each vehicle's tail pipe (ui/art.py); the
    # scrambler's high pipe exits higher, the trike's short pipe lower.
    EXHAUST = {"trike": (2, 31), "scrambler": (3, 25), "sprinter": (4, 28)}
    EXHAUST_DEFAULT = (5, 28)

    def exhaust_pos(self, bike, cam_x):
        """Screen position of the tail pipe and the backward unit vector along the bike."""
        sx, sy = self.bike_screen_pos(bike, cam_x)
        a = math.radians(bike.angle)
        ex, ey = self.EXHAUST.get(bike.stats.vehicle, self.EXHAUST_DEFAULT)
        k = self.sprites.scale
        dx, dy = (ex - art.CONTACT[0]) * k, (ey - art.CONTACT[1]) * k
        px = sx + dx * math.cos(a) + dy * math.sin(a)
        py = sy - dx * math.sin(a) + dy * math.cos(a)
        return px, py, (-math.cos(a), math.sin(a))

    def draw_boost_flame(self, surf, bike, cam_x, t, k=1.0, super_boost=False, palette="flame"):
        """Flickering exhaust flame behind the bike (drawn before the sprite). k = 0..1 fade.
        Overheating: a longer flame with a hot blue-white core."""
        px, py, (bx, by) = self.exhaust_pos(bike, cam_x)
        nx, ny = -by, bx                       # perpendicular
        flick = (t * 7919) % 5
        pal = art.boost_palette(palette)
        o, m, c = pal["boost"][1]
        layers = ((24 + flick * 2, 9, o), (16 + flick, 6, m), (8 + flick // 2, 3, c))
        if super_boost:
            ro, rm, rc = pal["red"][1]
            layers = ((26 + flick * 3, 11, ro), (18 + flick * 2, 7, rm),
                      (12 + flick, 4, rc), (6, 2, (255, 255, 255)))
        for length, width, col in layers:
            L, w = length * k, width * (0.5 + 0.5 * k) / 2
            pts = [(px + nx * w, py + ny * w), (px + bx * L, py + by * L), (px - nx * w, py - ny * w)]
            pygame.draw.polygon(surf, col, pts)

    def draw_heat_flame(self, surf, bike, cam_x, t, palette="flame"):
        """One-button mode: the exhaust flame is the heat gauge. It grows with heat
        and shifts from yellow-orange (cold) through orange (boost) to deep red
        (super / about to blow), flickering harder in the red window."""
        h = max(0.0, min(1.0, bike.temp / C.TEMP_OVERHEAT))
        if h < 0.03:
            return
        px, py, (bx, by) = self.exhaust_pos(bike, cam_x)
        nx, ny = -by, bx
        red = bike.temp >= C.ONE_SUPER_AT
        flick = (t * 7919) % 5 * (2 if red else 1)
        # Colour steps at the band edges so "boosting or not" reads at a glance:
        # (outer, mid, core) at the start and end of each band, blended within it.
        T = bike.temp
        pal = art.boost_palette(palette)
        if T < C.ONE_BOOST_AT:          # cold: a small pale flame
            k, (a, b) = T / C.ONE_BOOST_AT, pal["cold"]
        elif not red:                    # boost band: deepening
            k, (a, b) = (T - C.ONE_BOOST_AT) / (C.ONE_SUPER_AT - C.ONE_BOOST_AT), pal["boost"]
        else:                            # red window: the scheme's most intense colour
            k, (a, b) = 1.0, pal["red"]
        cols = [tuple(int(a[j][i] + (b[j][i] - a[j][i]) * k) for i in range(3)) for j in range(3)]
        layers = ((4 + 36 * h + flick * 1.5, 3 + 9 * h, cols[0]),
                  (3 + 25 * h + flick, 2 + 6 * h, cols[1]),
                  (2 + 12 * h + flick * 0.5, 1 + 3 * h, cols[2]))
        for length, width, col in layers:
            w = width / 2
            pts = [(px + nx * w, py + ny * w), (px + bx * length, py + by * length),
                   (px - nx * w, py - ny * w)]
            pygame.draw.polygon(surf, col, pts)

    def draw_boost_wind(self, surf, bike, cam_x, t, k=1.0, hot=False, palette="flame"):
        """Speed streaks rushing past the rider (drawn over the bikes).
        hot: super boost, about to blow - the streaks burn orange-red."""
        sx, sy = self.bike_screen_pos(bike, cam_x)
        w, h = 220, 56
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        speed = 10 + bike.speed * 0.3
        for i in range(7):
            y = 4 + (i * 29 + 11) % (h - 8)
            ln = 16 + (i % 3) * 10
            x = w - ((t * speed + i * 61) % (w + ln))
            a = int((170 + (i % 2) * 70) * k)
            th = 1 + (i % 3 == 0)
            pygame.draw.line(layer, (40, 30, 60, a // 2), (x, y + th), (x + ln, y + th), 1)
            streak = art.boost_palette(palette)["streak"]
            col = (streak[0] if i % 2 else streak[1]) if hot else (255, 255, 255)
            pygame.draw.line(layer, (*col, a), (x, y), (x + ln, y), th)
        surf.blit(layer, (sx - w + 70, sy - h + 6))

    def emit_boost_sparks(self, bike, cam_x, palette="flame"):
        px, py, (bx, by) = self.exhaust_pos(bike, cam_x)
        wx = bike.x + (px - (C.BIKE_SCREEN_X + bike.x - cam_x))
        for col in art.boost_palette(palette)["sparks"]:
            self.particles.emit(wx + bx * 6, py + by * 6, bx * self._rng.uniform(1, 2.5) - bike.vx * 0.2,
                                by * 2 + self._rng.uniform(-0.6, 0.3), self._rng.randint(6, 12), col)

    HEAT_ARC_SEGS = C.HEAT_BARS
    HEAT_ARC_DROP = {}               # per-vehicle arc offset (all riders sit at one height now)

    def draw_heat_arc(self, surf, bike, cam_x, t, always=False):
        """Heat gauge worn by the rider: a smooth curved bar over the helmet, filled
        exactly like the old bottom bar (0..overheat one-button, start..overheat
        classic) in its colours: green, orange in the boost band, flashing red in
        the red window. The zones show as a dim track behind, with ticks at the
        boost and red edges. always: show it at any heat (the player's, the only
        heat gauge); otherwise only once boosting (rivals, so the pack stays clear)."""
        if bike.one_button:
            lo, boost_at, red_at = 0.0, C.ONE_BOOST_AT, C.ONE_SUPER_AT
        else:
            lo, boost_at, red_at = C.TEMP_START, C.TEMP_STABLE_A, 27.0
        if bike.state != "ride" or (not always and bike.temp < boost_at):
            return
        hi = C.TEMP_OVERHEAT
        sx, sy = self.bike_screen_pos(bike, cam_x)
        cx, cy = sx + C.HEAT_ARC_DX, sy + C.HEAT_ARC_DY + self.HEAT_ARC_DROP.get(bike.stats.vehicle, 0)
        r0, r1 = C.HEAT_ARC_R, C.HEAT_ARC_R + 4
        a0, a1 = math.radians(172), math.radians(8)             # left, over the helmet, right

        def ang(v):
            return a0 + (a1 - a0) * max(0.0, min(1.0, (v - lo) / (hi - lo)))

        def band(v0, v1, col, outline=False):
            b0, b1 = ang(v0), ang(v1)
            n = max(2, int(abs(b1 - b0) / math.radians(4)) + 1)
            outer = [(cx + math.cos(b0 + (b1 - b0) * k / n) * r1, cy - math.sin(b0 + (b1 - b0) * k / n) * r1)
                     for k in range(n + 1)]
            inner = [(cx + math.cos(b1 - (b1 - b0) * k / n) * r0, cy - math.sin(b1 - (b1 - b0) * k / n) * r0)
                     for k in range(n + 1)]
            if outline:
                pygame.draw.polygon(surf, col, outer + inner, 3)
            pygame.draw.polygon(surf, col, outer + inner)

        band(lo, hi, (20, 16, 28), outline=True)                # dark backing for contrast
        band(lo, boost_at, (34, 52, 84))                        # dim zone track: cold / boost / overheating
        band(boost_at, red_at, (92, 60, 30))
        band(red_at, hi, (96, 26, 30))
        temp = min(bike.temp, hi)
        if temp > lo:
            # the fill runs icy blue (cold) through orange (boost) to flaming red
            # (overheating), each slice coloured by its own heat; overheating flickers
            stops = ((lo, (130, 205, 255)), (boost_at, (200, 240, 255)), ((boost_at + red_at) / 2, (255, 190, 70)),
                     (red_at, (255, 110, 30)), (hi, (225, 25, 15)))
            hot = temp >= red_at and (t // 4) % 2 == 1
            step = (hi - lo) / 48
            v = lo
            while v < temp:
                v1 = min(temp, v + step)
                col = _heat_colour(stops, (v + v1) / 2)
                if hot and v >= red_at:
                    col = (255, 220, 160)
                band(v, v1 + step * 0.15, col)                  # tiny overlap: no seams
                v = v1
        for v in (boost_at, red_at):                            # zone edge ticks
            a = ang(v)
            pygame.draw.line(surf, (245, 245, 250), (cx + math.cos(a) * (r0 - 1), cy - math.sin(a) * (r0 - 1)),
                             (cx + math.cos(a) * (r1 + 1), cy - math.sin(a) * (r1 + 1)), 1)

    TILT_COL = {-1: ((175, 230, 255), (30, 175, 255)),    # back / nose up: pale -> vivid cyan
                1: ((255, 210, 160), (255, 100, 25))}     # forward / nose down: pale -> vivid orange

    def draw_tilt_arrow(self, surf, bike, cam_x, direction, level=1, max_level=1):
        """Lean indicator: a curved arrow just ahead of the bike's nose that turns
        the way the bike is being rotated (up = lean back, down = lean forward).
        It follows the bike's angle. Stronger aim = longer, thicker, more vivid."""
        if not direction or bike.state != "ride":
            return
        sx, sy = self.bike_screen_pos(bike, cam_x)
        a = math.radians(bike.angle)
        ox, oy = 0, -18 * self.sprites.scale              # pivot: middle of the bike
        cx = sx + ox * math.cos(a) + oy * math.sin(a)
        cy = sy - ox * math.sin(a) + oy * math.cos(a)
        t = level / max_level if max_level > 1 else 0.55
        span = math.radians(28 + 46 * t)
        R = 29 * self.sprites.scale
        pale, vivid = self.TILT_COL[direction]
        col = tuple(int(pale[i] + (vivid[i] - pale[i]) * t) for i in range(3))
        w = 2 if t < 0.5 else 3
        # nose up turns counter-clockwise: the arrow runs from low to high
        s0, s1 = (-span / 2, span / 2) if direction < 0 else (span / 2, -span / 2)
        n = 8
        pts = [(cx + R * math.cos(a + s0 + (s1 - s0) * i / n),
                cy - R * math.sin(a + s0 + (s1 - s0) * i / n)) for i in range(n + 1)]
        # arrowhead along the tangent at the end
        e = a + s1
        tx, ty =(-math.sin(e), -math.cos(e)) if direction < 0 else (math.sin(e), math.cos(e))
        hx, hy = pts[-1]
        hs = 5 + 3 * t
        nx, ny = -ty, tx
        head = [(hx + tx * hs, hy + ty * hs), (hx + nx * hs * 0.75, hy + ny * hs * 0.75),
                (hx - nx * hs * 0.75, hy - ny * hs * 0.75)]
        dark = (20, 16, 28)
        pygame.draw.lines(surf, dark, False, pts, w + 2)
        pygame.draw.polygon(surf, dark, head, 3)
        pygame.draw.lines(surf, col, False, pts, w)
        for p in pts[1:-1]:
            pygame.draw.circle(surf, col, p, w / 2)       # fill the joins of the thick line
        pygame.draw.polygon(surf, col, head)

    def draw_speed_lines(self, surf, t, k, hot=False):
        """Screen-wide streaks in the sky and over the ground while boosting.
        k = 0..1 strength (more, longer, faster lines); hot = super boost."""
        if k <= 0.02:
            return
        W, H = surf.get_size()
        layer = pygame.Surface((W, H), pygame.SRCALPHA)
        n = int(6 + 16 * k)
        bands = ((22, C.LANE_BASE_Y - 40), (C.LANE_BASE_Y + C.LANES * C.LANE_SPACING + 6, H - 34))
        for i in range(n):
            y0, y1 = bands[i % 2]
            y = y0 + (i * 53 + 17) % max(1, y1 - y0)
            ln = int((30 + (i % 4) * 22) * (0.6 + 0.8 * k))
            speed = (18 + (i % 3) * 7) * (0.7 + k)
            x = W - ((t * speed + i * 97) % (W + ln))
            a = int((60 + (i % 3) * 40) * k)
            col = ((255, 120, 50) if i % 2 else (255, 200, 90)) if hot else (255, 255, 255)
            pygame.draw.line(layer, (*col, a), (x, y), (x + ln, y), 1 + (i % 5 == 0))
        surf.blit(layer, (0, 0))

    def emit_smoke(self, bike, cam_x, danger=0.0):
        """Dark smoke pouring off the engine in super boost. danger 0..1 (closer
        to the explosion) makes it thicker and darker."""
        px, py, (bx, by) = self.exhaust_pos(bike, cam_x)
        sx, sy = self.bike_screen_pos(bike, cam_x)
        wx0 = bike.x - (sx - px)                       # exhaust, in world x
        for _ in range(1 + int(danger * 2)):
            # from the exhaust and from the engine under the rider
            ox, oy = (wx0, py) if self._rng.random() < 0.5 else (bike.x - 2, sy - 12)
            g = int(120 - 70 * danger + self._rng.uniform(-14, 14))
            self.particles.emit(ox + self._rng.uniform(-3, 3), oy + self._rng.uniform(-2, 2),
                                -bike.vx * 0.55 + self._rng.uniform(-0.4, 0.4),
                                self._rng.uniform(-1.1, -0.5), self._rng.randint(22, 38),
                                (g, g - 6, g - 4), size=3, gravity=-0.01, grow=7 + 5 * danger)

    def _dust_colour(self, bike):
        mat = bike.track.material_at(bike.x)
        base = self.mat_col.get(mat, self.theme["dirt"])
        if mat == GRASS:
            return _shade(base, 0.85), mat
        pale = (236, 222, 196)                  # dry dust reads lighter than the track
        return tuple(int(base[i] * 0.45 + pale[i] * 0.55) for i in range(3)), mat

    def emit_dust(self, bike, cam_x, boost=False):
        """Dust kicked up behind the rear tyre while riding: more and bigger puffs
        the faster the bike goes, extra while boosting; grass throws less."""
        if bike.airborne or bike.state != "ride" or bike.speed < 8:
            return
        sx, sy = self.bike_screen_pos(bike, cam_x)
        if sx < -40 or sx > self.width + 40:
            return
        col, mat = self._dust_colour(bike)
        k = min(1.0, bike.speed / 50.0)
        rate = (0.25 + 0.55 * k) * (1.5 if boost else 1.0) * (0.5 if mat == GRASS else 1.0)
        r = self._rng
        while rate > 0:
            if r.random() < rate:
                self.particles.emit(bike.x - 14 + r.uniform(-2, 2), sy + 4 + r.uniform(-1, 1),
                                    -r.uniform(0.3, 1.2) - bike.vx * 0.15, -r.uniform(0.15, 0.7),
                                    r.randint(16, 30), col, size=3, gravity=0.012,
                                    grow=4 + 6 * k, alpha=150)
            rate -= 1
        if r.random() < 0.18 * k:            # the odd clod of dirt flicked off the knobs
            self.particles.emit(bike.x - 16, sy + 1, -r.uniform(0.8, 2.0) - bike.vx * 0.2,
                                -r.uniform(0.8, 1.8), r.randint(12, 20), _shade(col, 0.7), 2, 0.12)

    def emit_landing_dust(self, bike, strength=1.0):
        """A cloud of dust from both tyres on touchdown; strength 0..1 (fall speed)."""
        sx, sy = self.bike_screen_pos(bike, 0)
        col, mat = self._dust_colour(bike)
        r = self._rng
        n = int(8 + 18 * strength) // (2 if mat == GRASS else 1)
        for i in range(n):
            wheel = -14 if i % 2 else 14
            side = r.choice((-1, 1))
            self.particles.emit(bike.x + wheel + r.uniform(-3, 3), sy + 4 + r.uniform(-1, 1),
                                side * r.uniform(0.3, 1.6 + 1.2 * strength) + bike.vx * 0.25,
                                -r.uniform(0.1, 0.5 + 0.6 * strength), r.randint(20, 36), col,
                                size=4 + int(3 * strength), gravity=0.015,
                                grow=8 + 10 * strength, alpha=180)
        for _ in range(int(3 + 5 * strength)):  # dirt clods
            self.particles.emit(bike.x + r.uniform(-16, 16), sy + 2, r.uniform(-1.6, 1.6) + bike.vx * 0.2,
                                -r.uniform(1.0, 2.2) * (0.6 + strength * 0.6), r.randint(14, 24),
                                _shade(col, 0.7), 2, 0.14)

    def emit_splash(self, bike, col, hi):
        """Puddle splash / lava spatter: droplets thrown up and forward from the tyres."""
        sx, sy = self.bike_screen_pos(bike, 0)
        r = self._rng
        for i in range(18):
            self.particles.emit(bike.x + r.uniform(-14, 16), sy + 3,
                                r.uniform(-1.5, 2.0) + bike.vx * 0.3, -r.uniform(1.2, 3.2),
                                r.randint(14, 26), hi if i % 3 == 0 else col, 2, 0.16)

    def emit_burst(self, bike, color, n=14, spread=2.5):
        sx, sy = self.bike_screen_pos(bike, 0)
        for _ in range(n):
            self.particles.emit(bike.x, sy - 8, self._rng.uniform(-spread, spread),
                                self._rng.uniform(-spread * 1.2, 0), self._rng.randint(16, 30), color, 2)
