"""One race on one track: countdown, laps, rivals, finish. Engine-agnostic."""
import config as C
from bike import Bike, Controls, base_stats


class Race:
    def __init__(self, track, stats=None, rivals=0, lane=1, countdown=True,
                 rival_skill=0.85, seed=0):
        from track.validator import GhostAI
        self.track = track
        self.bike = Bike(track, stats or base_stats(), lane=lane)
        self.countdown = C.COUNTDOWN_TICKS if countdown else 0
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
            skill = max(0.3, min(0.98, rival_skill + (i - rivals / 2) * 0.05))
            # Rivals ride a little below the player's top speed so racing is fair.
            rs.max_speed_a = C.SPEED_MAX_A - 2 + i % 3
            rb = Bike(track, rs, lane=lanes[i % len(lanes)],
                      x=C.START_X - 6 * (i + 1))
            self.rivals.append(rb)
            self.rival_ai.append(GhostAI(turbo=i % 2 == 0, turbo_temp=22 + i * 2,
                                         skill=skill, seed=seed * 31 + i))
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
            rb.step(ai.controls(rb) if self.rival_finish[i] is None else Controls())
            if self.rival_finish[i] is None and rb.x >= finish_x:
                self.rival_finish[i] = self.time_ticks
                rb.state = "done"
        return ev


def fmt_time(ticks):
    s = ticks / C.FPS
    return f"{int(s // 60)}:{s % 60:05.2f}"
