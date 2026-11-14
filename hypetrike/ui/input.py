"""Unified input: keyboard + multi-touch + mouse, in logical coordinates.

Race controls (decision Q2): on-screen buttons for throttle (A), turbo (B),
lean back / lean forward, plus vertical swipes anywhere else for lane changes.
Menus and the editor consume generic pointer events (down / move / up / tap).

Desktop mouse, "button" scheme (setting "mouse_steer" = "button", the default):
the button is throttle on the ground and pulls the nose up in the air; released
mid-air the nose falls, faster the longer it's free. The cursor only picks
lanes (hover, below); left/right does nothing, so there is no home point and
nothing to drift. See button_air.py.

Desktop mouse steering (setting "mouse_steer" = "angle" / "hold"): pressing a mouse button drops an
anchor (the "home" point) where the cursor is, pinned to the rider's current lane.
While throttle or turbo is held, the cursor's offset from home steers; the anchor
never moves on its own, so returning to home always means neutral and the
starting lane. With both buttons up the cursor moves freely, and the next press
sets a new home there.
  Lanes: each LANE_BAND px above/below home = one lane (clamped to the track).
  Lean:  within LEAN_DEAD px of home = neutral. Behind = back, ahead = forward.
    "angle" (default): on the ground, behind = wheelie. In the air, leaving
        neutral captures the current nose angle; each AIR_LEAN_STEP-px step out
        from home then aims AIM_STEP_DEG further up (behind) or down (ahead) from
        it. Air zones are tighter than ground ones (AIR_LEAN_DEAD), so small,
        quick hand movements steer the nose.
        The rider rotates there and holds, so it turns the way the hand moves and
        can't over-rotate. Back at home the nose drifts down, as with no keys.
    "hold": any offset past LEAN_DEAD holds the lean (rate control, like keys).
Zones and lanes switch in discrete steps with hysteresis. Left button =
throttle, right button = turbo. Whichever device was used last (mouse movement
vs. lean/lane keys) owns steering.

Ground wheelies (setting "mouse_wheelie"): "ramps" (default) means that on
flat ground, side-to-side movement just slides home along with the cursor (no
lean; up/down still picks lanes). On a ramp, or just before one
(RAMP_LEAN_LOOKAHEAD), leaning switches on, measured from where the cursor was,
so you can pull a wheelie off the lip; in the air it works as above.
"anywhere": the cursor leans on the ground at all times (the old behaviour).

Lane picking (setting "mouse_lanes"): "hover" (default) puts the rider in
whichever lane the cursor is over, so the bike follows the cursor up and down,
with or without a button held and before any click. It wakes once the cursor
moves in a race, so a cursor left at the top of the screen after a menu click
doesn't yank the rider at GO. "drag" is the older scheme above: lanes count
from home in LANE_BAND steps.

One-button throttle ("sticky anchor"): the anchor stays put when the button is
released, and the cursor keeps steering lanes and lean with the button up, so
tapping to manage heat never moves home. A press held still for
ANCHOR_HOLD_TICKS away from home moves home to that spot (a ring fills while it
charges). The first press of a race still anchors at once.
"""
import math

import pygame

import config as C
from bike import Controls
from button_air import ButtonAir
from track.tiles import RAMPS

SWIPE_STEP = 26          # logical px of vertical drag per lane change
TAP_SLOP = 12            # max movement for a tap

LEAN_DEAD = 24           # px either side of home that counts as "no lean"
LEAN_STEP = 22           # px per extra lean step past the neutral zone (angle mode)
LEAN_HYST = 6            # px a cursor must be inside a new zone before it switches
AIR_LEAN_DEAD = 10       # angle mode, mid-air: tighter neutral zone ...
AIR_LEAN_STEP = 11       # ... and px per aim step (6 steps = 77 px for 72 deg; was 10 px, 1.2 deg/px)
AIR_LEAN_HYST = 4
RAMP_LEAN_LOOKAHEAD = 0.6  # tiles ahead of the rider where a ramp turns ground lean on
AIM_MAX_STEPS = 6        # angle mode: furthest step counted (6 x 12 deg = 72 deg)
AIM_STEP_DEG = 12.0      # angle mode: nose turn per lean step, mid-air
LANE_BAND = 26           # px of cursor travel per lane (lanes are drawn 20 px apart)
LANE_HYST = 6            # extra px past a band edge before switching lane
HOVER_HYST = 3           # hover lanes: px past the edge between lanes before switching
ANCHOR_HOLD_TICKS = 30  # sticky anchor: hold still this long to move home (0.5 s)
ANCHOR_MIN_DIST = 12     # sticky anchor: presses closer than this to home never re-anchor
STEER_KEYS = (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT,
              pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d)


