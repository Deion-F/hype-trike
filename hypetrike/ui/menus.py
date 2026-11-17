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
            hud.flush_queued(surf, r)
            button_face(surf, r, on, en)
            tc = C.HUD_FG if en else (130, 126, 150)
            hud.text(surf, it["label"], (r.centerx, r.centery - (5 if it.get("sub") else 0)),
                     24 if not it.get("sub") else 22, tc, anchor="center")
            if it.get("sub"):
                hud.text(surf, it["sub"], (r.centerx, r.centery + 8), 15, (200, 196, 220), anchor="center")


def button_face(surf, rect, on=False, enabled=True):
    """A chunky 16-bit button: dark outline, a two-tone face (lit top half),
    a bright top edge, a shaded bottom lip; selected = a gold frame with a
    lit corner and a pointer notch on the left."""
    r = pygame.Rect(rect)
    base = (84, 74, 124) if on else (50, 46, 74)
    if not enabled:
        base = (44, 42, 56)
    top = tuple(min(255, c + 18) for c in base)
    lip = tuple(max(0, c - 22) for c in base)
    pygame.draw.rect(surf, (12, 8, 22), r, border_radius=7)
    inner = r.inflate(-2, -2)
    pygame.draw.rect(surf, lip, inner, border_radius=6)
    face = pygame.Rect(inner.x, inner.y, inner.w, inner.h - 2)
    pygame.draw.rect(surf, base, face, border_radius=6)
    pygame.draw.rect(surf, top, (face.x, face.y, face.w, face.h // 2), border_top_left_radius=6,
                     border_top_right_radius=6)
    surf.fill(tuple(min(255, c + 60) for c in base), (face.x + 5, face.y, face.w - 10, 1))
    if on:
        pygame.draw.rect(surf, (150, 96, 0), r, 3, border_radius=7)
        pygame.draw.rect(surf, C.ACCENT, r.inflate(-1, -1), 2, border_radius=7)
        surf.fill((255, 240, 170), (r.x + 6, r.y + 1, min(24, r.w - 12), 1))
        cy = r.centery
        pygame.draw.polygon(surf, C.ACCENT, [(r.x + 4, cy - 4), (r.x + 8, cy), (r.x + 4, cy + 4)])


def button(surf, rect, label, on=False, size=22, enabled=True):
    hud.flush_queued(surf, pygame.Rect(rect))
    button_face(surf, rect, on, enabled)
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
        self._demo_liv = app.profile.player_livery()
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


def random_biome():
    """(theme, generator depth) for a quick race or time trial: any biome, on
    tracks as hard as a normal race in that biome of a run."""
    import random
    from run.manager import BIOMES
    b = random.randrange(len(BIOMES))
    return BIOMES[b], b


class TitleScene(BackdropScene):
    def __init__(self, app):
        super().__init__(app)
        self.build_menu()

    def build_menu(self):
        items = []
        items.append(dict(label="NEW RUN", sub="5 biomes, 15 races - 3 lives", action=self.new_run))
        items.append(dict(label="TIME TRIAL", sub="Solo vs the clock - beat par", action=self.time_trial))
        items.append(dict(label="PRACTICE", sub="Valley Loop - solo, best lap", action=self.practice))
        items.append(dict(label="QUICK RACE", sub="New generated track vs 3 rivals", action=self.quick_race))
        for extra in getattr(self.app, "title_items", []):
            items.append(extra(self))
        items.append(dict(label="TRACK EDITOR", sub="Build, test & share tracks",
                          action=lambda: self.app.set_scene(__import__("editor.ui", fromlist=["x"]).EditorScene(self.app))))
        items.append(dict(label="GARAGE", sub=f"Bike upgrades (XP) & style ({self.app.profile.currency} coins)",
                          action=lambda: self.app.set_scene(__import__("ui.garage", fromlist=["x"]).GarageScene(self.app))))
        items.append(dict(label="REPLAYS", sub="Watch your recorded races",
                          action=lambda: self.app.set_scene(__import__("ui.replays", fromlist=["x"]).ReplayListScene(self.app))))
        items.append(dict(label="SETTINGS", action=lambda: self.app.set_scene(SettingsScene(self.app))))
        self.menu = Menu(items, top=82, height=29, gap=2, width=250)

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
        biome, depth = random_biome()
        tr = generate(seed, depth, validate_with=self.app.profile.player_stats()).track
        tr.theme = biome
        self.app.set_scene(RaceScene(self.app, tr, self.app.profile.player_stats(), self.app.profile.player_livery(),
                                     rivals=3, title=tr.name, seed=seed,
                                     info_lines=[f"Seed {seed}  Depth {depth}"],
                                     context={"kind": "quick", "depth": depth, "vehicle": sel["vehicle"]},
                                     on_done=lambda r: self.app.set_scene(TitleScene(self.app))))

    def time_trial(self):
        """Solo on a fresh generated track against a par time (no rivals)."""
        import random
        from track.generator import generate
        from track.validator import validate
        from bike import base_stats
        from run.manager import Target
        p = self.app.profile
        sel = p.selected
        st = self.app.profile.player_stats()
        seed = random.randrange(1 << 30)
        biome, depth = random_biome()
        g = generate(seed, depth, validate_with=st)
        tr = g.track
        tr.theme = biome
        ghost = validate(tr, st)
        par = int((ghost["ticks"] if ghost["finished"] else g.validation["ticks"]) * TRIAL_PAR_SLACK)
        self.app.set_scene(RaceScene(self.app, tr, st, self.app.profile.player_livery(), rivals=0,
                                     title=f"Time Trial: {tr.name}", seed=seed,
                                     target=Target("time", par),
                                     info_lines=[f"Seed {seed}  Depth {depth}"],
                                     context={"kind": "trial", "depth": depth, "par": par,
                                              "vehicle": sel["vehicle"]},
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
        self.app.set_scene(RaceScene(self.app, tr, self.app.profile.player_stats(),
                                     self.app.profile.player_livery(), rivals=rivals, on_done=done,
                                     title=tr.name,
                                     context={"kind": "exhibition" if rivals else "practice",
                                              "vehicle": sel["vehicle"]}))

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
        one = self.app.profile.settings.get("throttle_mode") == "one"
        hint = ("Z hold: heat builds into boost - overheating is faster, don't blow up!  arrows lean/lane" if one
                else "Z throttle  X turbo  arrows lean/lane")
        if self.app.input.button_mode:
            hint = ("Mouse: hold to heat, point at a lane - in the air hold to lean forward, let go to lift"
                    if one else "Mouse: L throttle  R turbo, point at a lane - in the air hold to lean forward")
        elif self.app.input.mouse_enabled:
            hover = self.app.profile.settings.get("mouse_lanes", "hover") == "hover"
            if hover:
                hint = ("Mouse: hold/tap to heat, point at a lane to ride it, back/fwd of home leans"
                        if one else "Mouse: L throttle  R turbo - point at a lane to ride it, drag back/fwd to lean")
            else:
                hint = ("Mouse: hold/tap to heat, cursor steers from home - hold still to move home"
                        if one else "Mouse: L throttle  R turbo - click, then drag back/fwd to lean, up/down for lanes")
        hud.text(surf, hint, (10, C.VIEW_H - 10), 16, (200, 196, 220), anchor="bottomleft")


TRIAL_PAR_SLACK = 1.12   # time trial par = ghost time (throttle only, perfect landings) x this

SLIDER = "slider"     # SETTING_ROWS marker: a 0..1 volume slider instead of a cycled option

SETTING_ROWS = [
    ("lane_mode", "Lane change", [("swipe", "Swipe"), ("buttons", "Buttons"), ("both", "Swipe + buttons")]),
    ("button_scale", "Button size", [(0.85, "Small"), (1.0, "Normal"), (1.2, "Large")]),
    ("swap_sides", "Throttle side", [(False, "Right"), (True, "Left")]),
    ("touch_ui", "Touch buttons", [("auto", "Auto"), ("on", "Always"), ("off", "Hidden")]),
    ("throttle_mode", "Throttle", [("classic", "Throttle + boost"), ("one", "One button")]),
    ("mouse_steer", "Mouse controls", [("button", "Click to lean fwd"), ("angle", "Aim angle"),
                                       ("hold", "Hold lean"), (False, "Off")]),
    ("mouse_wheelie", "Mouse wheelie", [("ramps", "Ramps only"), ("anywhere", "Anywhere")]),
    ("mouse_lanes", "Mouse lanes", [("hover", "Follow cursor"), ("drag", "Drag from home")]),
    ("air_lane_lock", "Lanes in the air", [(True, "Locked"), (False, "Free")]),
    ("lane_guide", "Mouse lane dots", [(False, "Off"), (True, "On")]),
    ("record_races", "Race recordings", [(True, "On"), (False, "Off")]),
    ("speed_gauge", "Speed gauge (testing)", [(False, "Off"), (True, "On")]),
    ("free_upgrades", "Free bike upgrades (testing)", [(False, "Off"), (True, "On")]),
    ("sfx_vol", "Sound effects", SLIDER),
    ("music_vol", "Music", SLIDER),
    ("smooth", "Desktop scaling", [(False, "Sharp"), (True, "Smooth")]),
]


class SettingsScene(BackdropScene):
    def __init__(self, app, back=None):
        super().__init__(app)
        self.back = back or (lambda: app.set_scene(TitleScene(app)))
        self.sel = 0
        self.drag = None          # (row index, pointer id) while dragging a slider
        self.scroll = 0.0         # px the list is scrolled down
        self._pan = None          # (pointer id, last y) while dragging the list

    # The list scrolls (wheel, drag, or just moving the selection) inside a fixed
    # window, so any number of settings fit; BACK stays put under it.
    PITCH = 28
    LIST_TOP = 50
    LIST_BOTTOM = C.VIEW_H - 46

    def _max_scroll(self):
        return max(0, len(SETTING_ROWS) * self.PITCH - (self.LIST_BOTTOM - self.LIST_TOP))

    def _scroll_to(self, v):
        self.scroll = max(0.0, min(float(self._max_scroll()), v))

    def _follow_sel(self):
        if self.sel < len(SETTING_ROWS):
            y = self.sel * self.PITCH
            view = self.LIST_BOTTOM - self.LIST_TOP
            if y < self.scroll:
                self._scroll_to(y)
            elif y + self.PITCH > self.scroll + view:
                self._scroll_to(y + self.PITCH - view)

    def _visible(self, r):
        return r.top >= self.LIST_TOP - 1 and r.bottom <= self.LIST_BOTTOM + 1

    def _rows(self):
        W = self.app.view.width
        rows = [pygame.Rect(W // 2 - 170, self.LIST_TOP + i * self.PITCH - int(self.scroll), 340, self.PITCH - 2)
                for i in range(len(SETTING_ROWS))]
        return rows + [pygame.Rect(W // 2 - 170, self.LIST_BOTTOM + 8, 340, 30)]

    @staticmethod
    def _bar(r):
        return pygame.Rect(r.right - 172, r.centery - 5, 112, 10)

    def _set_vol(self, i, v, save=True):
        key = SETTING_ROWS[i][0]
        st = self.app.profile.settings
        st[key] = max(0.0, min(1.0, round(v * 20) / 20))
        self.app.apply_settings()
        if save:
            self.app.profile.save()
            self.app.audio.ui("click")

    def _cycle(self, i, d=1):
        key, _, opts = SETTING_ROWS[i]
        st = self.app.profile.settings
        if opts == SLIDER:
            self._set_vol(i, st.get(key, 1.0) + 0.1 * d)
            return
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
                    if SETTING_ROWS[self.sel][2] != SLIDER or k in (pygame.K_RIGHT, pygame.K_d):
                        self._cycle(self.sel)
                elif k != pygame.K_RIGHT:
                    self.back()
            elif k in (pygame.K_ESCAPE, pygame.K_AC_BACK):
                self.back()
            self._follow_sel()
        rows = self._rows()
        for kind, pid, x, y in inp.pointer_events:
            if kind == "down":
                for i, (key, _, opts) in enumerate(SETTING_ROWS):
                    bar = self._bar(rows[i])
                    if opts == SLIDER and self._visible(rows[i]) and bar.inflate(16, 18).collidepoint(x, y):
                        self.sel = i
                        self.drag = (i, pid)
                        self._set_vol(i, (x - bar.x) / bar.w, save=False)
                if not self.drag and self.LIST_TOP <= y <= self.LIST_BOTTOM:
                    self._pan = (pid, y)
            elif kind == "move" and self.drag and self.drag[1] == pid:
                bar = self._bar(rows[self.drag[0]])
                self._set_vol(self.drag[0], (x - bar.x) / bar.w, save=False)
            elif kind == "move" and self._pan and self._pan[0] == pid:
                self._scroll_to(self.scroll - (y - self._pan[1]))
                self._pan = (pid, y)
            elif kind == "up" and self._pan and self._pan[0] == pid:
                self._pan = None
            elif kind == "up" and self.drag and self.drag[1] == pid:
                self._set_vol(self.drag[0], self.app.profile.settings[SETTING_ROWS[self.drag[0]][0]])
                self.drag = None
            elif kind == "wheel":
                self._scroll_to(self.scroll - x * self.PITCH)       # x carries the wheel's y steps
        for x, y in inp.taps():
            for i, r in enumerate(rows):
                if r.collidepoint(x, y) and (i == len(SETTING_ROWS) or self._visible(r)):
                    self.sel = i
                    if i < n:
                        if SETTING_ROWS[i][2] != SLIDER:
                            self._cycle(i)
                    else:
                        self.back()

    def draw(self, surf):
        W = self.app.view.width
        self.draw_bg(surf)
        hud.text(surf, "SETTINGS", (W // 2, 26), 36, C.ACCENT, anchor="center")
        st = self.app.profile.settings
        rows = self._rows()
        fs = 20
        for i, (key, label, opts) in enumerate(SETTING_ROWS):
            r = rows[i]
            if not self._visible(r):
                continue
            on = i == self.sel
            pygame.draw.rect(surf, (78, 70, 110) if on else (46, 42, 66), r, border_radius=6)
            if on:
                pygame.draw.rect(surf, C.ACCENT, r, 2, border_radius=6)
            hud.text(surf, label, (r.x + 12, r.centery), fs, anchor="midleft")
            if opts == SLIDER:
                v = float(st.get(key, 1.0))
                bar = self._bar(r)
                pygame.draw.rect(surf, (24, 22, 36), bar, border_radius=5)
                if v > 0:
                    pygame.draw.rect(surf, C.ACCENT, (bar.x, bar.y, max(6, int(bar.w * v)), bar.h),
                                     border_radius=5)
                kx = bar.x + int(bar.w * v)
                pygame.draw.circle(surf, (20, 18, 30), (kx, bar.centery), 8)
                pygame.draw.circle(surf, C.HUD_FG, (kx, bar.centery), 6)
                txt = f"{int(round(v * 100))}%" if v > 0 else "Off"
                hud.text(surf, txt, (r.right - 12, r.centery), fs, C.ACCENT, anchor="midright")
            else:
                val = dict(opts).get(st.get(key), str(st.get(key)))
                hud.text(surf, f"< {val} >", (r.right - 12, r.centery), fs, C.ACCENT, anchor="midright")
        button(surf, rows[-1], "BACK", self.sel == len(SETTING_ROWS))
        if self._max_scroll():                    # scrollbar
            x = rows[0].right + 8
            h = self.LIST_BOTTOM - self.LIST_TOP
            view = h / (h + self._max_scroll())
            pygame.draw.rect(surf, (46, 42, 66), (x, self.LIST_TOP, 5, h), border_radius=3)
            pygame.draw.rect(surf, C.ACCENT, (x, self.LIST_TOP + int((h - h * view) * self.scroll /
                                                                      self._max_scroll()), 5, int(h * view)),
                             border_radius=3)
