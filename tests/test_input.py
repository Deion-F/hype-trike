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


def make(mode="one", wheelie="anywhere"):
    if not pygame.display.get_init():
        pygame.display.init(); pygame.display.set_mode((10, 10))
    inp = I.InputManager(View())
    inp.settings = {"mouse_steer": "angle", "throttle_mode": mode, "mouse_wheelie": wheelie}
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
