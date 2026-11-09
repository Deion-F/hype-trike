"""Menus: title screen and shared widgets."""
import pygame

import config as C
from ui import hud
from ui.scene import Scene, RaceScene
from ui.render import WorldRenderer


class Menu:
    """Vertical button list; keyboard + tap."""

    def __init__(self, items, top=150, width=240, height=30, gap=6, cx=None):
        self.items = items        # list of dicts: label, action, enabled=True, sub=""
        self.top, self.w, self.h, self.gap = top, width, height, gap
        self.cx = cx
        self.sel = 0

    def rects(self, W):
        cx = self.cx if self.cx is not None else W // 2
        return [pygame.Rect(cx - self.w // 2, self.top + i * (self.h + self.gap), self.w, self.h)
                for i in range(len(self.items))]

    def handle(self, inp, W, audio=None):
        rs = self.rects(W)
        for k in inp.keys_down:
            if k in (pygame.K_UP, pygame.K_w):
                self.sel = (self.sel - 1) % len(self.items)
            elif k in (pygame.K_DOWN, pygame.K_s):
                self.sel = (self.sel + 1) % len(self.items)
            elif k in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z):
                it = self.items[self.sel]
                if it.get("enabled", True):
                    if audio:
                        audio.ui("click")
                    it["action"]()
                    return True
        for kind, _, x, y in inp.pointer_events:
            if kind == "hover":
                for i, r in enumerate(rs):
                    if r.collidepoint(x, y):
                        self.sel = i
        for x, y in inp.taps():
            for i, r in enumerate(rs):
                if r.collidepoint(x, y):
                    self.sel = i
                    it = self.items[i]
                    if it.get("enabled", True):
                        if audio:
                            audio.ui("click")
                        it["action"]()
                        return True
        return False

    def draw(self, surf, W):
        for i, (r, it) in enumerate(zip(self.rects(W), self.items)):
            on = i == self.sel
            en = it.get("enabled", True)
            col = (78, 70, 110) if on else (46, 42, 66)
            pygame.draw.rect(surf, col, r, border_radius=7)
            if on:
                pygame.draw.rect(surf, C.ACCENT, r, 2, border_radius=7)
            tc = C.HUD_FG if en else (130, 126, 150)
            hud.text(surf, it["label"], (r.centerx, r.centery - (5 if it.get("sub") else 0)),
                     24 if not it.get("sub") else 22, tc, anchor="center")
            if it.get("sub"):
                hud.text(surf, it["sub"], (r.centerx, r.centery + 8), 15, (200, 196, 220), anchor="center")


def button(surf, rect, label, on=False, size=22, enabled=True):
    pygame.draw.rect(surf, (78, 70, 110) if on else (46, 42, 66), rect, border_radius=7)
    if on:
        pygame.draw.rect(surf, C.ACCENT, rect, 2, border_radius=7)
    hud.text(surf, label, rect.center, size, C.HUD_FG if enabled else (130, 126, 150), anchor="center")


