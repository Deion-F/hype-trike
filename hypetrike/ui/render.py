"""World rendering: backdrop, track, surface tiles, vehicles, particles."""
import math
import random

import pygame

import config as C
from track.tiles import (PROFILES, GAP, START, COOLANT, MUD, DEBRIS,
                         DIRT, GRASS, SAND, PIT_DEPTH)
from ui import art

FRONT_BOTTOM = 342


def _shade(c, k):
    return (max(0, min(255, int(c[0] * k))), max(0, min(255, int(c[1] * k))),
            max(0, min(255, int(c[2] * k))))


class Particles:
    def __init__(self):
        # [x, y, vx, vy, life, max_life, color, size, gravity, grow] in world coords (x=track px)
        self.items = []

    def emit(self, x, y, vx, vy, life, color, size=2, gravity=0.05, grow=0.0):
        """grow > 0: a puff that swells by that many px over its life (smoke)."""
        if len(self.items) < 220:
            self.items.append([x, y, vx, vy, life, life, color, size, gravity, grow])

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

    def draw(self, surf, cam_x):
        for x, y, _, _, life, ml, col, size, _, grow in self.items:
            sx = C.BIKE_SCREEN_X + (x - cam_x)
            if grow:
                s = int(size + grow * (1 - life / ml))
                surf.fill(col, (int(sx - s / 2), int(y - s / 2), s, s))
                continue
            s = size if life > ml * 0.4 else max(1, size - 1)
            surf.fill(col, (int(sx), int(y), s, s))


