"""Milestone 1: the feel contract (spec §3.1)."""
import config as C
from bike import Bike, Controls, base_stats
from race import Race
from track.static import static_track, material_demo_track
from track.tiles import make_track, apply_layer
from track.validator import validate


def flat(n=200):
    return make_track("S" + "." * n, laps=1)


def run(bike, ctl, ticks):
    evs = []
    for _ in range(ticks):
        evs += bike.step(ctl)
    return evs


def test_speed_starts_at_zero_and_caps_on_A():
    b = Bike(flat())
    assert b.speed == 0
    run(b, Controls(a=True), 600)
    assert b.speed == C.SPEED_MAX_A == 46


def test_A_adds_one_and_B_adds_two_per_step():
    a = Bike(flat()); bb = Bike(flat())
    run(a, Controls(a=True), C.ACCEL_INTERVAL)
    run(bb, Controls(b=True), C.ACCEL_INTERVAL)
    assert a.speed == 1 and bb.speed == 2


def test_turbo_cap_is_higher():
    b = Bike(flat())
    run(b, Controls(b=True), 200)
    assert C.SPEED_MAX_A < b.speed <= C.SPEED_MAX_B


def test_temperature_starts_8_settles_17_on_A():
    b = Bike(flat(400))
    assert b.temp == 8
    run(b, Controls(a=True), 1200)
    assert b.temp == C.TEMP_STABLE_A == 17
    assert b.state == "ride"


def test_turbo_overheats_at_32_and_stalls():
    b = Bike(flat(800))
    for t in range(600):
        if ("overheat",) in b.step(Controls(b=True)):
            break
    assert b.state == "overheat" and b.temp == C.TEMP_OVERHEAT
    assert 4 * C.FPS < t < 7 * C.FPS      # several seconds of turbo from cold
    run(b, Controls(), C.OVERHEAT_TICKS + 5)
    assert b.state == "ride" and b.temp == C.TEMP_START


def test_coolant_resets_temperature():
    t = make_track("S" + "." * 60, laps=1)
    apply_layer(t, 1, "." * 40 + "c")
    b = Bike(t, lane=1)
    hot = Controls(b=True)
    for _ in range(2000):
        ev = b.step(hot)
        if ("coolant",) in ev:
            assert b.temp == C.TEMP_START
            return
        if b.state != "ride":
            b.state = "ride"; b.temp = 20
    raise AssertionError("never reached coolant")


def test_level_landing_keeps_speed_bad_landing_crashes():
    t = make_track("S...L" + "." * 30, laps=1)
    # level-ish landing: ghost steering
    r = validate(t)
    assert r["ok"]
    # nose-down landing: hold right all the way
    b = Bike(t, lane=1)
    evs = []
    for _ in range(600):
        evs += b.step(Controls(a=True, right=b.airborne))
        if b.state == "crash":
            break
    assert any(e[0] == "crash" for e in evs)


def test_crash_costs_time_then_recovers():
    t = make_track("S...L" + "." * 30, laps=1)
    b = Bike(t, lane=1)
    for _ in range(600):
        b.step(Controls(a=True, right=b.airborne))
        if b.state == "crash":
            break
    assert b.speed == 0
    run(b, Controls(), b.stats.crash_ticks + 1)
    assert b.state == "ride"


def test_lanes_clamp_to_four():
    b = Bike(flat(), lane=0)
    for _ in range(10):
        b.step(Controls(lane_down=True))
    run(b, Controls(), 40)
    assert b.lane == 3 and b.lane_pos == 3.0
    b.step(Controls(lane_down=True))
    assert b.lane == 3


def test_mud_slows():
    t = make_track("S" + "." * 80, laps=1)
    apply_layer(t, 1, "." * 20 + "m" * 30)
    b = Bike(t, lane=1)
    while b.x < 30 * C.TILE_W:
        b.step(Controls(a=True))
    assert b.speed <= C.MUD_SPEED


