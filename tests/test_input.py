"""Mouse steering: the sticky anchor used with the one-button throttle."""
import pygame

import config as C
from bike import Bike
from track.static import static_track
from ui import input as I


class View:
    width, height = 640, 360

    def to_logical(self, pos):
        return pos


def make(mode="one", wheelie="anywhere", lanes="drag"):
    if not pygame.display.get_init():
        pygame.display.init(); pygame.display.set_mode((10, 10))
    inp = I.InputManager(View())
    inp.settings = {"mouse_steer": "angle", "throttle_mode": mode, "mouse_wheelie": wheelie,
                    "mouse_lanes": lanes}
    inp.race_mode = True
    return inp


class Mouse:
    def __init__(self, monkeypatch, inp):
        self.inp, self.down = inp, False
        monkeypatch.setattr(pygame.mouse, "get_pressed", lambda *a: (self.down, False, False))

    def press(self, x, y):
        self.down = True
        self.inp.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y)))

    def release(self, x, y):
        self.down = False
        self.inp.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(x, y)))

    def move(self, x, y):
        self.inp.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=(x, y), rel=(0, 0),
                                           buttons=(self.down, False, False)))


def tick(inp, bike, n=1):
    for _ in range(n):
        c = inp.race_controls(bike)
        inp.consume_edges()
        bike.lane = max(0, min(C.LANES - 1, bike.lane - c.lane_up + c.lane_down))
    return c


def test_sticky_anchor_survives_taps_and_steers_lanes_with_button_up(monkeypatch):
    inp, bike = make(), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200); tick(inp, bike); m.release(300, 200)
    home = inp.anchor
    assert home == (300, 200) and bike.lane == 1
    # Button up: moving down one lane band still changes lane.
    m.move(300, 200 + I.LANE_BAND + 2); tick(inp, bike, 3)
    assert bike.lane == 2 and inp.anchor == home
    # Quick heat taps elsewhere never move home.
    for _ in range(5):
        m.press(300, 200 + I.LANE_BAND + 2); tick(inp, bike, 5); m.release(300, 200 + I.LANE_BAND + 2)
        tick(inp, bike, 5)
    assert inp.anchor == home and bike.lane == 2


def test_sticky_anchor_moves_after_a_still_hold(monkeypatch):
    inp, bike = make(), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200); tick(inp, bike); m.release(300, 200)
    m.move(450, 120); m.press(450, 120)
    tick(inp, bike, I.ANCHOR_HOLD_TICKS - 2)
    assert inp.anchor == (300, 200) and inp.anchor_charge > 0.8
    tick(inp, bike, 3)
    assert inp.anchor == (450, 120) and inp.anchor_charge is None
    # A press that drags (a lean/lane steer) never re-anchors.
    m.release(450, 120); m.press(450, 120); tick(inp, bike, 2)
    m.move(450 - 60, 120); tick(inp, bike, I.ANCHOR_HOLD_TICKS * 2)
    assert inp.anchor == (450, 120) and inp.mouse_lean < 0


def test_classic_mode_still_reanchors_every_press(monkeypatch):
    inp, bike = make("classic"), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200); tick(inp, bike); m.release(300, 200)
    m.press(400, 100); tick(inp, bike)
    assert inp.anchor == (400, 100)
    m.release(400, 100)
    m.move(400, 100 + 3 * I.LANE_BAND); tick(inp, bike, 3)
    assert bike.lane == 1                     # button up: no steering in classic


def test_air_lean_needs_less_mouse_travel_than_ground(monkeypatch):
    inp, bike = make(), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200); tick(inp, bike)
    m.move(300 - 15, 200); tick(inp, bike)
    assert inp.mouse_lean == 0                     # ground: still neutral
    bike.airborne = True
    tick(inp, bike)
    assert inp.mouse_lean == -1 and inp.air_target is not None   # air: already aiming
    m.move(300 - (I.AIR_LEAN_DEAD + 5 * I.AIR_LEAN_STEP + 4), 200); tick(inp, bike)
    assert inp.mouse_lean == -I.AIM_MAX_STEPS      # full nose-up aim in ~65 px


