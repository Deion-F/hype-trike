"""HUD: lap timer, temperature gauge, speed, position, run info, popups."""
import pygame

import config as C
from race import fmt_time

_fonts = {}
# High-res text (desktop): text drawn onto this canvas is queued instead and
# rendered smooth at the window's real resolution after the canvas is scaled up
# (main.View.present), so it isn't blocky low-res glyphs stretched 3-4x.
_hires_canvas = None
_queued = []


def set_hires_canvas(surface):
    global _hires_canvas
    _hires_canvas = surface
    _queued.clear()


def take_queued():
    out = list(_queued)
    _queued.clear()
    return out


def font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def text(surf, s, pos, size=20, color=C.HUD_FG, anchor="topleft", shadow=True):
    f = font(size)
    if surf is _hires_canvas and _hires_canvas is not None:
        r = pygame.Rect((0, 0), f.size(str(s)))
        setattr(r, anchor, pos)
        clip = surf.get_clip()
        if clip.colliderect(r):
            _queued.append((str(s), r, size, tuple(color[:3]), shadow, clip, anchor))
        return r
    img = f.render(str(s), False, color)
    r = img.get_rect(**{anchor: pos})
    if shadow:
        sh = f.render(str(s), False, (0, 0, 0))
        surf.blit(sh, (r.x + 1, r.y + 1))
    surf.blit(img, r)
    return r


def flush_queued(surf, rect=None):
    """Draw queued high-res text (all, or what overlaps `rect`) into the canvas the
    old low-res way, before something is drawn on top of it (panels, shades)."""
    if surf is not _hires_canvas or not _queued:
        return
    keep = []
    for item in _queued:
        s, r, size, color, shadow, clip, _anchor = item
        if rect is not None and not r.colliderect(rect):
            keep.append(item)
            continue
        f = font(size)
        prev = surf.get_clip()
        surf.set_clip(clip)
        if shadow:
            surf.blit(f.render(s, False, (0, 0, 0)), (r.x + 1, r.y + 1))
        surf.blit(f.render(s, False, color), r)
        surf.set_clip(prev)
    _queued[:] = keep


