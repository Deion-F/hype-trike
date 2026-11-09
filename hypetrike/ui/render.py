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
        self.items = []   # [x, y, vx, vy, life, max_life, color, size] in world coords (x=track px)

    def emit(self, x, y, vx, vy, life, color, size=2):
        if len(self.items) < 220:
            self.items.append([x, y, vx, vy, life, life, color, size])

    def update(self):
        keep = []
        for p in self.items:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += 0.05
            p[4] -= 1
            if p[4] > 0:
                keep.append(p)
        self.items = keep

    def draw(self, surf, cam_x):
        for x, y, _, _, life, ml, col, size in self.items:
            sx = C.BIKE_SCREEN_X + (x - cam_x)
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
    def draw_backdrop(self, surf, cam_x):
        W = self.far.get_width()
        for layer, k in ((self.far, 0.08), (self.mid, 0.4)):
            off = -int(cam_x * k) % (W // 2)
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
        if getattr(self, "_cache_track", None) is not track or self._cache_theme != self.theme_name:
            self._cache_track = track
            self._cache_theme = self.theme_name
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

    def _draw_crash(self, surf, bike, sx, sy, livery, vehicle):
        T = bike.stats.crash_ticks
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
