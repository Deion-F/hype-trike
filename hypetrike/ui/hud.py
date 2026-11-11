"""HUD: lap timer, temperature gauge, speed, position, run info, popups."""
import pygame

import config as C
from race import fmt_time

_fonts = {}


def font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def text(surf, s, pos, size=20, color=C.HUD_FG, anchor="topleft", shadow=True):
    f = font(size)
    img = f.render(str(s), False, color)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        sh = f.render(str(s), False, (0, 0, 0))
        surf.blit(sh, (r.x + 1, r.y + 1))
    surf.blit(img, r)
    return r


def panel(surf, rect, alpha=170, color=C.HUD_BG, radius=6):
    s = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    pygame.draw.rect(s, (*color, alpha), (0, 0, rect[2], rect[3]), border_radius=radius)
    surf.blit(s, (rect[0], rect[1]))


class Popups:
    def __init__(self):
        self.items = []  # [text, color, ticks, x, y]

    def add(self, s, color, x, y, ticks=50):
        for p in self.items:
            if p[0] == s:          # refresh instead of stacking duplicates
                p[2], p[3], p[4] = ticks, x, y
                return
        self.items.append([s, color, ticks, x, y])

    def update(self):
        for p in self.items:
            p[2] -= 1
            p[4] -= 0.5
        self.items = [p for p in self.items if p[2] > 0]

    def draw(self, surf):
        for s, col, t, x, y in self.items:
            text(surf, s, (x, y), 22, col, anchor="center")


def temp_gauge(surf, temp, x, y, w=150, h=10, ticks=0):
    panel(surf, (x - 4, y - 16, w + 8, h + 22), 150)
    text(surf, "TEMP", (x, y - 14), 16)
    surf.fill((40, 36, 52), (x, y, w, h))
    k = (temp - C.TEMP_START) / (C.TEMP_OVERHEAT - C.TEMP_START)
    k = max(0.0, min(1.0, k))
    if temp < 20:
        col = C.GOOD
    elif temp < 27:
        col = C.ACCENT
    else:
        col = C.DANGER if (ticks // 6) % 2 == 0 else (255, 140, 120)
    surf.fill(col, (x, y, int(w * k), h))
    # A-stable marker and danger zone
    mx = x + int(w * (C.TEMP_STABLE_A - C.TEMP_START) / (C.TEMP_OVERHEAT - C.TEMP_START))
    surf.fill((250, 250, 250), (mx, y - 2, 1, h + 4))
    dz = x + int(w * (27 - C.TEMP_START) / (C.TEMP_OVERHEAT - C.TEMP_START))
    pygame.draw.rect(surf, C.DANGER, (dz, y, x + w - dz, h), 1)


def heat_gauge_one(surf, temp, boost_level, x, y, w=150, h=10, ticks=0):
    """One-button heat gauge, 0..overheat: normal | BOOST band | red SUPER window."""
    panel(surf, (x - 4, y - 16, w + 8, h + 22), 150)
    full = C.TEMP_OVERHEAT
    px = lambda t: x + int(w * max(0.0, min(full, t)) / full)        # noqa: E731
    b0, s0 = px(C.ONE_BOOST_AT), px(C.ONE_SUPER_AT)
    surf.fill((40, 36, 52), (x, y, w, h))
    surf.fill((86, 62, 40), (b0, y, s0 - b0, h))                      # boost band
    surf.fill((110, 30, 36), (s0, y, x + w - s0, h))                  # red window
    if temp < C.ONE_BOOST_AT:
        col = C.GOOD
    elif temp < C.ONE_SUPER_AT:
        col = (255, 150, 50)
    else:
        col = C.DANGER if (ticks // 4) % 2 == 0 else (255, 230, 200)
    surf.fill(col, (x, y, px(temp) - x, h))
    surf.fill((250, 250, 250), (b0, y - 2, 1, h + 4))
    pygame.draw.rect(surf, C.DANGER, (s0, y - 1, x + w - s0, h + 2), 1)
    label = {0: ("HEAT", C.HUD_FG), 1: ("BOOST", (255, 170, 70)), 2: ("SUPER BOOST!", C.DANGER)}
    s, c = label.get(boost_level, label[0])
    text(surf, s, (x, y - 14), 16, c)


def race_hud(surf, race, width, ticks, extra_left=None, best=None, heat_bar=True):
    b = race.bike
    panel(surf, (6, 6, 150, 40))
    lap = min(race.laps_done + 1, race.track.laps)
    text(surf, f"LAP {lap}/{race.track.laps}", (12, 10), 18)
    text(surf, fmt_time(race.time_ticks), (12, 26), 22, C.ACCENT)
    if race.lap_times:
        panel(surf, (width - 136, 6, 130, 40))
        text(surf, f"LAST {fmt_time(race.lap_times[-1])}", (width - 130, 10), 18)
        if best:
            text(surf, f"BEST {fmt_time(best)}", (width - 130, 26), 18)
    if race.rivals:
        n = len(race.rivals) + 1
        panel(surf, (width // 2 - 40, 6, 80, 26))
        text(surf, f"P{race.position()}/{n}", (width // 2, 19), 24,
             C.ACCENT if race.position() == 1 else C.HUD_FG, anchor="center")
    if extra_left:
        for i, line in enumerate(extra_left):
            text(surf, line, (12, 52 + i * 14), 16)
    gx = width // 2 - 75
    if not heat_bar:
        pass                    # heat shown on the rider instead (setting "heat_gauge")
    elif getattr(b, "one_button", False):
        lvl = b.boost_level if b.state == "ride" else 0
        heat_gauge_one(surf, b.temp, lvl, gx, C.VIEW_H - 18, ticks=ticks)
    else:
        temp_gauge(surf, b.temp, gx, C.VIEW_H - 18, ticks=ticks)
    text(surf, f"{int(b.speed):02d}", (gx + 162, C.VIEW_H - 24), 22)
    text(surf, "SPD", (gx + 162, C.VIEW_H - 34), 12)
    if b.state == "overheat" and (ticks // 10) % 2 == 0:
        text(surf, "OVERHEAT!", (width // 2, 120), 40, C.DANGER, anchor="center")
    if race.countdown > 0:
        n = race.countdown // C.FPS + 1
        text(surf, str(n), (width // 2, 120), 72, C.ACCENT, anchor="center")
    elif race.time_ticks < 45:
        text(surf, "GO!", (width // 2, 120), 72, C.GOOD, anchor="center")
