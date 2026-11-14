"""Roguelike run flow: race intro -> race -> upgrade pick -> ... -> run over.
A run tours the biomes; each ends in a boss race followed by an elite pick."""
import pygame

import config as C
from race import fmt_time
from run.manager import (RunState, RUN_HEATS, MODIFIERS, BIOMES, RACES_PER_BIOME, biome_of,
                         is_boss)
from run.upgrades import UPGRADES, CATEGORY_COLORS
from ui import hud
from ui.menus import BackdropScene, button
from ui.scene import RaceScene
from ui.art import THEMES

CONTINUE_KEYS = (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z)
ELITE_COL = (255, 206, 80)


def upgrade_summary(ids):
    counts = {}
    for u in ids:
        if u in UPGRADES:
            counts[u] = counts.get(u, 0) + 1
    return [(UPGRADES[u], n) for u, n in counts.items()]


def start_run(app):
    p = app.profile
    sel = p.selected
    run = RunState(vehicle=sel["vehicle"], livery=p.player_livery(), kit_levels=p.data.get("kit_levels", {}),
                   bike_levels=p.bike_levels(sel["vehicle"]),
                   mode=p.settings.get("throttle_mode", "one"))
    app.set_scene(HeatIntroScene(app, run))


def biome_name(i):
    return THEMES[BIOMES[biome_of(i)]]["name"]


def race_label(i):
    """'Valley race 2' / 'Valley boss'."""
    k = i % RACES_PER_BIOME
    return f"{biome_name(i)} boss" if is_boss(i) else f"{biome_name(i)} race {k + 1}"


def draw_progress(surf, run, cx, y):
    """Three dots per biome (the boss one bigger), with a gap between biomes."""
    step, gap = 18, 16
    width = (RUN_HEATS - 1) * step + (len(BIOMES) - 1) * gap
    x0 = cx - width / 2
    for i in range(RUN_HEATS):
        x = x0 + i * step + biome_of(i) * gap
        if i < run.heat_i:
            col = C.GOOD
        elif i == run.heat_i:
            col = C.ACCENT
        else:
            col = (90, 86, 110)
        pygame.draw.circle(surf, col, (int(x), y), 8 if is_boss(i) else 5)
        if not is_boss(i):
            pygame.draw.line(surf, (90, 86, 110), (x + 5, y), (x + step - 7, y), 2)


def draw_upgrade_strip(surf, ids, x, y, max_w, mode="one"):
    for up, n in upgrade_summary(ids):
        label = up.title(mode) + (f" x{n}" if n > 1 else "")
        w = hud.font(16).size(label)[0] + 12
        if x + w > max_w:
            break
        pygame.draw.rect(surf, CATEGORY_COLORS[up.category], (x, y, w, 18), border_radius=4)
        hud.text(surf, label, (x + 6, y + 3), 16, (20, 18, 30), shadow=False)
        x += w + 4