def test_lap_timing_and_finish():
    r = Race(make_track("S" + "." * 20, laps=2), countdown=False)
    while not r.finished and r.time_ticks < 5000:
        r.step(Controls(a=True))
    assert r.finished and len(r.lap_times) == 2


def test_static_tracks_solvable_by_every_vehicle():
    for tr in (static_track(), material_demo_track()):
        for v in ("dirt", "trike", "scrambler", "sprinter"):
            assert validate(tr, base_stats(v))["ok"], (tr.name, v)


def test_determinism():
    a = validate(static_track()); b = validate(static_track())
    assert a == b


# --- one-button throttle (setting "throttle_mode" = "one") -----------------------
def one_button_bike():
    b = Bike(flat(400))
    b.one_button = True
    return b


def test_one_button_starts_cold_and_boosts_within_about_two_seconds():
    b = one_button_bike()
    assert b.temp == 0.0
    run(b, Controls(a=True), 60)
    assert b.boost_level == 0 and 0 < b.speed < C.SPEED_MAX_A
    t = 60
    while b.boost_level == 0:
        run(b, Controls(a=True), 1)
        t += 1
    assert t <= 2.3 * C.FPS                        # first boost comes quickly
    run(b, Controls(a=True), 60)
    assert C.SPEED_MAX_A < b.speed <= C.SPEED_MAX_B
    while b.temp < C.ONE_SUPER_AT + 0.1:
        run(b, Controls(a=True), 1)
    assert b.boost_level == 2 and b.state == "ride"
    run(b, Controls(a=True), 20)
    assert b.speed > C.SPEED_MAX_B                 # super boost beats normal turbo


def test_one_button_speed_follows_heat():
    b = one_button_bike()
    b.temp = C.ONE_BOOST_AT / 2
    run(b, Controls(), 1)
    b.temp = C.ONE_BOOST_AT / 2                    # hold the heat steady by hand
    for _ in range(200):
        b.step(Controls())
        b.temp = C.ONE_BOOST_AT / 2
    assert abs(b.speed - C.SPEED_MAX_A / 2) <= 1   # half heat -> half speed
    # Letting go: heat and speed fall together, both reach zero.
    b.temp = C.ONE_BOOST_AT
    b.speed = C.SPEED_MAX_A
    run(b, Controls(), C.THROTTLE_GRACE_TICKS + 120)
    assert 0 < b.temp < C.ONE_BOOST_AT
    assert abs(b.speed - b.heat_speed()) <= 1.5    # speed tracks heat on the way down
    run(b, Controls(), 400)
    assert b.temp == 0 and b.speed == 0


def test_one_button_explodes_past_red_window_and_recovers_cold():
    b = one_button_bike()
    evs = []
    while b.state == "ride":
        evs += b.step(Controls(a=True))
    assert ("explode",) in [e[:1] for e in evs]
    assert b.state == "crash" and b.crash_reason == "explode" and b.temp == 0
    assert b.crash_total == C.CRASH_TICKS + C.EXPLODE_EXTRA_TICKS   # longer than a crash
    evs = run(b, Controls(), b.crash_total + 2)
    kinds = [e[0] for e in evs]
    assert "bike_drop" in kinds and "recovered" in kinds and b.state == "ride"


def test_one_button_crash_zeroes_heat():
    b = one_button_bike()
    b.temp = 20.0
    b._crash([], "nose")
    assert b.temp == 0.0


def test_classic_mode_unchanged_by_one_button_rules():
    b = Bike(flat(400))
    run(b, Controls(a=True), 600)
    assert abs(b.temp - C.TEMP_STABLE_A) < 1e-6 and b.boost_level == 0
    b.temp = 20.0
    b._crash([], "nose")
    assert b.temp == 20.0