class BackdropScene(Scene):
    """A scene with the animated track backdrop behind a menu."""

    def __init__(self, app, theme="valley"):
        super().__init__(app)
        self.bg = WorldRenderer(app.view.width, theme)
        self.cam = 0.0
        self.t = 0
        from track.static import static_track
        from race import Race
        from track.validator import GhostAI
        from bike import base_stats
        self._bg_track = static_track()
        demo_vehicle = app.profile.selected.get("vehicle", "dirt")
        self._demo = Race(self._bg_track, base_stats(demo_vehicle), lane=2, countdown=False)
        self._demo_ai = GhostAI(turbo=True, turbo_temp=22)
        self._demo_liv = app.profile.selected.get("livery", "flame")
        app.audio.music("title")

    def on_resize(self):
        self.bg.set_theme(self.bg.theme_name, self.app.view.width)

    def update(self):
        self.t += 1
        d = self._demo
        d.step(self._demo_ai.controls(d.bike))
        if d.finished:
            d.finished = False
            d.bike.state = "ride"
            d.lap_times.clear()
        self.cam = d.bike.x + 110      # keep the demo rider left of the centred menu

    def draw_bg(self, surf):
        self.bg.draw_backdrop(surf, self.cam)
        self.bg.draw_track(surf, self._bg_track, self.cam)
        b = self._demo.bike
        frame = (b.ticks // 3) % 2 if b.speed > 0 else 0
        self.bg.draw_bike(surf, b, self.cam, self._demo_liv, frame)
        shade = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        shade.fill((10, 8, 20, 120))
        surf.blit(shade, (0, 0))


class TitleScene(BackdropScene):
    def __init__(self, app):
        super().__init__(app)
        self.build_menu()

    def build_menu(self):
        items = []
        items.append(dict(label="NEW RUN", sub="6 heats - one life", action=self.new_run))
        items.append(dict(label="PRACTICE", sub="Valley Loop - solo, best lap", action=self.practice))
        items.append(dict(label="QUICK RACE", sub="New generated track vs 3 rivals", action=self.quick_race))
        for extra in getattr(self.app, "title_items", []):
            items.append(extra(self))
        items.append(dict(label="TRACK EDITOR", sub="Build, test & share tracks",
                          action=lambda: self.app.set_scene(__import__("editor.ui", fromlist=["x"]).EditorScene(self.app))))
        items.append(dict(label="GARAGE", sub=f"{self.app.profile.currency} coins - unlocks & loadout",
                          action=lambda: self.app.set_scene(__import__("ui.garage", fromlist=["x"]).GarageScene(self.app))))
        items.append(dict(label="SETTINGS", action=lambda: self.app.set_scene(SettingsScene(self.app))))
        self.menu = Menu(items, top=94, height=34, gap=4, width=250)

    def new_run(self):
        from ui.run_scenes import start_run
        start_run(self.app)

    def practice(self):
        self._race(rivals=0)

    def exhibition(self):
        self._race(rivals=3)

    def quick_race(self):
        import random
        from track.generator import generate
        from bike import base_stats
        p = self.app.profile
        sel = p.selected
        seed = random.randrange(1 << 30)
        depth = random.randint(0, 3)
        tr = generate(seed, depth, validate_with=base_stats(sel["vehicle"])).track
        from meta.shop import active_themes
        tr.theme = random.choice(active_themes(p))
        self.app.set_scene(RaceScene(self.app, tr, base_stats(sel["vehicle"]), sel["livery"],
                                     rivals=3, title=tr.name, seed=seed,
                                     info_lines=[f"Seed {seed}  Depth {depth}"],
                                     on_done=lambda r: self.app.set_scene(TitleScene(self.app))))

    def _race(self, rivals):
        from track.static import static_track
        from bike import base_stats
        p = self.app.profile
        sel = p.selected
        tr = static_track()

        def done(result):
            if result and result.get("laps"):
                p.record_lap(tr.name, min(result["laps"]))
                p.save()
            self.app.set_scene(TitleScene(self.app))
        self.app.set_scene(RaceScene(self.app, tr, base_stats(sel["vehicle"]),
                                     sel["livery"], rivals=rivals, on_done=done,
                                     title=tr.name))

    def frame(self, inp):
        self.menu.handle(inp, self.app.view.width, self.app.audio)
        for k in inp.keys_down:
            if k == pygame.K_ESCAPE and not getattr(self.app, "_web", False):
                self.app.running = False

    def draw(self, surf):
        W = self.app.view.width
        self.draw_bg(surf)
        f = hud.font(72)
        w1, w2, gap = f.size("HYPE")[0], f.size("TRIKE")[0], 18
        x0 = W // 2 - (w1 + gap + w2) // 2
        hud.text(surf, "HYPE", (x0, 48), 72, C.ACCENT, anchor="midleft")
        hud.text(surf, "TRIKE", (x0 + w1 + gap, 48), 72, (255, 120, 60), anchor="midleft")
        self.menu.draw(surf, W)
        best = self.app.profile.best_laps.get("Valley Loop")
        if best:
            from race import fmt_time
            hud.text(surf, f"Best lap: {fmt_time(best)}", (W - 10, C.VIEW_H - 10), 16,
                     anchor="bottomright")
        hud.text(surf, "Z throttle  X turbo  arrows lean/lane", (10, C.VIEW_H - 10), 16,
                 (200, 196, 220), anchor="bottomleft")


SETTING_ROWS = [
    ("lane_mode", "Lane change", [("swipe", "Swipe"), ("buttons", "Buttons"), ("both", "Swipe + buttons")]),
    ("button_scale", "Button size", [(0.85, "Small"), (1.0, "Normal"), (1.2, "Large")]),
    ("swap_sides", "Throttle side", [(False, "Right"), (True, "Left")]),
    ("touch_ui", "Touch buttons", [("auto", "Auto"), ("on", "Always"), ("off", "Hidden")]),
    ("sound", "Sound effects", [(True, "On"), (False, "Off")]),
    ("music", "Music", [(True, "On"), (False, "Off")]),
    ("smooth", "Desktop scaling", [(False, "Sharp"), (True, "Smooth")]),
]


class SettingsScene(BackdropScene):
    def __init__(self, app, back=None):
        super().__init__(app)
        self.back = back or (lambda: app.set_scene(TitleScene(app)))
        self.sel = 0

    def _rows(self):
        W = self.app.view.width
        return [pygame.Rect(W // 2 - 170, 66 + i * 34, 340, 30) for i in range(len(SETTING_ROWS) + 1)]

    def _cycle(self, i, d=1):
        key, _, opts = SETTING_ROWS[i]
        st = self.app.profile.settings
        vals = [v for v, _ in opts]
        cur = st.get(key, vals[0])
        idx = vals.index(cur) if cur in vals else 0
        st[key] = vals[(idx + d) % len(vals)]
        self.app.profile.save()
        self.app.apply_settings()
        self.app.audio.ui("click")

    def frame(self, inp):
        n = len(SETTING_ROWS)
        for k in inp.keys_down:
            if k in (pygame.K_UP, pygame.K_w):
                self.sel = (self.sel - 1) % (n + 1)
            elif k in (pygame.K_DOWN, pygame.K_s):
                self.sel = (self.sel + 1) % (n + 1)
            elif k in (pygame.K_LEFT, pygame.K_a) and self.sel < n:
                self._cycle(self.sel, -1)
            elif k in (pygame.K_RIGHT, pygame.K_d, pygame.K_RETURN, pygame.K_SPACE, pygame.K_z):
                if self.sel < n:
                    self._cycle(self.sel)
                elif k != pygame.K_RIGHT:
                    self.back()
            elif k in (pygame.K_ESCAPE, pygame.K_AC_BACK):
                self.back()
        for x, y in inp.taps():
            for i, r in enumerate(self._rows()):
                if r.collidepoint(x, y):
                    self.sel = i
                    if i < n:
                        self._cycle(i)
                    else:
                        self.back()

    def draw(self, surf):
        W = self.app.view.width
        self.draw_bg(surf)
        hud.text(surf, "SETTINGS", (W // 2, 34), 40, C.ACCENT, anchor="center")
        st = self.app.profile.settings
        rows = self._rows()
        for i, (key, label, opts) in enumerate(SETTING_ROWS):
            r = rows[i]
            on = i == self.sel
            pygame.draw.rect(surf, (78, 70, 110) if on else (46, 42, 66), r, border_radius=6)
            if on:
                pygame.draw.rect(surf, C.ACCENT, r, 2, border_radius=6)
            hud.text(surf, label, (r.x + 12, r.centery), 22, anchor="midleft")
            val = dict(opts).get(st.get(key), str(st.get(key)))
            hud.text(surf, f"< {val} >", (r.right - 12, r.centery), 22, C.ACCENT, anchor="midright")
        button(surf, rows[-1], "BACK", self.sel == len(SETTING_ROWS))