class Button:
    def __init__(self, name, cx, cy, r, label):
        self.name, self.cx, self.cy, self.r, self.label = name, cx, cy, r, label

    def hit(self, x, y, pad=8):
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= (self.r + pad) ** 2


class Pointer:
    __slots__ = ("pid", "x", "y", "sx", "sy", "button", "swipe_y", "moved")

    def __init__(self, pid, x, y):
        self.pid, self.x, self.y, self.sx, self.sy = pid, x, y, x, y
        self.button = None
        self.swipe_y = y
        self.moved = False


class InputManager:
    def __init__(self, view):
        self.view = view               # object with .width/.height and to_logical()
        self.pointers = {}
        self.touch_seen = False
        self.force_touch_ui = False
        self.pointer_events = []       # (kind, pid, x, y) for menus/editor this frame
        self.keys_down = []            # pygame key codes pressed this frame
        self.text_in = []
        self._edge = {"lane_up": False, "lane_down": False}
        self.race_mode = False
        self.settings = {}
        self.mouse_active = False      # mouse moved more recently than the steer keys
        self.mouse_pos = (0.0, 0.0)    # logical coords
        self.mouse_lean = 0            # -1 back, 0 neutral, +1 forward (quantised)
        self.air_base = None           # nose angle when the cursor left neutral mid-air
        self.air_target = None         # aimed nose angle, None = untouched (drift)
        self.mouse_lane = None         # lane the cursor is pointing at
        self.mouse_driving = False     # steering AND throttle/turbo held this tick
        self.anchor = None             # (x, y) where the steering click landed
        self.anchor_lane = None        # rider's lane when the anchor was dropped
        self.lean_locked = False       # flat ground, ramps-only wheelies: no lean this tick
        self._mouse_held = set()       # mouse buttons (1, 3) currently down
        self._press = None             # sticky anchor: (x, y) of a press that may re-anchor
        self._press_ticks = 0
        self._hover_armed = False      # hover lanes: cursor has moved since the race began
        self.cam_lead = 0.0            # camera x minus rider x (set by the race scene)
        self.button_air = ButtonAir()  # "button" scheme: throttle on the ground, pull-up in the air
        self.layout(view.width)

    # -- layout --------------------------------------------------------------
    def layout(self, width):
        h = self.view.height
        st = getattr(self, "settings", None) or {}
        k = float(st.get("button_scale", 1.0))
        swap = st.get("swap_sides", False)
        lane_btns = st.get("lane_mode", "swipe") in ("buttons", "both")
        one = st.get("throttle_mode") == "one"
        L = lambda x: width - x if swap else x      # noqa: E731
        R = lambda x: x if swap else width - x      # noqa: E731
        self.buttons = [
            Button("left", L(48 * k), h - 54 * k, 28 * k, "<"),
            Button("right", L(118 * k), h - 54 * k, 28 * k, ">"),
            Button("a", R(54 * k), h - 50 * k, 32 * k, "A"),
        ]
        if not one:          # one-button throttle: boost comes from heat, no B button
            self.buttons.insert(2, Button("b", R(128 * k), h - 62 * k, 28 * k, "B"))
        if lane_btns:
            self.buttons += [
                Button("up", L(83 * k), h - 160 * k, 22 * k, "^"),
                Button("down", L(83 * k), h - 112 * k, 22 * k, "v"),
            ]
        self.buttons.append(Button("pause", width - 20, 64, 14, "II"))

    @property
    def show_touch(self):
        mode = self.settings.get("touch_ui", "auto")
        if mode == "on":
            return True
        if mode == "off":
            return False
        return self.touch_seen or self.force_touch_ui

    # -- event intake -------------------------------------------------------------
    def begin_frame(self):
        self.pointer_events = []
        self.keys_down = []
        self.text_in = []

    def handle(self, e):
        if e.type == pygame.TEXTINPUT:
            self.text_in.append(e.text)
            return
        if e.type == pygame.KEYDOWN:
            self.keys_down.append(e.key)
            if e.key in STEER_KEYS:
                self.mouse_active = False
            if e.key in (pygame.K_UP, pygame.K_w):
                self._edge["lane_up"] = True
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                self._edge["lane_down"] = True
        elif e.type == pygame.FINGERDOWN:
            self.touch_seen = True
            x, y = e.x * self.view.width, e.y * self.view.height
            self._down(("f", e.finger_id), x, y)
        elif e.type == pygame.FINGERMOTION:
            self._move(("f", e.finger_id), e.x * self.view.width, e.y * self.view.height)
        elif e.type == pygame.FINGERUP:
            self._up(("f", e.finger_id), e.x * self.view.width, e.y * self.view.height)
        elif e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            if getattr(e, "touch", False) or self.touch_seen:
                return  # synthetic mouse from touch; fingers already handled
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and e.button in (1, 3):
                x, y = self.view.to_logical(e.pos)
                if e.type == pygame.MOUSEBUTTONDOWN:
                    if self.button_mode:
                        self.mouse_active = True
                        if self.race_mode:
                            self._hover_armed = True
                    elif not self._mouse_held:
                        if self.sticky_anchor and self.anchor is not None:
                            self._press, self._press_ticks = (x, y), 0   # maybe re-anchor
                        else:
                            self.set_anchor(x, y)     # first button down: re-anchor here
                    self._mouse_held.add(e.button)
                else:
                    self._mouse_held.discard(e.button)
                    if not self._mouse_held:
                        self._press = None
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and e.button == 3:
                x, y = self.view.to_logical(e.pos)
                self.mouse_pos = (x, y)
                self.pointer_events.append(("rdown" if e.type == pygame.MOUSEBUTTONDOWN else "rup", "r", x, y))
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and e.button != 1:
                return
            x, y = self.view.to_logical(e.pos)
            self.mouse_pos = (x, y)
            if e.type == pygame.MOUSEBUTTONDOWN:
                self._down("m", x, y)
            elif e.type == pygame.MOUSEMOTION:
                self.mouse_active = True
                if self.race_mode:
                    self._hover_armed = True
                if "m" in self.pointers:
                    self._move("m", x, y)
                else:
                    self.pointer_events.append(("hover", "m", x, y))
                if e.buttons[2]:
                    self.pointer_events.append(("rmove", "r", x, y))
            else:
                self._up("m", x, y)
        elif e.type == pygame.MOUSEWHEEL:
            self.pointer_events.append(("wheel", "m", e.y, e.x))

    def _down(self, pid, x, y):
        p = Pointer(pid, x, y)
        if self.race_mode and self.show_touch:
            for b in self.buttons:
                if b.hit(x, y):
                    p.button = b.name
                    if b.name == "up":
                        self._edge["lane_up"] = True
                    elif b.name == "down":
                        self._edge["lane_down"] = True
                    break
        self.pointers[pid] = p
        self.pointer_events.append(("down", pid, x, y))

    def _move(self, pid, x, y):
        p = self.pointers.get(pid)
        if not p:
            return
        p.x, p.y = x, y
        if abs(x - p.sx) > TAP_SLOP or abs(y - p.sy) > TAP_SLOP:
            p.moved = True
        swipe_ok = self.settings.get("lane_mode", "swipe") in ("swipe", "both")
        if pid == "m" and self.mouse_enabled:
            swipe_ok = False      # left button is throttle; the cursor's height picks lanes
        if self.race_mode and p.button is None and swipe_ok:
            dy = y - p.swipe_y
            if dy <= -SWIPE_STEP:
                self._edge["lane_up"] = True
                p.swipe_y = y
            elif dy >= SWIPE_STEP:
                self._edge["lane_down"] = True
                p.swipe_y = y
        elif self.race_mode and p.button in ("left", "right", "a", "b"):
            # thumbs slide between neighbouring buttons
            for b in self.buttons:
                if b.name != "pause" and b.hit(x, y, pad=4):
                    p.button = b.name
                    break
        self.pointer_events.append(("move", pid, x, y))

    def _up(self, pid, x, y):
        p = self.pointers.pop(pid, None)
        self.pointer_events.append(("up", pid, x, y))
        if p and not p.moved:
            self.pointer_events.append(("tap", pid, x, y))

    # -- queries ---------------------------------------------------------------
    def taps(self):
        return [(x, y) for k, _, x, y in self.pointer_events if k == "tap"]

    def touch_held(self, name):
        return any(p.button == name for p in self.pointers.values())

    @property
    def mouse_enabled(self):
        """Mouse buttons drive throttle/turbo (desktop, mouse steering on)."""
        return bool(self.settings.get("mouse_steer", "button")) and not self.touch_seen

    @property
    def button_mode(self):
        """Mouse "button" scheme: the button pulls up mid-air, the cursor only picks lanes."""
        return self.mouse_enabled and self.settings.get("mouse_steer", "button") == "button"

    @property
    def lean_mode(self):
        return "hold" if self.settings.get("mouse_steer") == "hold" else "angle"

    def _ground_lean_locked(self, bike):
        """True on the ground away from ramps when wheelies are ramps-only."""
        if bike is None or bike.airborne or self.settings.get("mouse_wheelie", "ramps") != "ramps":
            return False
        tr = bike.track
        ahead = bike.x + RAMP_LEAN_LOOKAHEAD * C.TILE_W
        return not any(tr.terrain_at(x, bike.lane_index) in RAMPS for x in (bike.x, ahead))

    @property
    def hover_lanes(self):
        """Hover lanes are on and the cursor owns lane choice right now."""
        return (self.mouse_enabled and self.mouse_active and self._hover_armed
                and (self.button_mode or self.settings.get("mouse_lanes", "hover") == "hover"))

    @property
    def sticky_anchor(self):
        """One-button throttle: home stays put between presses (see module doc)."""
        return self.mouse_enabled and not self.button_mode and self.settings.get("throttle_mode") == "one"

    @property
    def anchor_charge(self):
        """0..1 progress of a press that will move home, or None."""
        if self._press is None:
            return None
        return min(1.0, self._press_ticks / ANCHOR_HOLD_TICKS)

    def _update_sticky_press(self):
        """Count a still, held press; once it has charged, home moves there."""
        if self._press is None:
            return
        px, py = self._press
        mx, my = self.mouse_pos
        if abs(mx - px) > TAP_SLOP or abs(my - py) > TAP_SLOP:
            self._press = None                 # the press became a steer
            return
        if self.anchor is not None and math.hypot(px - self.anchor[0], py - self.anchor[1]) < ANCHOR_MIN_DIST:
            self._press = None                 # already home
            return
        self._press_ticks += 1
        if self._press_ticks >= ANCHOR_HOLD_TICKS:
            self._press = None
            self.set_anchor(px, py)

    @property
    def mouse_steering(self):
        """Cursor drives lean/lanes: anchored by a click, and used more recently than keys.

        Deliberately does not require mouse focus: if the cursor slips out of the
        window, steering holds its last lean/lane instead of dropping to neutral.
        (Never grab input here: pygame turns grab + hidden cursor into relative
        mouse mode, which scrambles cursor positions under WSLg.)"""
        return self.mouse_enabled and self.mouse_active and self.anchor is not None

    def set_anchor(self, x, y):
        self.anchor = (x, y)
        self.anchor_lane = None        # filled from the rider on the next tick
        self.mouse_lean = 0
        self.mouse_lane = None
        self.mouse_active = True
        self._hover_armed = True
        self._reset_air()              # a mid-air click starts the lean afresh too

    def recenter_anchor(self):
        """After a crash recovery: move home to the cursor (rider's current lane),
        so the player doesn't have to find the old home again. Only once the mouse
        has been steering this race (an anchor exists)."""
        if self.anchor is None or not self.mouse_enabled:
            return
        self._press = None
        self.set_anchor(*self.mouse_pos)

    def reset_mouse(self):
        """Forget the anchor (race start / end)."""
        self.anchor = None
        self.anchor_lane = None
        self.mouse_lean = 0
        self.mouse_lane = None
        self._mouse_held.clear()
        self._press = None
        self._hover_armed = False
        self._reset_air()
        self.button_air.reset()

    def _reset_air(self):
        self.air_base = None
        self.air_target = None

    def _lean_steps(self):
        return AIM_MAX_STEPS if self.lean_mode == "angle" else 1

    @staticmethod
    def _lean_sizes(air):
        """(dead zone, step, hysteresis) in px: tighter mid-air in angle mode."""
        return (AIR_LEAN_DEAD, AIR_LEAN_STEP, AIR_LEAN_HYST) if air else (LEAN_DEAD, LEAN_STEP, LEAN_HYST)

    @staticmethod
    def _zone(dx, n, dead=LEAN_DEAD, step=LEAN_STEP):
        a = abs(dx)
        if a <= dead:
            return 0
        z = min(n, 1 + int((a - dead) // step))
        return z if dx > 0 else -z

    def _update_mouse_lean(self, air=False):
        n = self._lean_steps()
        dead, step, hyst = self._lean_sizes(air)
        dx = self.mouse_pos[0] - self.anchor[0]
        z = self._zone(dx, n, dead, step)
        # Hysteresis: only switch once the cursor is hyst px inside the new zone.
        if z != self.mouse_lean and (self._zone(dx - hyst, n, dead, step) == z
                                     == self._zone(dx + hyst, n, dead, step)):
            self.mouse_lean = z

    def _update_air_aim(self, bike):
        """Angle mode, mid-air: the step out from home aims relative to the angle at exit."""
        z = self.mouse_lean
        if z == 0:                 # home: let the nose drift, forget the base
            self._reset_air()
            return
        if self.air_base is None:
            self.air_base = bike.angle
        self.air_target = max(-85.0, min(85.0, self.air_base - z * AIM_STEP_DEG))

    def lane_center_y(self, lane):
        """Screen y of a lane's band centre relative to home."""
        return self.anchor[1] + (lane - self.anchor_lane) * LANE_BAND

    def _update_mouse_lane(self, bike):
        if self.anchor_lane is None:
            self.anchor_lane = bike.lane
            self.mouse_lane = bike.lane
        f = self.anchor_lane + (self.mouse_pos[1] - self.anchor[1]) / LANE_BAND
        f = max(-0.5, min(C.LANES - 0.5, f))      # past the edge lanes: just clamp
        cur = self.mouse_lane
        if cur is not None and abs(f - cur) < 0.5 + LANE_HYST / LANE_BAND:
            return
        self.mouse_lane = max(0, min(C.LANES - 1, int(round(f))))

    def _update_hover_lane(self, bike):
        """Hover lanes: the lane whose drawn band is under the cursor. Bands rise
        with the ground under the cursor (ramps), never sink into pits.
        Only a moving cursor picks a new lane: with the cursor still, the track
        scrolling or rising under it (ramps, a split bridge's skyway) never
        steers you, so you stay where you pointed."""
        if self.mouse_lane is not None and self.mouse_pos == getattr(self, "_hover_seen", None):
            return
        self._hover_seen = self.mouse_pos
        mx, my = self.mouse_pos
        wx = bike.x + self.cam_lead + (mx - C.BIKE_SCREEN_X)
        tr = bike.track
        if tr.has_split:
            # Split bridge: the back lanes sit higher, so find the band under the
            # cursor lane by lane (front lanes drawn on top win).
            f = None
            for lane in reversed(range(C.LANES)):
                top = C.lane_y(lane) - max(0.0, tr.ground(wx, lane))
                if top <= my < top + C.LANE_SPACING:
                    f = float(lane)
                    break
            if f is None:
                f = (my + max(0.0, tr.ground(wx)) - C.LANE_BASE_Y) / C.LANE_SPACING - 0.5
        else:
            g = max(0.0, tr.ground(wx))
            f = (my + g - C.LANE_BASE_Y) / C.LANE_SPACING - 0.5    # lane centres at whole numbers
        f = max(-0.5, min(C.LANES - 0.5, f))
        cur = self.mouse_lane
        if cur is not None and abs(f - cur) < 0.5 + HOVER_HYST / C.LANE_SPACING:
            return
        self.mouse_lane = max(0, min(C.LANES - 1, int(round(f))))

    def race_controls(self, bike=None):
        k = pygame.key.get_pressed()
        c = Controls(
            a=k[pygame.K_z] or k[pygame.K_j] or k[pygame.K_SPACE] or self.touch_held("a"),
            b=k[pygame.K_x] or k[pygame.K_k] or self.touch_held("b"),
            left=k[pygame.K_LEFT] or k[pygame.K_a] or self.touch_held("left"),
            right=k[pygame.K_RIGHT] or k[pygame.K_d] or self.touch_held("right"),
            lane_up=self._edge["lane_up"],
            lane_down=self._edge["lane_down"],
        )
        if self.button_mode:
            return self._button_controls(c, bike)
        driving = False
        if self.mouse_enabled:
            m = pygame.mouse.get_pressed()
            c.a = c.a or m[0]
            c.b = c.b or m[2]
            driving = bool(m[0] or m[2])
            if self.sticky_anchor:
                if driving:
                    self._update_sticky_press()
                else:
                    self._press = None
                driving = True             # the cursor steers with the button up too
        self.mouse_driving = self.mouse_steering and driving
        hover = self.hover_lanes and bike is not None
        if not hover and self.settings.get("mouse_lanes", "hover") == "hover" and not self.mouse_driving:
            self.mouse_lane = None         # keys took over: forget the hovered lane
        self.lean_locked = False
        if self.mouse_driving:
            air_aim = self.lean_mode == "angle" and bike is not None and bike.airborne
            if self._ground_lean_locked(bike):
                # Flat ground, ramps-only wheelies: home slides sideways with the
                # cursor, so horizontal movement never leans (lanes still work).
                self.anchor = (self.mouse_pos[0], self.anchor[1])
                self.mouse_lean = 0
                self.lean_locked = True
            self._update_mouse_lean(air_aim)
            if air_aim:
                self._update_air_aim(bike)
            elif bike is not None:
                self._reset_air()      # on the ground: the next take-off starts fresh
            if air_aim and self.air_target is not None:
                # Steer the nose to the aimed angle, then hold it there.
                tol = bike.stats.pitch_rate / 2
                c.left = c.left or bike.angle < self.air_target - tol
                c.right = c.right or bike.angle > self.air_target + tol
            elif not air_aim:
                c.left = c.left or self.mouse_lean < 0
                c.right = c.right or self.mouse_lean > 0
            if bike is not None and not hover:
                self._update_mouse_lane(bike)
        else:
            # Buttons up: the cursor is free to move to a new spot without steering.
            # The next press drops a fresh anchor there (see handle()).
            self.mouse_lean = 0
            if not hover:
                self.mouse_lane = None
            self._reset_air()
        if hover:
            self._update_hover_lane(bike)
        if bike is not None and self.mouse_lane is not None and (hover or self.mouse_driving):
            # One edge per tick until the rider is in the aimed lane; the bike
            # ignores edges mid-air, so the change lands as soon as it touches down.
            if self.mouse_lane < bike.lane:
                c.lane_up = True
            elif self.mouse_lane > bike.lane:
                c.lane_down = True
        return c

    def _button_controls(self, c, bike):
        """Mouse "button" scheme (see button_air.py): no anchor, no mouse lean."""
        m = pygame.mouse.get_pressed()
        one = self.settings.get("throttle_mode") == "one"
        # one-button mode has no turbo: either button is the one button
        self.button_air.apply(c, bool(m[0] or (one and m[2])), bool(m[2] and not one), bike, one)
        self.mouse_driving = False
        self.mouse_lean = 0
        self.lean_locked = False
        self._reset_air()
        if self.hover_lanes and bike is not None:
            self._update_hover_lane(bike)
            if self.mouse_lane < bike.lane:
                c.lane_up = True
            elif self.mouse_lane > bike.lane:
                c.lane_down = True
        else:
            self.mouse_lane = None
        return c

    def consume_edges(self):
        self._edge["lane_up"] = False
        self._edge["lane_down"] = False

    def pause_tapped(self):
        if not self.show_touch:
            return False
        b = self.buttons[-1]
        return any(b.hit(x, y) for x, y in self.taps())

    def tilt(self, ctl, bike):
        """Lean being applied, for the indicator at the rider: (direction, level,
        max level). direction -1 = back (nose up), +1 = forward, 0 = none. Mouse
        aim mid-air (angle mode) has one level per aim step; everything else
        (keys, touch, hold mode, ground wheelies) is a single level."""
        if self.mouse_driving and not self.lean_locked and self.mouse_lean:
            z = self.mouse_lean
            if self.lean_mode == "angle" and bike is not None and bike.airborne:
                return (-1 if z < 0 else 1), abs(z), AIM_MAX_STEPS
            return (-1 if z < 0 else 1), 1, 1
        if ctl is not None and ctl.left != ctl.right:
            return (-1 if ctl.left else 1), 1, 1
        return 0, 0, 1

    # -- drawing ------------------------------------------------------------------
    def draw_mouse_guide(self, surf, bike_pos=None, airborne=False):
        """Anchor, lean zones, reticle and aimed lane while steering; the lane
        ladder around home only with the "Lane guide" setting on."""
        if not (self.mouse_steering or self.hover_lanes):
            return
        mx, my = self.mouse_pos
        # aimed lane: chevron just behind the rider
        col = (240, 240, 250) if self.mouse_lean == 0 else (120, 220, 255) if self.mouse_lean < 0 else (255, 150, 70)
        if self.mouse_lane is not None:
            bx = bike_pos[0] if bike_pos else C.BIKE_SCREEN_X   # camera may lead the rider
            ly = C.lane_y(self.mouse_lane) + C.LANE_SPACING / 2
            pygame.draw.polygon(surf, col, [(bx - 52, ly - 5), (bx - 44, ly), (bx - 52, ly + 5)])
        if not self.mouse_driving:
            # Buttons up: just a dim reticle so the (hidden) cursor can be repositioned.
            pygame.draw.circle(surf, (20, 18, 30), (int(mx), int(my)), 6, 3)
            pygame.draw.circle(surf, (170, 170, 185), (int(mx), int(my)), 5, 1)
            return
        ax, ay = self.anchor
        air = airborne and self.lean_mode == "angle"
        z = self.mouse_lean
        dim = (200, 200, 215)
        # zone edges around home: tall ticks = neutral zone, short ticks = air lean steps
        dead, step, _ = self._lean_sizes(air)
        for k in range(0 if self.lean_locked else self._lean_steps() if air else 1):
            off = dead + k * step
            h = 6 if k == 0 else 3
            for sx in (ax - off, ax + off):
                pygame.draw.line(surf, dim, (sx, my - h), (sx, my + h), 1)
        # lane ladder through the anchor: one dot per lane, the aimed one lit
        if (self.anchor_lane is not None and self.settings.get("lane_guide", False)
                and self.settings.get("mouse_lanes", "hover") != "hover"):
            for lane in range(C.LANES):
                y = int(self.lane_center_y(lane))
                on = lane == self.mouse_lane
                pygame.draw.circle(surf, (20, 18, 30), (int(ax), y), 4 if on else 3)
                pygame.draw.circle(surf, col if on else dim, (int(ax), y), 3 if on else 2)
        # sticky anchor: a ring fills around a held press that is about to become home
        charge = self.anchor_charge
        if charge is not None and self._press_ticks >= 6:      # skip quick heat taps
            px, py = self._press
            r = pygame.Rect(int(px) - 12, int(py) - 12, 24, 24)
            pygame.draw.circle(surf, (20, 18, 30), r.center, 12, 1)
            pygame.draw.arc(surf, (255, 225, 120), r, math.pi / 2,
                            math.pi / 2 + 2 * math.pi * charge, 3)
        # reticle with one arrow per lean step
        pygame.draw.circle(surf, (20, 18, 30), (int(mx), int(my)), 7, 3)
        pygame.draw.circle(surf, col, (int(mx), int(my)), 6, 2)
        d = 1 if z > 0 else -1
        for k in range(min(4, abs(z))):
            tip = mx + d * (16 + k * 6)
            pygame.draw.polygon(surf, col, [(tip, my), (tip - d * 6, my - 4), (tip - d * 6, my + 4)])

    def draw_touch(self, surf, font_fn):
        if not self.show_touch:
            return
        for b in self.buttons:
            held = self.touch_held(b.name)
            s = pygame.Surface((b.r * 2 + 2, b.r * 2 + 2), pygame.SRCALPHA)
            col = {"a": (90, 220, 110), "b": (255, 120, 60)}.get(b.name, (230, 230, 240))
            pygame.draw.circle(s, (*col, 150 if held else 70), (b.r + 1, b.r + 1), b.r)
            pygame.draw.circle(s, (*col, 220), (b.r + 1, b.r + 1), b.r, 2)
            surf.blit(s, (b.cx - b.r - 1, b.cy - b.r - 1))
            f = font_fn(26 if b.r > 20 else 16)
            img = f.render(b.label, False, (255, 255, 255))
            surf.blit(img, img.get_rect(center=(b.cx, b.cy)))