class HeatIntroScene(BackdropScene):
    def _draw_boss_portrait(self, surf, info, W):
        """The boss, big, beside the panel: who you have to beat."""
        from ui import art
        cache = getattr(self, "_boss_sprites", None) or art.SpriteCache()
        self._boss_sprites = cache
        img = cache.vehicle(info["vehicle"], art.boss_key(self.heat.biome), (self.t // 8) % 2)
        big = pygame.transform.scale(img, (img.get_width() * 2, img.get_height() * 2))
        x = max(4, W // 2 - 200 - big.get_width() - 4)
        glow = art.outlined(big, info["glow"], 2)
        surf.blit(glow, (x - 2, 92))
        hud.text(surf, info["name"], (x + big.get_width() // 2, 96 + big.get_height() + 4), 18,
                 info["glow"], anchor="center")

    def __init__(self, app, run):
        self.run = run
        h = run.prepare_heat()
        super().__init__(app, h.track.theme)
        self.heat = h

    def frame(self, inp):
        if inp.taps() or any(k in CONTINUE_KEYS for k in inp.keys_down):
            self.go()
        if any(k in (pygame.K_ESCAPE,) for k in inp.keys_down):
            self.run.status = "lost"
            self.app.set_scene(RunOverScene(self.app, self.run, abandoned=True))

    def go(self):
        run, h = self.run, self.heat
        stats = run.stats_for_heat(h)
        info = [race_label(h.index).upper()]

        def done(result):
            met = run.record(result, stats)
            if run.status == "active":
                self.app.set_scene(UpgradeScene(self.app, run, result))
            else:
                self.app.set_scene(RunOverScene(self.app, run, abandoned=bool(result and result.get("forfeit"))))
        self.app.set_scene(RaceScene(self.app, h.track, stats, run.livery, rivals=h.rivals,
                                     rival_level=h.rival_level, seed=h.seed, on_done=done,
                                     boss=h.biome if h.boss else None,
                                     title=h.track.name,
                                     info_lines=info, target=h.target,
                                     context={"kind": "run", "run_seed": run.seed, "heat": h.index,
                                              "heats": RUN_HEATS, "biome": h.biome, "boss": h.boss,
                                              "depth": h.depth, "target": h.target.describe(),
                                              "target_kind": h.target.kind, "target_value": h.target.value,
                                              "modifier": h.target.modifier, "upgrades": list(run.upgrades),
                                              "kit": dict(run.kit_levels),
                                              "bike_levels": dict(run.bike_levels or {}),
                                              "mode": run.mode, "vehicle": run.vehicle}))

    def draw(self, surf):
        W = self.app.view.width
        self.draw_bg(surf)
        h, run = self.heat, self.run
        b = biome_of(h.index)
        if h.boss:
            title = "FINAL BOSS" if b == len(BIOMES) - 1 else f"{biome_name(h.index).upper()} BOSS"
        else:
            title = f"{biome_name(h.index).upper()}  -  RACE {h.index % RACES_PER_BIOME + 1}"
        hud.text(surf, title, (W // 2, 34), 40, C.DANGER if h.boss else C.ACCENT, anchor="center")
        draw_progress(surf, run, W // 2, 64)
        hud.panel(surf, (W // 2 - 200, 82, 400, 150), 200)
        hud.text(surf, h.track.name, (W // 2, 102), 32, anchor="center")
        hud.text(surf, f"Biome {b + 1}/{len(BIOMES)}  -  {h.track.laps} laps  -  {h.track.ncols} sections",
                 (W // 2, 126), 18, (200, 196, 220), anchor="center")
        hud.text(surf, h.target.describe(), (W // 2, 154), 24, C.HUD_FG, anchor="center")
        if h.boss:
            from bosses import BOSSES
            info = BOSSES[h.biome]
            for k, (power, what) in enumerate(info["powers"]):
                y = 166 + k * 15
                r = hud.text(surf, power + ":", (W // 2 - 192, y), 14, info["glow"])
                hud.text(surf, what, (r.right + 5, y), 14, (220, 216, 236))
            self._draw_boss_portrait(surf, info, W)
        elif h.target.modifier:
            hud.text(surf, MODIFIERS[h.target.modifier][1], (W // 2, 178), 20, C.DANGER, anchor="center")
        elif h.track.theme == C.LAVA_THEME:
            hud.text(surf, "VOLCANO: heat rises faster, cools slower - lava pits!", (W // 2, 178), 18,
                     (255, 130, 40), anchor="center")
        if h.boss:
            nxt = (f"Win: on to the {THEMES[BIOMES[b + 1]]['name']} + an elite upgrade"
                   if b + 1 < len(BIOMES) else "Win to be champion!")
            hud.text(surf, nxt, (W // 2, 218), 18, (255, 196, 90), anchor="center")
        elif h.rivals:
            hud.text(surf, f"{h.rivals} rivals on track", (W // 2, 200), 18, (200, 196, 220), anchor="center")
        hud.text(surf, "UPGRADES:", (20, 246), 18)
        if run.upgrades:
            draw_upgrade_strip(surf, run.upgrades, 20, 264, W - 20, run.mode)
        else:
            hud.text(surf, "none yet", (20, 266), 16, (170, 166, 190))
        if (self.t // 25) % 2 == 0:
            hud.text(surf, "TAP / ENTER TO RACE", (W // 2, 316), 26, C.ACCENT, anchor="center")
        hud.text(surf, "Esc: abandon run", (W - 10, C.VIEW_H - 8), 14, (170, 166, 190), anchor="bottomright")


def _wrap_center(surf, text, cx, y, w, size, col):
    f = hud.font(size)
    lines, line = [], ""
    for word in text.split():
        t = (line + " " + word).strip()
        if f.size(t)[0] > w and line:
            lines.append(line)
            line = word
        else:
            line = t
    lines.append(line)
    for i, ln in enumerate(lines[:2]):
        hud.text(surf, ln, (cx, y + i * (size + 1)), size, col, anchor="center")


class UpgradeScene(BackdropScene):
    def __init__(self, app, run, result):
        super().__init__(app, run.heat.track.theme)
        self.run = run
        self.result = result
        self.sel = 0
        self.hold = 20

    def _cards(self):
        W = self.app.view.width
        n = len(self.run.pending_offer)
        cw, gap = min(190, (W - 40) // 3 - 10), 12
        x0 = W // 2 - (n * cw + (n - 1) * gap) // 2
        return [pygame.Rect(x0 + i * (cw + gap), 100, cw, 170) for i in range(n)]

    def update(self):
        super().update()
        if self.hold > 0:
            self.hold -= 1

    def frame(self, inp):
        offers = self.run.pending_offer
        if not offers:
            self.run.heat_i += 1
            self.app.set_scene(HeatIntroScene(self.app, self.run))
            return
        if self.hold > 0:
            return
        for k in inp.keys_down:
            if k in (pygame.K_LEFT, pygame.K_a):
                self.sel = (self.sel - 1) % len(offers)
            elif k in (pygame.K_RIGHT, pygame.K_d):
                self.sel = (self.sel + 1) % len(offers)
            elif k in CONTINUE_KEYS:
                self.pick(self.sel)
                return
        for x, y in inp.taps():
            for i, r in enumerate(self._cards()):
                if r.collidepoint(x, y):
                    self.pick(i)
                    return

    def pick(self, i):
        self.app.audio.ui("upgrade")
        self.run.choose(self.run.pending_offer[i].id)
        self.app.set_scene(HeatIntroScene(self.app, self.run))

    def draw(self, surf):
        W = self.app.view.width
        self.draw_bg(surf)
        r = self.result or {}
        cleared = self.run.heats[self.run.heat_i]
        elite = cleared.boss
        title = f"{biome_name(cleared.index).upper()} CLEARED!" if elite else "RACE CLEARED!"
        hud.text(surf, title, (W // 2, 30), 40, C.GOOD, anchor="center")
        hud.text(surf, f"{fmt_time(r.get('time', 0))}   -   {r.get('perfect', 0)} perfect landings",
                 (W // 2, 58), 20, anchor="center")
        hud.text(surf, "Choose an ELITE upgrade" if elite else "Choose an upgrade", (W // 2, 84), 22,
                 ELITE_COL if elite else C.ACCENT, anchor="center")
        for i, (rect, up) in enumerate(zip(self._cards(), self.run.pending_offer)):
            on = i == self.sel
            col = CATEGORY_COLORS[up.category]
            pygame.draw.rect(surf, (52, 46, 74), rect, border_radius=10)
            pygame.draw.rect(surf, col, (rect.x, rect.y, rect.w, 26), border_top_left_radius=10,
                             border_top_right_radius=10)
            label = "ELITE " + up.category.upper() if up.tier == "elite" else up.category.upper()
            hud.text(surf, label, (rect.centerx, rect.y + 13), 18, (20, 18, 30),
                     anchor="center", shadow=False)
            hud.text(surf, up.title(self.run.mode), (rect.centerx, rect.y + 48), 24, anchor="center")
            _wrap(surf, up.text(self.run.mode), rect.x + 10, rect.y + 72, rect.w - 20, 18)
            have = self.run.upgrades.count(up.id)
            if have:
                hud.text(surf, f"owned x{have} (max {up.max_stacks})", (rect.centerx, rect.bottom - 16),
                         15, (200, 196, 220), anchor="center")
            edge = C.ACCENT if on else ELITE_COL if up.tier == "elite" else (90, 86, 110)
            pygame.draw.rect(surf, edge, rect, 3 if on or up.tier == "elite" else 1, border_radius=10)
        if self.run.upgrades:
            draw_upgrade_strip(surf, self.run.upgrades, 20, 300, W - 20, self.run.mode)


def _wrap(surf, text, x, y, w, size):
    f = hud.font(size)
    line = ""
    for word in text.split():
        t = (line + " " + word).strip()
        if f.size(t)[0] > w and line:
            hud.text(surf, line, (x, y), size)
            y += size - 2
            line = word
        else:
            line = t
    if line:
        hud.text(surf, line, (x, y), size)


class RunOverScene(BackdropScene):
    def __init__(self, app, run, abandoned=False):
        super().__init__(app)
        self.run = run
        self.abandoned = abandoned
        total, parts, mult = run.payout()
        self.total, self.parts, self.mult = total, parts, mult
        p = app.profile
        p.earn(total)
        p.data["runs"] += 1
        if run.status == "won":
            p.data["wins"] += 1
        p.data["best_heat"] = max(p.best_heat, run.heats_cleared())
        p.data["best_biome"] = max(p.data.get("best_biome", 0), run.biomes_cleared())
        p.save()
        self.hold = 40

    def update(self):
        super().update()
        if self.hold > 0:
            self.hold -= 1

    def frame(self, inp):
        if self.hold > 0:
            return
        if inp.taps() or any(k in CONTINUE_KEYS + (pygame.K_ESCAPE,) for k in inp.keys_down):
            from ui.menus import TitleScene
            self.app.set_scene(TitleScene(self.app))

    def draw(self, surf):
        W = self.app.view.width
        self.draw_bg(surf)
        run = self.run
        won = run.status == "won"
        title = "CHAMPION!" if won else ("RUN ABANDONED" if self.abandoned else "RUN OVER")
        hud.text(surf, title, (W // 2, 40), 48, C.ACCENT if won else C.DANGER, anchor="center")
        draw_progress(surf, run, W // 2, 76)
        hud.panel(surf, (W // 2 - 170, 94, 340, 176), 210)
        if not won and run.results:
            last = run.results[-1]
            h = run.heats[last["heat"]]
            hud.text(surf, f"Fell at {race_label(h.index)}: {h.target.describe()}", (W // 2, 112), 18,
                     (255, 170, 160), anchor="center")
        rows = [("Races (biomes)", f"{run.heats_cleared()}/{RUN_HEATS} ({run.biomes_cleared()}/{len(BIOMES)})",
                 self.parts["heats"]),
                ("Distance", f"{int(run.distance_cols)} sections", self.parts["distance"]),
                ("Perfect landings", str(run.perfect), self.parts["perfect"])]
        if won:
            rows.append(("Champion bonus", "", self.parts["victory"]))
        y = 134
        for label, val, coins in rows:
            hud.text(surf, label, (W // 2 - 154, y), 20)
            hud.text(surf, val, (W // 2 + 40, y), 20, (200, 196, 220), anchor="topright")
            hud.text(surf, f"+{coins}", (W // 2 + 154, y), 20, C.ACCENT, anchor="topright")
            y += 22
        if self.mult != 1.0:
            hud.text(surf, f"Sponsor multiplier x{self.mult:.2f}", (W // 2 - 154, y), 18, (200, 196, 220))
            y += 20
        pygame.draw.line(surf, (120, 116, 140), (W // 2 - 154, y + 2), (W // 2 + 154, y + 2))
        hud.text(surf, "COINS EARNED", (W // 2 - 154, y + 8), 24)
        hud.text(surf, f"{self.total}", (W // 2 + 154, y + 8), 26, C.ACCENT, anchor="topright")
        hud.text(surf, f"Bank: {self.app.profile.currency} coins", (W // 2, 286), 20, anchor="center")
        if run.upgrades:
            draw_upgrade_strip(surf, run.upgrades, 20, 308, W - 20, run.mode)
        if self.hold <= 0 and (self.t // 25) % 2 == 0:
            hud.text(surf, "TAP TO CONTINUE", (W // 2, 344), 20, C.ACCENT, anchor="center")