class WorldRenderer:
    def __init__(self, width, theme="valley"):
        self.sprites = art.SpriteCache()
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
            off = -int(scroll * k) % (W // 2)
            surf.blit(layer, (-off, 0))
            if W - off < self.width:
                surf.blit(layer, (W - off, 0))
        th = self.theme
        # berm behind lane 0
        surf.fill(_shade(th["berm"], 0.85), (0, C.LANE_BASE_Y - 12, self.width, 12))
        surf.fill(_shade(th["berm"], 1.05), (0, C.LANE_BASE_Y - 12, self.width, 2))

    COL_TOP = C.LANE_BASE_Y - 82

    def draw_track(self, surf, track, cam_x, editor_cursor=None):
        """Blit pre-rendered columns (each column is rendered once per track)."""
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
            surf.blit(img, (int(round(C.BIKE_SCREEN_X + ci * C.TILE_W - cam_x)), self.COL_TOP))

    def _render_column(self, track, col):
        tmp = pygame.Surface((C.TILE_W + 2, FRONT_BOTTOM + 2), pygame.SRCALPHA)
        self._draw_column(tmp, track, col, 0)
        return tmp.subsurface((0, self.COL_TOP, C.TILE_W + 2, FRONT_BOTTOM + 2 - self.COL_TOP)).copy()

    def _draw_column(self, surf, track, col, sx0):
        th = self.theme
        t = track.terrain[col]
        base = self.mat_col.get(track.material[col], th["dirt"])
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

    def _draw_pit(self, surf, sx0, open_left=False, open_right=False):
        th = self.theme
        top = C.lane_y(0) - 2
        x0 = sx0 if open_left else sx0 + 2
        x1 = sx0 + C.TILE_W if open_right else sx0 + C.TILE_W - 2
        pygame.draw.rect(surf, (20, 16, 24), (x0, top, x1 - x0 + 1, FRONT_BOTTOM - top))
        for i in range(6):
            pygame.draw.rect(surf, (34, 28, 40), (sx0 + 6 + i * 12, top + 8 + (i % 2) * 6, 6, 3))
        pygame.draw.rect(surf, (60, 120, 170), (x0, FRONT_BOTTOM - 14, x1 - x0 + 1, 14))
        pygame.draw.rect(surf, (120, 180, 220), (x0, FRONT_BOTTOM - 14, x1 - x0 + 1, 2))
        for edge, is_open in ((sx0, open_left), (sx0 + C.TILE_W - 3, open_right)):
            if is_open:
                continue
            pygame.draw.rect(surf, _shade(th["wall"], 0.7), (edge, top, 3, FRONT_BOTTOM - top))
            for lane in range(C.LANES + 1):   # hazard stripes on the lips
                y = C.lane_y(lane)
                surf.fill((250, 210, 40) if lane % 2 else (30, 30, 30), (edge - 1, y - 2, 4, 4))

    def _draw_start(self, surf, sx0):
        x = sx0 + C.START_X - 4
        for lane in range(C.LANES):
            y0 = C.lane_y(lane)
            for j in range(5):
                for i in range(2):
                    col = (250, 250, 250) if (i + j) % 2 == 0 else (24, 24, 30)
                    surf.fill(col, (int(x + i * 4 - lane * 1), int(y0 + j * 4), 4, 4))
        # gate behind lane 0
        gx = int(sx0 + C.START_X)
        pygame.draw.rect(surf, (230, 230, 240), (gx - 30, C.LANE_BASE_Y - 70, 3, 58))
        pygame.draw.rect(surf, (230, 230, 240), (gx + 30, C.LANE_BASE_Y - 70, 3, 58))
        pygame.draw.rect(surf, (232, 72, 52), (gx - 32, C.LANE_BASE_Y - 78, 67, 12))
        for i in range(8):
            surf.fill((250, 250, 250) if i % 2 else (24, 24, 30), (gx - 28 + i * 8, C.LANE_BASE_Y - 75, 8, 6))

    def _draw_surfaces(self, surf, track, col, sx0):
        for lane in range(C.LANES):
            s = track.surface[lane][col]
            if s < 0:
                continue
            y0 = C.lane_y(lane)
            h = track._h[col * C.TILE_W + 40]
            cy = y0 + C.LANE_SPACING // 2 - h
            if s == MUD:
                pygame.draw.ellipse(surf, (88, 58, 40), (sx0 + 8, cy - 6, 64, 13))
                pygame.draw.ellipse(surf, (110, 76, 52), (sx0 + 16, cy - 4, 40, 7))
                surf.fill((70, 46, 30), (int(sx0 + 30), int(cy - 1), 6, 2))
            elif s == COOLANT and getattr(self, "heat_pads", False):
                # one-button mode: a heat pad (orange plate, flame chevrons)
                pygame.draw.rect(surf, (150, 46, 20), (sx0 + 12, cy - 6, 56, 13), border_radius=3)
                pygame.draw.rect(surf, (255, 120, 40), (sx0 + 12, cy - 6, 56, 13), 1, border_radius=3)
                for i in range(3):
                    x = sx0 + 20 + i * 15
                    pygame.draw.polygon(surf, (255, 200, 60), [(x, cy - 4), (x + 8, cy), (x, cy + 4), (x + 3, cy)])
            elif s == COOLANT:
                pygame.draw.rect(surf, (30, 90, 140), (sx0 + 12, cy - 6, 56, 13), border_radius=3)
                for i in range(3):
                    x = sx0 + 20 + i * 15
                    pygame.draw.polygon(surf, (90, 220, 255), [(x, cy - 4), (x + 8, cy), (x, cy + 4), (x + 3, cy)])
            elif s == DEBRIS:
                # striped barrier (crash window is local x 28..52)
                bx = sx0 + 30
                pygame.draw.rect(surf, (60, 50, 50), (bx + 1, cy - 1, 20, 4))
                pygame.draw.rect(surf, (240, 240, 240), (bx, cy - 15, 20, 12))
                for i in range(0, 20, 6):
                    pygame.draw.polygon(surf, (232, 59, 59), [(bx + i, cy - 3), (bx + i + 3, cy - 15),
                                                              (bx + min(20, i + 6), cy - 15), (bx + min(20, i + 3), cy - 3)])
                pygame.draw.rect(surf, (40, 30, 30), (bx, cy - 15, 20, 12), 1)

    # ------------------------------------------------------------------------
    def bike_screen_pos(self, bike, cam_x):
        sx = C.BIKE_SCREEN_X + (bike.x - cam_x)
        sy = C.lane_y(bike.lane_pos) + C.LANE_SPACING // 2 + 2 - bike.h
        return sx, sy

    def draw_bike(self, surf, bike, cam_x, livery="flame", frame=0, is_player=True):
        vehicle = bike.stats.vehicle
        sx, sy = self.bike_screen_pos(bike, cam_x)
        if sx < -60 or sx > self.width + 60:
            return
        ground_y = C.lane_y(bike.lane_pos) + C.LANE_SPACING // 2 + 2 - bike.track.ground(bike.x)
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
        img, a = self.sprites.rotated(vehicle, livery, frame, angle)
        art.blit_rotated(surf, img, a, (sx, sy))
        if bike.state == "overheat" and (bike.ticks // 8) % 2 == 0:
            for i in range(3):
                pygame.draw.circle(surf, (235, 235, 240), (int(sx + 6 + i * 5), int(sy - 26 - i * 5)), 3 + i)

    def _draw_explosion(self, surf, bike, sx, sy, livery, vehicle):
        """Fireball, rider launched sky-high, then a new bike parachutes in."""
        T = bike.crash_total
        e = T - bike.timer
        liv = art.LIVERIES[livery]
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
                art.blit_rotated(surf, img, 0, (sx + sway, y))
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
                art.blit_rotated(surf, img, 0, (sx, sy - bounce))

    def _draw_crash(self, surf, bike, sx, sy, livery, vehicle):
        if bike.crash_reason == "explode":
            self._draw_explosion(surf, bike, sx, sy, livery, vehicle)
            return
        T = bike.crash_total
        e = T - bike.timer
        liv = art.LIVERIES[livery]
        if bike.crash_reason == "pit":
            # bike vanished into the pit; rider climbs out and runs back
            img, a = self.sprites.rotated(vehicle, livery, 0, 0, rider=False)
            if e > T * 0.5:
                art.blit_rotated(surf, img, 0, (sx, sy - 4))
        else:
            tumble = min(e, 18)
            ang = -tumble * 22 if e < 18 else 160
            img, a = self.sprites.rotated(vehicle, livery, 0, ang, rider=False)
            art.blit_rotated(surf, img, a, (sx, sy - (8 if e >= 18 else 4)))
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
    # Flame origin in sprite coords: the dirt-bike family's tail pipe (art.draw_dirt_bike);
    # the trike has no pipe, so it fires from the back of its rear body.
    EXHAUST = {"trike": (4, 25)}
    EXHAUST_DEFAULT = (9, 27)

    def exhaust_pos(self, bike, cam_x):
        """Screen position of the tail pipe and the backward unit vector along the bike."""
        sx, sy = self.bike_screen_pos(bike, cam_x)
        a = math.radians(bike.angle)
        ex, ey = self.EXHAUST.get(bike.stats.vehicle, self.EXHAUST_DEFAULT)
        dx, dy = ex - art.CONTACT[0], ey - art.CONTACT[1]
        px = sx + dx * math.cos(a) + dy * math.sin(a)
        py = sy - dx * math.sin(a) + dy * math.cos(a)
        return px, py, (-math.cos(a), math.sin(a))

    def draw_boost_flame(self, surf, bike, cam_x, t, k=1.0, super_boost=False):
        """Flickering exhaust flame behind the bike (drawn before the sprite). k = 0..1 fade.
        Super boost: a longer flame with a hot blue-white core."""
        px, py, (bx, by) = self.exhaust_pos(bike, cam_x)
        nx, ny = -by, bx                       # perpendicular
        flick = (t * 7919) % 5
        layers = ((24 + flick * 2, 9, (255, 100, 30)), (16 + flick, 6, (255, 200, 60)),
                  (8 + flick // 2, 3, (255, 250, 220)))
        if super_boost:
            layers = ((26 + flick * 3, 11, (240, 60, 40)), (18 + flick * 2, 7, (255, 170, 50)),
                      (12 + flick, 4, (150, 220, 255)), (6, 2, (255, 255, 255)))
        for length, width, col in layers:
            L, w = length * k, width * (0.5 + 0.5 * k) / 2
            pts = [(px + nx * w, py + ny * w), (px + bx * L, py + by * L), (px - nx * w, py - ny * w)]
            pygame.draw.polygon(surf, col, pts)

    def draw_heat_flame(self, surf, bike, cam_x, t):
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
        if T < C.ONE_BOOST_AT:          # cold: small yellow flame
            k, a, b = T / C.ONE_BOOST_AT, ((255, 215, 70), (255, 240, 150), (255, 255, 235)), \
                ((255, 185, 50), (255, 230, 120), (255, 255, 230))
        elif not red:                    # boost band: orange, deepening
            k = (T - C.ONE_BOOST_AT) / (C.ONE_SUPER_AT - C.ONE_BOOST_AT)
            a, b = ((255, 130, 25), (255, 205, 70), (255, 250, 210)), \
                ((240, 70, 20), (255, 150, 40), (255, 225, 160))
        else:                            # red window: deep red
            k, a, b = 1.0, ((200, 15, 15),) * 3, ((200, 15, 15), (255, 60, 30), (255, 170, 120))
        cols = [tuple(int(a[j][i] + (b[j][i] - a[j][i]) * k) for i in range(3)) for j in range(3)]
        layers = ((4 + 36 * h + flick * 1.5, 3 + 9 * h, cols[0]),
                  (3 + 25 * h + flick, 2 + 6 * h, cols[1]),
                  (2 + 12 * h + flick * 0.5, 1 + 3 * h, cols[2]))
        for length, width, col in layers:
            w = width / 2
            pts = [(px + nx * w, py + ny * w), (px + bx * length, py + by * length),
                   (px - nx * w, py - ny * w)]
            pygame.draw.polygon(surf, col, pts)

    def draw_boost_wind(self, surf, bike, cam_x, t, k=1.0, hot=False):
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
            col = ((255, 70, 35) if i % 2 else (255, 150, 50)) if hot else (255, 255, 255)
            pygame.draw.line(layer, (*col, a), (x, y), (x + ln, y), th)
        surf.blit(layer, (sx - w + 70, sy - h + 6))

    def emit_boost_sparks(self, bike, cam_x):
        px, py, (bx, by) = self.exhaust_pos(bike, cam_x)
        wx = bike.x + (px - (C.BIKE_SCREEN_X + bike.x - cam_x))
        for col in ((255, 200, 70), (255, 130, 40)):
            self.particles.emit(wx + bx * 6, py + by * 6, bx * self._rng.uniform(1, 2.5) - bike.vx * 0.2,
                                by * 2 + self._rng.uniform(-0.6, 0.3), self._rng.randint(6, 12), col)

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

    def emit_dust(self, bike, cam_x, turbo=False):
        if bike.airborne or bike.state != "ride" or bike.speed < 6:
            return
        sx, sy = self.bike_screen_pos(bike, 0)
        mat = bike.track.material_at(bike.x)
        col = _shade(self.mat_col.get(mat, self.theme["dirt"]), 1.15)
        n = 2 if turbo else 1
        for _ in range(n):
            self.particles.emit(bike.x - 14, sy - 2 + self._rng.uniform(-1, 1),
                                -self._rng.uniform(0.5, 1.5) - bike.vx * 0.3,
                                -self._rng.uniform(0.2, 0.9), self._rng.randint(12, 22), col)

    def emit_burst(self, bike, color, n=14, spread=2.5):
        sx, sy = self.bike_screen_pos(bike, 0)
        for _ in range(n):
            self.particles.emit(bike.x, sy - 8, self._rng.uniform(-spread, spread),
                                self._rng.uniform(-spread * 1.2, 0), self._rng.randint(16, 30), color, 2)
