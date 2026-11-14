"""Scene base class and the race scene (shared by quick race, run heats and
editor playtest)."""
import math

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
                 target=None, context=None, replay=None, boss=None):
        """context: what this race is, for the recording (run heat, quick race...).
        replay: a recording dict to play back instead of reading input."""
        super().__init__(app)
        self.track = track
        self.stats = stats
        self.livery = livery
        self.boost_theme = app.profile.selected.get("boost", "flame")
        self.on_done = on_done
        self.title = title
        self.info_lines = info_lines or []
        self.target = target
        self.race = Race(track, stats, rivals=rivals, rival_level=rival_level, seed=seed, boss=boss)
        self.replay = replay
        if replay is not None:
            import replay as rp
            self.race.bike.one_button = replay["race"]["one_button"]
            self.race.bike.air_lane_lock = replay["race"].get("air_lane_lock", True)
            self._replay_ctl = rp.unrle(replay["inputs"])
            self._replay_i = 0
            self.replay_fast = False
        else:
            self.race.bike.one_button = app.profile.settings.get("throttle_mode") == "one"
            self.race.bike.air_lane_lock = app.profile.settings.get("air_lane_lock", True)
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
        self._cam_offset = 0.0      # camera lag after a respawn jump (eases back to 0)
        self._prev_bx = None
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
            if k == "boss":
                self._boss_popup(e[1], sx, sy)
                continue
            if k == "hoop":
                self.popups.add("THROUGH THE HOOP!", (255, 150, 40), sx, sy - 50, 40)
                self.app.audio.event("heatpad")
                continue
            if k == "hoop_boost":
                self.popups.add("HOOP BOOST!" + (" PERFECT!" if e[1] else ""), (255, 210, 60), sx, sy - 58, 70)
                self.renderer.emit_burst(b, (255, 140, 40), 26, 3.0)
                self.app.audio.event("heatpad")
                continue
            if k == "hoop_lost":
                self.popups.add("HOOP LOST", (200, 120, 100), sx, sy - 50, 40)
                continue
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
            self.renderer.emit_boost_sparks(b, b.x, self.boost_theme)
        if self.race.started and self.ticks % 4 == 0:
            for rb in self.race.rivals:             # rivals show their boost too
                if rb.state == "ride" and rb.boost_level > 0 and abs(rb.x - b.x) < self.app.view.width:
                    self.renderer.emit_boost_sparks(rb, b.x)
        if self.ticks % 2 == 0:
            for bk in (b, *self.race.rivals):
                if abs(bk.x - b.x) < self.app.view.width:
                    self.renderer.emit_fire_embers(bk, b.x)
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
    # landing glow: green (PERFECT) -> yellow (clean) -> orange (rough) -> red (crash)
    LANDING_COLS = ((0.0, (70, 235, 90)), (0.4, (250, 225, 60)), (0.8, (255, 140, 40)), (1.0, (240, 40, 40)))

    @classmethod
    def landing_colour(cls, q):
        cols = cls.LANDING_COLS
        for (q0, c0), (q1, c1) in zip(cols, cols[1:]):
            if q <= q1:
                k = (q - q0) / max(1e-6, q1 - q0)
                return tuple(int(a + (b - a) * k) for a, b in zip(c0, c1))
        return cols[-1][1]

    def _outline(self, b):
        """Player outline: mid-air it shows the landing you're lined up for, green
        (PERFECT) through yellow and orange to red (crash); a pulsing white/yellow
        'this is you' outline at the start; otherwise none."""
        q = b.landing_quality()
        if q is not None:
            return (self.landing_colour(q), 2)
        if self.race.countdown > 0 or self.race.time_ticks < self.YOU_TICKS:
            return ((255, 255, 255) if (self.ticks // 10) % 2 else C.ACCENT, 2)
        return None

    @property
    def _boss_info(self):
        from bosses import BOSSES
        return BOSSES[self.race.boss]

    BOSS_POPUPS = {
        "bomb": ("MUD BOMB INCOMING!", (200, 150, 90)), "quake": ("QUAKE!", (200, 150, 90)),
        "devil": ("DUST DEVIL!", (236, 206, 140)), "shoved": ("SHOVED!", (236, 206, 140)),
        "blackout": ("LIGHTS OUT...", (190, 140, 255)),
        "pyro": ("PYRO CANNONS!", (255, 170, 60)), "scorched": ("SCORCHED +HEAT", (255, 120, 40)),
        "crowd_boss": ("CROWD GOES WILD", (255, 215, 60)), "crowd_you": ("STOLE THE CROWD! +SPEED", C.GOOD),
        "eruption": ("ERUPTION!", (255, 110, 30)), "lava": ("LAVA! +SPEED +HEAT", (255, 130, 40)),
    }

    def _boss_popup(self, kind, sx, sy):
        text, col = self.BOSS_POPUPS.get(kind, (kind.upper(), C.ACCENT))
        if kind in ("bomb", "devil", "blackout", "pyro", "eruption", "crowd_boss"):
            self.popups.add(text, col, self.app.view.width // 2, 118, 60)        # the boss acts
        else:
            self.popups.add(text, col, sx, sy - 44, 45)                        # it got you
        self.app.audio.event("rough" if kind in ("shoved", "quake", "scorched") else "heatpad"
                             if kind in ("lava", "crowd_you") else "beep")

    def _draw_blackout(self, surf, rd, b, cam):
        """Phantom's Blackout: the screen goes dark except a headlight round you."""
        k = self.race.brain.dark(self.race.time_ticks)
        if k <= 0:
            return
        W, H = surf.get_size()
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        shade.fill((4, 2, 12, int(235 * k)))
        sx, sy = rd.bike_screen_pos(b, cam)
        for r, a in ((95, 0.75), (70, 0.45), (48, 0.15)):          # soft-edged headlight
            pygame.draw.circle(shade, (4, 2, 12, int(235 * k * a)), (int(sx + 40), int(sy - 10)), r)
        surf.blit(shade, (0, 0))

    def _boss_glow(self):
        """Pulsing outline in the boss's colour, so you always know who to beat."""
        g = self._boss_info["glow"]
        k = 0.65 + 0.35 * (1 + math.sin(self.ticks * 0.15)) / 2
        return (tuple(int(c * k) for c in g), 2)

    def _draw_boss_tag(self, surf, rd, b, cam):
        sx, sy = rd.bike_screen_pos(b, cam)
        x, y = int(sx + C.HEAT_ARC_DX), int(sy + C.HEAT_ARC_DY - C.HEAT_ARC_R - 10)
        g = self._boss_info["glow"]
        pygame.draw.polygon(surf, g, [(x - 6, y - 14), (x - 6, y - 19), (x - 3, y - 16), (x, y - 20),
                                      (x + 3, y - 16), (x + 6, y - 19), (x + 6, y - 14)])     # crown
        hud.text(surf, self._boss_info["name"], (x, y - 6), 15, g, anchor="center")

    def _draw_overheating(self, surf, rd, b, cam):
        """Above your heat gauge while it's in the top zone (faster, but it can blow)."""
        hot_at = C.ONE_SUPER_AT if b.one_button else C.RED_AT
        if b.state != "ride" or b.temp < hot_at:
            return
        sx, sy = rd.bike_screen_pos(b, cam)
        col = C.DANGER if (self.ticks // 6) % 2 == 0 else (255, 220, 160)
        hud.text(surf, "OVERHEATING", (int(sx + C.HEAT_ARC_DX), int(sy + C.HEAT_ARC_DY - C.HEAT_ARC_R - 10)),
                 14, col, anchor="center")

    def _draw_you(self, surf, rd, b, cam):
        """'YOU' tag with a little arrow over the player's helmet at the start."""
        sx, sy = rd.bike_screen_pos(b, cam)
        x, y = int(sx + C.HEAT_ARC_DX), int(sy + C.HEAT_ARC_DY - C.HEAT_ARC_R - 6 - (self.ticks // 8) % 2)
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
            "time": r.clock,
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
        # A respawn can move the bike ahead in one tick (out of a pit, past the
        # hazard): keep the camera where it was and scroll over, instead of cutting.
        if self._prev_bx is not None and abs(b.x - self._prev_bx) > C.CAM_JUMP_PX:
            self._cam_offset -= b.x - self._prev_bx
        self._prev_bx = b.x
        self._cam_offset *= C.CAM_SCROLL_EASE
        if abs(self._cam_offset) < 0.5:
            self._cam_offset = 0.0
        cam = b.x + lead + shake + self._cam_offset
        rd = self.renderer
        rd.draw_backdrop(surf, cam, self.bg_scroll)
        rd.draw_track(surf, self.track, cam, ticks=self.race.time_ticks)
        from ui.art import LIVERIES, bike_paint
        pool = [k for k in LIVERIES if k != bike_paint(self.livery)]
        bikes = [(rb, pool[i % len(pool)], False)
                 for i, rb in enumerate(self.race.rivals)]
        boss_bike = None
        if self.race.boss is not None:
            from ui.art import boss_key, minion_key
            boss_bike = self.race.rivals[self.race.boss_i]
            bikes = [(rb, boss_key(self.race.boss) if rb is boss_bike else minion_key(self.race.boss), False)
                     for rb in self.race.rivals]
        rd.draw_boss_trail(surf, self.race, cam, self.ticks)
        rd.draw_hoops(surf, self.track, cam, self.ticks, front=False)
        bikes.append((b, self.livery, True))
        marked = self.race.countdown > 0 or self.race.time_ticks < self.YOU_TICKS
        # depth by lane; while the start marker shows, the player is drawn on top
        bikes.sort(key=lambda t: (marked and t[2], t[0].lane_pos))
        for bk, liv, me in bikes:
            frame = 0
            if bk.speed > 0 and bk.state == "ride":
                period = max(2, int(10 - bk.speed / 6))
                frame = (bk.ticks // period) % 2
            pal = self.boost_theme if me else (self._boss_info["boost"] if boss_bike else "flame")
            if bk.one_button and bk.state == "ride":
                # everyone's exhaust flame is their heat gauge (rivals included)
                rd.draw_heat_flame(surf, bk, cam, self.ticks, pal)
            elif me and self.boost_k > 0 and bk.state == "ride":
                rd.draw_boost_flame(surf, bk, cam, self.ticks, self.boost_k, self.boost_lvl == 2, pal)
            outline = self._outline(bk) if me else (self._boss_glow() if bk is boss_bike else None)
            rd.draw_bike(surf, bk, cam, liv, frame, me, outline)
            rd.draw_bike_fire(surf, bk, cam, self.ticks)
            if bk is boss_bike and bk.state in ("ride", "done"):
                self._draw_boss_tag(surf, rd, bk, cam)
            if me and (self.race.countdown > 0 or self.race.time_ticks < self.YOU_TICKS) \
                    and bk.state == "ride":
                self._draw_you(surf, rd, bk, cam)
            rd.draw_heat_arc(surf, bk, cam, self.ticks, always=me)
            if me:
                self._draw_overheating(surf, rd, bk, cam)
        rd.draw_hoops(surf, self.track, cam, self.ticks, front=True)
        rd.draw_boss_aura(surf, self.race, cam, self.ticks)
        if self.race.brain is not None:
            self._draw_blackout(surf, rd, b, cam)
        if self.boost_k > 0 and b.state == "ride":
            rd.draw_boost_wind(surf, b, cam, self.ticks, self.boost_k, self.boost_lvl == 2, self.boost_theme)
        rd.particles.draw(surf, cam)
        rd.draw_speed_lines(surf, self.ticks, self.fx_boost * 0.7 + self.fx_super * 0.3,
                            self.fx_super > 0.5)
        self.popups.draw(surf)
        W = self.app.view.width
        extra = list(self.info_lines)
        if self.target:
            extra.append(self.target.describe())
        hud.race_hud(surf, self.race, W, self.ticks, extra, self.best_lap,
)
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