def test_anchor_moves_to_cursor_after_crash_recovery(monkeypatch):
    inp, bike = make(), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200); tick(inp, bike); m.release(300, 200)
    m.move(250, 150)
    bike.lane = 0                     # wherever the rider respawned
    inp.recenter_anchor()
    assert inp.anchor == (250, 150)
    tick(inp, bike, 3)
    assert inp.anchor_lane == 0 and bike.lane == 0 and inp.mouse_lean == 0   # no jump


def test_recenter_does_nothing_without_mouse_steering(monkeypatch):
    inp = make()
    inp.recenter_anchor()
    assert inp.anchor is None


def test_landing_moves_the_anchor_to_the_cursor():
    import main as M
    from ui.menus import TitleScene
    app = M.App()
    sc = TitleScene(app); app.set_scene(sc); sc.practice()
    rs = app.scene
    inp = app.input
    inp.settings = dict(inp.settings, mouse_steer="angle")
    inp.anchor, inp.anchor_lane, inp.mouse_pos = (300, 200), 1, (340, 180)
    inp.touch_seen = False
    for kind, moved in (("bounce", False), ("land", True)):
        inp.anchor = (300, 200)
        rs.race.step = lambda ctl, k=kind: [(k,)]
        rs.update()
        assert (inp.anchor == (340, 180)) == moved, kind


def _ramp_track():
    from track.tiles import make_track
    return make_track("S" + "." * 6 + "L" + "." * 10, laps=1)


def test_ramps_only_wheelie_slides_home_on_flat_ground(monkeypatch):
    inp, bike = make(wheelie="ramps"), Bike(_ramp_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200); tick(inp, bike)
    m.move(300 - 60, 200 + I.LANE_BAND + 2); c = tick(inp, bike, 3)
    assert inp.mouse_lean == 0 and not c.left and not c.right   # no wheelie on the flat
    assert inp.anchor[0] == 300 - 60                             # home slid with the cursor
    assert bike.lane == 2                                        # lanes still work


def test_ramps_only_wheelie_leans_on_the_ramp(monkeypatch):
    inp, bike = make(wheelie="ramps"), Bike(_ramp_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200); tick(inp, bike)
    bike.x = 7 * C.TILE_W + 10                                   # on the ramp column
    tick(inp, bike)
    home = inp.anchor
    m.move(300 - 60, 200); c = tick(inp, bike)
    assert inp.anchor == home and inp.mouse_lean < 0 and c.left  # wheelie off the lip
    bike.x = 6 * C.TILE_W + 40                                   # just before the ramp
    m.move(300 - 60, 200); assert I.InputManager._ground_lean_locked(inp, bike) is False


def test_lane_dots_are_off_by_default_and_toggle_on(monkeypatch):
    from meta.profile import DEFAULTS
    assert DEFAULTS["settings"]["lane_guide"] is False
    inp, bike = make(), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200); tick(inp, bike)
    lane_ys = [int(inp.lane_center_y(l)) for l in range(C.LANES) if l != bike.lane]

    def dots_drawn():
        s = pygame.Surface((640, 360)); s.fill((0, 0, 0))
        inp.draw_mouse_guide(s, (170, 250))
        return any(s.get_at((300, y))[:3] != (0, 0, 0) for y in lane_ys)
    assert not dots_drawn()
    inp.settings["lane_guide"] = True
    assert dots_drawn()


