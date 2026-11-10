"""Unified input: keyboard + multi-touch + mouse, in logical coordinates.

Race controls (decision Q2): on-screen buttons for throttle (A), turbo (B),
lean back / lean forward, plus vertical swipes anywhere else for lane changes.
Menus and the editor consume generic pointer events (down / move / up / tap).

Desktop mouse steering (setting "mouse_steer"): pressing a mouse button drops an
anchor (the "home" point) where the cursor is, pinned to the rider's current lane.
While throttle or turbo is held, the cursor's offset from home steers; the anchor
never moves on its own, so returning to home always means neutral and the
starting lane. With both buttons up the cursor moves freely, and the next press
sets a new home there.
  Lanes: each LANE_BAND px above/below home = one lane (clamped to the track).
  Lean:  within LEAN_DEAD px of home = neutral. Behind = back, ahead = forward.
    "angle" (default): on the ground, behind = wheelie. In the air, leaving
        neutral captures the current nose angle; each LEAN_STEP-px step out from
        home then aims AIM_STEP_DEG further up (behind) or down (ahead) from it.
        The rider rotates there and holds, so it turns the way the hand moves and
        can't over-rotate. Back at home the nose drifts down, as with no keys.
    "hold": any offset past LEAN_DEAD holds the lean (rate control, like keys).
Zones and lanes switch in discrete steps with hysteresis. Left button =
throttle, right button = turbo. Whichever device was used last (mouse movement
vs. lean/lane keys) owns steering.
"""
import pygame

import config as C
from bike import Controls

SWIPE_STEP = 26          # logical px of vertical drag per lane change
TAP_SLOP = 12            # max movement for a tap

