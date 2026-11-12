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
                 title="", info_lines=None, rival_level=0.5, seed=0,
                 target=None, context=None, replay=None):
        """context: what this race is, for the recording (run heat, quick race...).
        replay: a recording dict to play back instead of reading input."""
        super().__init__(app)
        self.track = track
        self.stats = stats
        self.livery = livery
        self.on_done = on_done
        self.title = title
        self.info_lines = info_lines or []
        self.target = target
        self.race = Race(track, stats, rivals=rivals, rival_level=rival_level, seed=seed)
        self.replay = replay
        if replay is not None:
            import replay as rp
            self.race.bike.one_button = replay["race"]["one_button"]
            self._replay_ctl = rp.unrle(replay["inputs"])
            self._replay_i = 0
            self.replay_fast = False
        else:
            self.race.bike.one_button = app.profile.settings.get("throttle_mode") == "one"
        self.recorder = None
        self.recording_path = None
        if replay is None and app.profile.settings.get("record_races", True):
            from replay import Recorder
            self.recorder = Recorder(self.race, livery, context, app.profile.settings)
        self.renderer = WorldRenderer(app.view.width, track.theme)
        self.renderer.heat_pads = self.race.bike.one_button   # pads draw as heat pads
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
        self.fx_boost = 0.0         # 0..1 eased "speed feel" from boosting (any level)
        self.fx_super = 0.0         # 0..1 eased extra feel from super boost
        self.bg_scroll = 0.0        # backdrop parallax position (runs ahead while boosting)
        self.tilt = (0, 0, 1)       # (direction, level, max level) for the lean arrow
        self._air_prev = {}         # id(bike) -> (airborne, vy) last tick, for landing dust
        app.audio.music(None)

    def on_resize(self):
        self.renderer.set_theme(self.renderer.theme_name, self.app.view.width)
        self.app.input.layout(self.app.view.width)

    # ------------------------------------------------------------------------
    def frame(self, inp):
        for k in inp.keys_down:
            if k in (pygame.K_ESCAPE, pygame.K_p, pygame.K_AC_BACK):
                self.paused = not self.paused
            elif self.replay is not None and self.result is None and k in (pygame.K_f, pygame.K_TAB):
                self.replay_fast = not self.replay_fast
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
        fast = self.replay is not None and self.replay_fast and self.result is None
        for _ in range(2 if fast else 1):
            self._tick()

    def _tick(self):
        if self.paused:
            self.app.input.consume_edges()
            return
        self.ticks += 1
        if self.replay is not None:
            ctl = self._replay_next()
            if ctl is None:
                return
            self.tilt = ((-1 if ctl.left else 1), 1, 1) if ctl.left != ctl.right and self.race.started \
                else (0, 0, 1)
        else:
            ctl = self.app.input.race_controls(self.race.bike)
            self.tilt = self.app.input.tilt(ctl, self.race.bike) if self.race.started else (0, 0, 1)
        self.app.input.consume_edges()
        if self.race.countdown > 0:
            sec = self.race.countdown // C.FPS
            if sec != self._last_count and sec < 3:
                self.app.audio.event("beep")
            self._last_count = sec
        ev = self.race.step(ctl)
        if self.recorder:
            self.recorder.tick(ctl, ev)
        b = self.race.bike
        sx, sy = self.renderer.bike_screen_pos(b, b.x)
        for e in ev:
            k = e[0]
            if k in ("perfect", "land", "rough"):
                # Every real landing (not micro-hops): home moves to the cursor, so
                # the air lean the hand was holding becomes the new neutral.
                self.app.input.recenter_anchor()
            if k == "perfect":
                self.popups.add("PERFECT!", C.ACCENT, sx, sy - 40)
                self.renderer.emit_burst(b, (255, 230, 120), 10, 1.5)
            elif k == "rough":
                self.popups.add("ROUGH  -HEAT" if b.one_button else "ROUGH", (255, 160, 90), sx, sy - 40)
                if b.one_button:
                    self.renderer.emit_burst(b, (200, 200, 210), 10, 1.4)     # heat vented as steam
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
            elif k == "recovered":
                self.app.input.recenter_anchor()     # fresh start: home is where the cursor is
            elif k == "bike_drop":
                self.renderer.emit_burst(b, (240, 220, 180), 12, 2)       # dust as it lands
            elif k == "forgiven":
                self.popups.add("SAVED!", C.COOL, sx, sy - 40)
            elif k == "splash":
                self.popups.add("SPLASH", C.COOL, sx, sy - 40, 30)
                self.renderer.emit_splash(b, (110, 180, 240), (210, 235, 255))
            elif k == "lava":
                self.popups.add("LAVA!", (255, 130, 40), sx, sy - 40, 40)
                self.renderer.emit_splash(b, (255, 110, 30), (255, 220, 90))
            elif k == "vent":
                self.popups.add("VENTED!", C.COOL, sx, sy - 40)
                self.renderer.emit_burst(b, (235, 235, 240), 16, 1.4)     # steam
            elif k == "overheat":
                self.renderer.emit_burst(b, (235, 235, 240), 16, 1.2)     # steam
            elif k == "coolant":
                self.popups.add("COOL", C.COOL, sx, sy - 40, 30)
                self.renderer.emit_burst(b, (120, 220, 255), 10, 1.5)
            elif k == "heatpad":
                bars = e[1]
                self.popups.add("HEAT" + "+" * bars, (255, 120, 40), sx, sy - 40, 30)
                self.renderer.emit_burst(b, (255, 150, 40), 6 + 5 * bars, 1.2 + 0.5 * bars)
            elif k == "lap":
                self.best_lap = e[1] if self.best_lap is None else min(self.best_lap, e[1])
                if self.race.laps_done < self.track.laps:
                    self.popups.add(f"LAP {fmt_time(e[1])}", C.HUD_FG, self.app.view.width // 2, 90, 90)
            elif k == "finish":
                self._finish()
            self.app.audio.event(k)
        self.app.audio.engine(b, ctl)
        self._dust(b)
        self._ambient(b)
        boosting = b.boost_level > 0 and b.state == "ride" and self.race.started
        if boosting:
            self.boost_lvl = b.boost_level
        self.boost_k = min(1.0, self.boost_k + 0.25) if boosting else max(0.0, self.boost_k - 0.15)
        # Speed feel: ease toward the boost level, then scroll the backdrop faster.
        tb = 1.0 if boosting else 0.0
        ts = 1.0 if boosting and b.boost_level == 2 else 0.0
        self.fx_boost += max(-C.FX_EASE, min(C.FX_EASE, tb - self.fx_boost))
        self.fx_super += max(-C.FX_EASE, min(C.FX_EASE, ts - self.fx_super))
        self.bg_scroll += b.vx * (1 + C.FX_BG_BOOST * self.fx_boost + C.FX_BG_SUPER * self.fx_super)
        if boosting and self.ticks % (2 if b.boost_level == 2 else 3) == 0:
            self.renderer.emit_boost_sparks(b, b.x)
        if b.state == "ride" and b.boost_level == 2:
            # super boost: smoke, thicker as the heat nears the explosion
            danger = (b.temp - C.ONE_SUPER_AT) / (C.TEMP_OVERHEAT - C.ONE_SUPER_AT)
            if self.ticks % (3 if danger < 0.5 else 2) == 0:
                self.renderer.emit_smoke(b, b.x, max(0.0, min(1.0, danger)))
        self.renderer.particles.update()
        self.popups.update()
        if self.finish_hold > 0:
            self.finish_hold -= 1

    def _dust(self, me):
        """Riding dust for every bike on screen, and a dust cloud on touchdown
        (sized by how fast the bike came down)."""
        rd = self.renderer
        cam = me.x
        for bk in [me, *self.race.rivals]:
            prev = self._air_prev.get(id(bk))
            if prev and prev[0] and not bk.airborne and bk.state in ("ride", "done"):
                rd.emit_landing_dust(bk, max(0.15, min(1.0, -prev[1] / 6.0)))
            self._air_prev[id(bk)] = (bk.airborne, bk.vy)
            rd.emit_dust(bk, cam, bk.boost_level > 0)

    YOU_TICKS = 90                     # player marker stays this long after GO
    PERFECT_GOLD = ((255, 205, 50), 2)

    def _outline(self, b):
        """Player outline: gold while lined up for a perfect landing, a pulsing
        white/yellow 'this is you' outline at the start, otherwise none."""
        if b.perfect_aligned():
            return self.PERFECT_GOLD
        if self.race.countdown > 0 or self.race.time_ticks < self.YOU_TICKS:
            return ((255, 255, 255) if (self.ticks // 10) % 2 else C.ACCENT, 2)
        return None

    def _draw_you(self, surf, rd, b, cam):
        """'YOU' tag with a little arrow over the player's helmet at the start."""
        sx, sy = rd.bike_screen_pos(b, cam)
        x, y = int(sx + C.HEAT_ARC_DX), int(sy - 62 - (self.ticks // 8) % 2)
        hud.text(surf, "YOU", (x, y - 8), 16, C.ACCENT, anchor="center")
        pygame.draw.polygon(surf, (20, 18, 30), [(x - 6, y - 1), (x + 6, y - 1), (x, y + 6)])
        pygame.draw.polygon(surf, C.ACCENT, [(x - 4, y), (x + 4, y), (x, y + 4)])

    def _ambient(self, b):
        """Volcano level: embers drifting up out of the ground."""
        if self.track.theme != C.LAVA_THEME or self.ticks % 3:
            return
        rd = self.renderer
        r = rd._rng
        x = b.x + r.uniform(-C.BIKE_SCREEN_X, self.app.view.width - C.BIKE_SCREEN_X)
        rd.particles.emit(x, C.lane_y(r.uniform(0, C.LANES)), r.uniform(-0.3, 0.3),
                          -r.uniform(0.4, 1.0), r.randint(40, 80),
                          r.choice(((255, 140, 40), (255, 210, 80), (230, 70, 30))), 1, -0.004)

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
        self._save_recording()
        self.finish_hold = 50 if not self.forfeit else 0
        self.paused = False
        if self.forfeit:
            self._leave()

    def _save_recording(self):
        """Write the recording once, when the race ends (finished or quit)."""
        if not self.recorder or self.recording_path:
            return
        import replay as rp
        try:
            self.recording_path = rp.save(self.recorder.finish(self.result))
        except OSError:
            self.recording_path = None          # never let a full disk break a race
        self.recorder = None

    def _replay_next(self):
        """Next recorded control; at the end of the tape the replay finishes."""
        import replay as rp
        if self._replay_i >= len(self._replay_ctl):
            if self.result is None:
                self._finish()
            return None
        v = self._replay_ctl[self._replay_i]
        self._replay_i += 1
        return rp.bits_ctl(v)

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
        # Camera runs ahead of the rider while boosting (the bike drifts back on
        # screen, more road shows ahead) and shakes a touch in super boost.
        lead = C.FX_CAM_LEAD * self.fx_boost + C.FX_CAM_LEAD_SUPER * self.fx_super
        shake = C.FX_SHAKE * self.fx_super * (((self.ticks * 7919) % 5) / 2 - 1)
        cam = b.x + lead + shake
        rd = self.renderer
        rd.draw_backdrop(surf, cam, self.bg_scroll)
        rd.draw_track(surf, self.track, cam)
        from ui.art import LIVERIES
        pool = [k for k in LIVERIES if k != self.livery]
        bikes = [(rb, pool[i % len(pool)], False)
                 for i, rb in enumerate(self.race.rivals)]
        bikes.append((b, self.livery, True))
        marked = self.race.countdown > 0 or self.race.time_ticks < self.YOU_TICKS
        # depth by lane; while the start marker shows, the player is drawn on top
        bikes.sort(key=lambda t: (marked and t[2], t[0].lane_pos))
        for bk, liv, me in bikes:
            frame = 0
            if bk.speed > 0 and bk.state == "ride":
                period = max(2, int(10 - bk.speed / 6))
                frame = (bk.ticks // period) % 2
            if me and bk.one_button and bk.state == "ride":
                rd.draw_heat_flame(surf, bk, cam, self.ticks)
            elif me and self.boost_k > 0 and bk.state == "ride":
                rd.draw_boost_flame(surf, bk, cam, self.ticks, self.boost_k, self.boost_lvl == 2)
            rd.draw_bike(surf, bk, cam, liv, frame, me, self._outline(bk) if me else None)
            if me and (self.race.countdown > 0 or self.race.time_ticks < self.YOU_TICKS) \
                    and bk.state == "ride":
                self._draw_you(surf, rd, bk, cam)
            if me and not self.paused and self.result is None:
                rd.draw_tilt_arrow(surf, bk, cam, *self.tilt)
            if me and self.app.profile.settings.get("heat_gauge", "both") != "bar":
                rd.draw_heat_arc(surf, bk, cam, self.ticks)
        if self.boost_k > 0 and b.state == "ride":
            rd.draw_boost_wind(surf, b, cam, self.ticks, self.boost_k, self.boost_lvl == 2)
        rd.particles.draw(surf, cam)
        rd.draw_speed_lines(surf, self.ticks, self.fx_boost * 0.7 + self.fx_super * 0.3,
                            self.fx_super > 0.5)
        self.popups.draw(surf)
        W = self.app.view.width
        extra = list(self.info_lines)
        if self.target:
            extra.append(self.target.describe())
        hud.race_hud(surf, self.race, W, self.ticks, extra, self.best_lap,
                     heat_bar=self.app.profile.settings.get("heat_gauge", "both") != "bike")
        if self.replay is not None and (self.ticks // 30) % 2 == 0 and self.result is None:
            hud.text(surf, "REPLAY" + ("  x2" if self.replay_fast else ""), (W // 2, 96), 26,
                     (255, 90, 90), anchor="center")
        if self.replay is not None and self.result is None:
            hud.text(surf, "F: speed x2   Esc: pause / quit", (W // 2, C.VIEW_H - 54), 15,
                     (220, 216, 236), anchor="center")
        if self.title and self.race.countdown > 0:
            hud.text(surf, self.title, (W // 2, 70), 30, C.HUD_FG, anchor="center")
        self.app.input.draw_touch(surf, hud.font)
        self.app.input.cam_lead = cam - b.x
        inp = self.app.input
        steering = ((inp.mouse_steering or inp.hover_lanes) and not self.paused and self.result is None
                    and self.replay is None)
        if steering:
            inp.draw_mouse_guide(surf, rd.bike_screen_pos(b, cam), b.airborne)
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