def panel(surf, rect, alpha=170, color=C.HUD_BG, radius=6):
    """A see-through window: a dark outline, a two-tone body (lighter top
    half), a lit inner top edge and a shaded bottom edge (16-bit UI frame)."""
    flush_queued(surf, pygame.Rect(rect))
    w, h = rect[2], rect[3]
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    hi = tuple(min(255, c + 22) for c in color)
    lo = tuple(max(0, c - 10) for c in color)
    pygame.draw.rect(s, (8, 6, 16, min(255, alpha + 60)), (0, 0, w, h), border_radius=radius)
    pygame.draw.rect(s, (*color, alpha), (1, 1, w - 2, h - 2), border_radius=max(0, radius - 1))
    if h > 8:
        pygame.draw.rect(s, (*hi, alpha), (1, 1, w - 2, (h - 2) // 2), border_top_left_radius=max(0, radius - 1),
                         border_top_right_radius=max(0, radius - 1))
        s.fill((*lo, alpha), (radius, h - 3, w - 2 * radius, 2))
    s.fill((255, 255, 255, min(255, alpha // 2 + 40)), (radius, 1, w - 2 * radius, 1))
    surf.blit(s, (rect[0], rect[1]))


class Popups:
    def __init__(self):
        self.items = []  # [text, color, ticks, x, y]

    def add(self, s, color, x, y, ticks=50):
        for p in self.items:
            if p[0] == s:          # refresh instead of stacking duplicates
                p[2], p[3], p[4] = ticks, x, y
                return
        for _ in range(4):         # another message already there: stack below it
            if not any(abs(p[3] - x) < 2 and abs(p[4] - y) < 14 for p in self.items):
                break
            y += 16
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
    """One-button heat gauge, 0..blow-up: cold | WARM | HOT | OVERHEATING."""
    panel(surf, (x - 4, y - 16, w + 8, h + 22), 150)
    full = C.TEMP_OVERHEAT
    px = lambda t: x + int(w * max(0.0, min(full, t)) / full)        # noqa: E731
    b0, s0, o0 = px(C.ONE_BOOST_AT), px(C.ONE_HOT_AT), px(C.ONE_OVERHEAT_AT)
    surf.fill((40, 36, 52), (x, y, w, h))
    surf.fill((86, 62, 40), (b0, y, s0 - b0, h))                      # warm band
    surf.fill((110, 50, 30), (s0, y, o0 - s0, h))                     # hot
    surf.fill((110, 30, 36), (o0, y, x + w - o0, h))                  # overheating
    if temp < C.ONE_BOOST_AT:
        col = C.GOOD
    elif temp < C.ONE_HOT_AT:
        col = (255, 190, 70)
    elif temp < C.ONE_OVERHEAT_AT:
        col = (255, 120, 40)
    else:
        col = C.DANGER if (ticks // 4) % 2 == 0 else (255, 230, 200)
    surf.fill(col, (x, y, px(temp) - x, h))
    surf.fill((250, 250, 250), (b0, y - 2, 1, h + 4))
    surf.fill((250, 250, 250), (s0, y - 2, 1, h + 4))
    pygame.draw.rect(surf, C.DANGER, (o0, y - 1, x + w - o0, h + 2), 1)
    label = {0: ("COLD", C.HUD_FG), 1: ("WARM", (255, 190, 70)), 2: ("HOT", (255, 130, 40)),
             3: ("OVERHEATING!", C.DANGER)}
    s, c = label.get(boost_level, label[0])
    text(surf, s, (x, y - 14), 16, c)


def race_hud(surf, race, width, ticks, extra_left=None, best=None, heat_bar=False, speed=False):
    if getattr(race, "chase", None) is not None:
        boss_hud(surf, race, width, ticks)
    else:
        _lap_hud(surf, race, width, best)
    _common_hud(surf, race, width, ticks, extra_left, heat_bar, speed)


def boss_hud(surf, race, width, ticks):
    """Boss chase: the clock, the boss's hits left, and how far ahead it is."""
    from bosses import BOSSES, HP, ENGAGE_GAP, WARN_GAP, LOSE_GAP
    ch = race.chase
    info = BOSSES[race.boss]
    panel(surf, (6, 6, 110, 40))
    text(surf, "CHASE", (12, 10), 18)
    text(surf, fmt_time(race.clock), (12, 26), 22, C.ACCENT)
    w = 230
    x0 = width // 2 - w // 2
    panel(surf, (x0, 6, w, 44))
    text(surf, info["name"], (x0 + 8, 9), 16, info["glow"])
    for i in range(HP):                                     # hits still needed: full pips
        cx = x0 + w - 14 - i * 16
        full = i < ch.hp
        pygame.draw.circle(surf, (20, 16, 28), (cx, 17), 7)
        pygame.draw.circle(surf, info["glow"] if full else (70, 66, 86), (cx, 17), 5)
    gap = max(0.0, ch.gap(race.bike))
    k = min(1.0, gap / LOSE_GAP)
    bx, bw = x0 + 8, w - 16
    surf.fill((40, 36, 52), (bx, 32, bw, 10))
    col = C.GOOD if gap < ENGAGE_GAP else (C.ACCENT if gap < WARN_GAP else C.DANGER)
    if gap >= WARN_GAP and (ticks // 8) % 2:
        col = (255, 230, 220)
    surf.fill(col, (bx, 32, max(2, int(bw * k)), 10))
    wx = bx + int(bw * WARN_GAP / LOSE_GAP)
    surf.fill((240, 240, 240), (wx, 30, 1, 14))
    text(surf, "GAP", (bx + 3, 31), 11, (20, 16, 28), shadow=False)
    if gap >= WARN_GAP and ch.outcome is None and (ticks // 12) % 2 == 0:
        text(surf, "IT'S GETTING AWAY - CATCH UP!", (width // 2, 62), 18, C.DANGER, anchor="center")


# --- LCD digits: a pixel 7-segment readout ------------------------------------------------
_SEGS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc",
         "7": "abc", "8": "abcdefg", "9": "abcfgd", "-": "g", " ": ""}


def lcd(surf, s, pos, h=12, color=C.ACCENT, off=(60, 50, 30)):
    """Draw s (digits, ':', '.', '-') as 7-segment digits h px tall at pos
    (top left); unlit segments show faintly. Returns the width used."""
    x, y = pos
    t = max(1, h // 6)                      # segment thickness
    w = h // 2 + t
    half = h // 2
    lit_hi = tuple(min(255, c + 50) for c in color)
    for ch in str(s):
        if ch in ":.":
            n = (y + h // 3, y + h - t * 2) if ch == ":" else (y + h - t,)
            for yy in n:
                surf.fill(color, (x, yy, t, t))
            x += t * 2 + 1
            continue
        on = _SEGS.get(ch, "")
        segs = {"a": (x + t, y, w - 2 * t, t), "g": (x + t, y + half - t // 2, w - 2 * t, t),
                "d": (x + t, y + h - t, w - 2 * t, t), "f": (x, y + t, t, half - t), "b": (x + w - t, y + t, t, half - t),
                "e": (x, y + half + t // 2, t, half - t - t // 2), "c": (x + w - t, y + half + t // 2, t, half - t - t // 2)}
        for k, r in segs.items():
            surf.fill(color if k in on else off, r)
            if k in on and k in "agd":
                surf.fill(lit_hi, (r[0], r[1], r[2], 1))
        x += w + max(2, t + 1)
    return x - pos[0]


def lcd_box(surf, s, rect, h=12, color=C.ACCENT):
    """A recessed LCD screen (dark inset with a lit bottom edge) holding s, right-aligned."""
    flush_queued(surf, pygame.Rect(rect))
    x, y, w, hh = rect
    surf.fill((6, 4, 12), (x, y, w, hh))
    surf.fill((22, 18, 20), (x + 1, y + 1, w - 2, hh - 2))
    surf.fill((70, 64, 90), (x + 1, y + hh - 1, w - 2, 1))
    tw = lcd(pygame.Surface((w * 2, hh)), s, (0, 0), h)
    lcd(surf, s, (x + w - tw - 3, y + (hh - h) // 2), h, color)


def start_lights(surf, cx, y, countdown):
    """A gantry of three lamps over the countdown: one more turns red each
    second, all green at GO (countdown <= 0)."""
    lit = 3 - min(3, countdown // C.FPS) if countdown > 0 else 3
    green = countdown <= 0
    x0 = cx - 46
    pygame.draw.rect(surf, (8, 6, 14), (x0, y, 92, 32), border_radius=6)
    pygame.draw.rect(surf, (52, 50, 66), (x0 + 1, y + 1, 90, 30), border_radius=5)
    surf.fill((84, 82, 100), (x0 + 6, y + 1, 80, 1))
    for i in range(3):
        c = (cx - 28 + i * 28, y + 16)
        pygame.draw.circle(surf, (14, 10, 20), c, 12)
        if green:
            col, hi = (60, 220, 90), (200, 255, 200)
        elif i < lit:
            col, hi = (230, 40, 40), (255, 190, 170)
        else:
            col, hi = (50, 30, 36), (80, 60, 66)
        pygame.draw.circle(surf, col, c, 10)
        pygame.draw.circle(surf, tuple(max(0, v - 50) for v in col), (c[0] + 2, c[1] + 2), 7)
        pygame.draw.circle(surf, col, (c[0] - 1, c[1] - 1), 7)
        surf.fill(hi, (c[0] - 5, c[1] - 6, 3, 2))


def _lap_hud(surf, race, width, best):
    panel(surf, (6, 6, 150, 40))
    lap = min(race.laps_done + 1, race.track.laps)
    text(surf, f"LAP {lap}/{race.track.laps}", (12, 20), 18)
    lcd_box(surf, fmt_time(race.clock), (64, 10, 88, 32), 14)
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


def _common_hud(surf, race, width, ticks, extra_left, heat_bar, speed):
    b = race.bike
    if extra_left:
        for i, line in enumerate(extra_left):
            text(surf, line, (12, 52 + i * 14), 16)
    gx = width // 2 - 75
    if heat_bar:                # the old bottom bar (off: heat is the curved bar over the rider)
        if getattr(b, "one_button", False):
            lvl = b.boost_level if b.state == "ride" else 0
            heat_gauge_one(surf, b.temp, lvl, gx, C.VIEW_H - 18, ticks=ticks)
        else:
            temp_gauge(surf, b.temp, gx, C.VIEW_H - 18, ticks=ticks)
    if speed:                   # speed readout: off by default (heat is the gauge), a testing option
        panel(surf, (width // 2 - 26, C.VIEW_H - 36, 52, 32), 150)
        text(surf, "SPD", (width // 2, C.VIEW_H - 28), 12, anchor="center")
        text(surf, f"{int(b.speed):02d}", (width // 2, C.VIEW_H - 13), 22, anchor="center")
    if b.state == "overheat" and (ticks // 10) % 2 == 0:
        text(surf, "OVERHEAT!", (width // 2, 120), 40, C.DANGER, anchor="center")
    if race.countdown > 0:
        n = race.countdown // C.FPS + 1
        start_lights(surf, width // 2, 152, race.countdown)
        text(surf, str(n), (width // 2, 120), 72, C.ACCENT, anchor="center")
    elif race.time_ticks < 45:
        start_lights(surf, width // 2, 152, 0)
        text(surf, "GO!", (width // 2, 120), 72, C.GOOD, anchor="center")


# -- run upgrades worn in the race ----------------------------------------------------
# Upgrades with charges per race (or per run) are drawn as round tokens with a pip
# per charge (spent pips go dark); the rest are square badges with xN when stacked.
CHARGES = {                    # upgrade id -> (bike counter left, stats field for the total)
    "barrier_buster": ("barrier_saves_left", "barrier_saves"),
    "paddle_tyres": ("barrier_saves_left", "barrier_saves"),
    "crumple_zone": ("land_saves_left", "land_saves"),
    "pro_suspension": ("land_saves_left", "land_saves"),
    "blow_off": ("vents_left", "vent_charges"),
    "twin_radiators": ("vents_left", "vent_charges"),
    "second_wind": ("forgives_left", "crash_forgives"),
    "factory_rider": ("forgives_left", "crash_forgives"),
}
ICON = 22


def _initials(name):
    words = [w for w in name.replace("-", " ").split() if w]
    return (words[0][:2] if len(words) == 1 else words[0][0] + words[1][0]).upper()


def upgrade_icons(surf, ids, bike, right, top, bottom, mode="one", names=False):
    """A column of icons down the right edge (wrapping leftwards past `bottom`)
    for the run upgrades in `ids`. names: label each (pause screen)."""
    from run.upgrades import UPGRADES, CATEGORY_COLORS
    counts = {}
    for u in ids:
        if u in UPGRADES:
            counts[u] = counts.get(u, 0) + 1
    if not counts:
        return
    step = ICON + 4
    per_col = max(1, (bottom - top) // step)
    for i, (uid, n) in enumerate(counts.items()):
        up = UPGRADES[uid]
        col, row = divmod(i, per_col)
        x = right - ICON - col * (step + (110 if names else 0))
        y = top + row * step
        colr = CATEGORY_COLORS.get(up.category, C.GOOD)
        elite = up.tier == "elite"
        edge = (255, 206, 80) if elite else (20, 16, 28)
        if uid in CHARGES:
            left_attr, total_attr = CHARGES[uid]
            left = getattr(bike, left_attr, 0)
            total = max(1, getattr(bike.stats, total_attr, 1))
            c = (x + ICON // 2, y + ICON // 2)
            dim = left <= 0
            pygame.draw.circle(surf, edge, c, ICON // 2 + 1)
            pygame.draw.circle(surf, (90, 86, 104) if dim else colr, c, ICON // 2 - 1)
            pygame.draw.circle(surf, (20, 16, 28), c, ICON // 2 - 4, 1)
            text(surf, _initials(up.title(mode)), c, 12, (20, 16, 28), anchor="center", shadow=False)
            for k in range(min(total, 4)):                   # charges left
                px = x + ICON // 2 + (k - (min(total, 4) - 1) / 2) * 6
                pygame.draw.circle(surf, (20, 16, 28), (int(px), y + ICON + 1), 3)
                pygame.draw.circle(surf, (255, 240, 200) if k < left else (70, 64, 88), (int(px), y + ICON + 1), 2)
        else:
            r = pygame.Rect(x, y, ICON, ICON)
            pygame.draw.rect(surf, edge, r.inflate(2, 2), border_radius=5)
            pygame.draw.rect(surf, colr, r, border_radius=4)
            text(surf, _initials(up.title(mode)), r.center, 12, (20, 16, 28), anchor="center", shadow=False)
            if n > 1:
                text(surf, f"x{n}", (r.right + 2, r.bottom + 2), 12, C.HUD_FG, anchor="bottomright")
        if uid == "pro_suspension" and getattr(bike, "rough_shield", False):
            # a free rough landing banked (by a perfect): a bright ring round the token
            pygame.draw.circle(surf, (140, 230, 255), (x + ICON // 2, y + ICON // 2), ICON // 2 + 3, 2)
        if names:
            text(surf, up.title(mode), (x - 4, y + ICON // 2), 12, C.HUD_FG, anchor="midright")