def test_one_button_pads_are_heat_pads_in_three_sizes():
    for ch, bars in (("k", 1), ("c", 2), ("K", 3)):
        t = make_track("S" + "." * 60, laps=1)
        apply_layer(t, 1, "." * 20 + ch)
        b = Bike(t, lane=1)
        b.one_button = True
        b.speed = 30
        for _ in range(2000):
            b.temp = 12.0                                   # hold mid-boost heat
            ev = b.step(Controls())
            if ("heatpad", bars) in ev:
                assert ("coolant",) not in ev
                assert abs(b.temp - (12.0 + bars * C.HEAT_BAR)) < 0.2   # +1/+2/+3 bars
                break
        else:
            raise AssertionError(f"never reached the {ch} pad")


def test_super_boost_is_the_top_three_heat_bars():
    assert abs(C.TEMP_OVERHEAT - C.ONE_SUPER_AT - 3 * C.HEAT_BAR) < 1e-9
    assert abs(C.HEAT_BAR * C.HEAT_BARS - C.TEMP_OVERHEAT) < 1e-9
    b = Bike(flat(20)); b.one_button = True
    b.temp = C.ONE_SUPER_AT - 0.01
    assert b._boost_from(Controls()) == 1
    b.temp = C.ONE_SUPER_AT
    assert b._boost_from(Controls()) == 2


def test_heat_arc_shows_three_red_bars():
    import pygame
    from ui.render import WorldRenderer
    rd = WorldRenderer(640)
    n = rd.HEAT_ARC_SEGS
    red = [i for i in range(n) if (i + 0.5) * C.TEMP_OVERHEAT / n >= C.ONE_SUPER_AT]
    assert red == [n - 3, n - 2, n - 1]


def test_generated_pads_come_in_all_sizes():
    from track.generator import generate
    from track.tiles import PAD_S, PAD_L, COOLANT
    seen = {x for s in range(12) for l in generate(s, 2).track.surface for x in l}
    assert {PAD_S, COOLANT, PAD_L} <= seen


def test_one_button_heat_pad_in_the_red_explodes():
    t = make_track("S" + "." * 60, laps=1)
    apply_layer(t, 1, "." * 20 + "c")
    b = Bike(t, lane=1)
    b.one_button = True
    evs = []
    for _ in range(2000):
        if not any(e[0] == "heatpad" for e in evs):
            b.temp = C.TEMP_OVERHEAT - 2           # deep in the red window until the pad
        evs += b.step(Controls())
        if ("explode",) in evs:
            return
    raise AssertionError("heat pad in the red window should blow the bike up")


def _land_at(one_button, angle, temp=20.0):
    b = Bike(flat(100))
    b.one_button = one_button
    b.temp, b.speed, b.angle = temp, 40, angle
    b.air_ticks = C.MICRO_HOP_TICKS + 10
    ev = []
    b._land(ev)
    return b, ev


def test_one_button_rough_landing_dumps_heat():
    b, ev = _land_at(True, angle=20)               # nose-high: rough, not a crash
    assert ("rough",) in ev and b.temp == 20.0 - C.ONE_ROUGH_HEAT_LOSS
    b, ev = _land_at(True, angle=2)                # clean landing keeps the heat
    assert ("perfect",) in ev and b.temp == 20.0
    b, _ = _land_at(True, angle=20, temp=3.0)
    assert b.temp == 0.0                           # never below cold
    b, _ = _land_at(False, angle=20)               # classic: heat is a cost, untouched
    assert b.temp == 20.0


def test_nose_low_landings_have_a_rough_band_slightly_smaller_than_nose_high():
    assert C.LAND_TOLERANCE < C.LAND_ROUGH_NOSE < C.LAND_ROUGH
    for angle in (-(C.LAND_TOLERANCE + 1), -C.LAND_ROUGH_NOSE):      # nose-low: rough, not a crash
        b, ev = _land_at(True, angle=angle)
        assert ("rough",) in ev and b.state != "crash"
    b, ev = _land_at(True, angle=-(C.LAND_ROUGH_NOSE + 1))           # past the band: crash
    assert b.state == "crash"
    b, ev = _land_at(True, angle=C.LAND_ROUGH_NOSE + 1)              # the same error nose-high is rough
    assert ("rough",) in ev


