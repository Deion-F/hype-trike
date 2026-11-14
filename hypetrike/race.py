"""One race on one track: countdown, laps, rivals, finish. Engine-agnostic.

Rivals ride the player's one-button heat model (heat is speed: below the boost
band, the boost band, the red window), driven by RivalPilot, so their speed is
always visible in their heat flame and heat arc. Each rival also carries a
Starter Kit (meta/kit.py) spread at random from its difficulty's budget.
"""
import random

import config as C
from bike import Bike, Controls, base_stats

# Starter Kit levels a rival gets at difficulty level 1 (scaled down linearly
# below that), spread at random over the kit items each race. The player can
# own up to 5 levels x 8 items; rivals never get Sponsor Deal (no use to them).
RIVAL_KIT_MAX = 20
RIVAL_KIT_ITEMS = ("gyro", "soft_shocks", "cool_head", "radiator", "track_boots", "quick_steer",
                   "all_terrain")


def rival_kit(level, rng):
    """{kit item: level} for one rival: round(RIVAL_KIT_MAX * level) levels,
    each dropped on a random item that isn't maxed yet."""
    from meta.kit import MAX_LEVEL
    levels = {k: 0 for k in RIVAL_KIT_ITEMS}
    for _ in range(int(round(RIVAL_KIT_MAX * max(0.0, min(1.0, level))))):
        open_items = [k for k, v in levels.items() if v < MAX_LEVEL]
        if not open_items:
            break
        levels[rng.choice(open_items)] += 1
    return {k: v for k, v in levels.items() if v}


def rival_setup(level, i, n):
    """Stats tweaks + AI settings + heat plan for rival i of n at difficulty 0..1.

    Level 0 (first round of a run): clearly slower than the player, never
    boosts, sloppy landings and the odd missed hazard, so they crash now and
    then. Level 1 (final round): every rival rides the boost band and rarely
    makes mistakes. Rivals in one race are spread a little around the level so
    there's a pack, not a wall. Returns (stats, ai, heat) where heat is
    (keep, band): the pilot holds the throttle up to `keep` heat and lets go
    until it drops `band` below."""
    lv = max(0.0, min(1.0, level + (i - (n - 1) / 2) * 0.1))
    sloppy = (1.0 - lv) ** 1.5
    stats = dict(max_speed_a=41 + 5 * lv,                      # 41 .. 46 (top speed under boost)
                 accel_interval=C.ACCEL_INTERVAL + 1.0 * (1 - lv))
    boosts = lv >= 0.3 and (i % 2 == 0 or lv >= 0.7)
    # Boost tops out at the player's boost speed (the player's red window is faster).
    stats["max_speed_b"] = min(C.SPEED_MAX_B, stats["max_speed_a"] + 2)
    if boosts:
        heat = (C.ONE_BOOST_AT + 4 + 9 * lv, 2.0)                # in the boost band, never the red
    else:
        heat = (C.ONE_BOOST_AT - 0.2, 0.5)                       # just under the boost band
    ai = dict(turbo=boosts, turbo_temp=heat[0], skill=0.45 + 0.53 * lv,
              blunder=0.14 * sloppy, miss=0.35 * sloppy)
    return stats, ai, heat


class RivalPilot:
    """One-button throttle for a rival: hold to climb to `keep` heat, let go
    until it drops `band` below. Lean, lanes and coasting (drawbridges) come
    from the GhostAI underneath."""

    def __init__(self, ai, keep, band):
        self.ai, self.keep, self.band, self._hold = ai, keep, band, True

    def controls(self, bike):
        c = self.ai.controls(bike)
        wants = c.a or c.b                     # False: the AI is coasting on purpose
        if bike.temp >= self.keep:
            self._hold = False
        elif bike.temp < self.keep - self.band:
            self._hold = True
        c.a, c.b = wants and self._hold, False
        return c