LEAN_DEAD = 24           # px either side of home that counts as "no lean"
LEAN_STEP = 22           # px per extra lean step past the neutral zone (angle mode)
LEAN_HYST = 6            # px a cursor must be inside a new zone before it switches
AIM_MAX_STEPS = 6        # angle mode: furthest step counted (6 x 12 deg = 72 deg)
AIM_STEP_DEG = 12.0      # angle mode: nose turn per lean step, mid-air
LANE_BAND = 26           # px of cursor travel per lane (lanes are drawn 20 px apart)
LANE_HYST = 6            # extra px past a band edge before switching lane
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
        self._mouse_held = set()       # mouse buttons (1, 3) currently down
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
                    if not self._mouse_held:          # first button down: re-anchor here
                        self.set_anchor(x, y)
                    self._mouse_held.add(e.button)
                else:
                    self._mouse_held.discard(e.button)
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
        return bool(self.settings.get("mouse_steer", "angle")) and not self.touch_seen

    @property
    def lean_mode(self):
        return "hold" if self.settings.get("mouse_steer") == "hold" else "angle"

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
        self._reset_air()              # a mid-air click starts the lean afresh too

    def reset_mouse(self):
        """Forget the anchor (race start / end)."""
        self.anchor = None
        self.anchor_lane = None
        self.mouse_lean = 0
        self.mouse_lane = None
        self._mouse_held.clear()
        self._reset_air()

    def _reset_air(self):
        self.air_base = None
        self.air_target = None

    def _lean_steps(self):
        return AIM_MAX_STEPS if self.lean_mode == "angle" else 1

    @staticmethod
    def _zone(dx, n):
        a = abs(dx)
        if a <= LEAN_DEAD:
            return 0
        z = min(n, 1 + int((a - LEAN_DEAD) // LEAN_STEP))
        return z if dx > 0 else -z

    def _update_mouse_lean(self):
        n = self._lean_steps()
        dx = self.mouse_pos[0] - self.anchor[0]
        z = self._zone(dx, n)
        # Hysteresis: only switch once the cursor is LEAN_HYST px inside the new zone.
        if z != self.mouse_lean and self._zone(dx - LEAN_HYST, n) == z == self._zone(dx + LEAN_HYST, n):
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
        driving = False
        if self.mouse_enabled:
            m = pygame.mouse.get_pressed()
            c.a = c.a or m[0]
            c.b = c.b or m[2]
            driving = bool(m[0] or m[2])
        self.mouse_driving = self.mouse_steering and driving
        if self.mouse_driving:
            self._update_mouse_lean()
            air_aim = self.lean_mode == "angle" and bike is not None and bike.airborne
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
            if bike is not None:
                self._update_mouse_lane(bike)
                # One edge per tick until the rider is in the aimed lane; the bike
                # ignores edges mid-air, so the change lands as soon as it touches down.
                if self.mouse_lane < bike.lane:
                    c.lane_up = True
                elif self.mouse_lane > bike.lane:
                    c.lane_down = True
        else:
            # Buttons up: the cursor is free to move to a new spot without steering.
            # The next press drops a fresh anchor there (see handle()).
            self.mouse_lean = 0
            self.mouse_lane = None
            self._reset_air()
        return c

    def consume_edges(self):
        self._edge["lane_up"] = False
        self._edge["lane_down"] = False

    def pause_tapped(self):
        if not self.show_touch:
            return False
        b = self.buttons[-1]
        return any(b.hit(x, y) for x, y in self.taps())

    # -- drawing ------------------------------------------------------------------
    def draw_mouse_guide(self, surf, bike_pos=None, airborne=False):
        """Anchor, lean zones, lane ladder, reticle and aimed nose angle while steering."""
        if not self.mouse_steering:
            return
        import math
        mx, my = self.mouse_pos
        if not self.mouse_driving:
            # Buttons up: just a dim reticle so the (hidden) cursor can be repositioned.
            pygame.draw.circle(surf, (20, 18, 30), (int(mx), int(my)), 6, 3)
            pygame.draw.circle(surf, (170, 170, 185), (int(mx), int(my)), 5, 1)
            return
        ax, ay = self.anchor
        air = airborne and self.lean_mode == "angle"
        z = self.mouse_lean
        col = (240, 240, 250) if z == 0 else (120, 220, 255) if z < 0 else (255, 150, 70)
        dim = (200, 200, 215)
        # zone edges around home: tall ticks = neutral zone, short ticks = air lean steps
        for k in range(self._lean_steps() if air else 1):
            off = LEAN_DEAD + k * LEAN_STEP
            h = 6 if k == 0 else 3
            for sx in (ax - off, ax + off):
                pygame.draw.line(surf, dim, (sx, my - h), (sx, my + h), 1)
        # lane ladder through the anchor: one dot per lane, the aimed one lit
        if self.anchor_lane is not None:
            for lane in range(C.LANES):
                y = int(self.lane_center_y(lane))
                on = lane == self.mouse_lane
                pygame.draw.circle(surf, (20, 18, 30), (int(ax), y), 4 if on else 3)
                pygame.draw.circle(surf, col if on else dim, (int(ax), y), 3 if on else 2)
        # aimed lane: chevron just behind the rider
        if self.mouse_lane is not None:
            bx = C.BIKE_SCREEN_X
            ly = C.lane_y(self.mouse_lane) + C.LANE_SPACING / 2
            pygame.draw.polygon(surf, col, [(bx - 52, ly - 5), (bx - 44, ly), (bx - 52, ly + 5)])
        # aimed nose angle: a dashed line through the rider while airborne
        aim = self.air_target if air else None
        if aim is not None and bike_pos:
            bx, by = bike_pos
            by -= 8
            dx, dy = math.cos(math.radians(aim)), -math.sin(math.radians(aim))
            for t in range(-26, 30, 8):
                p0 = (bx + dx * t, by + dy * t)
                p1 = (bx + dx * (t + 4), by + dy * (t + 4))
                pygame.draw.line(surf, (20, 18, 30), p0, p1, 4)
                pygame.draw.line(surf, col, p0, p1, 2)
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