def test_backdrop_scrolls_left_as_the_rider_moves_forward():
    import pygame
    if not pygame.display.get_init():
        pygame.display.init(); pygame.display.set_mode((10, 10))
    from ui.render import WorldRenderer
    rd = WorldRenderer(640)
    rd.far = pygame.Surface((1280, 360)); rd.far.fill((0, 0, 0))
    rd.mid = pygame.Surface((1280, 360), pygame.SRCALPHA)
    rd.far.fill((255, 0, 0), (300, 0, 4, 360))        # one red marker stripe

    def marker_x(scroll):
        s = pygame.Surface((640, 360))
        rd.draw_backdrop(s, 0, scroll)
        return [x for x in range(640) if s.get_at((x, 20))[:3] == (255, 0, 0)][0]
    assert marker_x(100) < marker_x(0)                   # moved left, not right


def test_heat_arc_draws_in_both_throttle_modes():
    import pygame
    if not pygame.display.get_init():
        pygame.display.init(); pygame.display.set_mode((10, 10))
    from ui.render import WorldRenderer
    rd = WorldRenderer(640)
    for one in (True, False):
        b = Bike(flat(50)); b.one_button = one; b.temp = 30.0
        s = pygame.Surface((640, 360)); s.fill((0, 0, 0))
        rd.draw_heat_arc(s, b, b.x, 0)
        sx, sy = rd.bike_screen_pos(b, b.x)
        top = (int(sx + C.HEAT_ARC_DX), int(sy + C.HEAT_ARC_DY - C.HEAT_ARC_R - 2))
        assert s.get_at(top)[:3] != (0, 0, 0)           # the arc's top segment is drawn


def test_heat_arc_hidden_until_the_boost_zone():
    import pygame
    from ui.render import WorldRenderer
    rd = WorldRenderer(640)
    b = Bike(flat(50)); b.one_button = True
    s = pygame.Surface((640, 360)); s.fill((0, 0, 0))
    b.temp = C.ONE_BOOST_AT - 0.5
    rd.draw_heat_arc(s, b, b.x, 0)
    assert pygame.mask.from_threshold(s, (0, 0, 0), (1, 1, 1, 255)).count() == 640 * 360


def test_one_button_cools_the_moment_you_let_go_classic_keeps_grace():
    b = Bike(flat(200)); b.one_button = True
    b.temp = 20.0
    b.step(Controls(a=True)); hot = b.temp
    b.step(Controls())
    assert b.temp < hot and not b.in_grace          # no grace: cooling starts at once
    c = Bike(flat(200))
    c.temp = 20.0
    c.step(Controls(a=True)); held = c.temp
    c.step(Controls())
    assert c.in_grace and c.temp == held            # classic: grace still freezes heat


def test_rivals_line_up_level_with_the_player():
    from race import Race
    r = Race(flat(50), rivals=3)
    assert all(rb.x == r.bike.x == C.START_X for rb in r.rivals)
    assert len({rb.lane for rb in r.rivals} | {r.bike.lane}) == 4