class Race:
    def __init__(self, track, stats=None, rivals=0, lane=1, countdown=True,
                 rival_level=0.5, seed=0, boss=None):
        from track.validator import GhostAI
        self.track = track
        self.bike = Bike(track, stats or base_stats(), lane=lane)
        self.countdown = C.COUNTDOWN_TICKS if countdown else 0
        self.countdown_start = self.countdown
        self.rival_level = rival_level
        self.seed = seed
        self.last_rival_events = []      # [(rival index, events)] from the latest step
        self.time_ticks = 0
        self.lap_times = []
        self._lap_start = 0
        self.finished = False
        self.finish_ticks = None         # the player's race time, frozen at the line
        self.rivals = []
        self.rival_ai = []
        self.rival_finish = []
        self.rival_kits = []             # each rival's Starter Kit levels this race
        lanes = [l for l in range(C.LANES) if l != lane]
        from meta.kit import apply_kit
        for i in range(rivals):
            rs = base_stats("dirt")
            tweaks, ai, (keep, band) = rival_setup(rival_level, i, rivals)
            for k, v in tweaks.items():
                setattr(rs, k, v)
            kit = rival_kit(rival_level, random.Random(seed * 7919 + i * 104729 + 17))
            rs = apply_kit(rs, kit)
            # Everyone lines up level, front wheels on the start line.
            rb = Bike(track, rs, lane=lanes[i % len(lanes)], x=C.START_X)
            rb.one_button = True
            self.rivals.append(rb)
            self.rival_kits.append(kit)
            self.rival_ai.append(RivalPilot(GhostAI(seed=seed * 31 + i, **ai), keep, band))
            self.rival_finish.append(None)
        # Boss race: the rival with the best setup becomes the biome's boss.
        from bosses import BOSSES, BossTrail, BossBrain, boss_score, MINION_LIFE, MINION_K
        self.boss = boss if boss in BOSSES and self.rivals else None
        self.boss_i = None
        self.trails = []                 # boss + minion trails (bosses.BossTrail)
        self.brain = None                # the boss's powers (bosses.BossBrain)
        if self.boss:
            info = BOSSES[self.boss]
            self.boss_i = max(range(len(self.rivals)),
                              key=lambda i: boss_score(self.rivals[i].stats, self.rival_kits[i]))
            rb = self.rivals[self.boss_i]
            rb.stats.vehicle = info["vehicle"]                  # the boss's themed ride (looks)
            rb.stats.max_speed_b = max(rb.stats.max_speed_b, C.SPEED_MAX_B)
            pilot = self.rival_ai[self.boss_i]
            pilot.keep, pilot.band = C.ONE_BOOST_AT + 4 + 9 * max(rival_level, 0.5), 2.0   # always boosting
            self.brain = BossBrain(self.boss, seed)
            # everyone else rides as the boss's minions: a weaker, shorter trail
            for i in range(len(self.rivals)):
                if i == self.boss_i:
                    self.trails.append(BossTrail(info["trail"], i))
                else:
                    self.trails.append(BossTrail(info["trail"], i, MINION_LIFE, MINION_K))

    @property
    def started(self):
        return self.countdown <= 0

    @property
    def laps_done(self):
        return len(self.lap_times)

    @property
    def progress(self):
        """0..1 progress through the whole race."""
        total = self.track.length * self.track.laps
        return max(0.0, min(1.0, (self.bike.x - C.START_X) / total))

    @property
    def clock(self):
        """Race time to show: stops when the player crosses the line."""
        return self.finish_ticks if self.finished else self.time_ticks

    def lap_time_now(self):
        return self.clock - self._lap_start

    def position(self):
        """1-based place among the player and rivals."""
        me = self.finish_ticks if self.finished else None
        place = 1
        for rb, fin in zip(self.rivals, self.rival_finish):
            if fin is not None:
                if me is None or fin < me:
                    place += 1
            elif me is None and rb.x > self.bike.x:
                place += 1
        return place

    def step(self, ctl: Controls):
        self.last_rival_events = []
        if self.countdown > 0:
            self.countdown -= 1
            return [("go",)] if self.countdown == 0 else []
        self.time_ticks += 1
        if self.bike.stats.draft_bonus:
            # Slipstream: a rival less than two sections ahead in your lane
            b = self.bike
            self.bike.drafting = any(rb.lane_index == b.lane_index and 0 < rb.x - b.x < 2 * C.TILE_W
                                     and rb.state == "ride" for rb in self.rivals)
        boss_bike = self.rivals[self.boss_i] if self.boss else None
        if self.brain is not None:
            self.brain.player_mods(self, boss_bike)
            hit = [tr for tr in self.trails if tr.hits(self.bike)]
            if self.brain.mud_under(self.bike, self.time_ticks):
                self.bike.trail, self.bike.trail_k = "mud", 1.0      # a Mud Bomb splat
            elif hit:
                strongest = max(hit, key=lambda tr: tr.k)
                self.bike.trail, self.bike.trail_k = strongest.kind, strongest.k
            else:
                self.bike.trail, self.bike.trail_k = None, 1.0
        ev = self.bike.step(ctl if not self.finished else Controls())
        finish_x = C.START_X + self.track.length * self.track.laps
        if not self.finished:
            lap_idx = int((self.bike.x - C.START_X) // self.track.length)
            while lap_idx > self.laps_done and self.laps_done < self.track.laps:
                self.lap_times.append(self.time_ticks - self._lap_start)
                self._lap_start = self.time_ticks
                ev.append(("lap", self.lap_times[-1]))
            if self.bike.x >= finish_x:
                self.finished = True
                self.finish_ticks = self.time_ticks
                self.bike.state = "done"
                ev.append(("finish", self.time_ticks))
        for i, (rb, ai) in enumerate(zip(self.rivals, self.rival_ai)):
            rev = rb.step(ai.controls(rb) if self.rival_finish[i] is None else Controls())
            if rev:
                self.last_rival_events.append((i, rev))
            if self.rival_finish[i] is None and rb.x >= finish_x:
                self.rival_finish[i] = self.time_ticks
                rb.state = "done"
        if self.brain is not None:
            for tr in self.trails:
                tr.update(self.rivals[tr.owner], self.time_ticks)
            boss_ev = next((e for i, e in self.last_rival_events if i == self.boss_i), [])
            ev.extend(self.brain.update(self, boss_bike, ev, boss_ev))
        return ev


def fmt_time(ticks):
    s = ticks / C.FPS
    return f"{int(s // 60)}:{s % 60:05.2f}"