def test_tilt_reports_direction_and_air_aim_strength(monkeypatch):
    inp, bike = make(), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200); c = tick(inp, bike)
    assert inp.tilt(c, bike) == (0, 0, 1)
    m.move(300 - 60, 200); c = tick(inp, bike)                  # ground: lean back, one level
    assert inp.tilt(c, bike) == (-1, 1, 1)
    bike.airborne = True
    m.move(300 + 70, 200); c = tick(inp, bike)                  # air: strong forward aim
    d, lvl, mx = inp.tilt(c, bike)
    assert d == 1 and mx == I.AIM_MAX_STEPS and lvl >= 3
    # keys / touch: a single level from the held direction
    inp2 = make()
    c2 = I.Controls(left=True)
    assert inp2.tilt(c2, bike) == (-1, 1, 1)


def lane_screen_y(lane):
    return C.lane_y(lane) + C.LANE_SPACING / 2


def test_hover_lanes_are_the_default():
    from meta.profile import DEFAULTS
    assert DEFAULTS["settings"]["mouse_lanes"] == "hover"


def test_hover_lanes_follow_the_cursor_without_a_click(monkeypatch):
    for mode in ("one", "classic"):
        inp, bike = make(mode, lanes="hover"), Bike(static_track())
        m = Mouse(monkeypatch, inp)
        assert bike.lane == 1
        tick(inp, bike, 3)
        assert bike.lane == 1                         # cursor hasn't moved this race: no yank
        m.move(300, lane_screen_y(3)); tick(inp, bike, 4)
        assert bike.lane == 3                         # hovering lane 3, no button held
        m.move(300, lane_screen_y(0) - 40); tick(inp, bike, 4)
        assert bike.lane == 0                         # above the track: top lane
        m.move(300, 359); tick(inp, bike, 4)
        assert bike.lane == C.LANES - 1               # below the track: front lane


def test_hover_lanes_have_hysteresis_and_keys_take_over(monkeypatch):
    inp, bike = make(lanes="hover"), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    edge = C.lane_y(2)                                # border between lanes 1 and 2
    m.move(300, edge - 1); tick(inp, bike, 3)
    assert bike.lane == 1
    m.move(300, edge + 1); tick(inp, bike, 3)
    assert bike.lane == 1                             # just past the edge: stays
    m.move(300, edge + I.HOVER_HYST + 2); tick(inp, bike, 3)
    assert bike.lane == 2
    inp.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, mod=0, unicode="", scancode=0))
    tick(inp, bike, 3)
    assert bike.lane == 1                             # the key wins until the mouse moves again


def test_hover_lanes_still_lean_from_home(monkeypatch):
    inp, bike = make(lanes="hover"), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, lane_screen_y(1)); tick(inp, bike)
    m.move(300 - 60, lane_screen_y(1)); c = tick(inp, bike)
    assert c.left and bike.lane == 1


def test_still_cursor_keeps_you_on_the_skyway(monkeypatch):
    """Split bridge: the skyway lanes are drawn higher, so a cursor left where it
    was ends up over the lower deck. A still cursor must not steer you off."""
    from bike import Controls
    from track.tiles import make_track, SPLIT_DRAW, SKY_H
    tr = make_track("S" + "." * 6 + "..oryyyZyne" + "." * 10, laps=1)
    inp, bike = make(lanes="hover"), Bike(tr, lane=0)
    m = Mouse(monkeypatch, inp)
    m.move(C.BIKE_SCREEN_X + 40, lane_screen_y(0)); tick(inp, bike, 2)
    assert bike.lane == 0
    col = tr.terrain.index(SPLIT_DRAW)
    bike.speed = 30
    while bike.x < col * C.TILE_W + 40:
        c = inp.race_controls(bike)
        inp.consume_edges()
        c.a = True
        bike.step(c)
    assert bike.lane_index == 0 and abs(bike.h - SKY_H) < 1          # still up on the skyway
    m.move(C.BIKE_SCREEN_X + 40, lane_screen_y(3)); tick(inp, bike, 4)
    assert bike.lane == 3                                             # moving the cursor still steers


# -- "button" scheme: click pulls up mid-air, the cursor only picks lanes ----------

def make_button(mode="one"):
    inp = make(mode)
    inp.settings = {"mouse_steer": "button", "throttle_mode": mode}
    return inp


