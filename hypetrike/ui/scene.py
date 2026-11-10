"""Scene base class and the race scene (shared by quick race, run heats and
editor playtest)."""
import pygame

import config as C
from race import Race, fmt_time
from ui import hud
from ui.render import WorldRenderer


class Scene:
    def __init__(self, app):
        self.app = app

    def on_resize(self):
        pass

    def update(self):           # one fixed tick
        pass

    def frame(self, inp):       # once per rendered frame, after input intake
        pass

    def draw(self, surf):
        pass


class RaceScene(Scene):
    """Plays one race. on_done(result_dict) is called when the player leaves."""

    def __init__(self, app, track, stats, livery="flame", rivals=0, on_done=None,
                 title="", info_lines=None, rival_skill=0.85, seed=0,
                 target=None):
        super().__init__(app)
        self.track = track
        self.stats = stats
        self.livery = livery
        self.on_done = on_done
        self.title = title
        self.info_lines = info_lines or []
        self.target = target
        self.race = Race(track, stats, rivals=rivals, rival_skill=rival_skill, seed=seed)
        self.race.bike.one_button = app.profile.settings.get("throttle_mode") == "one"
        self.renderer = WorldRenderer(app.view.width, track.theme)
        self.popups = hud.Popups()
        self.paused = False
        self.ticks = 0
        self.finish_hold = 0
        self.result = None
        self.best_lap = None
        self.forfeit = False
        self._last_count = None
        app.input.race_mode = True
        app.input.reset_mouse()
        self._cursor_visible = True
        self.boost_k = 0.0          # 0..1 fade of the turbo flame / wind effect
        self.boost_lvl = 1          # 1 boost, 2 super (last level seen, kept while fading)
        app.audio.music(None)

    def on_resize(self):
        self.renderer.set_theme(self.renderer.theme_name, self.app.view.width)
        self.app.input.layout(self.app.view.width)

    # ------------------------------------------------------------------------
    def frame(self, inp):
        for k in inp.keys_down:
            if k in (pygame.K_ESCAPE, pygame.K_p, pygame.K_AC_BACK):
                self.paused = not self.paused
        if inp.pause_tapped():
            self.paused = not self.paused
        if self.paused:
            for x, y in inp.taps():
                if self._pause_btn("resume").collidepoint(x, y):
                    self.paused = False
                elif self._pause_btn("quit").collidepoint(x, y):
                    self.forfeit = True
                    self._finish()
            for k in inp.keys_down:
                if k == pygame.K_q:
                    self.forfeit = True
                    self._finish()
        if self.result is not None and self.finish_hold <= 0:
            if inp.taps() or any(k in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z) for k in inp.keys_down):
                self._leave()

    def update(self):
        if self.paused:
            self.app.input.consume_edges()
            return
        self.ticks += 1
        ctl = self.app.input.race_controls(self.race.bike)
        self.app.input.consume_edges()
        if self.race.countdown > 0:
            sec = self.race.countdown // C.FPS
            if sec != self._last_count and sec < 3:
                self.app.audio.event("beep")
            self._last_count = sec
        ev = self.race.step(ctl)
        b = self.race.bike
        sx, sy = self.renderer.bike_screen_pos(b, b.x)
        for e in ev:
            k = e[0]
            if k == "perfect":
                self.popups.add("PERFECT!", C.ACCENT, sx, sy - 40)
                self.renderer.emit_burst(b, (255, 230, 120), 10, 1.5)
            elif k == "rough":
                self.popups.add("ROUGH", (255, 160, 90), sx, sy - 40)
            elif k == "bounce":
                self.popups.add("bump", (230, 230, 230), sx, sy - 34, 25)
            elif k == "crash":
                self.popups.add("CRASH!", C.DANGER, sx + 30, sy - 50, 70)
                self.renderer.emit_burst(b, (240, 220, 180), 18, 3)       # dirt
                self.renderer.emit_burst(b, (255, 210, 80), 10, 4.5)      # sparks
                self.renderer.emit_burst(b, (255, 120, 40), 6, 3.5)
            elif k == "explode":
                self.popups.add("BOOM!", (255, 140, 40), sx + 20, sy - 60, 90)
                self.renderer.emit_burst(b, (255, 90, 30), 24, 5)         # fire
                self.renderer.emit_burst(b, (255, 220, 90), 16, 6.5)      # sparks
                self.renderer.emit_burst(b, (70, 64, 70), 18, 3)          # smoke / debris
            elif k == "bike_drop":
                self.renderer.emit_burst(b, (240, 220, 180), 12, 2)       # dust as it lands
            elif k == "forgiven":
                self.popups.add("SAVED!", C.COOL, sx, sy - 40)
            elif k == "overheat":
                self.renderer.emit_burst(b, (235, 235, 240), 16, 1.2)     # steam
            elif k == "coolant":
                self.popups.add("COOL", C.COOL, sx, sy - 40, 30)
                self.renderer.emit_burst(b, (120, 220, 255), 10, 1.5)
            elif k == "lap":
                self.best_lap = e[1] if self.best_lap is None else min(self.best_lap, e[1])
                if self.race.laps_done < self.track.laps:
                    self.popups.add(f"LAP {fmt_time(e[1])}", C.HUD_FG, self.app.view.width // 2, 90, 90)
            elif k == "finish":
                self._finish()
            self.app.audio.event(k)
        self.app.audio.engine(b, ctl)
        if b.state == "ride" and (ctl.a or ctl.b) and self.ticks % 2 == 0:
            self.renderer.emit_dust(b, b.x, ctl.b)
        boosting = b.boost_level > 0 and b.state == "ride" and self.race.started
        if boosting:
            self.boost_lvl = b.boost_level
        self.boost_k = min(1.0, self.boost_k + 0.25) if boosting else max(0.0, self.boost_k - 0.15)
        if boosting and self.ticks % (2 if b.boost_level == 2 else 3) == 0:
            self.renderer.emit_boost_sparks(b, b.x)
        self.renderer.particles.update()
        self.popups.update()
        if self.finish_hold > 0:
            self.finish_hold -= 1

    def _finish(self):
        if self.result is not None:
            return
        r = self.race
        self.result = {
            "finished": r.finished and not self.forfeit,
            "forfeit": self.forfeit,
            "time": r.time_ticks,
            "laps": list(r.lap_times),
            "position": r.position(),
            "field": len(r.rivals) + 1,
            "perfect": r.bike.stats_counters["perfect"],
            "crashes": r.bike.stats_counters["crashes"],
            "forgiven": r.bike.stats.crash_forgives - r.bike.forgives_left,
            "distance": max(0.0, r.bike.x - C.START_X),
        }
        if self.target:
            self.result["target_met"] = self.target.check(self.result)
        self.finish_hold = 50 if not self.forfeit else 0
        self.paused = False
        if self.forfeit:
            self._leave()

    def _leave(self):
        self.app.input.race_mode = False
        self.app.input.reset_mouse()
        pygame.mouse.set_visible(True)
        self.app.audio.stop_engine()
        if self.on_done:
            self.on_done(self.result)

    # ------------------------------------------------------------------------
    def _pause_btn(self, which):
        W = self.app.view.width
        y = 170 if which == "resume" else 214
        return pygame.Rect(W // 2 - 80, y, 160, 34)

    def draw(self, surf):
        b = self.race.bike
        cam = b.x
        rd = self.renderer
        rd.draw_backdrop(surf, cam)
        rd.draw_track(surf, self.track, cam)
        from ui.art import LIVERIES
        pool = [k for k in LIVERIES if k != self.livery]
        bikes = [(rb, pool[i % len(pool)], False)
                 for i, rb in enumerate(self.race.rivals)]
        bikes.append((b, self.livery, True))
        bikes.sort(key=lambda t: t[0].lane_pos)
        for bk, liv, me in bikes:
            frame = 0
            if bk.speed > 0 and bk.state == "ride":
                period = max(2, int(10 - bk.speed / 6))
                frame = (bk.ticks // period) % 2
            if me and self.boost_k > 0 and bk.state == "ride":
                rd.draw_boost_flame(surf, bk, cam, self.ticks, self.boost_k, self.boost_lvl == 2)
            rd.draw_bike(surf, bk, cam, liv, frame, me)
        if self.boost_k > 0 and b.state == "ride":
            rd.draw_boost_wind(surf, b, cam, self.ticks, self.boost_k)
        rd.particles.draw(surf, cam)
        self.popups.draw(surf)
        W = self.app.view.width
        extra = list(self.info_lines)
        if self.target:
            extra.append(self.target.describe())
        hud.race_hud(surf, self.race, W, self.ticks, extra, self.best_lap)
        if self.title and self.race.countdown > 0:
            hud.text(surf, self.title, (W // 2, 70), 30, C.HUD_FG, anchor="center")
        self.app.input.draw_touch(surf, hud.font)
        steering = (self.app.input.mouse_steering and not self.paused and self.result is None)
        if steering:
            self.app.input.draw_mouse_guide(surf, rd.bike_screen_pos(b, cam), b.airborne)
        if steering == self._cursor_visible:      # only touch the OS cursor on change
            self._cursor_visible = not steering
            pygame.mouse.set_visible(self._cursor_visible)
        if self.paused:
            hud.panel(surf, (W // 2 - 110, 110, 220, 150), 220)
            hud.text(surf, "PAUSED", (W // 2, 136), 34, C.ACCENT, anchor="center")
            for which, label in (("resume", "RESUME"), ("quit", "QUIT RACE")):
                r = self._pause_btn(which)
                pygame.draw.rect(surf, (60, 56, 80), r, border_radius=6)
                hud.text(surf, label, r.center, 24, anchor="center")
        if self.result is not None and not self.forfeit:
            self._draw_result(surf, W)

    def _draw_result(self, surf, W):
        r = self.result
        hud.panel(surf, (W // 2 - 140, 80, 280, 150), 220)
        hud.text(surf, "FINISH!", (W // 2, 104), 40, C.ACCENT, anchor="center")
        hud.text(surf, f"TIME  {fmt_time(r['time'])}", (W // 2, 138), 26, anchor="center")
        lines = []
        if r["field"] > 1:
            lines.append(f"PLACE  {r['position']}/{r['field']}")
        lines.append(f"PERFECT LANDINGS  {r['perfect']}   CRASHES  {r['crashes']}")
        if "target_met" in r:
            lines.append("TARGET MET!" if r["target_met"] else "TARGET MISSED")
        for i, ln in enumerate(lines):
            col = C.HUD_FG
            if ln.startswith("TARGET"):
                col = C.GOOD if r["target_met"] else C.DANGER
            hud.text(surf, ln, (W // 2, 164 + i * 18), 20, col, anchor="center")
        if self.finish_hold <= 0 and (self.ticks // 20) % 2 == 0:
            hud.text(surf, "TAP / ENTER TO CONTINUE", (W // 2, 218), 18, anchor="center")