def test_tilt_arrow_draws_ahead_of_the_nose_and_grows_with_strength():
    import pygame
    if not pygame.display.get_init():
        pygame.display.init(); pygame.display.set_mode((10, 10))
    from ui.render import WorldRenderer
    rd = WorldRenderer(640)
    b = Bike(flat(50))

    def lit(direction, level, mx):
        s = pygame.Surface((640, 360)); s.fill((0, 0, 0))
        rd.draw_tilt_arrow(s, b, b.x, direction, level, mx)
        sx, _ = rd.bike_screen_pos(b, b.x)
        n = pygame.mask.from_threshold(s, (0, 0, 0), (1, 1, 1, 255)).count()
        ahead = pygame.mask.from_threshold(s.subsurface((int(sx + 20 * C.SPRITE_SCALE), 0, 40, 360)), (0, 0, 0),
                                           (1, 1, 1, 255)).count()
        return 640 * 360 - n, 40 * 360 - ahead
    assert lit(0, 0, 1)[0] == 0                       # no lean, nothing drawn
    weak, weak_ahead = lit(-1, 1, 6)
    strong, _ = lit(-1, 6, 6)
    assert weak_ahead == weak > 0 and strong > weak   # all ahead of the bike; bigger when stronger


# --- water puddles, the Volcano (lava) level, perfect-landing alignment --------------------
from track.tiles import WATER


def _puddle_bike(theme, one=True, temp=20.0, speed=40):
    t = flat(30)
    t.surface[1][5] = WATER
    t.theme = theme
    b = Bike(t, lane=1); b.one_button = one
    b.x = 5 * C.TILE_W - 2; b.temp = temp; b.speed = speed
    return b


def test_water_puddle_cools_and_slows_in_both_modes():
    for one in (True, False):
        b = _puddle_bike("valley", one)
        ev = []
        for _ in range(3):
            ev += b.step(Controls(a=True))
        assert ("splash",) in ev
        assert b.temp < 20.0 - C.WATER_COOL + 1 and b.speed < 40 * C.WATER_SPEED_KEEP + 3


def test_lava_pit_kicks_speed_and_adds_lots_of_heat():
    b = _puddle_bike("lava", one=True, temp=12.0, speed=40)
    ev = []
    for _ in range(3):
        ev += b.step(Controls(a=True))
    assert ("lava",) in ev and b.temp >= 12.0 + C.LAVA_PIT_HEAT and b.speed > 44
    hot = _puddle_bike("lava", one=True, temp=C.TEMP_OVERHEAT - 3)
    for _ in range(3):
        hot.step(Controls(a=True))
    assert hot.state == "crash"                        # a pit in the red blows you up


def test_volcano_heats_faster_and_cools_slower():
    def heat_after(theme, ctl, temp, n=120):
        t = flat(100); t.theme = theme
        b = Bike(t); b.one_button = True; b.temp = temp
        for _ in range(n):
            b.step(ctl)
        return b.temp
    assert heat_after("lava", Controls(a=True), 10.0) > heat_after("valley", Controls(a=True), 10.0)
    assert heat_after("lava", Controls(), 20.0) > heat_after("valley", Controls(), 20.0)


def test_perfect_aligned_tracks_the_landing_slope():
    b = Bike(flat(60)); b.speed = 40
    b.airborne = True; b.air_ticks = 20; b.h = 60; b.vy = 1.0
    t, _ = b.predicted_landing()
    b.angle = 0.0
    assert not b.perfect_aligned()                     # level now, but the nose drops before touchdown
    b.angle = b.stats.nose_drop * t
    assert b.perfect_aligned()                         # lands level if you let go now
    b.angle = 25.0
    assert not b.perfect_aligned()
    b.airborne = False
    assert not b.perfect_aligned()


def test_run_final_heat_is_the_volcano():
    from run.manager import RunState, RUN_HEATS
    r = RunState(seed=3)
    r.heat_i = RUN_HEATS - 1
    assert r.prepare_heat().track.theme == C.LAVA_THEME
    r.heat_i = 0
    assert r.prepare_heat().track.theme == "valley"


def test_outline_pads_the_sprite_evenly():
    import pygame
    if not pygame.display.get_init():
        pygame.display.init(); pygame.display.set_mode((10, 10))
    from ui import art
    img = art.draw_dirt_bike(art.LIVERIES["flame"], 0)
    out = art.outlined(img, (255, 205, 50), 2)
    assert out.get_size() == (img.get_width() + 4, img.get_height() + 4)
    assert pygame.mask.from_surface(out).count() > pygame.mask.from_surface(img).count()


