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
        self.upgrades = list((context or {}).get("upgrades") or ())   # run upgrades, shown as icons
        self.race = Race(track, stats, rivals=rivals, rival_level=rival_level, seed=seed, boss=boss)
        self.track = self.race.track           # a boss chase rides a live track it lays as it goes
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
                self._boss_popup(e, sx, sy)
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
            if k in ("perfect", "land", "rough", "rough_free"):
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
            elif k == "rough_free":
                self.popups.add("ROUGH - ABSORBED!", (140, 230, 255), sx, sy - 40)
                self.renderer.emit_burst(b, (140, 230, 255), 10, 1.5)
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
        ts = (0.0, 0.0, 0.5, 1.0)[b.boost_level] if boosting else 0.0
        self.fx_boost += max(-C.FX_EASE, min(C.FX_EASE, tb - self.fx_boost))
        self.fx_super += max(-C.FX_EASE, min(C.FX_EASE, ts - self.fx_super))
        self.bg_scroll += b.vx * (1 + C.FX_BG_BOOST * self.fx_boost + C.FX_BG_SUPER * self.fx_super)
        if boosting and self.ticks % (2 if b.boost_level >= 2 else 3) == 0:
            self.renderer.emit_boost_sparks(b, b.x, self.boost_theme)
        if self.race.started and self.ticks % 4 == 0:
            for rb in self.race.rivals:             # rivals show their boost too
                if rb.state == "ride" and rb.boost_level > 0 and abs(rb.x - b.x) < self.app.view.width:
                    self.renderer.emit_boost_sparks(rb, b.x)
        if self.ticks % 2 == 0:
            for bk in (b, *self.race.rivals):
                if bk.state != "gone" and abs(bk.x - b.x) < self.app.view.width:
                    self.renderer.emit_fire_embers(bk, b.x)
        if b.state == "ride" and b.boost_level >= 2:
            # hot / overheating: smoke, thicker as the heat nears the explosion
            danger = (b.temp - C.ONE_HOT_AT) / (C.TEMP_OVERHEAT - C.ONE_HOT_AT)
            if self.ticks % (3 if danger < 0.5 else 2) == 0:
                self.renderer.emit_smoke(b, b.x, max(0.0, min(1.0, danger)))
        if self.race.chase is not None:
            self._chase_fx()
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
            if bk.state == "gone":
                continue
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
        "bomb": ("MUD BOMB INCOMING!", (200, 150, 90)), "devil": ("DUST DEVIL!", (236, 206, 140)),
        "shoved": ("SHOVED!", (236, 206, 140)), "blackout": ("LIGHTS OUT...", (190, 140, 255)),
        "pyro": ("PYRO CANNONS!", (255, 170, 60)), "scorched": ("SCORCHED +HEAT", (255, 120, 40)),
        "eruption": ("ERUPTION!", (255, 110, 30)), "lava": ("LAVA! +SPEED +HEAT", (255, 130, 40)),
        "window": ("IT'S BRAKING - STRIKE!", C.GOOD), "minion_bump": ("BLOCKED!", (230, 200, 200)),
        "spotlight": ("SPOTLIGHT ON YOU - RAM IT!", (255, 230, 120)), "lantern": ("LANTERN MOVED", (200, 160, 255)),
        "hatch": ("NEW HATCH LIT - GET IN ITS LANE!", (190, 230, 110)),
        "escaping": ("IT'S GETTING AWAY!", C.DANGER), "escaped": ("IT GOT AWAY...", C.DANGER),
        "wrecked": ("BOSS WRECKED!", C.ACCENT),
    }
    # Bonking it without the weak point: what the boss needs instead.
    BONK_HINTS = {
        "roof": "TOO LOW - JUMP INTO THE GLOWING ZONE!", "hatch_lane": "WRONG LANE - GET IN THE HATCH'S LANE!",
        "hatch_shut": "SHIELD'S DOWN - WAIT FOR IT TO LIFT!",
        "lantern": "WRONG LANE - RAM THE LIT LANTERN!", "spotlight": "LAND A PERFECT FIRST!",
        "core": "TOO COLD - RAM IT OVERHEATING!",
    }
    BOSS_SOUND = {"hit": "explode", "wrecked": "finish", "bonk": "rough", "minion_bump": "bump",
                  "shoved": "rough", "scorched": "rough", "lava": "heatpad", "spotlight": "perfect",
                  "escaping": "overheat", "window": "lap", "minion": None, "lantern": None}

    def _boss_popup(self, e, sx, sy):
        kind = e[1]
        W = self.app.view.width
        if kind == "lap":
            self.popups.add(f"LAP {e[2]}", C.HUD_FG, W // 2, 112, 70)
            self.app.audio.event("lap")
            return
        if kind == "hit":
            hp = e[2]
            self.popups.add("DIRECT HIT!" if hp > 0 else "KNOCKOUT!", C.ACCENT, sx + 40, sy - 56, 70)
            if hp > 0:
                self.popups.add(f"{hp} MORE TO WRECK IT - CHASE IT DOWN!", C.HUD_FG, W // 2, 112, 90)
            ch, r = self.race.chase, self.renderer._rng
            for col, n, sp in (((255, 230, 120), 26, 4.5), ((255, 120, 40), 18, 3.5), ((70, 64, 70), 10, 2.5)):
                for _ in range(n):                                  # sparks off the rig's tail
                    a = r.uniform(0, 2 * math.pi)
                    self.renderer.particles.emit(ch.x, sy - 20 + r.uniform(-12, 12), math.cos(a) * sp - 1,
                                                 math.sin(a) * sp, r.randint(16, 34), col, 2, 0.08)
        elif kind == "bonk":
            self.popups.add(self.BONK_HINTS.get(e[2], "BONK!"), (255, 170, 120), W // 2, 136, 70)
            self.popups.add("IT'S PULLING AWAY - CATCH IT!", C.DANGER, W // 2, 88, 70)
            self.renderer.emit_burst(self.race.bike, (255, 210, 80), 8, 2.5)
        elif kind == "minion":
            pass
        elif kind in ("lantern", "wrecked"):
            pass                                   # the lantern shows it; the result panel says it
        else:
            text, col = self.BOSS_POPUPS.get(kind, (kind.upper(), C.ACCENT))
            if kind in ("shoved", "scorched", "lava", "minion_bump"):
                self.popups.add(text, col, sx, sy - 44, 45)                    # it got you
            else:
                self.popups.add(text, col, W // 2, 88, 70)                      # the boss acts
        snd = self.BOSS_SOUND.get(kind, "beep")
        if snd:
            self.app.audio.event(snd)

    def _chase_fx(self):
        """Smoke and fire off a wrecked rig; sparks where a hit lands."""
        ch = self.race.chase
        rd = self.renderer
        r = rd._rng
        if ch.outcome == "won" and self.ticks % 2 == 0:
            from bosses import RIG_LEN
            x = ch.x + r.uniform(10, RIG_LEN - 10)
            rd.particles.emit(x, C.lane_y(r.uniform(0, 2)) - r.uniform(20, 90), r.uniform(-0.4, 0.4),
                              -r.uniform(0.6, 1.4), r.randint(30, 60),
                              r.choice(((255, 140, 40), (255, 210, 80), (70, 64, 70), (90, 84, 90))),
                              r.choice((2, 3, 4)), -0.01)

    def _draw_rig(self, surf, cam):
        from ui import boss_rig
        ch = self.race.chase
        sx = C.BIKE_SCREEN_X + (ch.x - cam)
        W = self.app.view.width
        if boss_rig.on_screen(sx, W):
            if ch.weak in ("hatch", "lantern") and ch.outcome is None:
                self._draw_lane_guide(surf, ch, sx, cam)
            boss_rig.draw(surf, self.race.boss, sx, self.ticks,
                          boss_rig.Look(ch, self.race.time_ticks, self.race.bike))
        elif sx > W and ch.outcome is None:
            self._draw_rig_pointer(surf, ch, W)

    def _draw_lane_guide(self, surf, ch, sx, cam):
        """Chevrons on the ground leading to the weak point's lane (hatch / lantern),
        green while it's open to a hit."""
        lane = ch.lantern
        t = self.race.time_ticks
        live = ch.weak == "lantern" or ch.shield(t) == "open"
        from ui.boss_rig import HIT
        col = HIT if live else (230, 230, 210)
        tr = self.race.track
        band = pygame.Surface((180, 12), pygame.SRCALPHA)        # the lane lit up behind it
        for i in range(180):
            band.fill((*col, int(110 * i / 180)), (i, 0, 1, 12))
        y0 = C.lane_y(lane) + C.LANE_SPACING // 2 + 2 - tr.ground(ch.x - 10, lane)
        surf.blit(band, (sx - 186, y0 - 9))
        for k in range(8):
            off = 16 + k * 22 - (self.ticks % 22)
            wx = ch.x - off
            x = sx - off
            y = C.lane_y(lane) + C.LANE_SPACING // 2 + 2 - tr.ground(wx, lane)
            pygame.draw.lines(surf, col, False, [(x - 7, y - 7), (x, y - 3), (x - 7, y + 1)], 3)

    def _draw_rig_pointer(self, surf, ch, W):
        """The boss is off screen ahead: an arrow at the right edge with the gap."""
        from bosses import WARN_GAP
        info = self._boss_info
        gap = ch.gap(self.race.bike)
        cols = gap / C.TILE_W
        warn = gap > WARN_GAP
        col = C.DANGER if warn and (self.ticks // 8) % 2 else info["glow"]
        y = 200
        pygame.draw.polygon(surf, (20, 16, 28), [(W - 4, y), (W - 22, y - 14), (W - 22, y + 14)])
        pygame.draw.polygon(surf, col, [(W - 7, y), (W - 20, y - 10), (W - 20, y + 10)])
        hud.text(surf, info["name"], (W - 26, y - 9), 14, col, anchor="topright")
        hud.text(surf, f"{cols:.0f} ahead", (W - 26, y + 5), 14, C.HUD_FG, anchor="topright")

    def _draw_spotlight(self, surf, rd, b, cam):
        """Showstopper: after a PERFECT, a spotlight beam follows you until you ram it."""
        ch = self.race.chase
        if ch is None or ch.weak != "spotlight" or not ch.spotlit(self.race.time_ticks) or b.state != "ride":
            return
        sx, sy = rd.bike_screen_pos(b, cam)
        beam = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        a = 50 + int(20 * math.sin(self.ticks * 0.3))
        pygame.draw.polygon(beam, (255, 240, 170, a), [(sx - 6, 0), (sx + 26, 0), (sx + 30, sy + 4), (sx - 26, sy + 4)])
        surf.blit(beam, (0, 0))

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

    def _draw_overheating(self, surf, rd, b, cam):
        """Above your heat gauge in the top zones: HOT (faster), OVERHEATING (fastest,
        on fire, can blow)."""
        if b.state != "ride":
            return
        if b.one_button:
            zone = b.heat_zone()
        else:
            zone = 3 if b.temp >= C.RED_AT else 0
        if zone < 2:
            return
        sx, sy = rd.bike_screen_pos(b, cam)
        if zone == 2:
            label, col = "HOT", (255, 150, 50)
        else:
            label = "OVERHEATING"
            col = C.DANGER if (self.ticks // 6) % 2 == 0 else (255, 220, 160)
        hud.text(surf, label, (int(sx + C.HEAT_ARC_DX), int(sy + C.HEAT_ARC_DY - C.HEAT_ARC_R - 10)),
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
            "beat_boss": r.beat_boss(),
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
        chase = self.race.chase
        if chase is not None:
            from ui.art import minion_key
            bikes = [(rb, minion_key(self.race.boss), False) for rb in self.race.rivals if rb.state != "gone"]
        rd.draw_boss_trail(surf, self.race, cam, self.ticks)
        rd.draw_hoops(surf, self.track, cam, self.ticks, front=False)
        if chase is not None:
            self._draw_rig(surf, cam)
        if b.drafting:
            leader = self.race.slipstream_of(b)
            if leader is not None:
                rd.draw_slipstream(surf, b, leader, cam, self.ticks)
        bikes.append((b, self.livery, True))
        marked = self.race.countdown > 0 or self.race.time_ticks < self.YOU_TICKS
        # depth by lane; while the start marker shows, the player is drawn on top
        bikes.sort(key=lambda t: (marked and t[2], t[0].lane_pos))
        for bk, liv, me in bikes:
            frame = 0
            if bk.speed > 0 and bk.state == "ride":
                period = max(2, int(10 - bk.speed / 6))
                frame = (bk.ticks // period) % 2
            pal = self.boost_theme if me else (self._boss_info["boost"] if chase else "flame")
            if bk.one_button and bk.state == "ride":
                # everyone's exhaust flame is their heat gauge (rivals included)
                rd.draw_heat_flame(surf, bk, cam, self.ticks, pal)
            elif me and self.boost_k > 0 and bk.state == "ride":
                rd.draw_boost_flame(surf, bk, cam, self.ticks, self.boost_k, self.boost_lvl >= 2, pal)
            outline = self._outline(bk) if me else None
            rd.draw_bike(surf, bk, cam, liv, frame, me, outline)
            rd.draw_bike_fire(surf, bk, cam, self.ticks)
            if me and (self.race.countdown > 0 or self.race.time_ticks < self.YOU_TICKS) \
                    and bk.state == "ride":
                self._draw_you(surf, rd, bk, cam)
            if me:                                 # the heat gauge is the player's alone
                rd.draw_heat_arc(surf, bk, cam, self.ticks, always=True)
                self._draw_overheating(surf, rd, bk, cam)
        rd.draw_hoops(surf, self.track, cam, self.ticks, front=True)
        if chase is not None:
            self._draw_spotlight(surf, rd, b, cam)
            self._draw_blackout(surf, rd, b, cam)
        if self.boost_k > 0 and b.state == "ride":
            rd.draw_boost_wind(surf, b, cam, self.ticks, self.boost_k, self.boost_lvl >= 2, self.boost_theme)
        rd.particles.draw(surf, cam)
        rd.draw_speed_lines(surf, self.ticks, self.fx_boost * 0.7 + self.fx_super * 0.3,
                            self.fx_super > 0.5)
        self.popups.draw(surf)
        W = self.app.view.width
        extra = list(self.info_lines)
        if self.target:
            extra.append(self.target.describe())
        hud.race_hud(surf, self.race, W, self.ticks, extra, self.best_lap,
                     speed=self.app.profile.settings.get("speed_gauge", False))
        if self.upgrades and self.result is None:
            mode = "one" if self.race.bike.one_button else "classic"
            hud.upgrade_icons(surf, self.upgrades, self.race.bike, W - 8, 54, 230, mode, names=self.paused)
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
        if self.race.chase is not None:
            won = r.get("beat_boss")
            hud.text(surf, "BOSS WRECKED!" if won else "IT GOT AWAY", (W // 2, 104), 36,
                     C.ACCENT if won else C.DANGER, anchor="center")
            hud.text(surf, f"TIME  {fmt_time(r['time'])}   HITS  {self.race.chase.hits}/{self.race.chase.hits + self.race.chase.hp}",
                     (W // 2, 138), 22, anchor="center")
            lines = [f"PERFECT LANDINGS  {r['perfect']}   CRASHES  {r['crashes']}"]
            if "target_met" in r:
                lines.append("TARGET MET!" if r["target_met"] else "TARGET MISSED")
            for i, ln in enumerate(lines):
                col = C.HUD_FG if not ln.startswith("TARGET") else (C.GOOD if r["target_met"] else C.DANGER)
                hud.text(surf, ln, (W // 2, 164 + i * 18), 20, col, anchor="center")
            if self.finish_hold <= 0 and (self.ticks // 20) % 2 == 0:
                hud.text(surf, "TAP / ENTER TO CONTINUE", (W // 2, 218), 18, anchor="center")
            return
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