def test_button_scheme_is_the_default():
    from meta.profile import DEFAULTS, Profile
    assert DEFAULTS["settings"]["mouse_steer"] == "button"
    old = Profile({"settings": {"mouse_steer": "angle", "settings_v": 2}})
    assert old.settings["mouse_steer"] == "button"          # old default moved over once
    held = Profile({"settings": {"mouse_steer": "hold", "settings_v": 2}})
    assert held.settings["mouse_steer"] == "hold"           # a deliberate pick is kept
    again = Profile({"settings": {"mouse_steer": "angle", "settings_v": 3}})
    assert again.settings["mouse_steer"] == "angle"


def test_button_scheme_ground_throttle_no_anchor_no_lean(monkeypatch):
    inp, bike = make_button(), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200)
    c = tick(inp, bike)
    assert c.a and not c.left and not c.right and inp.anchor is None
    m.move(100, 200); c = tick(inp, bike)                # sideways does nothing
    assert not c.left and not c.right and inp.anchor is None


def test_button_scheme_air_press_leans_forward_and_freezes_heat(monkeypatch):
    inp, bike = make_button(), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.press(300, 200); tick(inp, bike)
    bike.airborne = True                                 # took off with the button held
    c = tick(inp, bike)
    assert c.right and not c.left and c.ramp and c.a     # carries on into a forward lean; heat frozen
    assert inp.tilt(c, bike) == (1, 1, 1)
    m.release(300, 200); c = tick(inp, bike)
    assert not c.right and not c.left and c.ramp and c.a  # released: nose lifts, still frozen
    m.press(300, 200); c = tick(inp, bike)
    assert c.right and c.ramp
    bike.airborne = False; m.release(300, 200); c = tick(inp, bike)
    assert not c.a and not c.ramp                        # landed, button up: coasting


def test_button_scheme_lanes_follow_the_cursor(monkeypatch):
    inp, bike = make_button(), Bike(static_track())
    m = Mouse(monkeypatch, inp)
    m.move(300, lane_screen_y(3)); tick(inp, bike, 6)
    assert bike.lane == 3


def test_button_pitch_winds_up_both_ways():
    from bike import Controls
    from track.tiles import make_track
    def turn(ctl, n):
        """Degrees the nose turns up in n ticks from level."""
        b = Bike(make_track("S" + "." * 40, laps=1))
        b.airborne, b.h, b.angle = True, 400.0, 0.0
        for _ in range(n):
            b._air(ctl, [])
        return b.angle
    free = Controls(ramp=True)
    # released: the nose lifts, a short release a nudge, a long one a big swing
    assert 0 < turn(free, 4) < 3.0
    assert turn(free, 25) > 30.0
    # held: the nose goes down, winding up the same way to near the keys rate
    push = Controls(right=True, ramp=True)
    tap, hold, keys = -turn(push, 4), -turn(push, 20), -turn(Controls(right=True), 20)
    assert 0 < tap < 4 * C.PITCH_RATE * 0.6 and keys * 0.75 < hold < keys


def test_air_lane_lock_freezes_the_mouse_lane_aim(monkeypatch):
    inp, bike = make(lanes="hover"), Bike(static_track())
    inp.settings["air_lane_lock"] = True
    m = Mouse(monkeypatch, inp)
    m.move(300, lane_screen_y(1)); tick(inp, bike, 2)
    assert bike.lane == 1
    bike.airborne = True
    m.move(300, lane_screen_y(3)); c = tick(inp, bike, 3)
    assert not c.lane_down and inp.mouse_lane == 1          # aiming elsewhere mid-air does nothing
    bike.airborne = False
    tick(inp, bike, 3)
    assert bike.lane == 1                                   # ... and nothing jumps lanes on landing
    m.move(302, lane_screen_y(3) + 2); tick(inp, bike, 4)
    assert bike.lane == 3                                   # new movement after landing steers again