def test_heat_never_rises_in_the_air():
    for one in (True, False):
        for ctl in (Controls(a=True), Controls(a=True, b=True)):
            b = Bike(flat(100))
            b.one_button = one
            b.temp, b.speed = 12.0, 40
            b.airborne, b.air_ticks, b.h, b.vy = True, 1, b.track.ground(b.x) + 200, 4.0
            for _ in range(30):
                b.step(ctl)
                assert b.airborne and b.temp <= 12.0
    b = Bike(flat(100))                                  # letting go in the air still cools
    b.one_button = True
    b.temp, b.speed = 12.0, 40
    b.airborne, b.air_ticks, b.h, b.vy = True, 1, b.track.ground(b.x) + 200, 4.0
    for _ in range(10):
        b.step(Controls())
    assert b.temp < 12.0


def _crash_at(track, x, lane=1):
    """Crash a bike at x and run it through recovery; returns it."""
    b = Bike(track, lane=lane, x=x)
    b._crash([], "nose")
    run(b, Controls(), b.crash_total + 1)
    assert b.state == "ride"
    return b


def test_respawn_skips_a_pit_just_ahead():
    t = make_track("S" + "." * 5 + "sgg" + "." * 20, laps=1)
    b = _crash_at(t, 4 * C.TILE_W + 40)          # two tiles short of the ramp
    assert b.x >= 9 * C.TILE_W                   # past the ramp and the pit


def test_respawn_skips_a_barrier_just_ahead():
    t = make_track("S" + "." * 30, laps=1)
    apply_layer(t, 1, "." * 7 + "d")
    b = _crash_at(t, 5 * C.TILE_W + 40)
    assert int(b.x // C.TILE_W) == 8


def test_respawn_stays_put_with_a_clear_run_up():
    t = make_track("S" + "." * 12 + "g" + "." * 20, laps=1)
    b = _crash_at(t, 4 * C.TILE_W + 10)
    assert b.x < 7 * C.TILE_W                    # only the tumble moved it



def test_perfect_grace_forgives_a_last_moment_twitch():
    for twitch, perfect in ((0.0, True), (C.LAND_PERFECT + 3, True), (C.LAND_TOLERANCE + 1, False)):
        b = Bike(flat(60)); b.speed = 40
        b.airborne = True; b.air_ticks = 30; b.h = b.track.ground(b.x) + 6; b.vy = -1.0; b.angle = 0.0
        b.step(Controls())                             # lined up just above the ground ...
        b.angle = -twitch                              # ... then a last-moment twitch
        ev = []
        for _ in range(10):
            ev += b.step(Controls())
            if not b.airborne:
                break
        assert (("perfect",) in ev) == perfect, twitch


def test_heat_does_not_rise_up_a_ramp():
    from track.tiles import make_track
    tr = make_track("S..L......", laps=1)
    b = Bike(tr); b.one_button = True
    b.x = 3 * C.TILE_W + 20; b.h = tr.ground(b.x); b.speed = 30; b.temp = 15.0
    assert b.climbing()
    b.step(Controls(a=True))
    assert b.temp <= 15.0
    b.x = 6 * C.TILE_W; b.h = tr.ground(b.x); b.airborne = False
    b.step(Controls(a=True))
    assert b.temp > 15.0                               # on the flat it heats again


def test_lap_clock_stops_at_the_finish():
    from race import Race
    from track.tiles import make_track
    race = Race(make_track("S" + "." * 8, laps=1), rivals=1, rival_level=0.0, countdown=False)
    race.bike.speed = 46
    while not race.finished:
        race.bike.speed = 46
        race.step(Controls(a=True))
    stop = race.clock
    for _ in range(120):
        race.step(Controls())
    assert race.clock == stop and race.time_ticks > stop
    assert race.position() == 1                         # rivals finishing later stay behind
