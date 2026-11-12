"""One race on one track: countdown, laps, rivals, finish. Engine-agnostic."""
import config as C
from bike import Bike, Controls, base_stats


def rival_setup(level, i, n):
    """Stats tweaks + AI settings for rival i of n at difficulty level 0..1.

    Level 0 (first round of a run): clearly slower than the player, no turbo,
    sloppy landings and the odd missed hazard, so they crash now and then.
    Level 1 (final round): close to the player's top speed, the faster ones
    turbo, and they rarely make mistakes. Rivals in one race are spread a
    little around the level so there's a pack, not a wall."""
    lv = max(0.0, min(1.0, level + (i - (n - 1) / 2) * 0.1))
    sloppy = (1.0 - lv) ** 1.5
    stats = dict(max_speed_a=41 + 5 * lv,                      # 41 .. 46
                 accel_interval=C.ACCEL_INTERVAL + 1.0 * (1 - lv))
    turbo = lv >= 0.3 and (i % 2 == 0 or lv >= 0.7)
    # Turbo tops out at the player's turbo speed, so classic-mode players can win too.
    stats["max_speed_b"] = min(C.SPEED_MAX_B, stats["max_speed_a"] + 2)
    ai = dict(turbo=turbo, turbo_temp=22 + i * 2, skill=0.45 + 0.53 * lv,
              blunder=0.14 * sloppy, miss=0.35 * sloppy)
    return stats, ai


class Race:
    def __init__(self, track, stats=None, rivals=0, lane=1, countdown=True,
                 rival_level=0.5, seed=0):
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
        self.rivals = []
        self.rival_ai = []
        self.rival_finish = []
        lanes = [l for l in range(C.LANES) if l != lane]
        for i in range(rivals):
            rs = base_stats("dirt")
            tweaks, ai = rival_setup(rival_level, i, rivals)
            for k, v in tweaks.items():
                setattr(rs, k, v)
            # Everyone lines up level, front wheels on the start line.
            rb = Bike(track, rs, lane=lanes[i % len(lanes)], x=C.START_X)
            self.rivals.append(rb)
            self.rival_ai.append(GhostAI(seed=seed * 31 + i, **ai))
            self.rival_finish.append(None)

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

    def lap_time_now(self):
        return self.time_ticks - self._lap_start

    def position(self):
        """1-based place among the player and rivals."""
        me = self.time_ticks if self.finished else None
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
                self.bike.state = "done"
                ev.append(("finish", self.time_ticks))
        for i, (rb, ai) in enumerate(zip(self.rivals, self.rival_ai)):
            rev = rb.step(ai.controls(rb) if self.rival_finish[i] is None else Controls())
            if rev:
                self.last_rival_events.append((i, rev))
            if self.rival_finish[i] is None and rb.x >= finish_x:
                self.rival_finish[i] = self.time_ticks
                rb.state = "done"
        return ev


def fmt_time(ticks):
    s = ticks / C.FPS
    return f"{int(s // 60)}:{s % 60:05.2f}"
